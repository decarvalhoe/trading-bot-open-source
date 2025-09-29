from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

import httpx
import pytest

from algo_engine.app.main import StrategyRecord, StrategyStatus, orchestrator, store
from algo_engine.app.order_router_client import OrderRouterClientError
from algo_engine.app.strategies.base import StrategyBase, StrategyConfig
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
    mock_order_router: Any,
) -> None:
    """Ensure orchestrator routes signals, updates state and handles failures."""

    strategy_id = str(uuid4())
    record = store.create(
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

    reports = asyncio.run(orchestrator.execute_strategy(strategy=strategy, market_state={"emit": True}))
    assert len(reports) == 1
    assert reports[0].order_id == "order-success"
    assert mock_order_router.requests and mock_order_router.requests[0].url.path == "/orders"

    state = orchestrator.get_state()
    assert state.trades_submitted == 1
    assert state.recent_executions
    assert state.recent_executions[0]["order_id"] == "order-success"

    updated = store.update(strategy_id, status=StrategyStatus.ACTIVE)
    assert updated.status is StrategyStatus.ACTIVE
    assert updated.last_error is None

    orchestrator.update_daily_limit(trades_submitted=0)
    orchestrator._state.recent_executions.clear()  # type: ignore[attr-defined]
    mock_order_router.reset()
    failure_id = str(uuid4())
    failing_record = store.create(
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

    stored_failure = store.get(failure_id)
    assert stored_failure.status is StrategyStatus.ERROR
    assert stored_failure.last_error

    # Ensure PENDING strategy without emitted signals remains untouched
    idle_id = str(uuid4())
    idle_record = store.create(
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
    assert store.get(idle_id).status is StrategyStatus.PENDING
    assert orchestrator.get_state().trades_submitted == 0
