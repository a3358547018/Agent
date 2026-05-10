"""
swap_engine.py — Uniswap V3 交易执行引擎

封装核心操作：
  1. ETH → Token（买入）
  2. Token → ETH（卖出）
  3. ERC20 Transfer（转账到陌生地址）
  4. V3 Position 手续费领取
"""

import logging
import time
from web3 import Web3

from config import (
    UNISWAP_V3_ROUTER, UNISWAP_V3_QUOTER, UNISWAP_V3_NFT_MANAGER,
    WETH_ADDRESS, V3_FEE_TIERS, CHAIN_ID,
)
from abi import (
    ERC20_ABI, UNISWAP_V3_ROUTER_ABI,
    UNISWAP_V3_QUOTER_ABI, V3_POSITION_MANAGER_ABI,
)
from gas_estimator import build_gas_params
from token_pool import ban_token

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
#  辅助函数
# ══════════════════════════════════════════════════════════════

def _get_nonce(w3: Web3, address: str) -> int:
    return w3.eth.get_transaction_count(w3.to_checksum_address(address), "pending")


def _sign_and_send(w3: Web3, tx: dict, private_key: str) -> str | None:
    """签名并发送交易，返回 tx_hash 或 None。"""
    try:
        signed  = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        return tx_hash.hex()
    except Exception as e:
        logger.error(f"[Swap] 签名/发送失败: {e}")
        return None


def _wait_receipt(w3: Web3, tx_hash: str, timeout: int = 120) -> bool:
    """等待交易上链确认，返回是否成功。"""
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        return receipt.status == 1
    except Exception as e:
        logger.error(f"[Swap] 等待回执失败 {tx_hash}: {e}")
        return False


def get_token_decimals(w3: Web3, token_address: str) -> int:
    try:
        c = w3.eth.contract(
            address=w3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )
        return c.functions.decimals().call()
    except Exception:
        return 18


def get_token_balance(w3: Web3, token_address: str, owner: str) -> int:
    try:
        c = w3.eth.contract(
            address=w3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )
        return c.functions.balanceOf(w3.to_checksum_address(owner)).call()
    except Exception as e:
        logger.debug(f"[Swap] balanceOf 失败: {e}")
        return 0


# ══════════════════════════════════════════════════════════════
#  Uniswap V3 — Quote (询价，不花钱)
# ══════════════════════════════════════════════════════════════

def quote_v3(w3: Web3, token_in: str, token_out: str, amount_in: int) -> tuple[int, int]:
    """
    尝试三个 fee tier，返回 (amount_out, fee)。失败返回 (0, 0)。
    """
    quoter = w3.eth.contract(
        address=w3.to_checksum_address(UNISWAP_V3_QUOTER),
        abi=UNISWAP_V3_QUOTER_ABI,
    )
    for fee in V3_FEE_TIERS:
        try:
            out = quoter.functions.quoteExactInputSingle(
                w3.to_checksum_address(token_in),
                w3.to_checksum_address(token_out),
                amount_in,
                fee,
                0,
            ).call()
            if out > 0:
                return out, fee
        except Exception:
            continue
    return 0, 0


# ══════════════════════════════════════════════════════════════
#  1. ETH → Token（买入）
# ══════════════════════════════════════════════════════════════

