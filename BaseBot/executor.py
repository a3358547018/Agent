"""
executor.py — 交易执行主循环

核心逻辑：
  1. 加载今日时间表
  2. 主循环每 10 秒检查一次到期事件
  3. 到期事件分派给对应处理器：
       - swap       → buy/sell 随机决定
       - transfer   → 转 30% 某代币到陌生地址（排除自家钱包）
       - claim_fee  → 领取 V3 position 手续费
  4. 支持暂停/恢复（通过 state.json 控制）
"""

import json
import time
import random
import logging
from pathlib import Path
from datetime import datetime
from threading import Event

from config import (
    WALLETS_COUNT, TX_AMOUNT_MIN_ETH, TX_AMOUNT_MAX_ETH,
    TRANSFER_PCT, WETH_ADDRESS, STATE_FILE,
)
import rpc_client
import wallet_manager
import token_pool
import stranger_pool
import scheduler
import swap_engine
import ledger

logger = logging.getLogger(__name__)

# 全局停止信号
STOP_EVENT = Event()


# ══════════════════════════════════════════════════════════════
#  运行状态管理（暂停/运行，供 TG 控制）
# ══════════════════════════════════════════════════════════════

def _load_state() -> dict:
    p = Path(STATE_FILE)
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return {"running": True, "started_at": datetime.now().isoformat()}


