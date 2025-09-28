from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from infra import AuditLog, Listing, ListingVersion, MarketplaceSubscription
from libs.db.db import SessionLocal
from libs.entitlements.client import Entitlements

from services.marketplace.app.dependencies import get_entitlements
from services.marketplace.app.main import app

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def disable_entitlements_middleware() -> None:
    app.user_middleware = [mw for mw in app.user_middleware if mw.cls.__name__ != "EntitlementsMiddleware"]
    app.middleware_stack = app.build_middleware_stack()



def _clear_marketplace_tables(db: Session) -> None:
    db.execute(delete(MarketplaceSubscription))
    db.execute(delete(ListingVersion))
    db.execute(delete(Listing))
    db.execute(delete(AuditLog))
    db.commit()


@pytest.fixture(autouse=True)
def clean_database() -> None:
    with SessionLocal() as db:
        _clear_marketplace_tables(db)
    yield
    with SessionLocal() as db:
        _clear_marketplace_tables(db)


@pytest.fixture
def entitlements_state():
    state = {"value": None}

    def override_entitlements():
        if state["value"] is None:
            raise HTTPException(status_code=403, detail="Entitlements override missing")
        return state["value"]

    app.dependency_overrides[get_entitlements] = override_entitlements
    try:
        yield state
    finally:
        app.dependency_overrides.pop(get_entitlements, None)


def test_publish_listing_requires_capability():
    payload = {
        "strategy_name": "Mean Reversion Alpha",
        "description": "Daily swing trades",
        "price_cents": 9900,
        "currency": "EUR",
        "connect_account_id": "acct_123",
    }
    response = client.post("/marketplace/listings", json=payload, headers={"x-user-id": "creator-1"})
    assert response.status_code == 403


def test_publish_and_copy_flow(entitlements_state):
    entitlements_state["value"] = Entitlements(
        customer_id="creator-1",
        features={"can.publish_strategy": True},
        quotas={},
    )
    payload = {
        "strategy_name": "Momentum Edge",
        "description": "1h breakout entries",
        "price_cents": 19900,
        "currency": "USD",
        "connect_account_id": "acct_creator",
        "initial_version": {"version": "1.0.0", "configuration": {"risk": 2}},
    }
    response = client.post("/marketplace/listings", json=payload, headers={"x-user-id": "creator-1"})
    assert response.status_code == 201, response.text
    listing_id = response.json()["id"]
    assert response.json()["versions"][0]["version"] == "1.0.0"

    entitlements_state["value"] = Entitlements(
        customer_id="investor-9",
        features={"can.copy_trade": True},
        quotas={},
    )
    copy_payload = {"listing_id": listing_id, "payment_reference": "pi_123"}
    copy_response = client.post(
        "/marketplace/copies",
        json=copy_payload,
        headers={"x-user-id": "investor-9"},
    )
    assert copy_response.status_code == 201, copy_response.text
    subscription = copy_response.json()
    assert subscription["listing_id"] == listing_id
    assert subscription["payment_reference"] == "pi_123"

    copies_response = client.get("/marketplace/copies", headers={"x-user-id": "investor-9"})
    assert copies_response.status_code == 200
    assert len(copies_response.json()) == 1

    with SessionLocal() as db:
        listing = db.get(Listing, listing_id)
        assert listing is not None
        assert listing.strategy_name == "Momentum Edge"
        versions = db.scalars(select(ListingVersion.id)).all()
        assert versions, "Expected at least one stored version"
        audit_actions = db.scalars(select(AuditLog.action)).all()
        assert {"listing.created", "listing.copied"}.issubset(set(audit_actions))


def test_only_owner_can_publish_new_version(entitlements_state):
    entitlements_state["value"] = Entitlements(
        customer_id="creator-1",
        features={"can.publish_strategy": True},
        quotas={},
    )
    listing_payload = {
        "strategy_name": "Scalper",
        "description": "Fast entries",
        "price_cents": 5000,
        "currency": "USD",
        "connect_account_id": "acct_1",
    }
    resp = client.post("/marketplace/listings", json=listing_payload, headers={"x-user-id": "creator-1"})
    listing_id = resp.json()["id"]

    entitlements_state["value"] = Entitlements(
        customer_id="intruder",
        features={"can.publish_strategy": True},
        quotas={},
    )
    version_resp = client.post(
        f"/marketplace/listings/{listing_id}/versions",
        json={"version": "2.0.0", "configuration": {}},
        headers={"x-user-id": "other-user"},
    )
    assert version_resp.status_code == 403

    entitlements_state["value"] = Entitlements(
        customer_id="creator-1",
        features={"can.publish_strategy": True},
        quotas={},
    )
    ok_resp = client.post(
        f"/marketplace/listings/{listing_id}/versions",
        json={"version": "2.0.0", "configuration": {}},
        headers={"x-user-id": "creator-1"},
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["versions"][0]["version"] == "2.0.0"
