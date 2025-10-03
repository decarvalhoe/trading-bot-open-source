from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from schemas.market import ExecutionVenue


class TradingViewSignal(BaseModel):
    symbol: str
    exchange: str
    interval: str | None = None
    price: float
    timestamp: datetime
    strategy: str | None = None
    size: float | None = Field(None, ge=0)
    direction: str | None = Field(None, description="Long/Short direction if provided")
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersistedBar(BaseModel):
    exchange: str
    symbol: str
    interval: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float | None = None
    trades: int | None = None
    extra: dict[str, Any] | None = None


class PersistedTick(BaseModel):
    exchange: str
    symbol: str
    source: str
    timestamp: datetime
    price: float
    size: float | None = None
    side: str | None = None
    extra: dict[str, Any] | None = None


class MarketContextSnapshot(BaseModel):
    """Aggregated snapshot combining quote, volume and indicator data."""

    symbol: str
    venue: ExecutionVenue
    price: float
    bid: float
    ask: float
    spread_bps: float
    volume: float
    total_bid_volume: float
    total_ask_volume: float
    indicators: dict[str, float] = Field(default_factory=dict)
    timestamp: datetime

    model_config = ConfigDict(json_encoders={datetime: lambda value: value.isoformat()})

    def model_post_init(self, __context: Any) -> None:  # noqa: D401
        """Ensure timestamps are timezone aware for downstream services."""

        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))


class MarketStreamEvent(BaseModel):
    """Structure for streaming payloads consumed by alert-engine."""

    price: float
    volume: float | None = None
    bid: float | None = None
    ask: float | None = None
    metadata: dict[str, Any] | None = None
    timestamp: datetime

    model_config = ConfigDict(json_encoders={datetime: lambda value: value.isoformat()})

    def model_post_init(self, __context: Any) -> None:  # noqa: D401
        """Normalise timestamps to UTC for deterministic tests."""

        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))


class MarketSymbol(BaseModel):
    symbol: str
    base_asset: str | None = None
    quote_asset: str | None = None
    status: str | None = None
    description: str | None = None
    tick_size: float | None = Field(default=None, ge=0)
    lot_size: float | None = Field(default=None, ge=0)


class SymbolListResponse(BaseModel):
    venue: ExecutionVenue
    symbols: list[MarketSymbol]


class QuoteLevel(BaseModel):
    price: float
    size: float | None = Field(default=None, ge=0)


class QuoteSnapshot(BaseModel):
    venue: ExecutionVenue
    symbol: str
    bid: QuoteLevel | None = None
    ask: QuoteLevel | None = None
    mid: float | None = Field(default=None, ge=0)
    spread_bps: float | None = Field(default=None, ge=0)
    last_update: datetime

    model_config = ConfigDict(json_encoders={datetime: lambda value: value.isoformat()})

    def model_post_init(self, __context: Any) -> None:  # noqa: D401
        """Ensure timestamps are timezone aware for downstream services."""

        if self.last_update.tzinfo is None:
            object.__setattr__(self, "last_update", self.last_update.replace(tzinfo=timezone.utc))


class HistoricalCandle(BaseModel):
    open_time: datetime
    close_time: datetime | None = None
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int | None = None
    quote_volume: float | None = None

    model_config = ConfigDict(json_encoders={datetime: lambda value: value.isoformat()})

    def model_post_init(self, __context: Any) -> None:  # noqa: D401
        """Ensure all timestamps carry timezone information."""

        if self.open_time.tzinfo is None:
            object.__setattr__(self, "open_time", self.open_time.replace(tzinfo=timezone.utc))
        if self.close_time and self.close_time.tzinfo is None:
            object.__setattr__(self, "close_time", self.close_time.replace(tzinfo=timezone.utc))


class HistoryResponse(BaseModel):
    venue: ExecutionVenue
    symbol: str
    interval: str
    candles: list[HistoricalCandle]


__all__ = [
    "HistoricalCandle",
    "HistoryResponse",
    "MarketContextSnapshot",
    "MarketStreamEvent",
    "MarketSymbol",
    "PersistedBar",
    "PersistedTick",
    "QuoteLevel",
    "QuoteSnapshot",
    "SymbolListResponse",
    "TradingViewSignal",
]
