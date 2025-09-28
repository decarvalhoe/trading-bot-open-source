from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from infra import Activity, AuditLog, Follow, Leaderboard, Profile
from libs.db.db import SessionLocal
from libs.entitlements.client import Entitlements

from services.social.app.dependencies import get_entitlements
from services.social.app.main import app

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def disable_entitlements_middleware() -> None:
    app.user_middleware = [mw for mw in app.user_middleware if mw.cls.__name__ != "EntitlementsMiddleware"]
    app.middleware_stack = app.build_middleware_stack()



def _clear_social_tables(db: Session) -> None:
    db.execute(delete(Follow))
    db.execute(delete(Activity))
    db.execute(delete(Profile))
    db.execute(delete(Leaderboard))
    db.execute(delete(AuditLog))
    db.commit()


@pytest.fixture(autouse=True)
def clean_database() -> None:
    with SessionLocal() as db:
        _clear_social_tables(db)
    yield
    with SessionLocal() as db:
        _clear_social_tables(db)


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


def test_profile_update_requires_capability():
    payload = {
        "display_name": "Alpha Trader",
        "bio": "Loves market micro-structure",
        "avatar_url": None,
        "is_public": True,
    }
    response = client.put("/social/profiles/me", json=payload, headers={"x-user-id": "creator-1"})
    assert response.status_code == 403


def test_social_flow(entitlements_state):
    entitlements_state["value"] = Entitlements(
        customer_id="creator-1",
        features={"can.publish_strategy": True},
        quotas={},
    )
    profile_payload = {
        "display_name": "Creator One",
        "bio": "Trend following",
        "avatar_url": "https://example.com/avatar.png",
        "is_public": True,
    }
    profile_resp = client.put(
        "/social/profiles/me",
        json=profile_payload,
        headers={"x-user-id": "creator-1"},
    )
    assert profile_resp.status_code == 200
    assert profile_resp.json()["display_name"] == "Creator One"

    entitlements_state["value"] = Entitlements(
        customer_id="follower-9",
        features={"can.publish_strategy": True},
        quotas={},
    )
    follower_profile = {
        "display_name": "Follower Nine",
        "bio": "Copy trading fan",
        "avatar_url": None,
        "is_public": True,
    }
    client.put(
        "/social/profiles/me",
        json=follower_profile,
        headers={"x-user-id": "follower-9"},
    )

    entitlements_state["value"] = Entitlements(
        customer_id="follower-9",
        features={"can.copy_trade": True},
        quotas={},
    )
    follow_resp = client.post(
        "/social/follows",
        json={"target_user_id": "creator-1", "follow": True},
        headers={"x-user-id": "follower-9"},
    )
    assert follow_resp.status_code == 200
    assert follow_resp.json()["changed"] is True

    entitlements_state["value"] = Entitlements(
        customer_id="follower-9",
        features={"can.publish_strategy": True},
        quotas={},
    )
    activity_resp = client.post(
        "/social/activities",
        json={"activity_type": "shared_trade", "data": {"symbol": "BTCUSDT"}},
        headers={"x-user-id": "follower-9"},
    )
    assert activity_resp.status_code == 201

    feed_resp = client.get("/social/activities", headers={"x-user-id": "follower-9"})
    assert feed_resp.status_code == 200
    assert len(feed_resp.json()) >= 1

    board_payload = {
        "title": "Top Sharpe",
        "metric": "sharpe",
        "period": "weekly",
        "data": {"creator-1": 2.1},
    }
    entitlements_state["value"] = Entitlements(
        customer_id="creator-1",
        features={"can.publish_strategy": True},
        quotas={},
    )
    board_resp = client.put(
        "/social/leaderboards/top-creators",
        json=board_payload,
        headers={"x-user-id": "creator-1"},
    )
    assert board_resp.status_code == 200
    assert board_resp.json()["metric"] == "sharpe"

    with SessionLocal() as db:
        profiles = db.scalars(select(Profile.user_id)).all()
        assert set(profiles) == {"creator-1", "follower-9"}
        follows = db.scalars(select(Follow.followee_id)).all()
        assert follows == ["creator-1"]
        activities = db.scalars(select(Activity.activity_type)).all()
        assert "follow" in activities
        audits = db.scalars(select(AuditLog.action)).all()
        assert {"profile.created", "profile.followed", "activity.logged", "leaderboard.created"}.issubset(set(audits))
