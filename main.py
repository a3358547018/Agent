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

import rootdata
import cryptorank
import okboost
from notifier import send_message, fmt_daily_report
from config   import SCHEDULE_HOUR, SCHEDULE_MINUTE


import concurrent.futures

def run_daily_job():
    """核心任务：抓取所有数据 → 格式化 → 推送 TG。"""
    today     = date.today()
    today_str = today.strftime("%Y-%m-%d")
    print(f"[{today_str}] ⏰ 开始执行每日空投日报任务…")

    # ── 并行抓取（利用 ThreadPoolExecutor 与线程局部 Session 优化并发） ───────────────────────
    tasks = {
        "rd_funding":  lambda: rootdata.get_daily_funding(today),
        "rd_events":   lambda: rootdata.get_project_events(today),
        "rd_new_proj": lambda: rootdata.get_new_projects(days=1),
        "rd_tge":      lambda: rootdata.get_upcoming_tge(days_ahead=7),
        "cr_funding":  lambda: cryptorank.get_daily_funding(today),
        "cr_ido":      lambda: cryptorank.get_upcoming_ido(days_ahead=7),
        "okboost_data": lambda: okboost.get_daily_okboost(today),
    }

    results = {}
    print("  → 并发启动 external APIs 数据抓取...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_to_name = {executor.submit(func): name for name, func in tasks.items()}
        for future in concurrent.futures.as_completed(future_to_name):
            name = future_to_name[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                print(f"  [Error] 任务 {name} 执行失败: {exc}")
                results[name] = []

    rd_funding   = results.get("rd_funding") or []
    rd_events    = results.get("rd_events") or []
    rd_new_proj  = results.get("rd_new_proj") or []
    rd_tge       = results.get("rd_tge") or []
    cr_funding   = results.get("cr_funding") or []
    cr_ido       = results.get("cr_ido") or []
    okboost_data = results.get("okboost_data") or []

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
