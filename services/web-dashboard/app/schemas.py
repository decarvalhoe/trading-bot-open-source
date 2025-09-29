"""Data models for the web dashboard service."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List

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


class StrategyRuntimeStatus(str, Enum):
    """Runtime status for a trading strategy managed by the orchestrator."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"


class StrategyExecutionSnapshot(BaseModel):
    """Last execution observed for a strategy."""

    order_id: str | None = Field(default=None, description="Identifier of the routed order")
    status: str | None = Field(default=None, description="Execution status returned by the broker")
    submitted_at: datetime | None = Field(
        default=None,
        description="Timestamp when the order was acknowledged by the broker",
    )
    symbol: str | None = Field(default=None, description="Instrument traded during the execution")
    venue: str | None = Field(default=None, description="Market venue associated to the execution")
    side: str | None = Field(default=None, description="Side of the trade (buy/sell)")
    quantity: float | None = Field(default=None, description="Quantity submitted with the order")
    filled_quantity: float | None = Field(
        default=None,
        description="Quantity filled according to the execution report",
    )


class StrategyStatus(BaseModel):
    """High level status for a strategy exposed on the dashboard."""

    id: str = Field(..., description="Unique identifier of the strategy")
    name: str = Field(..., description="Human readable name")
    status: StrategyRuntimeStatus = Field(
        default=StrategyRuntimeStatus.PENDING,
        description="Latest runtime status returned by the orchestrator",
    )
    enabled: bool = Field(default=False, description="Whether the strategy is configured as active")
    strategy_type: str | None = Field(
        default=None,
        description="Identifier of the plugin or strategy template",
    )
    tags: List[str] = Field(default_factory=list, description="Labels attached to the strategy")
    last_error: str | None = Field(
        default=None,
        description="Latest error message recorded when the strategy transitioned to ERROR",
    )
    last_execution: StrategyExecutionSnapshot | None = Field(
        default=None,
        description="Most recent execution recorded for this strategy",
    )
    metadata: Dict[str, object] = Field(
        default_factory=dict,
        description="Additional metadata propagated from the orchestrator store",
    )


class LiveLogEntry(BaseModel):
    """Structured log entry displayed in the live activity console."""

    timestamp: datetime = Field(..., description="Moment when the event was recorded")
    level: str = Field(default="info", description="Log severity level")
    message: str = Field(..., description="Human readable summary of the event")
    order_id: str | None = Field(default=None, description="Order identifier associated to the event")
    status: str | None = Field(default=None, description="Execution status or state change associated")
    symbol: str | None = Field(default=None, description="Instrument referenced by the event")
    strategy_id: str | None = Field(
        default=None,
        description="Identifier of the strategy associated to the log entry when known",
    )
    strategy_hint: str | None = Field(
        default=None,
        description="Name or tag extracted from the upstream payload to help with filtering",
    )
    extra: Dict[str, object] = Field(
        default_factory=dict,
        description="Raw fields preserved from the upstream payload for debugging purposes",
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
    strategies: List[StrategyStatus] = Field(
        default_factory=list,
        description="Status payloads for strategies managed by the orchestrator",
    )
    logs: List[LiveLogEntry] = Field(
        default_factory=list,
        description="Recent orchestration or execution events for the live console",
    )

