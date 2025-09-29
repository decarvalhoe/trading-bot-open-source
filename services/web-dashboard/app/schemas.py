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


class PortfolioTimeseriesPoint(BaseModel):
    """Represent a single observation in a portfolio history series."""

    timestamp: datetime = Field(..., description="Moment where the snapshot was captured")
    value: float = Field(..., description="Total portfolio value at the timestamp")
    pnl: float | None = Field(
        default=None,
        description="Profit and loss variation relative to the initial observation",
    )


class PortfolioHistorySeries(BaseModel):
    """Collection of history points for a specific portfolio."""

    name: str = Field(..., description="Portfolio identifier")
    owner: str | None = Field(default=None, description="Owner of the portfolio")
    currency: str = Field(default="$", description="Currency used for valuation")
    series: List[PortfolioTimeseriesPoint] = Field(
        default_factory=list,
        description="Ordered list of observations for the portfolio",
    )


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


class PerformanceMetrics(BaseModel):
    """Summarise risk and return analytics provided by the reports service."""

    account: str | None = Field(default=None, description="Trading account identifier")
    as_of: datetime | None = Field(default=None, description="Timestamp of the latest data point")
    currency: str = Field(default="$", description="Currency symbol for monetary values")
    current_pnl: float = Field(default=0.0, description="Most recent realised P&L")
    current_drawdown: float = Field(default=0.0, description="Drawdown captured for the latest session")
    cumulative_return: float = Field(
        default=0.0,
        description="Compounded return over the available sample (expressed as a ratio when exposure is known)",
    )
    cumulative_return_is_ratio: bool = Field(
        default=False,
        description="Flag indicating whether cumulative_return is a ratio (True) or an absolute amount (False)",
    )
    sharpe_ratio: float | None = Field(default=None, description="Annualised Sharpe ratio when computable")
    sample_size: int = Field(default=0, ge=0, description="Number of daily observations considered")
    uses_exposure: bool = Field(
        default=False,
        description="True when the Sharpe ratio and returns are normalised by exposure values",
    )
    available: bool = Field(
        default=False,
        description="Set to True when metrics were successfully retrieved from the reports service",
    )
    source: str = Field(
        default="reports-service",
        description="Identifier of the upstream service providing the metrics",
    )


class DashboardContext(BaseModel):
    """Container with all payloads rendered in the dashboard template."""

    portfolios: List[Portfolio]
    transactions: List[Transaction]
    alerts: List[Alert]
    metrics: PerformanceMetrics | None = Field(
        default=None,
        description="Aggregated performance analytics sourced from the reports service",
    )

