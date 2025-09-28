"""Security helpers for the auth service."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pyotp
from jose import jwt
from passlib.context import CryptContext

from libs.secrets import get_secret

JWT_SECRET = get_secret("JWT_SECRET", default="dev-secret-change-me")
JWT_ALG = "HS256"
ACCESS_MIN = int(os.getenv("ACCESS_MIN", "15"))
REFRESH_DAYS = int(os.getenv("REFRESH_DAYS", "7"))

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd.verify(password, hashed)


def create_token_pair(sub: str, roles: list[str]) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    access = jwt.encode(
        {
            "sub": sub,
            "roles": roles,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=ACCESS_MIN)).timestamp()),
        },
        JWT_SECRET,
        algorithm=JWT_ALG,
    )
    refresh = jwt.encode(
        {
            "sub": sub,
            "type": "refresh",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=REFRESH_DAYS)).timestamp()),
        },
        JWT_SECRET,
        algorithm=JWT_ALG,
    )
    return access, refresh


def verify_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_now(secret: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret)


__all__ = [
    "hash_password",
    "verify_password",
    "create_token_pair",
    "verify_token",
    "generate_totp_secret",
    "totp_now",
]
