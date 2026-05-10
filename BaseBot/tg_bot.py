"""
tg_bot.py — Telegram 控制面板（多级菜单，覆盖每个步骤）

菜单结构：
  主菜单
  ├─ ⚙️ 运行控制        （启动/暂停/停止/重启）
  ├─ 📝 时间表管理      （生成/清空/按钱包删/按类型删/预览）
  ├─ 💼 钱包管理        （余额/详情/按钱包操作）
  ├─ 💱 交易控制        （手动 Swap/Buy/Sell 某钱包，开关 swap）
  ├─ 📤 转账控制        （手动 transfer，开关 transfer，调整比例）
  ├─ 💰 V3 手续费       （手动领取，开关 claim_fee）
  ├─ 🪙 代币池          （查看/刷新）
  ├─ 🔑 陌生地址池      （查看/刷新）
  ├─ ⛽ Gas 设置        （查看/调整 gwei/limit/成本上限）
  ├─ 🎲 交易参数        （调整笔数/金额/转账比例）
  ├─ 📊 今日统计        （账本统计 + 最近交易）
  └─ ℹ️ 系统状态
"""

import json
import logging
from pathlib import Path
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters,
)

from config import TG_BOT_TOKEN, TG_ADMIN_CHAT_IDS, STATE_FILE, WALLETS_COUNT
import executor
import scheduler
import ledger
import wallet_manager
import rpc_client
import token_pool
import overrides
import gas_estimator

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
#  权限 & 工具
# ══════════════════════════════════════════════════════════════

def _is_admin(chat_id: int) -> bool:
    if not TG_ADMIN_CHAT_IDS:
        return True
    return chat_id in TG_ADMIN_CHAT_IDS


async def _deny(update_or_query) -> None:
    msg = update_or_query.effective_message if hasattr(update_or_query, "effective_message") else update_or_query.message
    await msg.reply_text("⛔ 你无权使用此 Bot")


def _safe_page(lst: list, page: int, page_size: int = 10) -> tuple[list, int, int]:
    """分页工具：返回 (当前页数据, 当前页号, 总页数)。"""
    total = len(lst)
    pages = max(1, (total + page_size - 1) // page_size)
    page  = max(0, min(page, pages - 1))
    start = page * page_size
    return lst[start:start + page_size], page, pages


# ══════════════════════════════════════════════════════════════
#  主菜单
# ══════════════════════════════════════════════════════════════

def _main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("⚙️ 运行控制",    callback_data="run"),
         InlineKeyboardButton("📝 时间表管理",  callback_data="sched")],
        [InlineKeyboardButton("💼 钱包管理",    callback_data="wallets"),
         InlineKeyboardButton("💱 交易控制",    callback_data="swap")],
        [InlineKeyboardButton("📤 转账控制",    callback_data="xfer"),
         InlineKeyboardButton("💰 V3 手续费",   callback_data="claim")],
        [InlineKeyboardButton("🪙 代币池",      callback_data="tokens"),
         InlineKeyboardButton("🔑 陌生地址池",  callback_data="strangers")],
        [InlineKeyboardButton("⛽ Gas 设置",    callback_data="gas"),
         InlineKeyboardButton("🎲 交易参数",    callback_data="params")],
        [InlineKeyboardButton("🎰 随机性调节",  callback_data="rand"),
         InlineKeyboardButton("📊 今日统计",    callback_data="stats")],
        [InlineKeyboardButton("ℹ️ 系统状态",   callback_data="status")],
    ]
    return InlineKeyboardMarkup(rows)


def _main_title() -> str:
    running = executor.is_running()
    status  = "🟢 运行中" if running else "🟡 已暂停"
    enabled = executor.get_enabled()
    marks   = " ".join([
        f"{'✅' if enabled['swap'] else '❌'}Swap",
        f"{'✅' if enabled['transfer'] else '❌'}Transfer",
        f"{'✅' if enabled['claim_fee'] else '❌'}Claim",
    ])
    return (
        f"🦾 <b>Base 机器人控制面板</b>\n"
        f"状态: {status}\n"
        f"开关: {marks}\n\n"
        f"请选择操作 👇"
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_chat.id):
        return await _deny(update)
    await update.message.reply_text(
        _main_title() + f"\nChat ID: <code>{update.effective_chat.id}</code>",
        reply_markup=_main_menu_kb(),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════
#  子菜单生成器
# ══════════════════════════════════════════════════════════════

def _back_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton("🔙 返回主菜单", callback_data="menu")


# ── ⚙️ 运行控制 ───────────────────────────────────────────────
def _run_menu() -> tuple[str, InlineKeyboardMarkup]:
    running = executor.is_running()
    text = (
        "⚙️ <b>运行控制</b>\n\n"
        f"当前状态: <b>{'🟢 运行中' if running else '🟡 已暂停'}</b>\n\n"
        "• <b>启动</b>: 恢复执行计划事件\n"
        "• <b>暂停</b>: 停止执行，不退出进程\n"
        "• <b>停止进程</b>: 完全退出机器人（需命令行重启）"
    )
    kb = [
        [InlineKeyboardButton("▶️ 启动运行", callback_data="run:start"),
         InlineKeyboardButton("⏸ 暂停运行", callback_data="run:pause")],
        [InlineKeyboardButton("🛑 停止进程", callback_data="run:stop")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


# ── 📝 时间表管理 ─────────────────────────────────────────────
def _sched_menu() -> tuple[str, InlineKeyboardMarkup]:
    s = scheduler.get_stats()
    next_ev = s.get("next")
    next_txt = f"{next_ev['time'][11:19]} 钱包#{next_ev['wallet']} {next_ev['type']}" if next_ev else "无"

    text = (
        "📝 <b>时间表管理</b>\n\n"
        f"总事件: {s['total']}\n"
        f"待执行: <b>{s['pending']}</b>  已执行: {s['past']}\n"
        f"分类(待): Swap {s['by_type']['swap']} / Transfer {s['by_type']['transfer']} / Claim {s['by_type']['claim_fee']}\n"
        f"下一事件: {next_txt}"
    )
    kb = [
        [InlineKeyboardButton("🔄 重新生成时间表", callback_data="sched:regen")],
        [InlineKeyboardButton("🗑 清空时间表",    callback_data="sched:clear"),
         InlineKeyboardButton("📋 预览事件",      callback_data="sched:preview:0")],
        [InlineKeyboardButton("❌ 删除所有 Swap",   callback_data="sched:del:swap"),
         InlineKeyboardButton("❌ 删除所有 Transfer",callback_data="sched:del:transfer")],
        [InlineKeyboardButton("❌ 删除所有 Claim",  callback_data="sched:del:claim_fee")],
        [InlineKeyboardButton("🎯 按钱包删除", callback_data="sched:bywallet:0")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


def _sched_preview(page: int) -> tuple[str, InlineKeyboardMarkup]:
    events  = scheduler.load_schedule()
    now_iso = datetime.now().isoformat()
    pending = [e for e in events if e["time"] > now_iso]
    chunk, p, pages = _safe_page(pending, page, 10)

    text = f"📋 <b>待执行事件</b>（第 {p+1}/{pages} 页，共 {len(pending)} 个）\n\n"
    if not chunk:
        text += "暂无待执行事件"
    else:
        for e in chunk:
            text += f"• {e['time'][11:19]}  钱包#{e['wallet']:02d}  {e['type']}\n"

    kb_row = []
    if p > 0:
        kb_row.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"sched:preview:{p-1}"))
    if p < pages - 1:
        kb_row.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"sched:preview:{p+1}"))

    kb = []
    if kb_row:
        kb.append(kb_row)
    kb.append([InlineKeyboardButton("🔙 时间表管理", callback_data="sched")])
    return text, InlineKeyboardMarkup(kb)


def _sched_by_wallet(page: int) -> tuple[str, InlineKeyboardMarkup]:
    # 展示 22 个钱包按钮，点击删除该钱包的事件
    start = page * 10
    end   = min(start + 10, WALLETS_COUNT)
    text = (
        "🎯 <b>按钱包删除事件</b>\n\n"
        "点击钱包编号可删除它所有待执行事件。"
    )
    rows = []
    row  = []
    for i in range(start, end):
        row.append(InlineKeyboardButton(f"#{i:02d}", callback_data=f"sched:delw:{i}"))
        if len(row) == 5:
            rows.append(row); row = []
    if row:
        rows.append(row)

    pg_row = []
    if page > 0:
        pg_row.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"sched:bywallet:{page-1}"))
    if end < WALLETS_COUNT:
        pg_row.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"sched:bywallet:{page+1}"))
    if pg_row:
        rows.append(pg_row)
    rows.append([InlineKeyboardButton("🔙 时间表管理", callback_data="sched")])
    return text, InlineKeyboardMarkup(rows)


