"""Minimal dashboard service for monitoring trading activity."""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
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
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from libs.alert_events import AlertEventBase, AlertEventRepository

from .data import (
    MARKETPLACE_BASE_URL,
    MARKETPLACE_TIMEOUT_SECONDS,
    ORDER_ROUTER_BASE_URL,
    ORDER_ROUTER_TIMEOUT_SECONDS,
    MarketplaceServiceError,
    fetch_marketplace_listings,
    fetch_marketplace_reviews,
    load_dashboard_context,
    load_follower_dashboard,
    load_portfolio_history,
    load_tradingview_config,
    REPORTS_BASE_URL,
    REPORTS_TIMEOUT_SECONDS,
    save_tradingview_config,
)
from .order_router_client import OrderRouterClient, OrderRouterError
from .alerts_client import AlertsEngineClient, AlertsEngineError
from .schemas import (
    Alert,
    AlertCreateRequest,
    AlertUpdateRequest,
    TradingViewConfig,
    TradingViewConfigUpdate,
)
from .documentation import load_strategy_documentation
from .helpcenter import HelpArticle, get_article_by_slug, load_help_center
from .help_progress import (
    LearningProgress,
    get_learning_progress,
    record_learning_activity,
)
from .strategy_presets import STRATEGY_PRESETS, STRATEGY_PRESET_SUMMARIES
from .localization import LocalizationMiddleware, template_base_context
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from schemas.order_router import PositionCloseRequest


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Web Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.add_middleware(LocalizationMiddleware)


def _template_context(request: Request, extra: dict[str, object] | None = None) -> dict[str, object]:
    context = {"request": request}
    context.update(template_base_context(request))
    if extra:
        context.update(extra)
    return context

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
DEFAULT_FOLLOWER_ID = os.getenv("WEB_DASHBOARD_DEFAULT_FOLLOWER_ID", "demo-investor")
USER_SERVICE_BASE_URL = os.getenv(
    "WEB_DASHBOARD_USER_SERVICE_URL",
    os.getenv("USER_SERVICE_URL", "http://user-service:8000/"),
)
USER_SERVICE_TIMEOUT = float(os.getenv("WEB_DASHBOARD_USER_SERVICE_TIMEOUT", "5.0"))
USER_SERVICE_JWT_SECRET = os.getenv(
    "USER_SERVICE_JWT_SECRET",
    os.getenv("JWT_SECRET", "dev-secret-change-me"),
)
USER_SERVICE_JWT_ALG = "HS256"
DEFAULT_DASHBOARD_USER_ID = os.getenv("WEB_DASHBOARD_DEFAULT_USER_ID", "1")


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


AUTH_SERVICE_BASE_URL = os.getenv(
    "WEB_DASHBOARD_AUTH_SERVICE_URL",
    os.getenv("AUTH_SERVICE_URL", "http://auth-service:8011/"),
)
AUTH_SERVICE_TIMEOUT = float(os.getenv("WEB_DASHBOARD_AUTH_SERVICE_TIMEOUT", "5.0"))
AUTH_PUBLIC_BASE_URL = os.getenv("AUTH_BASE_URL") or AUTH_SERVICE_BASE_URL
ACCESS_TOKEN_COOKIE_NAME = os.getenv("WEB_DASHBOARD_ACCESS_COOKIE", "dashboard_access_token")
REFRESH_TOKEN_COOKIE_NAME = os.getenv("WEB_DASHBOARD_REFRESH_COOKIE", "dashboard_refresh_token")
ACCESS_TOKEN_MAX_AGE = int(os.getenv("WEB_DASHBOARD_ACCESS_TOKEN_MAX_AGE", str(15 * 60)))
REFRESH_TOKEN_MAX_AGE = int(
    os.getenv("WEB_DASHBOARD_REFRESH_TOKEN_MAX_AGE", str(7 * 24 * 60 * 60))
)
AUTH_COOKIE_SECURE = _env_bool(os.getenv("WEB_DASHBOARD_AUTH_COOKIE_SECURE"), False)
AUTH_COOKIE_SAMESITE = os.getenv("WEB_DASHBOARD_AUTH_COOKIE_SAMESITE", "lax")
AUTH_COOKIE_DOMAIN = os.getenv("WEB_DASHBOARD_AUTH_COOKIE_DOMAIN") or None
 
