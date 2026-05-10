# 🦾 Base 链交易机器人

22 钱包 × 随机时间 × 自动交易 / 转账 / V3 手续费领取，附带 Telegram 控制面板。

---

## ⚠️ 风险提示

- 这是一个**真金白银**的链上自动化机器人，请**务必先在 Base Sepolia 测试网**跑通
- 钱包**私钥**是最高机密，绝对不能泄漏（已 `.gitignore` 保护）
- 建议初期每个钱包只放 **0.01~0.02 ETH**（gas + 小额交易足够）
- Base 链 gas 很便宜，但高频交易仍有被前端运行（MEV）的风险
- **本代码仅供研究学习，因使用造成的任何资产损失由使用者自行承担**

---

## 🎯 功能清单

### 💹 交易
- ✅ 22 个钱包，每个钱包每天 **3~10 笔** 交易
- ✅ 每笔交易时间**独立随机**，同一天内 66~220 笔交易**互不重叠**
- ✅ 金额 0.000001~0.000003 ETH 随机
- ✅ 60 种代币 **Fisher-Yates 洗牌** 轮询分配
- ✅ Uniswap V3 直接 Swap（三档手续费 500/3000/10000 自动尝试）
- ✅ Gas 上限 1M，价格 OKX 估算 / 0.1 gwei，单笔成本 > $0.01 自动跳过
- ✅ 交易失败的代币**当日自动拉黑**

### 📤 转账（30% 陌生地址）
- ✅ 每日每钱包随机时间抽代币**转 30%** 到陌生地址
- ✅ 陌生地址从 **Etherscan V2 API（Base 链）**抓取
- ✅ 自动排除自家 22 个钱包、合约地址
- ✅ 仅转 ERC20 代币，**绝不转 ETH**

### 💰 DeFi 收益
- ✅ 每日随机时间领取 Uniswap V3 Position 手续费
- ✅ 自动遍历钱包名下所有 NFT Position

### 🤖 Telegram 控制面板
- ✅ 按钮式交互（非命令行）
- ✅ 启停运行、重新生成时间表
- ✅ 今日统计、钱包余额、时间表预览
- ✅ 陌生地址池查看、系统状态
- ✅ 管理员白名单（防止他人控制）

---

## 📁 项目结构

```
BaseBot/
├── main.py              # 启动入口
├── executor.py          # 交易执行主循环 + 状态机
├── scheduler.py         # 每日时间表生成器（Fisher-Yates 互不重叠）
├── swap_engine.py       # Uniswap V3 Swap / Transfer / Claim
├── wallet_manager.py    # 22 钱包加载 + AES 加密存储
├── token_pool.py        # 代币池（DexScreener TOP60）+ 洗牌分配
├── stranger_pool.py     # 陌生地址池（Etherscan V2）
├── gas_estimator.py     # Gas 价格估算 + 成本守护
├── rpc_client.py        # Web3 RPC 多节点自动切换
├── ledger.py            # 交易账本（JSON 持久化）
├── tg_bot.py            # Telegram 控制面板
├── abi.py               # ERC20 / Uniswap V3 合约 ABI
├── config.py            # ⚠️ 本地配置（不上传 GitHub）
├── requirements.txt
└── data/                # 运行时数据（不上传）
    ├── wallets.enc        # 加密钱包
    ├── ledger.json        # 交易账本
    ├── schedule.json      # 今日时间表
    ├── stranger_pool.json # 陌生地址池缓存
    └── state.json         # 运行状态
```

---

## 🚀 使用流程

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 填写配置（`config.py`）

打开 `config.py`，填入：

```python
# 22 个钱包私钥（明文，不推荐）
WALLET_PRIVATE_KEYS = [
    "0x私钥1", "0x私钥2", ..., "0x私钥22",
]

# Telegram
TG_BOT_TOKEN      = "你的 Bot Token"   # 从 @BotFather 获取
TG_ADMIN_CHAT_IDS = [123456789]          # 你的 Chat ID（从 @userinfobot 查询）
```

### 3. （推荐）加密钱包私钥

