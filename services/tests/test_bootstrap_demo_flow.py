from __future__ import annotations

import asyncio
import importlib
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Coroutine

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from scripts.dev import bootstrap_demo

pytestmark = pytest.mark.end_to_end


def _normalise_base_url(url: str | httpx.URL | None) -> str | None:
    if url is None:
        return None
    if isinstance(url, httpx.URL):
        url = str(url)
    return url.rstrip("/")


def _prepare_database(tmp_path: Path) -> str:
    db_path = tmp_path / "bootstrap_demo.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path}"

    import os

    os.environ["DATABASE_URL"] = database_url

    db_module = importlib.import_module("libs.db.db")
    db_module = importlib.reload(db_module)

    from infra import (  # noqa: WPS433 - imported after DB reload on purpose
        AuditBase,
        EntitlementsBase,
        MarketplaceBase,
        ScreenerBase,
        SocialBase,
        TradingBase,
    )
    from services.reports.app import tables as report_tables

    for base in (AuditBase, EntitlementsBase, MarketplaceBase, ScreenerBase, SocialBase):
        base.metadata.drop_all(bind=db_module.engine)
        base.metadata.create_all(bind=db_module.engine)

    TradingBase.metadata.drop_all(bind=db_module.engine)
    TradingBase.metadata.create_all(bind=db_module.engine)

    report_tables.Base.metadata.drop_all(bind=db_module.engine)
    report_tables.Base.metadata.create_all(bind=db_module.engine)

    from datetime import datetime, timezone

    from schemas.report import StrategyName, Timeframe

    with db_module.engine.begin() as connection:
        connection.execute(report_tables.ReportSnapshot.__table__.delete())
        connection.execute(
            report_tables.ReportSnapshot.__table__.insert(),
            [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": Timeframe.DAILY,
                    "strategy": StrategyName.GAP_FILL,
                    "probability": 0.68,
                    "target": 45000.0,
                    "stop": 42000.0,
                    "expectancy": 0.12,
                    "sample_size": 125,
                    "updated_at": datetime.now(timezone.utc),
                },
                {
                    "symbol": "BTCUSDT",
                    "timeframe": Timeframe.INTRADAY,
                    "strategy": StrategyName.ORB,
                    "probability": 0.55,
                    "target": 45500.0,
                    "stop": 43000.0,
                    "expectancy": 0.09,
                    "sample_size": 87,
                    "updated_at": datetime.now(timezone.utc),
                },
            ],
        )

    return database_url