HELP_DEFAULT_USER_ID = os.getenv("WEB_DASHBOARD_HELP_DEFAULT_USER_ID", "demo-user")

security = HTTPBearer(auto_error=False)


def _default_user_id() -> int:
    try:
        return int(DEFAULT_DASHBOARD_USER_ID)
    except (TypeError, ValueError):  # pragma: no cover - invalid env configuration
        return 1


def _coerce_dashboard_user_id(value: Optional[str]) -> int:
    if value:
        try:
            return int(value)
        except ValueError:
            pass
    return _default_user_id()


def _extract_dashboard_user_id(request: Request) -> int:
    header = request.headers.get("x-user-id")
    query_value = request.query_params.get("user_id")
    return _coerce_dashboard_user_id(header or query_value)


def _build_user_service_token(user_id: int) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode(
        {"sub": str(user_id), "iat": now},
        USER_SERVICE_JWT_SECRET,
        algorithm=USER_SERVICE_JWT_ALG,
    )


async def _forward_user_service_request(
    method: str,
    path: str,
    user_id: int,
    *,
    json: dict[str, Any] | None = None,
    error_detail: str | None = None,
) -> dict[str, object]:
    base_url = USER_SERVICE_BASE_URL.rstrip("/") + "/"
    target_url = urljoin(base_url, path)
    headers = {
        "Authorization": f"Bearer {_build_user_service_token(user_id)}",
        "x-customer-id": str(user_id),
        "x-user-id": str(user_id),
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=USER_SERVICE_TIMEOUT) as client:
            response = await client.request(
                method.upper(), target_url, headers=headers, json=json
            )
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        detail = error_detail or "Service utilisateur indisponible."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from error

    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            fallback = error_detail or "Erreur lors de la synchronisation avec le service utilisateur."
            payload = {"detail": fallback}
        raise HTTPException(status_code=response.status_code, detail=payload)

    try:
        return response.json()
    except ValueError:
        return {}


async def _forward_onboarding_request(method: str, path: str, user_id: int) -> dict[str, object]:
    return await _forward_user_service_request(
        method,
        path,
        user_id,
        error_detail="Service utilisateur indisponible pour l'onboarding.",
    )


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


class AccountUser(BaseModel):
    id: int
    email: EmailStr
    roles: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(extra="ignore")


class AccountSession(BaseModel):
    authenticated: bool = False
    user: AccountUser | None = None

    model_config = ConfigDict(extra="ignore")


class AccountLoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp: str | None = None


class BrokerCredentialUpdatePayload(BaseModel):
    broker: str = Field(min_length=1)
    api_key: str | None = None
    api_secret: str | None = None

    model_config = ConfigDict(extra="ignore")


class BrokerCredentialsUpdateRequest(BaseModel):
    credentials: List[BrokerCredentialUpdatePayload] = Field(default_factory=list)


class BrokerCredentialPayload(BaseModel):
    broker: str
    has_api_key: bool = False
    has_api_secret: bool = False
    api_key_masked: str | None = None
    api_secret_masked: str | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(extra="ignore")


class BrokerCredentialsPayload(BaseModel):
    credentials: List[BrokerCredentialPayload] = Field(default_factory=list)


def _auth_service_url(path: str) -> str:
    base = AUTH_SERVICE_BASE_URL.rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def _extract_auth_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = (response.text or "").strip()
        return text or "Une erreur est survenue lors de l'authentification."

    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail:
        return detail
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message:
            return message
    message = payload.get("message") if isinstance(payload, dict) else None
    if isinstance(message, str) and message:
        return message
    return "Une erreur est survenue lors de l'authentification."


