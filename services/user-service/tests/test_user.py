from datetime import datetime, timezone
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(255) UNIQUE NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                preferences TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    yield TestingSessionLocal
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS user_preferences")
        conn.exec_driver_sql("DROP TABLE IF EXISTS users")


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


def test_get_me_returns_user_and_preferences(client, session_factory):
    with session_factory() as session:
        user = User(email="me@example.com")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
        session.add(UserPreferences(user_id=user.id, preferences={"currency": "USD"}))
        session.commit()

    response = client.get("/users/me", headers=_auth_header(user_id))
    assert response.status_code == 200
    body = response.json()
    assert body == {"id": user_id, "email": "me@example.com", "preferences": {"currency": "USD"}}


def test_update_preferences_creates_or_updates_entry(client, session_factory):
    with session_factory() as session:
        user = User(email="update@example.com")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

    new_prefs = {"theme": "dark", "language": "fr"}
    put_response = client.put(
        "/users/me/preferences",
        headers=_auth_header(user_id),
        json=new_prefs,
    )
    assert put_response.status_code == 200
    assert put_response.json() == {"ok": True}

    response = client.get("/users/me", headers=_auth_header(user_id))
    assert response.status_code == 200
    assert response.json()["preferences"] == new_prefs

    updated_prefs = {"theme": "light"}
    second_put = client.put(
        "/users/me/preferences",
        headers=_auth_header(user_id),
        json=updated_prefs,
    )
    assert second_put.status_code == 200

    with session_factory() as session:
        prefs = session.execute(select(UserPreferences).where(UserPreferences.user_id == user_id)).scalar_one()
        assert prefs.preferences == updated_prefs

