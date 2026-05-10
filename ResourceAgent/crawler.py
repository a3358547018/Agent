"""
crawler.py — 资源抓取模块

两个抓取源：
  1. Telegram 群组监听（Telethon 用户端，可监听任意公开群）
  2. 资源网站爬取（GitHub Trending / Product Hunt / HackerNews / Toolify 等）
"""

import re
import asyncio
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from config import (
    TG_API_ID, TG_API_HASH, TG_PHONE,
    TG_SOURCE_GROUPS, CRAWL_SOURCES, RESOURCE_KEYWORDS,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════

def _is_resource(text: str) -> bool:
    """判断文本是否命中资源关键词。"""
    t = text.lower()
    return any(kw.lower() in t for kw in RESOURCE_KEYWORDS)


def _extract_links(text: str) -> list[str]:
    """从文本中提取所有 URL。"""
    return re.findall(r'https?://[^\s\)\]\"\'<>]+', text)


def _build_resource(title: str, url: str, desc: str, source: str) -> dict:
    return {
        "title":      title.strip()[:200],
        "url":        url.strip(),
        "desc":       desc.strip()[:500],
        "source":     source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════
#  1. Telegram 群组抓取
# ══════════════════════════════════════════════════════════════

async def fetch_tg_resources(limit_per_group: int = 50) -> list:
    """
    用 Telethon 拉取 TG 群最新消息，筛选含资源关键词的条目。
    返回资源列表。
    """
    try:
        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError
    except ImportError:
        logger.warning("[TG] telethon 未安装，跳过 TG 抓取。pip install telethon")
        return []

    if not TG_SOURCE_GROUPS:
        logger.info("[TG] 未配置 TG 群组，跳过。")
        return []

    results = []
    client = TelegramClient("resource_agent_session", TG_API_ID, TG_API_HASH)

    # 使用 async with 统一管理生命周期，避免 start + async with 重复启动
    try:
        async with client:
            try:
                await client.start(phone=TG_PHONE)
            except SessionPasswordNeededError:
                logger.error("[TG] 账号开启了两步验证，请先在 config.py 配置或手动登录。")
                return []

            for group in TG_SOURCE_GROUPS:
                try:
                    entity   = await client.get_entity(group)
                    messages = await client.get_messages(entity, limit=limit_per_group)
                    hit_count = 0
                    for msg in messages:
                        text = msg.text or ""
                        if not text or not _is_resource(text):
                            continue
                        links = _extract_links(text)
                        url   = links[0] if links else ""
                        first_line = text.split("\n")[0].strip()[:100]
                        results.append(_build_resource(
                            title  = first_line or "TG资源",
                            url    = url,
                            desc   = text[:300],
                            source = f"tg:{getattr(entity, 'username', str(group))}",
                        ))
                        hit_count += 1
                    logger.info(f"[TG] {group} 抓取 {len(messages)} 条，命中 {hit_count} 条")
                except Exception as e:
                    logger.error(f"[TG] 抓取群 {group} 失败: {e}")
    except Exception as e:
        logger.error(f"[TG] 客户端异常: {e}")
        return results

    return results


# ══════════════════════════════════════════════════════════════
#  2. 网站爬取
# ══════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _get_soup(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.error(f"[爬虫] 请求 {url} 失败: {e}")
        return None


# ── GitHub Trending ──────────────────────────────────────────
def fetch_github_trending() -> list[dict]:
    soup = _get_soup("https://github.com/trending")
    if not soup:
        return []
    results = []
    for repo in soup.select("article.Box-row")[:20]:
        name_tag = repo.select_one("h2 a")
        desc_tag = repo.select_one("p")
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True).replace("\n", "").replace(" ", "")
        url  = "https://github.com" + name_tag.get("href", "")
        desc = desc_tag.get_text(strip=True) if desc_tag else ""
        results.append(_build_resource(name, url, desc, "github_trending"))
    logger.info(f"[GitHub Trending] 抓取 {len(results)} 个项目")
    return results


# ── Product Hunt ─────────────────────────────────────────────
def fetch_product_hunt() -> list[dict]:
    soup = _get_soup("https://www.producthunt.com")
    if not soup:
        return []
    results = []
    # Product Hunt 部分内容是 JS 渲染的，抓取静态可见部分
    for item in soup.select('[data-test="product-item"]')[:15]:
        name_tag = item.select_one("strong") or item.select_one("h3")
        link_tag = item.select_one("a[href]")
        desc_tag = item.select_one("p")
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        href = link_tag.get("href", "") if link_tag else ""
        url  = ("https://www.producthunt.com" + href) if href.startswith("/") else href
        desc = desc_tag.get_text(strip=True) if desc_tag else ""
        if not _is_resource(name + " " + desc):
            continue
        results.append(_build_resource(name, url, desc, "product_hunt"))
    logger.info(f"[Product Hunt] 抓取 {len(results)} 个产品")
    return results


# ── Hacker News（Show HN / Ask HN 资源帖）───────────────────
def fetch_hacker_news() -> list[dict]:
    # 使用官方 JSON API
    try:
        resp = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=10
        )
        story_ids = resp.json()[:50]
    except Exception as e:
        logger.error(f"[HN] 获取 top stories 失败: {e}")
        return []

    results = []
    for sid in story_ids:
        try:
            s = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                timeout=8
            ).json()
            title = s.get("title", "")
            url   = s.get("url", f"https://news.ycombinator.com/item?id={sid}")
            if _is_resource(title):
                results.append(_build_resource(title, url, "", "hacker_news"))
        except Exception:
            continue
        if len(results) >= 10:
            break

    logger.info(f"[Hacker News] 抓取 {len(results)} 条资源")
    return results


