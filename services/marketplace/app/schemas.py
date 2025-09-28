"""Pydantic models exposed by the marketplace API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ListingVersionCreate(BaseModel):
    version: str = Field(default="1.0.0", max_length=32)
    configuration: Dict[str, Any] = Field(default_factory=dict)
    changelog: Optional[str] = None


class ListingCreate(BaseModel):
    strategy_name: str = Field(max_length=128)
    description: Optional[str] = None
    price_cents: int = Field(ge=0)
    currency: str = Field(default="USD", max_length=3)
    connect_account_id: str = Field(max_length=64)
    initial_version: Optional[ListingVersionCreate] = None


class ListingVersionOut(BaseModel):
    id: int
    version: str
    changelog: Optional[str]
    configuration: Dict[str, Any]
    is_published: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ListingOut(BaseModel):
    id: int
    owner_id: str
    strategy_name: str
    description: Optional[str]
    price_cents: int
    currency: str
    connect_account_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    versions: list[ListingVersionOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ListingVersionRequest(BaseModel):
    version: str = Field(max_length=32)
    configuration: Dict[str, Any] = Field(default_factory=dict)
    changelog: Optional[str] = None


class CopyRequest(BaseModel):
    listing_id: int
    version_id: Optional[int] = None
    payment_reference: Optional[str] = Field(default=None, max_length=128)


class CopyResponse(BaseModel):
    id: int
    listing_id: int
    subscriber_id: str
    version_id: Optional[int]
    payment_reference: Optional[str]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
