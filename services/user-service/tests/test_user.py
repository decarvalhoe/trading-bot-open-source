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
    token = jwt.encode({"sub": user_id, "iat": now}, JWT_SECRET, algorithm=JWT_ALG)
    return {"Authorization": f"Bearer {token}"}


def _service_auth_header():
    now = int(datetime.now(timezone.utc).timestamp())
    token = jwt.encode({"sub": "auth-service", "iat": now}, JWT_SECRET, algorithm=JWT_ALG)
    return {"Authorization": f"Bearer {token}"}


def _admin_entitlements():
    return Entitlements(
        customer_id="admin",
        features={"can.manage_users": True},
        quotas={},
    )


def test_signup_activation_profile_flow(client, session_factory):
    email = "flow@example.com"
    register_payload = {
        "email": email,
        "first_name": "Flow",
        "last_name": "Example",
        "phone": "+33123456789",
    }
    register_resp = client.post(
        "/users/register",
        json=register_payload,
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
        "first_name": "Flowy",
        "last_name": "User",
        "phone": "+33987654321",
        "marketing_opt_in": True,
    }
    update_resp = client.put(
        "/users/me",
        json=profile_payload,
        headers=headers,
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["first_name"] == "Flowy"
    assert body["last_name"] == "User"
    assert body["phone"] == "+33987654321"
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
    assert me_body["first_name"] == "Flowy"
    assert me_body["preferences"] == prefs_payload["preferences"]

    with session_factory() as session:
        stored = session.get(User, user_id)
        assert stored is not None
        assert stored.is_active is True
        assert stored.first_name == "Flowy"
        assert stored.last_name == "User"
        assert stored.phone == "+33987654321"
        prefs_row = session.get(UserPreferences, user_id)
        assert prefs_row is not None
        assert prefs_row.preferences == prefs_payload["preferences"]

    app.dependency_overrides.pop(main.get_entitlements, None)


def test_list_users_pagination(client, session_factory):
    with session_factory() as session:
        for index in range(5):
            session.add(
                User(
                    email=f"user{index}@example.com",
                    first_name=f"User{index}",
                    last_name="Tester",
                    phone=f"+3300000000{index}",
                    is_active=True,
                )
            )
        session.commit()

    app.dependency_overrides[main.get_entitlements] = _admin_entitlements

    default_resp = client.get("/users")
    assert default_resp.status_code == 200
    default_body = default_resp.json()
    assert default_body["pagination"] == {
        "total": 5,
        "count": 5,
        "limit": 20,
        "offset": 0,
    }
    assert [item["email"] for item in default_body["items"]] == [
        "user0@example.com",
        "user1@example.com",
        "user2@example.com",
        "user3@example.com",
        "user4@example.com",
    ]

    paged_resp = client.get("/users", params={"limit": 2, "offset": 1})
    assert paged_resp.status_code == 200
    paged_body = paged_resp.json()
    assert paged_body["pagination"] == {
        "total": 5,
        "count": 2,
        "limit": 2,
        "offset": 1,
    }
    assert [item["email"] for item in paged_body["items"]] == [
        "user1@example.com",
        "user2@example.com",
    ]

    app.dependency_overrides.pop(main.get_entitlements, None)


def test_register_requires_token(client):
    resp = client.post(
        "/users/register",
        json={"email": "no-token@example.com"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing token"


def test_get_user_requires_manage_users_capability(client, session_factory):
    with session_factory() as session:
        target = User(
            email="target@example.com",
            first_name="Target",
            last_name="Name",
            phone="+33101010101",
            marketing_opt_in=True,
            is_active=True,
        )
        session.add(target)
        session.commit()
        session.refresh(target)
        target_id = target.id
        other = User(email="other@example.com", is_active=True)
        session.add(other)
        session.commit()
        session.refresh(other)
        other_id = other.id

    ent_viewer = Entitlements(
        customer_id=str(other_id), features={"can.use_users": True}, quotas={}
    )
    app.dependency_overrides[main.get_entitlements] = lambda: ent_viewer

    headers = _auth_header(other_id)
    resp = client.get(f"/users/{target_id}", headers=headers)
    assert resp.status_code == 403

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
    assert admin_data["first_name"] == "Target"
    assert admin_data["last_name"] == "Name"
    assert admin_data["phone"] == "+33101010101"
    assert admin_data["marketing_opt_in"] is True

    app.dependency_overrides.pop(main.get_entitlements, None)


def test_delete_me_performs_soft_delete(client, session_factory):
    with session_factory() as session:
        user = User(email="self-delete@example.com", first_name="Self", last_name="Delete", is_active=True)
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

    ent_self = Entitlements(
        customer_id=str(user_id), features={"can.use_users": True}, quotas={}
    )
    app.dependency_overrides[main.get_entitlements] = lambda: ent_self

    headers = _auth_header(user_id)
    delete_resp = client.delete("/users/me", headers=headers)
    assert delete_resp.status_code == 204

    me_resp = client.get("/users/me", headers=headers)
    assert me_resp.status_code == 404

    with session_factory() as session:
        stored = session.get(User, user_id)
        assert stored is not None
        assert stored.is_active is False
        assert stored.deleted_at is not None

    app.dependency_overrides.pop(main.get_entitlements, None)


def test_user_cannot_modify_other_profile_without_rights(client, session_factory):
    with session_factory() as session:
        target = User(
            email="target2@example.com",
            first_name="Other",
            last_name="Target",
            is_active=True,
        )
        session.add(target)
        session.commit()
        session.refresh(target)
        target_id = target.id
        actor = User(email="actor@example.com", first_name="Actor", last_name="User", is_active=True)
        session.add(actor)
        session.commit()
        session.refresh(actor)
        actor_id = actor.id

    ent_user = Entitlements(
        customer_id=str(actor_id), features={"can.use_users": True}, quotas={}
    )
    app.dependency_overrides[main.get_entitlements] = lambda: ent_user

    headers = _auth_header(actor_id)
    update_resp = client.patch(
        f"/users/{target_id}", json={"first_name": "Hack"}, headers=headers
    )
    assert update_resp.status_code == 403

    delete_resp = client.delete(f"/users/{target_id}", headers=headers)
    assert delete_resp.status_code == 403

    app.dependency_overrides.pop(main.get_entitlements, None)


def test_admin_can_update_and_soft_delete_user(client, session_factory):
    with session_factory() as session:
        user = User(
            email="admin-target@example.com",
            first_name="Initial",
            last_name="Admin",
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

    ent_admin = Entitlements(
        customer_id="admin",
        features={"can.manage_users": True},
        quotas={},
    )
    app.dependency_overrides[main.get_entitlements] = lambda: ent_admin

    headers = _service_auth_header()

    update_resp = client.patch(
        f"/users/{user_id}",
        json={"last_name": "Updated"},
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["last_name"] == "Updated"

    list_resp = client.get("/users", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["pagination"] == {
        "total": 1,
        "count": 1,
        "limit": 20,
        "offset": 0,
    }
    assert [item["email"] for item in list_data["items"]] == [
        "admin-target@example.com"
    ]

    delete_resp = client.delete(f"/users/{user_id}", headers=headers)
    assert delete_resp.status_code == 204

    get_resp = client.get(f"/users/{user_id}", headers=headers)
    assert get_resp.status_code == 404

    with session_factory() as session:
        stored = session.get(User, user_id)
        assert stored is not None
        assert stored.deleted_at is not None
        assert stored.is_active is False

    list_after = client.get("/users", headers=headers)
    assert list_after.status_code == 200
    assert list_after.json() == {
        "items": [],
        "pagination": {"total": 0, "count": 0, "limit": 20, "offset": 0},
    }

    app.dependency_overrides.pop(main.get_entitlements, None)
