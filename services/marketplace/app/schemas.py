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
    performance_score: Optional[float] = Field(default=None, ge=0)
    risk_score: Optional[float] = Field(default=None, ge=0)
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
    review_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    performance_score: Optional[float] = None
    risk_score: Optional[float] = None
    average_rating: Optional[float] = None
    reviews_count: int = 0
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
    connect_transfer_reference: Optional[str]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ListingReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=2000)


class ListingReviewOut(BaseModel):
    id: int
    listing_id: int
    reviewer_id: str
    rating: int
    comment: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
