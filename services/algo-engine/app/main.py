"""Algo engine service exposing a plugin oriented strategy registry."""
from __future__ import annotations

import logging
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

ASSISTANT_SRC = Path(__file__).resolve().parents[2] / "ai-strategy-assistant" / "src"
if ASSISTANT_SRC.exists():
    sys.path.insert(0, str(ASSISTANT_SRC))

from ai_strategy_assistant import (  # noqa: E402
    AIStrategyAssistant,
    StrategyGenerationError,
    StrategyGenerationRequest,
)
from ai_strategy_assistant.schemas import StrategyFormat  # noqa: E402

from libs.entitlements import install_entitlements_middleware
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from providers.limits import build_plan, get_pair_limit
from schemas.market import ExecutionPlan, ExecutionVenue, OrderRequest, OrderSide, OrderType, TimeInForce

from .backtest import Backtester
from .declarative import DeclarativeStrategyError, load_declarative_definition
from .order_router_client import OrderRouterClient
from .orchestrator import Orchestrator
from .reports_client import ReportsPublisher
from .strategies import base  # noqa: F401 - ensures registry initialised
from .strategies.base import StrategyConfig, registry
from .strategies import declarative, gap_fill, orb  # noqa: F401 - register plugins


logger = logging.getLogger(__name__)


class StrategyStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"


@dataclass
class StrategyRecord:
    id: str
    name: str
    strategy_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = False
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_format: Optional[str] = None
    source: Optional[str] = None
    last_backtest: Optional[Dict[str, Any]] = None
    status: StrategyStatus = StrategyStatus.PENDING
    last_error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class StrategyStore:
    """Thread-safe in-memory strategy catalogue."""

    def __init__(self) -> None:
        self._strategies: Dict[str, StrategyRecord] = {}
        self._lock = threading.Lock()
        self._allowed_transitions: Dict[StrategyStatus, List[StrategyStatus]] = {
            StrategyStatus.PENDING: [StrategyStatus.ACTIVE, StrategyStatus.ERROR],
            StrategyStatus.ACTIVE: [StrategyStatus.ERROR],
            StrategyStatus.ERROR: [StrategyStatus.ACTIVE],
        }

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
            record = self._strategies[strategy_id]
            pending_updates = dict(updates)

            status_update = pending_updates.pop("status", None)
            error_update = pending_updates.pop("last_error", None)

            if status_update is not None:
                if not isinstance(status_update, StrategyStatus):
                    status_update = StrategyStatus(status_update)
                current_status = record.status
                if status_update != current_status:
                    allowed = self._allowed_transitions.get(current_status, [])
                    if status_update not in allowed:
                        raise ValueError(
                            f"Invalid status transition from {current_status.value} to {status_update.value}"
                        )
                record.status = status_update
                if status_update == StrategyStatus.ERROR:
                    if error_update is not None:
                        record.last_error = error_update
                elif status_update == StrategyStatus.ACTIVE:
                    record.last_error = None

            if error_update is not None and status_update is None:
                record.last_error = error_update

            for key, value in pending_updates.items():
                if value is not None:
                    setattr(record, key, value)
            return record

    def delete(self, strategy_id: str) -> None:
        with self._lock:
            if strategy_id not in self._strategies:
                raise KeyError("strategy not found")
            del self._strategies[strategy_id]

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._strategies.values() if s.enabled)


store = StrategyStore()


def _handle_strategy_execution_error(strategy: base.StrategyBase, error: Exception) -> None:
    logger.error(
        "Strategy %s routing failure, transitioning to ERROR: %s",
        strategy.config.name,
        error,
    )
    metadata = strategy.config.metadata or {}
    strategy_id = metadata.get("strategy_id") if isinstance(metadata, dict) else None
    if not strategy_id:
        logger.warning(
            "Strategy %s missing 'strategy_id' metadata; unable to persist ERROR state",
            strategy.config.name,
        )
        return
    try:
        store.update(strategy_id, status=StrategyStatus.ERROR, last_error=str(error))
    except KeyError:
        logger.warning(
            "Strategy id %s not found in store when handling routing failure",
            strategy_id,
        )
    except ValueError as exc:
        logger.warning(
            "Failed to update status for strategy %s after routing failure: %s",
            strategy_id,
            exc,
        )


