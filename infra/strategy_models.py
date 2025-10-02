"""SQLAlchemy models backing strategy management for the algo engine."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship


StrategyBase = declarative_base()


class Strategy(StrategyBase):
    """Primary table storing the latest state for a trading strategy."""

    __tablename__ = "strategies"

    id: str = Column(String(36), primary_key=True)
    name: str = Column(String(255), nullable=False)
    strategy_type: str = Column(String(64), nullable=False, index=True)
    version: int = Column(Integer, nullable=False, default=1)
    parameters: dict | None = Column(JSON, nullable=False, default=dict)
    enabled: bool = Column(Boolean, nullable=False, default=False, index=True)
    tags: list[str] | None = Column(JSON, nullable=False, default=list)
    metadata_: dict | None = Column("metadata", JSON, nullable=True)
    source_format: str | None = Column(String(16), nullable=True)
    source: str | None = Column(Text, nullable=True)
    derived_from: str | None = Column(
        String(36), ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: str = Column(String(16), nullable=False, default="PENDING", index=True)
    last_error: str | None = Column(Text, nullable=True)
    last_backtest: dict | None = Column(JSON, nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    versions = relationship(
        "StrategyVersion",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyVersion.version.desc()",
    )
    executions = relationship(
        "StrategyExecution",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyExecution.submitted_at.desc()",
    )
    backtests = relationship(
        "StrategyBacktest",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyBacktest.ran_at.desc()",
    )


class StrategyVersion(StrategyBase):
    """Immutable snapshot recorded every time a strategy is updated."""

    __tablename__ = "strategy_versions"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id: str = Column(
        String(36),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: int = Column(Integer, nullable=False)
    name: str = Column(String(255), nullable=False)
    strategy_type: str = Column(String(64), nullable=False)
    parameters: dict | None = Column(JSON, nullable=False, default=dict)
    metadata_: dict | None = Column("metadata", JSON, nullable=True)
    tags: list[str] | None = Column(JSON, nullable=False, default=list)
    source_format: str | None = Column(String(16), nullable=True)
    source: str | None = Column(Text, nullable=True)
    derived_from: str | None = Column(String(36), nullable=True, index=True)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: str | None = Column(String(128), nullable=True)

    strategy = relationship("Strategy", back_populates="versions")

    __table_args__ = (
        UniqueConstraint(
            "strategy_id", "version", name="uq_strategy_versions_strategy_version"
        ),
    )


class StrategyExecution(StrategyBase):
    """Historical record of executions routed on behalf of a strategy."""

    __tablename__ = "strategy_executions"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id: str = Column(
        String(36),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: str = Column(String(128), nullable=False)
    status: str = Column(String(32), nullable=False)
    broker: str = Column(String(64), nullable=False)
    venue: str = Column(String(64), nullable=False)
    symbol: str = Column(String(64), nullable=False)
    side: str = Column(String(16), nullable=False)
    quantity: float = Column(Float, nullable=False)
    filled_quantity: float = Column(Float, nullable=False)
    avg_price: float | None = Column(Float, nullable=True)
    submitted_at: datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    payload: dict = Column(JSON, nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    strategy = relationship("Strategy", back_populates="executions")

    __table_args__ = (
        Index(
            "ix_strategy_executions_strategy_submitted_at",
            "strategy_id",
            "submitted_at",
        ),
    )


class StrategyBacktest(StrategyBase):
    """Historical record of backtests executed for a strategy."""

    __tablename__ = "strategy_backtests"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id: str = Column(
        String(36),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ran_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    initial_balance: float = Column(Float, nullable=False)
    profit_loss: float = Column(Float, nullable=False)
    total_return: float = Column(Float, nullable=False)
    max_drawdown: float = Column(Float, nullable=False)
    equity_curve: list[float] | None = Column(JSON, nullable=False)
    summary: dict | None = Column(JSON, nullable=False)

    strategy = relationship("Strategy", back_populates="backtests")

    __table_args__ = (
        Index(
            "ix_strategy_backtests_strategy_ran_at",
            "strategy_id",
            "ran_at",
        ),
    )


__all__ = [
    "StrategyBase",
    "Strategy",
    "StrategyVersion",
    "StrategyExecution",
    "StrategyBacktest",
]
