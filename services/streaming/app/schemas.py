from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class RoomCreate(BaseModel):
    room_id: str = Field(..., description="Identifiant unique de la room")
    title: str
    description: Optional[str] = None
    is_private: bool = False
    allowed_users: List[str] = Field(default_factory=list)


class Room(BaseModel):
    room_id: str
    title: str
    description: Optional[str] = None
    is_private: bool = False
    allowed_users: List[str] = Field(default_factory=list)
    created_at: datetime


class SessionCreate(BaseModel):
    room_id: str
    title: str
    scheduled_for: datetime
    host_id: str


class Session(BaseModel):
    session_id: str
    room_id: str
    title: str
    host_id: str
    scheduled_for: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    replay_url: Optional[str] = None
    status: str


class ReplayCreate(BaseModel):
    replay_url: str
    duration_seconds: int


class ModerationAction(BaseModel):
    action: str = Field(..., description="mute|ban|warn")
    target_user: str
    reason: Optional[str] = None


class StreamIngestPayload(BaseModel):
    room_id: str
    source: str = Field(..., description="reports|inplay|manual")
    payload: dict


class LiveState(BaseModel):
    room: Room
    session: Optional[Session]


__all__ = [
    "RoomCreate",
    "Room",
    "SessionCreate",
    "Session",
    "ReplayCreate",
    "ModerationAction",
    "StreamIngestPayload",
    "LiveState",
]
