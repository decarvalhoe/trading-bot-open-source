from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
