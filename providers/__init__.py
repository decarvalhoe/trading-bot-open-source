"""External market data providers and sandbox configuration helpers."""
from __future__ import annotations

from .binance import (
    BinanceClient,
    BinanceConfig,
    BinanceError,
    normalize_symbol as normalize_binance_symbol,
)
from .fmp import FinancialModelingPrepClient, FinancialModelingPrepError
from .ibkr import (
    IBKRClient,
    IBKRConfig,
    IBKRError,
    normalize_symbol as normalize_ibkr_symbol,
)
from .limits import (
    PairLimit,
    build_orderbook,
    build_plan,
    build_quote,
    get_pair_limit,
    iter_supported_pairs,
    universe,
)

__all__ = [
    "BinanceClient",
    "BinanceConfig",
    "BinanceError",
    "FinancialModelingPrepClient",
    "FinancialModelingPrepError",
    "IBKRClient",
    "IBKRConfig",
    "IBKRError",
    "PairLimit",
    "build_orderbook",
    "build_plan",
    "build_quote",
    "get_pair_limit",
    "iter_supported_pairs",
    "normalize_binance_symbol",
    "normalize_ibkr_symbol",
    "universe",
]
