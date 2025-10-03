"""Security helpers for the auth service."""
from __future__ import annotations

import os
import re
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

PASSWORD_MIN_LENGTH = 12
_PASSWORD_CLASSES = {
    "uppercase letter": r"[A-Z]",
    "lowercase letter": r"[a-z]",
    "digit": r"\d",
    "special character": r"[^A-Za-z0-9]",
}
_PASSWORD_CLASS_NAMES = list(_PASSWORD_CLASSES.keys())
if len(_PASSWORD_CLASS_NAMES) > 1:
    _requirements = ", ".join(_PASSWORD_CLASS_NAMES[:-1]) + f", and one {_PASSWORD_CLASS_NAMES[-1]}"
else:
    _requirements = _PASSWORD_CLASS_NAMES[0]
PASSWORD_REQUIREMENTS_MESSAGE = (
    f"Password must be at least {PASSWORD_MIN_LENGTH} characters long and include at least one {_requirements}."
)


def validate_password_requirements(password: str) -> tuple[bool, str | None]:
    """Return whether ``password`` meets strength requirements.

    Args:
        password: The candidate password.

    Returns:
        A tuple ``(is_valid, message)`` where ``is_valid`` is ``True`` when the
        password meets the expected requirements. When ``is_valid`` is ``False``
        the ``message`` contains a human-friendly explanation of the
        requirements.
    """

    if len(password) < PASSWORD_MIN_LENGTH:
        return False, PASSWORD_REQUIREMENTS_MESSAGE
    for pattern in _PASSWORD_CLASSES.values():
        if not re.search(pattern, password):
            return False, PASSWORD_REQUIREMENTS_MESSAGE
    return True, None


def hash_password(password: str) -> str:
    return pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd.verify(password, hashed)


def _encode_subject(subject: int) -> str:
    """Return a JWT-compliant representation of ``subject``."""

    return str(subject)


def _normalise_subject(value: object) -> int | object:
    """Coerce JWT subject claims back to integers when possible."""

    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def create_token_pair(sub: int, roles: list[str]) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    access = jwt.encode(
        {
            "sub": _encode_subject(sub),
            "roles": roles,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=ACCESS_MIN)).timestamp()),
        },
        JWT_SECRET,
        algorithm=JWT_ALG,
    )
    refresh = jwt.encode(
        {
            "sub": _encode_subject(sub),
            "type": "refresh",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=REFRESH_DAYS)).timestamp()),
        },
        JWT_SECRET,
        algorithm=JWT_ALG,
    )
    return access, refresh


def verify_token(token: str) -> dict:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    subject = payload.get("sub")
    normalised_subject = _normalise_subject(subject)
    if normalised_subject is not subject:
        payload["sub"] = normalised_subject
    return payload


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_now(secret: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret)


__all__ = [
    "PASSWORD_MIN_LENGTH",
    "PASSWORD_REQUIREMENTS_MESSAGE",
    "validate_password_requirements",
    "hash_password",
    "verify_password",
    "create_token_pair",
    "verify_token",
    "generate_totp_secret",
    "totp_now",
]
