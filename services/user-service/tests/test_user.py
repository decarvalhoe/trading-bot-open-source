import importlib
import importlib.util
import sys
from pathlib import Path
from datetime import datetime, timezone
import os

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from libs.entitlements.client import Entitlements

os.environ.setdefault("ENTITLEMENTS_BYPASS", "1")

_service_root = Path(__file__).resolve().parents[1]
_package_name = "user_service_app"
_repo_root = _service_root.parents[1]

if str(_repo_root) not in sys.path:
    sys.path.append(str(_repo_root))

if _package_name not in sys.modules:
    _package_spec = importlib.util.spec_from_file_location(
        _package_name,
        _service_root / "app" / "__init__.py",
        submodule_search_locations=[str(_service_root / "app")],
    )
    assert _package_spec and _package_spec.loader
    _package_module = importlib.util.module_from_spec(_package_spec)
    sys.modules[_package_name] = _package_module
    _package_spec.loader.exec_module(_package_module)  # type: ignore[arg-type]

main = importlib.import_module(f"{_package_name}.main")

app = main.app  # type: ignore[attr-defined]
Base = main.Base  # type: ignore[attr-defined]
User = main.User  # type: ignore[attr-defined]
UserPreferences = main.UserPreferences  # type: ignore[attr-defined]
JWT_SECRET = main.JWT_SECRET  # type: ignore[attr-defined]
JWT_ALG = main.JWT_ALG  # type: ignore[attr-defined]
get_db = importlib.import_module("libs.db.db").get_db


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    yield TestingSessionLocal
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _auth_header(user_id: int):
    now = int(datetime.now(timezone.utc).timestamp())
    token = jwt.encode({"sub": str(user_id), "iat": now}, JWT_SECRET, algorithm=JWT_ALG)
    return {"Authorization": f"Bearer {token}"}


def _service_auth_header():
    now = int(datetime.now(timezone.utc).timestamp())
    token = jwt.encode({"sub": "auth-service", "iat": now}, JWT_SECRET, algorithm=JWT_ALG)
    return {"Authorization": f"Bearer {token}"}


def test_signup_activation_profile_flow(client, session_factory):
    email = "flow@example.com"
    register_resp = client.post(
        "/users/register",
        json={"email": email, "display_name": "Flow"},
        headers=_service_auth_header(),
    )
    assert register_resp.status_code == 201
    registered = register_resp.json()
    user_id = registered["id"]
    assert registered["is_active"] is False

    ent_self = Entitlements(
        customer_id=str(user_id), features={"can.use_users": True}, quotas={}
    )
    app.dependency_overrides[main.get_entitlements] = lambda: ent_self

    headers = _auth_header(user_id)

    activate_resp = client.post(f"/users/{user_id}/activate", headers=headers)
    assert activate_resp.status_code == 200
    assert activate_resp.json()["is_active"] is True

    profile_payload = {
        "display_name": "Flow User",
        "full_name": "Flow Example",
        "locale": "fr_FR",
        "marketing_opt_in": True,
    }
    update_resp = client.patch(
        f"/users/{user_id}",
        json=profile_payload,
        headers=headers,
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["display_name"] == "Flow User"
    assert body["full_name"] == "Flow Example"
    assert body["marketing_opt_in"] is True

    prefs_payload = {"preferences": {"theme": "dark", "currency": "EUR"}}
    pref_resp = client.put(
        "/users/me/preferences",
        json=prefs_payload,
        headers=headers,
    )
    assert pref_resp.status_code == 200
    assert pref_resp.json()["preferences"] == prefs_payload["preferences"]

    me_resp = client.get("/users/me", headers=headers)
    assert me_resp.status_code == 200
    me_body = me_resp.json()
    assert me_body["email"] == email
    assert me_body["preferences"] == prefs_payload["preferences"]

    with session_factory() as session:
        stored = session.get(User, user_id)
        assert stored is not None
        assert stored.is_active is True
        assert stored.display_name == "Flow User"
        prefs_row = session.get(UserPreferences, user_id)
        assert prefs_row is not None
        assert prefs_row.preferences == prefs_payload["preferences"]

    app.dependency_overrides.pop(main.get_entitlements, None)


def test_register_requires_token(client):
    resp = client.post(
        "/users/register",
        json={"email": "no-token@example.com"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing token"


def test_get_user_masks_sensitive_data_for_other_actor(client, session_factory):
    with session_factory() as session:
        target = User(
            email="target@example.com",
            display_name="Target",
            full_name="Target Name",
            marketing_opt_in=True,
            is_active=True,
        )
        session.add(target)
        session.commit()
        session.refresh(target)
        target_id = target.id
        session.add(
            UserPreferences(
                user_id=target_id, preferences={"watchlists": ["growth"]}
            )
        )
        other = User(email="other@example.com", is_active=True)
        session.add(other)
        session.commit()
        session.refresh(other)
        other_id = other.id
        session.commit()

    ent_viewer = Entitlements(
        customer_id=str(other_id), features={"can.use_users": True}, quotas={}
    )
    app.dependency_overrides[main.get_entitlements] = lambda: ent_viewer

    headers = _auth_header(other_id)
    resp = client.get(f"/users/{target_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] is None
    assert data["full_name"] is None
    assert data["marketing_opt_in"] is None
    assert data["display_name"] == "Target"
    assert data["preferences"] == {"watchlists": ["growth"]}

    ent_admin = Entitlements(
        customer_id=str(other_id),
        features={"can.manage_users": True},
        quotas={},
    )
    app.dependency_overrides[main.get_entitlements] = lambda: ent_admin

    admin_resp = client.get(f"/users/{target_id}", headers=headers)
    assert admin_resp.status_code == 200
    admin_data = admin_resp.json()
    assert admin_data["email"] == "target@example.com"
    assert admin_data["full_name"] == "Target Name"
    assert admin_data["marketing_opt_in"] is True

    app.dependency_overrides.pop(main.get_entitlements, None)
