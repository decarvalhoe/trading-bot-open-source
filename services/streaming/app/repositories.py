from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict

from . import schemas


@dataclass
class RoomStore:
    rooms: Dict[str, schemas.Room] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def create(self, payload: schemas.RoomCreate) -> schemas.Room:
        async with self.lock:
            if payload.room_id in self.rooms:
                raise ValueError("Room already exists")
            room = schemas.Room(
                room_id=payload.room_id,
                title=payload.title,
                description=payload.description,
                is_private=payload.is_private,
                allowed_users=payload.allowed_users,
                created_at=datetime.now(tz=timezone.utc),
            )
            self.rooms[payload.room_id] = room
            return room

    async def get(self, room_id: str) -> schemas.Room:
        async with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                raise KeyError(room_id)
            return room

    async def list(self) -> list[schemas.Room]:
        async with self.lock:
            return list(self.rooms.values())


@dataclass
class SessionStore:
    sessions: Dict[str, schemas.Session] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _counter: int = 0

    async def create(self, payload: schemas.SessionCreate) -> schemas.Session:
        async with self.lock:
            self._counter += 1
            session_id = f"sess-{self._counter}"
            session = schemas.Session(
                session_id=session_id,
                room_id=payload.room_id,
                title=payload.title,
                host_id=payload.host_id,
                scheduled_for=payload.scheduled_for,
                status="scheduled",
            )
            self.sessions[session_id] = session
            return session

    async def get(self, session_id: str) -> schemas.Session:
        async with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                raise KeyError(session_id)
            return session

    async def update(self, session_id: str, **fields) -> schemas.Session:
        async with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                raise KeyError(session_id)
            updated = session.model_copy(update=fields)
            self.sessions[session_id] = updated
            return updated

    async def list_by_room(self, room_id: str) -> list[schemas.Session]:
        async with self.lock:
            return [s for s in self.sessions.values() if s.room_id == room_id]


__all__ = ["RoomStore", "SessionStore"]
