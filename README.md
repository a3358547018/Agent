# 🦞 空投项目发掘助手

每天早上 **10:00** 自动抓取加密市场融资动态，通过 **Telegram Bot** 推送日报。

## 📋 推送内容

| 板块 | 数据来源 |
|------|---------|
| 📢 项目动态（日历事件） | RootData |
| 💰 新融资事件 | RootData + CryptoRank |
| 🆕 新收录项目 | RootData |
| 🚀 即将发币（7天内 TGE/IDO） | RootData + CryptoRank |
| ⚡ OKBoost / OKX 每日动态 | OKX 官方公告 RSS |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 `config.py`

打开 `config.py`，填入以下信息：

```python
ROOTDATA_API_KEY  = "你的 RootData API Key"
CRYPTORANK_API_KEY = "你的 CryptoRank API Key"
TG_BOT_TOKEN      = "你的 Telegram Bot Token"   # 从 @BotFather 获取
TG_CHAT_ID        = "你的 Chat ID"               # 用 @userinfobot 查询
```

> **如何获取 Telegram Bot Token？**
> 1. 在 Telegram 搜索 `@BotFather`
> 2. 发送 `/newbot`，按提示创建 Bot
> 3. 复制返回的 Token

> **如何获取 Chat ID？**
> 1. 在 Telegram 搜索 `@userinfobot`
> 2. 发送任意消息，它会返回你的 Chat ID

### 3. 立即测试推送

```bash
python main.py --now
```

### 4. 启动定时调度（后台运行）

```bash
# 前台运行
python main.py

# 后台运行（Linux/macOS）
nohup python main.py > logs/agent.log 2>&1 &

# 使用 screen（推荐）
screen -S airdrop-agent
python main.py
# Ctrl+A D 脱离 screen
```

---

## 📁 项目结构

```
Agent/
├── main.py          # 主入口，定时调度
├── config.py        # 配置文件（API Key、TG Token 等）
├── rootdata.py      # RootData 数据抓取模块
├── cryptorank.py    # CryptoRank 数据抓取模块
├── okboost.py       # OKX/OKBoost 动态抓取模块
├── notifier.py      # Telegram Bot 推送 + 消息格式化
├── requirements.txt # 依赖列表
└── README.md        # 本文件
```

---

## ⚙️ 自定义配置

在 `config.py` 中可调整：

```python
SCHEDULE_HOUR   = 10   # 推送小时（默认 10）
SCHEDULE_MINUTE = 0    # 推送分钟（默认 0，即 10:00）

MIN_RAISE_USD    = 0          # 最低融资金额过滤（0 = 不限制）
FOCUS_CATEGORIES = ["DeFi", "Layer2"]  # 关注赛道（空列表 = 全部）
```

---

## 🛡️ 注意事项

- **API Key 安全**：不要将 `config.py` 提交到公开仓库（已在 `.gitignore` 中排除）
- **API 限制**：RootData 和 CryptoRank 免费套餐有每日请求上限，请注意不要超额
- **时区**：定时任务使用服务器本地时区，部署到服务器时请确认时区设置

---

## 📡 部署到服务器（推荐）

推荐使用 **轻量云服务器**（如腾讯云/阿里云）持续运行：

```bash
# 设置时区（以上海为例）
timedatectl set-timezone Asia/Shanghai

# 安装依赖
pip3 install -r requirements.txt

# 使用 systemd 管理进程（生产推荐）
# 或直接用 screen/tmux 后台运行
screen -S airdrop-agent -dm python3 main.py
```
