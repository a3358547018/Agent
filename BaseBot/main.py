"""
main.py — Base 机器人启动入口

启动后同时运行：
  1. 交易执行主循环（executor.run_forever）—— 独立线程
  2. Telegram 控制面板（tg_bot.run_bot）—— 主线程（阻塞）

运行方式：
  python main.py             # 正式启动（executor + TG Bot）
  python main.py --exec-only # 只启动执行器（无 TG）
  python main.py --schedule  # 只生成/打印今日时间表
  python main.py --encrypt   # 加密 wallets 私钥
"""

import argparse
import signal
import sys
import logging
import threading
from pathlib import Path

from config import LOG_DIR, DATA_DIR


# ── 日志初始化 ───────────────────────────────────────────────
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"{LOG_DIR}/base_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


# ── 优雅退出 ─────────────────────────────────────────────────
def _setup_signals(executor_mod):
    def _sigterm(sig, frame):
        logger.info("🛑 收到退出信号，正在停止…")
        executor_mod.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT,  _sigterm)
    signal.signal(signal.SIGTERM, _sigterm)


# ══════════════════════════════════════════════════════════════
#  启动模式
# ══════════════════════════════════════════════════════════════

def run_executor_and_bot():
    """主执行模式：启动交易线程 + TG 面板。"""
    import executor
    import tg_bot

    _setup_signals(executor)

    # 交易执行线程（daemon=False 保证进程不退出，符合"运行那就不能关闭"的要求）
    exec_thread = threading.Thread(target=executor.run_forever, name="Executor", daemon=False)
    exec_thread.start()
    logger.info("✅ Executor 线程已启动")

    # TG Bot 主线程（阻塞）
    try:
        tg_bot.run_bot()
    except Exception as e:
        logger.error(f"TG Bot 异常退出: {e}")

    # 确保 executor 也退出
    executor.stop()
    exec_thread.join(timeout=30)


def run_executor_only():
    """只运行交易执行器（无 TG）。"""
    import executor
    _setup_signals(executor)
    executor.run_forever()


def print_schedule():
    """生成并打印今日时间表。"""
    import scheduler
    events = scheduler.ensure_today_schedule()
    print(f"共 {len(events)} 个事件")
    for e in events[:30]:
        print(f"  {e['time']}  钱包#{e['wallet']:02d}  {e['type']}")
    if len(events) > 30:
        print(f"  … 省略 {len(events) - 30} 个 …")


def encrypt_wallets_cli():
    """交互式加密钱包私钥。"""
    import getpass
    import wallet_manager

    print("=== 钱包私钥加密工具 ===")
    passphrase = getpass.getpass("设置加密口令: ")
    confirm    = getpass.getpass("再次输入确认: ")
    if passphrase != confirm:
        print("❌ 两次口令不一致")
        return
    if not passphrase:
        print("❌ 口令不能为空")
        return

    print("\n请逐行粘贴 22 个钱包私钥（每行一个，空行结束）:")
    keys = []
    while True:
        line = input().strip()
        if not line:
            break
        if not line.startswith("0x"):
            line = "0x" + line
        keys.append(line)

    if not keys:
        print("❌ 未输入任何私钥")
        return

    wallet_manager.encrypt_wallets(keys, passphrase)
    print(f"\n✅ 已加密保存 {len(keys)} 个钱包")
    print("⚠️ 请在 config.py 中设置 WALLET_ENCRYPTION_PASSPHRASE=你的口令")
    print("⚠️ 并清空 WALLET_PRIVATE_KEYS 列表")


# ══════════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Base 链交易机器人")
    parser.add_argument("--exec-only", action="store_true", help="只启动执行器，不启动 TG Bot")
    parser.add_argument("--schedule",  action="store_true", help="生成并打印今日时间表")
    parser.add_argument("--encrypt",   action="store_true", help="加密 wallets 私钥")
    args = parser.parse_args()

    if args.schedule:
        print_schedule()
    elif args.encrypt:
        encrypt_wallets_cli()
    elif args.exec_only:
        run_executor_only()
    else:
        run_executor_and_bot()


if __name__ == "__main__":
    main()
