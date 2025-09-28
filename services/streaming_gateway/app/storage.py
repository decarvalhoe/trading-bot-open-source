"""In-memory storage for overlays and sessions."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from .models import OverlayCreateRequest, SessionCreateRequest


@dataclass
class Overlay:
    overlay_id: str
    user_id: str
    layout: str
    indicators: List[dict]
    theme: str
    created_at: float


@dataclass
class Session:
    session_id: str
    overlay_id: str
    user_id: str
    targets: List[dict]
    status: str = "scheduled"
    scheduled_start: Optional[float] = None
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    discord_webhook_url: Optional[str] = None


class InMemoryStorage:
    def __init__(self) -> None:
        self.overlays: Dict[str, Overlay] = {}
        self.sessions: Dict[str, Session] = {}

    def create_overlay(self, user_id: str, payload: OverlayCreateRequest) -> Overlay:
        overlay_id = secrets.token_urlsafe(8)
        overlay = Overlay(
            overlay_id=overlay_id,
            user_id=user_id,
            layout=payload.layout,
            indicators=[ind.dict() for ind in payload.indicators],
            theme=payload.theme,
            created_at=time.time(),
        )
        self.overlays[overlay_id] = overlay
        return overlay

    def get_overlay(self, overlay_id: str, user_id: str) -> Optional[Overlay]:
        overlay = self.overlays.get(overlay_id)
        if overlay and overlay.user_id == user_id:
            return overlay
        return None

    def create_session(self, user_id: str, payload: SessionCreateRequest) -> Session:
        session_id = secrets.token_urlsafe(8)
        session = Session(
            session_id=session_id,
            overlay_id=payload.overlay_id,
            user_id=user_id,
            targets=[target.dict() for target in payload.targets],
            scheduled_start=payload.scheduled_start.timestamp() if payload.scheduled_start else None,
            discord_webhook_url=payload.discord_webhook_url,
        )
        self.sessions[session_id] = session
        return session

    def update_session_status(self, session_id: str, status: str) -> None:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError(session_id)
        session.status = status
        now = time.time()
        if status == "live":
            session.started_at = now
        elif status == "ended":
            session.ended_at = now


storage = InMemoryStorage()
