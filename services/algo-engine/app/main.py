"""Algo engine service exposing a plugin oriented strategy registry."""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from libs.entitlements import install_entitlements_middleware
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from providers.limits import build_plan, get_pair_limit
from schemas.market import ExecutionPlan, ExecutionVenue, OrderRequest, OrderSide, OrderType, TimeInForce

from .orchestrator import Orchestrator
from .strategies import base  # noqa: F401 - ensures registry initialised
from .strategies.base import StrategyConfig, registry
from .strategies import gap_fill, orb  # noqa: F401 - register plugins


@dataclass
class StrategyRecord:
    id: str
    name: str
    strategy_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = False
    tags: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StrategyStore:
    """Thread-safe in-memory strategy catalogue."""

    def __init__(self) -> None:
        self._strategies: Dict[str, StrategyRecord] = {}
        self._lock = threading.Lock()

    def list(self) -> List[StrategyRecord]:
        with self._lock:
            return list(self._strategies.values())

    def get(self, strategy_id: str) -> StrategyRecord:
        with self._lock:
            try:
                return self._strategies[strategy_id]
            except KeyError as exc:
                raise KeyError("strategy not found") from exc

    def create(self, record: StrategyRecord) -> StrategyRecord:
        with self._lock:
            self._strategies[record.id] = record
            return record

    def update(self, strategy_id: str, **updates: Any) -> StrategyRecord:
        with self._lock:
            if strategy_id not in self._strategies:
                raise KeyError("strategy not found")
            for key, value in updates.items():
                if value is not None:
                    setattr(self._strategies[strategy_id], key, value)
            return self._strategies[strategy_id]

    def delete(self, strategy_id: str) -> None:
        with self._lock:
            if strategy_id not in self._strategies:
                raise KeyError("strategy not found")
            del self._strategies[strategy_id]

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._strategies.values() if s.enabled)


store = StrategyStore()
orchestrator = Orchestrator()

configure_logging("algo-engine")

app = FastAPI(title="Algo Engine", version="0.1.0")
install_entitlements_middleware(
    app,
    required_capabilities=["can.manage_strategies"],
)
app.add_middleware(RequestContextMiddleware, service_name="algo-engine")
setup_metrics(app, service_name="algo-engine")


class StrategyPayload(BaseModel):
    name: str
    strategy_type: str = Field(..., description="Registered strategy key")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False
    tags: List[str] = Field(default_factory=list)


class StrategyUpdatePayload(BaseModel):
    name: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    tags: Optional[List[str]] = None


class OrchestratorStatePayload(BaseModel):
    mode: Optional[str] = Field(default=None, pattern="^(paper|live)$")
    daily_trade_limit: Optional[int] = Field(default=None, ge=1)
    trades_submitted: Optional[int] = Field(default=None, ge=0)


class ExecutionIntent(BaseModel):
    broker: str
    venue: ExecutionVenue = ExecutionVenue.BINANCE_SPOT
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0)
    time_in_force: TimeInForce = TimeInForce.GTC
    estimated_loss: Optional[float] = None
    tags: List[str] = Field(default_factory=list)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/strategies")
def list_strategies(request: Request) -> Dict[str, Any]:
    entitlements = getattr(request.state, "entitlements", None)
    limit = entitlements.quota("max_active_strategies") if entitlements else None
    return {
        "items": [record.as_dict() for record in store.list()],
        "available": registry.available_strategies(),
        "active_limit": limit,
        "orchestrator_state": orchestrator.get_state().as_dict(),
    }


def _enforce_entitlements(request: Request, enabled: bool) -> None:
    if not enabled:
        return
    entitlements = getattr(request.state, "entitlements", None)
    limit = entitlements.quota("max_active_strategies") if entitlements else None
    if limit is not None and store.active_count() >= limit:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active strategy limit reached")


@app.post("/strategies", status_code=status.HTTP_201_CREATED)
def create_strategy(payload: StrategyPayload, request: Request) -> Dict[str, Any]:
    if payload.strategy_type not in registry.available_strategies():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown strategy type")
    _enforce_entitlements(request, payload.enabled)

    config = StrategyConfig(
        name=payload.name,
        parameters=payload.parameters,
        enabled=payload.enabled,
        tags=payload.tags,
    )
    registry.create(payload.strategy_type, config)  # instantiation validates plugin
    record = StrategyRecord(
        id=str(uuid.uuid4()),
        name=payload.name,
        strategy_type=payload.strategy_type,
        parameters=payload.parameters,
        enabled=payload.enabled,
        tags=payload.tags,
    )
    store.create(record)
    return record.as_dict()


@app.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: str) -> Dict[str, Any]:
    try:
        record = store.get(strategy_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return record.as_dict()


@app.put("/strategies/{strategy_id}")
def update_strategy(strategy_id: str, payload: StrategyUpdatePayload, request: Request) -> Dict[str, Any]:
    try:
        existing = store.get(strategy_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    updates: Dict[str, Any] = payload.model_dump(exclude_unset=True)
    if "enabled" in updates:
        _enforce_entitlements(request, bool(updates["enabled"]))

    if "parameters" in updates:
        parameters = updates["parameters"] or {}
        StrategyConfig(
            name=updates.get("name", existing.name),
            parameters=parameters,
            enabled=updates.get("enabled", existing.enabled),
            tags=updates.get("tags", existing.tags),
        )
        registry.create(existing.strategy_type, StrategyConfig(name=existing.name, parameters=parameters))

    record = store.update(strategy_id, **updates)
    return record.as_dict()


@app.delete("/strategies/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy(strategy_id: str) -> None:
    try:
        store.delete(strategy_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")


@app.get("/state")
def get_state() -> Dict[str, Any]:
    return orchestrator.get_state().as_dict()


@app.put("/state")
def update_state(payload: OrchestratorStatePayload) -> Dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("mode") is not None:
        orchestrator.set_mode(updates["mode"])
    if updates.get("daily_trade_limit") is not None or updates.get("trades_submitted") is not None:
        orchestrator.update_daily_limit(
            limit=updates.get("daily_trade_limit"),
            trades_submitted=updates.get("trades_submitted"),
        )
    return orchestrator.get_state().as_dict()


@app.post("/mvp/plan", response_model=ExecutionPlan)
def build_execution_plan(payload: ExecutionIntent) -> ExecutionPlan:
    limit = get_pair_limit(payload.venue, payload.symbol)
    if limit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported trading pair")
    if payload.quantity > limit.max_order_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order size exceeds sandbox limit")
    order = OrderRequest(
        broker=payload.broker,
        venue=payload.venue,
        symbol=payload.symbol,
        side=payload.side,
        order_type=payload.order_type,
        quantity=payload.quantity,
        price=payload.price,
        time_in_force=payload.time_in_force,
        estimated_loss=payload.estimated_loss,
        tags=payload.tags,
    )
    return build_plan(order)


__all__ = ["app"]
