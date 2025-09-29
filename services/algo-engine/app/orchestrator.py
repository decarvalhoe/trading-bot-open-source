"""Service level state orchestration helpers."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from schemas.order_router import ExecutionIntent, ExecutionReport

from .order_router_client import OrderRouterClient, OrderRouterClientError
from .strategies.base import StrategyBase


logger = logging.getLogger(__name__)


@dataclass
class OrchestratorState:
    mode: str = "paper"
    daily_trade_limit: int = 100
    trades_submitted: int = 0
    last_simulation: Dict[str, object] | None = None
    recent_executions: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "mode": self.mode,
            "daily_trade_limit": self.daily_trade_limit,
            "trades_submitted": self.trades_submitted,
            "last_simulation": self.last_simulation,
            "recent_executions": [dict(report) for report in self.recent_executions],
        }


class Orchestrator:
    """Mutable orchestrator shared by API endpoints."""

    def __init__(
        self,
        *,
        order_router_client: OrderRouterClient | None = None,
        on_strategy_error: Callable[[StrategyBase, Exception], None] | None = None,
    ) -> None:
        self._state = OrchestratorState()
        self._lock = threading.RLock()
        self._order_router_client = order_router_client
        self._max_execution_records = 50
        self._on_strategy_error = on_strategy_error

    def get_state(self) -> OrchestratorState:
        with self._lock:
            last_simulation = (
                dict(self._state.last_simulation) if self._state.last_simulation else None
            )
            recent_executions = [dict(report) for report in self._state.recent_executions]
            return OrchestratorState(
                mode=self._state.mode,
                daily_trade_limit=self._state.daily_trade_limit,
                trades_submitted=self._state.trades_submitted,
                last_simulation=last_simulation,
                recent_executions=recent_executions,
            )

    def set_mode(self, mode: str) -> OrchestratorState:
        if mode not in {"paper", "live", "simulation"}:
            raise ValueError("mode must be either 'paper', 'live' or 'simulation'")
        with self._lock:
            self._state.mode = mode
            return self.get_state()

    def update_daily_limit(self, *, limit: int | None = None, trades_submitted: int | None = None) -> OrchestratorState:
        with self._lock:
            if limit is not None:
                if limit <= 0:
                    raise ValueError("daily limit must be positive")
                self._state.daily_trade_limit = limit
            if trades_submitted is not None:
                if trades_submitted < 0:
                    raise ValueError("trades submitted must be non-negative")
                self._state.trades_submitted = trades_submitted
            return self.get_state()

    def can_submit_trade(self, *, quantity: int = 1) -> bool:
        with self._lock:
            return self._state.trades_submitted + quantity <= self._state.daily_trade_limit

    def register_submission(self, *, quantity: int = 1) -> OrchestratorState:
        with self._lock:
            if self._state.trades_submitted + quantity > self._state.daily_trade_limit:
                raise RuntimeError("daily trade limit exceeded")
            self._state.trades_submitted += quantity
            return self.get_state()

    def rollback_submission(self, *, quantity: int = 1) -> OrchestratorState:
        with self._lock:
            self._state.trades_submitted = max(0, self._state.trades_submitted - quantity)
            return self.get_state()

    def record_simulation(self, summary: Dict[str, object]) -> OrchestratorState:
        with self._lock:
            self._state.last_simulation = summary
            self._state.mode = "simulation"
            return self.get_state()

    def get_order_router_client(self) -> OrderRouterClient:
        client = self._order_router_client
        if client is None:
            raise RuntimeError("order router client is not configured")
        return client

    def set_order_router_client(self, client: OrderRouterClient) -> None:
        with self._lock:
            self._order_router_client = client

    async def execute_strategy(
        self,
        *,
        strategy: StrategyBase,
        market_state: Dict[str, Any],
    ) -> List[ExecutionReport]:
        """Generate orders for an active strategy and route them.

        The orchestrator enforces the daily trade limit before issuing orders and
        records the resulting execution reports into the shared state so that
        recent executions can be inspected via the API.
        """

        if not strategy.config.enabled:
            logger.debug("Skipping disabled strategy %s", strategy.config.name)
            return []

        signals = strategy.generate_signals(market_state)
        if not signals:
            return []

        client = self.get_order_router_client()
        reports: List[ExecutionReport] = []
        for signal in signals:
            try:
                intent = self._build_execution_intent(strategy, signal)
            except ValueError as exc:
                logger.warning(
                    "Invalid signal produced by strategy %s: %s", strategy.config.name, exc
                )
                continue

            with self._lock:
                if self._state.trades_submitted + 1 > self._state.daily_trade_limit:
                    logger.info("Daily trade limit reached, skipping further signals")
                    break
                self._state.trades_submitted += 1

            try:
                report = await client.submit_order(intent)
            except OrderRouterClientError as exc:
                with self._lock:
                    self._state.trades_submitted = max(0, self._state.trades_submitted - 1)
                logger.error(
                    "Failed to submit order for strategy %s: %s",
                    strategy.config.name,
                    exc,
                )
                handler = self._on_strategy_error
                if handler is not None:
                    try:
                        handler(strategy, exc)
                    except Exception:
                        logger.exception(
                            "Strategy error handler raised while processing failure for %s",
                            strategy.config.name,
                        )
                raise

            self._record_execution(report)
            reports.append(report)

        return reports

    def _build_execution_intent(
        self, strategy: StrategyBase, signal: Dict[str, Any]
    ) -> ExecutionIntent:
        metadata = strategy.config.metadata or {}
        defaults = dict(metadata.get("order_defaults", {}))
        payload: Dict[str, Any] = {**defaults, **signal}

        action = payload.pop("action", None)
        if action and "side" not in payload:
            payload["side"] = action

        size = payload.pop("size", None)
        if size is not None and "quantity" not in payload:
            payload["quantity"] = size

        if "order_type" not in payload:
            raise ValueError("order_type is required to build an execution intent")
        if "broker" not in payload:
            raise ValueError("broker is required to build an execution intent")
        if "symbol" not in payload:
            raise ValueError("symbol is required to build an execution intent")
        if "venue" not in payload:
            raise ValueError("venue is required to build an execution intent")
        if "side" not in payload:
            raise ValueError("side is required to build an execution intent")
        if "quantity" not in payload:
            raise ValueError("quantity is required to build an execution intent")

        return ExecutionIntent.model_validate(payload)

    def _record_execution(self, report: ExecutionReport) -> None:
        payload = report.model_dump(mode="json")
        with self._lock:
            self._state.recent_executions.append(payload)
            if len(self._state.recent_executions) > self._max_execution_records:
                del self._state.recent_executions[:-self._max_execution_records]


__all__ = ["Orchestrator", "OrchestratorState"]
