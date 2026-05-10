"""
scheduler.py — 每日交易时间表生成器

核心逻辑：
  1. 每日 00:00 重新生成时间表
  2. 为 22 个钱包各分配 3-10 笔交易
  3. 所有交易时间点在一天内随机分布，且互不重叠（至少相隔 N 秒）
  4. 每个钱包独立时间机制（不是轮次切片）
  5. 为每个钱包额外安排：
       - 1 次转账事件（转 30% 某代币到陌生地址）
       - 1 次 V3 手续费领取事件
"""

import json
import random
import logging
from pathlib import Path
from datetime import date, datetime, timedelta
from threading import Lock

from config import WALLETS_COUNT, SCHEDULE_FILE
from overrides import get_param

logger = logging.getLogger(__name__)

# 默认最小间隔（秒），可被 overrides.MIN_GAP_SECONDS 覆盖
_DEFAULT_GAP = 20

_SCHEDULE_LOCK = Lock()


def _pick_unique_timestamps(n: int, day_start: datetime, day_end: datetime, existing: set[int]) -> list[datetime]:
    """在 [day_start, day_end) 内生成 n 个不重叠时间点。"""
    total_seconds = int((day_end - day_start).total_seconds())
    gap_s = int(get_param("MIN_GAP_SECONDS") or _DEFAULT_GAP)
    picked = []
    attempts = 0
    max_attempts = n * 200

    while len(picked) < n and attempts < max_attempts:
        offset    = random.randint(0, total_seconds - 1)
        candidate = int((day_start + timedelta(seconds=offset)).timestamp())

        too_close = False
        for t in existing:
            if abs(candidate - t) < gap_s:
                too_close = True
                break
        if not too_close:
            for p in picked:
                if abs(candidate - int(p.timestamp())) < gap_s:
                    too_close = True
                    break

        if not too_close:
            picked.append(datetime.fromtimestamp(candidate))
            existing.add(candidate)

        attempts += 1

    if len(picked) < n:
        logger.warning(f"[Scheduler] 仅生成 {len(picked)}/{n} 个时间点")

    return sorted(picked)


def generate_daily_schedule(target_date: date = None) -> list[dict]:
    """为当天生成完整时间表，按时间升序。"""
    target_date = target_date or date.today()
    day_start   = datetime.combine(target_date, datetime.min.time())
    day_end     = day_start + timedelta(days=1)

    # 从 overrides 读取最新参数（TG 可实时调整）
    min_tx      = int(get_param("MIN_TX_PER_WALLET_DAY") or 3)
    max_tx      = int(get_param("MAX_TX_PER_WALLET_DAY") or 10)
    n_transfers = int(get_param("TRANSFERS_PER_WALLET_DAY") or 1)
    n_claims    = int(get_param("CLAIMS_PER_WALLET_DAY")    or 1)
    if max_tx < min_tx:
        max_tx = min_tx

    all_events   = []
    used_seconds = set()

    for widx in range(WALLETS_COUNT):
        n_swaps = random.randint(min_tx, max_tx)
        for t in _pick_unique_timestamps(n_swaps, day_start, day_end, used_seconds):
            all_events.append({"time": t.isoformat(), "wallet": widx, "type": "swap"})

        for t in _pick_unique_timestamps(n_transfers, day_start, day_end, used_seconds):
            all_events.append({"time": t.isoformat(), "wallet": widx, "type": "transfer"})

        for t in _pick_unique_timestamps(n_claims, day_start, day_end, used_seconds):
            all_events.append({"time": t.isoformat(), "wallet": widx, "type": "claim_fee"})

    all_events.sort(key=lambda e: e["time"])
    logger.info(
        f"[Scheduler] 生成 {target_date} 时间表: "
        f"swap={sum(1 for e in all_events if e['type']=='swap')}, "
        f"transfer={sum(1 for e in all_events if e['type']=='transfer')}, "
        f"claim={sum(1 for e in all_events if e['type']=='claim_fee')}, "
        f"total={len(all_events)}"
    )
    return all_events


def save_schedule(events: list[dict]) -> None:
    p = Path(SCHEDULE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    with _SCHEDULE_LOCK:
        with open(p, "w") as f:
            json.dump({
                "generated_at": datetime.now().isoformat(),
                "date":         events[0]["time"][:10] if events else date.today().isoformat(),
                "events":       events,
            }, f, indent=2, ensure_ascii=False)


def load_schedule() -> list[dict]:
    p = Path(SCHEDULE_FILE)
    if not p.exists():
        return []
    try:
        with _SCHEDULE_LOCK:
            with open(p) as f:
                data = json.load(f)
        today = date.today().isoformat()
        if data.get("date") != today:
            return []
        return data.get("events", [])
    except Exception:
        return []


def ensure_today_schedule() -> list[dict]:
    events = load_schedule()
    if not events:
        events = generate_daily_schedule()
        save_schedule(events)
    return events


def remove_completed_event(event_time: str, wallet: int, event_type: str) -> None:
    events = load_schedule()
    events = [
        e for e in events
        if not (e["time"] == event_time and e["wallet"] == wallet and e["type"] == event_type)
    ]
    save_schedule(events)


# ══════════════════════════════════════════════════════════════
#  TG 面板辅助函数
# ══════════════════════════════════════════════════════════════

def clear_schedule() -> int:
    """清空今日时间表。返回清掉的事件数。"""
    events = load_schedule()
    n = len(events)
    save_schedule([])
    logger.info(f"[Scheduler] 已清空今日时间表，共 {n} 个事件")
    return n


def remove_events_by_wallet(wallet_idx: int) -> int:
    """移除指定钱包的所有待执行事件。"""
    events = load_schedule()
    before = len(events)
    events = [e for e in events if e["wallet"] != wallet_idx]
    save_schedule(events)
    return before - len(events)


def remove_events_by_type(event_type: str) -> int:
    """移除指定类型的所有待执行事件（swap/transfer/claim_fee）。"""
    events = load_schedule()
    before = len(events)
    events = [e for e in events if e["type"] != event_type]
    save_schedule(events)
    return before - len(events)


def get_stats() -> dict:
    """返回时间表统计信息（供 TG 展示）。"""
    events = load_schedule()
    now_iso = datetime.now().isoformat()
    pending = [e for e in events if e["time"] > now_iso]
    done    = [e for e in events if e["time"] <= now_iso]

    by_type = {"swap": 0, "transfer": 0, "claim_fee": 0}
    by_wallet = {}
    for e in pending:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        by_wallet[e["wallet"]] = by_wallet.get(e["wallet"], 0) + 1

    return {
        "total":     len(events),
        "pending":   len(pending),
        "past":      len(done),
        "by_type":   by_type,
        "by_wallet": by_wallet,
        "next":      pending[0] if pending else None,
    }
