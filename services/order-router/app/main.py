"""Order router service centralising broker connectivity."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from libs.entitlements import install_entitlements_middleware

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
        self._orders_log: List[Dict[str, float]] = []
        self._executions: List[Dict[str, float]] = []
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

    def route_order(self, order: Dict[str, Any], context: Dict[str, float]) -> Dict[str, Any]:
        broker_name = order.get("broker")
        if not broker_name or broker_name not in self._adapters:
            raise KeyError("Unknown broker")
        adapter = self._adapters[broker_name]
        self._risk_engine.validate(order, context)
        notional = order.get("quantity", 0.0) * order.get("price", context.get("last_price", 0.0))
        self._apply_daily_limit(notional)
        response = adapter.place_order(order)
        with self._lock:
            self._orders_log.append(response)
            self._executions.extend(adapter.fetch_executions())
        return response

    def cancel(self, broker: str, order_id: str) -> Dict[str, str]:
        if broker not in self._adapters:
            raise KeyError("Unknown broker")
        result = self._adapters[broker].cancel_order(order_id)
        with self._lock:
            self._orders_log.append({"order_id": order_id, "status": result["status"], "broker": broker})
        return result

    def orders_log(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._orders_log)

    def executions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._executions)


router = OrderRouter(
    adapters=[BinanceAdapter(), IBKRAdapter()],
    risk_engine=RiskEngine(
        [
            MaxNotionalRule({"BTCUSDT": 500_000.0, "AAPL": 250_000.0}),
            MaxDailyLossRule(max_loss=50_000.0),
        ]
    ),
)

app = FastAPI(title="Order Router", version="0.1.0")
install_entitlements_middleware(app, required_capabilities=["can.route_orders"])


class OrderPayload(BaseModel):
    broker: str
    symbol: str
    quantity: float = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0)
    estimated_loss: Optional[float] = None


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


@app.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderPayload, request: Request) -> Dict[str, Any]:
    entitlements = getattr(request.state, "entitlements", None)
    bypass = getattr(entitlements, "customer_id", None) == "anonymous"
    if entitlements and not bypass and not entitlements.has("can.route_orders"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing capability")
    context = {"daily_loss": 0.0, "last_price": payload.price or 0.0}
    try:
        result = router.route_order(payload.model_dump(), context)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return result


@app.post("/orders/{broker}/cancel")
def cancel_order(broker: str, payload: CancelPayload) -> Dict[str, str]:
    try:
        return router.cancel(broker, payload.order_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.get("/orders/log")
def get_orders_log() -> Dict[str, List[Dict[str, Any]]]:
    return {"orders": router.orders_log()}


@app.get("/executions")
def get_executions() -> Dict[str, List[Dict[str, Any]]]:
    return {"executions": router.executions()}


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
