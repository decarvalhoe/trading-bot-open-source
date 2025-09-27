from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from infra import ScreenerPreset, ScreenerResult, ScreenerSnapshot
from libs.db import db
from libs.entitlements.client import Entitlements
from services.screener.app.main import (
    app,
    get_entitlements,
    get_fmp_client,
    get_user_service_client,
)


@pytest.fixture(scope="module", autouse=True)
def disable_entitlements_middleware() -> None:
    """Remove the entitlements middleware for isolated unit tests."""

    app.user_middleware = [mw for mw in app.user_middleware if mw.cls.__name__ != "EntitlementsMiddleware"]
    app.middleware_stack = app.build_middleware_stack()


@pytest.fixture(autouse=True)
def cleanup_db() -> Iterator[None]:
    """Ensure the screener tables are empty before each test."""

    yield
    with db.SessionLocal() as session:
        session.query(ScreenerResult).delete()
        session.query(ScreenerSnapshot).delete()
        session.query(ScreenerPreset).delete()
        session.commit()


class DummyProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def screen(self, *, filters: dict[str, Any] | None = None, limit: int = 50) -> list[dict[str, Any]]:
        payload = {
            "filters": filters or {},
            "limit": limit,
        }
        self.calls.append(payload)
        return [
            {"symbol": "AAPL", "score": 0.91, "sector": "Technology"},
            {"symbol": "MSFT", "score": 0.87, "sector": "Technology"},
        ]


@dataclass
class DummyUserService:
    preferences: dict[str, Any] | None = None

    async def __aenter__(self) -> "DummyUserService":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get_preferences(self, authorization: str) -> dict[str, Any]:  # noqa: ARG002 - signature compatibility
        return self.preferences or {}

    async def update_preferences(self, authorization: str, preferences: dict[str, Any]) -> None:  # noqa: ARG002
        self.preferences = preferences


@pytest.fixture
def dummy_provider() -> DummyProvider:
    provider = DummyProvider()

    async def dependency_override() -> AsyncGenerator[DummyProvider, None]:
        yield provider

    app.dependency_overrides[get_fmp_client] = dependency_override
    yield provider
    app.dependency_overrides.pop(get_fmp_client, None)


@pytest.fixture
def dummy_user_service() -> DummyUserService:
    client = DummyUserService()

    async def dependency_override() -> AsyncGenerator[DummyUserService, None]:
        async with client as session:
            yield session

    app.dependency_overrides[get_user_service_client] = dependency_override
    yield client
    app.dependency_overrides.pop(get_user_service_client, None)


@pytest.fixture
def entitlements_limit_one() -> None:
    entitlements = Entitlements(customer_id="1", features={}, quotas={"limit.watchlists": 1})

    def dependency_override(request: Request) -> Entitlements:  # noqa: ARG001
        return entitlements

    app.dependency_overrides[get_entitlements] = dependency_override
    yield
    app.dependency_overrides.pop(get_entitlements, None)


def _auth_headers() -> dict[str, str]:
    return {
        "x-customer-id": "1",
        "Authorization": "Bearer test-token",
    }


def test_run_screener_creates_snapshot(dummy_provider: DummyProvider, dummy_user_service: DummyUserService) -> None:
    with TestClient(app) as client:
        response = client.get("/screener/run", headers={"x-customer-id": "1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "fmp"
    assert payload["results"][0]["symbol"] == "AAPL"
    assert dummy_provider.calls[0]["limit"] == 50

    with db.SessionLocal() as session:
        snapshot_count = session.query(ScreenerSnapshot).count()
        results_count = session.query(ScreenerResult).count()
    assert snapshot_count == 1
    assert results_count == 2


def test_create_preset_with_favorite_enforces_quota(
    dummy_provider: DummyProvider,
    dummy_user_service: DummyUserService,
    entitlements_limit_one: None,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/screener/presets",
            json={"name": "Growth", "filters": {"sector": "Technology"}, "favorite": True},
            headers=_auth_headers(),
        )
        assert response.status_code == 201, response.text

        response = client.post(
            "/screener/presets",
            json={"name": "Value", "filters": {"sector": "Financial"}, "favorite": True},
            headers=_auth_headers(),
        )
        assert response.status_code == 403
        assert "quota" in response.json()["detail"].lower()

    assert dummy_user_service.preferences is not None
    assert dummy_user_service.preferences["screener"]["favorites"]


def test_toggle_favorite_updates_preferences(
    dummy_provider: DummyProvider,
    dummy_user_service: DummyUserService,
    entitlements_limit_one: None,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/screener/presets",
            json={"name": "Momentum", "filters": {"betaMoreThan": 1.0}},
            headers=_auth_headers(),
        )
        assert response.status_code == 201, response.text
        preset_id = response.json()["id"]

        response = client.post(
            f"/screener/presets/{preset_id}/favorite",
            json={"favorite": True},
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["favorite"] is True

        response = client.post(
            f"/screener/presets/{preset_id}/favorite",
            json={"favorite": False},
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["favorite"] is False

    assert dummy_user_service.preferences is not None
    assert dummy_user_service.preferences["screener"]["favorites"] == []
