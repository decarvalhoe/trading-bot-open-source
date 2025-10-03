#!/usr/bin/env python3
"""Bootstrap a complete demo flow against the local docker stack."""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import sys
from pathlib import Path
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable, Mapping

import httpx

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.market import ExecutionVenue, OrderSide, OrderType
from schemas.order_router import ExecutionIntent, ExecutionReport, RiskOverrides
from services.algo_engine.app.order_router_client import OrderRouterClient
from services.web_dashboard.app.alerts_client import AlertsEngineClient


def _running_inside_container() -> bool:
    """Return ``True`` when the script is executed from within a container."""

    docker_flags = {"IN_DOCKER", "DOCKER_CONTAINER", "RUNNING_IN_DOCKER"}
    if any(os.getenv(flag, "").lower() in {"1", "true", "yes"} for flag in docker_flags):
        return True

    if Path("/.dockerenv").exists():
        return True

    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return False

    return "docker" in content or "containerd" in content


def _service_default(env_var: str, *, docker_host: str, docker_port: int, local_port: int) -> str:
    """Return the appropriate default URL for a downstream service."""

    if value := os.getenv(env_var):
        return value

    if _running_inside_container():
        return f"http://{docker_host}:{docker_port}"

    return f"http://127.0.0.1:{local_port}"


@dataclass
class AuthTokens:
    """Container for authentication tokens issued by the auth service."""

    access_token: str
    refresh_token: str


class ServiceError(RuntimeError):
    """Raised when one of the downstream services rejects a request."""


class BillingClient:
    """Helper wrapping the billing service API to manage plans and subscriptions."""

    def __init__(
        self, base_url: str, *, timeout: float = 5.0, webhook_secret: str = "whsec_test"
    ) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self._webhook_secret = webhook_secret

    def close(self) -> None:
        self._client.close()

    def ensure_plan(
        self,
        *,
        plan_code: str,
        capabilities: Iterable[str],
        quotas: Mapping[str, int],
    ) -> None:
        payload = {"code": plan_code, "name": plan_code, "stripe_price_id": plan_code}
        response = self._client.post("/billing/plans", json=payload)
        if response.status_code >= 400:
            raise ServiceError(f"Unable to upsert plan {plan_code}: {response.text}")

        for capability in capabilities:
            self._upsert_feature(capability, kind="capability")
            self._attach_feature(plan_code, capability, limit=None)

        for quota_code, limit in quotas.items():
            self._upsert_feature(quota_code, kind="quota")
            self._attach_feature(plan_code, quota_code, limit=limit)

    def _upsert_feature(self, code: str, *, kind: str) -> None:
        payload = {"code": code, "name": code, "kind": kind}
        response = self._client.post("/billing/features", json=payload)
        if response.status_code >= 400:
            raise ServiceError(f"Unable to upsert feature {code}: {response.text}")

    def _attach_feature(self, plan_code: str, feature_code: str, *, limit: int | None) -> None:
        payload = {"plan_code": plan_code, "feature_code": feature_code, "limit": limit}
        response = self._client.post(f"/billing/plans/{plan_code}/features", json=payload)
        if response.status_code >= 400:
            raise ServiceError(
                f"Unable to attach feature {feature_code} to plan {plan_code}: {response.text}"
            )

    def ensure_subscription(self, *, plan_code: str, customer_id: str) -> None:
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
            self._webhook_secret.encode(), msg=signed_payload, digestmod=sha256
        ).hexdigest()
        headers = {"stripe-signature": f"t={timestamp},v1={signature}"}
        response = self._client.post("/webhooks/stripe", content=body, headers=headers)
        if response.status_code >= 400:
            raise ServiceError(
                f"Unable to register subscription for {customer_id}: {response.text}"
            )


class AuthServiceClient:
    """Client orchestrating registration and login flows on the auth service."""

    def __init__(self, base_url: str, *, timeout: float = 5.0, customer_id: str) -> None:
        headers = {"x-customer-id": customer_id}
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    def register(self, *, email: str, password: str) -> dict[str, Any] | None:
        response = self._client.post("/auth/register", json={"email": email, "password": password})
        if response.status_code == 201:
            return response.json()
        if response.status_code == 409:
            return None
        raise ServiceError(f"Auth register failed: {response.text}")

    def login(self, *, email: str, password: str) -> AuthTokens:
        response = self._client.post("/auth/login", json={"email": email, "password": password})
        if response.status_code >= 400:
            raise ServiceError(f"Auth login failed: {response.text}")
        payload = response.json()
        return AuthTokens(
            access_token=payload["access_token"], refresh_token=payload["refresh_token"]
        )

    def me(self, *, access_token: str) -> dict[str, Any]:
        response = self._client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        if response.status_code >= 400:
            raise ServiceError(f"Fetching /auth/me failed: {response.text}")
        return response.json()


