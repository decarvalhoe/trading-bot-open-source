"""Pydantic models exposed by the screener API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScreenerResultPayload(BaseModel):
    symbol: str | None = None
    rank: int
    score: float | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ScreenerRunResponse(BaseModel):
    snapshot_id: int
    provider: str
    preset_id: int | None = None
    filters: dict[str, Any]
    results: list[dict[str, Any]]


class ScreenerPresetOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    filters: dict[str, Any]
    favorite: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScreenerPresetCreate(BaseModel):
    name: str
    filters: dict[str, Any]
    description: str | None = None
    favorite: bool = False


class ScreenerPresetFavoriteUpdate(BaseModel):
    favorite: bool
