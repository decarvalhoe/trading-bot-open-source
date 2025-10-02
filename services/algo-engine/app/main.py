"""Algo engine service exposing a plugin oriented strategy registry."""
from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

ASSISTANT_SRC = Path(__file__).resolve().parents[2] / "ai-strategy-assistant" / "src"
ASSISTANT_ENV_FLAG = os.getenv("AI_ASSISTANT_ENABLED", "true").lower()
ASSISTANT_FEATURE_ENABLED = ASSISTANT_ENV_FLAG not in {"0", "false", "no", "off"}
ASSISTANT_AVAILABLE = False

if ASSISTANT_FEATURE_ENABLED and ASSISTANT_SRC.exists():
    sys.path.insert(0, str(ASSISTANT_SRC))
    try:
        from ai_strategy_assistant import (  # noqa: E402
            AIStrategyAssistant,
            StrategyGenerationError,
            StrategyGenerationRequest,
        )
        from ai_strategy_assistant.schemas import StrategyFormat  # noqa: E402
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - optional dependency
        logging.getLogger(__name__).warning(
            "AI strategy assistant unavailable: %s", exc
        )
        AIStrategyAssistant = None  # type: ignore[assignment]
        StrategyGenerationError = RuntimeError  # type: ignore[assignment]
        StrategyGenerationRequest = None  # type: ignore[assignment]
        StrategyFormat = None  # type: ignore[assignment]
    else:
        ASSISTANT_AVAILABLE = True
else:
    if not ASSISTANT_FEATURE_ENABLED:
        logging.getLogger(__name__).info(
            "AI strategy assistant disabled via AI_ASSISTANT_ENABLED environment flag"
        )
    AIStrategyAssistant = None  # type: ignore[assignment]
    StrategyGenerationError = RuntimeError  # type: ignore[assignment]
    StrategyGenerationRequest = None  # type: ignore[assignment]
    StrategyFormat = None  # type: ignore[assignment]

from libs.db.db import SessionLocal
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
from .repository import StrategyRecord, StrategyRepository, StrategyStatus
from .strategies import base  # noqa: F401 - ensures registry initialised
from .strategies.base import StrategyConfig, registry
from .strategies import declarative, gap_fill, orb  # noqa: F401 - register plugins


logger = logging.getLogger(__name__)

ASSISTANT_UNAVAILABLE_DETAIL = (
    "AI strategy assistant is disabled or unavailable. "
    "Install optional dependencies from services/ai-strategy-assistant and set "
    "AI_ASSISTANT_ENABLED=1 to enable the feature."
)


if ASSISTANT_AVAILABLE and "AIStrategyAssistant" in globals() and AIStrategyAssistant:
    logger.info("AI strategy assistant enabled")
    ai_assistant = AIStrategyAssistant()
else:
    if ASSISTANT_FEATURE_ENABLED and not ASSISTANT_AVAILABLE:
        logger.warning("AI strategy assistant dependencies missing; feature disabled")
    ai_assistant = None

strategy_repository = StrategyRepository(SessionLocal)


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
        strategy_repository.update(
            strategy_id, status=StrategyStatus.ERROR, last_error=str(error)
        )
    except KeyError:
        logger.warning(
            "Strategy id %s not found in repository when handling routing failure",
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
    strategy_repository=strategy_repository,
)
try:
    orchestrator.restore_recent_executions(
        strategy_repository.get_recent_executions(
            limit=orchestrator.execution_history_limit
        )
    )
except Exception:
    logger.exception("Unable to restore execution history from repository")
backtester = Backtester()
reports_publisher = ReportsPublisher()

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
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
        "items": [record.as_dict() for record in strategy_repository.list()],
        "available": registry.available_strategies(),
        "active_limit": limit,
        "orchestrator_state": orchestrator.get_state().as_dict(),
    }


def _enforce_entitlements(request: Request, enabled: bool) -> None:
    if not enabled:
        return
    entitlements = getattr(request.state, "entitlements", None)
    limit = entitlements.quota("max_active_strategies") if entitlements else None
    if limit is not None and strategy_repository.active_count() >= limit:
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
    strategy_repository.create(record)
    return record.as_dict()


@app.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: str) -> Dict[str, Any]:
    try:
        record = strategy_repository.get(strategy_id)
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
    strategy_repository.create(record)
    return record.as_dict()


@app.post("/strategies/generate")
def generate_strategy_from_prompt(payload: StrategyGenerationPayload) -> Dict[str, Any]:
    if (
        ai_assistant is None
        or not ASSISTANT_AVAILABLE
        or StrategyGenerationRequest is None
        or StrategyFormat is None
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ASSISTANT_UNAVAILABLE_DETAIL,
        )
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
        existing = strategy_repository.get(strategy_id)
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
        record = strategy_repository.update(strategy_id, **updates)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return record.as_dict()


@app.post("/strategies/{strategy_id}/status")
def transition_strategy_status(strategy_id: str, payload: StrategyStatusUpdatePayload) -> Dict[str, Any]:
    try:
        strategy_repository.get(strategy_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    try:
        record = strategy_repository.update(
            strategy_id, status=payload.status, last_error=payload.error
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return record.as_dict()


@app.delete("/strategies/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy(strategy_id: str) -> None:
    try:
        strategy_repository.delete(strategy_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")


@app.get("/strategies/{strategy_id}/export")
def export_strategy(strategy_id: str, fmt: Literal["yaml", "python"] = Query("yaml")) -> Dict[str, Any]:
    try:
        record = strategy_repository.get(strategy_id)
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
        record = strategy_repository.get(strategy_id)
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
    timestamp = datetime.now(timezone.utc)
    summary_dict["metadata"] = payload.metadata or {}
    summary_dict["ran_at"] = timestamp.isoformat()
    strategy_repository.update(strategy_id, last_backtest=summary_dict)
    strategy_repository.record_backtest(
        strategy_id,
        summary_dict,
        ran_at=timestamp,
    )
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


@app.get("/strategies/{strategy_id}/backtest/ui")
def get_backtest_ui_metrics(strategy_id: str) -> Dict[str, Any]:
    """Expose the latest backtest metrics optimised for UI consumption."""

    try:
        record = strategy_repository.get(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found") from exc

    if not record.last_backtest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No backtest available")

    summary = dict(record.last_backtest)
    equity_curve = summary.get("equity_curve")
    if not isinstance(equity_curve, list):
        equity_curve = []
    return {
        "strategy_id": record.id,
        "strategy_name": record.name,
        "equity_curve": equity_curve,
        "pnl": summary.get("profit_loss", 0.0),
        "initial_balance": summary.get("initial_balance", 0.0),
        "drawdown": summary.get("max_drawdown", 0.0),
        "total_return": summary.get("total_return", 0.0),
        "metadata": summary.get("metadata", {}),
        "ran_at": summary.get("ran_at"),
    }


@app.get("/strategies/{strategy_id}/backtests")
def list_backtests(
    strategy_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> Dict[str, Any]:
    """Return paginated historical backtest summaries."""

    try:
        strategy_repository.get(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found") from exc

    offset = (page - 1) * page_size
    items, total = strategy_repository.get_backtests(
        strategy_id,
        limit=page_size,
        offset=offset,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


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


__all__ = [
    "app",
    "orchestrator",
    "strategy_repository",
    "StrategyRecord",
    "StrategyStatus",
]
