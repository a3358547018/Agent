"""
ledger.py — 交易账本

记录每个钱包每天的代币交易明细，用于：
  1. 决定转账 30% 时抽哪些代币
  2. Telegram 面板展示
  3. 统计分析
"""

import json
import logging
from pathlib import Path
from datetime import date, datetime
from threading import Lock

from config import LEDGER_FILE

logger = logging.getLogger(__name__)

_LOCK = Lock()


def _load() -> dict:
    p = Path(LEDGER_FILE)
    if not p.exists():
        return {}
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    p = Path(LEDGER_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def record_buy(wallet_idx: int, token_addr: str, token_symbol: str,
               amount_eth: float, amount_token: float, tx_hash: str) -> None:
    """记录一笔买入（ETH → Token）。"""
    with _LOCK:
        data  = _load()
        today = date.today().isoformat()
        key   = f"{today}:{wallet_idx}"
        data.setdefault(key, {"wallet": wallet_idx, "date": today, "tokens": {}, "txs": []})

        token_low = token_addr.lower()
        holdings  = data[key]["tokens"].setdefault(
            token_low,
            {"symbol": token_symbol, "balance": 0.0, "eth_spent": 0.0},
        )
        holdings["balance"]   += amount_token
        holdings["eth_spent"] += amount_eth

        data[key]["txs"].append({
            "type":     "buy",
            "token":    token_symbol,
            "address":  token_addr,
            "eth":      amount_eth,
            "amount":   amount_token,
            "tx_hash":  tx_hash,
            "time":     datetime.now().isoformat(),
        })
        _save(data)


def record_sell(wallet_idx: int, token_addr: str, token_symbol: str,
                amount_token: float, amount_eth: float, tx_hash: str) -> None:
    """记录一笔卖出（Token → ETH）。"""
    with _LOCK:
        data  = _load()
        today = date.today().isoformat()
        key   = f"{today}:{wallet_idx}"
        data.setdefault(key, {"wallet": wallet_idx, "date": today, "tokens": {}, "txs": []})

        token_low = token_addr.lower()
        if token_low in data[key]["tokens"]:
            data[key]["tokens"][token_low]["balance"] = max(
                0, data[key]["tokens"][token_low]["balance"] - amount_token
            )

        data[key]["txs"].append({
            "type":     "sell",
            "token":    token_symbol,
            "address":  token_addr,
            "amount":   amount_token,
            "eth":      amount_eth,
            "tx_hash":  tx_hash,
            "time":     datetime.now().isoformat(),
        })
        _save(data)


def record_transfer(wallet_idx: int, token_addr: str, token_symbol: str,
                    to_address: str, amount: float, tx_hash: str) -> None:
    """记录一笔转账到陌生地址。"""
    with _LOCK:
        data  = _load()
        today = date.today().isoformat()
        key   = f"{today}:{wallet_idx}"
        data.setdefault(key, {"wallet": wallet_idx, "date": today, "tokens": {}, "txs": []})

        token_low = token_addr.lower()
        if token_low in data[key]["tokens"]:
            data[key]["tokens"][token_low]["balance"] = max(
                0, data[key]["tokens"][token_low]["balance"] - amount
            )

        data[key]["txs"].append({
            "type":     "transfer",
            "token":    token_symbol,
            "address":  token_addr,
            "to":       to_address,
            "amount":   amount,
            "tx_hash":  tx_hash,
            "time":     datetime.now().isoformat(),
        })
        _save(data)


def record_claim_fee(wallet_idx: int, amount_eth: float, tx_hash: str) -> None:
    """记录一笔 V3 手续费领取。"""
    with _LOCK:
        data  = _load()
        today = date.today().isoformat()
        key   = f"{today}:{wallet_idx}"
        data.setdefault(key, {"wallet": wallet_idx, "date": today, "tokens": {}, "txs": []})
        data[key]["txs"].append({
            "type":     "claim_fee",
            "amount":   amount_eth,
            "tx_hash":  tx_hash,
            "time":     datetime.now().isoformat(),
        })
        _save(data)


# ── 查询接口 ─────────────────────────────────────────────────
def get_today_holdings(wallet_idx: int) -> dict:
    """返回某钱包今日持仓 {token_addr: {symbol, balance, ...}}。"""
    data  = _load()
    today = date.today().isoformat()
    key   = f"{today}:{wallet_idx}"
    return data.get(key, {}).get("tokens", {})


def get_today_txs(wallet_idx: int) -> list[dict]:
    data  = _load()
    today = date.today().isoformat()
    key   = f"{today}:{wallet_idx}"
    return data.get(key, {}).get("txs", [])


def get_today_summary() -> dict:
    """全体钱包今日汇总（给 TG 面板用）。"""
    data  = _load()
    today = date.today().isoformat()
    summary = {
        "date":         today,
        "total_txs":    0,
        "total_buys":   0,
        "total_sells":  0,
        "total_transfers": 0,
        "total_claims": 0,
        "wallets":      {},
    }
    for key, rec in data.items():
        if not key.startswith(today):
            continue
        widx = rec.get("wallet")
        txs  = rec.get("txs", [])
        summary["wallets"][widx] = len(txs)
        for tx in txs:
            summary["total_txs"] += 1
            t = tx.get("type")
            if t == "buy":       summary["total_buys"]      += 1
            elif t == "sell":    summary["total_sells"]     += 1
            elif t == "transfer":summary["total_transfers"] += 1
            elif t == "claim_fee":summary["total_claims"]   += 1
    return summary
