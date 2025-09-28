from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import get_settings
from ..dependencies import require_capability
from ..pipeline import StreamEvent, StreamingBridge
from ..repositories import RoomStore, SessionStore
from ..schemas import ReplayCreate, Session, SessionCreate

router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_room_store(request: Request) -> RoomStore:
    return request.app.state.rooms


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.sessions


def get_bridge_dependency(request: Request) -> StreamingBridge:
    return request.app.state.bridge


@router.post("", response_model=Session, status_code=status.HTTP_201_CREATED)
async def schedule_session(
    payload: SessionCreate,
    request: Request,
    rooms_store: RoomStore = Depends(get_room_store),
    sessions_store: SessionStore = Depends(get_session_store),
):
    settings = get_settings()
    await require_capability(request, settings.entitlements_capability)
    try:
        await rooms_store.get(payload.room_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Room not found")
    session = await sessions_store.create(payload)
    return session


@router.get("/{session_id}", response_model=Session)
async def get_session(
    session_id: str,
    request: Request,
    sessions_store: SessionStore = Depends(get_session_store),
):
    settings = get_settings()
    await require_capability(request, settings.entitlements_capability)
    try:
        return await sessions_store.get(session_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")


@router.get("/rooms/{room_id}", response_model=list[Session])
async def list_sessions(
    room_id: str,
    request: Request,
    sessions_store: SessionStore = Depends(get_session_store),
):
    settings = get_settings()
    await require_capability(request, settings.entitlements_capability)
    return await sessions_store.list_by_room(room_id)


@router.post("/{session_id}/start", response_model=Session)
async def start_session(
    session_id: str,
    request: Request,
    sessions_store: SessionStore = Depends(get_session_store),
    bridge: StreamingBridge = Depends(get_bridge_dependency),
):
    settings = get_settings()
    await require_capability(request, settings.entitlements_capability)
    try:
        session = await sessions_store.update(
            session_id,
            status="live",
            started_at=datetime.now(tz=timezone.utc),
        )
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    await bridge.publish(StreamEvent(room_id=session.room_id, payload={"type": "session_started", "session_id": session.session_id}, source="sessions"))
    return session


@router.post("/{session_id}/stop", response_model=Session)
async def stop_session(
    session_id: str,
    request: Request,
    sessions_store: SessionStore = Depends(get_session_store),
    bridge: StreamingBridge = Depends(get_bridge_dependency),
):
    settings = get_settings()
    await require_capability(request, settings.entitlements_capability)
    try:
        session = await sessions_store.update(
            session_id,
            status="ended",
            ended_at=datetime.now(tz=timezone.utc),
        )
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    await bridge.publish(StreamEvent(room_id=session.room_id, payload={"type": "session_stopped", "session_id": session.session_id}, source="sessions"))
    return session


@router.post("/{session_id}/replay", response_model=Session)
async def register_replay(
    session_id: str,
    payload: ReplayCreate,
    request: Request,
    sessions_store: SessionStore = Depends(get_session_store),
    bridge: StreamingBridge = Depends(get_bridge_dependency),
):
    settings = get_settings()
    await require_capability(request, settings.entitlements_capability)
    try:
        session = await sessions_store.update(
            session_id,
            replay_url=payload.replay_url,
            status="replay",
            ended_at=datetime.now(tz=timezone.utc),
        )
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    await bridge.publish(
        StreamEvent(
            room_id=session.room_id,
            payload={"type": "session_replay", "session_id": session.session_id, "replay_url": payload.replay_url},
            source="sessions",
        )
    )
    return session


__all__ = ["router"]
