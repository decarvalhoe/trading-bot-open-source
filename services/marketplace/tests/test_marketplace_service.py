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
from services.marketplace.app.service import ListingSortOption

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def disable_entitlements_middleware() -> None:
    app.user_middleware = [
        mw for mw in app.user_middleware if mw.cls.__name__ != "EntitlementsMiddleware"
    ]
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
    response = client.post(
        "/marketplace/listings", json=payload, headers={"x-user-id": "creator-1"}
    )
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
    response = client.post(
        "/marketplace/listings", json=payload, headers={"x-user-id": "creator-1"}
    )
    assert response.status_code == 201, response.text
    listing_id = response.json()["id"]
    assert response.json()["versions"][0]["version"] == "1.0.0"
    assert response.json()["status"] == "approved"
    assert "All automated checks passed" in response.json()["review_notes"]

    entitlements_state["value"] = Entitlements(
        customer_id="investor-9",
        features={"can.copy_trade": True},
        quotas={},
    )
    copy_payload = {
        "listing_id": listing_id,
        "payment_reference": "pi_123",
        "leverage": 1.5,
        "allocated_capital": 2500.0,
        "risk_limits": {"max_notional": 3000},
    }
    copy_response = client.post(
        "/marketplace/copies",
        json=copy_payload,
        headers={"x-user-id": "investor-9"},
    )
    assert copy_response.status_code == 201, copy_response.text
    subscription = copy_response.json()
    assert subscription["listing_id"] == listing_id
    assert subscription["payment_reference"] == "pi_123"
    assert subscription["status"] == "active"
    assert subscription["connect_transfer_reference"] is None
    assert subscription["leverage"] == pytest.approx(1.5)
    assert subscription["allocated_capital"] == pytest.approx(2500.0)
    assert subscription["risk_limits"]["max_notional"] == 3000
    assert subscription["replication_status"] == "pending"
    assert subscription["total_fees_paid"] == pytest.approx(0.0)
    assert subscription["strategy_name"] == "Momentum Edge"
    assert subscription["leader_id"] == "creator-1"

    copies_response = client.get("/marketplace/copies", headers={"x-user-id": "investor-9"})
    assert copies_response.status_code == 200
    assert len(copies_response.json()) == 1
    returned = copies_response.json()[0]
    assert returned["strategy_name"] == "Momentum Edge"
    assert returned["leader_id"] == "creator-1"

    with SessionLocal() as db:
        listing = db.get(Listing, listing_id)
        assert listing is not None
        assert listing.strategy_name == "Momentum Edge"
        versions = db.scalars(select(ListingVersion.id)).all()
        assert versions, "Expected at least one stored version"
        audit_actions = db.scalars(select(AuditLog.action)).all()
        assert {"listing.created", "listing.copied"}.issubset(set(audit_actions))
        subscription_row = db.scalar(
            select(MarketplaceSubscription).where(MarketplaceSubscription.listing_id == listing_id)
        )
        assert subscription_row is not None
        assert subscription_row.leverage == pytest.approx(1.5)
        assert subscription_row.allocated_capital == pytest.approx(2500.0)
        assert subscription_row.risk_limits.get("max_notional") == 3000


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
    resp = client.post(
        "/marketplace/listings", json=listing_payload, headers={"x-user-id": "creator-1"}
    )
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


def test_listing_rejected_when_automated_checks_fail(entitlements_state):
    entitlements_state["value"] = Entitlements(
        customer_id="creator-2",
        features={"can.publish_strategy": True},
        quotas={},
    )
    payload = {
        "strategy_name": "Risky Play",
        "description": "",
        "price_cents": 0,
        "currency": "USD",
        "connect_account_id": "not_connect",
    }
    response = client.post(
        "/marketplace/listings", json=payload, headers={"x-user-id": "creator-2"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "rejected"
    assert "Stripe Connect account id" in data["review_notes"]

    listings = client.get("/marketplace/listings")
    assert listings.status_code == 200
    assert all(item["id"] != data["id"] for item in listings.json())


def _grant_publish(monkeypatch_state, customer_id="creator-1"):
    monkeypatch_state["value"] = Entitlements(
        customer_id=customer_id,
        features={"can.publish_strategy": True},
        quotas={},
    )


def _publish_listing(payload: dict, actor_id: str = "creator-1") -> int:
    response = client.post("/marketplace/listings", json=payload, headers={"x-user-id": actor_id})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_listings_filters_and_sorting(entitlements_state):
    _grant_publish(entitlements_state, customer_id="creator-1")
    base_payload = {
        "description": "",
        "price_cents": 1000,
        "currency": "USD",
        "connect_account_id": "acct_test",
    }
    listings = [
        {
            **base_payload,
            "strategy_name": "Alpha",
            "price_cents": 1999,
            "performance_score": 1.2,
            "risk_score": 1.5,
        },
        {
            **base_payload,
            "strategy_name": "Bravo",
            "price_cents": 9900,
            "performance_score": 2.8,
            "risk_score": 2.0,
        },
        {
            **base_payload,
            "strategy_name": "Charlie",
            "price_cents": 5000,
            "performance_score": 1.8,
            "risk_score": 0.9,
        },
    ]
    for payload in listings:
        _publish_listing(payload)

    response = client.get(
        "/marketplace/listings",
        params={
            "min_performance": 1.5,
            "max_risk": 2.0,
            "sort": ListingSortOption.PRICE_ASC.value,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert [item["strategy_name"] for item in data] == ["Charlie", "Bravo"]
    assert all(item["performance_score"] >= 1.5 for item in data)
    assert all(item["risk_score"] <= 2.0 for item in data)

    search_resp = client.get("/marketplace/listings", params={"search": "alpha"})
    assert search_resp.status_code == 200
    assert [item["strategy_name"] for item in search_resp.json()] == ["Alpha"]


def test_reviews_flow_updates_listing_metrics(entitlements_state):
    _grant_publish(entitlements_state, customer_id="creator-reviewer")
    payload = {
        "strategy_name": "Delta",
        "description": "",
        "price_cents": 2500,
        "currency": "USD",
        "connect_account_id": "acct_delta",
        "performance_score": 2.5,
        "risk_score": 1.1,
    }
    listing_id = _publish_listing(payload, actor_id="creator-reviewer")

    entitlements_state["value"] = Entitlements(
        customer_id="investor-1",
        features={},
        quotas={},
    )
    review_payload = {"rating": 4, "comment": "Solide exécution"}
    review_resp = client.post(
        f"/marketplace/listings/{listing_id}/reviews",
        json=review_payload,
        headers={"x-user-id": "investor-1"},
    )
    assert review_resp.status_code == 201, review_resp.text
    first_review = review_resp.json()
    assert first_review["rating"] == 4

    update_payload = {"rating": 5, "comment": "Encore mieux avec la V2"}
    update_resp = client.post(
        f"/marketplace/listings/{listing_id}/reviews",
        json=update_payload,
        headers={"x-user-id": "investor-1"},
    )
    assert update_resp.status_code == 201
    assert update_resp.json()["rating"] == 5

    listing_resp = client.get(f"/marketplace/listings/{listing_id}")
    assert listing_resp.status_code == 200
    listing = listing_resp.json()
    assert listing["reviews_count"] == 1
    assert listing["average_rating"] == 5

    reviews_resp = client.get(f"/marketplace/listings/{listing_id}/reviews")
    assert reviews_resp.status_code == 200
    reviews = reviews_resp.json()
    assert len(reviews) == 1
    assert reviews[0]["comment"].startswith("Encore mieux")
