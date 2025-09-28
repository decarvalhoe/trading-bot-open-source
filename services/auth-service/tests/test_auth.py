import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType

import pyotp
import pytest
from pydantic import ValidationError
from sqlalchemy import select

CURRENT_DIR = Path(__file__).resolve().parent

HELPERS_NAME = "auth_service_test_helpers"
HELPERS_PATH = CURRENT_DIR / "_helpers.py"


def _load_helpers(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


helpers = _load_helpers(HELPERS_NAME, HELPERS_PATH)

MFATotp = helpers.MFATotp
Role = helpers.Role
User = helpers.User
UserRole = helpers.UserRole
LoginRequest = helpers.LoginRequest
RegisterRequest = helpers.RegisterRequest
TokenPair = helpers.TokenPair
create_user_with_role = helpers.create_user_with_role
totp_now = helpers.totp_now
Me = helpers.Me


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


def test_login_without_mfa_returns_tokens(client, session_factory):
    with session_factory() as session:
        user = create_user_with_role(session)

    response = client.post(
        "/auth/login",
        json={"email": user.email, "password": "secret"},
    )

    assert response.status_code == 200
    body = TokenPair.model_validate(response.json())
    assert body.token_type == "bearer"


def test_login_requires_totp_when_enabled(client, session_factory):
    with session_factory() as session:
        user = create_user_with_role(session, email="mfa@example.com", password="mfa-pass")
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
    body = TokenPair.model_validate(response.json())
    assert body.access_token
    assert body.refresh_token


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
    body = Me.model_validate(response.json())
    assert body.email == "profile@example.com"
    assert body.roles == ["user"]


def test_user_flags_default_to_expected_values(session_factory):
    with session_factory() as session:
        user = User(email="defaults@example.com", password_hash="hash")
        session.add(user)
        session.commit()
        session.refresh(user)

    assert user.is_active is True
    assert user.is_superuser is False


def test_mfa_totp_defaults_to_disabled(session_factory):
    with session_factory() as session:
        user = create_user_with_role(session, email="totp-default@example.com")
        totp_entry = MFATotp(user_id=user.id, secret="A" * 32)
        session.add(totp_entry)
        session.commit()
        session.refresh(totp_entry)

    assert totp_entry.enabled is False


def test_token_pair_default_type():
    tokens = TokenPair(access_token="a", refresh_token="b")
    assert tokens.token_type == "bearer"


def test_register_request_validates_email():
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="pass")


def test_login_request_totp_optional():
    request = LoginRequest(email="user@example.com", password="pass")
    assert request.totp is None
