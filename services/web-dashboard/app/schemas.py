"""Data models for the web dashboard service."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Categorise the urgency of an alert."""

    info = "info"
    warning = "warning"
    critical = "critical"


class Holding(BaseModel):
    """Represent an asset position within a portfolio."""

    symbol: str = Field(..., description="Ticker or symbol of the asset")
    quantity: float = Field(..., description="Number of units held")
    average_price: float = Field(..., description="Average fill price of the position")
    current_price: float = Field(..., description="Last traded price for the asset")

    @property
    def market_value(self) -> float:
        """Return the current market value for the holding."""

        return self.quantity * self.current_price


class Portfolio(BaseModel):
    """Snapshot of a portfolio."""

    name: str
    owner: str
    holdings: List[Holding]

    @property
    def total_value(self) -> float:
        """Compute the aggregated value for all holdings."""

        return sum(position.market_value for position in self.holdings)


class Transaction(BaseModel):
    """Represent a trading event that impacted a portfolio."""

    timestamp: datetime
    symbol: str
    side: str = Field(..., description="buy or sell")
    quantity: float
    price: float
    portfolio: str = Field(..., description="Portfolio affected by the transaction")


class Alert(BaseModel):
    """Describe a signal that requires user attention."""

    id: str
    title: str
    detail: str
    risk: RiskLevel = Field(default=RiskLevel.info)
    created_at: datetime
    acknowledged: bool = Field(False, description="Whether the alert has been acknowledged")


class DashboardContext(BaseModel):
    """Container with all payloads rendered in the dashboard template."""

    portfolios: List[Portfolio]
    transactions: List[Transaction]
    alerts: List[Alert]

