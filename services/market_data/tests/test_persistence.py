import importlib
from datetime import datetime, timezone
from types import ModuleType
from typing import Callable, Iterator, NamedTuple

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

SessionScopeFactory = Callable[[], Iterator[Session]]


@pytest.fixture()
def sqlite_session_scope(monkeypatch: pytest.MonkeyPatch) -> "PersistenceTestContext":
    url = "sqlite+pysqlite:///:memory:"
    monkeypatch.setenv("MARKET_DATA_DATABASE_URL", url)
    monkeypatch.setenv("TRADINGVIEW_HMAC_SECRET", "test-secret")
    monkeypatch.setenv("SECRET_MANAGER_PROVIDER", "environment")

    from libs import secrets

    secrets.get_secret_manager.cache_clear()

    from services.market_data.app import config

    config.get_settings.cache_clear()

    engine = create_engine(
        url,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    tables_module = importlib.import_module("services.market_data.app.tables")
    persistence_module = importlib.import_module("services.market_data.app.persistence")

    ohlcv_table = tables_module.MarketDataOHLCV.__table__
    tick_table = tables_module.MarketDataTick.__table__
    ohlcv_extra_column = ohlcv_table.c.extra
    tick_extra_column = tick_table.c.extra
    original_ohlcv_extra_type = ohlcv_extra_column.type
    original_tick_extra_type = tick_extra_column.type
    ohlcv_extra_column.type = SQLITE_JSON()
    tick_extra_column.type = SQLITE_JSON()
    tables_module.Base.metadata.create_all(engine)

    database = importlib.import_module("services.market_data.app.database")
    monkeypatch.setattr(database, "_engine", engine, raising=False)
    monkeypatch.setattr(database, "_SessionLocal", session_factory, raising=False)

    try:
        yield PersistenceTestContext(
            session_scope=database.session_scope,
            tables=tables_module,
            persistence=persistence_module,
        )
    finally:
        tables_module.Base.metadata.drop_all(engine)
        engine.dispose()
        ohlcv_extra_column.type = original_ohlcv_extra_type
        tick_extra_column.type = original_tick_extra_type
        config.get_settings.cache_clear()
        secrets.get_secret_manager.cache_clear()


class PersistenceTestContext(NamedTuple):
    session_scope: SessionScopeFactory
    tables: ModuleType
    persistence: ModuleType


def test_persist_ohlcv_upserts(sqlite_session_scope: PersistenceTestContext) -> None:
    session_scope = sqlite_session_scope.session_scope
    tables = sqlite_session_scope.tables
    persistence = sqlite_session_scope.persistence
    first_timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    second_timestamp = datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc)

    initial_rows = [
        {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "timestamp": first_timestamp,
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 50.0,
        },
        {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "timestamp": second_timestamp,
            "open": 105.0,
            "high": 112.0,
            "low": 95.0,
            "close": 108.0,
            "volume": 60.0,
        },
    ]

    with session_scope() as session:
        persistence.persist_ohlcv(session, initial_rows)

    updated_rows = [
        {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "timestamp": first_timestamp,
            "open": 200.0,
            "high": 220.0,
            "low": 180.0,
            "close": 210.0,
            "volume": 100.0,
        }
    ]

    with session_scope() as session:
        persistence.persist_ohlcv(session, updated_rows)

    with session_scope() as session:
        refreshed = session.execute(
            select(
                tables.MarketDataOHLCV.open,
                tables.MarketDataOHLCV.high,
                tables.MarketDataOHLCV.low,
                tables.MarketDataOHLCV.close,
                tables.MarketDataOHLCV.volume,
            ).where(tables.MarketDataOHLCV.timestamp == first_timestamp)
        ).one()

    assert refreshed.open == 200.0
    assert refreshed.high == 220.0
    assert refreshed.low == 180.0
    assert refreshed.close == 210.0
    assert refreshed.volume == 100.0

    with session_scope() as session:
        total_rows = session.execute(select(func.count()).select_from(tables.MarketDataOHLCV)).scalar_one()
    assert total_rows == 2


def test_persist_ticks_deduplicates(sqlite_session_scope: PersistenceTestContext) -> None:
    session_scope = sqlite_session_scope.session_scope
    tables = sqlite_session_scope.tables
    persistence = sqlite_session_scope.persistence
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)

    first_tick = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "source": "api",
        "timestamp": timestamp,
        "price": 105.0,
        "size": 1.0,
    }
    duplicate_tick = dict(first_tick)
    second_tick = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "source": "api",
        "timestamp": datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        "price": 106.0,
        "size": 0.5,
    }

    with session_scope() as session:
        persistence.persist_ticks(session, [first_tick])

    with session_scope() as session:
        persistence.persist_ticks(session, [duplicate_tick, second_tick])

    with session_scope() as session:
        prices = session.execute(select(tables.MarketDataTick.price)).scalars().all()

    assert len(prices) == 2
    assert set(prices) == {105.0, 106.0}


def test_session_scope_rolls_back_on_error(sqlite_session_scope: PersistenceTestContext) -> None:
    session_scope = sqlite_session_scope.session_scope
    tables = sqlite_session_scope.tables
    persistence = sqlite_session_scope.persistence
    tick = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "source": "api",
        "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "price": 105.0,
        "size": 1.0,
    }

    with pytest.raises(RuntimeError):
        with session_scope() as session:
            persistence.persist_ticks(session, [tick])
            raise RuntimeError("boom")

    with session_scope() as session:
        tick_count = session.execute(select(func.count()).select_from(tables.MarketDataTick)).scalar_one()

    assert tick_count == 0
