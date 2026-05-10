"""
stranger_pool.py — 陌生地址池管理

从 Etherscan V2 API（Base 链）拉取近期活跃地址作为陌生地址池，
用于转账 30% 代币时随机抽取目标。

关键约束：
  - 陌生地址不能是 22 个机器人钱包之一
  - 不能是合约地址（避免转进合约丢失）
"""

import json
import random
import logging
import requests
from pathlib import Path
from datetime import date

from config import (
    ETHERSCAN_API_KEY, ETHERSCAN_V2_URL,
    STRANGER_ADDRESS_POOL, CHAIN_ID, DATA_DIR,
)

logger = logging.getLogger(__name__)

_POOL_FILE = Path(DATA_DIR) / "stranger_pool.json"


def _load_cache() -> dict:
    if _POOL_FILE.exists():
        try:
            with open(_POOL_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"date": "", "addresses": []}


def _save_cache(data: dict) -> None:
    _POOL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_POOL_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _fetch_recent_addresses(limit: int = 500) -> list[str]:
    """
    从 Etherscan V2 拉取 Base 链最新区块的所有交易地址。
    使用 proxy.eth_getBlockByNumber 获取真实区块交易。
    """
    addresses = set()

    # 先获取最新区块号
    try:
        resp = requests.get(ETHERSCAN_V2_URL, params={
            "chainid": CHAIN_ID,
            "module":  "proxy",
            "action":  "eth_blockNumber",
            "apikey":  ETHERSCAN_API_KEY,
        }, timeout=15)
        block_hex  = resp.json().get("result", "0x0")
        latest_blk = int(block_hex, 16)
    except Exception as e:
        logger.error(f"[Stranger] 获取最新区块失败: {e}")
        return []

    # 逐区块获取交易（最多拉 30 个区块以凑够 limit 个地址）
    for i in range(30):
        blk = latest_blk - i
        try:
            resp = requests.get(ETHERSCAN_V2_URL, params={
                "chainid": CHAIN_ID,
                "module":  "proxy",
                "action":  "eth_getBlockByNumber",
                "tag":     hex(blk),
                "boolean": "true",
                "apikey":  ETHERSCAN_API_KEY,
            }, timeout=15)
            block = resp.json().get("result") or {}
            txs   = block.get("transactions", []) or []
        except Exception as e:
            logger.debug(f"[Stranger] 获取区块 {blk} 失败: {e}")
            continue

        for tx in txs:
            from_addr = tx.get("from", "")
            to_addr   = tx.get("to", "")
            if from_addr:
                addresses.add(from_addr.lower())
            if to_addr:
                addresses.add(to_addr.lower())

        if len(addresses) >= limit:
            break

    return list(addresses)[:limit]


def build_stranger_pool(wallet_addresses: set[str], w3, limit: int = STRANGER_ADDRESS_POOL) -> list[str]:
    """
    构建陌生地址池：
      1. 拉取 Base 链最近交易地址
      2. 排除 22 个机器人钱包地址
      3. 排除合约地址（eth_getCode != 0x）
      4. 缓存到本地，每天刷新一次
    """
    cache = _load_cache()
    today = date.today().isoformat()

    if cache.get("date") == today and len(cache.get("addresses", [])) >= 50:
        logger.info(f"[Stranger] 使用今日缓存，池子大小: {len(cache['addresses'])}")
        return cache["addresses"]

    logger.info("[Stranger] 从 Etherscan V2 拉取陌生地址…")
    candidates = _fetch_recent_addresses(limit=limit * 2)

    # 排除机器人钱包
    own = {addr.lower() for addr in wallet_addresses}
    filtered = [a for a in candidates if a.lower() not in own]

    # 排除合约地址
    valid = []
    for addr in filtered[:limit * 2]:
        try:
            code = w3.eth.get_code(w3.to_checksum_address(addr))
            if len(code) == 0:   # EOA 地址（无代码）
                valid.append(addr)
            if len(valid) >= limit:
                break
        except Exception:
            continue

    if not valid:
        logger.error("[Stranger] 构建陌生地址池失败！")
        return []

    _save_cache({"date": today, "addresses": valid})
    logger.info(f"[Stranger] 陌生地址池构建完成，共 {len(valid)} 个")
    return valid


def random_stranger(pool: list[str], exclude: set[str] = None) -> str:
    """从池子中随机抽一个陌生地址，排除 exclude 集合。"""
    exclude = exclude or set()
    exclude_low = {e.lower() for e in exclude}
    candidates = [a for a in pool if a.lower() not in exclude_low]
    if not candidates:
        return ""
    return random.choice(candidates)
