from __future__ import annotations

import anyio
import contextlib
import functools
import hmac
import json
import sys
import time
import types
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping

import httpx
import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from schemas.market import ExecutionVenue, OrderSide, OrderType
from schemas.order_router import ExecutionIntent, RiskOverrides


class _ClosableASGITransport(httpx.ASGITransport):
    def close(self) -> None:  # type: ignore[override]
        return None

    def handle_request(self, request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        async def _call() -> tuple[int, httpx.Headers, bytes, dict[str, object]]:
            response = await super(_ClosableASGITransport, self).handle_async_request(request)
            try:
                body = await response.aread()
            finally:
                await response.aclose()
            return (
                response.status_code,
                response.headers,
                body,
                dict(response.extensions),
            )

        status_code, headers, body, extensions = anyio.run(_call)
        return httpx.Response(
            status_code=status_code,
            headers=headers,
            content=body,
            extensions=extensions,
            request=request,
        )


def _post_subscription(
    client: TestClient,
    *,
    plan_code: str,
    customer_id: str,
    webhook_secret: str,
) -> None:
    event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": f"sub_{customer_id}",
                "customer": customer_id,
                "status": "active",
                "plan": {
                    "id": f"price_{plan_code}",
                    "nickname": plan_code,
                    "product": "demo-product",
                },
                "current_period_end": int(time.time()) + 30 * 24 * 3600,
            }
        },
    }
    body = json.dumps(event, separators=(",", ":"))
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{body}".encode()
    signature = hmac.new(
        webhook_secret.encode(), msg=signed_payload, digestmod=sha256
    ).hexdigest()
    headers = {"stripe-signature": f"t={timestamp},v1={signature}"}
    response = client.post("/webhooks/stripe", data=body, headers=headers)
    assert response.status_code < 400, response.text


class _DummyAsyncClient:
    async def aclose(self) -> None:  # pragma: no cover - trivial helper
        return None


class _DummyMarketClient(_DummyAsyncClient):
    async def fetch_context(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "price": 0.0}


class _DummyReportsClient(_DummyAsyncClient):
    async def fetch_context(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "pnl": 0.0}


class _DummyPublisher(_DummyAsyncClient):
    async def publish(self, payload: dict[str, Any]) -> None:
        return None


class _DummyStreamProcessor:
    async def start(self, symbols: list[str] | tuple[str, ...]) -> None:
        return None

    async def stop(self) -> None:
        return None


