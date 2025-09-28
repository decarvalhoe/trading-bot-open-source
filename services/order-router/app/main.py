"""Order router service centralising broker connectivity."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from libs.entitlements import install_entitlements_middleware
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from providers.limits import build_plan, get_pair_limit, iter_supported_pairs
from schemas.market import ExecutionPlan, ExecutionReport, OrderRequest

from .brokers import BinanceAdapter, BrokerAdapter, IBKRAdapter
from .risk_rules import MaxDailyLossRule, MaxNotionalRule, RiskEngine


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

    def __init__(self, adapters: List[BrokerAdapter], risk_engine: RiskEngine) -> None:
        self._adapters = {adapter.name: adapter for adapter in adapters}
        self._risk_engine = risk_engine
        self._orders_log: List[ExecutionReport] = []
        self._executions: List[ExecutionReport] = []
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

    def route_order(self, order: OrderRequest, context: Dict[str, float]) -> ExecutionReport:
        broker_name = order.broker
        if broker_name not in self._adapters:
            raise KeyError("Unknown broker")
        adapter = self._adapters[broker_name]
        self._risk_engine.validate(order, context)
        price_reference = order.price or context.get("last_price", 0.0)
        notional = order.quantity * price_reference
        self._apply_daily_limit(notional)
        reference_price = price_reference if price_reference > 0 else 1.0
        response = adapter.place_order(order, reference_price=reference_price)
        with self._lock:
            self._orders_log.append(response)
            self._executions.extend(adapter.fetch_executions())
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


router = OrderRouter(
    adapters=[BinanceAdapter(), IBKRAdapter()],
    risk_engine=RiskEngine(
        [
            MaxNotionalRule({limit.symbol: limit.notional_limit() for limit in iter_supported_pairs()}),
            MaxDailyLossRule(max_loss=50_000.0),
        ]
    ),
)

configure_logging("order-router")

app = FastAPI(title="Order Router", version="0.1.0")
install_entitlements_middleware(app, required_capabilities=["can.route_orders"])
app.add_middleware(RequestContextMiddleware, service_name="order-router")
setup_metrics(app, service_name="order-router")


class OrderPayload(OrderRequest):
    """Request payload aligning with the shared order contract."""


class ExecutionPlanResponse(BaseModel):
    plan: ExecutionPlan


class CancelPayload(BaseModel):
    order_id: str


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
    context = {"daily_loss": 0.0, "last_price": payload.price or limit.reference_price}
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
