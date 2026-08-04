"""
rootdata.py — RootData API 数据抓取模块

覆盖功能：
  1. 当日融资事件列表
  2. 新收录项目列表
  3. 项目动态（日历事件）
  4. 即将 TGE / 发币项目
"""

import requests
import threading
from datetime import date, datetime
from config import ROOTDATA_API_KEY

BASE_URL = "https://api.rootdata.com/open"

HEADERS = {
    "apikey": ROOTDATA_API_KEY,
    "Content-Type": "application/json",
    "language": "cn",        # 返回中文内容；改成 "en" 可切换英文
}

_local = threading.local()


def _get_session() -> requests.Session:
    """获取线程局部的 requests.Session 实例，确保线程安全且复用连接"""
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
    return _local.session


def _post(endpoint: str, payload: dict) -> dict:
    """统一 POST 请求封装，返回 data 字段；出错返回空 dict。"""
    url = BASE_URL + endpoint
    try:
        resp = _get_session().post(url, json=payload, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        if body.get("result") is True or body.get("code") == 200:
            return body.get("data", {})
        else:
            print(f"[RootData] {endpoint} 业务错误: {body.get('message', body)}")
            return {}
    except Exception as e:
        print(f"[RootData] {endpoint} 请求异常: {e}")
        return {}


# ── 1. 当日新融资事件 ─────────────────────────────────────────
def get_daily_funding(target_date: date = None) -> list[dict]:
    """
    返回指定日期（默认今天）的融资事件列表。
    每条记录包含：项目名、融资金额、轮次、投资方、日期、链接。
    """
    if target_date is None:
        target_date = date.today()
    date_str = target_date.strftime("%Y-%m-%d")

    data = _post("/get_invest_list", {
        "page": 1,
        "page_size": 50,
        "date": date_str,         # 精确到日
    })

    items = data.get("items") or data.get("list") or (data if isinstance(data, list) else [])
    result = []
    for item in items:
        result.append({
            "name":      item.get("project_name") or item.get("name", "—"),
            "amount":    item.get("amount") or item.get("raise_amount", "未披露"),
            "round":     item.get("round") or item.get("financing_round", "—"),
            "investors": item.get("investors") or item.get("lead_investors", []),
            "date":      item.get("date") or date_str,
            "url":       item.get("url") or ("https://www.rootdata.com/Projects/" + str(item.get("id", ""))),
            "desc":      item.get("description") or item.get("desc", ""),
        })
    return result


# ── 2. 新收录项目 ────────────────────────────────────────────
def get_new_projects(days: int = 1) -> list[dict]:
    """
    返回最近 days 天内新收录的项目。
    """
    data = _post("/get_pro_list", {
        "page": 1,
        "page_size": 30,
        "type": 1,            # 1 = 按收录时间排序
        "day": days,
    })

    items = data.get("items") or data.get("list") or (data if isinstance(data, list) else [])
    result = []
    for item in items:
        result.append({
            "name":       item.get("project_name") or item.get("name", "—"),
            "category":   item.get("tags") or item.get("category", []),
            "desc":       item.get("description") or item.get("desc", ""),
            "added_date": item.get("add_time") or item.get("created_at", ""),
            "url":        item.get("url") or ("https://www.rootdata.com/Projects/" + str(item.get("id", ""))),
        })
    return result


# ── 3. 项目动态（日历事件） ────────────────────────────────────
def get_project_events(target_date: date = None) -> list[dict]:
    """
    返回指定日期的日历事件（融资公告、合作、主网上线等）。
    """
    if target_date is None:
        target_date = date.today()
    date_str = target_date.strftime("%Y-%m-%d")

    data = _post("/get_calendar_list", {
        "page": 1,
        "page_size": 30,
        "date": date_str,
    })

    items = data.get("items") or data.get("list") or (data if isinstance(data, list) else [])
    result = []
    for item in items:
        result.append({
            "name":     item.get("project_name") or item.get("name", "—"),
            "event":    item.get("event_name") or item.get("title", "—"),
            "date":     item.get("date") or date_str,
            "url":      item.get("url") or "",
            "desc":     item.get("description") or item.get("desc", ""),
        })
    return result


# ── 4. 即将 TGE / 发币项目 ───────────────────────────────────
def get_upcoming_tge(days_ahead: int = 7) -> list[dict]:
    """
    返回未来 days_ahead 天内即将发币（TGE）的项目。
    """
    data = _post("/get_token_unlock", {
        "page": 1,
        "page_size": 20,
        "type": 1,           # 1 = TGE 类型
        "day": days_ahead,
    })

    items = data.get("items") or data.get("list") or (data if isinstance(data, list) else [])
    result = []
    for item in items:
        result.append({
            "name":       item.get("project_name") or item.get("name", "—"),
            "tge_date":   item.get("tge_date") or item.get("date", "—"),
            "token":      item.get("symbol") or item.get("token_symbol", "—"),
            "total_raise": item.get("total_raise") or item.get("raise_amount", "未披露"),
            "url":        item.get("url") or ("https://www.rootdata.com/Projects/" + str(item.get("id", ""))),
        })
    return result
