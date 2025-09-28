from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Callable

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics

from .config import Settings, get_settings
from .schemas import TickPayload, WatchlistSnapshot, WatchlistStreamEvent
from .state import InPlayState
from .stream import RedisTickStream, SimulatedTickStream, TickStream


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, event: WatchlistStreamEvent) -> None:
        message = event.model_dump(mode="json")
        async with self._lock:
            connections = list(self._connections)
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                await self.disconnect(websocket)


def _default_stream_factory() -> TickStream:
    return RedisTickStream()


configure_logging("inplay")


def create_app(
    settings: Settings | None = None,
    stream_factory: Callable[[], TickStream] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    state = InPlayState(settings.watchlists)
    manager = WebSocketManager()

    async def _consumer(stream: TickStream) -> None:
        async for payload in stream.listen():
            snapshots = await state.apply_tick(payload)
            for snapshot in snapshots:
                await manager.broadcast(WatchlistStreamEvent(payload=snapshot))

    async def lifespan(app: FastAPI):
        stream = (stream_factory or _default_stream_factory)()
        consumer_task = asyncio.create_task(_consumer(stream))
        app.state.tick_stream = stream
        app.state.consumer_task = consumer_task
        yield
        consumer_task.cancel()
        with suppress(asyncio.CancelledError):
            await consumer_task
        close = getattr(stream, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                await result

    app = FastAPI(title="In-Play Service", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware, service_name="inplay")
    setup_metrics(app, service_name="inplay")

    async def get_state() -> InPlayState:
        return state

    async def get_manager() -> WebSocketManager:
        return manager

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/inplay/watchlists/{watchlist_id}", response_model=WatchlistSnapshot)
    async def get_watchlist(
        watchlist_id: str,
        state: InPlayState = Depends(get_state),
    ) -> WatchlistSnapshot:
        try:
            return await state.get_watchlist(watchlist_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown watchlist '{watchlist_id}'") from exc

    @app.websocket("/inplay/ws")
    async def inplay_ws(
        websocket: WebSocket,
        state: InPlayState = Depends(get_state),
        manager: WebSocketManager = Depends(get_manager),
    ) -> None:
        await manager.connect(websocket)
        try:
            snapshots = await state.list_watchlists()
            for snapshot in snapshots:
                await websocket.send_json(
                    WatchlistStreamEvent(payload=snapshot).model_dump(mode="json")
                )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect(websocket)

    return app


app = create_app()

__all__ = ["app", "create_app", "SimulatedTickStream"]