order_router_client = OrderRouterClient()
orchestrator = Orchestrator(
    order_router_client=order_router_client,
    on_strategy_error=_handle_strategy_execution_error,
)
backtester = Backtester()
reports_publisher = ReportsPublisher()
ai_assistant = AIStrategyAssistant()

configure_logging("algo-engine")

app = FastAPI(title="Algo Engine", version="0.1.0")
install_entitlements_middleware(
    app,
    required_capabilities=["can.manage_strategies"],
)
app.add_middleware(RequestContextMiddleware, service_name="algo-engine")
setup_metrics(app, service_name="algo-engine")


@app.on_event("shutdown")
async def _shutdown_clients() -> None:
    await order_router_client.aclose()
    reports_publisher.close()


class StrategyPayload(BaseModel):
    name: str
    strategy_type: str = Field(..., description="Registered strategy key")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source_format: Optional[str] = Field(default=None, pattern="^(yaml|python)$")
    source: Optional[str] = None


class StrategyUpdatePayload(BaseModel):
    name: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    source_format: Optional[str] = Field(default=None, pattern="^(yaml|python)$")
    source: Optional[str] = None
    status: Optional[StrategyStatus] = None
    last_error: Optional[str] = None


class StrategyStatusUpdatePayload(BaseModel):
    status: StrategyStatus
    error: Optional[str] = Field(default=None, description="Latest error message when status is ERROR")


class OrchestratorStatePayload(BaseModel):
    mode: Optional[str] = Field(default=None, pattern="^(paper|live|simulation)$")
    daily_trade_limit: Optional[int] = Field(default=None, ge=1)
    trades_submitted: Optional[int] = Field(default=None, ge=0)


class StrategyImportPayload(BaseModel):
    name: Optional[str] = None
    format: Literal["yaml", "python"]
    content: str
    enabled: bool = False
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class StrategyGenerationPayload(BaseModel):
    prompt: str = Field(..., description="Intent en langage naturel")
    preferred_format: Literal["yaml", "python", "both"] = "yaml"
    risk_profile: Optional[str] = Field(default=None)
    timeframe: Optional[str] = Field(default=None)
    capital: Optional[str] = Field(default=None)
    indicators: List[str] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None)


