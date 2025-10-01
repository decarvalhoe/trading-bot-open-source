from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Date, DateTime, Enum as SAEnum, Float, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from schemas.report import StrategyName, Timeframe, TradeOutcome


class Base(DeclarativeBase):
    pass


class ReportDaily(Base):
    __tablename__ = "reports_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    account: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    strategy: Mapped[StrategyName] = mapped_column(SAEnum(StrategyName), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[TradeOutcome] = mapped_column(SAEnum(TradeOutcome), nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ReportIntraday(Base):
    __tablename__ = "reports_intraday"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    strategy: Mapped[StrategyName] = mapped_column(SAEnum(StrategyName), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[TradeOutcome] = mapped_column(SAEnum(TradeOutcome), nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    timeframe: Mapped[Timeframe] = mapped_column(SAEnum(Timeframe), primary_key=True)
    strategy: Mapped[StrategyName] = mapped_column(SAEnum(StrategyName), primary_key=True)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    stop: Mapped[float] = mapped_column(Float, nullable=False)
    expectancy: Mapped[float] = mapped_column(Float, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ReportBenchmark(Base):
    __tablename__ = "report_benchmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    return_value: Mapped[float] = mapped_column(Float, nullable=False)


class ReportBacktest(Base):
    __tablename__ = "report_backtests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    strategy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    account: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    initial_balance: Mapped[float] = mapped_column(Float, nullable=False)
    trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_return: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown: Mapped[float] = mapped_column(Float, nullable=False)
    equity_curve: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    parameters: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    context: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)
    metrics_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    log_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ReportJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"


class ReportJob(Base):
    __tablename__ = "report_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    parameters: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[ReportJobStatus] = mapped_column(
        SAEnum(ReportJobStatus), nullable=False, default=ReportJobStatus.PENDING
    )
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)


__all__ = [
    "Base",
    "ReportDaily",
    "ReportIntraday",
    "ReportSnapshot",
    "ReportBenchmark",
    "ReportBacktest",
    "ReportJob",
    "ReportJobStatus",
]
