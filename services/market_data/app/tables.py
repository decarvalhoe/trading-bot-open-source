from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Integer, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

OHLCV_PK_COLUMNS = ("exchange", "symbol", "interval", "timestamp")
TICKS_PK_COLUMNS = ("exchange", "symbol", "source", "timestamp")


class MarketDataOHLCV(Base):
    __tablename__ = "market_data_ohlcv"
    __table_args__ = (
        PrimaryKeyConstraint(*OHLCV_PK_COLUMNS, name="pk_market_data_ohlcv"),
    )

    exchange = Column(String(32), nullable=False, primary_key=True)
    symbol = Column(String(64), nullable=False, primary_key=True)
    interval = Column(String(16), nullable=False, primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, primary_key=True)
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
        PrimaryKeyConstraint(*TICKS_PK_COLUMNS, name="pk_market_data_ticks"),
    )

    exchange = Column(String(32), nullable=False, primary_key=True)
    symbol = Column(String(64), nullable=False, primary_key=True)
    source = Column(String(32), nullable=False, primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, primary_key=True)
    price = Column(Float, nullable=False)
    size = Column(Float, nullable=True)
    side = Column(String(8), nullable=True)
    extra = Column(JSONB, nullable=True)