def swap_eth_to_token(
    w3:          Web3,
    private_key: str,
    from_addr:   str,
    token_out:   str,
    amount_eth:  float,
    slippage:    float = 0.05,
) -> tuple[str | None, int]:
    """
    买入代币。返回 (tx_hash, amount_out_raw) 或 (None, 0)。
    失败时会对 token 调用 ban_token（若是流动性问题）。
    """
    amount_in_wei = w3.to_wei(amount_eth, "ether")

    # 1. 询价
    out_raw, fee = quote_v3(w3, WETH_ADDRESS, token_out, amount_in_wei)
    if out_raw == 0:
        logger.warning(f"[Buy] 询价失败（无流动性）: {token_out}")
        ban_token(token_out)
        return None, 0

    min_out = int(out_raw * (1 - slippage))

    # 2. 构建交易
    router = w3.eth.contract(
        address=w3.to_checksum_address(UNISWAP_V3_ROUTER),
        abi=UNISWAP_V3_ROUTER_ABI,
    )
    params = (
        w3.to_checksum_address(WETH_ADDRESS),
        w3.to_checksum_address(token_out),
        fee,
        w3.to_checksum_address(from_addr),
        amount_in_wei,
        min_out,
        0,
    )

    # Gas 参数
    gas_cfg = build_gas_params(w3, estimated_gas=300_000)
    if gas_cfg is None:
        return None, 0

    tx = router.functions.exactInputSingle(params).build_transaction({
        "from":    w3.to_checksum_address(from_addr),
        "value":   amount_in_wei,
        "nonce":   _get_nonce(w3, from_addr),
        "chainId": CHAIN_ID,
        **gas_cfg,
    })

    tx_hash = _sign_and_send(w3, tx, private_key)
    if not tx_hash:
        return None, 0

    if _wait_receipt(w3, tx_hash):
        logger.info(f"[Buy] ✅ {from_addr[:10]}… {amount_eth} ETH → {token_out[:10]}… | {tx_hash}")
        return tx_hash, out_raw
    else:
        logger.warning(f"[Buy] ❌ 交易失败 {tx_hash}")
        ban_token(token_out)
        return None, 0


# ══════════════════════════════════════════════════════════════
#  2. Token → ETH（卖出）
# ══════════════════════════════════════════════════════════════

def _ensure_allowance(
    w3:           Web3,
    private_key:  str,
    from_addr:    str,
    token:        str,
    spender:      str,
    amount:       int,
) -> bool:
    """如果 allowance 不足，发送 approve 交易。"""
    erc20 = w3.eth.contract(
        address=w3.to_checksum_address(token),
        abi=ERC20_ABI,
    )
    current = erc20.functions.allowance(
        w3.to_checksum_address(from_addr),
        w3.to_checksum_address(spender),
    ).call()
    if current >= amount:
        return True

    gas_cfg = build_gas_params(w3, estimated_gas=80_000)
    if gas_cfg is None:
        return False

    max_uint = 2**256 - 1
    tx = erc20.functions.approve(
        w3.to_checksum_address(spender), max_uint,
    ).build_transaction({
        "from":    w3.to_checksum_address(from_addr),
        "nonce":   _get_nonce(w3, from_addr),
        "chainId": CHAIN_ID,
        **gas_cfg,
    })
    tx_hash = _sign_and_send(w3, tx, private_key)
    if tx_hash and _wait_receipt(w3, tx_hash, timeout=90):
        logger.info(f"[Approve] ✅ {token[:10]}… | {tx_hash}")
        return True
    return False


def swap_token_to_eth(
    w3:            Web3,
    private_key:   str,
    from_addr:     str,
    token_in:      str,
    amount_in_raw: int,
    slippage:      float = 0.05,
) -> tuple[str | None, int]:
    """卖出代币。返回 (tx_hash, eth_out_wei) 或 (None, 0)。"""
    # 1. 询价
    out_wei, fee = quote_v3(w3, token_in, WETH_ADDRESS, amount_in_raw)
    if out_wei == 0:
        logger.warning(f"[Sell] 询价失败: {token_in}")
        return None, 0

    min_out = int(out_wei * (1 - slippage))

    # 2. 授权
    if not _ensure_allowance(w3, private_key, from_addr, token_in, UNISWAP_V3_ROUTER, amount_in_raw):
        logger.warning(f"[Sell] 授权失败: {token_in}")
        return None, 0

    # 3. 构建 swap
    router = w3.eth.contract(
        address=w3.to_checksum_address(UNISWAP_V3_ROUTER),
        abi=UNISWAP_V3_ROUTER_ABI,
    )
    params = (
        w3.to_checksum_address(token_in),
        w3.to_checksum_address(WETH_ADDRESS),
        fee,
        w3.to_checksum_address(from_addr),
        amount_in_raw,
        min_out,
        0,
    )

    gas_cfg = build_gas_params(w3, estimated_gas=300_000)
    if gas_cfg is None:
        return None, 0

    tx = router.functions.exactInputSingle(params).build_transaction({
        "from":    w3.to_checksum_address(from_addr),
        "nonce":   _get_nonce(w3, from_addr),
        "chainId": CHAIN_ID,
        **gas_cfg,
    })

    tx_hash = _sign_and_send(w3, tx, private_key)
    if not tx_hash:
        return None, 0

    if _wait_receipt(w3, tx_hash):
        logger.info(f"[Sell] ✅ {from_addr[:10]}… {token_in[:10]}… → ETH | {tx_hash}")
        return tx_hash, out_wei
    else:
        logger.warning(f"[Sell] ❌ 交易失败 {tx_hash}")
        return None, 0


