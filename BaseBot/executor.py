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
    WALLETS_COUNT, WETH_ADDRESS, STATE_FILE,
)
from overrides import get_param
import rpc_client
import wallet_manager
import token_pool
import stranger_pool
import scheduler
import swap_engine
import ledger
from queue import Queue, Empty

logger = logging.getLogger(__name__)

# 全局停止信号
STOP_EVENT = Event()

# 紧急事件队列（TG「立即执行」按钮用）
# 每一项是 {"wallet": int, "type": "swap"/"buy"/"sell"/"transfer"/"claim_fee"}
_MANUAL_QUEUE: Queue = Queue()

# 开关：各类事件是否启用（TG 可单独关闭）
_ENABLED = {
    "swap":      True,
    "transfer":  True,
    "claim_fee": True,
}

# 对外暴露的共享状态快照（供 TG 查询）
_CONTEXT = {
    "w3":          None,
    "wallets":     [],
    "all_addrs":   set(),
    "tokens":      [],
    "allocation":  {},
    "strangers":   [],
}


def enqueue_manual(wallet_idx: int, event_type: str) -> bool:
    """TG 触发立即执行。event_type: swap/buy/sell/transfer/claim_fee。"""
    if event_type not in ("swap", "buy", "sell", "transfer", "claim_fee"):
        return False
    _MANUAL_QUEUE.put({"wallet": wallet_idx, "type": event_type})
    logger.info(f"[Executor] 手动事件入队: 钱包#{wallet_idx} {event_type}")
    return True


def set_enabled(event_type: str, enabled: bool) -> bool:
    if event_type not in _ENABLED:
        return False
    _ENABLED[event_type] = enabled
    logger.info(f"[Executor] {event_type} → {'ENABLED' if enabled else 'DISABLED'}")
    return True


def get_enabled() -> dict:
    return dict(_ENABLED)


def refresh_tokens() -> int:
    """TG 触发：重新拉取代币池并重新洗牌分配。"""
    tokens = token_pool.fetch_top_tokens()
    _CONTEXT["tokens"]     = tokens
    _CONTEXT["allocation"] = token_pool.allocate_tokens_to_wallets(tokens, WALLETS_COUNT)
    logger.info(f"[Executor] 代币池已刷新，共 {len(tokens)} 个")
    return len(tokens)


def refresh_strangers() -> int:
    """TG 触发：重新构建陌生地址池。"""
    w3 = _CONTEXT.get("w3")
    if not w3:
        return 0
    addrs = _CONTEXT.get("all_addrs", set())
    pool  = stranger_pool.build_stranger_pool(addrs, w3)
    _CONTEXT["strangers"] = pool
    return len(pool)


def get_context() -> dict:
    """返回当前运行时上下文（供 TG 面板只读查询）。"""
    return {
        "wallet_count":   len(_CONTEXT.get("wallets", [])),
        "token_count":    len(_CONTEXT.get("tokens", [])),
        "stranger_count": len(_CONTEXT.get("strangers", [])),
        "allocation":     {
            widx: [t["symbol"] for t in toks]
            for widx, toks in _CONTEXT.get("allocation", {}).items()
        },
    }


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
    lo = float(get_param("TX_AMOUNT_MIN_ETH") or 0.000001)
    hi = float(get_param("TX_AMOUNT_MAX_ETH") or 0.000003)
    return round(random.uniform(lo, hi), 8)


