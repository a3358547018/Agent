"""
twitter_poster.py — Twitter/X 自动发推模块

由于没有 Twitter 开发者 API，本模块使用 Playwright 模拟浏览器登录并发推。

依赖：
  pip install playwright
  playwright install chromium

安全说明：
  - 使用无头浏览器，行为与真实用户一致
  - 内置随机延迟，避免触发风控
  - 每日发推数量限制（config.py 中的 TWITTER_MAX_TWEETS_PER_DAY）
  - 仅在 TWEET_ACTIVE_HOURS 时间段内发推
"""

import json
import logging
import random
import time
import os
from datetime import datetime
from pathlib import Path
from config import (
    TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_EMAIL,
    TWITTER_MAX_TWEETS_PER_DAY, TWITTER_MIN_INTERVAL_MINUTES,
    TWEET_ACTIVE_HOURS,
)

from threading import Lock as _FileLock

logger = logging.getLogger(__name__)

# 发推计数文件
_COUNT_FILE = Path("data/tweet_count.json")
_COUNT_LOCK = _FileLock()


# ══════════════════════════════════════════════════════════════
#  发推计数管理（线程安全 + 原子写）
# ══════════════════════════════════════════════════════════════

def _load_count_unlocked() -> dict:
    if _COUNT_FILE.exists():
        try:
            with open(_COUNT_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"date": "", "count": 0}


def _save_count_unlocked(data: dict) -> None:
    _COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _COUNT_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f)
    tmp.replace(_COUNT_FILE)


def _get_today_count() -> int:
    with _COUNT_LOCK:
        data = _load_count_unlocked()
    today = datetime.now().strftime("%Y-%m-%d")
    if data.get("date") != today:
        return 0
    return data.get("count", 0)


def _increment_count() -> None:
    with _COUNT_LOCK:
        data  = _load_count_unlocked()
        today = datetime.now().strftime("%Y-%m-%d")
        if data.get("date") != today:
            data = {"date": today, "count": 0}
        data["count"] += 1
        _save_count_unlocked(data)


def _is_active_hour() -> bool:
    """判断当前是否在允许发推的时间段内。"""
    hour = datetime.now().hour
    return TWEET_ACTIVE_HOURS[0] <= hour <= TWEET_ACTIVE_HOURS[1]


def _can_tweet() -> bool:
    if not _is_active_hour():
        logger.info(f"[Twitter] 当前不在活跃时段 {TWEET_ACTIVE_HOURS}，跳过发推")
        return False
    count = _get_today_count()
    if count >= TWITTER_MAX_TWEETS_PER_DAY:
        logger.info(f"[Twitter] 今日已发 {count} 条，达到上限 {TWITTER_MAX_TWEETS_PER_DAY}")
        return False
    return True


# ══════════════════════════════════════════════════════════════
#  Playwright 发推核心
# ══════════════════════════════════════════════════════════════

_SESSION_FILE = Path("data/twitter_session.json")


def _human_delay(min_s: float = 0.5, max_s: float = 2.0) -> None:
    """模拟人类操作延迟。"""
    time.sleep(random.uniform(min_s, max_s))


