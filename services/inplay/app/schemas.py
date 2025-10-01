from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


SetupStatus = Literal["validated", "pending", "failed"]
SessionName = Literal["london", "new_york", "asia"]


class TickPayload(BaseModel):
    symbol: str
    strategy: str
    entry: float
    target: float
    stop: float
    probability: float = Field(..., ge=0.0, le=1.0)
    status: SetupStatus = "pending"
    session: SessionName = "london"
    watchlists: list[str] | None = None
    source: Literal["market-data", "manual"] = "market-data"
    received_at: datetime = Field(default_factory=datetime.utcnow)
    report_url: str | None = Field(
        default=None,
        description="Lien pointant vers les détails du rapport de stratégie",
    )


class StrategySetup(BaseModel):
    symbol: str
    strategy: str
    entry: float
    target: float
    stop: float
    probability: float
    status: SetupStatus = "pending"
    session: SessionName = "london"
    updated_at: datetime
    report_url: str | None = Field(
        default=None,
        description="Lien enrichi renvoyant vers les détails du rapport",
    )


class StrategyReportPayload(BaseModel):
    symbol: str
    strategy: str
    session: SessionName | None = None
    setup: StrategySetup
    report: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    market: dict[str, Any] | None = None


class SymbolSetups(BaseModel):
    symbol: str
    setups: list[StrategySetup]


class WatchlistSnapshot(BaseModel):
    id: str
    symbols: list[SymbolSetups]
    updated_at: datetime | None = None


class WatchlistStreamEvent(BaseModel):
    type: Literal["watchlist.update"] = "watchlist.update"
    payload: WatchlistSnapshot
