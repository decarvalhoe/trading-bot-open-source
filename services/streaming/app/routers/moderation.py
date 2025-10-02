from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import get_settings
from ..dependencies import require_capability
from ..pipeline import StreamEvent
from ..repositories import RoomStore
from ..schemas import ModerationAction

router = APIRouter(prefix="/moderation", tags=["moderation"])


def get_room_store(request: Request) -> RoomStore:
    return request.app.state.rooms


@router.post("/rooms/{room_id}", status_code=status.HTTP_202_ACCEPTED)
async def moderate_room(
    room_id: str,
    payload: ModerationAction,
    request: Request,
    rooms_store: RoomStore = Depends(get_room_store),
):
    settings = get_settings()
    await require_capability(request, settings.entitlements_capability)
    try:
        await rooms_store.get(room_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Room not found")
    bridge = request.app.state.bridge
    await bridge.publish(
        StreamEvent(
            room_id=room_id,
            payload={
                "type": "moderation",
                "action": payload.action,
                "target": payload.target_user,
                "reason": payload.reason,
            },
            source="moderation",
        )
    )
    return {"status": "propagated"}


__all__ = ["router"]
