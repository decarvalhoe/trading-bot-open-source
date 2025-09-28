"""Pydantic models describing Codex automation events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class CodexEventPayload(BaseModel):
    """Raw payload for an incoming webhook event."""

    content_type: str = Field(default="application/json", alias="contentType")
    body: bytes = Field(repr=False)
    encoding: str | None = None

    def json(self) -> Any:
        """Decode the payload as JSON."""

        if "json" not in self.content_type:
            msg = "Payload is not JSON encoded"
            raise ValueError(msg)
        text = self.body.decode(self.encoding or "utf-8")
        import json

        return json.loads(text)


class CodexEvent(BaseModel):
    """Representation of a webhook that should be processed by the worker."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    provider: Literal["github", "stripe", "tradingview"]
    event_type: str | None = Field(default=None, alias="eventType")
    delivery: str | None = None
    signature: str | None = None
    payload: CodexEventPayload
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), alias="receivedAt"
    )
    metadata: dict[str, str] = Field(default_factory=dict)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }

    def body_as_json(self) -> Any:
        """Helper returning the payload decoded as JSON."""

        return self.payload.json()
