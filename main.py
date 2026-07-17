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

    # ── 并行抓取（使用 ThreadPoolExecutor 异步并发，加速网络 IO 密集型操作） ──
    print("  → 开始并行抓取各项数据…")

    with ThreadPoolExecutor(max_workers=7) as executor:
        f_rd_funding  = executor.submit(rootdata.get_daily_funding, today)
        f_rd_events   = executor.submit(rootdata.get_project_events, today)
        f_rd_new_proj = executor.submit(rootdata.get_new_projects, 1)
        f_rd_tge      = executor.submit(rootdata.get_upcoming_tge, 7)
        f_cr_funding  = executor.submit(cryptorank.get_daily_funding, today)
        f_cr_ido      = executor.submit(cryptorank.get_upcoming_ido, 7)
        f_okboost     = executor.submit(okboost.get_daily_okboost, today)

        # 获取并解析结果
        rd_funding   = f_rd_funding.result()
        rd_events    = f_rd_events.result()
        rd_new_proj  = f_rd_new_proj.result()
        rd_tge       = f_rd_tge.result()
        cr_funding   = f_cr_funding.result()
        cr_ido       = f_cr_ido.result()
        okboost_data = f_okboost.result()

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
