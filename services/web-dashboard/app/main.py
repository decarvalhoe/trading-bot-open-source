"""Minimal dashboard service for monitoring trading activity."""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, List, Literal, Optional
from urllib.parse import urljoin

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from libs.alert_events import AlertEventBase, AlertEventRepository

from .data import (
    ORDER_ROUTER_BASE_URL,
    ORDER_ROUTER_TIMEOUT_SECONDS,
    load_dashboard_context,
    load_portfolio_history,
)
from .order_router_client import OrderRouterClient, OrderRouterError
from .alerts_client import AlertsEngineClient, AlertsEngineError
from .schemas import Alert, AlertCreateRequest, AlertUpdateRequest
from .documentation import load_strategy_documentation
from .strategy_presets import STRATEGY_PRESETS, STRATEGY_PRESET_SUMMARIES
from pydantic import BaseModel, Field, ConfigDict
from schemas.order_router import PositionCloseRequest


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Web Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

STREAMING_BASE_URL = os.getenv("WEB_DASHBOARD_STREAMING_BASE_URL", "http://localhost:8001/")
STREAMING_ROOM_ID = os.getenv("WEB_DASHBOARD_STREAMING_ROOM_ID", "public-room")
STREAMING_VIEWER_ID = os.getenv("WEB_DASHBOARD_STREAMING_VIEWER_ID", "demo-viewer")
ALERT_ENGINE_BASE_URL = os.getenv("WEB_DASHBOARD_ALERT_ENGINE_URL", "http://alerts-engine:8000/")
ALERT_ENGINE_TIMEOUT = float(os.getenv("WEB_DASHBOARD_ALERT_ENGINE_TIMEOUT", "5.0"))
ALGO_ENGINE_BASE_URL = os.getenv("WEB_DASHBOARD_ALGO_ENGINE_URL", "http://algo-engine:8000/")
ALGO_ENGINE_TIMEOUT = float(os.getenv("WEB_DASHBOARD_ALGO_ENGINE_TIMEOUT", "5.0"))
AI_ASSISTANT_BASE_URL = os.getenv(
    "WEB_DASHBOARD_AI_ASSISTANT_URL",
    "http://ai-strategy-assistant:8085/",
)
AI_ASSISTANT_TIMEOUT = float(os.getenv("WEB_DASHBOARD_AI_ASSISTANT_TIMEOUT", "10.0"))

security = HTTPBearer(auto_error=False)


ALERT_EVENTS_DATABASE_URL = os.getenv(
    "WEB_DASHBOARD_ALERT_EVENTS_DATABASE_URL",
    os.getenv("ALERT_EVENTS_DATABASE_URL", "sqlite:///./alert_events.db"),
)

_alert_events_engine = create_engine(ALERT_EVENTS_DATABASE_URL, future=True)
AlertEventBase.metadata.create_all(bind=_alert_events_engine)
_alert_events_session_factory = sessionmaker(
    bind=_alert_events_engine, autocommit=False, autoflush=False, future=True
)
_alert_events_repository = AlertEventRepository()


def get_alert_events_session() -> Iterator[Session]:
    session = _alert_events_session_factory()
    try:
        yield session
    finally:
        session.close()


@lru_cache(maxsize=1)
def _alerts_client_factory() -> AlertsEngineClient:
    return AlertsEngineClient(base_url=ALERT_ENGINE_BASE_URL, timeout=ALERT_ENGINE_TIMEOUT)


def get_alerts_client() -> AlertsEngineClient:
    """Return a configured client for communicating with the alert engine."""

    return _alerts_client_factory()


def _handle_alert_engine_error(error: AlertsEngineError) -> None:
    status_code = error.status_code or status.HTTP_502_BAD_GATEWAY
    if status_code < 400 or status_code >= 600:
        status_code = status.HTTP_502_BAD_GATEWAY
    message = error.message or "Erreur du moteur d'alertes."
    raise HTTPException(status_code=status_code, detail=message)


def require_alerts_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    """Ensure alert management routes are protected by a bearer token when configured."""

    token = os.getenv("WEB_DASHBOARD_ALERTS_TOKEN")
    if not token:
        return
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise pour gérer les alertes.",
        )
    if credentials.credentials != token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Jeton d'authentification invalide.",
        )


