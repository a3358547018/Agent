# 🤖 开源资源自动化 Agent

> 自动抓取热门开源资源 → 存迅雷云盘 → AI 生成推文 → 自动发推变现

## 🔄 工作流程

```
TG群 / GitHub Trending / Product Hunt / HackerNews / Toolify
        ↓ 抓取
      去重过滤
        ↓
    迅雷云盘存档
        ↓
    AI 自动写推文（DeepSeek / OpenAI / 智谱）
        ↓
    Twitter/X 自动发推（Playwright 模拟）
        ↓
      📈 流量 & 收益
```

---

## 📁 项目结构

```
ResourceAgent/
├── main.py            # 主入口，定时调度
├── crawler.py         # TG群 + 网站资源抓取
├── dedup.py           # 资源去重（本地 JSON 库）
├── thunder_drive.py   # 迅雷云盘存档（离线下载 + 文件上传）
├── ai_writer.py       # AI 生成推文（DeepSeek/OpenAI）
├── twitter_poster.py  # Playwright 自动发推
├── config.py          # ⚠️ 配置文件（不上传 GitHub）
├── requirements.txt   # 依赖列表
└── README.md
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 填写配置（`config.py`）

```python
# Telegram 抓取（从 https://my.telegram.org 获取）
TG_API_ID   = "你的 API ID"
TG_API_HASH = "你的 API Hash"
TG_PHONE    = "+8613800138000"

TG_SOURCE_GROUPS = [
    "https://t.me/你要监听的资源群",
]

# 迅雷云盘
THUNDER_USERNAME = "你的迅雷账号"
THUNDER_PASSWORD = "你的迅雷密码"

# AI 写推文（选一个）
AI_PROVIDER = "deepseek"            # 或 "openai" / "zhipu"
AI_API_KEY  = "你的 AI API Key"

# Twitter
TWITTER_USERNAME = "你的推特用户名"
TWITTER_PASSWORD = "你的推特密码"
TWITTER_EMAIL    = "你的推特注册邮箱"
```

### 3. 测试运行

```bash
# 立即执行完整流程（测试用）
python main.py --now

# 只测试抓取
python main.py --crawl

# 只测试发推（需要先有待发队列）
python main.py --tweet
```

### 4. 正式后台运行

```bash
# 使用 screen（推荐）
screen -S resource-agent
python main.py

# 或 nohup
nohup python main.py > logs/agent.log 2>&1 &
```

---

## ⚙️ 调度频率

| 任务 | 频率 |
|------|------|
| 抓取 + 存盘 | 每 **6 小时** 执行一次 |
| 自动发推 | 每 **30 分钟** 检查队列 |
| 每日最大发推 | **10 条**（可在 config.py 调整） |
| 发推时间段 | 早 **9:00** ~ 晚 **23:00** |

---

## 📡 抓取源说明

| 来源 | 内容 | 更新频率 |
|------|------|---------|
| TG 群组 | 你配置的资源群消息 | 实时监听 |
| GitHub Trending | 热门开源项目 | 每日更新 |
| Product Hunt | 新 AI 工具 / 产品 | 每日更新 |
| Hacker News | 技术资源 / 工具 | 实时更新 |
| Toolify AI | AI 工具目录 | 每日更新 |
| Free Programming Books | 免费编程电子书 | 按 commit 更新 |

---

## 🤖 AI 推文提供商

| 提供商 | `AI_PROVIDER` | `AI_BASE_URL` | 推荐模型 |
|--------|---------------|---------------|---------|
| DeepSeek | `deepseek` | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `openai` | 留空 | `gpt-4o-mini` |
| 智谱 GLM | `zhipu` | 自动设置 | `glm-4-flash` |

---

## ⚠️ 注意事项

1. **Twitter 发推**：使用 Playwright 模拟浏览器，有一定封号风险。建议：
   - 每日不超过 10 条
   - 使用新账号测试，稳定后再用主账号
   - 确保发推内容有价值，避免纯营销

2. **迅雷云盘**：接口基于移动端抓包，如登录失败请检查账号密码是否正确

3. **TG 监听**：需要真实手机号，首次运行会发短信验证码

4. **API Key 安全**：`config.py` 已加入 `.gitignore`，不会上传 GitHub
