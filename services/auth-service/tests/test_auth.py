import importlib.util
import sys
import time
from datetime import datetime, timedelta, timezone
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
security = helpers.security
TokenRefreshRequest = getattr(helpers.schemas, "TokenRefreshRequest")


def test_register_creates_user_with_default_role(client, session_factory):
    response = client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "Str0ngPassw0rd!"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["roles"] == ["user"]
    assert "created_at" in body
    assert "updated_at" in body
    created_at = datetime.fromisoformat(body["created_at"])
    updated_at = datetime.fromisoformat(body["updated_at"])
    assert created_at.tzinfo is not None
    assert updated_at.tzinfo is not None
    assert updated_at >= created_at

    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == "new@example.com"))
        assert user is not None
        assert user.password_hash != "Str0ngPassw0rd!"
        assert user.created_at is not None
        assert user.updated_at is not None
        assert user.created_at.tzinfo is not None
        assert user.updated_at.tzinfo is not None
        assert user.updated_at >= user.created_at

        role = session.scalar(select(Role).where(Role.name == "user"))
        assert role is not None
        user_role = session.scalar(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
        )
        assert user_role is not None


def test_register_rejects_password_not_meeting_requirements(client):
    response = client.post(
        "/auth/register",
        json={"email": "weak@example.com", "password": "weakpass"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == security.PASSWORD_REQUIREMENTS_MESSAGE


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


def test_refresh_returns_new_token_pair(client, session_factory):
    with session_factory() as session:
        user = create_user_with_role(session, email="refresh@example.com")

    login = client.post(
        "/auth/login",
        json={"email": "refresh@example.com", "password": "secret"},
    )
    assert login.status_code == 200
    original = TokenPair.model_validate(login.json())

    response = client.post(
        "/auth/refresh",
        json=TokenRefreshRequest(refresh_token=original.refresh_token).model_dump(exclude_none=True),
    )

    assert response.status_code == 200
    refreshed = TokenPair.model_validate(response.json())
    decoded_access = security.verify_token(refreshed.access_token)
    decoded_refresh = security.verify_token(refreshed.refresh_token)
    assert decoded_access["sub"] == user.id
    assert decoded_refresh["type"] == "refresh"


def test_refresh_rejects_invalid_token(client):
    response = client.post("/auth/refresh", json={"refresh_token": "invalid"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


def test_refresh_rejects_expired_token(client, session_factory):
    with session_factory() as session:
        user = create_user_with_role(session, email="expired@example.com")

    now = datetime.now(timezone.utc)
    expired_refresh = security.jwt.encode(
        {
            "sub": user.id,
            "type": "refresh",
            "iat": int(now.timestamp()),
            "exp": int((now - timedelta(minutes=1)).timestamp()),
        },
        security.JWT_SECRET,
        algorithm=security.JWT_ALG,
    )

    response = client.post("/auth/refresh", json={"refresh_token": expired_refresh})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


def test_auth_me_returns_profile_information(client):
    register = client.post(
        "/auth/register",
        json={"email": "profile@example.com", "password": "Str0ngProfil3!"},
    )
    assert register.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": "profile@example.com", "password": "Str0ngProfil3!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = Me.model_validate(response.json())
    assert body.email == "profile@example.com"
    assert body.roles == ["user"]
    assert body.created_at.tzinfo is not None
    assert body.updated_at.tzinfo is not None
    assert body.updated_at >= body.created_at


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
        RegisterRequest(email="not-an-email", password="ValidPassw0rd!")


def test_register_request_documents_password_rules():
    field = RegisterRequest.model_fields["password"]
    assert field.description == security.PASSWORD_REQUIREMENTS_MESSAGE
    assert field.json_schema_extra["error_message"] == security.PASSWORD_REQUIREMENTS_MESSAGE
    assert field.json_schema_extra["min_length"] == security.PASSWORD_MIN_LENGTH


def test_login_request_totp_optional():
    request = LoginRequest(email="user@example.com", password="pass")
    assert request.totp is None
