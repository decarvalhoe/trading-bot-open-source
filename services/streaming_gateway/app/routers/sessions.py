"""Session management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ..config import Settings
from ..deps import get_current_user_id, get_settings_dependency
from ..models import SessionCreateRequest, SessionResponse
from ..notifications import announce_session_start
from ..security import issue_overlay_token
from ..storage import storage

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreateRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings_dependency),
) -> SessionResponse:
    overlay = storage.get_overlay(payload.overlay_id, user_id)
    if not overlay:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overlay not found")
    session = storage.create_session(user_id, payload)
    overlay_token = issue_overlay_token(overlay.overlay_id, settings.overlay_token_secret, settings.overlay_token_ttl_seconds)
    overlay_url = f"{settings.public_base_url}/o/{overlay.overlay_id}?token={overlay_token}"
    background_tasks.add_task(
        announce_session_start,
        settings,
        session.session_id,
        overlay_url,
        session.discord_webhook_url,
    )
    status_value = "scheduled" if session.scheduled_start else "live"
    if status_value == "live":
        storage.update_session_status(session.session_id, "live")
    return SessionResponse(sessionId=session.session_id, status=storage.sessions[session.session_id].status)


@router.post("/{session_id}/status/{status}")
async def update_session_status(
    session_id: str,
    status: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    session = storage.sessions.get(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if status not in {"scheduled", "live", "ended"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    storage.update_session_status(session_id, status)
    return {"sessionId": session_id, "status": storage.sessions[session_id].status}


@router.get("/{session_id}/replay")
async def get_session_replay(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    session = storage.sessions.get(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.status != "ended":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not ended")
    return {"sessionId": session_id, "replayUrl": f"jetstream://{session_id}"}
