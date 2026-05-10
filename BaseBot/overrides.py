"""
overrides.py — 运行时参数覆盖层

TG Bot 面板修改参数（交易笔数/金额/gas/转账比例等），
实时写入 data/overrides.json。其他模块（scheduler/executor/gas_estimator）
通过 get_param 动态读取，无需重启进程即可生效。

使用：
    from overrides import get_param
    min_tx = get_param("MIN_TX_PER_WALLET_DAY")
"""

import json
import logging
from pathlib import Path
from threading import Lock

import config

logger = logging.getLogger(__name__)

_OVERRIDE_FILE = Path("data/overrides.json")
_LOCK = Lock()


# 可被覆盖的参数白名单
ALLOWED_KEYS = {
    "MIN_TX_PER_WALLET_DAY",
    "MAX_TX_PER_WALLET_DAY",
    "TX_AMOUNT_MIN_ETH",
    "TX_AMOUNT_MAX_ETH",
    "TRANSFER_PCT",
    "GAS_PRICE_DEFAULT_GWEI",
    "GAS_LIMIT_MAX",
    "MAX_GAS_COST_USD",
    "TOKEN_FETCH_COUNT",
}


def _load_all() -> dict:
    if _OVERRIDE_FILE.exists():
        try:
            with open(_OVERRIDE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_all(data: dict) -> None:
    _OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_OVERRIDE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_param(key: str):
    """返回参数值（优先覆盖层，fallback config.py）。"""
    if key not in ALLOWED_KEYS:
        return getattr(config, key, None)
    with _LOCK:
        data = _load_all()
    if key in data:
        return data[key]
    return getattr(config, key, None)


def get_all_params() -> dict:
    return {k: get_param(k) for k in sorted(ALLOWED_KEYS)}


def set_param(key: str, value) -> bool:
    if key not in ALLOWED_KEYS:
        logger.warning(f"[Override] 不允许修改 {key}")
        return False
    with _LOCK:
        data = _load_all()
        data[key] = value
        _save_all(data)
    logger.info(f"[Override] {key} → {value}")
    return True


def reset_param(key: str) -> bool:
    with _LOCK:
        data = _load_all()
        if key in data:
            del data[key]
            _save_all(data)
            logger.info(f"[Override] 重置 {key}")
            return True
    return False


def reset_all() -> None:
    with _LOCK:
        _save_all({})
    logger.info("[Override] 重置全部参数")
