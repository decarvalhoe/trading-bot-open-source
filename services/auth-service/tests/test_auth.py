import time

import importlib
import importlib.util
import sys
from pathlib import Path

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_service_root = Path(__file__).resolve().parents[1]
_package_name = "auth_service_app"
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
models = importlib.import_module(f"{_package_name}.models")
security = importlib.import_module(f"{_package_name}.security")
get_db = importlib.import_module("libs.db.db").get_db

app = main.app  # type: ignore[attr-defined]
Base = models.Base
MFATotp = models.MFATotp
Role = models.Role
User = models.User
UserRole = models.UserRole
totp_now = security.totp_now


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
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


@pytest.fixture(autouse=True)
def mock_password_hashing(monkeypatch):
    def _hash(password: str) -> str:
        return f"hashed::{password}"

    def _verify(password: str, hashed: str) -> bool:
        return hashed == f"hashed::{password}"

    monkeypatch.setattr(main, "hash_password", _hash)
    monkeypatch.setattr(main, "verify_password", _verify)


def test_register_creates_user_with_default_role(client, session_factory):
    response = client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "strong-password"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["roles"] == ["user"]

    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == "new@example.com"))
        assert user is not None
        assert user.password_hash != "strong-password"

        role = session.scalar(select(Role).where(Role.name == "user"))
        assert role is not None
        user_role = session.scalar(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
        )
        assert user_role is not None


def _create_user_with_role(session, email="user@example.com", password="secret"):
    user = User(email=email, password_hash=main.hash_password(password))
    session.add(user)
    role = session.scalar(select(Role).where(Role.name == "user"))
    if not role:
        role = Role(name="user")
        session.add(role)
        session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    session.commit()
    session.refresh(user)
    return user


def test_login_without_mfa_returns_tokens(client, session_factory):
    with session_factory() as session:
        user = _create_user_with_role(session)

    response = client.post(
        "/auth/login",
        json={"email": user.email, "password": "secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_requires_totp_when_enabled(client, session_factory):
    with session_factory() as session:
        user = _create_user_with_role(session, email="mfa@example.com", password="mfa-pass")
        secret = pyotp.random_base32()
        session.add(MFATotp(user_id=user.id, secret=secret, enabled=True))
        session.commit()

    missing_totp = client.post(
        "/auth/login",
        json={"email": "mfa@example.com", "password": "mfa-pass"},
    )
    assert missing_totp.status_code == 401

    code = totp_now(secret).now()
    time.sleep(0.1)
    response = client.post(
        "/auth/login",
        json={"email": "mfa@example.com", "password": "mfa-pass", "totp": code},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


def test_auth_me_returns_profile_information(client):
    register = client.post(
        "/auth/register",
        json={"email": "profile@example.com", "password": "profile-pass"},
    )
    assert register.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": "profile@example.com", "password": "profile-pass"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "profile@example.com"
    assert body["roles"] == ["user"]