@app.on_event("shutdown")
def shutdown_alerts_client() -> None:
    """Ensure HTTP resources opened for the alerts engine are properly released."""

    try:
        client = _alerts_client_factory()
    except Exception:  # pragma: no cover - defensive guard if instantiation fails
        return
    client.close()
    _alerts_client_factory.cache_clear()


class StrategySaveRequest(BaseModel):
    """Payload accepted by the strategy import endpoint."""

    name: str = Field(..., min_length=1)
    format: Literal["yaml", "python"]
    code: str = Field(..., min_length=1)


class StrategyGenerationRequestPayload(BaseModel):
    """Relay prompt instructions to the AI assistant."""

    prompt: str = Field(..., min_length=3)
    preferred_format: Literal["yaml", "python", "both"] = "yaml"
    risk_profile: str | None = None
    timeframe: str | None = None
    capital: str | None = None
    indicators: list[str] = Field(default_factory=list)
    notes: str | None = None


class StrategyDraftPayload(BaseModel):
    """Subset of the AI assistant draft returned to the UI."""

    model_config = ConfigDict(populate_by_name=True)

    summary: str
    yaml: str | None = Field(default=None, alias="yaml_strategy")
    python: str | None = Field(default=None, alias="python_strategy")
    indicators: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class StrategyGenerationResponsePayload(BaseModel):
    draft: StrategyDraftPayload
    request: StrategyGenerationRequestPayload


class StrategyAssistantImportRequest(BaseModel):
    """Payload accepted when importing a draft generated by the assistant."""

    name: str | None = None
    format: Literal["yaml", "python"]
    content: str = Field(..., min_length=1)
    enabled: bool = False
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    parameters: dict[str, object] = Field(default_factory=dict)


SUPPORTED_TIMEFRAMES: Dict[str, int] = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class StrategyBacktestRunRequest(BaseModel):
    """Form values submitted by the UI to execute a backtest."""

    symbol: str = Field(..., min_length=2, description="Symbole de l'actif à simuler")
    timeframe: Literal["15m", "1h", "4h", "1d"] = "1h"
    lookback_days: int = Field(30, ge=1, le=180)
    initial_balance: float = Field(10_000.0, gt=0)


def _timeframe_to_minutes(timeframe: str) -> int:
    minutes = SUPPORTED_TIMEFRAMES.get(timeframe)
    if minutes is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Période non supportée")
    return minutes


