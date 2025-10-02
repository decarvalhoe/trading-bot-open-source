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
    first_name: str = Field(max_length=120)
    last_name: str = Field(max_length=120)
    phone: Optional[str] = Field(default=None, max_length=32)
    marketing_opt_in: bool = Field(default=False)


class UserUpdate(BaseModel):
    """Payload for updating user profile information."""

    first_name: Optional[str] = Field(default=None, max_length=120)
    last_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=32)
    marketing_opt_in: Optional[bool] = None


class UserResponse(BaseModel):
    """Representation of a user returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr | None = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
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


class OnboardingStep(BaseModel):
    """Definition of an onboarding step exposed to the UI."""

    id: str = Field(min_length=1)
    title: str
    description: str


class OnboardingProgressResponse(BaseModel):
    """Payload describing the onboarding state for a user."""

    user_id: int
    current_step: Optional[str] = None
    completed_steps: List[str] = Field(default_factory=list)
    steps: List[OnboardingStep] = Field(default_factory=list)
    is_complete: bool = False
    updated_at: Optional[datetime] = None
    restarted_at: Optional[datetime] = None


__all__ = [
    "OnboardingProgressResponse",
    "OnboardingStep",
    "PreferencesResponse",
    "PreferencesUpdate",
    "UserCreate",
    "UserList",
    "UserResponse",
    "UserUpdate",
]
