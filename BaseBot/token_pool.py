"""
token_pool.py — 代币池管理

功能：
  1. 从 DexScreener 拉取 Base 链流动性 TOP 60 代币
  2. Fisher-Yates 洗牌
  3. 轮询分配给 22 个钱包
  4. 记录 banned tokens（gas 过高或流动性不足的代币）
"""

import json
import random
import logging
import requests
from pathlib import Path
from datetime import datetime, date

from config import (
    TOKEN_LIST_SOURCE, TOKEN_FETCH_COUNT,
    BANNED_TOKENS_FILE, WETH_ADDRESS,
)

logger = logging.getLogger(__name__)

# 静态 fallback 代币列表（Base 链知名代币，API 挂了用这个）
STATIC_TOKENS = [
    {"symbol": "USDC",   "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6},
    {"symbol": "cbETH",  "address": "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22", "decimals": 18},
    {"symbol": "DAI",    "address": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb", "decimals": 18},
    {"symbol": "AERO",   "address": "0x940181a94A35A4569E4529A3CDfB74e38FD98631", "decimals": 18},
    {"symbol": "USDbC",  "address": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA", "decimals": 6},
    {"symbol": "rETH",   "address": "0xB6fe221Fe9EeF5aBa221c348bA20A1Bf5e73624c", "decimals": 18},
    {"symbol": "DEGEN",  "address": "0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed", "decimals": 18},
    {"symbol": "TOSHI",  "address": "0xAC1Bd2486aAf3B5C0fc3Fd868558b082a531B2B4", "decimals": 18},
    {"symbol": "BRETT",  "address": "0x532f27101965dd16442E59d40670FaF5eBB142E4", "decimals": 18},
    {"symbol": "WELL",   "address": "0xA88594D404727625A9437C3f886C7643872296AE", "decimals": 18},
]


def _load_banned() -> set[str]:
    """加载被禁用（gas 过高 / 流动性不足）的代币地址列表。"""
    p = Path(BANNED_TOKENS_FILE)
    if not p.exists():
        return set()
    try:
        with open(p) as f:
            data = json.load(f)
        # 只保留当天的 ban（第二天自动解禁）
        today = date.today().isoformat()
        return {addr for addr, d in data.items() if d == today}
    except Exception:
        return set()


def ban_token(address: str) -> None:
    """将某代币加入今日禁用列表。"""
    p = Path(BANNED_TOKENS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if p.exists():
        try:
            with open(p) as f:
                data = json.load(f)
        except Exception:
            pass
    data[address.lower()] = date.today().isoformat()
    with open(p, "w") as f:
        json.dump(data, f, indent=2)
    logger.warning(f"[Token] 禁用代币 {address[:10]}… 当日不再交易")


def fetch_top_tokens(limit: int = TOKEN_FETCH_COUNT) -> list[dict]:
    """
    从 DexScreener 拉取 Base 链流动性最高的 limit 个代币。
    返回 [{"symbol", "address", "decimals"}] 列表。
    """
    if TOKEN_LIST_SOURCE == "static":
        return STATIC_TOKENS[:limit]

    try:
        # DexScreener 按链 + 流动性查询
        resp = requests.get(
            "https://api.dexscreener.com/latest/dex/pairs/base",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        pairs = resp.json().get("pairs", [])
    except Exception as e:
        logger.error(f"[Token] DexScreener 拉取失败: {e}，使用静态列表")
        return STATIC_TOKENS[:limit]

    # 按 liquidity.usd 降序排序，去重（同一代币可能出现在多个池子）
    seen     = set()
    tokens   = []
    weth_low = WETH_ADDRESS.lower()

    for p in sorted(pairs, key=lambda x: x.get("liquidity", {}).get("usd", 0) or 0, reverse=True):
        base_token = p.get("baseToken", {})
        addr = base_token.get("address", "").lower()
        if not addr or addr in seen or addr == weth_low:
            continue
        seen.add(addr)
        tokens.append({
            "symbol":   base_token.get("symbol", "UNKNOWN"),
            "address":  base_token["address"],
            "decimals": 18,    # DexScreener 不直接返回 decimals，默认 18，后续调用合约校正
        })
        if len(tokens) >= limit:
            break

    # 排除被禁用的
    banned = _load_banned()
    tokens = [t for t in tokens if t["address"].lower() not in banned]

    if not tokens:
        logger.warning("[Token] DexScreener 返回为空，使用静态列表")
        return STATIC_TOKENS[:limit]

    logger.info(f"[Token] 从 DexScreener 拉取 {len(tokens)} 个代币")
    return tokens


def fisher_yates_shuffle(arr: list) -> list:
    """标准 Fisher-Yates 洗牌（in-place）。"""
    arr = arr.copy()
    for i in range(len(arr) - 1, 0, -1):
        j = random.randint(0, i)
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def allocate_tokens_to_wallets(tokens: list[dict], wallet_count: int) -> dict[int, list[dict]]:
    """
    用 Fisher-Yates 洗牌后轮询分配代币给钱包。
    返回 {wallet_index: [token_list]} 的映射。
    每个钱包可能分到 2-3 种代币。
    """
    shuffled = fisher_yates_shuffle(tokens)
    allocation = {i: [] for i in range(wallet_count)}
    for idx, tok in enumerate(shuffled):
        wallet_idx = idx % wallet_count
        allocation[wallet_idx].append(tok)
    return allocation