async def _call_auth_service(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    token: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    url = _auth_service_url(path)
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if token:
        if token.lower().startswith("bearer "):
            request_headers["Authorization"] = token
        else:
            request_headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=AUTH_SERVICE_TIMEOUT) as client:
            response = await client.request(method.upper(), url, json=json, headers=request_headers)
    except httpx.HTTPError as error:  # pragma: no cover - network failure
        detail = "Service d'authentification indisponible."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from error
    return response


def _set_auth_cookies(response: Response, token_pair: dict[str, Any]) -> None:
    access_token = token_pair.get("access_token")
    refresh_token = token_pair.get("refresh_token")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        detail = "Réponse du service d'authentification invalide."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

    cookie_kwargs: dict[str, Any] = {
        "httponly": True,
        "secure": AUTH_COOKIE_SECURE,
        "samesite": AUTH_COOKIE_SAMESITE,
        "path": "/",
    }
    if AUTH_COOKIE_DOMAIN:
        cookie_kwargs["domain"] = AUTH_COOKIE_DOMAIN

    response.set_cookie(
        ACCESS_TOKEN_COOKIE_NAME,
        access_token,
        max_age=ACCESS_TOKEN_MAX_AGE,
        **cookie_kwargs,
    )
    response.set_cookie(
        REFRESH_TOKEN_COOKIE_NAME,
        refresh_token,
        max_age=REFRESH_TOKEN_MAX_AGE,
        **cookie_kwargs,
    )


def _clear_auth_cookies(response: Response) -> None:
    cookie_kwargs: dict[str, Any] = {"path": "/"}
    if AUTH_COOKIE_DOMAIN:
        cookie_kwargs["domain"] = AUTH_COOKIE_DOMAIN
    response.delete_cookie(ACCESS_TOKEN_COOKIE_NAME, **cookie_kwargs)
    response.delete_cookie(REFRESH_TOKEN_COOKIE_NAME, **cookie_kwargs)


async def _auth_login(payload: AccountLoginRequest) -> dict[str, Any]:
    response = await _call_auth_service(
        "POST",
        "/auth/login",
        json=payload.model_dump(exclude_none=True),
    )
    if response.status_code >= 400:
        detail = _extract_auth_error(response)
        raise HTTPException(status_code=response.status_code, detail=detail)
    try:
        return response.json()
    except ValueError:
        detail = "Réponse du service d'authentification invalide."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


async def _auth_me(access_token: str | None) -> AccountUser | None:
    if not access_token:
        return None
    response = await _call_auth_service("GET", "/auth/me", token=access_token)
    if response.status_code == status.HTTP_200_OK:
        try:
            payload = response.json()
        except ValueError:
            detail = "Réponse du service d'authentification invalide."
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
        return AccountUser.model_validate(payload)
    if response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
        return None
    detail = _extract_auth_error(response)
    raise HTTPException(status_code=response.status_code, detail=detail)


