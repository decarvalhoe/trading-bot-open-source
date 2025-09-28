"""WebSocket endpoint pushing overlay updates."""

from __future__ import annotations

import json
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


class OverlayConnectionManager:
    def __init__(self) -> None:
        self.connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, overlay_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.setdefault(overlay_id, []).append(websocket)

    def disconnect(self, overlay_id: str, websocket: WebSocket) -> None:
        peers = self.connections.get(overlay_id, [])
        if websocket in peers:
            peers.remove(websocket)
        if not peers:
            self.connections.pop(overlay_id, None)

    async def broadcast(self, overlay_id: str, message: dict) -> None:
        for connection in list(self.connections.get(overlay_id, [])):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(overlay_id, connection)


manager = OverlayConnectionManager()


@router.websocket("/ws/overlay/{overlay_id}")
async def overlay_socket(websocket: WebSocket, overlay_id: str) -> None:
    await manager.connect(overlay_id, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                payload = {"type": "ping"}
            await manager.broadcast(overlay_id, {"type": "echo", "payload": payload})
    except WebSocketDisconnect:
        manager.disconnect(overlay_id, websocket)
    except Exception:
        manager.disconnect(overlay_id, websocket)
        await websocket.close()
