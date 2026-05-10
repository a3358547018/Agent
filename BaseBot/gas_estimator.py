"""
gas_estimator.py — Gas 价格估算与成本守护

策略：
  1. 优先用 OKX Explorer API 估算
  2. 失败降级到 RPC eth_gasPrice
  3. 最终兜底使用 config.GAS_PRICE_DEFAULT_GWEI
  4. 计算 gas 美元成本，超过 MAX_GAS_COST_USD 返回 None（跳过交易）
"""

import logging
import requests
import time

from config import (
    OKX_API_URL, GAS_PRICE_DEFAULT_GWEI, GAS_LIMIT_MAX,
    MAX_GAS_COST_USD, ETH_PRICE_API,
)

logger = logging.getLogger(__name__)

_eth_price_cache = {"ts": 0, "usd": 0.0}


def get_eth_price_usd() -> float:
    """获取 ETH 当前美元价（带 5 分钟缓存）。"""
    now = time.time()
    if now - _eth_price_cache["ts"] < 300 and _eth_price_cache["usd"] > 0:
        return _eth_price_cache["usd"]

    try:
        resp  = requests.get(ETH_PRICE_API, timeout=10)
        price = resp.json().get("ethereum", {}).get("usd", 0)
        if price > 0:
            _eth_price_cache.update({"ts": now, "usd": price})
            return price
    except Exception as e:
        logger.debug(f"[Gas] ETH 价格获取失败: {e}")

    return _eth_price_cache["usd"] or 3000.0   # 兜底 $3000


def estimate_gas_price_gwei(w3) -> float:
    """
    估算当前 Base 链 gas price（gwei）。
    顺序：OKX → RPC → 默认值
    """
    # 1. OKX
    try:
        resp = requests.get(OKX_API_URL, params={"chainId": 8453}, timeout=8)
        data = resp.json().get("data", [{}])[0]
        standard = data.get("standard") or data.get("propose", {}).get("proposeGasPrice")
        if standard:
            return float(standard) / 1e9 if int(standard) > 1e6 else float(standard)
    except Exception as e:
        logger.debug(f"[Gas] OKX 估算失败: {e}")

    # 2. RPC
    try:
        wei = w3.eth.gas_price
        return float(w3.from_wei(wei, "gwei"))
    except Exception as e:
        logger.debug(f"[Gas] RPC eth_gasPrice 失败: {e}")

    # 3. 默认
    return GAS_PRICE_DEFAULT_GWEI


def calc_gas_cost_usd(gas_price_gwei: float, gas_limit: int) -> float:
    """计算 gas 成本（美元）。"""
    gas_eth = gas_price_gwei * gas_limit / 1e9
    return gas_eth * get_eth_price_usd()


def build_gas_params(w3, estimated_gas: int = None) -> dict | None:
    """
    构建交易的 gas 参数字典，供 build_transaction 使用。
    如果 gas 成本超过阈值，返回 None（调用方应跳过该笔交易）。
    """
    gas_price_gwei = estimate_gas_price_gwei(w3)
    # 题目要求：gas price 用 OKX 估算或 0.1 gwei（取较低者以保成本）
    gas_price_gwei = min(gas_price_gwei, max(GAS_PRICE_DEFAULT_GWEI, 0.1))

    gas_limit = min(estimated_gas or GAS_LIMIT_MAX, GAS_LIMIT_MAX)
    cost_usd  = calc_gas_cost_usd(gas_price_gwei, gas_limit)

    if cost_usd > MAX_GAS_COST_USD:
        logger.warning(f"[Gas] 成本 ${cost_usd:.4f} 超过上限 ${MAX_GAS_COST_USD}，跳过")
        return None

    return {
        "gas":       gas_limit,
        "gasPrice":  w3.to_wei(gas_price_gwei, "gwei"),
    }
