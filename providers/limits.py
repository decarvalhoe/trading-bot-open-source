"""Shared sandbox trading limits and helper factories."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable

from schemas.market import (
    ExecutionPlan,
    ExecutionVenue,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderRequest,
    Quote,
)

from .binance import normalize_symbol as normalize_binance_symbol
from .ibkr import normalize_symbol as normalize_ibkr_symbol


@dataclass(frozen=True)
class PairLimit:
    """Constraints and reference values for a trading pair."""

    symbol: str
    venue: ExecutionVenue
    max_position: float
    max_order_size: float
    quote_refresh_seconds: float
    orderbook_refresh_seconds: float
    reference_price: float
    tick_size: float
    depth_levels: int

    def notional_limit(self) -> float:
        return self.max_position * self.reference_price


_SANDBOX_LIMITS: Dict[ExecutionVenue, Dict[str, PairLimit]] = {
    ExecutionVenue.BINANCE_SPOT: {
        "BTCUSDT": PairLimit(
            symbol="BTCUSDT",
            venue=ExecutionVenue.BINANCE_SPOT,
            max_position=2.0,
            max_order_size=0.75,
            quote_refresh_seconds=1.0,
            orderbook_refresh_seconds=0.5,
            reference_price=30_000.0,
            tick_size=5.0,
            depth_levels=5,
        ),
        "ETHUSDT": PairLimit(
            symbol="ETHUSDT",
            venue=ExecutionVenue.BINANCE_SPOT,
            max_position=50.0,
            max_order_size=10.0,
            quote_refresh_seconds=1.0,
            orderbook_refresh_seconds=0.5,
            reference_price=2_000.0,
            tick_size=1.0,
            depth_levels=5,
        ),
    },
    ExecutionVenue.IBKR_PAPER: {
        "AAPL": PairLimit(
            symbol="AAPL",
            venue=ExecutionVenue.IBKR_PAPER,
            max_position=5_000.0,
            max_order_size=1_000.0,
            quote_refresh_seconds=2.0,
            orderbook_refresh_seconds=1.0,
            reference_price=180.0,
            tick_size=0.05,
            depth_levels=5,
        ),
        "MSFT": PairLimit(
            symbol="MSFT",
            venue=ExecutionVenue.IBKR_PAPER,
            max_position=4_000.0,
            max_order_size=800.0,
            quote_refresh_seconds=2.0,
            orderbook_refresh_seconds=1.0,
            reference_price=320.0,
            tick_size=0.05,
            depth_levels=5,
        ),
    },
}


def universe() -> Dict[ExecutionVenue, Dict[str, PairLimit]]:
    """Return the immutable sandbox limits universe."""

    return _SANDBOX_LIMITS


def _normalise_symbol(venue: ExecutionVenue, symbol: str) -> str:
    if venue is ExecutionVenue.BINANCE_SPOT:
        return normalize_binance_symbol(symbol)
    if venue is ExecutionVenue.IBKR_PAPER:
        return normalize_ibkr_symbol(symbol)
    return symbol.upper()


def get_pair_limit(venue: ExecutionVenue, symbol: str) -> PairLimit | None:
    """Retrieve the configured limits for a symbol."""

    normalised = _normalise_symbol(venue, symbol)
    return _SANDBOX_LIMITS.get(venue, {}).get(normalised)


def iter_supported_pairs() -> Iterable[PairLimit]:
    """Iterate over the configured pair limits."""

    for venue_limits in _SANDBOX_LIMITS.values():
        yield from venue_limits.values()


def build_quote(limit: PairLimit) -> Quote:
    """Construct a synthetic quote snapshot in sandbox mode."""

    bid = limit.reference_price - (limit.tick_size / 2)
    ask = limit.reference_price + (limit.tick_size / 2)
    mid = (bid + ask) / 2
    spread_bps = (ask - bid) / mid * 10_000
    return Quote(
        symbol=limit.symbol,
        venue=limit.venue,
        bid=bid,
        ask=ask,
        mid=mid,
        spread_bps=spread_bps,
        timestamp=datetime.now(timezone.utc),
    )


def build_orderbook(limit: PairLimit) -> OrderBookSnapshot:
    """Generate a deterministic sandbox order book."""

    bids = [
        OrderBookLevel(
            price=limit.reference_price - limit.tick_size * (index + 1),
            size=limit.max_order_size,
        )
        for index in range(limit.depth_levels)
    ]
    asks = [
        OrderBookLevel(
            price=limit.reference_price + limit.tick_size * (index + 1),
            size=limit.max_order_size,
        )
        for index in range(limit.depth_levels)
    ]
    return OrderBookSnapshot(
        symbol=limit.symbol,
        venue=limit.venue,
        bids=bids,
        asks=asks,
        depth=limit.depth_levels,
        last_update=datetime.now(timezone.utc),
    )


def build_plan(order: OrderRequest) -> ExecutionPlan:
    """Compose a sandbox execution plan for the provided order request."""

    limit = get_pair_limit(order.venue, order.symbol)
    if limit is None:
        raise ValueError(f"Pair {order.symbol} is not configured for {order.venue}")
    quote = build_quote(limit)
    book = build_orderbook(limit)
    rationale = (
        f"Sandbox plan for {order.side} {order.quantity} {order.symbol} on {order.venue}."
        " Risk controls sourced from providers.limits."
    )
    return ExecutionPlan(
        venue=order.venue,
        symbol=order.symbol,
        quote=quote,
        orderbook=book,
        order=order,
        rationale=rationale,
    )


__all__ = [
    "PairLimit",
    "build_orderbook",
    "build_plan",
    "build_quote",
    "get_pair_limit",
    "iter_supported_pairs",
    "universe",
]
