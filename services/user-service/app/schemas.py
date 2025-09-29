"""Pydantic schemas shared by the user service endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PreferencesUpdate(BaseModel):
    """Payload for replacing user preferences."""

    preferences: Dict[str, Any] = Field(
        default_factory=dict, description="Preferences map stored as-is."
    )


class PreferencesResponse(BaseModel):
    """Response wrapper for preference operations."""

    preferences: Dict[str, Any] = Field(default_factory=dict)


class UserCreate(BaseModel):
    """Payload required to create or register a user."""

    email: EmailStr
    display_name: Optional[str] = Field(default=None, max_length=120)
    full_name: Optional[str] = Field(default=None, max_length=255)
    locale: Optional[str] = Field(default=None, max_length=16)
    marketing_opt_in: bool = Field(default=False)


class UserUpdate(BaseModel):
    """Payload for updating user profile information."""

    display_name: Optional[str] = Field(default=None, max_length=120)
    full_name: Optional[str] = Field(default=None, max_length=255)
    locale: Optional[str] = Field(default=None, max_length=16)
    marketing_opt_in: Optional[bool] = None


class UserResponse(BaseModel):
    """Representation of a user returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr | None = None
    display_name: Optional[str] = None
    full_name: Optional[str] = None
    locale: Optional[str] = None
    marketing_opt_in: Optional[bool] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    preferences: Dict[str, Any] = Field(default_factory=dict)


class UserListPagination(BaseModel):
    """Metadata describing the pagination state for a list of users."""

    total: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class UserList(BaseModel):
    """Paginated list of users returned by the API."""

    items: List[UserResponse] = Field(default_factory=list)
    pagination: UserListPagination


__all__ = [
    "PreferencesResponse",
    "PreferencesUpdate",
    "UserCreate",
    "UserList",
    "UserResponse",
    "UserUpdate",
]