def _generate_synthetic_market_data(
    symbol: str,
    timeframe: str,
    lookback_days: int,
    *,
    max_candles: int = 500,
) -> List[Dict[str, Any]]:
    """Create deterministic OHLC data for backtests when real data is unavailable."""

    minutes = _timeframe_to_minutes(timeframe)
    total_minutes = lookback_days * 24 * 60
    candle_count = max(1, min(max_candles, total_minutes // minutes or 1))
    base_price = 50 + (abs(hash(symbol)) % 5_000) / 10.0
    start_time = datetime.now() - timedelta(days=lookback_days)
    equity: List[Dict[str, Any]] = []
    amplitude = max(1.0, base_price * 0.015)

    for index in range(candle_count):
        progress = index / max(1, candle_count - 1)
        angle = progress * math.pi * 4
        wave = math.sin(angle) * amplitude
        drift = progress * amplitude * 0.5
        close = base_price + wave + drift
        open_price = base_price + math.sin(max(0, index - 1)) * amplitude * 0.5 + drift
        high = max(close, open_price) + amplitude * 0.1
        low = min(close, open_price) - amplitude * 0.1
        timestamp = start_time + timedelta(minutes=index * minutes)
        equity.append(
            {
                "timestamp": timestamp.isoformat(),
                "open": round(open_price, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": round(abs(math.cos(angle)) * 10_000, 3),
            }
        )
    return equity


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"message": response.text or "Réponse invalide du moteur de stratégies."}


@app.get("/health")
def healthcheck() -> dict[str, str]:
    """Simple health endpoint."""

    return {"status": "ok"}


@app.get("/portfolios")
def list_portfolios() -> dict[str, object]:
    """Return a snapshot of portfolios."""

    context = load_dashboard_context()
    return {"items": context.portfolios}


@app.post("/positions/{position_id}/close")
def close_position(position_id: str, payload: PositionCloseRequest | None = None) -> dict[str, object]:
    """Forward close/adjust requests to the order router service."""

    request_payload = payload or PositionCloseRequest()
    base_url = ORDER_ROUTER_BASE_URL.rstrip("/")
    try:
        with OrderRouterClient(
            base_url=base_url, timeout=ORDER_ROUTER_TIMEOUT_SECONDS
        ) as client:
            response = client.close_position(
                position_id, target_quantity=request_payload.target_quantity
            )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Le routeur d'ordres est indisponible pour le moment.",
        ) from error
    except OrderRouterError as error:
        detail: dict[str, object]
        if error.response is not None:
            try:
                detail = error.response.json()
            except ValueError:
                detail = {
                    "message": error.response.text
                    or "Réponse invalide du routeur d'ordres.",
                }
        else:
            detail = {"message": "Réponse invalide du routeur d'ordres."}
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from error

    return response.model_dump(mode="json")


@app.get("/portfolios/history")
def portfolio_history() -> dict[str, object]:
    """Return historical valuation series for each portfolio."""

    history = load_portfolio_history()
    return {
        "items": [series.model_dump(mode="json") for series in history],
        "granularity": "daily",
    }


@app.get("/transactions")
def list_transactions() -> dict[str, object]:
    """Return recent transactions."""

    context = load_dashboard_context()
    return {"items": context.transactions}


@app.get("/alerts")
def list_alerts() -> dict[str, object]:
    """Return currently active alerts."""

    context = load_dashboard_context()
    return {"items": context.alerts}


@app.get("/alerts/history")
def list_alert_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start: datetime | None = Query(None, description="Filter events triggered after this timestamp"),
    end: datetime | None = Query(None, description="Filter events triggered before this timestamp"),
    strategy: str | None = Query(None, description="Filter by strategy or rule name"),
    severity: str | None = Query(None, description="Filter by severity"),
    session: Session = Depends(get_alert_events_session),
) -> dict[str, object]:
    """Return paginated alert history entries."""

    page_data = _alert_events_repository.list_events(
        session,
        page=page,
        page_size=page_size,
        start=start,
        end=end,
        strategy=strategy,
        severity=severity,
    )

    items = [
        {
            "id": event.id,
            "trigger_id": event.trigger_id,
            "rule_id": event.rule_id,
            "rule_name": event.rule_name,
            "strategy": event.strategy,
            "severity": event.severity,
            "symbol": event.symbol,
            "triggered_at": event.triggered_at.isoformat(),
            "context": event.context or {},
            "delivery_status": event.delivery_status,
            "notification_channel": event.notification_channel,
            "notification_target": event.notification_target,
        }
        for event in page_data.items
    ]

    available_filters = {
        "strategies": _alert_events_repository.list_strategies(session),
        "severities": _alert_events_repository.list_severities(session),
    }

    return {
        "items": items,
        "pagination": {
            "page": page_data.page,
            "page_size": page_data.page_size,
            "total": page_data.total,
            "pages": page_data.pages,
        },
        "available_filters": available_filters,
    }


@app.post("/alerts", response_model=Alert, status_code=status.HTTP_201_CREATED)
def create_alert(
    alert: AlertCreateRequest,
    client: AlertsEngineClient = Depends(get_alerts_client),
    _: None = Depends(require_alerts_auth),
) -> Alert:
    """Create a new alert by delegating to the alert engine."""

    try:
        payload = client.create_alert(alert.model_dump(mode="json"))
    except AlertsEngineError as error:
        _handle_alert_engine_error(error)
    return Alert.model_validate(payload)


@app.put("/alerts/{alert_id}", response_model=Alert)
def update_alert(
    alert_id: str,
    payload: AlertUpdateRequest,
    client: AlertsEngineClient = Depends(get_alerts_client),
    _: None = Depends(require_alerts_auth),
) -> Alert:
    """Update an existing alert by delegating to the alert engine."""

    body = payload.model_dump(mode="json", exclude_unset=True)
    try:
        response_payload = client.update_alert(alert_id, body)
    except AlertsEngineError as error:
        _handle_alert_engine_error(error)

    merged = {"id": alert_id, **body, **(response_payload or {})}
    return Alert.model_validate(merged)


