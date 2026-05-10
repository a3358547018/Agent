"""
main.py — 开源资源自动化 Agent 主入口

完整流程：
  抓取资源 → 去重 → 存迅雷网盘 → AI写推文 → 自动发推

运行方式：
  python main.py             # 启动定时调度
  python main.py --now       # 立即执行完整流程（调试）
  python main.py --crawl     # 只抓取，不存盘/发推
  python main.py --tweet     # 只发推（消费本地待发队列）
"""

import asyncio
import argparse
import json
import logging
import os
import time
import schedule
from datetime import datetime
from pathlib import Path

import crawler
import dedup
import thunder_drive
import ai_writer
import twitter_poster
from threading import Lock

# ── 日志配置 ─────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

# 待发推队列文件
PENDING_QUEUE = Path("data/pending_tweets.json")
_QUEUE_LOCK = Lock()


# ══════════════════════════════════════════════════════════════
#  队列管理（线程安全 + 原子写）
# ══════════════════════════════════════════════════════════════

def _load_queue() -> list:
    with _QUEUE_LOCK:
        if PENDING_QUEUE.exists():
            try:
                with open(PENDING_QUEUE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return []


def _save_queue(queue: list) -> None:
    PENDING_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with _QUEUE_LOCK:
        tmp = PENDING_QUEUE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)
        tmp.replace(PENDING_QUEUE)


def _append_to_queue(items: list) -> None:
    queue = _load_queue()
    queue.extend(items)
    _save_queue(queue)
    logger.info(f"[Queue] 加入待发队列 {len(items)} 条，当前队列共 {len(queue)} 条")


def _pop_from_queue(n: int = 5) -> list:
    """从队列头部取出 n 条，并更新队列文件。"""
    queue = _load_queue()
    batch = queue[:n]
    _save_queue(queue[n:])
    return batch


# ══════════════════════════════════════════════════════════════
#  核心任务
# ══════════════════════════════════════════════════════════════

async def run_crawl_pipeline() -> None:
    """
    任务①：抓取 → 去重 → 存迅雷网盘 → 加入待发队列
    建议每 6 小时执行一次。
    """
    logger.info("=" * 50)
    logger.info("▶ 开始执行【抓取存盘】任务")

    # 1. 抓取
    all_resources = await crawler.fetch_all_resources()
    if not all_resources:
        logger.info("  本次未抓取到任何资源，结束。")
        return

    # 2. 去重
    new_resources = dedup.filter_new(all_resources)
    if not new_resources:
        logger.info("  全部为重复资源，结束。")
        return

    # 3. 存迅雷网盘
    ok, fail = thunder_drive.save_resources_batch(new_resources)
    logger.info(f"  存盘完成: 成功 {ok} / 失败 {fail}")

    # 4. AI 生成推文
    resources_with_tweets = ai_writer.generate_tweets_batch(new_resources)

    # 5. 加入待发队列
    _append_to_queue(resources_with_tweets)
    logger.info("▶ 【抓取存盘】任务完成")


def run_tweet_pipeline() -> None:
    """
    任务②：从待发队列取出资源 → 发推
    建议每 30 分钟检查一次。
    """
    from config import TWITTER_MAX_TWEETS_PER_DAY
    batch = _pop_from_queue(n=TWITTER_MAX_TWEETS_PER_DAY)
    if not batch:
        logger.info("[发推] 待发队列为空，跳过。")
        return

    logger.info(f"[发推] 从队列取出 {len(batch)} 条，开始发推…")
    ok, unsent = twitter_poster.post_tweets_batch(batch)

    # 把未发出的退回队列头部（保持原顺序）
    if unsent:
        queue = _load_queue()
        _save_queue(unsent + queue)
        logger.info(f"[发推] {len(unsent)} 条未发出，已退回队列头部")


async def run_full_pipeline() -> None:
    """完整流程（调试用）。"""
    await run_crawl_pipeline()
    run_tweet_pipeline()


# ══════════════════════════════════════════════════════════════
#  调度入口
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="开源资源自动化 Agent")
    parser.add_argument("--now",    action="store_true", help="立即执行完整流程")
    parser.add_argument("--crawl",  action="store_true", help="只执行抓取存盘")
    parser.add_argument("--tweet",  action="store_true", help="只执行发推")
    args = parser.parse_args()

    if args.now:
        asyncio.run(run_full_pipeline())
        return

    if args.crawl:
        asyncio.run(run_crawl_pipeline())
        return

    if args.tweet:
        run_tweet_pipeline()
        return

    # ── 定时调度模式 ──────────────────────────────────────────
    logger.info("🤖 开源资源自动化 Agent 已启动")
    logger.info("   抓取存盘: 每 6 小时执行一次")
    logger.info("   自动发推: 每 30 分钟检查一次队列")
    logger.info("   按 Ctrl+C 停止\n")

    # 抓取任务：每 6 小时
    schedule.every(6).hours.do(lambda: asyncio.run(run_crawl_pipeline()))
    # 发推任务：每 30 分钟
    schedule.every(30).minutes.do(run_tweet_pipeline)

    # 启动时立即执行一次
    asyncio.run(run_crawl_pipeline())
    run_tweet_pipeline()

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
