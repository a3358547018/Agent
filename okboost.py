"""
okboost.py — OKX / OKBoost 每日动态抓取模块

策略：
  抓取 OKX 官方公告 RSS，筛选当日内容，
  提取 Boost / 质押挖矿 / Launchpool / 新币挖矿 等相关动态。
"""

import re
import threading
import requests
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime

OKX_RSS_URL = "https://www.okx.com/help-center/rss.xml"

_thread_local = threading.local()


def _get_session() -> requests.Session:
    """获取或初始化线程局部 Session 实例，保留连接池并避免并发冲突。"""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session()
    return _thread_local.session

# 关键词列表——命中其一即纳入推送
BOOST_KEYWORDS = [
    "boost", "launchpool", "launchpad",
    "jumpstart", "新币挖矿", "空投", "airdrop",
    "质押", "staking", "earn", "挖矿", "矿池",
    "上新", "上线", "okb", "okboost",
]


def _fetch_rss() -> list[dict]:
    """拉取并解析 OKX RSS，返回条目列表。"""
    try:
        resp = _get_session().get(OKX_RSS_URL, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"[OKBoost] RSS 拉取失败: {e}")
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    items = []
    for item in channel.findall("item"):
        title       = (item.findtext("title") or "").strip()
        link        = (item.findtext("link")  or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date_str = item.findtext("pubDate") or ""

        # 解析发布时间
        pub_dt = None
        if pub_date_str:
            try:
                pub_dt = parsedate_to_datetime(pub_date_str)
            except Exception:
                pass

        items.append({
            "title":   title,
            "link":    link,
            "desc":    re.sub(r"<[^>]+>", "", description).strip(),
            "pub_dt":  pub_dt,
        })
    return items


def get_daily_okboost(target_date: date = None) -> list[dict]:
    """
    返回指定日期（默认今天）内与 OKBoost / Launchpool / 空投相关的公告。
    """
    if target_date is None:
        target_date = date.today()

    all_items = _fetch_rss()
    result = []

    for item in all_items:
        # 时间过滤：只取 target_date 当天
        if item["pub_dt"] is not None:
            # 统一转本地日期比较
            try:
                local_date = item["pub_dt"].astimezone().date()
            except Exception:
                local_date = item["pub_dt"].date()
            if local_date != target_date:
                continue

        # 关键词过滤
        combined = (item["title"] + " " + item["desc"]).lower()
        if any(kw in combined for kw in BOOST_KEYWORDS):
            result.append({
                "title": item["title"],
                "desc":  item["desc"][:200] + ("…" if len(item["desc"]) > 200 else ""),
                "url":   item["link"],
                "date":  target_date.strftime("%Y-%m-%d"),
            })

    return result
