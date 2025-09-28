from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Iterable, List

from pydantic import BaseModel, Field, validator


class StrategyName(str, Enum):
    ORB = "ORB"
    IB = "IB"
    GAP_FILL = "Gap-Fill"
    ENGULFING = "Engulfing"


class TradeOutcome(str, Enum):
    """Normalized trade outcomes shared across analytics tables."""

    WIN = "win"
    LOSS = "loss"
    BREAK_EVEN = "breakeven"


class StrategyMetrics(BaseModel):
    strategy: StrategyName
    probability: float = Field(..., ge=0.0, le=1.0)
    target: float
    stop: float
    expectancy: float
    sample_size: int = Field(..., ge=0)

    @validator("target", "stop", "expectancy")
    def validate_numeric(cls, value: float) -> float:  # noqa: N805
        if not isinstance(value, (int, float)):
            raise TypeError("numeric field expected")
        return float(value)


class Timeframe(str, Enum):
    DAILY = "daily"
    INTRADAY = "intraday"


class ReportSection(BaseModel):
    timeframe: Timeframe
    strategies: list[StrategyMetrics]
    updated_at: datetime | None = None

    @property
    def strategy_names(self) -> Iterable[StrategyName]:
        return (metric.strategy for metric in self.strategies)


class ReportResponse(BaseModel):
    symbol: str
    daily: ReportSection | None = None
    intraday: ReportSection | None = None

    class Config:
        json_encoders = {datetime: lambda value: value.isoformat()}


class DailyRiskIncident(BaseModel):
    """Describe an incident contributing to a drawdown."""

    symbol: str
    strategy: StrategyName
    pnl: float
    outcome: TradeOutcome
    note: str | None = None


class DailyRiskReport(BaseModel):
    """Aggregated daily risk summary used by the reporting service."""

    session_date: date
    account: str
    pnl: float
    max_drawdown: float = Field(..., ge=0.0)
    incidents: List[DailyRiskIncident] = Field(default_factory=list)

    class Config:
        json_encoders = {
            datetime: lambda value: value.isoformat(),
            date: lambda value: value.isoformat(),
        }
