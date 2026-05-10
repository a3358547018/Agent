"""
wallet_manager.py — 钱包加载、加密存储、余额查询

功能：
  1. 从 config 或 wallets.json 加载 22 个钱包私钥
  2. 支持 AES 加密存储（cryptography + PBKDF2 密钥派生）
  3. 余额查询、地址导出
"""

import json
import base64
import hashlib
import logging
from pathlib import Path
from eth_account import Account

from config import (
    WALLET_PRIVATE_KEYS, WALLET_ENCRYPTION_PASSPHRASE,
    WALLETS_COUNT, DATA_DIR,
)

logger = logging.getLogger(__name__)

_WALLETS_FILE = Path(DATA_DIR) / "wallets.enc"


# ── AES 加密工具（可选）───────────────────────────────────────
def _derive_key(passphrase: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode(), b"base-bot-salt", 200_000, 32)


def _encrypt(data: str, passphrase: str) -> str:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return data
    key  = base64.urlsafe_b64encode(_derive_key(passphrase))
    enc  = Fernet(key).encrypt(data.encode())
    return enc.decode()


def _decrypt(data: str, passphrase: str) -> str:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return data
    key = base64.urlsafe_b64encode(_derive_key(passphrase))
    return Fernet(key).decrypt(data.encode()).decode()


# ── 钱包加载 ────────────────────────────────────────────────
def load_wallets() -> list[dict]:
    """
    返回 [{"index": 0, "address": "0x...", "private_key": "0x..."}] 的列表。
    优先级：
      1. data/wallets.enc（加密存储）
      2. config.WALLET_PRIVATE_KEYS（明文）
    """
    keys: list[str] = []

    # 1. 优先读加密文件
    if _WALLETS_FILE.exists() and WALLET_ENCRYPTION_PASSPHRASE:
        try:
            with open(_WALLETS_FILE, "r") as f:
                enc = f.read()
            raw = _decrypt(enc, WALLET_ENCRYPTION_PASSPHRASE)
            keys = json.loads(raw)
            logger.info(f"[Wallet] 从加密文件加载 {len(keys)} 个钱包")
        except Exception as e:
            logger.error(f"[Wallet] 解密钱包文件失败: {e}")

    # 2. fallback 到明文配置
    if not keys:
        keys = [k for k in WALLET_PRIVATE_KEYS if k]
        if keys:
            logger.warning("[Wallet] 使用明文私钥，建议用 encrypt_wallets() 加密！")

    if not keys:
        logger.error("[Wallet] 未找到任何钱包私钥！请在 config.py 中填入 WALLET_PRIVATE_KEYS")
        return []

    if len(keys) < WALLETS_COUNT:
        logger.warning(f"[Wallet] 配置了 {len(keys)} 个钱包，少于要求的 {WALLETS_COUNT} 个")

    wallets = []
    for idx, pk in enumerate(keys[:WALLETS_COUNT]):
        pk = pk if pk.startswith("0x") else "0x" + pk
        try:
            acct = Account.from_key(pk)
            wallets.append({
                "index":       idx,
                "address":     acct.address,
                "private_key": pk,
            })
        except Exception as e:
            logger.error(f"[Wallet] 第 {idx} 个私钥格式错误: {e}")

    return wallets


def encrypt_wallets(private_keys: list[str], passphrase: str) -> None:
    """将明文私钥加密存储到 data/wallets.enc。"""
    enc = _encrypt(json.dumps(private_keys), passphrase)
    _WALLETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_WALLETS_FILE, "w") as f:
        f.write(enc)
    logger.info(f"[Wallet] 已加密存储 {len(private_keys)} 个钱包到 {_WALLETS_FILE}")


def get_eth_balance(w3, address: str) -> float:
    """查询某地址 ETH 余额（返回 ETH 单位）。"""
    try:
        wei = w3.eth.get_balance(address)
        return float(w3.from_wei(wei, "ether"))
    except Exception as e:
        logger.error(f"[Wallet] 查询余额失败 {address[:10]}: {e}")
        return 0.0
