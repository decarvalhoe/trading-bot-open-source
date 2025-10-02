from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MarketDataOHLCV(Base):
    __tablename__ = "market_data_ohlcv"
    __table_args__ = (
        UniqueConstraint("exchange", "symbol", "interval", "timestamp", name="uq_ohlcv_bar"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange = Column(String(32), nullable=False)
    symbol = Column(String(64), nullable=False)
    interval = Column(String(16), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    quote_volume = Column(Float, nullable=True)
    trades = Column(Integer, nullable=True)
    extra = Column(JSONB, nullable=True)


class MarketDataTick(Base):
    __tablename__ = "market_data_ticks"
    __table_args__ = (
        UniqueConstraint("exchange", "symbol", "timestamp", "source", name="uq_tick"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange = Column(String(32), nullable=False)
    symbol = Column(String(64), nullable=False)
    source = Column(String(32), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    price = Column(Float, nullable=False)
    size = Column(Float, nullable=True)
    side = Column(String(8), nullable=True)
    extra = Column(JSONB, nullable=True)
