"""
abi.py — 精简 ABI 定义

只保留本项目用到的合约方法，减小体积。
"""

ERC20_ABI = [
    {"constant": True,  "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf",
     "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": True,  "inputs": [], "name": "decimals",
     "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True,  "inputs": [], "name": "symbol",
     "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": False, "inputs": [
        {"name": "_to",    "type": "address"},
        {"name": "_value", "type": "uint256"}], "name": "transfer",
     "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": False, "inputs": [
        {"name": "_spender", "type": "address"},
        {"name": "_value",   "type": "uint256"}], "name": "approve",
     "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [
        {"name": "_owner",   "type": "address"},
        {"name": "_spender", "type": "address"}], "name": "allowance",
     "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
]

# Uniswap V3 SwapRouter02 — exactInputSingle
UNISWAP_V3_ROUTER_ABI = [
    {
        "inputs": [{
            "components": [
                {"name": "tokenIn",           "type": "address"},
                {"name": "tokenOut",          "type": "address"},
                {"name": "fee",               "type": "uint24"},
                {"name": "recipient",         "type": "address"},
                {"name": "amountIn",          "type": "uint256"},
                {"name": "amountOutMinimum",  "type": "uint256"},
                {"name": "sqrtPriceLimitX96", "type": "uint160"}
            ],
            "name": "params",
            "type": "tuple"
        }],
        "name":    "exactInputSingle",
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function",
    },
    {"inputs": [], "name": "WETH9", "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
    # refundETH 用于多余 ETH 退回
    {"inputs": [], "name": "refundETH", "outputs": [],
     "stateMutability": "payable", "type": "function"},
]

# Uniswap V3 Quoter — quoteExactInputSingle
UNISWAP_V3_QUOTER_ABI = [
    {
        "inputs": [
            {"name": "tokenIn",           "type": "address"},
            {"name": "tokenOut",          "type": "address"},
            {"name": "amountIn",          "type": "uint256"},
            {"name": "fee",               "type": "uint24"},
            {"name": "sqrtPriceLimitX96", "type": "uint160"}
        ],
        "name":    "quoteExactInputSingle",
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# Uniswap V3 NonfungiblePositionManager — 手续费领取
V3_POSITION_MANAGER_ABI = [
    {
        "inputs": [{"name": "owner", "type": "address"}],
        "name":   "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view", "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "index", "type": "uint256"},
        ],
        "name":   "tokenOfOwnerByIndex",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view", "type": "function",
    },
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name":   "positions",
        "outputs": [
            {"name": "nonce",                     "type": "uint96"},
            {"name": "operator",                  "type": "address"},
            {"name": "token0",                    "type": "address"},
            {"name": "token1",                    "type": "address"},
            {"name": "fee",                       "type": "uint24"},
            {"name": "tickLower",                 "type": "int24"},
            {"name": "tickUpper",                 "type": "int24"},
            {"name": "liquidity",                 "type": "uint128"},
            {"name": "feeGrowthInside0LastX128",  "type": "uint256"},
            {"name": "feeGrowthInside1LastX128",  "type": "uint256"},
            {"name": "tokensOwed0",               "type": "uint128"},
            {"name": "tokensOwed1",               "type": "uint128"},
        ],
        "stateMutability": "view", "type": "function",
    },
    {
        "inputs": [{
            "components": [
                {"name": "tokenId",    "type": "uint256"},
                {"name": "recipient",  "type": "address"},
                {"name": "amount0Max", "type": "uint128"},
                {"name": "amount1Max", "type": "uint128"},
            ],
            "name": "params", "type": "tuple"
        }],
        "name":    "collect",
        "outputs": [
            {"name": "amount0", "type": "uint256"},
            {"name": "amount1", "type": "uint256"},
        ],
        "stateMutability": "payable",
        "type": "function",
    }
]