async def _auth_refresh(refresh_token: str | None) -> dict[str, Any] | None:
    if not refresh_token:
        return None
    response = await _call_auth_service(
        "POST",
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    if response.status_code == status.HTTP_200_OK:
        try:
            return response.json()
        except ValueError:
            detail = "Réponse du service d'authentification invalide."
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    if response.status_code in {
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
    }:
        return None
    detail = _extract_auth_error(response)
    raise HTTPException(status_code=response.status_code, detail=detail)


async def _auth_logout(access_token: str | None, refresh_token: str | None) -> None:
    if not access_token and not refresh_token:
        return
    json_payload = {"refresh_token": refresh_token} if refresh_token else None
    try:
        response = await _call_auth_service(
            "POST",
            "/auth/logout",
            json=json_payload,
            token=access_token,
        )
    except HTTPException:
        return
    if response.status_code >= 400 and response.status_code not in {404, 405}:
        # Logout should be best-effort; ignore unsupported endpoints.
        detail = _extract_auth_error(response)
        raise HTTPException(status_code=response.status_code, detail=detail)


async def _resolve_account_session(
    response: Response,
    access_token: str | None,
    refresh_token: str | None,
) -> AccountSession:
    user = await _auth_me(access_token)
    if user:
        return AccountSession(authenticated=True, user=user)

    refreshed = await _auth_refresh(refresh_token)
    if refreshed and isinstance(refreshed, dict):
        _set_auth_cookies(response, refreshed)
        user = await _auth_me(refreshed.get("access_token"))
        if user:
            return AccountSession(authenticated=True, user=user)

    _clear_auth_cookies(response)
    return AccountSession(authenticated=False)


async def _resolve_session_from_request(request: Request, response: Response) -> AccountSession:
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    return await _resolve_account_session(response, access_token, refresh_token)


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


class HelpArticlePayload(BaseModel):
    """Article payload returned by the help center API."""

    slug: str
    title: str
    summary: str
    resource_type: str
    category: str
    body_html: str
    resource_link: str | None = None
    tags: list[str] = Field(default_factory=list)


class LearningResourceVisitPayload(BaseModel):
    """Single resource visit serialised for the API."""

    slug: str
    title: str
    resource_type: str
    viewed_at: datetime


class LearningProgressPayload(BaseModel):
    """Learning progress metrics for the help center."""

    user_id: str
    completion_rate: int
    completed_resources: int
    total_resources: int
    recent_resources: list[LearningResourceVisitPayload] = Field(default_factory=list)


class HelpArticlesResponse(BaseModel):
    """Envelope returned by `/help/articles`."""

    articles: list[HelpArticlePayload]
    sections: Dict[str, list[HelpArticlePayload]]
    progress: LearningProgressPayload


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
            "notification_type": event.notification_type,
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


@app.get("/config/tradingview", response_model=TradingViewConfig)
def get_tradingview_config() -> TradingViewConfig:
    """Return the TradingView configuration consumed by the frontend widget."""

    config = load_tradingview_config()
    return TradingViewConfig.model_validate(config)


@app.put("/config/tradingview", response_model=TradingViewConfig)
def update_tradingview_config(payload: TradingViewConfigUpdate) -> TradingViewConfig:
    """Persist TradingView configuration updates provided by the UI."""

    current = load_tradingview_config()

    if payload.api_key is not None:
        current["api_key"] = payload.api_key or ""

    if payload.library_url is not None:
        current["library_url"] = payload.library_url.strip() if payload.library_url else ""

    if payload.default_symbol is not None:
        current["default_symbol"] = payload.default_symbol.strip() if payload.default_symbol else ""

    if payload.symbol_map is not None:
        normalised_map: dict[str, str] = {}
        for key, value in payload.symbol_map.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            cleaned_key = key.strip()
            cleaned_value = value.strip()
            if cleaned_key and cleaned_value:
                normalised_map[cleaned_key] = cleaned_value
        current["symbol_map"] = normalised_map

    if payload.overlays is not None:
        current["overlays"] = [overlay.model_dump() for overlay in payload.overlays]

    save_tradingview_config(current)
    return TradingViewConfig.model_validate(load_tradingview_config())


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


@app.get("/api/onboarding/progress", name="api_get_onboarding_progress")
async def api_get_onboarding_progress(request: Request) -> dict[str, object]:
    """Expose onboarding status proxied from user-service."""

    user_id = _extract_dashboard_user_id(request)
    return await _forward_onboarding_request("GET", "users/me/onboarding", user_id)


@app.post("/api/onboarding/steps/{step_id}", name="api_complete_onboarding_step")
async def api_complete_onboarding_step(step_id: str, request: Request) -> dict[str, object]:
    """Mark an onboarding step as complete on behalf of the authenticated viewer."""

    user_id = _extract_dashboard_user_id(request)
    path = f"users/me/onboarding/steps/{step_id}"
    return await _forward_onboarding_request("POST", path, user_id)


@app.post("/api/onboarding/reset", name="api_reset_onboarding_progress")
async def api_reset_onboarding_progress(request: Request) -> dict[str, object]:
    """Reset onboarding progress for the current viewer."""

    user_id = _extract_dashboard_user_id(request)
    return await _forward_onboarding_request("POST", "users/me/onboarding/reset", user_id)


@app.get(
    "/api/account/broker-credentials",
    response_model=BrokerCredentialsPayload,
    name="api_get_broker_credentials",
)
async def api_get_broker_credentials(request: Request) -> dict[str, object]:
    """Expose broker credential metadata proxied from the user service."""

    user_id = _extract_dashboard_user_id(request)
    payload = await _forward_user_service_request(
        "GET",
        "users/me/broker-credentials",
        user_id,
        error_detail="Service utilisateur indisponible pour les identifiants broker.",
    )
    model = BrokerCredentialsPayload.model_validate(payload)
    return model.model_dump(mode="json")


@app.put(
    "/api/account/broker-credentials",
    response_model=BrokerCredentialsPayload,
    name="api_update_broker_credentials",
)
async def api_update_broker_credentials(
    payload: BrokerCredentialsUpdateRequest, request: Request
) -> dict[str, object]:
    """Forward broker credential updates to the user service."""

    user_id = _extract_dashboard_user_id(request)
    result = await _forward_user_service_request(
        "PUT",
        "users/me/broker-credentials",
        user_id,
        json=payload.model_dump(exclude_none=True),
        error_detail="Service utilisateur indisponible pour les identifiants broker.",
    )
    model = BrokerCredentialsPayload.model_validate(result)
    return model.model_dump(mode="json")


@app.get("/dashboard", response_class=HTMLResponse)
def render_dashboard(request: Request) -> HTMLResponse:
    """Render an HTML dashboard that surfaces key trading signals."""

    context = load_dashboard_context()
    handshake_url = urljoin(STREAMING_BASE_URL, f"rooms/{STREAMING_ROOM_ID}/connection")
    alerts_token = os.getenv("WEB_DASHBOARD_ALERTS_TOKEN", "")
    user_id = _extract_dashboard_user_id(request)
    onboarding_api = {
        "progress_endpoint": request.url_for("api_get_onboarding_progress"),
        "step_template": request.url_for(
            "api_complete_onboarding_step", step_id="__STEP__"
        ),
        "reset_endpoint": request.url_for("api_reset_onboarding_progress"),
        "user_id": str(user_id),
    }
    return templates.TemplateResponse(
        "dashboard.html",
        _template_context(
            request,
            {
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
                "annotation_status": request.query_params.get("annotation"),
                "onboarding_api": onboarding_api,
            },
        ),
    )


@app.get("/dashboard/followers", response_class=HTMLResponse)
def render_follower_dashboard(request: Request) -> HTMLResponse:
    """Render the follower dashboard summarising copy-trading allocations."""

    viewer_id = request.headers.get("x-user-id") or request.query_params.get("viewer_id")
    viewer_id = viewer_id or DEFAULT_FOLLOWER_ID
    context = load_follower_dashboard(viewer_id)
    return templates.TemplateResponse(
        "follower.html",
        _template_context(
            request,
            {
                "context": context,
                "active_page": "followers",
            },
        ),
    )


@app.post("/dashboard/annotate")
def annotate_dashboard_order(
    request: Request,
    order_id: int = Form(..., ge=1),
    note: str = Form(..., min_length=1),
    tags: str = Form(default=""),
) -> Response:
    tag_list = [part.strip() for part in tags.split(",") if part.strip()]
    base_url = ORDER_ROUTER_BASE_URL.rstrip("/") + "/"
    status_flag = "success"
    try:
        with OrderRouterClient(
            base_url=base_url, timeout=ORDER_ROUTER_TIMEOUT_SECONDS
        ) as client:
            client.annotate_order(order_id, notes=note, tags=tag_list)
    except (httpx.HTTPError, OrderRouterError):
        status_flag = "error"
    redirect_target = request.url_for("render_dashboard")
    redirect_url = redirect_target.include_query_params(annotation=status_flag)
    return RedirectResponse(str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/marketplace", response_class=HTMLResponse, name="render_marketplace")
def render_marketplace(request: Request) -> HTMLResponse:
    """Render the marketplace view that embeds the React catalogue."""

    return templates.TemplateResponse(
        "marketplace.html",
        _template_context(
            request,
            {
                "active_page": "marketplace",
            },
        ),
    )


def _format_marketplace_error(error: MarketplaceServiceError) -> dict[str, object]:
    detail: dict[str, object] = {"message": error.message}
    if error.context:
        detail["context"] = error.context
    return detail


@app.get("/marketplace/listings", name="list_marketplace_listings")
async def list_marketplace_listings(
    search: str | None = Query(default=None, description="Recherche textuelle"),
    min_performance: float | None = Query(
        default=None, ge=0.0, description="Performance minimale"
    ),
    max_risk: float | None = Query(default=None, ge=0.0, description="Risque maximal"),
    max_price: float | None = Query(
        default=None, ge=0.0, description="Prix maximal en devise locale"
    ),
    sort: str = Query(default="created_desc", description="Clé de tri"),
) -> list[dict[str, object]]:
    """Proxy listings from the marketplace service."""

    filters = {
        "search": search,
        "min_performance": min_performance,
        "max_risk": max_risk,
        "max_price": max_price,
        "sort": sort,
    }
    try:
        return await fetch_marketplace_listings(filters)
    except MarketplaceServiceError as error:
        status_code = error.status_code or status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=_format_marketplace_error(error))


@app.get(
    "/marketplace/listings/{listing_id}/reviews",
    name="list_marketplace_listing_reviews",
)
async def list_marketplace_listing_reviews(listing_id: int) -> list[dict[str, object]]:
    """Proxy listing reviews from the marketplace service."""

    try:
        return await fetch_marketplace_reviews(listing_id)
    except MarketplaceServiceError as error:
        status_code = error.status_code or status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=_format_marketplace_error(error))


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
        _template_context(
            request,
            {
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
        ),
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
        _template_context(
            request,
            {
                "documentation": documentation,
                "active_page": "strategy-docs",
            },
        ),
    )