def _post_tweet_playwright(tweet_text: str) -> bool:
    """
    使用 Playwright 打开 Twitter，登录（或复用 session），发推。
    返回是否成功。
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.error("[Twitter] Playwright 未安装。请运行: pip install playwright && playwright install chromium")
        return False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )

        # 尝试复用已保存的 session（cookies）
        context_kwargs = {}
        if _SESSION_FILE.exists():
            context_kwargs["storage_state"] = str(_SESSION_FILE)

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            **context_kwargs,
        )
        page = context.new_page()

        try:
            page.goto("https://x.com/home", timeout=30000)
            _human_delay(2, 4)

            # 检查是否已登录（有 compose tweet 按钮）
            logged_in = page.is_visible('[data-testid="tweetTextarea_0"]', timeout=5000)

            if not logged_in:
                logger.info("[Twitter] 未检测到登录态，开始登录流程…")
                if not _do_login(page):
                    browser.close()
                    return False
                # 保存 session
                _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(_SESSION_FILE))
                logger.info("[Twitter] Session 已保存，后续免登录")

            # ── 点击发推按钮（新推文）────────────────────────
            compose_btn = page.locator('[data-testid="SideNav_NewTweet_Button"]')
            compose_btn.click()
            _human_delay(1, 2)

            # ── 在文本框输入推文 ──────────────────────────────
            textarea = page.locator('[data-testid="tweetTextarea_0"]')
            textarea.click()
            _human_delay(0.3, 0.8)

            # 逐字符输入（更像人类）
            for char in tweet_text:
                textarea.type(char, delay=random.randint(20, 80))

            _human_delay(1, 2)

            # ── 点击发送 ──────────────────────────────────────
            send_btn = page.locator('[data-testid="tweetButtonInline"]')
            send_btn.click()
            _human_delay(2, 4)

            # 确认发推成功（检查 toast 消息或 URL 变化）
            try:
                page.wait_for_selector(
                    'text="Your post was sent"',
                    timeout=10000,
                )
                logger.info(f"[Twitter] 发推成功: {tweet_text[:50]}…")
                _increment_count()
                browser.close()
                return True
            except PWTimeout:
                # 部分情况没有 toast，尝试其他方式确认
                logger.info(f"[Twitter] 发推可能成功（无 toast）: {tweet_text[:50]}…")
                _increment_count()
                browser.close()
                return True

        except Exception as e:
            logger.error(f"[Twitter] 发推过程异常: {e}")
            # 保存截图帮助调试
            _screenshot_path = Path("logs/twitter_error.png")
            _screenshot_path.parent.mkdir(exist_ok=True)
            try:
                page.screenshot(path=str(_screenshot_path))
                logger.info(f"[Twitter] 错误截图已保存: {_screenshot_path}")
            except Exception:
                pass
            browser.close()
            return False


def _do_login(page) -> bool:
    """执行登录流程（处理邮箱/手机 → 密码 → 可能的二次验证）。"""
    try:
        from playwright.sync_api import TimeoutError as PWTimeout
    except ImportError:
        return False

    try:
        page.goto("https://x.com/i/flow/login", timeout=30000)
        _human_delay(2, 3)

        # Step 1: 输入用户名/邮箱
        username_input = page.locator('input[name="text"]')
        username_input.fill(TWITTER_USERNAME)
        _human_delay(0.5, 1)
        page.keyboard.press("Enter")
        _human_delay(1.5, 2.5)

        # Step 2: 有时会要求输入邮箱（中间验证步骤）
        try:
            extra_input = page.locator('input[name="text"]')
            if extra_input.is_visible(timeout=3000):
                extra_input.fill(TWITTER_EMAIL or TWITTER_USERNAME)
                _human_delay(0.5, 1)
                page.keyboard.press("Enter")
                _human_delay(1.5, 2.5)
        except Exception:
            pass

        # Step 3: 输入密码
        pwd_input = page.locator('input[name="password"]')
        pwd_input.fill(TWITTER_PASSWORD)
        _human_delay(0.5, 1)
        page.keyboard.press("Enter")
        _human_delay(3, 5)

        # 等待登录完成
        page.wait_for_url("https://x.com/home", timeout=20000)
        logger.info("[Twitter] 登录成功")
        return True

    except Exception as e:
        logger.error(f"[Twitter] 登录失败: {e}")
        return False


# ══════════════════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════════════════

def post_tweet(tweet_text: str) -> bool:
    """
    发送单条推文。
    返回 True 表示成功，False 表示跳过或失败。
    注意：不在此函数做间隔 sleep，间隔交由 post_tweets_batch 统一控制。
    """
    if not _can_tweet():
        return False
    return _post_tweet_playwright(tweet_text)


def post_tweets_batch(resources_with_tweets: list) -> tuple[int, list]:
    """
    批量发推。
    返回 (成功发出的条数, 未发出的资源列表)。
    调用方应把"未发出的资源"退回队列，这样不会和已发的位置错位。
    """
    ok = 0
    unsent = []

    for i, r in enumerate(resources_with_tweets):
        tweet_text = r.get("tweet_text", "")
        if not tweet_text:
            # 空文本直接丢弃，不退回（避免无限循环）
            continue

        # 如果已达每日上限或过了活跃时段，把剩余全部退回
        if not _can_tweet():
            unsent.extend(resources_with_tweets[i:])
            break

        success = post_tweet(tweet_text)
        if success:
            ok += 1
            # 间隔等待（只在还有下一条时等待）
            if i < len(resources_with_tweets) - 1:
                wait = TWITTER_MIN_INTERVAL_MINUTES * 60 + random.randint(-60, 120)
                logger.info(f"[Twitter] 等待 {max(wait, 60) // 60} 分钟后发下一条…")
                time.sleep(max(wait, 60))
        else:
            # 发送失败：退回队列，之后再试
            unsent.append(r)

    logger.info(f"[Twitter] 批量发推完成: 成功 {ok} / 未发出 {len(unsent)}")
    return ok, unsent
