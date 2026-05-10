"""
tg_bot.py — Telegram 控制面板

功能按钮：
  ▶️ 启动运行   ⏸ 暂停运行   🔄 重新生成时间表
  📊 今日统计   💰 钱包余额   📝 时间表预览
  🔑 陌生地址池 ℹ️ 系统状态    ❌ 停止机器人

使用 python-telegram-bot v20.x，与主 executor 通过文件状态通信。
"""

import logging
import json
from pathlib import Path
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)

from config import (
    TG_BOT_TOKEN, TG_ADMIN_CHAT_IDS, SCHEDULE_FILE, STATE_FILE, LEDGER_FILE,
)
import executor
import scheduler
import ledger
import wallet_manager
import rpc_client

logger = logging.getLogger(__name__)


# ── 权限检查 ─────────────────────────────────────────────────
def _is_admin(chat_id: int) -> bool:
    if not TG_ADMIN_CHAT_IDS:
        return True   # 未配置则默认放开（仅建议开发环境）
    return chat_id in TG_ADMIN_CHAT_IDS


async def _deny(update: Update) -> None:
    await update.effective_message.reply_text("⛔ 你无权使用此 Bot")


# ══════════════════════════════════════════════════════════════
#  主菜单
# ══════════════════════════════════════════════════════════════

