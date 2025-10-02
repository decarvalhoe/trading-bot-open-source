"""Pydantic schemas for the social service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProfileUpdate(BaseModel):
    display_name: str = Field(max_length=128)
    bio: Optional[str] = None
    avatar_url: Optional[str] = Field(default=None, max_length=255)
    is_public: bool = True


class ProfileOut(BaseModel):
    user_id: str
    display_name: str
    bio: Optional[str]
    avatar_url: Optional[str]
    is_public: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FollowRequest(BaseModel):
    target_user_id: str = Field(max_length=64)
    follow: bool = True


class ActivityCreate(BaseModel):
    activity_type: str = Field(max_length=64)
    data: Dict[str, Any] = Field(default_factory=dict)


class ActivityOut(BaseModel):
    id: int
    profile_id: int
    activity_type: str
    data: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeaderboardUpsert(BaseModel):
    title: str = Field(max_length=128)
    metric: str = Field(max_length=64)
    period: str = Field(default="all", max_length=32)
    data: Dict[str, Any] = Field(default_factory=dict)


class LeaderboardOut(BaseModel):
    slug: str
    title: str
    metric: str
    period: str
    data: Dict[str, Any]
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)