def _save_state(state: dict) -> None:
    p = Path(STATE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(state, f, indent=2)


def set_running(running: bool) -> None:
    state = _load_state()
    state["running"]    = running
    state["changed_at"] = datetime.now().isoformat()
    _save_state(state)
    logger.info(f"[Executor] 运行状态 → {'RUNNING' if running else 'PAUSED'}")


def is_running() -> bool:
    return _load_state().get("running", True)


# ══════════════════════════════════════════════════════════════
#  事件处理器
# ══════════════════════════════════════════════════════════════

def _random_eth_amount() -> float:
    return round(random.uniform(TX_AMOUNT_MIN_ETH, TX_AMOUNT_MAX_ETH), 8)


def _handle_swap(w3, wallet: dict, tokens_allocated: list[dict]) -> bool:
    """
    执行一次 swap。根据当前持仓随机决定买入或卖出：
      - 无持仓 → 必须买入
      - 有持仓 → 50% 概率买 / 50% 概率卖
    """
    widx = wallet["index"]
    holdings = ledger.get_today_holdings(widx)
    # 过滤有余额的持仓
    holding_tokens = [
        addr for addr, info in holdings.items()
        if info.get("balance", 0) > 0
    ]

    # 决定买或卖
    if not holding_tokens or random.random() < 0.5:
        action = "buy"
    else:
        action = "sell"

    if action == "buy":
        if not tokens_allocated:
            logger.warning(f"[Executor] 钱包 #{widx} 无可用代币")
            return False
        tok = random.choice(tokens_allocated)
        eth_amount = _random_eth_amount()
        tx_hash, amount_out = swap_engine.swap_eth_to_token(
            w3, wallet["private_key"], wallet["address"],
            tok["address"], eth_amount,
        )
        if tx_hash:
            decimals = swap_engine.get_token_decimals(w3, tok["address"])
            ledger.record_buy(
                widx, tok["address"], tok["symbol"],
                eth_amount, amount_out / (10 ** decimals), tx_hash,
            )
            return True
        return False

    else:  # sell
        tok_addr = random.choice(holding_tokens)
        info     = holdings[tok_addr]
        decimals = swap_engine.get_token_decimals(w3, tok_addr)

        # 卖出持仓的 30-70%
        ratio      = random.uniform(0.3, 0.7)
        amount_raw = int(info["balance"] * ratio * (10 ** decimals))
        if amount_raw == 0:
            return False

        tx_hash, eth_out = swap_engine.swap_token_to_eth(
            w3, wallet["private_key"], wallet["address"],
            tok_addr, amount_raw,
        )
        if tx_hash:
            ledger.record_sell(
                widx, tok_addr, info["symbol"],
                info["balance"] * ratio,
                float(w3.from_wei(eth_out, "ether")),
                tx_hash,
            )
            return True
        return False


def _handle_transfer(w3, wallet: dict, all_wallet_addrs: set[str],
                     strangers: list[str]) -> bool:
    """
    转账 30% 某代币到陌生地址。
    约束：不能转给 22 个自家钱包，不能转 ETH，只能转已买入的 ERC20。
    """
    widx = wallet["index"]
    holdings = ledger.get_today_holdings(widx)

    # 筛选有余额的代币
    candidates = [
        (addr, info) for addr, info in holdings.items()
        if info.get("balance", 0) > 0 and addr.lower() != WETH_ADDRESS.lower()
    ]
    if not candidates:
        logger.info(f"[Executor] 钱包 #{widx} 无可转代币，跳过 transfer")
        return False

    token_addr, info = random.choice(candidates)
    decimals   = swap_engine.get_token_decimals(w3, token_addr)
    amount_raw = int(info["balance"] * TRANSFER_PCT * (10 ** decimals))
    if amount_raw == 0:
        return False

    # 选陌生地址
    to_addr = stranger_pool.random_stranger(strangers, exclude=all_wallet_addrs)
    if not to_addr:
        logger.warning("[Executor] 陌生地址池为空")
        return False

    tx_hash = swap_engine.transfer_token(
        w3, wallet["private_key"], wallet["address"],
        token_addr, to_addr, amount_raw,
    )
    if tx_hash:
        ledger.record_transfer(
            widx, token_addr, info["symbol"],
            to_addr, info["balance"] * TRANSFER_PCT, tx_hash,
        )
        return True
    return False


def _handle_claim_fee(w3, wallet: dict) -> bool:
    """领取 V3 手续费。"""
    widx = wallet["index"]
    ok, fail = swap_engine.collect_all_v3_fees(
        w3, wallet["private_key"], wallet["address"],
    )
    if ok > 0:
        ledger.record_claim_fee(widx, 0.0, f"collected_{ok}_positions")
    else:
        logger.info(f"[Executor] 钱包 #{widx} 无可领 V3 手续费")
    return True   # 即使无 position 也算已完成（避免反复重试）


# ══════════════════════════════════════════════════════════════
#  主循环
# ══════════════════════════════════════════════════════════════

def run_forever():
    """核心执行循环，跑在独立线程。"""
    logger.info("🚀 Base Bot Executor 启动")

    # 1. 加载钱包 & w3
    wallets = wallet_manager.load_wallets()
    if not wallets:
        logger.error("[Executor] 无有效钱包，退出")
        return

    w3 = rpc_client.get_w3()
    all_wallet_addrs = {w["address"] for w in wallets}

    # 2. 拉取代币池并分配
    tokens = token_pool.fetch_top_tokens()
    allocation = token_pool.allocate_tokens_to_wallets(tokens, len(wallets))
    logger.info(f"[Executor] 代币已分配: 每钱包约 {len(tokens) // len(wallets)} 种")

    # 3. 构建陌生地址池
    strangers = stranger_pool.build_stranger_pool(all_wallet_addrs, w3)

    # 4. 确保今日时间表存在
    events = scheduler.ensure_today_schedule()
    logger.info(f"[Executor] 今日待执行事件: {len(events)}")

    # 5. 主循环
    last_schedule_date = datetime.now().date()

    while not STOP_EVENT.is_set():
        try:
            # 检查是否跨日 → 重新生成时间表 & 刷新代币池
            now = datetime.now()
            if now.date() != last_schedule_date:
                logger.info("[Executor] 跨日，重新生成时间表 & 刷新代币池")
                events   = scheduler.generate_daily_schedule(now.date())
                scheduler.save_schedule(events)
                tokens   = token_pool.fetch_top_tokens()
                allocation = token_pool.allocate_tokens_to_wallets(tokens, len(wallets))
                strangers  = stranger_pool.build_stranger_pool(all_wallet_addrs, w3)
                last_schedule_date = now.date()

            # 暂停状态下空转
            if not is_running():
                time.sleep(10)
                continue

            # 重新读取 schedule（TG 可能改动）
            events = scheduler.load_schedule() or events

            # 找到所有到期事件（time <= now）
            now_iso = now.isoformat()
            due = [e for e in events if e["time"] <= now_iso]

            if due:
                # 按时间顺序执行
                for ev in due:
                    if STOP_EVENT.is_set() or not is_running():
                        break

                    widx   = ev["wallet"]
                    wallet = wallets[widx]
                    try:
                        if ev["type"] == "swap":
                            _handle_swap(w3, wallet, allocation.get(widx, []))
                        elif ev["type"] == "transfer":
                            _handle_transfer(w3, wallet, all_wallet_addrs, strangers)
                        elif ev["type"] == "claim_fee":
                            _handle_claim_fee(w3, wallet)
                    except Exception as e:
                        logger.error(f"[Executor] 事件执行异常: {e}")

                    # 从时间表移除
                    scheduler.remove_completed_event(ev["time"], ev["wallet"], ev["type"])

            time.sleep(10)

        except Exception as e:
            logger.error(f"[Executor] 主循环异常: {e}")
            time.sleep(30)
            # 尝试重连 RPC
            rpc_client.reset_connection()
            try:
                w3 = rpc_client.get_w3()
            except Exception:
                pass

    logger.info("[Executor] 主循环已退出")


def stop():
    STOP_EVENT.set()
