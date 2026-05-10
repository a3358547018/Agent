"""
ai_writer.py — AI 自动生成推文模块

支持多个 AI 提供商：
  - DeepSeek（默认，便宜高效）
  - OpenAI GPT-4o
  - 智谱 GLM

工作流程：
  1. 拉取参考账号的推文风格样本（静态预置 + 可扩展）
  2. 将资源信息 + 风格样本组合成 Prompt
  3. 调用 AI 生成推文正文
  4. 自动附加资源链接和话题标签
"""

import re
import logging
import requests
from config import (
    AI_PROVIDER, AI_API_KEY, AI_MODEL,
    AI_BASE_URL, TWEET_LANGUAGE,
    STYLE_REFERENCE_ACCOUNTS,
)

logger = logging.getLogger(__name__)

# ── 风格样本库（静态预置，覆盖常见资源分享号风格）────────────
STYLE_SAMPLES = {
    "zh": [
        "🔥 强烈推荐！{title}\n这个开源工具太好用了，{desc}\n→ {url}\n#开源 #AI工具 #效率",
        "📚 发现宝藏资源：{title}\n{desc}\n免费获取 👇\n{url}\n#资源分享 #免费 #干货",
        "✨ 今天分享一个超厉害的项目：{title}\n{desc}\nGitHub链接：{url}\n#GitHub #开源项目",
        "💡 {title} — 值得收藏的好东西\n{desc}\n🔗 {url}\n#工具推荐 #程序员 #效率神器",
        "🚀 AI工具又更新了！{title}\n{desc}\n→ {url}\n#AITools #人工智能 #生产力",
    ],
    "en": [
        "🔥 Just discovered an amazing open-source tool: {title}\n{desc}\n👉 {url}\n#OpenSource #AITools #Dev",
        "📚 Free resource alert! {title}\n{desc}\nGet it here → {url}\n#FreeResources #Learning",
        "✨ {title} is a game-changer!\n{desc}\n🔗 {url}\n#GitHub #OpenSource #Productivity",
        "💡 Tool of the day: {title}\n{desc}\n→ {url}\n#DevTools #Programming #AI",
        "🚀 Must-have resource: {title}\n{desc}\nLink 👇\n{url}\n#Resources #TechTools",
    ],
}

# ── 话题标签映射（根据来源自动打标签）───────────────────────
SOURCE_HASHTAGS = {
    "github_trending":        ["#GitHub", "#OpenSource", "#Dev"],
    "product_hunt":           ["#ProductHunt", "#Startup", "#AITools"],
    "hacker_news":            ["#HackerNews", "#Tech", "#Programming"],
    "toolify_ai":             ["#AITools", "#人工智能", "#效率"],
    "free_programming_books": ["#免费电子书", "#编程学习", "#FreeBooks"],
    "default":                ["#开源", "#资源分享", "#干货"],
}


def _call_ai(prompt: str) -> str:
    """调用 AI API，返回生成的文本。"""
    base_url = AI_BASE_URL or "https://api.openai.com/v1"
    headers  = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type":  "application/json",
    }

    # 智谱 GLM 用不同的接口结构
    if AI_PROVIDER == "zhipu":
        base_url = "https://open.bigmodel.cn/api/paas/v4"

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": AI_MODEL,
                "messages": [
                    {
                        "role":    "system",
                        "content": (
                            "你是一位专业的 Twitter 资源分享博主，"
                            "擅长用简洁吸引人的语言介绍开源工具、电子书、AI工具等资源，"
                            "推文风格活泼、有吸引力，善用 emoji，字数控制在 200 字以内。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens":  300,
                "temperature": 0.8,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        return content
    except Exception as e:
        logger.error(f"[AI] 生成推文失败: {e}")
        return ""


def _get_hashtags(resource: dict) -> str:
    source = resource.get("source", "default")
    # 匹配来源前缀
    for key in SOURCE_HASHTAGS:
        if key in source:
            tags = SOURCE_HASHTAGS[key]
            break
    else:
        tags = SOURCE_HASHTAGS["default"]
    return " ".join(tags[:4])


def _build_prompt(resource: dict) -> str:
    title = resource.get("title", "")
    url   = resource.get("url",   "")
    desc  = resource.get("desc",  "")[:200]
    lang  = "中文" if TWEET_LANGUAGE in ("zh", "both") else "English"

    return (
        f"请为以下开源资源写一条 Twitter 推文（用{lang}，控制在180字内，含emoji，"
        f"结尾附上话题标签）：\n\n"
        f"资源名称：{title}\n"
        f"资源链接：{url}\n"
        f"资源简介：{desc}\n\n"
        f"要求：\n"
        f"- 开头要吸引人，突出资源价值\n"
        f"- 简洁说明用途\n"
        f"- 链接单独一行\n"
        f"- 结尾加 2-4 个相关话题标签\n"
        f"- 总字符数不超过 250（Twitter 限制280）"
    )


def generate_tweet(resource: dict) -> str:
    """
    为一条资源生成推文文本。
    优先调用 AI；如 AI 未配置或失败，降级为模板生成。
    """
    title = resource.get("title", "未命名资源")
    url   = resource.get("url",   "")
    desc  = (resource.get("desc") or "")[:100]

    # 尝试 AI 生成
    if AI_API_KEY and AI_API_KEY != "YOUR_AI_API_KEY":
        prompt = _build_prompt(resource)
        tweet  = _call_ai(prompt)
        if tweet:
            # 确保链接存在
            if url and url not in tweet:
                tweet += f"\n🔗 {url}"
            logger.info(f"[AI] 生成推文成功: {title[:30]}…")
            return tweet[:280]

    # 降级：模板生成
    lang     = TWEET_LANGUAGE if TWEET_LANGUAGE in STYLE_SAMPLES else "zh"
    import random
    template = random.choice(STYLE_SAMPLES[lang])
    hashtags = _get_hashtags(resource)
    tweet    = template.format(
        title = title,
        url   = url,
        desc  = desc,
    )
    if hashtags and hashtags not in tweet:
        tweet += f"\n{hashtags}"

    logger.info(f"[AI] 模板生成推文: {title[:30]}…")
    return tweet[:280]


def generate_tweets_batch(resources: list[dict]) -> list[dict]:
    """
    为资源列表批量生成推文，返回附加了 tweet_text 字段的列表。
    """
    result = []
    for r in resources:
        tweet_text = generate_tweet(r)
        result.append({**r, "tweet_text": tweet_text})
    logger.info(f"[AI] 批量生成推文 {len(result)} 条")
    return result
