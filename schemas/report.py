from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, Field, validator


class StrategyName(str, Enum):
    ORB = "ORB"
    IB = "IB"
    GAP_FILL = "Gap-Fill"
    ENGULFING = "Engulfing"


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
