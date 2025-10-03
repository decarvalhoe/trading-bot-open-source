"""Shared market data and order execution contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Self

from pydantic import BaseModel, Field, RootModel, model_validator


class ExecutionVenue(str, Enum):
    """Identifier for the execution venue or liquidity source."""

    BINANCE_SPOT = "binance.spot"
    IBKR_PAPER = "ibkr.paper"
    SANDBOX_INTERNAL = "sandbox.internal"


class Quote(BaseModel):
    """Best bid/ask snapshot for a trading symbol."""

    symbol: str
    venue: ExecutionVenue
    bid: float = Field(..., gt=0)
    ask: float = Field(..., gt=0)
    mid: float = Field(..., gt=0)
    spread_bps: float = Field(..., ge=0)
    timestamp: datetime

    @model_validator(mode="after")
    def _validate_mid(self) -> Self:
        if self.bid > self.ask:
            raise ValueError("bid must be lower than ask")
        implied_mid = (self.bid + self.ask) / 2
        if abs(self.mid - implied_mid) > 1e-9:
            object.__setattr__(self, "mid", implied_mid)
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))
        return self


class OrderBookLevel(BaseModel):
    price: float = Field(..., gt=0)
    size: float = Field(..., ge=0)


class OrderBookSnapshot(BaseModel):
    """Aggregated order book levels for a symbol."""

    symbol: str
    venue: ExecutionVenue
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    depth: int = Field(..., ge=0)
    last_update: datetime

    @model_validator(mode="after")
    def _ensure_depth(self) -> Self:
        depth = min(len(self.bids), len(self.asks))
        object.__setattr__(self, "depth", depth)
        if self.last_update.tzinfo is None:
            object.__setattr__(self, "last_update", self.last_update.replace(tzinfo=timezone.utc))
        return self


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class OrderRequest(BaseModel):
    """Standardised order placement contract."""

    broker: str
    venue: ExecutionVenue
    symbol: str
    side: OrderSide
    quantity: float = Field(..., gt=0)
    order_type: OrderType
    price: float | None = Field(default=None, gt=0)
    time_in_force: TimeInForce = TimeInForce.GTC
    estimated_loss: float | None = None
    client_order_id: str | None = Field(default=None, max_length=36)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_price(self) -> Self:
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("price is required for limit orders")
        if self.order_type == OrderType.MARKET:
            object.__setattr__(self, "price", None)
        return self


class ExecutionStatus(str, Enum):
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ExecutionFill(BaseModel):
    quantity: float = Field(..., ge=0)
    price: float = Field(..., gt=0)
    timestamp: datetime

    @model_validator(mode="after")
    def _ensure_timestamp(self) -> Self:
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))
        return self


class ExecutionReport(BaseModel):
    order_id: str
    status: ExecutionStatus
    broker: str
    venue: ExecutionVenue
    symbol: str
    side: OrderSide
    quantity: float
    filled_quantity: float
    avg_price: float | None = None
    submitted_at: datetime
    fills: list[ExecutionFill] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _timestamps(self) -> Self:
        if self.submitted_at.tzinfo is None:
            object.__setattr__(self, "submitted_at", self.submitted_at.replace(tzinfo=timezone.utc))
        return self


class ExecutionPlan(BaseModel):
    """Aggregate payload linking quote, order book and order intent."""

    venue: ExecutionVenue
    symbol: str
    quote: Quote
    orderbook: OrderBookSnapshot
    order: OrderRequest
    rationale: str | None = None


class ExecutionPlanList(RootModel[list[ExecutionPlan]]):
    """Container used by orchestrator endpoints returning multiple plans."""


__all__ = [
    "ExecutionFill",
    "ExecutionPlan",
    "ExecutionPlanList",
    "ExecutionReport",
    "ExecutionStatus",
    "ExecutionVenue",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "OrderRequest",
    "OrderSide",
    "OrderType",
    "Quote",
    "TimeInForce",
]