def _handle_swap(w3, wallet: dict, tokens_allocated: list[dict],
                 forced_action: str = None) -> bool:
    """
    执行一次 swap。forced_action: "buy"/"sell"/None(随机)。
    """
    widx = wallet["index"]
    holdings = ledger.get_today_holdings(widx)
    holding_tokens = [
        addr for addr, info in holdings.items()
        if info.get("balance", 0) > 0
    ]

    if forced_action in ("buy", "sell"):
        action = forced_action
    elif not holding_tokens or random.random() < 0.5:
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
    """转账某代币到陌生地址。比例由 overrides.TRANSFER_PCT 控制。"""
    widx = wallet["index"]
    holdings = ledger.get_today_holdings(widx)

    candidates = [
        (addr, info) for addr, info in holdings.items()
        if info.get("balance", 0) > 0 and addr.lower() != WETH_ADDRESS.lower()
    ]
    if not candidates:
        logger.info(f"[Executor] 钱包 #{widx} 无可转代币，跳过 transfer")
        return False

    transfer_pct = float(get_param("TRANSFER_PCT") or 0.30)
    token_addr, info = random.choice(candidates)
    decimals   = swap_engine.get_token_decimals(w3, token_addr)
    amount_raw = int(info["balance"] * transfer_pct * (10 ** decimals))
    if amount_raw == 0:
        return False

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
            to_addr, info["balance"] * transfer_pct, tx_hash,
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
    logger.info(f"[Executor] 代币已分配: 每钱包约 {len(tokens) // max(len(wallets),1)} 种")

    # 3. 构建陌生地址池
    strangers = stranger_pool.build_stranger_pool(all_wallet_addrs, w3)

    # 4. 确保今日时间表存在
    events = scheduler.ensure_today_schedule()
    logger.info(f"[Executor] 今日待执行事件: {len(events)}")

    # 5. 共享上下文给 TG 面板
    _CONTEXT.update({
        "w3":         w3,
        "wallets":    wallets,
        "all_addrs":  all_wallet_addrs,
        "tokens":     tokens,
        "allocation": allocation,
        "strangers":  strangers,
    })

    # 6. 主循环
    last_schedule_date = datetime.now().date()

    while not STOP_EVENT.is_set():
        try:
            now = datetime.now()

            # 跨日：重置一切
            if now.date() != last_schedule_date:
                logger.info("[Executor] 跨日，重新生成时间表 & 刷新代币池")
                events = scheduler.generate_daily_schedule(now.date())
                scheduler.save_schedule(events)
                tokens     = token_pool.fetch_top_tokens()
                allocation = token_pool.allocate_tokens_to_wallets(tokens, len(wallets))
                strangers  = stranger_pool.build_stranger_pool(all_wallet_addrs, w3)
                _CONTEXT.update({
                    "tokens": tokens, "allocation": allocation, "strangers": strangers,
                })
                last_schedule_date = now.date()

            # ── 优先处理 TG 手动触发事件（不受暂停影响）─────
            try:
                while True:
                    manual = _MANUAL_QUEUE.get_nowait()
                    widx   = manual["wallet"]
                    if widx < 0 or widx >= len(wallets):
                        continue
                    wallet = wallets[widx]
                    typ    = manual["type"]
                    try:
                        if typ == "swap":
                            _handle_swap(w3, wallet, _CONTEXT["allocation"].get(widx, []))
                        elif typ == "buy":
                            _handle_swap(w3, wallet, _CONTEXT["allocation"].get(widx, []), forced_action="buy")
                        elif typ == "sell":
                            _handle_swap(w3, wallet, _CONTEXT["allocation"].get(widx, []), forced_action="sell")
                        elif typ == "transfer":
                            _handle_transfer(w3, wallet, all_wallet_addrs, _CONTEXT["strangers"])
                        elif typ == "claim_fee":
                            _handle_claim_fee(w3, wallet)
                    except Exception as e:
                        logger.error(f"[Executor] 手动事件异常: {e}")
            except Empty:
                pass

            # ── 暂停则空转（但仍处理手动队列）────────────────
            if not is_running():
                time.sleep(5)
                continue

            # ── 到期事件（从最新 schedule 读）────────────────
            events = scheduler.load_schedule() or events
            now_iso = now.isoformat()
            due = [e for e in events if e["time"] <= now_iso]

            if due:
                for ev in due:
                    if STOP_EVENT.is_set() or not is_running():
                        break

                    typ  = ev["type"]
                    # 检查该类事件是否被 TG 禁用
                    if not _ENABLED.get(typ, True):
                        # 不执行但从表中移除，避免堆积
                        scheduler.remove_completed_event(ev["time"], ev["wallet"], typ)
                        continue

                    widx   = ev["wallet"]
                    wallet = wallets[widx]
                    try:
                        if typ == "swap":
                            _handle_swap(w3, wallet, _CONTEXT["allocation"].get(widx, []))
                        elif typ == "transfer":
                            _handle_transfer(w3, wallet, all_wallet_addrs, _CONTEXT["strangers"])
                        elif typ == "claim_fee":
                            _handle_claim_fee(w3, wallet)
                    except Exception as e:
                        logger.error(f"[Executor] 事件执行异常: {e}")

                    scheduler.remove_completed_event(ev["time"], ev["wallet"], typ)

            time.sleep(5)

        except Exception as e:
            logger.error(f"[Executor] 主循环异常: {e}")
            time.sleep(30)
            rpc_client.reset_connection()
            try:
                w3 = rpc_client.get_w3()
                _CONTEXT["w3"] = w3
            except Exception:
                pass

    logger.info("[Executor] 主循环已退出")


def stop():
    STOP_EVENT.set()
