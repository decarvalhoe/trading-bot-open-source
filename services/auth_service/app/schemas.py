from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from .security import (
    PASSWORD_MIN_LENGTH,
    PASSWORD_REQUIREMENTS_MESSAGE,
)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    refresh_token: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp: str | None = None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        ...,
        description=PASSWORD_REQUIREMENTS_MESSAGE,
        examples=["Str0ngPassw0rd!"],
        json_schema_extra={
            "min_length": PASSWORD_MIN_LENGTH,
            "error_message": PASSWORD_REQUIREMENTS_MESSAGE,
        },
    )


class Me(BaseModel):
    id: int
    email: EmailStr
    roles: list[str]
    created_at: datetime
    updated_at: datetime


class TOTPSetup(BaseModel):
    secret: str
    otpauth_url: str
