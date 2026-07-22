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

    # ── 并行抓取（使用 ThreadPoolExecutor 进行并发请求以大幅缩短运行时间） ───────────────────
    print("  → 启动并发线程池抓取数据…")
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        f_rd_funding  = executor.submit(rootdata.get_daily_funding, today)
        f_rd_events   = executor.submit(rootdata.get_project_events, today)
        f_rd_new_proj = executor.submit(rootdata.get_new_projects, 1)
        f_rd_tge      = executor.submit(rootdata.get_upcoming_tge, 7)
        f_cr_funding  = executor.submit(cryptorank.get_daily_funding, today)
        f_cr_ido      = executor.submit(cryptorank.get_upcoming_ido, 7)
        f_okboost     = executor.submit(okboost.get_daily_okboost, today)

        try:
            rd_funding = f_rd_funding.result()
        except Exception as e:
            print(f"  ❌ 抓取 RootData 融资数据时发生异常: {e}")
            rd_funding = []

        try:
            rd_events = f_rd_events.result()
        except Exception as e:
            print(f"  ❌ 抓取 RootData 项目动态时发生异常: {e}")
            rd_events = []

        try:
            rd_new_proj = f_rd_new_proj.result()
        except Exception as e:
            print(f"  ❌ 抓取 RootData 新收录项目时发生异常: {e}")
            rd_new_proj = []

        try:
            rd_tge = f_rd_tge.result()
        except Exception as e:
            print(f"  ❌ 抓取 RootData TGE 信息时发生异常: {e}")
            rd_tge = []

        try:
            cr_funding = f_cr_funding.result()
        except Exception as e:
            print(f"  ❌ 抓取 CryptoRank 融资数据时发生异常: {e}")
            cr_funding = []

        try:
            cr_ido = f_cr_ido.result()
        except Exception as e:
            print(f"  ❌ 抓取 CryptoRank IDO 信息时发生异常: {e}")
            cr_ido = []

        try:
            okboost_data = f_okboost.result()
        except Exception as e:
            print(f"  ❌ 抓取 OKBoost 动态时发生异常: {e}")
            okboost_data = []

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
