"""
rpc_client.py — Web3 RPC 客户端（带自动故障切换）
"""

import logging
from web3 import Web3
from web3.middleware import geth_poa_middleware

from config import BASE_RPC_URL, BASE_RPC_BACKUPS, CHAIN_ID

logger = logging.getLogger(__name__)

_w3_cache = None


def _build_w3(url: str) -> Web3 | None:
    try:
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 15}))
        # Base 是 OP Stack，需要 POA 中间件
        try:
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except Exception:
            pass
        if w3.is_connected() and w3.eth.chain_id == CHAIN_ID:
            return w3
    except Exception as e:
        logger.debug(f"[RPC] 连接 {url} 失败: {e}")
    return None


def get_w3() -> Web3:
    """获取已连接的 Web3 实例；缓存单例，连不上时自动切换备用 RPC。"""
    global _w3_cache
    if _w3_cache and _w3_cache.is_connected():
        return _w3_cache

    for url in [BASE_RPC_URL, *BASE_RPC_BACKUPS]:
        w3 = _build_w3(url)
        if w3:
            logger.info(f"[RPC] 已连接 {url}")
            _w3_cache = w3
            return w3

    raise ConnectionError("所有 Base RPC 节点均不可用！请检查网络或更换 RPC。")


def reset_connection() -> None:
    """强制重连（主 RPC 挂了的时候调用）。"""
    global _w3_cache
    _w3_cache = None
