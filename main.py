"""
main.py — 空投项目发掘助手主入口

运行方式：
  python main.py            # 启动定时调度，每天 10:00 自动执行
  python main.py --now      # 立即执行一次（调试用）
"""

import argparse
import time
import schedule
import concurrent.futures
from datetime import date

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

    # ⚡ Bolt Optimization: Fetch all 7 datasets in parallel using ThreadPoolExecutor
    # to reduce execution time from the sum of all request latencies to the slowest single request.
    print("  → [⚡ Parallel] 启动多线程并发抓取 7 个数据源…")
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        future_to_name = {
            executor.submit(rootdata.get_daily_funding, today): "RootData 融资数据",
            executor.submit(rootdata.get_project_events, today): "RootData 项目动态",
            executor.submit(rootdata.get_new_projects, 1): "RootData 新收录项目",
            executor.submit(rootdata.get_upcoming_tge, 7): "RootData TGE 信息",
            executor.submit(cryptorank.get_daily_funding, today): "CryptoRank 融资数据",
            executor.submit(cryptorank.get_upcoming_ido, 7): "CryptoRank IDO 信息",
            executor.submit(okboost.get_daily_okboost, today): "OKBoost 动态"
        }

        # Collect results with standard fallbacks if any future raises an unexpected exception
        results = {}
        for future, name in future_to_name.items():
            try:
                results[name] = future.result()
            except Exception as e:
                print(f"  ❌ 抓取 {name} 失败: {e}")
                results[name] = []

    rd_funding   = results["RootData 融资数据"]
    rd_events    = results["RootData 项目动态"]
    rd_new_proj  = results["RootData 新收录项目"]
    rd_tge       = results["RootData TGE 信息"]
    cr_funding   = results["CryptoRank 融资数据"]
    cr_ido       = results["CryptoRank IDO 信息"]
    okboost_data = results["OKBoost 动态"]

    elapsed = time.time() - start_time
    print(f"  → [⚡ Parallel] 并发抓取完成，耗时: {elapsed:.2f}s")

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