def _main_keyboard() -> InlineKeyboardMarkup:
    running = executor.is_running()
    run_btn_text = "⏸ 暂停运行" if running else "▶️ 启动运行"
    run_btn_data = "pause" if running else "resume"

    keyboard = [
        [InlineKeyboardButton(run_btn_text, callback_data=run_btn_data),
         InlineKeyboardButton("🔄 重新生成时间表", callback_data="regen")],
        [InlineKeyboardButton("📊 今日统计", callback_data="stats"),
         InlineKeyboardButton("📝 时间表预览", callback_data="schedule")],
        [InlineKeyboardButton("💰 钱包余额", callback_data="balance"),
         InlineKeyboardButton("🔑 陌生地址池", callback_data="strangers")],
        [InlineKeyboardButton("ℹ️ 系统状态", callback_data="status"),
         InlineKeyboardButton("🔁 刷新菜单", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_chat.id):
        return await _deny(update)
    await update.message.reply_text(
        f"🤖 <b>Base 机器人控制面板</b>\n"
        f"你的 Chat ID: <code>{update.effective_chat.id}</code>\n"
        f"当前状态: {'🟢 运行中' if executor.is_running() else '🟡 已暂停'}\n\n"
        f"请选择操作 👇",
        reply_markup=_main_keyboard(),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════
#  按钮回调
# ══════════════════════════════════════════════════════════════

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    if not _is_admin(update.effective_chat.id):
        return await _deny(update)

    action = q.data

    # ── 启停控制 ──────────────────────────────────────────────
    if action == "pause":
        executor.set_running(False)
        await q.edit_message_text(
            "⏸ 已暂停运行。到期事件会累积，恢复后继续执行。",
            reply_markup=_main_keyboard(),
        )
    elif action == "resume":
        executor.set_running(True)
        await q.edit_message_text(
            "▶️ 已启动运行。",
            reply_markup=_main_keyboard(),
        )

    # ── 重新生成时间表 ───────────────────────────────────────
    elif action == "regen":
        events = scheduler.generate_daily_schedule()
        scheduler.save_schedule(events)
        await q.edit_message_text(
            f"🔄 已重新生成今日时间表\n"
            f"共 <b>{len(events)}</b> 个事件\n\n"
            f"• Swap: {sum(1 for e in events if e['type']=='swap')}\n"
            f"• Transfer: {sum(1 for e in events if e['type']=='transfer')}\n"
            f"• Claim Fee: {sum(1 for e in events if e['type']=='claim_fee')}",
            reply_markup=_main_keyboard(),
            parse_mode="HTML",
        )

    # ── 今日统计 ──────────────────────────────────────────────
    elif action == "stats":
        s = ledger.get_today_summary()
        text = (
            f"📊 <b>今日交易统计 ({s['date']})</b>\n\n"
            f"总交易数: <b>{s['total_txs']}</b>\n"
            f"├ 买入: {s['total_buys']}\n"
            f"├ 卖出: {s['total_sells']}\n"
            f"├ 转账: {s['total_transfers']}\n"
            f"└ 领取手续费: {s['total_claims']}\n\n"
            f"<b>各钱包交易数:</b>\n"
        )
        for widx in sorted(s["wallets"].keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
            text += f"  #{widx}: {s['wallets'][widx]} 笔\n"
        await q.edit_message_text(text, reply_markup=_main_keyboard(), parse_mode="HTML")

    # ── 时间表预览 ────────────────────────────────────────────
    elif action == "schedule":
        events = scheduler.load_schedule()
        if not events:
            text = "📝 今日时间表为空（可能刚执行完毕，或需要重新生成）"
        else:
            upcoming = [e for e in events if e["time"] > datetime.now().isoformat()]
            text  = f"📝 <b>今日时间表</b>\n剩余 {len(upcoming)} 个事件\n\n"
            text += "<b>未来 10 个事件:</b>\n"
            for e in upcoming[:10]:
                t = e["time"][11:19]
                text += f"• {t} | 钱包#{e['wallet']} | {e['type']}\n"
        await q.edit_message_text(text, reply_markup=_main_keyboard(), parse_mode="HTML")

    # ── 钱包余额 ──────────────────────────────────────────────
    elif action == "balance":
        await q.edit_message_text("⏳ 查询中，请稍候…")
        wallets = wallet_manager.load_wallets()
        w3 = rpc_client.get_w3()
        lines = [f"💰 <b>钱包 ETH 余额 (共 {len(wallets)} 个)</b>\n"]
        total = 0.0
        for w in wallets:
            bal = wallet_manager.get_eth_balance(w3, w["address"])
            total += bal
            short = w["address"][:6] + "…" + w["address"][-4:]
            lines.append(f"#{w['index']:02d} <code>{short}</code>  {bal:.6f} ETH")
        lines.append(f"\n总余额: <b>{total:.6f} ETH</b>")
        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=_main_keyboard(),
            parse_mode="HTML",
        )

    # ── 陌生地址池 ────────────────────────────────────────────
    elif action == "strangers":
        p = Path("data/stranger_pool.json")
        if p.exists():
            try:
                with open(p) as f:
                    data = json.load(f)
                text = (
                    f"🔑 <b>陌生地址池</b>\n\n"
                    f"刷新日期: {data.get('date')}\n"
                    f"池子大小: <b>{len(data.get('addresses', []))}</b>\n\n"
                    f"示例地址 (前 5 个):\n"
                )
                for addr in data.get("addresses", [])[:5]:
                    text += f"• <code>{addr}</code>\n"
            except Exception:
                text = "❌ 陌生地址池文件解析失败"
        else:
            text = "🔑 陌生地址池尚未构建（首次运行时自动构建）"
        await q.edit_message_text(text, reply_markup=_main_keyboard(), parse_mode="HTML")

    # ── 系统状态 ──────────────────────────────────────────────
    elif action == "status":
        state   = json.load(open(STATE_FILE)) if Path(STATE_FILE).exists() else {}
        running = executor.is_running()
        try:
            w3 = rpc_client.get_w3()
            rpc_ok = w3.is_connected()
            block  = w3.eth.block_number if rpc_ok else "—"
        except Exception:
            rpc_ok = False
            block  = "—"

        text = (
            f"ℹ️ <b>系统状态</b>\n\n"
            f"运行状态: {'🟢 运行中' if running else '🟡 已暂停'}\n"
            f"启动时间: {state.get('started_at', '—')}\n"
            f"最后切换: {state.get('changed_at', '—')}\n"
            f"RPC 连接: {'✅ 正常' if rpc_ok else '❌ 断开'}\n"
            f"最新区块: {block}\n"
        )
        await q.edit_message_text(text, reply_markup=_main_keyboard(), parse_mode="HTML")

    # ── 刷新菜单 ──────────────────────────────────────────────
    elif action == "menu":
        await q.edit_message_text(
            f"🤖 <b>Base 机器人控制面板</b>\n"
            f"当前状态: {'🟢 运行中' if executor.is_running() else '🟡 已暂停'}\n\n"
            f"请选择操作 👇",
            reply_markup=_main_keyboard(),
            parse_mode="HTML",
        )


# ══════════════════════════════════════════════════════════════
#  Bot 启动入口
# ══════════════════════════════════════════════════════════════

def run_bot() -> None:
    """启动 Telegram Bot（阻塞，建议在独立线程跑）。"""
    if not TG_BOT_TOKEN or TG_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.warning("[TG] 未配置 TG_BOT_TOKEN，Telegram 控制面板不启动")
        return

    app = Application.builder().token(TG_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu",  start_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("🤖 Telegram 控制面板已启动（发送 /start 打开菜单）")
    app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
