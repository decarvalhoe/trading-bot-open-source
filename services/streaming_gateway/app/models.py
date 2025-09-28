"""Pydantic schemas exposed by the streaming gateway."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, validator


class OverlayIndicator(BaseModel):
    """Indicator configuration included in overlays."""

    type: Literal["ma", "ema", "vwap", "rsi", "custom"]
    period: Optional[int] = Field(None, ge=1, le=500)
    settings: dict = Field(default_factory=dict)


class OverlayCreateRequest(BaseModel):
    """Request body for overlay creation."""

    layout: Literal["full", "mini", "ticker"] = "full"
    indicators: List[OverlayIndicator] = Field(default_factory=list)
    theme: Literal["dark", "light"] = "dark"


class OverlayResponse(BaseModel):
    overlay_id: str = Field(..., alias="overlayId")
    signed_url: str = Field(..., alias="signedUrl")

    class Config:
        allow_population_by_field_name = True


class SessionTarget(BaseModel):
    """Represents a target streaming destination."""

    type: Literal["twitch", "youtube", "discord"]
    identifier: str


class SessionCreateRequest(BaseModel):
    overlay_id: str = Field(..., alias="overlayId")
    targets: List[SessionTarget]
    scheduled_start: Optional[datetime] = None
    discord_webhook_url: Optional[str] = Field(None, alias="discordWebhookUrl")

    class Config:
        allow_population_by_field_name = True


class SessionResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    status: Literal["scheduled", "live", "ended"]

    class Config:
        allow_population_by_field_name = True


class TradingViewWebhook(BaseModel):
    """Inbound TradingView webhook payload."""

    symbol: str
    side: Literal["long", "short", "flat"]
    timeframe: str
    note: Optional[str] = None
    price: Optional[float] = None
    extras: dict = Field(default_factory=dict)

    @validator("symbol", "timeframe")
    def ensure_not_empty(cls, value: str) -> str:  # noqa: D417
        if not value:
            raise ValueError("must not be empty")
        return value
