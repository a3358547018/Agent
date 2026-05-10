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

生成的时间表格式：
  [
    {"time": "2025-01-01T00:15:30", "wallet": 3, "type": "swap"},
    {"time": "2025-01-01T00:18:42", "wallet": 7, "type": "swap"},
    {"time": "2025-01-01T01:05:12", "wallet": 3, "type": "transfer"},
    {"time": "2025-01-01T02:33:01", "wallet": 3, "type": "claim_fee"},
    ...
  ]
"""

import json
import random
import logging
from pathlib import Path
from datetime import date, datetime, timedelta

from config import (
    WALLETS_COUNT, MIN_TX_PER_WALLET_DAY, MAX_TX_PER_WALLET_DAY,
    SCHEDULE_FILE,
)

logger = logging.getLogger(__name__)

# 任何两笔交易之间的最小间隔（秒），避免同一时刻并发
MIN_GAP_SECONDS = 20


def _pick_unique_timestamps(n: int, day_start: datetime, day_end: datetime, existing: set[int]) -> list[datetime]:
    """
    在 [day_start, day_end) 区间内生成 n 个不重叠的时间点。
    existing: 已占用的时间戳（秒级），新时间点需与之相隔 MIN_GAP_SECONDS。
    """
    total_seconds = int((day_end - day_start).total_seconds())
    picked = []
    attempts = 0
    max_attempts = n * 200

    while len(picked) < n and attempts < max_attempts:
        offset   = random.randint(0, total_seconds - 1)
        candidate = int((day_start + timedelta(seconds=offset)).timestamp())

        # 检查与已有时间点的间隔
        too_close = False
        for t in existing:
            if abs(candidate - t) < MIN_GAP_SECONDS:
                too_close = True
                break
        if not too_close:
            for p in picked:
                if abs(candidate - int(p.timestamp())) < MIN_GAP_SECONDS:
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
    """
    为当天生成完整时间表。
    返回按时间升序排列的事件列表。
    """
    target_date = target_date or date.today()
    day_start   = datetime.combine(target_date, datetime.min.time())
    day_end     = day_start + timedelta(days=1)

    all_events   = []
    used_seconds = set()

    for widx in range(WALLETS_COUNT):
        # ── 1. Swap 交易（3-10 笔）───────────────────────────
        n_swaps = random.randint(MIN_TX_PER_WALLET_DAY, MAX_TX_PER_WALLET_DAY)
        swap_times = _pick_unique_timestamps(n_swaps, day_start, day_end, used_seconds)
        for t in swap_times:
            all_events.append({
                "time":   t.isoformat(),
                "wallet": widx,
                "type":   "swap",   # 具体是 buy 还是 sell 在执行时根据持仓决定
            })

        # ── 2. Transfer 事件（1 次，转 30% 代币到陌生地址）──
        transfer_times = _pick_unique_timestamps(1, day_start, day_end, used_seconds)
        for t in transfer_times:
            all_events.append({
                "time":   t.isoformat(),
                "wallet": widx,
                "type":   "transfer",
            })

        # ── 3. Claim V3 Fee 事件（1 次）──────────────────────
        claim_times = _pick_unique_timestamps(1, day_start, day_end, used_seconds)
        for t in claim_times:
            all_events.append({
                "time":   t.isoformat(),
                "wallet": widx,
                "type":   "claim_fee",
            })

    # 按时间排序
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
    with open(p, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "date":         events[0]["time"][:10] if events else "",
            "events":       events,
        }, f, indent=2, ensure_ascii=False)


def load_schedule() -> list[dict]:
    p = Path(SCHEDULE_FILE)
    if not p.exists():
        return []
    try:
        with open(p) as f:
            data = json.load(f)
        # 如果保存的日期不是今天，视为失效
        today = date.today().isoformat()
        if data.get("date") != today:
            return []
        return data.get("events", [])
    except Exception:
        return []


def ensure_today_schedule() -> list[dict]:
    """启动或每日首次调用时使用：有今日表就返回，没有就生成。"""
    events = load_schedule()
    if not events:
        events = generate_daily_schedule()
        save_schedule(events)
    return events


def remove_completed_event(event_time: str, wallet: int, event_type: str) -> None:
    """从时间表中移除已执行的事件（避免重启后重复执行）。"""
    events = load_schedule()
    events = [
        e for e in events
        if not (e["time"] == event_time and e["wallet"] == wallet and e["type"] == event_type)
    ]
    save_schedule(events)
