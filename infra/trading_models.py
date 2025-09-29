"""SQLAlchemy models for core trading entities."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

TradingBase = declarative_base()


SQLITE_BIGINT = BigInteger().with_variant(Integer, "sqlite")


class Order(TradingBase):
    """Represents an order submitted by a strategy or user."""

    __tablename__ = "trading_orders"

    id: int = Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    external_order_id: Optional[str] = Column(String(128), unique=True)
    correlation_id: Optional[str] = Column(String(128), index=True)
    account_id: str = Column(String(64), nullable=False, index=True)
    broker: str = Column(String(32), nullable=False, index=True)
    venue: str = Column(String(64), nullable=False, index=True)
    symbol: str = Column(String(32), nullable=False, index=True)
    side: str = Column(String(8), nullable=False)
    order_type: str = Column(String(16), nullable=False)
    quantity: Decimal = Column(Numeric(20, 8), nullable=False)
    filled_quantity: Decimal = Column(Numeric(20, 8), nullable=False, default=0)
    limit_price: Optional[Decimal] = Column(Numeric(20, 8))
    stop_price: Optional[Decimal] = Column(Numeric(20, 8))
    status: str = Column(String(16), nullable=False, default="pending")
    time_in_force: Optional[str] = Column(String(16))
    submitted_at: Optional[datetime] = Column(DateTime(timezone=True))
    expires_at: Optional[datetime] = Column(DateTime(timezone=True))
    notes: Optional[str] = Column(String(255))
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    executions = relationship(
        "Execution",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="Execution.executed_at.desc()",
    )

    __table_args__ = (
        Index("ix_trading_orders_symbol_created_at", "symbol", "created_at"),
        Index("ix_trading_orders_account_created_at", "account_id", "created_at"),
    )


class Execution(TradingBase):
    """Execution events associated with an order."""

    __tablename__ = "trading_executions"

    id: int = Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    order_id: int = Column(
        SQLITE_BIGINT,
        ForeignKey("trading_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_execution_id: Optional[str] = Column(String(128), unique=True)
    correlation_id: Optional[str] = Column(String(128), index=True)
    account_id: str = Column(String(64), nullable=False, index=True)
    symbol: str = Column(String(32), nullable=False, index=True)
    quantity: Decimal = Column(Numeric(20, 8), nullable=False)
    price: Decimal = Column(Numeric(20, 8), nullable=False)
    fees: Optional[Decimal] = Column(Numeric(20, 8))
    liquidity: Optional[str] = Column(String(16))
    executed_at: datetime = Column(DateTime(timezone=True), nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    order = relationship("Order", back_populates="executions")

    __table_args__ = (
        Index("ix_trading_executions_symbol_executed_at", "symbol", "executed_at"),
        Index("ix_trading_executions_account_executed_at", "account_id", "executed_at"),
    )


__all__ = ["TradingBase", "Order", "Execution"]