class StrategyDraftPreview(BaseModel):
    summary: str
    yaml: Optional[str] = None
    python: Optional[str] = None
    indicators: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BacktestPayload(BaseModel):
    market_data: List[Dict[str, Any]]
    initial_balance: float = Field(default=10_000.0, gt=0)


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
        metadata=payload.metadata,
    )
    registry.create(payload.strategy_type, config)  # instantiation validates plugin
    record = StrategyRecord(
        id=str(uuid.uuid4()),
        name=payload.name,
        strategy_type=payload.strategy_type,
        parameters=payload.parameters,
        enabled=payload.enabled,
        tags=payload.tags,
        metadata=payload.metadata,
        source_format=payload.source_format,
        source=payload.source,
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


@app.post("/strategies/import", status_code=status.HTTP_201_CREATED)
def import_strategy(payload: StrategyImportPayload, request: Request) -> Dict[str, Any]:
    _enforce_entitlements(request, payload.enabled)
    try:
        definition = load_declarative_definition(payload.content, payload.format)
    except DeclarativeStrategyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    name = payload.name or definition.name
    base_parameters = definition.to_parameters()
    parameters = {**base_parameters, **payload.parameters}
    parameters["definition"] = base_parameters["definition"]
    metadata = {**definition.metadata, **payload.metadata}

    config = StrategyConfig(
        name=name,
        parameters=parameters,
        enabled=payload.enabled,
        tags=payload.tags,
        metadata=metadata,
    )
    try:
        registry.create("declarative", config)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record = StrategyRecord(
        id=str(uuid.uuid4()),
        name=name,
        strategy_type="declarative",
        parameters=parameters,
        enabled=payload.enabled,
        tags=payload.tags,
        metadata=metadata,
        source_format=payload.format,
        source=payload.content,
    )
    store.create(record)
    return record.as_dict()


@app.post("/strategies/generate")
def generate_strategy_from_prompt(payload: StrategyGenerationPayload) -> Dict[str, Any]:
    try:
        assistant_request = StrategyGenerationRequest(
            prompt=payload.prompt,
            preferred_format=StrategyFormat(payload.preferred_format),
            risk_profile=payload.risk_profile,
            timeframe=payload.timeframe,
            capital=payload.capital,
            indicators=payload.indicators,
            notes=payload.notes,
        )
        result = ai_assistant.generate(assistant_request)
    except StrategyGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    draft = result.draft
    preview = StrategyDraftPreview(
        summary=draft.summary,
        yaml=draft.yaml_strategy,
        python=draft.python_strategy,
        indicators=draft.indicators,
        warnings=draft.warnings,
        metadata=draft.metadata,
    )
    return {
        "draft": preview.model_dump(),
        "request": payload.model_dump(),
    }


@app.put("/strategies/{strategy_id}")
def update_strategy(strategy_id: str, payload: StrategyUpdatePayload, request: Request) -> Dict[str, Any]:
    try:
        existing = store.get(strategy_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    updates: Dict[str, Any] = payload.model_dump(exclude_unset=True)
    if "enabled" in updates:
        _enforce_entitlements(request, bool(updates["enabled"]))

    if any(key in updates for key in ("parameters", "metadata", "name", "tags", "enabled")):
        parameters = updates.get("parameters", existing.parameters) or {}
        metadata = updates.get("metadata", existing.metadata) or {}
        config = StrategyConfig(
            name=updates.get("name", existing.name),
            parameters=parameters,
            enabled=updates.get("enabled", existing.enabled),
            tags=updates.get("tags", existing.tags),
            metadata=metadata,
        )
        registry.create(existing.strategy_type, config)

    try:
        record = store.update(strategy_id, **updates)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return record.as_dict()


@app.post("/strategies/{strategy_id}/status")
def transition_strategy_status(strategy_id: str, payload: StrategyStatusUpdatePayload) -> Dict[str, Any]:
    try:
        store.get(strategy_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    try:
        record = store.update(strategy_id, status=payload.status, last_error=payload.error)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return record.as_dict()


@app.delete("/strategies/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy(strategy_id: str) -> None:
    try:
        store.delete(strategy_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")


@app.get("/strategies/{strategy_id}/export")
def export_strategy(strategy_id: str, fmt: Literal["yaml", "python"] = Query("yaml")) -> Dict[str, Any]:
    try:
        record = store.get(strategy_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if record.source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy source unavailable")
    if record.source_format and record.source_format != fmt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Strategy stored as {record.source_format}; request the matching format",
        )

    return {
        "id": record.id,
        "name": record.name,
        "format": record.source_format or fmt,
        "content": record.source,
    }


@app.post("/strategies/{strategy_id}/backtest")
def backtest_strategy(strategy_id: str, payload: BacktestPayload) -> Dict[str, Any]:
    try:
        record = store.get(strategy_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    try:
        strategy = registry.create(
            record.strategy_type,
            StrategyConfig(
                name=record.name,
                parameters=record.parameters,
                enabled=record.enabled,
                tags=record.tags,
                metadata=record.metadata,
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        summary = backtester.run(
            strategy,
            payload.market_data,
            initial_balance=payload.initial_balance,
        )
    except Exception as exc:  # pragma: no cover - simulation errors surface to API
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    summary_dict = summary.as_dict()
    store.update(strategy_id, last_backtest=summary_dict)
    publish_payload: Dict[str, Any] = {
        "strategy_id": strategy_id,
        "strategy_name": record.name,
        "strategy_type": record.strategy_type,
        "account": (record.metadata or {}).get("account"),
        "symbol": (
            record.parameters.get("symbol")
            if isinstance(record.parameters, dict)
            else None
        )
        or (
            (record.metadata or {}).get("symbol")
            if isinstance(record.metadata, dict)
            else None
        ),
        "initial_balance": payload.initial_balance,
        "parameters": record.parameters,
        "tags": record.tags,
        "metadata": record.metadata,
        "summary": summary_dict,
    }
    reports_publisher.publish_backtest(publish_payload)
    orchestrator.record_simulation(summary.as_dict())
    return summary.as_dict()


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
