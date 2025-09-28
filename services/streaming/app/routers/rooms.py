from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import get_settings
from ..dependencies import require_capability
from ..repositories import RoomStore, SessionStore
from ..schemas import LiveState, Room, RoomCreate

router = APIRouter(prefix="/rooms", tags=["rooms"])


def get_room_store(request: Request) -> RoomStore:
    return request.app.state.rooms


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.sessions


@router.post("", response_model=Room, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: RoomCreate,
    request: Request,
    rooms_store: RoomStore = Depends(get_room_store),
):
    settings = get_settings()
    await require_capability(request, settings.entitlements_capability)
    try:
        room = await rooms_store.create(payload)
    except ValueError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Room already exists")
    return room


@router.get("", response_model=list[Room])
async def list_rooms(request: Request, rooms_store: RoomStore = Depends(get_room_store)):
    settings = get_settings()
    await require_capability(request, settings.entitlements_capability)
    return await rooms_store.list()


@router.get("/{room_id}", response_model=LiveState)
async def get_room(
    room_id: str,
    request: Request,
    rooms_store: RoomStore = Depends(get_room_store),
    sessions_store: SessionStore = Depends(get_session_store),
):
    settings = get_settings()
    await require_capability(request, settings.entitlements_capability)
    try:
        room = await rooms_store.get(room_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Room not found")
    sessions = await sessions_store.list_by_room(room_id)
    active_session = next((s for s in sessions if s.status in {"live", "scheduled"}), None)
    return LiveState(room=room, session=active_session)


__all__ = ["router"]