# ── Toolify AI（AI工具目录）──────────────────────────────────
def fetch_toolify_ai() -> list[dict]:
    soup = _get_soup("https://www.toolify.ai")
    if not soup:
        return []
    results = []
    for card in soup.select(".tool-card, .product-card, article")[:20]:
        name_tag = card.select_one("h2, h3, .title, strong")
        link_tag = card.select_one("a[href]")
        desc_tag = card.select_one("p, .desc, .description")
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        href = link_tag.get("href", "") if link_tag else ""
        url  = ("https://www.toolify.ai" + href) if href.startswith("/") else href
        desc = desc_tag.get_text(strip=True) if desc_tag else ""
        results.append(_build_resource(name, url, desc, "toolify_ai"))
    logger.info(f"[Toolify AI] 抓取 {len(results)} 个工具")
    return results


# ── Free Programming Books（GitHub）─────────────────────────
def fetch_free_books() -> list[dict]:
    """抓取 GitHub awesome free-programming-books 的最新 commit 变更。"""
    try:
        resp = requests.get(
            "https://api.github.com/repos/EbookFoundation/free-programming-books/commits",
            headers={**HEADERS, "Accept": "application/vnd.github.v3+json"},
            params={"per_page": 5},
            timeout=10,
        )
        commits = resp.json()
    except Exception as e:
        logger.error(f"[FreeBooks] 获取 commits 失败: {e}")
        return []

    results = []
    for c in commits:
        msg = c.get("commit", {}).get("message", "")
        sha = c.get("sha", "")
        if not msg:
            continue
        results.append(_build_resource(
            title  = msg.split("\n")[0][:100],
            url    = f"https://github.com/EbookFoundation/free-programming-books/commit/{sha}",
            desc   = msg[:300],
            source = "free_programming_books",
        ))
    logger.info(f"[FreeBooks] 抓取 {len(results)} 条更新")
    return results


# ══════════════════════════════════════════════════════════════
#  统一入口
# ══════════════════════════════════════════════════════════════

def fetch_website_resources() -> list[dict]:
    """按 config 中的开关，抓取所有启用的网站源。"""
    all_resources = []
    cfg = CRAWL_SOURCES

    if cfg.get("github_trending", {}).get("enabled"):
        all_resources += fetch_github_trending()

    if cfg.get("product_hunt", {}).get("enabled"):
        all_resources += fetch_product_hunt()

    if cfg.get("hacker_news", {}).get("enabled"):
        all_resources += fetch_hacker_news()

    if cfg.get("toolify_ai", {}).get("enabled"):
        all_resources += fetch_toolify_ai()

    if cfg.get("free_programming_books", {}).get("enabled"):
        all_resources += fetch_free_books()

    return all_resources


async def fetch_all_resources() -> list[dict]:
    """抓取全部来源（TG + 网站），返回合并列表。"""
    website_res = fetch_website_resources()
    tg_res      = await fetch_tg_resources()
    all_res     = website_res + tg_res
    logger.info(f"[Crawler] 共抓取资源 {len(all_res)} 条（网站 {len(website_res)} + TG {len(tg_res)}）")
    return all_res