class UserServiceClient:
    """Client targeting the user-service REST API."""

    def __init__(
        self, base_url: str, *, timeout: float = 5.0, access_token: str, customer_id: int
    ) -> None:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "x-customer-id": str(customer_id),
        }
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    def register(self, *, email: str, first_name: str, last_name: str) -> dict[str, Any]:
        payload = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "marketing_opt_in": True,
        }
        response = self._client.post("/users/register", json=payload)
        if response.status_code >= 400:
            raise ServiceError(f"User register failed: {response.text}")
        return response.json()

    def activate(self, user_id: int) -> dict[str, Any]:
        response = self._client.post(f"/users/{user_id}/activate")
        if response.status_code >= 400:
            raise ServiceError(f"User activation failed: {response.text}")
        return response.json()


class AlgoEngineClient:
    """Client calling the algo-engine strategy endpoints."""

    def __init__(self, base_url: str, *, timeout: float = 5.0, customer_id: int) -> None:
        headers = {"x-customer-id": str(customer_id)}
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    def create_strategy(
        self,
        *,
        name: str,
        strategy_type: str,
        parameters: Mapping[str, Any],
        enabled: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "strategy_type": strategy_type,
            "parameters": dict(parameters),
            "enabled": enabled,
            "tags": ["demo"],
            "metadata": {"source": "bootstrap-demo"},
        }
        response = self._client.post("/strategies", json=payload)
        if response.status_code >= 400:
            raise ServiceError(f"Strategy creation failed: {response.text}")
        return response.json()


class ReportsServiceClient:
    """Client for the reports service."""

    def __init__(self, base_url: str, *, timeout: float = 5.0) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def render(self, symbol: str, *, report_type: str = "symbol") -> dict[str, Any]:
        payload = {"report_type": report_type, "timeframe": "both"}
        response = self._client.post(f"/reports/{symbol}/render", json=payload)
        if response.status_code >= 400:
            raise ServiceError(f"Report generation failed: {response.text}")
        report_path = response.headers.get("X-Report-Path")
        return {
            "content_type": response.headers.get("content-type"),
            "size_bytes": len(response.content),
            "storage_path": report_path,
        }


class DashboardClient:
    """Client used to manage alerts through the dashboard facade."""

    def __init__(
        self, base_url: str, *, timeout: float = 5.0, alerts_token: str | None = None
    ) -> None:
        self._client = AlertsEngineClient(base_url=base_url.rstrip("/"), timeout=timeout)
        if alerts_token:
            self._client._client.headers.update({"Authorization": f"Bearer {alerts_token}"})

    def close(self) -> None:
        self._client.close()

    def create_alert(
        self,
        *,
        title: str,
        detail: str,
        risk: str = "info",
        symbol: str = "BTCUSDT",
        throttle_seconds: int = 900,
    ) -> Mapping[str, Any]:
        payload = {
            "title": title,
            "detail": detail,
            "risk": risk,
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
                {"type": "webhook", "target": "https://hooks.example.com/alerts", "enabled": True},
            ],
            "throttle_seconds": throttle_seconds,
        }
        return self._client.create_alert(payload)