def _build_alerts_stub() -> tuple[FastAPI, list[dict[str, Any]]]:
    from fastapi import FastAPI

    app = FastAPI()
    storage: list[dict[str, Any]] = []

    @app.post("/alerts")  # type: ignore[no-redef]
    def create_alert(payload: dict[str, Any]) -> dict[str, Any]:
        from datetime import datetime, timezone

        alert_id = f"alert-{len(storage) + 1}"
        record = {
            "id": alert_id,
            "title": payload.get("title", ""),
            "detail": payload.get("detail", ""),
            "risk": payload.get("risk", "info"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged": payload.get("acknowledged", False),
            "rule": payload.get("rule", {"symbol": payload.get("symbol", "BTCUSDT"), "conditions": {}}),
            "channels": payload.get("channels", []),
            "throttle_seconds": payload.get("throttle_seconds", 0),
        }
        storage.append(record)
        return record

    @app.get("/alerts")  # type: ignore[no-redef]
    def list_alerts() -> list[dict[str, Any]]:
        return list(storage)

    return app, storage


@pytest.fixture()
def bootstrap_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv("ENTITLEMENTS_BYPASS", "1")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STREAMING_PIPELINE_BACKEND", "memory")
    monkeypatch.setenv("STREAMING_SERVICE_TOKEN_REPORTS", "reports-token")
    monkeypatch.delenv("STREAMING_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("STREAMING_INGEST_URL", raising=False)
    monkeypatch.setenv("STREAMING_ROOM_ID", "public-room")
    monkeypatch.setenv("WEB_DASHBOARD_ALERTS_TOKEN", "demo-alerts-token")
    monkeypatch.setenv("JWT_SECRET", "test-bootstrap-secret")
    alerts_db = tmp_path / "dashboard_alerts.sqlite"
    database_url = _prepare_database(tmp_path)
    monkeypatch.setenv("WEB_DASHBOARD_ALERT_EVENTS_DATABASE_URL", f"sqlite+pysqlite:///{alerts_db}")
    monkeypatch.setenv("ALERT_EVENTS_DATABASE_URL", f"sqlite+pysqlite:///{alerts_db}")
    monkeypatch.setenv("ORDER_ROUTER_URL", "http://order-router.local")
    monkeypatch.setenv("REPORTS_DATABASE_URL", database_url)

    urls = {
        "auth": "http://auth.local",
        "user": "http://user.local",
        "algo": "http://algo.local",
        "order_router": "http://order-router.local",
        "reports": "http://reports.local",
        "billing": "http://billing.local",
        "dashboard": "http://dashboard.local",
        "streaming": "http://streaming.local",
        "alerts_engine": "http://alerts.local",
    }
    return urls


@pytest.fixture()
def local_app_map(
    bootstrap_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[
    dict[str, FastAPI],
    list[dict[str, Any]],
    Callable[[str | httpx.URL | None], FastAPI | None],
    dict[str, FastAPI],
]:
    urls = bootstrap_environment

    alerts_app, alerts_storage = _build_alerts_stub()

    from fastapi.dependencies import utils as fastapi_utils

    monkeypatch.setattr(fastapi_utils, "ensure_multipart_is_installed", lambda: None)

    modules = {
        "auth": importlib.import_module("services.auth_service.app.main"),
        "user": importlib.import_module("services.user_service.app.main"),
        "algo": importlib.import_module("services.algo_engine.app.main"),
        "order_router": importlib.import_module("services.order_router.app.main"),
        "reports": importlib.import_module("services.reports.app.main"),
        "dashboard": importlib.import_module("services.web_dashboard.app.main"),
        "streaming": importlib.import_module("services.streaming.app.main"),
    }

    reports_db_module = importlib.import_module("services.reports.app.database")
    reports_db_module.reset_engine()

    from libs.entitlements.client import Entitlements, EntitlementsClient

    async def _mock_resolve(self, customer_id: str) -> Entitlements:
        features = {
            "can.use_auth": True,
            "can.use_users": True,
            "can.manage_strategies": True,
            "can.route_orders": True,
            "can.stream_public": True,
            "can.manage_users": True,
        }
        quotas = {"quota.active_algos": 10}
        return Entitlements(customer_id=str(customer_id), features=features, quotas=quotas)

    async def _mock_require(
        self,
        customer_id: str,
        capabilities: list[str] | None = None,
        quotas: dict[str, int] | None = None,
    ) -> Entitlements:
        entitlements = await _mock_resolve(self, customer_id)
        for capability in capabilities or []:
            entitlements.features.setdefault(capability, True)
        for name, required in (quotas or {}).items():
            current = entitlements.quotas.get(name)
            entitlements.quotas[name] = max(required, current or 0)
        return entitlements

    monkeypatch.setattr(EntitlementsClient, "resolve", _mock_resolve)
    monkeypatch.setattr(EntitlementsClient, "require", _mock_require)

    auth_main = modules["auth"]
    monkeypatch.setattr(auth_main, "hash_password", lambda password: f"hashed::{password}")
    monkeypatch.setattr(
        auth_main, "verify_password", lambda password, hashed: hashed == f"hashed::{password}"
    )

    db_module = importlib.import_module("libs.db.db")
    with db_module.engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS users"))
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 0,
                    is_superuser BOOLEAN NOT NULL DEFAULT 0,
                    first_name VARCHAR(120),
                    last_name VARCHAR(120),
                    phone VARCHAR(32),
                    marketing_opt_in BOOLEAN NOT NULL DEFAULT 0,
                    deleted_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    with db_module.engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS roles"))
        connection.execute(
            text(
                "CREATE TABLE roles (id INTEGER PRIMARY KEY, name VARCHAR(50) UNIQUE NOT NULL)"
            )
        )
        connection.execute(text("DROP TABLE IF EXISTS user_roles"))
        connection.execute(
            text(
                """
                CREATE TABLE user_roles (
                    user_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    PRIMARY KEY (user_id, role_id)
                )
                """
            )
        )
        connection.execute(text("DROP TABLE IF EXISTS mfa_totp"))
        connection.execute(
            text(
                """
                CREATE TABLE mfa_totp (
                    user_id INTEGER PRIMARY KEY,
                    secret VARCHAR(64) NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT 0
                )
                """
            )
        )
        connection.execute(text("DROP TABLE IF EXISTS user_preferences"))
        connection.execute(
            text(
                """
                CREATE TABLE user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    preferences TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
        )
        connection.execute(text("DROP TABLE IF EXISTS onboarding_progress"))
        connection.execute(
            text(
                """
                CREATE TABLE onboarding_progress (
                    user_id INTEGER PRIMARY KEY,
                    current_step VARCHAR(64),
                    completed_steps TEXT NOT NULL DEFAULT '[]',
                    restarted_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    user_db_dir = tmp_path_factory.mktemp("user-service")
    user_db_url = f"sqlite+pysqlite:///{user_db_dir / 'user_service.sqlite'}"
    user_engine = create_engine(
        user_db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    user_session_factory = sessionmaker(
        bind=user_engine, autoflush=False, autocommit=False, future=True
    )

    user_base = modules["user"].Base
    user_base.metadata.drop_all(bind=user_engine)
    user_base.metadata.create_all(bind=user_engine)

    def _user_get_db():
        db = user_session_factory()
        try:
            yield db
        finally:
            db.close()

    user_app = modules["user"].app  # type: ignore[attr-defined]
    original_user_get_db = modules["user"].get_db
    user_app.dependency_overrides[original_user_get_db] = _user_get_db

    app_map: dict[str, FastAPI] = {
        _normalise_base_url(urls["auth"]): modules["auth"].app,  # type: ignore[attr-defined]
        _normalise_base_url(urls["user"]): modules["user"].app,  # type: ignore[attr-defined]
        _normalise_base_url(urls["algo"]): modules["algo"].app,  # type: ignore[attr-defined]
        _normalise_base_url(urls["order_router"]): modules["order_router"].app,  # type: ignore[attr-defined]
        _normalise_base_url(urls["reports"]): modules["reports"].app,  # type: ignore[attr-defined]
        _normalise_base_url(urls["billing"]): importlib.import_module(
            "services.billing_service.app.main"
        ).app,  # type: ignore[attr-defined]
        _normalise_base_url(urls["dashboard"]): modules["dashboard"].app,  # type: ignore[attr-defined]
        _normalise_base_url(urls["streaming"]): modules["streaming"].app,  # type: ignore[attr-defined]
        _normalise_base_url(urls["alerts_engine"]): alerts_app,
    }

    monkeypatch.setenv("WEB_DASHBOARD_ALERT_ENGINE_URL", urls["alerts_engine"])
    modules["dashboard"].ALERT_ENGINE_BASE_URL = urls["alerts_engine"]

    def resolve_app(base_url: str | httpx.URL | None) -> FastAPI | None:
        normalised = _normalise_base_url(base_url)
        if normalised is None:
            return None
        return app_map.get(normalised)

    started_apps: list[FastAPI] = []
    lifespan_contexts: list[tuple[FastAPI, Any]] = []

    streaming_app = modules["streaming"].app  # type: ignore[attr-defined]
    streaming_lifespan = getattr(modules["streaming"], "lifespan", None)
    if callable(streaming_lifespan):
        context = streaming_lifespan(streaming_app)
        asyncio.run(context.__aenter__())
        lifespan_contexts.append((streaming_app, context))
        started_apps.append(streaming_app)

    for application in app_map.values():
        if application is streaming_app:
            continue
        asyncio.run(application.router.startup())
        started_apps.append(application)

    try:
        yield urls, alerts_storage, resolve_app, app_map
    finally:
        for application, context in reversed(lifespan_contexts):
            asyncio.run(context.__aexit__(None, None, None))
        for application in reversed(started_apps):
            if application is streaming_app:
                continue
            asyncio.run(application.router.shutdown())


@pytest.fixture(autouse=True)
def patch_httpx_clients(local_app_map, monkeypatch: pytest.MonkeyPatch):
    _, _, resolve_app, app_map = local_app_map
    original_client = httpx.Client
    original_async_client = httpx.AsyncClient

    class _AsyncRequestRunner:
        def __init__(self) -> None:
            self._loop = asyncio.new_event_loop()
            self._started = threading.Event()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self._started.wait()

        def _run_loop(self) -> None:
            asyncio.set_event_loop(self._loop)
            self._started.set()
            self._loop.run_forever()

        def call(self, coro: Coroutine[Any, Any, Any]) -> Any:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result()

        def close(self) -> None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
            self._loop.close()

    class _LocalSyncClient:
        def __init__(self, client: httpx.AsyncClient) -> None:
            self._client = client
            self.headers = client.headers
            self.base_url = client.base_url
            self.cookies = client.cookies
            self._runner = _AsyncRequestRunner()

        def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            return self._runner.call(self._client.request(method, url, **kwargs))

        def get(self, url: str, **kwargs: Any) -> httpx.Response:
            return self._runner.call(self._client.get(url, **kwargs))

        def post(self, url: str, **kwargs: Any) -> httpx.Response:
            return self._runner.call(self._client.post(url, **kwargs))

        def put(self, url: str, **kwargs: Any) -> httpx.Response:
            return self._runner.call(self._client.put(url, **kwargs))

        def delete(self, url: str, **kwargs: Any) -> httpx.Response:
            return self._runner.call(self._client.delete(url, **kwargs))

        def close(self) -> None:
            try:
                self._runner.call(self._client.aclose())
            finally:
                self._runner.close()

        def __enter__(self) -> _LocalSyncClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401 - standard signature
            self.close()

        def __getattr__(self, item: str) -> Any:
            return getattr(self._client, item)

    def client_factory(*args: Any, **kwargs: Any):
        base_url = kwargs.get("base_url")
        if base_url is None and args:
            base_url = args[0]
        app = resolve_app(base_url)
        if app is not None:
            async_kwargs = dict(kwargs)
            if "base_url" not in async_kwargs and base_url is not None:
                async_kwargs["base_url"] = base_url
            async_kwargs["transport"] = httpx.ASGITransport(app=app)
            async_client = original_async_client(*args, **async_kwargs)
            return _LocalSyncClient(async_client)
        return original_client(*args, **kwargs)

    def async_client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        base_url = kwargs.get("base_url")
        if base_url is None and args:
            base_url = args[0]
        app = resolve_app(base_url)
        if app is not None:
            kwargs["transport"] = httpx.ASGITransport(app=app)
            if "base_url" not in kwargs:
                kwargs["base_url"] = base_url
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    monkeypatch.setattr(httpx, "AsyncClient", async_client_factory)
    try:
        yield
    finally:
        monkeypatch.setattr(httpx, "Client", original_client)
        monkeypatch.setattr(httpx, "AsyncClient", original_async_client)


def test_bootstrap_demo_flow(local_app_map):
    urls, alerts_storage, _, _ = local_app_map

    # Clear cached alert engine client to ensure patched transport is used
    dashboard_module = importlib.import_module("services.web_dashboard.app.main")
    cache_clear = getattr(dashboard_module._alerts_client_factory, "cache_clear", None)  # type: ignore[attr-defined]
    if callable(cache_clear):
        cache_clear()

    args = [
        "BTCUSDT",
        "0.5",
        "--auth-url",
        urls["auth"],
        "--user-url",
        urls["user"],
        "--algo-url",
        urls["algo"],
        "--order-router-url",
        urls["order_router"],
        "--reports-url",
        urls["reports"],
        "--billing-url",
        urls["billing"],
        "--dashboard-url",
        urls["dashboard"],
        "--streaming-url",
        urls["streaming"],
        "--alerts-token",
        "demo-alerts-token",
        "--streaming-token",
        "reports-token",
        "--password",
        "P@ssw0rd123!",
    ]

    summary = bootstrap_demo.run(args)

    email = "demo.trader@example.com"

    assert summary["auth"]["registration"]["email"] == email
    assert summary["auth"]["me"]["email"] == email

    user_section = summary["user"]
    assert user_section["email"] == email
    assert user_section["profile"]["is_active"] is True

    tokens = summary["tokens"]
    assert "access_token" in tokens and tokens["access_token"]
    assert "refresh_token" in tokens and tokens["refresh_token"]

    strategy = summary["strategy"]
    assert strategy["name"] == "Bootstrap Trend Follower"
    assert strategy["parameters"]["symbol"] == "BTCUSDT"

    order = summary["order"]
    assert order["symbol"] == "BTCUSDT"
    assert float(order["quantity"]) == pytest.approx(0.5)
    assert order["status"] == "filled"

    report = summary["report"]
    assert report["content_type"] == "application/pdf"
    assert report["size_bytes"] > 0

    alert = summary["alert"]
    assert alert["title"].startswith("BTCUSDT order executed")
    assert alerts_storage and alerts_storage[0]["id"] == alert["id"]

    stream = summary["stream"]
    assert stream == {"status": "queued"}

    streaming_module = importlib.import_module("services.streaming.app.main")
    bridge = streaming_module.app.state.bridge  # type: ignore[attr-defined]
    queue = bridge._publisher._queue  # type: ignore[attr-defined]
    queued_event = asyncio.run(queue.get())
    assert queued_event.room_id == "public-room"
    assert queued_event.payload["symbol"] == "BTCUSDT"