出于安全考虑，强烈建议用加密模式：

```bash
python main.py --encrypt
# 按提示输入口令和 22 个私钥
```

然后在 `config.py` 中：
```python
WALLET_PRIVATE_KEYS          = []             # 清空
WALLET_ENCRYPTION_PASSPHRASE = "你的口令"     # 启动时读取
```

### 4. 预览今日时间表（可选）

```bash
python main.py --schedule
# 输出 220+ 个事件的时间表
```

### 5. 启动机器人

```bash
# 完整模式（交易执行 + TG 面板）
python main.py

# 只启动执行器（无 TG）
python main.py --exec-only

# 后台运行（推荐 screen/tmux）
screen -S base-bot
python main.py
# Ctrl+A D 脱离
```

### 6. Telegram 操作

在 Telegram 向你的 Bot 发送 `/start`，即可看到按钮面板：

```
┌─────────────────────────────────┐
│ ⏸ 暂停运行  │ 🔄 重新生成时间表 │
│ 📊 今日统计 │ 📝 时间表预览     │
│ 💰 钱包余额 │ 🔑 陌生地址池     │
│ ℹ️ 系统状态 │ 🔁 刷新菜单       │
└─────────────────────────────────┘
```

---

## ⚙️ 关键参数说明

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `WALLETS_COUNT` | 22 | 钱包数量 |
| `MIN/MAX_TX_PER_WALLET_DAY` | 3 / 10 | 每钱包每日交易数 |
| `TX_AMOUNT_MIN/MAX_ETH` | 0.000001~0.000003 | 单笔金额 |
| `TRANSFER_PCT` | 0.30 | 转账比例 |
| `GAS_LIMIT_MAX` | 1,000,000 | Gas 上限 |
| `GAS_PRICE_DEFAULT_GWEI` | 0.1 | Gas price 上限 |
| `MAX_GAS_COST_USD` | 0.01 | 单笔 gas 美元成本上限 |
| `TOKEN_FETCH_COUNT` | 60 | 代币池大小 |
| `MIN_GAP_SECONDS` | 20 | 两笔交易最小间隔（防撞） |

---

## 🔐 安全建议

1. **钱包资金分离**：每个钱包只放够用的 ETH（0.01~0.02）
2. **私钥加密**：使用 `--encrypt` 模式，避免明文泄漏
3. **TG 白名单**：必须配置 `TG_ADMIN_CHAT_IDS`，否则任何人都能控制你的钱包
4. **定期备份** `data/ledger.json`（交易记录）
5. **监控余额**：通过 TG 面板「💰 钱包余额」按钮定期查看
6. **测试网先行**：主网上线前先在 Base Sepolia 跑 24 小时

---

## 📊 防检测设计

- ✅ **金额随机**：每笔不同
- ✅ **时间随机**：单日 86400 秒内均匀分布，间隔至少 20s
- ✅ **代币随机**：Fisher-Yates 洗牌 + 随机抽取
- ✅ **动作随机**：50/50 买 or 卖
- ✅ **钱包独立**：22 个钱包之间**完全无关联**（不互转）
- ✅ **陌生地址独立**：每次转账都从 500 个陌生地址随机选
- ✅ **Position 手续费**：领取时间点也是当天随机

---

## ❓ 常见问题

**Q: 如何停止机器人？**
A: TG 面板点「⏸ 暂停运行」仅暂停执行，进程仍在运行。若要完全停止，按 `Ctrl+C` 或 `kill <pid>`。

**Q: 交易都失败怎么办？**
A: 查 `logs/base_bot.log`，常见原因：① RPC 挂了（自动切换备用）② gas 不够 ③ 钱包 ETH 余额不足

**Q: 能换成其他链吗？**
A: 可以。改 `config.py` 的 `BASE_RPC_URL`、`CHAIN_ID`、Uniswap V3 地址即可。

**Q: 为什么用 0.1 gwei？**
A: Base 基础 gas 约 0.001 gwei，0.1 gwei 已是高优先级，再高纯属浪费。
