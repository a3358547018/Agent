"""
notifier.py — Telegram Bot 推送模块

使用 requests 直接调用 Telegram Bot API（无需第三方库）。
支持超长消息自动分段发送（Telegram 单条上限 4096 字符）。
"""

import requests
from config import TG_BOT_TOKEN, TG_CHAT_ID

TG_API_BASE = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
MAX_LEN = 4000   # 留出余量


def _send_chunk(text: str) -> bool:
    """发送单条消息（MarkdownV2 格式）。"""
    url  = f"{TG_API_BASE}/sendMessage"
    data = {
        "chat_id":    TG_CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",          # 使用 HTML 避免 MarkdownV2 转义问题
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, data=data, timeout=15)
        if not resp.ok:
            print(f"[TG] 发送失败: {resp.status_code} {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"[TG] 发送异常: {e}")
        return False


def send_message(text: str) -> None:
    """自动分段发送长消息。"""
    if not text.strip():
        return
    # 按段落切割，避免截断 HTML 标签
    while len(text) > MAX_LEN:
        split_pos = text.rfind("\n", 0, MAX_LEN)
        if split_pos == -1:
            split_pos = MAX_LEN
        chunk = text[:split_pos]
        text  = text[split_pos:].lstrip("\n")
        _send_chunk(chunk)
    if text.strip():
        _send_chunk(text)


# ──────────────────────────────────────────────────────────────
#  消息格式化函数
# ──────────────────────────────────────────────────────────────

def fmt_daily_report(
    rd_funding:  list[dict],
    rd_events:   list[dict],
    rd_new_proj: list[dict],
    rd_tge:      list[dict],
    cr_funding:  list[dict],
    cr_ido:      list[dict],
    okboost:     list[dict],
    report_date: str,
) -> str:
    lines = []
    lines.append(f"🦞 <b>空投项目日报 · {report_date}</b>")
    lines.append("━" * 30)

    # ── 1. 项目动态 ──────────────────────────────────────────
    lines.append("\n📢 <b>【项目动态】</b>")
    if rd_events:
        for e in rd_events[:8]:
            lines.append(
                f"• <b>{e['name']}</b> — {e['event']}\n"
                f"  📅 {e['date']}"
                + (f"\n  🔗 <a href='{e['url']}'>详情</a>" if e.get("url") else "")
            )
    else:
        lines.append("  今日暂无项目动态")

    # ── 2. 新融资（RootData） ─────────────────────────────────
    lines.append("\n💰 <b>【新融资 · RootData】</b>")
    if rd_funding:
        for f in rd_funding[:10]:
            investors_str = "、".join(f["investors"][:3]) if f["investors"] else "未披露"
            lines.append(
                f"• <b>{f['name']}</b> [{f['round']}]\n"
                f"  💵 {f['amount']}  👥 {investors_str}\n"
                f"  🔗 <a href='{f['url']}'>详情</a>"
            )
    else:
        lines.append("  今日暂无 RootData 融资数据")

    # ── 3. 新融资（CryptoRank） ───────────────────────────────
    lines.append("\n💸 <b>【新融资 · CryptoRank】</b>")
    if cr_funding:
        for f in cr_funding[:10]:
            investors_str = "、".join(f["investors"][:3]) if f["investors"] else "未披露"
            lines.append(
                f"• <b>{f['name']}</b> (${f['symbol']}) [{f['round']}]\n"
                f"  💵 {f['amount']}  👥 {investors_str}\n"
                f"  🔗 <a href='{f['url']}'>详情</a>"
            )
    else:
        lines.append("  今日暂无 CryptoRank 融资数据")

    # ── 4. 新收录项目（RootData） ─────────────────────────────
    lines.append("\n🆕 <b>【新收录项目 · RootData】</b>")
    if rd_new_proj:
        for p in rd_new_proj[:8]:
            tags = "、".join(p["category"][:3]) if p["category"] else "—"
            lines.append(
                f"• <b>{p['name']}</b>  [{tags}]\n"
                f"  {p['desc'][:80] + '…' if len(p['desc']) > 80 else p['desc']}\n"
                f"  🔗 <a href='{p['url']}'>详情</a>"
            )
    else:
        lines.append("  今日暂无新收录项目")

    # ── 5. 即将发币（TGE） ────────────────────────────────────
    lines.append("\n🚀 <b>【即将发币（7天内 TGE）】</b>")
    tge_combined = rd_tge + cr_ido
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
                f"• <b>{name}</b> (${symbol})  📅 {tge_date}\n"
                f"  🔗 <a href='{p['url']}'>详情</a>"
            )
    else:
        lines.append("  近期暂无 TGE 项目")

    # ── 6. OKBoost 每日动态 ───────────────────────────────────
    lines.append("\n⚡ <b>【OKBoost / OKX 动态】</b>")
    if okboost:
        for item in okboost[:5]:
            lines.append(
                f"• <b>{item['title']}</b>\n"
                f"  {item['desc'][:100] + '…' if len(item['desc']) > 100 else item['desc']}\n"
                f"  🔗 <a href='{item['url']}'>查看公告</a>"
            )
    else:
        lines.append("  今日暂无 OKBoost 相关公告")

    lines.append("\n━" * 30)
    lines.append("🤖 <i>由 空投发掘助手 自动推送</i>")

    return "\n".join(lines)