# ── 💼 钱包管理 ───────────────────────────────────────────────
def _wallets_menu() -> tuple[str, InlineKeyboardMarkup]:
    wallets = wallet_manager.load_wallets()
    text = f"💼 <b>钱包管理</b>\n\n共加载 <b>{len(wallets)}</b> 个钱包"
    kb = [
        [InlineKeyboardButton("💰 查看全部余额",  callback_data="wallets:bal")],
        [InlineKeyboardButton("📋 钱包地址列表",  callback_data="wallets:list:0")],
        [InlineKeyboardButton("🔍 按钱包查看",    callback_data="wallets:each:0")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


def _wallets_each(page: int) -> tuple[str, InlineKeyboardMarkup]:
    start = page * 10
    end   = min(start + 10, WALLETS_COUNT)
    text = (
        "🔍 <b>选择钱包查看/操作</b>\n\n"
        f"第 {page + 1}/{(WALLETS_COUNT + 9) // 10} 页"
    )
    rows = []
    row  = []
    for i in range(start, end):
        row.append(InlineKeyboardButton(f"钱包 #{i:02d}", callback_data=f"wallets:detail:{i}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)

    pg_row = []
    if page > 0:
        pg_row.append(InlineKeyboardButton("⬅️", callback_data=f"wallets:each:{page-1}"))
    if end < WALLETS_COUNT:
        pg_row.append(InlineKeyboardButton("➡️", callback_data=f"wallets:each:{page+1}"))
    if pg_row:
        rows.append(pg_row)
    rows.append([InlineKeyboardButton("🔙 钱包管理", callback_data="wallets")])
    return text, InlineKeyboardMarkup(rows)


def _wallet_detail(widx: int) -> tuple[str, InlineKeyboardMarkup]:
    wallets = wallet_manager.load_wallets()
    if widx < 0 or widx >= len(wallets):
        return "❌ 钱包编号无效", InlineKeyboardMarkup([[_back_btn()]])
    w = wallets[widx]

    try:
        w3  = rpc_client.get_w3()
        eth = wallet_manager.get_eth_balance(w3, w["address"])
    except Exception:
        eth = -1

    holdings = ledger.get_today_holdings(widx)
    txs      = ledger.get_today_txs(widx)

    text = (
        f"💼 <b>钱包 #{widx:02d} 详情</b>\n\n"
        f"地址: <code>{w['address']}</code>\n"
        f"ETH 余额: <b>{eth:.6f}</b>\n\n"
        f"今日交易数: <b>{len(txs)}</b>\n"
        f"今日持仓代币数: <b>{len([t for t,i in holdings.items() if i.get('balance',0)>0])}</b>\n"
    )
    if holdings:
        text += "\n<b>持仓明细:</b>\n"
        for addr, info in list(holdings.items())[:8]:
            bal = info.get("balance", 0)
            if bal > 0:
                text += f"  • {info.get('symbol','?')}: {bal:.6f}\n"

    kb = [
        [InlineKeyboardButton("💱 立即 Swap", callback_data=f"manual:swap:{widx}"),
         InlineKeyboardButton("💵 立即 Buy",  callback_data=f"manual:buy:{widx}"),
         InlineKeyboardButton("💸 立即 Sell", callback_data=f"manual:sell:{widx}")],
        [InlineKeyboardButton("📤 立即 Transfer", callback_data=f"manual:transfer:{widx}"),
         InlineKeyboardButton("💰 领 V3 手续费",  callback_data=f"manual:claim_fee:{widx}")],
        [InlineKeyboardButton("🗑 删此钱包事件", callback_data=f"sched:delw:{widx}")],
        [InlineKeyboardButton("🔙 钱包列表", callback_data="wallets:each:0"),
         _back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


# ── 💱 交易控制 ───────────────────────────────────────────────
def _swap_menu() -> tuple[str, InlineKeyboardMarkup]:
    enabled = executor.get_enabled()["swap"]
    text = (
        "💱 <b>交易（Swap）控制</b>\n\n"
        f"Swap 开关: <b>{'✅ 启用' if enabled else '❌ 禁用'}</b>\n\n"
        "• 切换开关：所有到期 Swap 事件是否执行\n"
        "• 立即执行：选择一个钱包手动触发 Swap/Buy/Sell"
    )
    kb = [
        [InlineKeyboardButton(
            "❌ 禁用 Swap" if enabled else "✅ 启用 Swap",
            callback_data="swap:toggle",
        )],
        [InlineKeyboardButton("💱 手动 Swap 某钱包", callback_data="swap:pick:swap:0")],
        [InlineKeyboardButton("💵 手动 Buy 某钱包",  callback_data="swap:pick:buy:0"),
         InlineKeyboardButton("💸 手动 Sell 某钱包", callback_data="swap:pick:sell:0")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


def _pick_wallet_menu(action: str, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """通用钱包选择器：action 是 swap/buy/sell/transfer/claim_fee。"""
    start = page * 10
    end   = min(start + 10, WALLETS_COUNT)
    act_label = {
        "swap":"Swap", "buy":"Buy", "sell":"Sell",
        "transfer":"Transfer", "claim_fee":"领V3",
    }.get(action, action)
    text = f"🎯 <b>选择钱包执行: {act_label}</b>\n点击立即执行（第 {page+1} 页）"
    rows = []
    row  = []
    for i in range(start, end):
        row.append(InlineKeyboardButton(f"#{i:02d}", callback_data=f"manual:{action}:{i}"))
        if len(row) == 5:
            rows.append(row); row = []
    if row:
        rows.append(row)

    pg_row = []
    if page > 0:
        pg_row.append(InlineKeyboardButton("⬅️", callback_data=f"swap:pick:{action}:{page-1}"))
    if end < WALLETS_COUNT:
        pg_row.append(InlineKeyboardButton("➡️", callback_data=f"swap:pick:{action}:{page+1}"))
    if pg_row:
        rows.append(pg_row)

    rows.append([InlineKeyboardButton("💡 对全部钱包执行", callback_data=f"manual_all:{action}")])
    rows.append([_back_btn()])
    return text, InlineKeyboardMarkup(rows)


# ── 📤 转账控制 ───────────────────────────────────────────────
def _xfer_menu() -> tuple[str, InlineKeyboardMarkup]:
    enabled = executor.get_enabled()["transfer"]
    n_xfer  = int(overrides.get_param("TRANSFERS_PER_WALLET_DAY") or 1)
    pct_min = overrides.get_param("TRANSFER_PCT_MIN")
    pct_max = overrides.get_param("TRANSFER_PCT_MAX")
    if pct_min is not None and pct_max is not None:
        pct_txt = f"{float(pct_min)*100:.0f}% ~ {float(pct_max)*100:.0f}%（区间随机）"
    else:
        fixed = float(overrides.get_param("TRANSFER_PCT") or 0.30)
        pct_txt = f"{fixed*100:.0f}%（固定）"

    text = (
        "📤 <b>转账控制</b>\n\n"
        f"Transfer 开关: <b>{'✅ 启用' if enabled else '❌ 禁用'}</b>\n"
        f"每钱包每日转账次数: <b>{n_xfer}</b>\n"
        f"当前转账比例: <b>{pct_txt}</b>\n\n"
        "转账规则: 抽代币 → 转 X% 到陌生地址\n"
        "限制: 不转 ETH, 不转给自家 22 个钱包"
    )
    kb = [
        [InlineKeyboardButton(
            "❌ 禁用 Transfer" if enabled else "✅ 启用 Transfer",
            callback_data="xfer:toggle",
        )],
        [InlineKeyboardButton("🎯 手动对某钱包转账", callback_data="swap:pick:transfer:0")],
        [InlineKeyboardButton("🔢 转账笔数 / 天",   callback_data="xfer:count"),
         InlineKeyboardButton("📊 转账比例",        callback_data="xfer:pct")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


def _xfer_count_menu() -> tuple[str, InlineKeyboardMarkup]:
    cur = int(overrides.get_param("TRANSFERS_PER_WALLET_DAY") or 1)
    text = (
        "🔢 <b>每钱包每日转账笔数</b>\n\n"
        f"当前: <b>{cur}</b> 次\n\n"
        "数值越大，每天每个钱包给陌生地址转账的次数越多。\n"
        "<i>改动后需点「📝 时间表 → 🔄 重新生成时间表」生效</i>"
    )
    kb = [
        [InlineKeyboardButton("0 次",  callback_data="xfer:setcnt:0"),
         InlineKeyboardButton("1 次",  callback_data="xfer:setcnt:1"),
         InlineKeyboardButton("2 次",  callback_data="xfer:setcnt:2")],
        [InlineKeyboardButton("3 次",  callback_data="xfer:setcnt:3"),
         InlineKeyboardButton("5 次",  callback_data="xfer:setcnt:5"),
         InlineKeyboardButton("10 次", callback_data="xfer:setcnt:10")],
        [InlineKeyboardButton("🔙 转账控制", callback_data="xfer")],
    ]
    return text, InlineKeyboardMarkup(kb)


def _xfer_pct_menu() -> tuple[str, InlineKeyboardMarkup]:
    pct_min = overrides.get_param("TRANSFER_PCT_MIN")
    pct_max = overrides.get_param("TRANSFER_PCT_MAX")
    if pct_min is not None and pct_max is not None:
        cur = f"{float(pct_min)*100:.0f}% ~ {float(pct_max)*100:.0f}%（区间随机）"
    else:
        fixed = float(overrides.get_param("TRANSFER_PCT") or 0.30)
        cur = f"{fixed*100:.0f}%（固定）"

    text = (
        "📊 <b>转账比例</b>\n\n"
        f"当前: <b>{cur}</b>\n\n"
        "• <b>固定比例</b>：每次都转相同百分比\n"
        "• <b>区间随机</b>：每次在区间内随机（更像真人）"
    )
    kb = [
        [InlineKeyboardButton("固定 10%", callback_data="xfer:fix:0.10"),
         InlineKeyboardButton("固定 30%", callback_data="xfer:fix:0.30"),
         InlineKeyboardButton("固定 50%", callback_data="xfer:fix:0.50")],
        [InlineKeyboardButton("区间 10~30%", callback_data="xfer:rng:0.10:0.30"),
         InlineKeyboardButton("区间 20~50%", callback_data="xfer:rng:0.20:0.50")],
        [InlineKeyboardButton("区间 30~70%", callback_data="xfer:rng:0.30:0.70"),
         InlineKeyboardButton("区间 50~90%", callback_data="xfer:rng:0.50:0.90")],
        [InlineKeyboardButton("🔙 转账控制", callback_data="xfer")],
    ]
    return text, InlineKeyboardMarkup(kb)


# ── 💰 V3 手续费 ──────────────────────────────────────────────
def _claim_menu() -> tuple[str, InlineKeyboardMarkup]:
    enabled = executor.get_enabled()["claim_fee"]
    n_claim = int(overrides.get_param("CLAIMS_PER_WALLET_DAY") or 1)
    text = (
        "💰 <b>Uniswap V3 手续费控制</b>\n\n"
        f"Claim 开关: <b>{'✅ 启用' if enabled else '❌ 禁用'}</b>\n"
        f"每钱包每日领取次数: <b>{n_claim}</b>\n\n"
        "规则: 每个钱包按此次数随机时间领取\n"
        "可手动立即触发某钱包或全部钱包领取"
    )
    kb = [
        [InlineKeyboardButton(
            "❌ 禁用 Claim" if enabled else "✅ 启用 Claim",
            callback_data="claim:toggle",
        )],
        [InlineKeyboardButton("🎯 某钱包立即领取",   callback_data="swap:pick:claim_fee:0")],
        [InlineKeyboardButton("🌟 全部钱包立即领取", callback_data="manual_all:claim_fee")],
        [InlineKeyboardButton("🔢 领取笔数 / 天",   callback_data="claim:count")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


def _claim_count_menu() -> tuple[str, InlineKeyboardMarkup]:
    cur = int(overrides.get_param("CLAIMS_PER_WALLET_DAY") or 1)
    text = f"🔢 <b>每钱包每日领费次数</b>\n\n当前: <b>{cur}</b> 次"
    kb = [
        [InlineKeyboardButton("0 次", callback_data="claim:setcnt:0"),
         InlineKeyboardButton("1 次", callback_data="claim:setcnt:1"),
         InlineKeyboardButton("2 次", callback_data="claim:setcnt:2")],
        [InlineKeyboardButton("3 次", callback_data="claim:setcnt:3"),
         InlineKeyboardButton("5 次", callback_data="claim:setcnt:5")],
        [InlineKeyboardButton("🔙 V3 手续费", callback_data="claim")],
    ]
    return text, InlineKeyboardMarkup(kb)


# ── 🪙 代币池 ─────────────────────────────────────────────────
def _tokens_menu() -> tuple[str, InlineKeyboardMarkup]:
    ctx = executor.get_context()
    text = (
        f"🪙 <b>代币池</b>\n\n"
        f"当前代币数: <b>{ctx['token_count']}</b>\n"
        f"已分配钱包数: {len(ctx['allocation'])}"
    )
    # 展示前 5 个钱包的代币分配
    alloc = ctx["allocation"]
    for widx in sorted(alloc.keys())[:5]:
        syms = ", ".join(alloc[widx][:5])
        text += f"\n  #{widx:02d}: {syms}"
    if len(alloc) > 5:
        text += f"\n  … 其余 {len(alloc)-5} 个钱包略"

    kb = [
        [InlineKeyboardButton("🔄 刷新代币池", callback_data="tokens:refresh")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


# ── 🔑 陌生地址池 ─────────────────────────────────────────────
def _strangers_menu() -> tuple[str, InlineKeyboardMarkup]:
    p = Path("data/stranger_pool.json")
    text = "🔑 <b>陌生地址池</b>\n\n"
    if p.exists():
        try:
            with open(p) as f:
                data = json.load(f)
            addrs = data.get("addresses", [])
            text += (
                f"刷新日期: {data.get('date')}\n"
                f"池子大小: <b>{len(addrs)}</b>\n\n"
                f"示例 (前 3):\n"
            )
            for a in addrs[:3]:
                text += f"• <code>{a}</code>\n"
        except Exception:
            text += "❌ 文件解析失败"
    else:
        text += "尚未构建（首次运行时自动构建）"

    kb = [
        [InlineKeyboardButton("🔄 重新抓取", callback_data="strangers:refresh")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


# ── ⛽ Gas 设置 ──────────────────────────────────────────────
def _gas_menu() -> tuple[str, InlineKeyboardMarkup]:
    default_gwei = float(overrides.get_param("GAS_PRICE_DEFAULT_GWEI") or 0.1)
    gas_limit    = int(overrides.get_param("GAS_LIMIT_MAX") or 1_000_000)
    cost_cap     = float(overrides.get_param("MAX_GAS_COST_USD") or 0.01)

    try:
        w3 = rpc_client.get_w3()
        live_gwei = gas_estimator.estimate_gas_price_gwei(w3)
        eth_price = gas_estimator.get_eth_price_usd()
    except Exception:
        live_gwei = -1
        eth_price = -1

    text = (
        "⛽ <b>Gas 设置</b>\n\n"
        f"实时链上 gwei: <b>{live_gwei:.4f}</b>\n"
        f"ETH 价格: ${eth_price:.2f}\n\n"
        f"当前默认上限: <b>{default_gwei} gwei</b>\n"
        f"Gas Limit: <b>{gas_limit:,}</b>\n"
        f"单笔美元成本上限: <b>${cost_cap}</b>"
    )
    kb = [
        [InlineKeyboardButton("↓ 0.05 gwei", callback_data="gas:gwei:0.05"),
         InlineKeyboardButton("0.1 gwei",    callback_data="gas:gwei:0.1"),
         InlineKeyboardButton("↑ 0.2 gwei",  callback_data="gas:gwei:0.2")],
        [InlineKeyboardButton("0.5 gwei",    callback_data="gas:gwei:0.5"),
         InlineKeyboardButton("1.0 gwei",    callback_data="gas:gwei:1.0")],
        [InlineKeyboardButton("成本上限 $0.005", callback_data="gas:cap:0.005"),
         InlineKeyboardButton("$0.01",         callback_data="gas:cap:0.01"),
         InlineKeyboardButton("$0.05",         callback_data="gas:cap:0.05")],
        [InlineKeyboardButton("Gas Limit 500K", callback_data="gas:limit:500000"),
         InlineKeyboardButton("1M",            callback_data="gas:limit:1000000"),
         InlineKeyboardButton("2M",            callback_data="gas:limit:2000000")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


# ── 🎲 交易参数 ───────────────────────────────────────────────
def _params_menu() -> tuple[str, InlineKeyboardMarkup]:
    p = overrides.get_all_params()
    text = (
        "🎲 <b>交易参数</b>\n\n"
        f"每钱包每日交易数: <b>{p['MIN_TX_PER_WALLET_DAY']} ~ {p['MAX_TX_PER_WALLET_DAY']}</b>\n"
        f"单笔 ETH: <b>{p['TX_AMOUNT_MIN_ETH']} ~ {p['TX_AMOUNT_MAX_ETH']}</b>\n"
        f"转账比例: <b>{float(p['TRANSFER_PCT'])*100:.0f}%</b>\n"
        f"代币池大小: <b>{p['TOKEN_FETCH_COUNT']}</b>\n\n"
        "<i>改动后，下次生成时间表生效</i>"
    )
    kb = [
        [InlineKeyboardButton("笔数 3~5",  callback_data="p:tx:3:5"),
         InlineKeyboardButton("3~10",     callback_data="p:tx:3:10"),
         InlineKeyboardButton("5~15",     callback_data="p:tx:5:15")],
        [InlineKeyboardButton("金额(微)", callback_data="p:amt:0.000001:0.000003"),
         InlineKeyboardButton("(小)",     callback_data="p:amt:0.00001:0.00005"),
         InlineKeyboardButton("(中)",     callback_data="p:amt:0.0001:0.0005")],
        [InlineKeyboardButton("代币池 30", callback_data="p:tok:30"),
         InlineKeyboardButton("60",       callback_data="p:tok:60"),
         InlineKeyboardButton("100",      callback_data="p:tok:100")],
        [InlineKeyboardButton("🔄 重置全部", callback_data="p:reset")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


# ── 🎰 随机性调节 ────────────────────────────────────────────
def _rand_menu() -> tuple[str, InlineKeyboardMarkup]:
    gap     = int(overrides.get_param("MIN_GAP_SECONDS") or 20)
    buy_p   = float(overrides.get_param("BUY_PROBABILITY") or 0.5)
    sr_min  = float(overrides.get_param("SELL_RATIO_MIN") or 0.3)
    sr_max  = float(overrides.get_param("SELL_RATIO_MAX") or 0.7)
    jitter  = float(overrides.get_param("AMOUNT_JITTER_PCT") or 0.0)

    text = (
        "🎰 <b>随机性调节</b>\n\n"
        f"⏱ 事件最小间隔: <b>{gap}s</b>\n"
        f"💵 买入概率: <b>{buy_p*100:.0f}%</b>  (卖出 {(1-buy_p)*100:.0f}%)\n"
        f"💸 卖出比例区间: <b>{sr_min*100:.0f}% ~ {sr_max*100:.0f}%</b>\n"
        f"🎯 金额抖动: <b>±{jitter*100:.0f}%</b>\n\n"
        "<i>所有参数立即生效（下一笔交易开始使用新值）</i>"
    )
    kb = [
        [InlineKeyboardButton("⏱ 调整间隔", callback_data="rand:gap"),
         InlineKeyboardButton("💵 买卖概率", callback_data="rand:buyp")],
        [InlineKeyboardButton("💸 卖出比例", callback_data="rand:sellr"),
         InlineKeyboardButton("🎯 金额抖动", callback_data="rand:jit")],
        [InlineKeyboardButton("🎲 预设：谨慎", callback_data="rand:preset:safe"),
         InlineKeyboardButton("🎲 标准",       callback_data="rand:preset:normal"),
         InlineKeyboardButton("🎲 激进",       callback_data="rand:preset:wild")],
        [_back_btn()],
    ]
    return text, InlineKeyboardMarkup(kb)


def _rand_gap_menu() -> tuple[str, InlineKeyboardMarkup]:
    cur = int(overrides.get_param("MIN_GAP_SECONDS") or 20)
    text = (
        f"⏱ <b>事件最小间隔</b>\n\n当前: <b>{cur} 秒</b>\n\n"
        "时间表里任意两个事件至少相隔这么多秒，\n"
        "数值越大，交易时间分散越明显（更难被识别）"
    )
    kb = [
        [InlineKeyboardButton("5s",  callback_data="rand:setgap:5"),
         InlineKeyboardButton("10s", callback_data="rand:setgap:10"),
         InlineKeyboardButton("20s", callback_data="rand:setgap:20")],
        [InlineKeyboardButton("30s", callback_data="rand:setgap:30"),
         InlineKeyboardButton("60s", callback_data="rand:setgap:60"),
         InlineKeyboardButton("120s",callback_data="rand:setgap:120")],
        [InlineKeyboardButton("🔙 随机性", callback_data="rand")],
    ]
    return text, InlineKeyboardMarkup(kb)


def _rand_buyp_menu() -> tuple[str, InlineKeyboardMarkup]:
    cur = float(overrides.get_param("BUY_PROBABILITY") or 0.5)
    text = (
        f"💵 <b>买入概率</b>\n\n当前: <b>{cur*100:.0f}% 买</b> / {(1-cur)*100:.0f}% 卖\n\n"
        "有持仓时，按此概率决定这一笔是买还是卖。"
    )
    kb = [
        [InlineKeyboardButton("20% 买",  callback_data="rand:setbuyp:0.2"),
         InlineKeyboardButton("35% 买",  callback_data="rand:setbuyp:0.35"),
         InlineKeyboardButton("50% 买",  callback_data="rand:setbuyp:0.5")],
        [InlineKeyboardButton("65% 买",  callback_data="rand:setbuyp:0.65"),
         InlineKeyboardButton("80% 买",  callback_data="rand:setbuyp:0.8")],
        [InlineKeyboardButton("🔙 随机性", callback_data="rand")],
    ]
    return text, InlineKeyboardMarkup(kb)


def _rand_sellr_menu() -> tuple[str, InlineKeyboardMarkup]:
    lo = float(overrides.get_param("SELL_RATIO_MIN") or 0.3)
    hi = float(overrides.get_param("SELL_RATIO_MAX") or 0.7)
    text = (
        f"💸 <b>卖出比例区间</b>\n\n当前: <b>{lo*100:.0f}% ~ {hi*100:.0f}%</b>\n\n"
        "每次卖出时，在此区间内随机决定卖多少持仓。"
    )
    kb = [
        [InlineKeyboardButton("10~30%", callback_data="rand:setsr:0.1:0.3"),
         InlineKeyboardButton("20~50%", callback_data="rand:setsr:0.2:0.5"),
         InlineKeyboardButton("30~70%", callback_data="rand:setsr:0.3:0.7")],
        [InlineKeyboardButton("40~80%", callback_data="rand:setsr:0.4:0.8"),
         InlineKeyboardButton("50~100%",callback_data="rand:setsr:0.5:1.0")],
        [InlineKeyboardButton("🔙 随机性", callback_data="rand")],
    ]
    return text, InlineKeyboardMarkup(kb)


def _rand_jit_menu() -> tuple[str, InlineKeyboardMarkup]:
    cur = float(overrides.get_param("AMOUNT_JITTER_PCT") or 0.0)
    text = (
        f"🎯 <b>金额抖动</b>\n\n当前: <b>±{cur*100:.0f}%</b>\n\n"
        "每笔在基础区间金额上再随机扰动 ±X%，\n"
        "使金额更不可预测（0 = 关闭）。"
    )
    kb = [
        [InlineKeyboardButton("0% (关闭)", callback_data="rand:setjit:0"),
         InlineKeyboardButton("±10%",      callback_data="rand:setjit:0.10"),
         InlineKeyboardButton("±20%",      callback_data="rand:setjit:0.20")],
        [InlineKeyboardButton("±30%",      callback_data="rand:setjit:0.30"),
         InlineKeyboardButton("±50%",      callback_data="rand:setjit:0.50"),
         InlineKeyboardButton("±80%",      callback_data="rand:setjit:0.80")],
        [InlineKeyboardButton("🔙 随机性", callback_data="rand")],
    ]
    return text, InlineKeyboardMarkup(kb)


# 🎲 随机性预设
_RAND_PRESETS = {
    # 谨慎：间隔大，买卖接近对称，卖出幅度小，抖动小
    "safe": {
        "MIN_GAP_SECONDS":   60,
        "BUY_PROBABILITY":   0.5,
        "SELL_RATIO_MIN":    0.2,
        "SELL_RATIO_MAX":    0.5,
        "AMOUNT_JITTER_PCT": 0.10,
    },
    # 标准：默认配置
    "normal": {
        "MIN_GAP_SECONDS":   20,
        "BUY_PROBABILITY":   0.5,
        "SELL_RATIO_MIN":    0.3,
        "SELL_RATIO_MAX":    0.7,
        "AMOUNT_JITTER_PCT": 0.20,
    },
    # 激进：间隔小，买多卖少（更积攒持仓），抖动大
    "wild": {
        "MIN_GAP_SECONDS":   10,
        "BUY_PROBABILITY":   0.65,
        "SELL_RATIO_MIN":    0.4,
        "SELL_RATIO_MAX":    0.9,
        "AMOUNT_JITTER_PCT": 0.50,
    },
}



def _stats_menu() -> tuple[str, InlineKeyboardMarkup]:
    s = ledger.get_today_summary()
    text = (
        f"📊 <b>今日交易统计 ({s['date']})</b>\n\n"
        f"总交易: <b>{s['total_txs']}</b>\n"
        f"├ 买入: {s['total_buys']}\n"
        f"├ 卖出: {s['total_sells']}\n"
        f"├ 转账: {s['total_transfers']}\n"
        f"└ 领费: {s['total_claims']}\n\n"
        f"<b>各钱包交易数:</b>\n"
    )
    for widx in sorted(s["wallets"].keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
        text += f"  #{widx}: {s['wallets'][widx]} 笔\n"
    kb = [[_back_btn()]]
    return text, InlineKeyboardMarkup(kb)


# ── ℹ️ 系统状态 ──────────────────────────────────────────────
def _status_menu() -> tuple[str, InlineKeyboardMarkup]:
    state = {}
    if Path(STATE_FILE).exists():
        try:
            state = json.load(open(STATE_FILE))
        except Exception:
            pass
    try:
        w3     = rpc_client.get_w3()
        rpc_ok = w3.is_connected()
        block  = w3.eth.block_number if rpc_ok else "—"
    except Exception:
        rpc_ok = False
        block  = "—"

    ctx = executor.get_context()
    text = (
        "ℹ️ <b>系统状态</b>\n\n"
        f"运行: {'🟢 运行中' if executor.is_running() else '🟡 暂停'}\n"
        f"启动: {state.get('started_at', '—')}\n"
        f"RPC: {'✅' if rpc_ok else '❌'}  区块: {block}\n\n"
        f"钱包数: {ctx['wallet_count']}\n"
        f"代币池: {ctx['token_count']}\n"
        f"陌生地址池: {ctx['stranger_count']}"
    )
    kb = [[_back_btn()]]
    return text, InlineKeyboardMarkup(kb)


# ══════════════════════════════════════════════════════════════
#  按钮路由
# ══════════════════════════════════════════════════════════════

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_admin(update.effective_chat.id):
        return await _deny(q)

    data  = q.data
    parts = data.split(":")
    cmd   = parts[0]

    try:
        # ── 主菜单导航 ────────────────────────────────────────
        if cmd == "menu":
            await q.edit_message_text(_main_title(), reply_markup=_main_menu_kb(), parse_mode="HTML")
            return

        if cmd == "run" and len(parts) == 1:
            t, kb = _run_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "sched" and len(parts) == 1:
            t, kb = _sched_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "wallets" and len(parts) == 1:
            t, kb = _wallets_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "swap" and len(parts) == 1:
            t, kb = _swap_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "xfer" and len(parts) == 1:
            t, kb = _xfer_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "claim" and len(parts) == 1:
            t, kb = _claim_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "tokens" and len(parts) == 1:
            t, kb = _tokens_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "strangers" and len(parts) == 1:
            t, kb = _strangers_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "gas" and len(parts) == 1:
            t, kb = _gas_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "params" and len(parts) == 1:
            t, kb = _params_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "rand" and len(parts) == 1:
            t, kb = _rand_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "stats" and len(parts) == 1:
            t, kb = _stats_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "status" and len(parts) == 1:
            t, kb = _status_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # ── ⚙️ 运行控制 ───────────────────────────────────────
        if cmd == "run" and parts[1] == "start":
            executor.set_running(True)
            t, kb = _run_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "run" and parts[1] == "pause":
            executor.set_running(False)
            t, kb = _run_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "run" and parts[1] == "stop":
            await q.edit_message_text("🛑 正在停止进程…", parse_mode="HTML")
            executor.stop()
            return

        # ── 📝 时间表 ────────────────────────────────────────
        if cmd == "sched" and parts[1] == "regen":
            events = scheduler.generate_daily_schedule()
            scheduler.save_schedule(events)
            t, kb = _sched_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "sched" and parts[1] == "clear":
            n = scheduler.clear_schedule()
            await q.edit_message_text(f"🗑 已清空 {n} 个事件", reply_markup=_main_menu_kb(), parse_mode="HTML"); return
        if cmd == "sched" and parts[1] == "preview":
            page = int(parts[2])
            t, kb = _sched_preview(page); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "sched" and parts[1] == "del":
            typ = parts[2]
            n = scheduler.remove_events_by_type(typ)
            await q.answer(f"已删除 {n} 个 {typ} 事件", show_alert=False)
            t, kb = _sched_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "sched" and parts[1] == "bywallet":
            page = int(parts[2])
            t, kb = _sched_by_wallet(page); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "sched" and parts[1] == "delw":
            widx = int(parts[2])
            n = scheduler.remove_events_by_wallet(widx)
            await q.answer(f"钱包 #{widx} 删除 {n} 个事件", show_alert=False)
            t, kb = _sched_by_wallet(0); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # ── 💼 钱包 ──────────────────────────────────────────
        if cmd == "wallets" and parts[1] == "bal":
            await q.edit_message_text("⏳ 查询中…", parse_mode="HTML")
            wallets = wallet_manager.load_wallets()
            w3 = rpc_client.get_w3()
            lines = [f"💰 <b>钱包 ETH 余额 (共 {len(wallets)})</b>\n"]
            total = 0.0
            for w in wallets:
                bal = wallet_manager.get_eth_balance(w3, w["address"])
                total += bal
                short = w["address"][:6] + "…" + w["address"][-4:]
                lines.append(f"#{w['index']:02d} <code>{short}</code>  {bal:.6f} ETH")
            lines.append(f"\n<b>总计: {total:.6f} ETH</b>")
            kb = [[InlineKeyboardButton("🔙 钱包管理", callback_data="wallets")]]
            await q.edit_message_text("\n".join(lines),
                                      reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            return
        if cmd == "wallets" and parts[1] == "list":
            page = int(parts[2])
            wallets = wallet_manager.load_wallets()
            chunk, p, pages = _safe_page(wallets, page, 10)
            text = f"📋 <b>钱包地址列表</b>（第 {p+1}/{pages}）\n\n"
            for w in chunk:
                text += f"#{w['index']:02d} <code>{w['address']}</code>\n"
            row = []
            if p > 0: row.append(InlineKeyboardButton("⬅️", callback_data=f"wallets:list:{p-1}"))
            if p < pages-1: row.append(InlineKeyboardButton("➡️", callback_data=f"wallets:list:{p+1}"))
            kb = []
            if row: kb.append(row)
            kb.append([InlineKeyboardButton("🔙 钱包管理", callback_data="wallets")])
            await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"); return
        if cmd == "wallets" and parts[1] == "each":
            page = int(parts[2])
            t, kb = _wallets_each(page); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "wallets" and parts[1] == "detail":
            widx = int(parts[2])
            t, kb = _wallet_detail(widx); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # ── 💱 Swap 开关 + 选钱包 ────────────────────────────
        if cmd == "swap" and parts[1] == "toggle":
            cur = executor.get_enabled()["swap"]
            executor.set_enabled("swap", not cur)
            t, kb = _swap_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "swap" and parts[1] == "pick":
            action = parts[2]; page = int(parts[3])
            t, kb = _pick_wallet_menu(action, page)
            await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # ── 📤 Transfer 开关 + 笔数 + 比例 ───────────────────
        if cmd == "xfer" and parts[1] == "toggle":
            cur = executor.get_enabled()["transfer"]
            executor.set_enabled("transfer", not cur)
            t, kb = _xfer_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "xfer" and parts[1] == "count":
            t, kb = _xfer_count_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "xfer" and parts[1] == "setcnt":
            overrides.set_param("TRANSFERS_PER_WALLET_DAY", int(parts[2]))
            await q.answer("✅ 已保存，下次重新生成时间表生效", show_alert=False)
            t, kb = _xfer_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "xfer" and parts[1] == "pct":
            t, kb = _xfer_pct_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "xfer" and parts[1] == "fix":
            # 固定比例：清除区间，设置 TRANSFER_PCT
            overrides.reset_param("TRANSFER_PCT_MIN")
            overrides.reset_param("TRANSFER_PCT_MAX")
            overrides.set_param("TRANSFER_PCT", float(parts[2]))
            t, kb = _xfer_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "xfer" and parts[1] == "rng":
            overrides.set_param("TRANSFER_PCT_MIN", float(parts[2]))
            overrides.set_param("TRANSFER_PCT_MAX", float(parts[3]))
            t, kb = _xfer_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        # 兼容旧按钮：setpct 作为固定比例
        if cmd == "xfer" and parts[1] == "setpct":
            overrides.reset_param("TRANSFER_PCT_MIN")
            overrides.reset_param("TRANSFER_PCT_MAX")
            overrides.set_param("TRANSFER_PCT", float(parts[2]))
            t, kb = _xfer_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # ── 💰 Claim 开关 + 笔数 ─────────────────────────────
        if cmd == "claim" and parts[1] == "toggle":
            cur = executor.get_enabled()["claim_fee"]
            executor.set_enabled("claim_fee", not cur)
            t, kb = _claim_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "claim" and parts[1] == "count":
            t, kb = _claim_count_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "claim" and parts[1] == "setcnt":
            overrides.set_param("CLAIMS_PER_WALLET_DAY", int(parts[2]))
            await q.answer("✅ 已保存，下次重新生成时间表生效", show_alert=False)
            t, kb = _claim_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # ── 🎯 手动触发（单钱包）──────────────────────────────
        if cmd == "manual":
            action = parts[1]; widx = int(parts[2])
            executor.enqueue_manual(widx, action)
            await q.answer(f"✅ 钱包 #{widx} {action} 已入队", show_alert=True)
            return

        # ── 🌟 手动触发（全部钱包）───────────────────────────
        if cmd == "manual_all":
            action = parts[1]
            n = 0
            for i in range(WALLETS_COUNT):
                if executor.enqueue_manual(i, action):
                    n += 1
            await q.answer(f"✅ 已为 {n} 个钱包排队 {action}", show_alert=True)
            return

        # ── 🪙 代币池刷新 ─────────────────────────────────────
        if cmd == "tokens" and parts[1] == "refresh":
            await q.edit_message_text("⏳ 刷新中…", parse_mode="HTML")
            n = executor.refresh_tokens()
            await q.answer(f"✅ 已刷新，共 {n} 个代币", show_alert=True)
            t, kb = _tokens_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # ── 🔑 陌生地址池刷新 ─────────────────────────────────
        if cmd == "strangers" and parts[1] == "refresh":
            await q.edit_message_text("⏳ 抓取中…", parse_mode="HTML")
            n = executor.refresh_strangers()
            await q.answer(f"✅ 已刷新，共 {n} 个陌生地址", show_alert=True)
            t, kb = _strangers_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # ── ⛽ Gas 设置 ──────────────────────────────────────
        if cmd == "gas" and parts[1] == "gwei":
            overrides.set_param("GAS_PRICE_DEFAULT_GWEI", float(parts[2]))
            t, kb = _gas_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "gas" and parts[1] == "cap":
            overrides.set_param("MAX_GAS_COST_USD", float(parts[2]))
            t, kb = _gas_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "gas" and parts[1] == "limit":
            overrides.set_param("GAS_LIMIT_MAX", int(parts[2]))
            t, kb = _gas_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # ── 🎲 交易参数 ───────────────────────────────────────
        if cmd == "p" and parts[1] == "tx":
            overrides.set_param("MIN_TX_PER_WALLET_DAY", int(parts[2]))
            overrides.set_param("MAX_TX_PER_WALLET_DAY", int(parts[3]))
            t, kb = _params_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "p" and parts[1] == "amt":
            overrides.set_param("TX_AMOUNT_MIN_ETH", float(parts[2]))
            overrides.set_param("TX_AMOUNT_MAX_ETH", float(parts[3]))
            t, kb = _params_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "p" and parts[1] == "tok":
            overrides.set_param("TOKEN_FETCH_COUNT", int(parts[2]))
            t, kb = _params_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "p" and parts[1] == "reset":
            overrides.reset_all()
            await q.answer("✅ 已重置全部参数到默认值", show_alert=True)
            t, kb = _params_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # ── 🎰 随机性调节 ────────────────────────────────────
        if cmd == "rand" and parts[1] == "gap":
            t, kb = _rand_gap_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "rand" and parts[1] == "setgap":
            overrides.set_param("MIN_GAP_SECONDS", int(parts[2]))
            t, kb = _rand_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "rand" and parts[1] == "buyp":
            t, kb = _rand_buyp_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "rand" and parts[1] == "setbuyp":
            overrides.set_param("BUY_PROBABILITY", float(parts[2]))
            t, kb = _rand_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "rand" and parts[1] == "sellr":
            t, kb = _rand_sellr_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "rand" and parts[1] == "setsr":
            overrides.set_param("SELL_RATIO_MIN", float(parts[2]))
            overrides.set_param("SELL_RATIO_MAX", float(parts[3]))
            t, kb = _rand_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "rand" and parts[1] == "jit":
            t, kb = _rand_jit_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "rand" and parts[1] == "setjit":
            overrides.set_param("AMOUNT_JITTER_PCT", float(parts[2]))
            t, kb = _rand_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return
        if cmd == "rand" and parts[1] == "preset":
            preset = _RAND_PRESETS.get(parts[2])
            if preset:
                for k, v in preset.items():
                    overrides.set_param(k, v)
                await q.answer(f"✅ 已应用预设: {parts[2]}", show_alert=False)
            t, kb = _rand_menu(); await q.edit_message_text(t, reply_markup=kb, parse_mode="HTML"); return

        # 兜底
        await q.answer("⚠️ 未知操作")

    except Exception as e:
        logger.exception(f"[TG] 回调处理异常: {e}")
        try:
            await q.edit_message_text(
                f"❌ 操作失败: {e}\n\n请返回主菜单重试",
                reply_markup=InlineKeyboardMarkup([[_back_btn()]]),
                parse_mode="HTML",
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
#  Bot 启动
# ══════════════════════════════════════════════════════════════

def run_bot() -> None:
    if not TG_BOT_TOKEN or TG_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.warning("[TG] 未配置 TG_BOT_TOKEN，Telegram 控制面板不启动")
        return

    app = Application.builder().token(TG_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu",  start_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("🤖 Telegram 控制面板已启动（发送 /start 打开菜单）")
    app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
