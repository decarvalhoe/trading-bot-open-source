"""Order router service centralising broker connectivity."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from libs.entitlements import install_entitlements_middleware
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from providers.limits import build_plan, get_pair_limit, iter_supported_pairs
from schemas.market import ExecutionPlan, ExecutionReport, OrderRequest

from .brokers import BinanceAdapter, BrokerAdapter, IBKRAdapter
from .risk_rules import (
    DynamicLimitRule,
    DynamicLimitStore,
    MaxDailyLossRule,
    MaxNotionalRule,
    RiskEngine,
    RiskLevel,
    RiskSignal,
    StopLossRule,
    SymbolLimit,
)


logger = logging.getLogger("order-router.risk")


@dataclass
class RouterState:
    mode: str = "paper"
    daily_notional_limit: float = 1_000_000.0
    notional_routed: float = 0.0

    def as_dict(self) -> Dict[str, float | str]:
        return {
            "mode": self.mode,
            "daily_notional_limit": self.daily_notional_limit,
            "notional_routed": self.notional_routed,
        }


class OrderRouter:
    """Coordinate brokers, risk and logging."""

    def __init__(
        self,
        adapters: List[BrokerAdapter],
        risk_engine: RiskEngine,
        limit_store: DynamicLimitStore,
    ) -> None:
        self._adapters = {adapter.name: adapter for adapter in adapters}
        self._risk_engine = risk_engine
        self._limit_store = limit_store
        self._orders_log: List[ExecutionReport] = []
        self._executions: List[ExecutionReport] = []
        self._risk_alerts: List[RiskSignal] = []
        self._lock = threading.RLock()
        self._state = RouterState()

    def list_brokers(self) -> List[str]:
        return sorted(self._adapters.keys())

    def get_state(self) -> RouterState:
        with self._lock:
            return RouterState(**self._state.__dict__)

    def update_state(self, *, mode: Optional[str] = None, limit: Optional[float] = None) -> RouterState:
        with self._lock:
            if mode is not None:
                if mode not in {"paper", "live"}:
                    raise ValueError("mode must be 'paper' or 'live'")
                self._state.mode = mode
            if limit is not None:
                if limit <= 0:
                    raise ValueError("daily_notional_limit must be positive")
                self._state.daily_notional_limit = float(limit)
            return self.get_state()

    def _apply_daily_limit(self, notional: float) -> None:
        with self._lock:
            projected = self._state.notional_routed + notional
            if projected > self._state.daily_notional_limit:
                raise RuntimeError("Daily notional limit exceeded")
            self._state.notional_routed = projected

    def route_order(self, order: OrderRequest, context: Dict[str, Any]) -> ExecutionReport:
        broker_name = order.broker
        if broker_name not in self._adapters:
            raise KeyError("Unknown broker")
        adapter = self._adapters[broker_name]
        account_id = str(context.get("account_id") or "default")
        signals = self._risk_engine.evaluate(order, context)
        locks = [signal for signal in signals if signal.level is RiskLevel.LOCK]
        if locks:
            raise ValueError(locks[0].message)
        alerts = [signal for signal in signals if signal.level is RiskLevel.ALERT]
        if alerts:
            self._record_alerts(alerts)

        price_reference = float(order.price or context.get("last_price") or 0.0)
        if price_reference <= 0:
            price_reference = 1.0
        notional = abs(order.quantity) * price_reference
        self._apply_daily_limit(notional)
        response = adapter.place_order(order, reference_price=price_reference)
        with self._lock:
            self._orders_log.append(response)
            self._executions.extend(adapter.fetch_executions())
        self._risk_engine.register_execution(order, account_id, price_reference)
        return response

    def cancel(self, broker: str, order_id: str) -> ExecutionReport:
        if broker not in self._adapters:
            raise KeyError("Unknown broker")
        result = self._adapters[broker].cancel_order(order_id)
        with self._lock:
            self._orders_log.append(result)
        return result

    def orders_log(self) -> List[ExecutionReport]:
        with self._lock:
            return list(self._orders_log)

    def executions(self) -> List[ExecutionReport]:
        with self._lock:
            return list(self._executions)

    def _record_alerts(self, alerts: List[RiskSignal]) -> None:
        if not alerts:
            return
        with self._lock:
            self._risk_alerts.extend(alerts)
        for signal in alerts:
            logger.warning(
                "Risk alert triggered - %s: %s",
                signal.rule_id,
                signal.message,
                extra={"metadata": signal.metadata},
            )

    def risk_alerts(self) -> List[RiskSignal]:
        with self._lock:
            return list(self._risk_alerts)

    def set_stop_loss(self, account_id: str, threshold: float) -> None:
        self._limit_store.set_stop_loss(account_id, threshold)


_supported_limits = list(iter_supported_pairs())
_symbol_limits = {
    limit.symbol: SymbolLimit(max_position=limit.max_position, max_notional=limit.notional_limit())
    for limit in _supported_limits
}
_notional_limits = {limit.symbol: limit.notional_limit() for limit in _supported_limits}
_limit_store = DynamicLimitStore(_symbol_limits)
_limit_store.set_stop_loss("default", 50_000.0)

router = OrderRouter(
    adapters=[BinanceAdapter(), IBKRAdapter()],
    risk_engine=RiskEngine(
        [
            DynamicLimitRule(_limit_store),
            StopLossRule(_limit_store, default_threshold=50_000.0),
            MaxDailyLossRule(max_loss=50_000.0),
            MaxNotionalRule(_notional_limits),
        ]
    ),
    limit_store=_limit_store,
)

configure_logging("order-router")

app = FastAPI(title="Order Router", version="0.1.0")
install_entitlements_middleware(app, required_capabilities=["can.route_orders"])
app.add_middleware(RequestContextMiddleware, service_name="order-router")
setup_metrics(app, service_name="order-router")


class RiskOverrides(BaseModel):
    account_id: str = Field(default="default", min_length=1, max_length=64)
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    stop_loss: float | None = Field(default=None, gt=0)


class OrderPayload(OrderRequest):
    """Request payload aligning with the shared order contract."""

    account_id: str | None = Field(default=None, min_length=1, max_length=64)
    risk: RiskOverrides | None = None


class ExecutionPlanResponse(BaseModel):
    plan: ExecutionPlan


class CancelPayload(BaseModel):
    order_id: str


class RiskAlertResponse(BaseModel):
    rule_id: str
    level: RiskLevel
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StateUpdatePayload(BaseModel):
    mode: Optional[str] = Field(default=None, pattern="^(paper|live)$")
    daily_notional_limit: Optional[float] = Field(default=None, gt=0)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/brokers")
def list_brokers() -> Dict[str, List[str]]:
    return {"brokers": router.list_brokers()}


@app.post("/plans", response_model=ExecutionPlanResponse)
def preview_execution_plan(payload: OrderPayload) -> ExecutionPlanResponse:
    limit = get_pair_limit(payload.venue, payload.symbol)
    if limit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported trading pair")
    if payload.quantity > limit.max_order_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order size exceeds sandbox limit")
    return ExecutionPlanResponse(plan=build_plan(payload))


@app.post("/orders", response_model=ExecutionReport, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderPayload, request: Request) -> ExecutionReport:
    entitlements = getattr(request.state, "entitlements", None)
    bypass = getattr(entitlements, "customer_id", None) == "anonymous"
    if entitlements and not bypass and not entitlements.has("can.route_orders"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing capability")
    limit = get_pair_limit(payload.venue, payload.symbol)
    if limit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported trading pair")
    if payload.quantity > limit.max_order_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order size exceeds sandbox limit")
    risk_payload = payload.risk.model_dump(exclude_unset=True) if payload.risk else {}
    account_id = payload.account_id or risk_payload.get("account_id") or "default"
    risk_payload["account_id"] = account_id
    risk_overrides = RiskOverrides(**risk_payload)
    if risk_overrides.stop_loss:
        router.set_stop_loss(risk_overrides.account_id, risk_overrides.stop_loss)
    context: Dict[str, Any] = {
        "daily_loss": 0.0,
        "last_price": payload.price or limit.reference_price,
        "account_id": risk_overrides.account_id,
        "realized_pnl": risk_overrides.realized_pnl or 0.0,
        "unrealized_pnl": risk_overrides.unrealized_pnl or 0.0,
        "stop_loss": risk_overrides.stop_loss,
    }
    try:
        result = router.route_order(payload, context)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return result


@app.post("/orders/{broker}/cancel", response_model=ExecutionReport)
def cancel_order(broker: str, payload: CancelPayload) -> ExecutionReport:
    try:
        return router.cancel(broker, payload.order_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.get("/orders/log", response_model=List[ExecutionReport])
def get_orders_log() -> List[ExecutionReport]:
    return router.orders_log()


@app.get("/executions", response_model=List[ExecutionReport])
def get_executions() -> List[ExecutionReport]:
    return router.executions()


@app.get("/risk/alerts", response_model=List[RiskAlertResponse])
def get_risk_alerts() -> List[RiskAlertResponse]:
    return [
        RiskAlertResponse(
            rule_id=alert.rule_id,
            level=alert.level,
            message=alert.message,
            metadata=alert.metadata,
        )
        for alert in router.risk_alerts()
    ]


@app.get("/state")
def get_state() -> Dict[str, float | str]:
    return router.get_state().as_dict()


@app.put("/state")
def update_state(payload: StateUpdatePayload) -> Dict[str, float | str]:
    data = payload.model_dump(exclude_unset=True)
    try:
        state = router.update_state(
            mode=data.get("mode"),
            limit=data.get("daily_notional_limit"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return state.as_dict()


__all__ = ["app", "router"]