@app.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(
    alert_id: str,
    client: AlertsEngineClient = Depends(get_alerts_client),
    _: None = Depends(require_alerts_auth),
) -> Response:
    """Remove an alert through the alert engine API."""

    try:
        client.delete_alert(alert_id)
    except AlertsEngineError as error:
        _handle_alert_engine_error(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/strategies", name="api_list_strategies")
async def list_available_strategies() -> dict[str, object]:
    """Expose the list of strategies managed by the algo-engine."""

    target_url = urljoin(ALGO_ENGINE_BASE_URL, "strategies")
    try:
        async with httpx.AsyncClient(timeout=ALGO_ENGINE_TIMEOUT) as client:
            response = await client.get(target_url, headers={"Accept": "application/json"})
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        message = "Algo-engine indisponible pour récupérer les stratégies."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from error

    if response.status_code >= 400:
        detail = _safe_json(response)
        raise HTTPException(status_code=response.status_code, detail=detail)

    payload = _safe_json(response)
    items: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        for raw in payload.get("items", []) or []:
            if isinstance(raw, dict) and raw.get("id"):
                items.append(
                    {
                        "id": raw.get("id"),
                        "name": raw.get("name"),
                        "strategy_type": raw.get("strategy_type"),
                    }
                )
    return {"items": items}


@app.post("/api/strategies/{strategy_id}/backtest", name="run_strategy_backtest")
async def run_strategy_backtest(
    strategy_id: str,
    payload: StrategyBacktestRunRequest,
) -> dict[str, Any]:
    """Trigger a backtest run by proxying to the algo-engine."""

    market_data = _generate_synthetic_market_data(
        payload.symbol,
        payload.timeframe,
        payload.lookback_days,
    )
    target_url = urljoin(ALGO_ENGINE_BASE_URL, f"strategies/{strategy_id}/backtest")
    request_payload = {
        "market_data": market_data,
        "initial_balance": payload.initial_balance,
        "metadata": {
            "symbol": payload.symbol,
            "timeframe": payload.timeframe,
            "lookback_days": payload.lookback_days,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=ALGO_ENGINE_TIMEOUT) as client:
            response = await client.post(
                target_url,
                json=request_payload,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        message = "Algo-engine indisponible pour lancer le backtest."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from error

    if response.status_code >= 400:
        detail = _safe_json(response)
        raise HTTPException(status_code=response.status_code, detail=detail)

    try:
        return response.json()
    except ValueError as error:  # pragma: no cover - invalid payload
        message = "Réponse invalide du moteur de stratégies."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from error


@app.get(
    "/api/strategies/{strategy_id}/backtest/ui",
    name="get_strategy_backtest_ui",
)
async def get_strategy_backtest_ui(strategy_id: str) -> dict[str, Any]:
    """Fetch the latest backtest metrics for UI consumption."""

    target_url = urljoin(ALGO_ENGINE_BASE_URL, f"strategies/{strategy_id}/backtest/ui")
    try:
        async with httpx.AsyncClient(timeout=ALGO_ENGINE_TIMEOUT) as client:
            response = await client.get(target_url, headers={"Accept": "application/json"})
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        message = "Algo-engine indisponible pour récupérer les métriques."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from error

    if response.status_code >= 400:
        detail = _safe_json(response)
        raise HTTPException(status_code=response.status_code, detail=detail)

    payload = _safe_json(response)
    if not isinstance(payload, dict):
        return {"equity_curve": [], "pnl": 0, "drawdown": 0}
    return payload


@app.get(
    "/api/strategies/{strategy_id}/backtests",
    name="list_strategy_backtests",
)
async def list_strategy_backtests(
    strategy_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
) -> dict[str, Any]:
    """Retrieve historical backtests from the algo-engine."""

    target_url = urljoin(ALGO_ENGINE_BASE_URL, f"strategies/{strategy_id}/backtests")
    params = {"page": page, "page_size": page_size}
    try:
        async with httpx.AsyncClient(timeout=ALGO_ENGINE_TIMEOUT) as client:
            response = await client.get(
                target_url,
                params=params,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        message = "Algo-engine indisponible pour récupérer l'historique."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from error

    if response.status_code >= 400:
        detail = _safe_json(response)
        raise HTTPException(status_code=response.status_code, detail=detail)

    payload = _safe_json(response)
    if not isinstance(payload, dict):
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    return payload


@app.post("/strategies/save")
async def save_strategy(payload: StrategySaveRequest) -> dict[str, object]:
    """Relay strategy definitions to the algo-engine import endpoint."""

    target_url = urljoin(ALGO_ENGINE_BASE_URL, "strategies/import")
    try:
        async with httpx.AsyncClient(timeout=ALGO_ENGINE_TIMEOUT) as client:
            response = await client.post(
                target_url,
                json={
                    "name": payload.name,
                    "format": payload.format,
                    "content": payload.code,
                },
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        message = "Le moteur de stratégies est indisponible pour le moment."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from error

    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:  # pragma: no cover - fallback when JSON parsing fails
            detail = {"message": response.text or "Erreur lors de l'import de la stratégie."}
        raise HTTPException(status_code=response.status_code, detail=detail)

    try:
        return response.json()
    except ValueError:  # pragma: no cover - defensive guard when response is empty
        return {"status": "imported"}


@app.post("/strategies/import/upload")
async def upload_strategy_file(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    source_format: Literal["yaml", "python"] | None = Form(None),
) -> dict[str, object]:
    """Allow users to upload an existing YAML/Python file to the algo-engine."""

    try:
        content_bytes = await file.read()
    except Exception as error:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lecture du fichier impossible.",
        ) from error

    if not content_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le fichier envoyé est vide.",
        )

    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le fichier doit être encodé en UTF-8.",
        ) from error

    filename = file.filename or ""
    guessed_format = "yaml"
    if filename.lower().endswith(".py"):
        guessed_format = "python"
    elif filename.lower().endswith((".yaml", ".yml")):
        guessed_format = "yaml"

    target_url = urljoin(ALGO_ENGINE_BASE_URL, "strategies/import")
    payload = {
        "name": name or (filename.rsplit(".", 1)[0] if filename else "Stratégie importée"),
        "format": source_format or guessed_format,
        "content": content,
    }

    try:
        async with httpx.AsyncClient(timeout=ALGO_ENGINE_TIMEOUT) as client:
            response = await client.post(
                target_url,
                json=payload,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        message = "Le moteur de stratégies est indisponible pour le moment."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from error

    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = {"message": response.text or "Erreur lors de l'import de la stratégie."}
        raise HTTPException(status_code=response.status_code, detail=detail)

    try:
        return response.json()
    except ValueError:  # pragma: no cover - defensive guard when response is empty
        return {"status": "imported"}


@app.post("/strategies/generate")
async def generate_strategy(payload: StrategyGenerationRequestPayload) -> dict[str, object]:
    """Delegate strategy generation to the AI assistant microservice."""

    target_url = urljoin(AI_ASSISTANT_BASE_URL, "generate")
    try:
        async with httpx.AsyncClient(timeout=AI_ASSISTANT_TIMEOUT) as client:
            response = await client.post(target_url, json=payload.model_dump())
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        message = "Le service d'assistance IA est indisponible pour le moment."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from error

    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = {"message": response.text or "Erreur lors de la génération."}
        raise HTTPException(status_code=response.status_code, detail=detail)

    try:
        data = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Réponse invalide du service d'assistance IA.",
        ) from error

    model = StrategyGenerationResponsePayload.model_validate(data)
    return model.model_dump(mode="json")


@app.post("/strategies/import/assistant")
async def import_assistant_strategy(payload: StrategyAssistantImportRequest) -> dict[str, object]:
    """Forward assistant drafts to the algo-engine import endpoint."""

    target_url = urljoin(ALGO_ENGINE_BASE_URL, "strategies/import")
    try:
        async with httpx.AsyncClient(timeout=ALGO_ENGINE_TIMEOUT) as client:
            response = await client.post(
                target_url,
                json=payload.model_dump(),
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        message = "Le moteur de stratégies est indisponible pour le moment."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from error

    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = {"message": response.text or "Erreur lors de l'import de la stratégie."}
        raise HTTPException(status_code=response.status_code, detail=detail)

    try:
        return response.json()
    except ValueError:
        return {"status": "imported"}


@app.get("/dashboard", response_class=HTMLResponse)
def render_dashboard(request: Request) -> HTMLResponse:
    """Render an HTML dashboard that surfaces key trading signals."""

    context = load_dashboard_context()
    handshake_url = urljoin(STREAMING_BASE_URL, f"rooms/{STREAMING_ROOM_ID}/connection")
    alerts_token = os.getenv("WEB_DASHBOARD_ALERTS_TOKEN", "")
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "context": context,
            "streaming": {
                "handshake_url": handshake_url,
                "room_id": STREAMING_ROOM_ID,
                "viewer_id": STREAMING_VIEWER_ID,
            },
            "alerts_api": {
                "endpoint": request.url_for("list_alerts"),
                "history_endpoint": request.url_for("list_alert_history"),
                "token": alerts_token,
            },
            "active_page": "dashboard",
        },
    )


def _render_strategies_page(
    request: Request, *, initial_strategy: dict[str, Any] | None = None
) -> HTMLResponse:
    save_endpoint = request.url_for("save_strategy")
    ai_generate_endpoint = request.url_for("generate_strategy")
    ai_import_endpoint = request.url_for("import_assistant_strategy")
    upload_endpoint = request.url_for("upload_strategy_file")
    backtest_config = {
        "strategies_endpoint": request.url_for("api_list_strategies"),
        "run_endpoint_template": request.url_for(
            "run_strategy_backtest", strategy_id="__id__"
        ),
        "ui_endpoint_template": request.url_for(
            "get_strategy_backtest_ui", strategy_id="__id__"
        ),
        "history_endpoint_template": request.url_for(
            "list_strategy_backtests", strategy_id="__id__"
        ),
    }
    return templates.TemplateResponse(
        "strategies.html",
        {
            "request": request,
            "save_endpoint": save_endpoint,
            "ai_generate_endpoint": ai_generate_endpoint,
            "ai_import_endpoint": ai_import_endpoint,
            "upload_endpoint": upload_endpoint,
            "preset_summaries": STRATEGY_PRESET_SUMMARIES,
            "presets": STRATEGY_PRESETS,
            "backtest_config": backtest_config,
            "initial_strategy": initial_strategy,
            "active_page": "strategies",
        },
    )


@app.get("/strategies", response_class=HTMLResponse)
def render_strategies(request: Request) -> HTMLResponse:
    """Render the visual strategy designer page."""

    return _render_strategies_page(request)


@app.get("/strategies/documentation", response_class=HTMLResponse)
def render_strategy_documentation(request: Request) -> HTMLResponse:
    """Expose the declarative strategy schema and tutorials."""

    documentation = load_strategy_documentation()
    return templates.TemplateResponse(
        "strategy_documentation.html",
        {
            "request": request,
            "documentation": documentation,
            "active_page": "strategy-docs",
        },
    )


@app.post("/strategies/clone", response_class=HTMLResponse, name="clone_strategy_action")
async def clone_strategy_action(request: Request, strategy_id: str = Form(...)) -> HTMLResponse:
    """Clone an existing strategy and prefill the designer with the result."""

    target_url = urljoin(ALGO_ENGINE_BASE_URL, f"strategies/{strategy_id}/clone")
    try:
        async with httpx.AsyncClient(timeout=ALGO_ENGINE_TIMEOUT) as client:
            response = await client.post(target_url, headers={"Accept": "application/json"})
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        message = "Impossible de cloner la stratégie pour le moment."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from error

    if response.status_code >= 400:
        detail = _safe_json(response)
        raise HTTPException(status_code=response.status_code, detail=detail)

    payload = _safe_json(response)
    if not isinstance(payload, dict):
        message = "Réponse invalide du moteur de stratégies."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message)

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    initial_strategy = {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "strategy_type": payload.get("strategy_type"),
        "parameters": parameters,
        "metadata": metadata,
        "source_format": payload.get("source_format"),
        "source": payload.get("source"),
        "derived_from": payload.get("derived_from"),
        "derived_from_name": payload.get("derived_from_name"),
    }

    parent_label = initial_strategy.get("derived_from_name") or initial_strategy.get("derived_from")
    if parent_label:
        initial_strategy["status_message"] = f"Clone de {parent_label} prêt à être édité."
        initial_strategy["status_type"] = "success"

    return _render_strategies_page(request, initial_strategy=initial_strategy)


@app.get("/account", response_class=HTMLResponse)
def render_account(request: Request) -> HTMLResponse:
    """Render the account and API key management page."""

    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "active_page": "account",
        },
    )


@app.get("/")
def root_redirect(request: Request) -> HTMLResponse:
    """Serve the dashboard at the root path for convenience."""

    return render_dashboard(request)

