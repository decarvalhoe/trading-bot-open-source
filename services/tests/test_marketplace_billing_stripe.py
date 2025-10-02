from __future__ import annotations

import hmac
import importlib.util
import hmac
import importlib.util
import json
import os
import sys
import time
import types
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test")
os.environ.setdefault("STRIPE_API_KEY", "sk_test_123")

from infra import AuditBase, EntitlementsBase, MarketplaceBase, Subscription
from libs.db import db as db_module
from libs.entitlements.client import Entitlements

# Dynamically load billing service app
BILLING_DIR = Path(__file__).resolve().parents[1] / "billing-service"
BILLING_PACKAGE = "services.billing_service"
if BILLING_PACKAGE not in sys.modules:
    package = types.ModuleType(BILLING_PACKAGE)
    package.__path__ = [str(BILLING_DIR)]
    sys.modules[BILLING_PACKAGE] = package
    app_package = types.ModuleType(f"{BILLING_PACKAGE}.app")
    app_package.__path__ = [str(BILLING_DIR / "app")]
    sys.modules[f"{BILLING_PACKAGE}.app"] = app_package

spec = importlib.util.spec_from_file_location(f"{BILLING_PACKAGE}.app.main", BILLING_DIR / "app" / "main.py")
billing_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = billing_module
spec.loader.exec_module(billing_module)
billing_app = billing_module.app

# Dynamically load marketplace app
MARKETPLACE_DIR = Path(__file__).resolve().parents[1] / "marketplace"
MARKETPLACE_PACKAGE = "services.marketplace"
if MARKETPLACE_PACKAGE not in sys.modules:
    package = types.ModuleType(MARKETPLACE_PACKAGE)
    package.__path__ = [str(MARKETPLACE_DIR)]
    sys.modules[MARKETPLACE_PACKAGE] = package
    app_package = types.ModuleType(f"{MARKETPLACE_PACKAGE}.app")
    app_package.__path__ = [str(MARKETPLACE_DIR / "app")]
    sys.modules[f"{MARKETPLACE_PACKAGE}.app"] = app_package

spec_marketplace = importlib.util.spec_from_file_location(
    f"{MARKETPLACE_PACKAGE}.app.main", MARKETPLACE_DIR / "app" / "main.py"
)
marketplace_module = importlib.util.module_from_spec(spec_marketplace)
sys.modules[spec_marketplace.name] = marketplace_module
spec_marketplace.loader.exec_module(marketplace_module)
marketplace_app = marketplace_module.app

from services.marketplace.app.dependencies import get_entitlements, get_payments_gateway
from services.marketplace.app.payments import (
    StripeConnectGateway,
    StripeSettings,
    StripeSubscriptionRequest,
    StripeSubscriptionResult,
)


class FakeStripeClient:
    def __init__(self) -> None:
        self.requests: list[StripeSubscriptionRequest] = []

    def create_subscription(self, request: StripeSubscriptionRequest) -> StripeSubscriptionResult:
        self.requests.append(request)
        return StripeSubscriptionResult(
            reference="sub_test_001", status="active", transfer_reference="tr_test_001"
        )


@pytest.fixture(autouse=True)
def setup_database():
    AuditBase.metadata.create_all(bind=db_module.engine)
    MarketplaceBase.metadata.create_all(bind=db_module.engine)
    EntitlementsBase.metadata.create_all(bind=db_module.engine)
    try:
        yield
    finally:
        AuditBase.metadata.drop_all(bind=db_module.engine)
        MarketplaceBase.metadata.drop_all(bind=db_module.engine)
        EntitlementsBase.metadata.drop_all(bind=db_module.engine)


@pytest.fixture
def marketplace_client():
    # Disable entitlements middleware to control dependency in tests
    marketplace_app.user_middleware = [
        mw for mw in marketplace_app.user_middleware if mw.cls.__name__ != "EntitlementsMiddleware"
    ]
    marketplace_app.middleware_stack = marketplace_app.build_middleware_stack()

    entitlements_state: dict[str, Entitlements | None] = {"value": None}

    def override_entitlements():
        ent = entitlements_state["value"]
        if ent is None:
            raise HTTPException(status_code=403, detail="Entitlements override missing")
        return ent

    fake_client = FakeStripeClient()
    fake_gateway = StripeConnectGateway(settings=StripeSettings(api_key="sk_test_123"), client=fake_client)

    marketplace_app.dependency_overrides[get_entitlements] = override_entitlements
    marketplace_app.dependency_overrides[get_payments_gateway] = lambda: fake_gateway

    client = TestClient(marketplace_app)
    client.entitlements_state = entitlements_state  # type: ignore[attr-defined]
    client.fake_gateway = fake_gateway  # type: ignore[attr-defined]
    client.fake_gateway_client = fake_client  # type: ignore[attr-defined]
    try:
        yield client
    finally:
        marketplace_app.dependency_overrides.pop(get_entitlements, None)
        marketplace_app.dependency_overrides.pop(get_payments_gateway, None)


