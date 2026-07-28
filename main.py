"""
main.py — 空投项目发掘助手主入口

运行方式：
  python main.py            # 启动定时调度，每天 10:00 自动执行
  python main.py --now      # 立即执行一次（调试用）
"""

import argparse
import time
import schedule
from datetime import date
from concurrent.futures import ThreadPoolExecutor

import rootdata
import cryptorank
import okboost
from notifier import send_message, fmt_daily_report
from config   import SCHEDULE_HOUR, SCHEDULE_MINUTE


def run_daily_job():
    """核心任务：抓取所有数据 → 格式化 → 推送 TG。"""
    today     = date.today()
    today_str = today.strftime("%Y-%m-%d")
    print(f"[{today_str}] ⏰ 开始执行每日空投日报任务…")

    # ── ⚡ 性能优化: 并行抓取 (Performance Optimization: Parallel Data Fetching) ───────────────────────
    # 相比之前顺序、逐个调用的抓取流程（总耗时约 7 个独立的 API/RSS 请求延迟之和，约 3-4s 以上），
    # 我们采用 ThreadPoolExecutor 进行并发抓取，大幅度降低总体 I/O 等待时间到仅单个最慢请求的耗时（约 0.5s - 1s）。
    print("  → 启动并行抓取任务 (Starting parallel data fetching)...")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=7) as executor:
        fut_rd_funding  = executor.submit(rootdata.get_daily_funding, today)
        fut_rd_events   = executor.submit(rootdata.get_project_events, today)
        fut_rd_new_proj = executor.submit(rootdata.get_new_projects, 1)
        fut_rd_tge      = executor.submit(rootdata.get_upcoming_tge, 7)
        fut_cr_funding  = executor.submit(cryptorank.get_daily_funding, today)
        fut_cr_ido      = executor.submit(cryptorank.get_upcoming_ido, 7)
        fut_okboost     = executor.submit(okboost.get_daily_okboost, today)

        # 阻塞等待所有并发任务完成并获取其结果 (Blocks until all parallel tasks finish)
        rd_funding   = fut_rd_funding.result()
        rd_events    = fut_rd_events.result()
        rd_new_proj  = fut_rd_new_proj.result()
        rd_tge       = fut_rd_tge.result()
        cr_funding   = fut_cr_funding.result()
        cr_ido       = fut_cr_ido.result()
        okboost_data = fut_okboost.result()

    elapsed = time.time() - start_time
    print(f"  → 所有数据抓取完成，耗时 {elapsed:.2f} 秒！")

    # ── 格式化报告 ────────────────────────────────────────────
    report = fmt_daily_report(
        rd_funding  = rd_funding,
        rd_events   = rd_events,
        rd_new_proj = rd_new_proj,
        rd_tge      = rd_tge,
        cr_funding  = cr_funding,
        cr_ido      = cr_ido,
        okboost     = okboost_data,
        report_date = today_str,
    )

    # ── 推送 Telegram ─────────────────────────────────────────
    print("  → 推送至 Telegram…")
    send_message(report)
    print(f"[{today_str}] ✅ 日报推送完成！")


def main():
    parser = argparse.ArgumentParser(description="空投项目发掘助手")
    parser.add_argument("--now", action="store_true", help="立即执行一次（不启动调度）")
    args = parser.parse_args()

    if args.now:
        run_daily_job()
        return

    # ── 定时调度模式 ──────────────────────────────────────────
    job_time = f"{SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}"
    schedule.every().day.at(job_time).do(run_daily_job)
    print(f"🦞 空投发掘助手已启动，每天 {job_time} 自动推送日报")
    print("   按 Ctrl+C 停止服务\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