class StreamingClient:
    """Client pushing events to the streaming ingest endpoint."""

    def __init__(
        self, base_url: str, *, timeout: float = 5.0, service_token: str | None = None
    ) -> None:
        headers: dict[str, str] = {}
        if service_token:
            headers["X-Service-Token"] = service_token
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    def publish(self, room_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        body = {"room_id": room_id, "source": "reports", "payload": dict(payload)}
        response = self._client.post("/ingest/reports", json=body)
        if response.status_code >= 400:
            raise ServiceError(f"Streaming publish failed: {response.text}")
        return response.json()


async def _route_order(
    *,
    order_router_url: str,
    customer_id: int,
    broker: str,
    venue: ExecutionVenue,
    symbol: str,
    side: OrderSide,
    order_type: OrderType,
    quantity: float,
    price: float | None,
) -> ExecutionReport:
    async with httpx.AsyncClient(
        base_url=order_router_url.rstrip("/"),
        timeout=5.0,
        headers={"x-customer-id": str(customer_id)},
    ) as client:
        router = OrderRouterClient(base_url=order_router_url, client=client)
        intent = ExecutionIntent(
            broker=broker,
            venue=venue,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            account_id=f"acct-{customer_id}",
            risk=RiskOverrides(account_id=f"acct-{customer_id}", realized_pnl=0.0),
            tags=["bootstrap-demo"],
        )
        report = await router.submit_order(intent)
        return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap the end-to-end demo flow")
    parser.add_argument("symbol", help="Trading symbol to route")
    parser.add_argument("quantity", type=float, help="Order quantity")
    parser.add_argument(
        "--broker", default="binance", help="Broker identifier for the order router"
    )
    parser.add_argument(
        "--venue",
        default=ExecutionVenue.BINANCE_SPOT.value,
        choices=[venue.value for venue in ExecutionVenue],
        help="Execution venue",
    )
    parser.add_argument(
        "--side",
        default=OrderSide.BUY.value,
        choices=[side.value for side in OrderSide],
        help="Order side",
    )
    parser.add_argument(
        "--order-type",
        default=OrderType.MARKET.value,
        choices=[order_type.value for order_type in OrderType],
        help="Order type",
    )
    parser.add_argument(
        "--price", type=float, default=None, help="Limit price when using limit orders"
    )
    parser.add_argument("--email", default="demo.trader@example.com", help="Demo account email")
    parser.add_argument(
        "--password", default="BootstrapPassw0rd!", help="Demo account password"
    )
    parser.add_argument(
        "--auth-url",
        default=_service_default(
            "BOOTSTRAP_AUTH_URL", docker_host="auth_service", docker_port=8000, local_port=8011
        ),
        help="Auth service base URL",
    )
    parser.add_argument(
        "--user-url",
        default=_service_default(
            "BOOTSTRAP_USER_URL", docker_host="user_service", docker_port=8000, local_port=8012
        ),
        help="User service base URL",
    )
    parser.add_argument(
        "--algo-url",
        default=_service_default(
            "BOOTSTRAP_ALGO_URL", docker_host="algo_engine", docker_port=8000, local_port=8014
        ),
        help="Algo engine base URL",
    )
    parser.add_argument(
        "--order-router-url",
        default=_service_default(
            "BOOTSTRAP_ORDER_ROUTER_URL",
            docker_host="order_router",
            docker_port=8000,
            local_port=8013,
        ),
        help="Order router base URL",
    )
    parser.add_argument(
        "--reports-url",
        default=_service_default(
            "BOOTSTRAP_REPORTS_URL", docker_host="reports", docker_port=8000, local_port=8016
        ),
        help="Reports service base URL",
    )
    parser.add_argument(
        "--billing-url",
        default=_service_default(
            "BOOTSTRAP_BILLING_URL",
            docker_host="billing_service",
            docker_port=8000,
            local_port=8005,
        ),
        help="Billing service base URL",
    )
    parser.add_argument(
        "--dashboard-url",
        default=_service_default(
            "BOOTSTRAP_DASHBOARD_URL", docker_host="web_dashboard", docker_port=8000, local_port=8022
        ),
        help="Web dashboard base URL",
    )
    parser.add_argument(
        "--streaming-url",
        default=_service_default(
            "BOOTSTRAP_STREAMING_URL", docker_host="streaming", docker_port=8000, local_port=8019
        ),
        help="Streaming service base URL",
    )
    parser.add_argument(
        "--plan-code",
        default=os.getenv("BOOTSTRAP_PLAN_CODE", "demo-enterprise"),
        help="Billing plan code used to assign entitlements",
    )
    parser.add_argument(
        "--service-customer-id",
        default=os.getenv("BOOTSTRAP_SERVICE_CUSTOMER", "bootstrap-service"),
        help="Customer identifier used when calling service endpoints",
    )
    parser.add_argument(
        "--alerts-token",
        default=os.getenv("WEB_DASHBOARD_ALERTS_TOKEN", "demo-alerts-token"),
        help="Bearer token required by the dashboard alert endpoints",
    )
    parser.add_argument(
        "--streaming-token",
        default=os.getenv("STREAMING_SERVICE_TOKEN_REPORTS", "reports-token"),
        help="Service token expected by the streaming ingest endpoint",
    )
    parser.add_argument(
        "--webhook-secret",
        default=os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test"),
        help="Stripe webhook secret configured on the billing service",
    )
    parser.add_argument(
        "--skip-billing-setup",
        action="store_true",
        help="Skip billing plan/subscription bootstrap (when the environment is already prepared)",
    )
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parse_args(argv)
    venue = ExecutionVenue(args.venue)
    side = OrderSide(args.side)
    order_type = OrderType(args.order_type)
    if order_type is OrderType.LIMIT and args.price is None:
        raise SystemExit("--price is required for limit orders")

    billing_client: BillingClient | None = None
    auth_client: AuthServiceClient | None = None
    user_client: UserServiceClient | None = None
    algo_client: AlgoEngineClient | None = None
    reports_client: ReportsServiceClient | None = None
    dashboard_client: DashboardClient | None = None
    streaming_client: StreamingClient | None = None

    try:
        if not args.skip_billing_setup:
            billing_client = BillingClient(args.billing_url, webhook_secret=args.webhook_secret)
            billing_client.ensure_plan(
                plan_code=args.plan_code,
                capabilities=[
                    "can.use_auth",
                    "can.use_users",
                    "can.manage_strategies",
                    "can.route_orders",
                    "can.stream_public",
                ],
                quotas={"quota.active_algos": 5},
            )
            billing_client.ensure_subscription(
                plan_code=args.plan_code, customer_id=args.service_customer_id
            )
        elif billing_client is None:
            billing_client = BillingClient(args.billing_url, webhook_secret=args.webhook_secret)

        auth_client = AuthServiceClient(args.auth_url, customer_id=args.service_customer_id)

        registration = auth_client.register(email=args.email, password=args.password)
        tokens = auth_client.login(email=args.email, password=args.password)
        profile = auth_client.me(access_token=tokens.access_token)
        user_id = int(profile["id"])

        if billing_client is not None:
            billing_client.ensure_subscription(plan_code=args.plan_code, customer_id=str(user_id))

        user_client = UserServiceClient(
            args.user_url,
            access_token=tokens.access_token,
            customer_id=user_id,
        )
        user_profile = user_client.register(
            email=args.email,
            first_name="Demo",
            last_name="Trader",
        )
        activated_profile = user_client.activate(user_id)

        algo_client = AlgoEngineClient(args.algo_url, customer_id=user_id)
        strategy = algo_client.create_strategy(
            name="Bootstrap Trend Follower",
            strategy_type="gap_fill",
            parameters={"gap_pct": 0.8, "fade_pct": 0.4, "symbol": args.symbol},
            enabled=True,
        )

        report = asyncio.run(
            _route_order(
                order_router_url=args.order_router_url,
                customer_id=user_id,
                broker=args.broker,
                venue=venue,
                symbol=args.symbol,
                side=side,
                order_type=order_type,
                quantity=args.quantity,
                price=args.price,
            )
        )

        reports_client = ReportsServiceClient(args.reports_url)
        rendered_report = reports_client.render(args.symbol)

        dashboard_client = DashboardClient(args.dashboard_url, alerts_token=args.alerts_token)
        alert_payload = dashboard_client.create_alert(
            title=f"{args.symbol} order executed",
            detail=f"Bootstrap routed {args.quantity} {args.symbol} ({side.value}).",
            risk="info",
            symbol=args.symbol,
            throttle_seconds=900,
        )

        streaming_client = StreamingClient(args.streaming_url, service_token=args.streaming_token)
        stream_response = streaming_client.publish(
            room_id="public-room",
            payload={
                "symbol": args.symbol,
                "side": side.value,
                "quantity": args.quantity,
                "status": report.status.value,
                "order_id": report.order_id,
            },
        )

        summary = {
            "auth": {
                "registration": registration,
                "me": profile,
            },
            "user": {
                "id": user_id,
                "email": args.email,
                "registration": user_profile,
                "profile": activated_profile,
            },
            "tokens": {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
            },
            "strategy": strategy,
            "order": report.model_dump(mode="json"),
            "report": rendered_report,
            "alert": dict(alert_payload),
            "stream": stream_response,
        }
        return summary
    finally:
        for client in [
            streaming_client,
            dashboard_client,
            reports_client,
            algo_client,
            user_client,
            auth_client,
            billing_client,
        ]:
            if client is None:
                continue
            close = getattr(client, "close", None)
            if callable(close):
                close()


def main(argv: list[str] | None = None) -> None:
    summary = run(argv)
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