@pytest.fixture
def billing_client():
    return TestClient(billing_app)


def sign(payload: bytes, secret: str) -> str:
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    signature = hmac.new(secret.encode(), msg=signed_payload, digestmod=sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def test_end_to_end_listing_and_subscription(marketplace_client: TestClient, billing_client: TestClient):
    entitlements_state = marketplace_client.entitlements_state  # type: ignore[attr-defined]
    fake_client = marketplace_client.fake_gateway_client  # type: ignore[attr-defined]
    assert isinstance(fake_client, FakeStripeClient)

    # Creator publishes a listing which is auto-reviewed
    entitlements_state["value"] = Entitlements(
        customer_id="creator-e2e",
        features={"can.publish_strategy": True},
        quotas={},
    )
    listing_payload = {
        "strategy_name": "Momentum Deluxe",
        "description": "",
        "price_cents": 2599,
        "currency": "USD",
        "connect_account_id": "acct_e2e",
        "initial_version": {"version": "1.0.0", "configuration": {"risk": 1}},
    }
    listing_response = marketplace_client.post(
        "/marketplace/listings", json=listing_payload, headers={"x-user-id": "creator-e2e"}
    )
    assert listing_response.status_code == 201, listing_response.text
    listing = listing_response.json()
    assert listing["status"] == "approved"
    assert "All automated checks passed" in listing["review_notes"]

    # Billing team provisions a plan with free trial and yearly billing
    plan_payload = {
        "code": "price_premium",
        "name": "Premium",
        "stripe_price_id": "price_premium",
        "description": "Premium yearly plan",
        "billing_interval": "annual",
        "trial_period_days": 7,
    }
    plan_resp = billing_client.post("/billing/plans", json=plan_payload)
    assert plan_resp.status_code == 201, plan_resp.text

    # Investor copies the listing triggering Stripe Connect flow
    entitlements_state["value"] = Entitlements(
        customer_id="investor-e2e",
        features={"can.copy_trade": True},
        quotas={},
    )
    subscription_resp = marketplace_client.post(
        "/marketplace/copies",
        json={"listing_id": listing["id"]},
        headers={"x-user-id": "investor-e2e"},
    )
    assert subscription_resp.status_code == 201, subscription_resp.text
    subscription = subscription_resp.json()
    assert subscription["status"] == "active"
    assert subscription["payment_reference"] == "sub_test_001"
    assert subscription["connect_transfer_reference"] == "tr_test_001"

    assert fake_client.requests
    stripe_request = fake_client.requests[-1]
    assert stripe_request.connect_account_id == listing_payload["connect_account_id"]
    assert stripe_request.subscriber_id == "investor-e2e"

    # Stripe notifies billing service of the subscription, including Connect details
    body = {
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_test_001",
                "customer": "investor-e2e",
                "status": "active",
                "current_period_end": int(time.time()) + 3600,
                "trial_end": int(time.time()) + 7 * 86400,
                "plan": {
                    "id": "price_premium",
                    "nickname": "Premium",
                    "product": "prod_premium",
                    "interval": "year",
                    "trial_period_days": 7,
                },
                "latest_invoice": {
                    "id": "in_test",
                    "payment_intent": {
                        "id": "pi_test",
                        "transfer_data": {"destination": "acct_e2e"},
                        "charges": {"data": [{"id": "ch_test", "transfer": "tr_test_001"}]},
                    },
                },
            }
        },
    }
    payload = json.dumps(body).encode()
    headers = {"stripe-signature": sign(payload, os.environ["STRIPE_WEBHOOK_SECRET"])}
    webhook_resp = billing_client.post("/webhooks/stripe", data=payload, headers=headers)
    assert webhook_resp.status_code == 200, webhook_resp.text

    with db_module.SessionLocal() as session:
        stored_subscription = (
            session.query(Subscription).filter_by(customer_id="investor-e2e", status="active").one()
        )
        assert stored_subscription.plan.billing_interval == "annual"
        assert stored_subscription.plan.trial_period_days == 7
        assert stored_subscription.connect_account_id == "acct_e2e"
        assert stored_subscription.payment_reference == "tr_test_001"
        assert stored_subscription.trial_end is not None
