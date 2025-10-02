"""Pydantic schemas for order router contracts and persisted entities."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator

from datetime import datetime

from schemas.market import (
    ExecutionReport as MarketExecutionReport,
    OrderRequest,
)

from providers import normalize_binance_symbol, normalize_ibkr_symbol


class RiskOverrides(BaseModel):
    """Risk adjustments provided by the caller when routing an order."""

    account_id: str = Field(default="default", min_length=1, max_length=64)
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    stop_loss: float | None = Field(default=None, gt=0)


class ExecutionIntent(OrderRequest):
    """Order routing payload combining the shared order request and risk context."""

    account_id: str | None = Field(default=None, min_length=1, max_length=64)
    risk: RiskOverrides | None = None

    @model_validator(mode="after")
    def _normalise_symbol(self) -> "ExecutionIntent":
        if self.venue.value.startswith("binance"):
            symbol = normalize_binance_symbol(self.symbol)
        elif self.venue.value.startswith("ibkr"):
            symbol = normalize_ibkr_symbol(self.symbol)
        else:
            symbol = self.symbol.upper()
        object.__setattr__(self, "symbol", symbol)
        return self


class ExecutionReport(MarketExecutionReport):
    """Execution acknowledgment returned by the order router."""

    pass


class PositionHolding(BaseModel):
    """Describe an aggregated position for a given portfolio."""

    id: str
    portfolio_id: str
    portfolio: str
    account_id: str
    symbol: str
    quantity: float
    average_price: float
    current_price: float
    market_value: float


class PortfolioSnapshot(BaseModel):
    """Collection of holdings representing the exposure of an account."""

    id: str
    name: str
    owner: str
    total_value: float
    holdings: List[PositionHolding] = Field(default_factory=list)


class PositionsResponse(BaseModel):
    """Payload returned when listing current positions."""

    items: List[PortfolioSnapshot]
    as_of: datetime | None = None


class PositionCloseRequest(BaseModel):
    """Optional target quantity when closing or resizing a position."""

    target_quantity: float | None = Field(
        default=None,
        description="Target net quantity after the adjustment. Defaults to 0 (full close).",
    )


class PositionCloseResponse(BaseModel):
    """Execution report returned after requesting a close/adjustment."""

    order: ExecutionReport
    positions: PositionsResponse


class ExecutionRecord(BaseModel):
    id: int
    order_id: int
    external_execution_id: str | None = None
    correlation_id: str | None = None
    account_id: str
    symbol: str
    quantity: float
    price: float
    fees: float | None = None
    liquidity: str | None = None
    executed_at: datetime
    created_at: datetime
    notes: str | None = None
    tags: List[str] = Field(default_factory=list)

    @field_validator("quantity", "price", "fees", mode="before")
    @classmethod
    def _convert_decimal(cls, value: float | Decimal | None) -> float | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        return value


class OrderRecord(BaseModel):
    id: int
    external_order_id: str | None = None
    correlation_id: str | None = None
    account_id: str
    broker: str
    venue: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    filled_quantity: float
    limit_price: float | None = None
    stop_price: float | None = None
    status: str
    time_in_force: str | None = None
    submitted_at: datetime | None = None
    expires_at: datetime | None = None
    notes: str | None = None
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    executions: List[ExecutionRecord] = Field(default_factory=list)

    @field_validator(
        "quantity",
        "filled_quantity",
        "limit_price",
        "stop_price",
        mode="before",
    )
    @classmethod
    def _convert_order_decimal(cls, value: float | Decimal | None) -> float | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        return value


class PaginationMetadata(BaseModel):
    limit: int
    offset: int
    total: int


class OrdersLogMetadata(PaginationMetadata):
    account_id: str | None = None
    symbol: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    tag: str | None = None
    strategy: str | None = None


class ExecutionsMetadata(PaginationMetadata):
    account_id: str | None = None
    symbol: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    order_id: int | None = None


class PaginatedOrders(BaseModel):
    items: List[OrderRecord]
    metadata: OrdersLogMetadata


class OrderAnnotationPayload(BaseModel):
    notes: str | None = Field(default=None, min_length=1, max_length=2000)
    tags: List[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def _normalise_tags(cls, value: List[str]) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            return parts
        cleaned: List[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            stripped = item.strip()
            if stripped:
                cleaned.append(stripped)
        return cleaned


class PaginatedExecutions(BaseModel):
    items: List[ExecutionRecord]
    metadata: ExecutionsMetadata


__all__ = [
    "ExecutionIntent",
    "ExecutionReport",
    "ExecutionRecord",
    "OrderRecord",
    "OrderAnnotationPayload",
    "RiskOverrides",
    "PaginationMetadata",
    "OrdersLogMetadata",
    "ExecutionsMetadata",
    "PaginatedExecutions",
    "PaginatedOrders",
    "PositionHolding",
    "PortfolioSnapshot",
    "PositionsResponse",
    "PositionCloseRequest",
    "PositionCloseResponse",
]