# ══════════════════════════════════════════════════════════════
#  3. ERC20 Transfer（转账到陌生地址）
# ══════════════════════════════════════════════════════════════

def transfer_token(
    w3:           Web3,
    private_key:  str,
    from_addr:    str,
    token:        str,
    to_address:   str,
    amount_raw:   int,
) -> str | None:
    """ERC20 transfer。返回 tx_hash 或 None。"""
    erc20 = w3.eth.contract(
        address=w3.to_checksum_address(token),
        abi=ERC20_ABI,
    )

    gas_cfg = build_gas_params(w3, estimated_gas=80_000)
    if gas_cfg is None:
        return None

    tx = erc20.functions.transfer(
        w3.to_checksum_address(to_address), amount_raw,
    ).build_transaction({
        "from":    w3.to_checksum_address(from_addr),
        "nonce":   _get_nonce(w3, from_addr),
        "chainId": CHAIN_ID,
        **gas_cfg,
    })

    tx_hash = _sign_and_send(w3, tx, private_key)
    if tx_hash and _wait_receipt(w3, tx_hash, timeout=90):
        logger.info(f"[Transfer] ✅ {token[:10]}… → {to_address[:10]}… | {tx_hash}")
        return tx_hash
    return None


# ══════════════════════════════════════════════════════════════
#  4. Uniswap V3 手续费领取
# ══════════════════════════════════════════════════════════════

def collect_all_v3_fees(
    w3:          Web3,
    private_key: str,
    from_addr:   str,
) -> tuple[int, int]:
    """
    领取 from_addr 名下所有 V3 position 的累积手续费。
    返回 (成功数, 失败数)。
    """
    nft = w3.eth.contract(
        address=w3.to_checksum_address(UNISWAP_V3_NFT_MANAGER),
        abi=V3_POSITION_MANAGER_ABI,
    )

    try:
        count = nft.functions.balanceOf(w3.to_checksum_address(from_addr)).call()
    except Exception as e:
        logger.debug(f"[Claim] 查询 position 数量失败: {e}")
        return 0, 0

    if count == 0:
        return 0, 0

    ok = fail = 0
    max_uint128 = (2**128) - 1

    for i in range(count):
        try:
            token_id = nft.functions.tokenOfOwnerByIndex(
                w3.to_checksum_address(from_addr), i,
            ).call()

            pos = nft.functions.positions(token_id).call()
            owed0, owed1 = pos[10], pos[11]
            if owed0 == 0 and owed1 == 0:
                continue   # 没有待领手续费，跳过

            gas_cfg = build_gas_params(w3, estimated_gas=250_000)
            if gas_cfg is None:
                fail += 1
                continue

            params = (
                token_id,
                w3.to_checksum_address(from_addr),
                max_uint128,
                max_uint128,
            )
            tx = nft.functions.collect(params).build_transaction({
                "from":    w3.to_checksum_address(from_addr),
                "nonce":   _get_nonce(w3, from_addr),
                "chainId": CHAIN_ID,
                **gas_cfg,
            })

            tx_hash = _sign_and_send(w3, tx, private_key)
            if tx_hash and _wait_receipt(w3, tx_hash, timeout=120):
                logger.info(f"[Claim] ✅ position #{token_id} | {tx_hash}")
                ok += 1
            else:
                fail += 1

            time.sleep(3)   # position 之间稍等
        except Exception as e:
            logger.error(f"[Claim] position #{i} 领取异常: {e}")
            fail += 1

    return ok, fail