def _build_help_article_payload(article: HelpArticle) -> HelpArticlePayload:
    return HelpArticlePayload(
        slug=article.slug,
        title=article.title,
        summary=article.summary,
        resource_type=article.resource_type,
        category=article.category,
        body_html=article.body_html,
        resource_link=article.resource_link,
        tags=list(article.tags),
    )


def _build_learning_progress_payload(progress: LearningProgress) -> LearningProgressPayload:
    return LearningProgressPayload(
        user_id=progress.user_id,
        completion_rate=progress.completion_rate,
        completed_resources=progress.completed_resources,
        total_resources=progress.total_resources,
        recent_resources=[
            LearningResourceVisitPayload(
                slug=visit.slug,
                title=visit.title,
                resource_type=visit.resource_type,
                viewed_at=visit.viewed_at,
            )
            for visit in progress.recent_resources
        ],
    )


@app.get("/help", response_class=HTMLResponse)
def render_help_center(request: Request) -> HTMLResponse:
    """Expose the help & training knowledge base."""

    help_content = load_help_center()
    progress = get_learning_progress(HELP_DEFAULT_USER_ID, len(help_content.articles))
    return templates.TemplateResponse(
        "help_center.html",
        _template_context(
            request,
            {
                "help_content": help_content,
                "progress": progress,
                "articles_endpoint": request.url_for("list_help_articles"),
                "active_page": "help",
            },
        ),
    )


