"""FastAPI application exposing screener capabilities."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from infra import ScreenerPreset, ScreenerResult, ScreenerSnapshot
from libs.db.db import get_db
from libs.entitlements import install_entitlements_middleware
from libs.entitlements.client import Entitlements
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from libs.secrets import get_secret
from providers import FinancialModelingPrepClient, FinancialModelingPrepError

from .schemas import (
    ScreenerPresetCreate,
    ScreenerPresetFavoriteUpdate,
    ScreenerPresetOut,
    ScreenerRunResponse,
)

configure_logging("screener")

app = FastAPI(title="Screener Service", version="0.1.0")
install_entitlements_middleware(
    app,
    required_capabilities=["can.use_screener"],
    required_quotas={},
)
app.add_middleware(RequestContextMiddleware, service_name="screener")
setup_metrics(app, service_name="screener")


async def get_fmp_client() -> FinancialModelingPrepClient:
    base_url = os.getenv("FMP_BASE_URL", "https://financialmodelingprep.com/api/v3")
    api_key = get_secret("FMP_API_KEY", default=os.getenv("FMP_API_KEY"))
    client = FinancialModelingPrepClient(api_key=api_key, base_url=base_url)
    async with client as session:
        yield session


class UserServiceClient:
    """Minimal async client used to read and write user preferences."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = None

    async def __aenter__(self) -> "UserServiceClient":
        import httpx

        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=5.0)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_preferences(self, authorization: str) -> dict[str, Any]:
        if self._client is None:  # pragma: no cover - defensive
            raise RuntimeError("UserServiceClient must be awaited as a context manager")
        response = await self._client.get("/users/me", headers={"Authorization": authorization})
        if response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized user"
            )
        response.raise_for_status()
        payload = response.json()
        return payload.get("preferences") or {}

    async def update_preferences(self, authorization: str, preferences: dict[str, Any]) -> None:
        if self._client is None:  # pragma: no cover - defensive
            raise RuntimeError("UserServiceClient must be awaited as a context manager")
        response = await self._client.put(
            "/users/me/preferences",
            headers={"Authorization": authorization},
            json=preferences,
        )
        if response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized user"
            )
        response.raise_for_status()


async def get_user_service_client() -> UserServiceClient:
    base_url = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
    client = UserServiceClient(base_url)
    async with client as session:
        yield session


def get_entitlements(request: Request) -> Entitlements:
    entitlements = getattr(request.state, "entitlements", None)
    if entitlements is None:
        return Entitlements(customer_id="anonymous", features={}, quotas={})
    return entitlements


def require_authorization(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header"
        )
    return authorization


def require_customer_id(request: Request) -> int:
    header_value = request.headers.get("x-customer-id") or request.headers.get("x-user-id")
    if not header_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing x-customer-id header"
        )
    try:
        return int(header_value)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid customer id"
        ) from exc


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _extract_filters(filters: str | None) -> dict[str, Any]:
    if not filters:
        return {}
    try:
        parsed = json.loads(filters)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid filters payload"
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Filters must be a JSON object"
        )
    return parsed


def _preferences_favorites(preferences: dict[str, Any]) -> list[int]:
    screener_section = preferences.get("screener") or {}
    favorites = screener_section.get("favorites") or []
    normalized: list[int] = []
    for pid in favorites:
        if isinstance(pid, int):
            normalized.append(pid)
        elif isinstance(pid, str) and pid.isdigit():
            normalized.append(int(pid))
    return normalized


def _update_favorites(preferences: dict[str, Any], favorite_ids: list[int]) -> dict[str, Any]:
    updated = dict(preferences)
    screener_section = dict(updated.get("screener") or {})
    screener_section["favorites"] = favorite_ids
    updated["screener"] = screener_section
    return updated


def _ensure_quota(entitlements: Entitlements, desired: int) -> None:
    limit = entitlements.quota("limit.watchlists")
    if limit is not None and desired > limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Watchlist quota exceeded ({desired}/{limit})",
        )


