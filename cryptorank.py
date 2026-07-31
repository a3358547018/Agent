"""
cryptorank.py — CryptoRank API 数据抓取模块

覆盖功能：
  1. 当日融资轮次（Funding Rounds）
  2. 近期新上线 / 即将上币项目（IDO/IEO/ICO）

注意：
  - 使用 CryptoRank V2 公开 API（V1 已停用）
  - V2 鉴权通过 HTTP Header `X-Api-Key`，不再用 query `api_key`
"""

import threading
import requests
from datetime import date, timedelta
from config import CRYPTORANK_API_KEY

BASE_V2 = "https://api.cryptorank.io/v2"

_thread_local = threading.local()


def _get_session() -> requests.Session:
    """获取线程局部的 requests.Session 实例，保留连接池优势并避免并发冲突。"""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session()
    return _thread_local.session


def _get(endpoint: str, params: dict = None) -> dict:
    """统一 GET 请求，返回 data 字段；出错返回 {}。"""
    url = BASE_V2 + endpoint
    headers = {"X-Api-Key": CRYPTORANK_API_KEY}
    try:
        resp = _get_session().get(url, params=params or {}, headers=headers, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        # V2 返回结构通常是 {"data": [...], "meta": {...}}
        return body if isinstance(body, dict) else {}
    except Exception as e:
        print(f"[CryptoRank] {endpoint} 请求异常: {e}")
        return {}


# ── 1. 当日融资轮次 ──────────────────────────────────────────
def get_daily_funding(target_date: date = None) -> list[dict]:
    """
    返回指定日期（默认今天）的融资轮次列表。
    注意：CryptoRank 按 dateFrom/dateTo 范围过滤。
    """
    if target_date is None:
        target_date = date.today()
    date_str = target_date.strftime("%Y-%m-%d")

    raw = _get("/currencies/funding-rounds", {
        "dateFrom": date_str,
        "dateTo":   date_str,
        "limit":    50,
        "offset":   0,
    })

    items = raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        items = []
    result = []
    for item in items:
        investors = [inv.get("name", "") for inv in (item.get("investors") or [])]
        result.append({
            "name":      item.get("name") or item.get("currencyName", "—"),
            "symbol":    item.get("symbol") or item.get("key", "—"),
            "amount":    item.get("amount") or item.get("totalRaise", "未披露"),
            "round":     item.get("stage") or item.get("type", "—"),
            "investors": investors,
            "date":      item.get("date") or date_str,
            "url":       "https://cryptorank.io/ico/" + (item.get("key") or item.get("slug", "")),
        })
    return result


# ── 2. 即将上币 / IDO 项目 ───────────────────────────────────
def get_upcoming_ido(days_ahead: int = 7) -> list[dict]:
    """
    返回未来 days_ahead 天内即将开始 IDO/IEO/ICO 的项目。
    """
    today      = date.today()
    end_date   = today + timedelta(days=days_ahead)
    date_from  = today.strftime("%Y-%m-%d")
    date_to    = end_date.strftime("%Y-%m-%d")

    raw = _get("/currencies/token-sales", {
        "dateFrom": date_from,
        "dateTo":   date_to,
        "status":   "upcoming",
        "limit":    30,
        "offset":   0,
    })

    items = raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        items = []
    result = []
    for item in items:
        result.append({
            "name":       item.get("name") or item.get("currencyName", "—"),
            "symbol":     item.get("symbol") or item.get("key", "—"),
            "platform":   item.get("platform") or item.get("launchpad", "—"),
            "start_date": item.get("startDate") or item.get("saleStartDate", "—"),
            "end_date":   item.get("endDate")   or item.get("saleEndDate",   "—"),
            "raise":      item.get("hardCap")   or item.get("totalRaise", "未披露"),
            "url":        "https://cryptorank.io/ico/" + (item.get("key") or item.get("slug", "")),
        })
    return result


# ── 3. 近期新上线项目（Recently Listed）────────────────────────
def get_recent_listings(days: int = 1) -> list[dict]:
    """
    返回最近 days 天内在 CryptoRank 新收录的代币。
    """
    since = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    raw = _get("/currencies", {
        "dateFrom": since,
        "sort":     "addedAt",
        "order":    "desc",
        "limit":    30,
    })

    items = raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        items = []
    result = []
    for item in items:
        result.append({
            "name":     item.get("name", "—"),
            "symbol":   item.get("symbol") or item.get("key", "—"),
            "category": item.get("categories") or item.get("tags", []),
            "added":    item.get("addedAt") or item.get("listedAt", "—"),
            "url":      "https://cryptorank.io/price/" + item.get("key", item.get("slug", "")),
        })
    return result
