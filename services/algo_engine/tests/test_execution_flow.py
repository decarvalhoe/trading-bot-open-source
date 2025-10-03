from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import importlib
from typing import Any, Dict, List
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.migration import MigrationContext
from alembic.operations import Operations
from algo_engine.app.main import StrategyRecord, StrategyStatus, orchestrator, strategy_repository
from algo_engine.app.orchestrator import Orchestrator
from algo_engine.app.order_router_client import OrderRouterClientError
from algo_engine.app.repository import StrategyRepository
from algo_engine.app.strategies.base import StrategyBase, StrategyConfig

from libs.db.db import SessionLocal
from sqlalchemy.orm import sessionmaker
from schemas.market import ExecutionStatus, ExecutionVenue, OrderSide, OrderType


class StaticSignalStrategy(StrategyBase):
    """Strategy emitting a single configurable signal when triggered."""

    key: str = "static"
    _signal: Dict[str, Any] | None = None

    def __init__(self, config: StrategyConfig, signal: Dict[str, Any]) -> None:
        super().__init__(config)
        self._signal = signal

    def generate_signals(self, market_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not market_state.get("emit", True):
            return []
        assert self._signal is not None
        return [dict(self._signal)]


def test_strategy_execution_flow_updates_state_and_handles_errors(
    main_module: Any, mock_order_router: Any
) -> None:
    """Ensure orchestrator routes signals, updates state and handles failures."""

    strategy_id = str(uuid4())
    record = strategy_repository.create(
        StrategyRecord(
            id=strategy_id,
            name="Static",
            strategy_type="static",
            parameters={},
            enabled=True,
            metadata={"strategy_id": strategy_id},
        )
    )

    signal: Dict[str, Any] = {
        "order_type": OrderType.MARKET.value,
        "broker": "paper",
        "symbol": "BTCUSDT",
        "venue": ExecutionVenue.BINANCE_SPOT.value,
        "side": OrderSide.BUY.value,
        "quantity": 1.0,
    }
    config = StrategyConfig(name="Static", enabled=True, metadata={"strategy_id": strategy_id})
    strategy = StaticSignalStrategy(config, signal)

    submitted_at = datetime.now(tz=timezone.utc).isoformat()
    mock_order_router.set_response(
        {
            "order_id": "order-success",
            "status": ExecutionStatus.FILLED.value,
            "broker": "paper",
            "venue": ExecutionVenue.BINANCE_SPOT.value,
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY.value,
            "quantity": 1.0,
            "filled_quantity": 1.0,
            "avg_price": 25000.0,
            "submitted_at": submitted_at,
            "fills": [],
            "tags": ["strategy:static"],
        }
    )

    reports = asyncio.run(
        orchestrator.execute_strategy(strategy=strategy, market_state={"emit": True})
    )
    assert len(reports) == 1
    assert reports[0].order_id == "order-success"
    assert mock_order_router.requests and mock_order_router.requests[0].url.path == "/orders"

    state = orchestrator.get_state()
    assert state.trades_submitted == 1
    assert state.recent_executions
    assert state.recent_executions[0]["order_id"] == "order-success"
    history = strategy_repository.get_recent_executions()
    assert history and history[0]["order_id"] == "order-success"

    fresh_repository = StrategyRepository(SessionLocal)
    reloaded = fresh_repository.get(strategy_id)
    assert reloaded.name == "Static"
    restored = Orchestrator(
        order_router_client=main_module.order_router_client,
        strategy_repository=fresh_repository,
    )
    restored.restore_recent_executions(
        fresh_repository.get_recent_executions(limit=restored.execution_history_limit)
    )
    assert restored.get_state().recent_executions

    updated = strategy_repository.update(strategy_id, status=StrategyStatus.ACTIVE)
    assert updated.status is StrategyStatus.ACTIVE
    assert updated.last_error is None

    orchestrator.update_daily_limit(trades_submitted=0)
    orchestrator._state.recent_executions.clear()  # type: ignore[attr-defined]
    mock_order_router.reset()
    failure_id = str(uuid4())
    failing_record = strategy_repository.create(
        StrategyRecord(
            id=failure_id,
            name="Static Failure",
            strategy_type="static",
            parameters={},
            enabled=True,
            metadata={"strategy_id": failure_id},
        )
    )
    failing_config = StrategyConfig(
        name="Static Failure",
        enabled=True,
        metadata={"strategy_id": failure_id},
    )
    failing_strategy = StaticSignalStrategy(failing_config, signal)

    mock_order_router.set_error(httpx.ConnectError("boom"))
    with pytest.raises(OrderRouterClientError):
        asyncio.run(
            orchestrator.execute_strategy(strategy=failing_strategy, market_state={"emit": True})
        )

    failure_state = orchestrator.get_state()
    assert failure_state.trades_submitted == 0
    assert failure_state.recent_executions == []

    stored_failure = strategy_repository.get(failure_id)
    assert stored_failure.status is StrategyStatus.ERROR
    assert stored_failure.last_error

    # Ensure PENDING strategy without emitted signals remains untouched
    idle_id = str(uuid4())
    idle_record = strategy_repository.create(
        StrategyRecord(
            id=idle_id,
            name="Idle",
            strategy_type="static",
            parameters={},
            enabled=True,
            metadata={"strategy_id": idle_id},
        )
    )
    idle_strategy = StaticSignalStrategy(
        StrategyConfig(name="Idle", enabled=True, metadata={"strategy_id": idle_id}),
        signal,
    )
    reports_idle = asyncio.run(
        orchestrator.execute_strategy(strategy=idle_strategy, market_state={"emit": False})
    )
    assert reports_idle == []
    assert strategy_repository.get(idle_id).status is StrategyStatus.PENDING
    assert orchestrator.get_state().trades_submitted == 0


def test_strategy_repository_handles_legacy_integer_ids(tmp_path: Any) -> None:
    """Migration converts legacy integer identifiers so repository initialises."""

    legacy_db = tmp_path / "legacy_strategies.sqlite"
    engine = sa.create_engine(f"sqlite:///{legacy_db}", isolation_level=None)

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.execute(
            sa.text(
                """
                CREATE TABLE strategies (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    strategy_type VARCHAR(64) NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    parameters TEXT NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT 0,
                    tags TEXT NOT NULL,
                    metadata TEXT,
                    source_format VARCHAR(16),
                    source TEXT,
                    derived_from INTEGER REFERENCES strategies(id) ON DELETE SET NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
                    last_error TEXT,
                    last_backtest TEXT,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        connection.execute(sa.text("CREATE INDEX ix_strategies_enabled ON strategies(enabled)"))
        connection.execute(sa.text("CREATE INDEX ix_strategies_status ON strategies(status)"))
        connection.execute(sa.text("CREATE INDEX ix_strategies_strategy_type ON strategies(strategy_type)"))
        connection.execute(
            sa.text(
                """
                CREATE TABLE strategy_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    strategy_type VARCHAR(64) NOT NULL,
                    parameters TEXT NOT NULL,
                    metadata TEXT,
                    tags TEXT NOT NULL,
                    source_format VARCHAR(16),
                    source TEXT,
                    derived_from INTEGER,
                    created_at DATETIME,
                    created_by VARCHAR(128)
                )
                """
            )
        )
        connection.execute(
            sa.text(
                "CREATE UNIQUE INDEX uq_strategy_versions_strategy_version "
                "ON strategy_versions(strategy_id, version)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE INDEX ix_strategy_versions_strategy_id ON strategy_versions(strategy_id)"
            )
        )
        connection.execute(
            sa.text(
                """
                CREATE TABLE strategy_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
                    order_id VARCHAR(128) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    broker VARCHAR(64) NOT NULL,
                    venue VARCHAR(64) NOT NULL,
                    symbol VARCHAR(64) NOT NULL,
                    side VARCHAR(16) NOT NULL,
                    quantity FLOAT NOT NULL,
                    filled_quantity FLOAT NOT NULL,
                    avg_price FLOAT,
                    submitted_at DATETIME NOT NULL,
                    payload TEXT NOT NULL,
                    created_at DATETIME
                )
                """
            )
        )
        connection.execute(
            sa.text(
                "CREATE INDEX ix_strategy_executions_strategy_id ON "
                "strategy_executions(strategy_id)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE INDEX ix_strategy_executions_strategy_submitted_at "
                "ON strategy_executions(strategy_id, submitted_at)"
            )
        )
        connection.execute(
            sa.text(
                """
                CREATE TABLE strategy_backtests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
                    ran_at DATETIME NOT NULL,
                    initial_balance FLOAT NOT NULL,
                    profit_loss FLOAT NOT NULL,
                    total_return FLOAT NOT NULL,
                    max_drawdown FLOAT NOT NULL,
                    equity_curve TEXT,
                    summary TEXT
                )
                """
            )
        )
        connection.execute(
            sa.text(
                "CREATE INDEX ix_strategy_backtests_strategy_ran_at "
                "ON strategy_backtests(strategy_id, ran_at)"
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO strategies (
                    id, name, strategy_type, version, parameters, enabled, tags,
                    metadata, source_format, source, derived_from, status,
                    last_error, last_backtest, created_at, updated_at
                ) VALUES
                (1, 'Legacy One', 'static', 1, '{}', 1, '[]', '{"strategy_id": 1}',
                 'python', 'code', NULL, 'PENDING', NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (2, 'Legacy Two', 'static', 1, '{}', 1, '[]', '{"strategy_id": 2}',
                 'python', 'code', 1, 'ACTIVE', NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO strategy_versions (
                    strategy_id, version, name, strategy_type, parameters,
                    metadata, tags, source_format, source, derived_from, created_at
                ) VALUES
                (1, 1, 'Legacy One', 'static', '{}', '{"strategy_id": 1}', '[]', 'python', 'code', NULL, CURRENT_TIMESTAMP),
                (2, 1, 'Legacy Two', 'static', '{}', '{"strategy_id": 2}', '[]', 'python', 'code', 1, CURRENT_TIMESTAMP)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO strategy_executions (
                    strategy_id, order_id, status, broker, venue, symbol, side,
                    quantity, filled_quantity, avg_price, submitted_at, payload, created_at
                ) VALUES
                (1, 'order-1', 'filled', 'paper', 'binance.spot', 'BTCUSDT', 'buy',
                 1.0, 1.0, 25000.0, CURRENT_TIMESTAMP, '{"ok": true}', CURRENT_TIMESTAMP),
                (2, 'order-2', 'filled', 'paper', 'binance.spot', 'BTCUSDT', 'buy',
                 1.0, 1.0, 25000.0, CURRENT_TIMESTAMP, '{"ok": true}', CURRENT_TIMESTAMP)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO strategy_backtests (
                    strategy_id, ran_at, initial_balance, profit_loss, total_return,
                    max_drawdown, equity_curve, summary
                ) VALUES
                (1, CURRENT_TIMESTAMP, 10000.0, 500.0, 0.05, 0.02, '[1,2,3]', '{"result": "ok"}'),
                (2, CURRENT_TIMESTAMP, 10000.0, -100.0, -0.01, 0.03, '[1,2,3]', '{"result": "ok"}')
                """
            )
        )

        context = MigrationContext.configure(connection)
        operations = Operations(context)
        had_original_proxy = hasattr(alembic_op, "_proxy")
        original_proxy = getattr(alembic_op, "_proxy", None)
        alembic_op._proxy = operations  # type: ignore[attr-defined]
        try:
            for module_path in (
                "infra.migrations.versions.0a9b90ff8c8f_convert_strategy_ids_to_strings",
                "infra.migrations.versions.4d3f2c1f5b1a_retype_strategy_identifiers",
            ):
                migration = importlib.import_module(module_path)
                migration.upgrade()
        finally:
            if had_original_proxy:
                alembic_op._proxy = original_proxy  # type: ignore[attr-defined]
            else:
                delattr(alembic_op, "_proxy")

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    repository = StrategyRepository(session_factory)
    records = sorted(repository.list(), key=lambda record: record.id)
    assert [record.id for record in records] == ["1", "2"]
    assert repository.get("2").derived_from == "1"
    assert repository.get("1").metadata["strategy_id"] == "1"