@app.get(
    "/help/articles",
    response_model=HelpArticlesResponse,
    name="list_help_articles",
)
def list_help_articles(viewed: str | None = Query(default=None, description="Slug de la ressource consultée")) -> HelpArticlesResponse:
    """Return rendered help center articles and progress metadata."""

    help_content = load_help_center()
    if viewed:
        article = get_article_by_slug(viewed)
        if article is not None:
            record_learning_activity(
                HELP_DEFAULT_USER_ID,
                slug=article.slug,
                title=article.title,
                resource_type=article.resource_type,
            )

    progress = get_learning_progress(HELP_DEFAULT_USER_ID, len(help_content.articles))
    sections_payload = {
        section: [_build_help_article_payload(item) for item in items]
        for section, items in help_content.sections.items()
    }
    return HelpArticlesResponse(
        articles=[_build_help_article_payload(article) for article in help_content.articles],
        sections=sections_payload,
        progress=_build_learning_progress_payload(progress),
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


@app.post("/account/login", response_model=AccountSession)
async def account_login(payload: AccountLoginRequest, response: Response) -> AccountSession:
    token_pair = await _auth_login(payload)
    _set_auth_cookies(response, token_pair)
    return await _resolve_account_session(
        response,
        token_pair.get("access_token"),
        token_pair.get("refresh_token"),
    )


@app.get("/account/session", response_model=AccountSession)
async def account_session(request: Request, response: Response) -> AccountSession:
    return await _resolve_session_from_request(request, response)


@app.post("/account/logout", response_model=AccountSession)
async def account_logout(request: Request, response: Response) -> AccountSession:
    await _auth_logout(
        request.cookies.get(ACCESS_TOKEN_COOKIE_NAME),
        request.cookies.get(REFRESH_TOKEN_COOKIE_NAME),
    )
    _clear_auth_cookies(response)
    return AccountSession(authenticated=False)


def _account_template_context(request: Request) -> dict[str, object]:
    created_flag = request.query_params.get("created")
    account_created = False
    if isinstance(created_flag, str):
        account_created = created_flag.strip().lower() in {"1", "true", "yes"}

    return _template_context(
        request,
        {
            "active_page": "account",
            "broker_credentials_endpoint": request.url_for(
                "api_get_broker_credentials"
            ),
            "account_created": account_created,
            "registration_url": request.url_for("render_account_register"),
        },
    )


@app.get("/account", response_class=HTMLResponse)
def render_account(request: Request) -> HTMLResponse:
    """Render the account and API key management page."""

    return templates.TemplateResponse("account.html", _account_template_context(request))


@app.get("/account/login", response_class=HTMLResponse, name="render_account_login")
def render_account_login(request: Request) -> HTMLResponse:
    """Expose a dedicated login entry point that reuses the account view."""

    return templates.TemplateResponse("account.html", _account_template_context(request))


def _render_registration_page(
    request: Request,
    *,
    email: str = "",
    error_message: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    return templates.TemplateResponse(
        "account_register.html",
        _template_context(
            request,
            {
                "active_page": "account",
                "form_email": email,
                "form_error": error_message,
                "submit_endpoint": request.url_for("submit_account_registration"),
                "login_url": request.url_for("render_account_login"),
            },
        ),
        status_code=status_code,
    )


@app.get(
    "/account/register",
    response_class=HTMLResponse,
    name="render_account_register",
)
async def render_account_register(request: Request) -> HTMLResponse:
    """Render the account registration form."""

    initial_email = request.query_params.get("email")
    return _render_registration_page(request, email=initial_email or "")


def _build_auth_registration_url() -> str:
    base = AUTH_PUBLIC_BASE_URL.rstrip("/") + "/"
    return urljoin(base, "auth/register")


@app.post(
    "/account/register",
    response_class=HTMLResponse,
    name="submit_account_registration",
)
async def submit_account_registration(
    request: Request,
    email: EmailStr = Form(...),
    password: str = Form(...),
) -> Response:
    """Forward registration requests to the authentication service."""

    try:
        async with httpx.AsyncClient(timeout=AUTH_SERVICE_TIMEOUT) as client:
            response = await client.post(
                _build_auth_registration_url(),
                json={"email": email, "password": password},
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError:
        message = "Impossible de créer le compte pour le moment."
        return _render_registration_page(
            request,
            email=email,
            error_message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    if response.status_code >= 400:
        error_message = _extract_auth_error(response)
        return _render_registration_page(
            request,
            email=email,
            error_message=error_message,
            status_code=response.status_code,
        )

    redirect_target = request.url_for("render_account_login").include_query_params(
        created="1"
    )
    return RedirectResponse(str(redirect_target), status_code=status.HTTP_303_SEE_OTHER)


def _service_health_definitions() -> list[dict[str, object]]:
    return [
        {
            "id": "auth",
            "label": "Service d'authentification",
            "description": "Gestion des comptes utilisateurs et des sessions.",
            "base_url": AUTH_PUBLIC_BASE_URL,
            "timeout": AUTH_SERVICE_TIMEOUT,
        },
        {
            "id": "reports",
            "label": "Service de rapports",
            "description": "Calcul des indicateurs de performance et exports.",
            "base_url": REPORTS_BASE_URL,
            "timeout": REPORTS_TIMEOUT_SECONDS,
        },
        {
            "id": "algo",
            "label": "Algo Engine",
            "description": "Orchestration et exécution des stratégies automatisées.",
            "base_url": ALGO_ENGINE_BASE_URL,
            "timeout": ALGO_ENGINE_TIMEOUT,
        },
        {
            "id": "router",
            "label": "Order Router",
            "description": "Acheminement des ordres vers les exchanges connectés.",
            "base_url": ORDER_ROUTER_BASE_URL,
            "timeout": ORDER_ROUTER_TIMEOUT_SECONDS,
        },
        {
            "id": "marketplace",
            "label": "Marketplace",
            "description": "Publication des stratégies et signaux proposés.",
            "base_url": MARKETPLACE_BASE_URL,
            "timeout": MARKETPLACE_TIMEOUT_SECONDS,
        },
    ]


async def _fetch_service_health(
    *, base_url: str, timeout: float
) -> tuple[str, str | None, str]:
    health_url = urljoin(base_url.rstrip("/") + "/", "health")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(health_url, headers={"Accept": "application/json"})
    except httpx.HTTPError as error:
        return "down", str(error), health_url

    if response.status_code >= 400:
        return "down", f"HTTP {response.status_code}", health_url

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        status_value = payload.get("status")
        if isinstance(status_value, str):
            normalised = status_value.strip().lower()
            if normalised and normalised not in {"ok", "up", "healthy", "online"}:
                return "down", status_value, health_url

    return "up", None, health_url


@app.get("/status", response_class=HTMLResponse, name="render_status_page")
async def render_status_page(request: Request) -> HTMLResponse:
    """Display the live health information for the platform services."""

    checked_at = datetime.now(timezone.utc)
    services: list[dict[str, object]] = []

    for definition in _service_health_definitions():
        base_url = str(definition["base_url"])
        timeout = float(definition["timeout"])
        status_value, detail, health_url = await _fetch_service_health(
            base_url=base_url, timeout=timeout
        )
        is_up = status_value == "up"
        services.append(
            {
                "id": definition["id"],
                "label": definition["label"],
                "description": definition["description"],
                "status": status_value,
                "status_label": "Opérationnel" if is_up else "Indisponible",
                "badge_variant": "success" if is_up else "critical",
                "detail": detail,
                "health_url": health_url,
            }
        )

    return templates.TemplateResponse(
        "status.html",
        _template_context(
            request,
            {
                "active_page": "status",
                "services": services,
                "checked_at": checked_at,
            },
        ),
    )


@app.get("/")
def root_redirect(request: Request) -> HTMLResponse:
    """Serve the dashboard at the root path for convenience."""

    return render_dashboard(request)