@pytest.mark.end_to_end
def test_bootstrap_demo_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.PathLike[str]) -> None:
    plan_code = "demo-enterprise"
    email = "demo.trader@example.com"
    password = "BootstrapPassw0rd!"
    symbol = "BTCUSDT"
    quantity = 0.1
    webhook_secret = "whsec_test"
    service_customer_id = "bootstrap-service"
    streaming_token = "reports-token"
    alerts_token = "demo-alerts-token"

    reports_dir = tmp_path / "reports"
    reports_db = tmp_path / "reports.db"
    alerts_db = tmp_path / "alerts.db"
    alerts_events_db = tmp_path / "alerts-events.db"

    monkeypatch.setenv("JWT_SECRET", "bootstrap-demo-secret")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", webhook_secret)
    monkeypatch.setenv("STREAMING_SERVICE_TOKEN_REPORTS", streaming_token)
    monkeypatch.setenv("WEB_DASHBOARD_ALERTS_TOKEN", alerts_token)
    monkeypatch.setenv("WEB_DASHBOARD_ALERT_ENGINE_URL", "http://alerts-engine.local")
    monkeypatch.setenv("REPORTS_STORAGE_PATH", str(reports_dir))
    monkeypatch.setenv("REPORTS_DATABASE_URL", f"sqlite+pysqlite:///{reports_db}")
    monkeypatch.setenv("ALERT_ENGINE_DATABASE_URL", f"sqlite+pysqlite:///{alerts_db}")
    monkeypatch.setenv(
        "ALERT_ENGINE_EVENTS_DATABASE_URL", f"sqlite+pysqlite:///{alerts_events_db}"
    )

    from services.reports.app import config as reports_config
    from services.streaming.app import config as streaming_config

    reports_config.get_settings.cache_clear()
    streaming_config.get_settings.cache_clear()

    if "python_multipart" not in sys.modules:
        multipart_module = types.ModuleType("python_multipart")
        multipart_module.__version__ = "0.0.20"
        sys.modules.setdefault("python_multipart", multipart_module)

    from services.auth_service.app import models as auth_models
    from services.auth_service.app import security as auth_security
    from services.user_service.app import main as user_main

    auth_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    user_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    auth_models.Base.metadata.create_all(bind=auth_engine)
    user_main.Base.metadata.create_all(bind=user_engine)

    AuthSessionLocal = sessionmaker(bind=auth_engine, autoflush=False, autocommit=False, future=True)
    UserSessionLocal = sessionmaker(bind=user_engine, autoflush=False, autocommit=False, future=True)

    def _auth_get_db():
        session = AuthSessionLocal()
        try:
            yield session
        finally:
            session.close()

    def _user_get_db():
        session = UserSessionLocal()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(
        auth_security,
        "hash_password",
        lambda password: f"hashed::{password}",
    )
    monkeypatch.setattr(
        auth_security,
        "verify_password",
        lambda password, hashed: hashed == f"hashed::{password}",
    )
    original_jwt_encode = auth_security.jwt.encode

    def _encode(payload: dict, key: str, algorithm: str, *args, **kwargs):
        coerced = dict(payload)
        if "sub" in coerced:
            coerced["sub"] = str(coerced["sub"])
        return original_jwt_encode(coerced, key, algorithm=algorithm, *args, **kwargs)

    monkeypatch.setattr(auth_security.jwt, "encode", _encode)

    original_verify_token = auth_security.verify_token

    def _verify_token(token: str) -> dict:
        payload = original_verify_token(token)
        sub = payload.get("sub")
        if isinstance(sub, str) and sub.isdigit():
            payload["sub"] = int(sub)
        return payload

    monkeypatch.setattr(auth_security, "verify_token", _verify_token)

    from services.billing_service.app.main import app as billing_app
    from services.auth_service.app.main import app as auth_app
    from services.user_service.app.main import app as user_app
    from services.algo_engine.app.main import app as algo_app
    from services.order_router.app.main import app as order_router_app
    from services.reports.app import main as reports_main
    from services.reports.app.main import app as reports_app
    from services.streaming.app.main import create_app as create_streaming_app
    from services.alert_engine.app.config import AlertEngineSettings
    from services.alert_engine.app.main import create_app as create_alert_engine_app
    from services.web_dashboard.app import main as dashboard_main
    from services.web_dashboard.app.alerts_client import AlertsEngineClient
    from services.web_dashboard.app.main import app as dashboard_app
    from libs.entitlements.client import Entitlements
    import libs.entitlements.client as entitlements_client

    from services.auth_service.app.main import get_db as auth_get_db
    from services.user_service.app.main import get_db as user_get_db

    auth_app.dependency_overrides[auth_get_db] = _auth_get_db
    user_app.dependency_overrides[user_get_db] = _user_get_db

    generated_at = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    def _fake_build_render_payload(request, session, render_symbol):
        context = {
            "title": f"{render_symbol} strategy report",
            "report": {"symbol": render_symbol, "daily": None, "intraday": None},
            "generated_at": generated_at,
        }
        return "bootstrap-symbol-report.html", context

    def _fake_render_template(name: str, **context: object) -> str:
        payload = {
            "template": name,
            "title": context.get("title"),
            "symbol": (context.get("report") or {}).get("symbol"),
            "generated_at": generated_at.isoformat(),
        }
        return json.dumps(payload, separators=(",", ":"))

    def _fake_render_pdf(html: str) -> bytes:
        return b"%PDF-1.4\n" + html.encode("utf-8") + b"\n%%EOF"

    monkeypatch.setattr(reports_main, "_build_render_payload", _fake_build_render_payload)
    monkeypatch.setattr(reports_main, "_render_template", _fake_render_template)
    monkeypatch.setattr(reports_main, "_render_pdf", _fake_render_pdf)

    alert_settings = AlertEngineSettings(
        database_url=f"sqlite+pysqlite:///{alerts_db}",
        events_database_url=f"sqlite+pysqlite:///{alerts_events_db}",
        market_data_url="http://market-data",
        market_data_stream_url="http://market-data",
        reports_url="http://reports",
        notification_url="http://notification",
        evaluation_interval_seconds=15.0,
        market_snapshot_ttl_seconds=30.0,
        market_event_ttl_seconds=2.0,
        reports_ttl_seconds=60.0,
        stream_symbols=(),
    )

    alert_app = create_alert_engine_app(
        settings=alert_settings,
        market_client=_DummyMarketClient(),
        reports_client=_DummyReportsClient(),
        publisher=_DummyPublisher(),
        stream_processor=_DummyStreamProcessor(),
        start_background_tasks=False,
    )

    streaming_app = create_streaming_app()

    alert_transport = _ClosableASGITransport(app=alert_app)

    def _alerts_client_factory() -> AlertsEngineClient:
        return AlertsEngineClient(
            base_url="http://alerts-engine.local",
            timeout=5.0,
            transport=alert_transport,
        )

    dashboard_client_factory = functools.lru_cache(maxsize=1)(_alerts_client_factory)
    monkeypatch.setattr(dashboard_main, "_alerts_client_factory", dashboard_client_factory)
    monkeypatch.setattr(dashboard_main, "get_alerts_client", lambda: dashboard_client_factory())

    original_create_alert = AlertsEngineClient.create_alert

    def _create_alert_with_str_id(self: AlertsEngineClient, payload: Mapping[str, Any]):
        response_payload = original_create_alert(self, payload)
        if isinstance(response_payload, Mapping):
            coerced = dict(response_payload)
            if "id" in coerced:
                coerced["id"] = str(coerced["id"])
            return coerced
        return response_payload

    monkeypatch.setattr(AlertsEngineClient, "create_alert", _create_alert_with_str_id)
    async def _fake_require(self, customer_id, capabilities=None, quotas=None):
        features = {capability: True for capability in (capabilities or [])}
        quotas_map = {key: value for key, value in (quotas or {}).items()}
        return Entitlements(customer_id=str(customer_id), features=features, quotas=quotas_map)

    monkeypatch.setattr(entitlements_client.EntitlementsClient, "require", _fake_require)

    with contextlib.ExitStack() as stack:
        billing_client = stack.enter_context(TestClient(billing_app))
        auth_client = stack.enter_context(TestClient(auth_app))
        user_client = stack.enter_context(TestClient(user_app))
        algo_client = stack.enter_context(TestClient(algo_app))
        order_router_client = stack.enter_context(TestClient(order_router_app))
        reports_client = stack.enter_context(TestClient(reports_app))
        streaming_client = stack.enter_context(TestClient(streaming_app))
        stack.enter_context(TestClient(alert_app))
        dashboard_client = stack.enter_context(TestClient(dashboard_app))

        plan_payload = {"code": plan_code, "name": plan_code, "stripe_price_id": plan_code}
        response = billing_client.post("/billing/plans", json=plan_payload)
        assert response.status_code == 201, response.text

        for capability in [
            "can.use_auth",
            "can.use_users",
            "can.manage_strategies",
            "can.route_orders",
            "can.stream_public",
        ]:
            feature_payload = {"code": capability, "name": capability, "kind": "capability"}
            feature_resp = billing_client.post("/billing/features", json=feature_payload)
            assert feature_resp.status_code == 201, feature_resp.text
            mapping_payload = {
                "plan_code": plan_code,
                "feature_code": capability,
                "limit": None,
            }
            mapping_resp = billing_client.post(
                f"/billing/plans/{plan_code}/features", json=mapping_payload
            )
            assert mapping_resp.status_code == 202, mapping_resp.text

        quota_payload = {"code": "quota.active_algos", "name": "quota.active_algos", "kind": "quota"}
        quota_resp = billing_client.post("/billing/features", json=quota_payload)
        assert quota_resp.status_code == 201, quota_resp.text
        quota_mapping = {
            "plan_code": plan_code,
            "feature_code": "quota.active_algos",
            "limit": 5,
        }
        quota_map_resp = billing_client.post(
            f"/billing/plans/{plan_code}/features", json=quota_mapping
        )
        assert quota_map_resp.status_code == 202, quota_map_resp.text

        _post_subscription(
            billing_client,
            plan_code=plan_code,
            customer_id=service_customer_id,
            webhook_secret=webhook_secret,
        )

        auth_headers = {"x-customer-id": service_customer_id}
        registration_resp = auth_client.post(
            "/auth/register",
            json={"email": email, "password": password},
            headers=auth_headers,
        )
        assert registration_resp.status_code in {201, 409}, registration_resp.text
        registration_payload = (
            registration_resp.json() if registration_resp.status_code == 201 else None
        )

        login_resp = auth_client.post(
            "/auth/login",
            json={"email": email, "password": password},
            headers=auth_headers,
        )
        assert login_resp.status_code == 200, login_resp.text
        tokens = login_resp.json()
        assert "access_token" in tokens and "refresh_token" in tokens

        me_resp = auth_client.get(
            "/auth/me",
            headers={
                "Authorization": f"Bearer {tokens['access_token']}",
                "x-customer-id": service_customer_id,
            },
        )
        assert me_resp.status_code == 200, me_resp.text
        me_payload = me_resp.json()
        user_id = int(me_payload["id"])

        _post_subscription(
            billing_client,
            plan_code=plan_code,
            customer_id=str(user_id),
            webhook_secret=webhook_secret,
        )

        user_headers = {
            "Authorization": f"Bearer {tokens['access_token']}",
            "x-customer-id": str(user_id),
        }
        user_registration_resp = user_client.post(
            "/users/register",
            json={
                "email": email,
                "first_name": "Demo",
                "last_name": "Trader",
                "marketing_opt_in": True,
            },
            headers=user_headers,
        )
        assert user_registration_resp.status_code == 201, user_registration_resp.text
        user_registration = user_registration_resp.json()

        activation_resp = user_client.post(
            f"/users/{user_id}/activate",
            headers=user_headers,
        )
        assert activation_resp.status_code == 200, activation_resp.text
        activated_profile = activation_resp.json()

        strategy_resp = algo_client.post(
            "/strategies",
            json={
                "name": "Bootstrap Trend Follower",
                "strategy_type": "gap_fill",
                "parameters": {"gap_pct": 0.8, "fade_pct": 0.4, "symbol": symbol},
                "enabled": True,
                "tags": ["demo"],
                "metadata": {"source": "bootstrap-demo"},
            },
            headers={"x-customer-id": str(user_id)},
        )
        assert strategy_resp.status_code == 201, strategy_resp.text
        strategy_payload = strategy_resp.json()

        intent = ExecutionIntent(
            broker="binance",
            venue=ExecutionVenue.BINANCE_SPOT,
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=quantity,
            price=None,
            account_id=f"acct-{user_id}",
            risk=RiskOverrides(account_id=f"acct-{user_id}", realized_pnl=0.0),
            tags=["bootstrap-demo"],
        )
        order_resp = order_router_client.post(
            "/orders",
            json=intent.model_dump(mode="json", exclude_none=True),
            headers={"x-customer-id": str(user_id)},
        )
        assert order_resp.status_code == 201, order_resp.text
        order_payload = order_resp.json()

        report_resp = reports_client.post(
            f"/reports/{symbol}/render",
            json={"report_type": "symbol", "timeframe": "both"},
        )
        assert report_resp.status_code == 200, report_resp.text
        report_summary = {
            "content_type": report_resp.headers.get("content-type"),
            "size_bytes": len(report_resp.content),
            "storage_path": report_resp.headers.get("X-Report-Path"),
        }

        alert_payload = {
            "title": f"{symbol} order executed",
            "detail": f"Bootstrap routed {quantity} {symbol} ({OrderSide.BUY.value}).",
            "risk": "info",
            "symbol": symbol,
            "throttle_seconds": 900,
            "rule": {
                "symbol": symbol,
                "timeframe": "1h",
                "conditions": {
                    "pnl": {"enabled": True, "operator": "below", "value": -150.0},
                    "drawdown": {"enabled": True, "operator": "above", "value": 5.0},
                    "indicators": [],
                },
            },
            "channels": [
                {"type": "email", "target": "alerts@example.com", "enabled": True},
                {
                    "type": "webhook",
                    "target": "https://hooks.example.com/alerts",
                    "enabled": True,
                },
            ],
        }
        dashboard_alert_resp = dashboard_client.post(
            "/alerts",
            json=alert_payload,
            headers={"Authorization": f"Bearer {alerts_token}"},
        )
        assert dashboard_alert_resp.status_code == 201, dashboard_alert_resp.text
        alert_record = dashboard_alert_resp.json()

        stream_resp = streaming_client.post(
            "/ingest/reports",
            json={
                "room_id": "public-room",
                "source": "reports",
                "payload": {
                    "symbol": symbol,
                    "side": OrderSide.BUY.value,
                    "quantity": quantity,
                    "status": order_payload.get("status"),
                    "order_id": order_payload.get("order_id"),
                },
            },
            headers={"X-Service-Token": streaming_token},
        )
        assert stream_resp.status_code == 202, stream_resp.text
        stream_payload = stream_resp.json()

    assert registration_payload is None or registration_payload["email"] == email
    assert me_payload["email"] == email
    assert user_registration["email"] == email
    assert activated_profile["is_active"] is True
    assert strategy_payload["name"] == "Bootstrap Trend Follower"
    assert strategy_payload["strategy_type"] == "gap_fill"
    assert strategy_payload["parameters"]["symbol"] == symbol
    assert order_payload["symbol"].upper() == symbol
    assert pytest.approx(order_payload["quantity"], rel=0.01) == quantity
    assert report_summary["content_type"] == "application/pdf"
    assert report_summary["size_bytes"] > 0
    assert report_summary["storage_path"] is not None
    assert alert_record["rule"]["symbol"].upper() == symbol
    assert alert_record["title"] == alert_payload["title"]
    assert stream_payload == {"status": "queued"}

    summary = {
        "auth": {"registration": registration_payload, "me": me_payload},
        "user": {
            "id": user_id,
            "email": email,
            "registration": user_registration,
            "profile": activated_profile,
        },
        "tokens": tokens,
        "strategy": strategy_payload,
        "order": order_payload,
        "report": report_summary,
        "alert": alert_record,
        "stream": stream_payload,
    }

    assert summary["auth"]["me"]["email"] == email
    assert summary["stream"]["status"] == "queued"