@app.get("/screener/run", response_model=ScreenerRunResponse)
async def run_screener(
    request: Request,
    provider: str = Query("fmp"),
    limit: int = Query(50, ge=1, le=200),
    preset_id: int | None = Query(default=None),
    filters: str | None = Query(default=None),
    db: Session = Depends(get_db),
    fmp_client: FinancialModelingPrepClient = Depends(get_fmp_client),
) -> ScreenerRunResponse:
    if provider != "fmp":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider '{provider}'"
        )

    user_id = require_customer_id(request)

    payload_filters: dict[str, Any] = {}
    resolved_preset_id: int | None = None
    if preset_id is not None:
        preset = db.get(ScreenerPreset, preset_id)
        if preset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
        if preset.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Preset does not belong to the user"
            )
        payload_filters.update(preset.filters)
        resolved_preset_id = preset.id

    payload_filters.update(_extract_filters(filters))

    try:
        results = await fmp_client.screen(filters=payload_filters, limit=limit)
    except FinancialModelingPrepError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    snapshot = ScreenerSnapshot(
        user_id=user_id, preset_id=resolved_preset_id, provider=provider, filters=payload_filters
    )
    db.add(snapshot)
    db.flush()

    for index, row in enumerate(results, start=1):
        symbol = row.get("symbol") or row.get("ticker") or ""
        if not symbol:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="Provider response missing symbol"
            )
        result = ScreenerResult(
            snapshot_id=snapshot.id,
            symbol=symbol,
            rank=index,
            score=row.get("score"),
            data=row,
        )
        db.add(result)

    db.commit()

    return ScreenerRunResponse(
        snapshot_id=snapshot.id,
        provider=provider,
        preset_id=resolved_preset_id,
        filters=payload_filters,
        results=results,
    )


@app.get("/screener/presets", response_model=list[ScreenerPresetOut])
async def list_presets(
    request: Request,
    authorization: str = Depends(require_authorization),
    user_client: UserServiceClient = Depends(get_user_service_client),
    db: Session = Depends(get_db),
) -> list[ScreenerPresetOut]:
    user_id = require_customer_id(request)

    preferences = await user_client.get_preferences(authorization)
    favorites = set(_preferences_favorites(preferences))

    presets = db.scalars(
        select(ScreenerPreset)
        .where(ScreenerPreset.user_id == user_id)
        .order_by(ScreenerPreset.created_at.desc())
    ).all()

    response: list[ScreenerPresetOut] = []
    for preset in presets:
        response.append(
            ScreenerPresetOut(
                id=preset.id,
                name=preset.name,
                description=preset.description,
                filters=preset.filters,
                favorite=preset.id in favorites,
                created_at=preset.created_at,
            )
        )

    return response


@app.post(
    "/screener/presets", response_model=ScreenerPresetOut, status_code=status.HTTP_201_CREATED
)
async def create_preset(
    request: Request,
    payload: ScreenerPresetCreate,
    authorization: str = Depends(require_authorization),
    user_client: UserServiceClient = Depends(get_user_service_client),
    entitlements: Entitlements = Depends(get_entitlements),
    db: Session = Depends(get_db),
) -> ScreenerPresetOut:
    user_id = require_customer_id(request)

    preset = ScreenerPreset(
        user_id=user_id,
        name=payload.name,
        description=payload.description,
        filters=payload.filters,
    )
    db.add(preset)
    db.flush()

    preferences = await user_client.get_preferences(authorization)
    favorites = set(_preferences_favorites(preferences))

    if payload.favorite:
        favorites.add(preset.id)
        _ensure_quota(entitlements, len(favorites))
        updated_preferences = _update_favorites(preferences, sorted(favorites))
        await user_client.update_preferences(authorization, updated_preferences)

    db.commit()

    return ScreenerPresetOut(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        filters=preset.filters,
        favorite=preset.id in favorites,
        created_at=preset.created_at,
    )


@app.post("/screener/presets/{preset_id}/favorite", response_model=ScreenerPresetOut)
async def toggle_favorite(
    request: Request,
    preset_id: int,
    payload: ScreenerPresetFavoriteUpdate,
    authorization: str = Depends(require_authorization),
    user_client: UserServiceClient = Depends(get_user_service_client),
    entitlements: Entitlements = Depends(get_entitlements),
    db: Session = Depends(get_db),
) -> ScreenerPresetOut:
    user_id = require_customer_id(request)
    preset = db.get(ScreenerPreset, preset_id)
    if preset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    if preset.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Preset does not belong to the user"
        )

    preferences = await user_client.get_preferences(authorization)
    favorites = set(_preferences_favorites(preferences))

    if payload.favorite:
        favorites.add(preset.id)
        _ensure_quota(entitlements, len(favorites))
    else:
        favorites.discard(preset.id)

    updated_preferences = _update_favorites(preferences, sorted(favorites))
    await user_client.update_preferences(authorization, updated_preferences)

    return ScreenerPresetOut(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        filters=preset.filters,
        favorite=preset.id in favorites,
        created_at=preset.created_at,
    )
