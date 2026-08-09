"""
notifier.py — Telegram Bot 推送模块

使用 requests 直接调用 Telegram Bot API（无需第三方库）。
支持超长消息自动分段发送（Telegram 单条上限 4096 字符）。

关键修复：
  - 对所有用户可控字段做 HTML escape（避免 API 返回 <>& 触发 TG 400）
  - 按「\n\n」段落边界切分，绝不切断 HTML 标签
"""

import html
import logging
import requests
import threading
from config import TG_BOT_TOKEN, TG_CHAT_ID

logger = logging.getLogger(__name__)

TG_API_BASE = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
MAX_LEN = 4000   # Telegram 硬上限是 4096，留出余量

_local = threading.local()


def _get_session() -> requests.Session:
    """获取或初始化线程局部 Session 实例，优化连接复用且保证并发安全。"""
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
    return _local.session


def _esc(s) -> str:
    """HTML 转义用户可控文本（名称/描述/地址等）。None 变空串。"""
    if s is None:
        return ""
    return html.escape(str(s), quote=False)


def _send_chunk(text: str) -> bool:
    """发送单条消息（HTML 格式）。"""
    url  = f"{TG_API_BASE}/sendMessage"
    data = {
        "chat_id":    TG_CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        session = _get_session()
        resp = session.post(url, data=data, timeout=15)
        if not resp.ok:
            logger.error(f"[TG] 发送失败: {resp.status_code} {resp.text[:300]}")
            return False
        return True
    except Exception as e:
        logger.error(f"[TG] 发送异常: {e}")
        return False


def send_message(text: str) -> None:
    """
    自动分段发送长消息。
    切分策略：优先在段落边界（双换行 \\n\\n），其次单换行，最后按字符切。
    """
    if not text.strip():
        return

    while len(text) > MAX_LEN:
        # 优先按段落切
        split_pos = text.rfind("\n\n", 0, MAX_LEN)
        if split_pos == -1:
            split_pos = text.rfind("\n", 0, MAX_LEN)
        if split_pos == -1:
            split_pos = MAX_LEN
        chunk = text[:split_pos]
        text  = text[split_pos:].lstrip("\n")
        if chunk.strip():
            _send_chunk(chunk)

    if text.strip():
        _send_chunk(text)


# ──────────────────────────────────────────────────────────────
#  消息格式化函数
# ──────────────────────────────────────────────────────────────

def fmt_daily_report(
    rd_funding:  list,
    rd_events:   list,
    rd_new_proj: list,
    rd_tge:      list,
    cr_funding:  list,
    cr_ido:      list,
    okboost:     list,
    report_date: str,
) -> str:
    lines = []
    lines.append(f"🦞 <b>空投项目日报 · {_esc(report_date)}</b>")
    lines.append("━" * 30)

    # ── 1. 项目动态 ──────────────────────────────────────────
    lines.append("\n📢 <b>【项目动态】</b>")
    if rd_events:
        for e in rd_events[:8]:
            name  = _esc(e.get("name", "—"))
            event = _esc(e.get("event", "—"))
            d     = _esc(e.get("date", ""))
            url   = e.get("url", "")
            line  = f"• <b>{name}</b> — {event}\n  📅 {d}"
            if url:
                line += f"\n  🔗 <a href=\"{_esc(url)}\">详情</a>"
            lines.append(line)
    else:
        lines.append("  今日暂无项目动态")

    # ── 2. 新融资（RootData） ─────────────────────────────────
    lines.append("\n💰 <b>【新融资 · RootData】</b>")
    if rd_funding:
        for f in rd_funding[:10]:
            investors = f.get("investors") or []
            investors_str = _esc("、".join(investors[:3]) if investors else "未披露")
            lines.append(
                f"• <b>{_esc(f.get('name','—'))}</b> [{_esc(f.get('round','—'))}]\n"
                f"  💵 {_esc(f.get('amount','未披露'))}  👥 {investors_str}\n"
                f"  🔗 <a href=\"{_esc(f.get('url',''))}\">详情</a>"
            )
    else:
        lines.append("  今日暂无 RootData 融资数据")

    # ── 3. 新融资（CryptoRank） ───────────────────────────────
    lines.append("\n💸 <b>【新融资 · CryptoRank】</b>")
    if cr_funding:
        for f in cr_funding[:10]:
            investors = f.get("investors") or []
            investors_str = _esc("、".join(investors[:3]) if investors else "未披露")
            lines.append(
                f"• <b>{_esc(f.get('name','—'))}</b> (${_esc(f.get('symbol','—'))}) [{_esc(f.get('round','—'))}]\n"
                f"  💵 {_esc(f.get('amount','未披露'))}  👥 {investors_str}\n"
                f"  🔗 <a href=\"{_esc(f.get('url',''))}\">详情</a>"
            )
    else:
        lines.append("  今日暂无 CryptoRank 融资数据")

    # ── 4. 新收录项目（RootData） ─────────────────────────────
    lines.append("\n🆕 <b>【新收录项目 · RootData】</b>")
    if rd_new_proj:
        for p in rd_new_proj[:8]:
            cats = p.get("category") or []
            tags = _esc("、".join(cats[:3]) if cats else "—")
            desc = p.get("desc", "") or ""
            desc_short = (desc[:80] + "…") if len(desc) > 80 else desc
            lines.append(
                f"• <b>{_esc(p.get('name','—'))}</b>  [{tags}]\n"
                f"  {_esc(desc_short)}\n"
                f"  🔗 <a href=\"{_esc(p.get('url',''))}\">详情</a>"
            )
    else:
        lines.append("  今日暂无新收录项目")

    # ── 5. 即将发币（TGE） ────────────────────────────────────
    lines.append("\n🚀 <b>【即将发币（7天内 TGE）】</b>")
    tge_combined = (rd_tge or []) + (cr_ido or [])
    if tge_combined:
        seen = set()
        for p in tge_combined[:10]:
            name = p.get("name", "—")
            if name in seen:
                continue
            seen.add(name)
            tge_date = p.get("tge_date") or p.get("start_date", "—")
            symbol   = p.get("token") or p.get("symbol", "—")
            lines.append(
                f"• <b>{_esc(name)}</b> (${_esc(symbol)})  📅 {_esc(tge_date)}\n"
                f"  🔗 <a href=\"{_esc(p.get('url',''))}\">详情</a>"
            )
    else:
        lines.append("  近期暂无 TGE 项目")

    # ── 6. OKBoost 每日动态 ───────────────────────────────────
    lines.append("\n⚡ <b>【OKBoost / OKX 动态】</b>")
    if okboost:
        for item in okboost[:5]:
            desc = item.get("desc", "") or ""
            desc_short = (desc[:100] + "…") if len(desc) > 100 else desc
            lines.append(
                f"• <b>{_esc(item.get('title','—'))}</b>\n"
                f"  {_esc(desc_short)}\n"
                f"  🔗 <a href=\"{_esc(item.get('url',''))}\">查看公告</a>"
            )
    else:
        lines.append("  今日暂无 OKBoost 相关公告")

    lines.append("\n" + "━" * 30)
    lines.append("🤖 <i>由 空投发掘助手 自动推送</i>")

    return "\n".join(lines)
