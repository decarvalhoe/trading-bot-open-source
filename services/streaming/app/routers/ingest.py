from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from ..config import get_settings
from ..dependencies import authorize_service
from ..pipeline import StreamEvent, StreamingBridge
from ..schemas import StreamIngestPayload

router = APIRouter(prefix="/ingest", tags=["ingest"])


def get_bridge_dependency(request: Request) -> StreamingBridge:
    return request.app.state.bridge


@router.post("/reports", status_code=status.HTTP_202_ACCEPTED)
async def ingest_from_reports(
    payload: StreamIngestPayload,
    request: Request,
    bridge: StreamingBridge = Depends(get_bridge_dependency),
):
    settings = get_settings()
    await authorize_service(request, [settings.service_token_reports])
    await bridge.publish(
        StreamEvent(room_id=payload.room_id, payload=payload.payload, source="reports")
    )
    return {"status": "queued"}


@router.post("/inplay", status_code=status.HTTP_202_ACCEPTED)
async def ingest_from_inplay(
    payload: StreamIngestPayload,
    request: Request,
    bridge: StreamingBridge = Depends(get_bridge_dependency),
):
    settings = get_settings()
    await authorize_service(request, [settings.service_token_inplay])
    await bridge.publish(
        StreamEvent(room_id=payload.room_id, payload=payload.payload, source="inplay")
    )
    return {"status": "queued"}


__all__ = ["router"]
