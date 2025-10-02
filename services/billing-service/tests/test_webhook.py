from __future__ import annotations

import hmac
import json
import os
import time
from hashlib import sha256
import importlib.util
import sys
from pathlib import Path
import types

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test")

from infra import EntitlementsBase, Subscription
from libs.db import db as db_module

MODULE_DIR = Path(__file__).resolve().parents[1]
PACKAGE_NAME = MODULE_DIR.name.replace('-', '_')
PACKAGE_ROOT = f"services.{PACKAGE_NAME}"

if PACKAGE_ROOT not in sys.modules:
    package = types.ModuleType(PACKAGE_ROOT)
    package.__path__ = [str(MODULE_DIR)]
    sys.modules[PACKAGE_ROOT] = package
    app_package = types.ModuleType(f"{PACKAGE_ROOT}.app")
    app_package.__path__ = [str(MODULE_DIR / 'app')]
    sys.modules[f"{PACKAGE_ROOT}.app"] = app_package

spec = importlib.util.spec_from_file_location(f"{PACKAGE_ROOT}.app.main", MODULE_DIR / 'app' / 'main.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
app = module.app


@pytest.fixture(autouse=True)
def setup_db():
    EntitlementsBase.metadata.create_all(bind=db_module.engine)
    try:
        yield
    finally:
        EntitlementsBase.metadata.drop_all(bind=db_module.engine)


def sign(payload: bytes, secret: str) -> str:
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    signature = hmac.new(secret.encode(), msg=signed_payload, digestmod=sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def test_subscription_upsert_through_webhook():
    client = TestClient(app)
    body = {
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_basic",
                "customer": "cus_123",
                "status": "active",
                "current_period_end": int(time.time()),
                "trial_end": int(time.time()) + 86400,
                "plan": {
                    "id": "price_basic",
                    "nickname": "basic",
                    "product": "prod_basic",
                    "interval": "month",
                    "trial_period_days": 14,
                },
            }
        },
    }
    payload = json.dumps(body).encode()
    headers = {"stripe-signature": sign(payload, os.environ["STRIPE_WEBHOOK_SECRET"])}

    response = client.post("/webhooks/stripe", data=payload, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"received": True}

    with db_module.SessionLocal() as session:
        sub = session.query(Subscription).filter_by(customer_id="cus_123").one()
        assert sub.status == "active"
        assert sub.plan.stripe_price_id == "price_basic"
        assert sub.plan.billing_interval == "monthly"
        assert sub.plan.trial_period_days == 14
        assert sub.trial_end is not None
        assert sub.connect_account_id is None
        assert sub.payment_reference == "sub_basic"


def test_webhook_extracts_connect_payout_details():
    client = TestClient(app)
    payment_intent_id = "pi_12345"
    body = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": "cus_789",
                "status": "active",
                "current_period_end": int(time.time()),
                "plan": {
                    "id": "price_premium",
                    "nickname": "premium",
                    "product": "prod_premium",
                    "interval": "year",
                },
                "latest_invoice": {
                    "id": "in_123",
                    "payment_intent": {
                        "id": payment_intent_id,
                        "transfer_data": {"destination": "acct_999"},
                        "charges": {
                            "data": [
                                {
                                    "id": "ch_1",
                                    "transfer": "tr_1",
                                }
                            ]
                        },
                    },
                },
            }
        },
    }
    payload = json.dumps(body).encode()
    headers = {"stripe-signature": sign(payload, os.environ["STRIPE_WEBHOOK_SECRET"])}

    response = client.post("/webhooks/stripe", data=payload, headers=headers)
    assert response.status_code == 200

    with db_module.SessionLocal() as session:
        sub = session.query(Subscription).filter_by(customer_id="cus_789").one()
        assert sub.plan.billing_interval == "annual"
        assert sub.connect_account_id == "acct_999"
        assert sub.payment_reference == "tr_1"
