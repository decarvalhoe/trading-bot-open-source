"""Pydantic schemas for order router contracts and persisted entities."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, Field, field_validator

from schemas.market import (
    ExecutionReport as MarketExecutionReport,
    OrderRequest,
)


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


class ExecutionReport(MarketExecutionReport):
    """Execution acknowledgment returned by the order router."""

    pass


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
    notes: str | None = Field(default=None, max_length=255)
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


class ExecutionsMetadata(PaginationMetadata):
    account_id: str | None = None
    symbol: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    order_id: int | None = None


class PaginatedOrders(BaseModel):
    items: List[OrderRecord]
    metadata: OrdersLogMetadata


class PaginatedExecutions(BaseModel):
    items: List[ExecutionRecord]
    metadata: ExecutionsMetadata


__all__ = [
    "ExecutionIntent",
    "ExecutionReport",
    "ExecutionRecord",
    "OrderRecord",
    "RiskOverrides",
    "PaginationMetadata",
    "OrdersLogMetadata",
    "ExecutionsMetadata",
    "PaginatedExecutions",
    "PaginatedOrders",
]
