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

    # ── 并行抓取 ──────────────────────────────────────────────
    print("  → 开启并行抓取任务…")

    tasks = {
        "rd_funding":  (rootdata.get_daily_funding, (today,)),
        "rd_events":   (rootdata.get_project_events, (today,)),
        "rd_new_proj": (rootdata.get_new_projects, (1,)),
        "rd_tge":      (rootdata.get_upcoming_tge, (7,)),
        "cr_funding":  (cryptorank.get_daily_funding, (today,)),
        "cr_ido":      (cryptorank.get_upcoming_ido, (7,)),
        "okboost":     (okboost.get_daily_okboost, (today,)),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_to_key = {executor.submit(func, *args): key for key, (func, args) in tasks.items()}
        for future in future_to_key:
            key = future_to_key[future]
            try:
                results[key] = future.result()
            except Exception as e:
                print(f"  ❌ 抓取任务 [{key}] 失败: {e}")
                results[key] = []

    rd_funding   = results.get("rd_funding", [])
    rd_events    = results.get("rd_events", [])
    rd_new_proj  = results.get("rd_new_proj", [])
    rd_tge       = results.get("rd_tge", [])
    cr_funding   = results.get("cr_funding", [])
    cr_ido       = results.get("cr_ido", [])
    okboost_data = results.get("okboost", [])

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
