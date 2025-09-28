from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect

from libs.entitlements import install_entitlements_middleware
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics

from .config import Settings, get_settings
from .dependencies import WebsocketAuthorizer, get_bridge
from .pipeline import InMemoryPublisher, NatsJetStreamPublisher, RedisStreamPublisher, StreamingBridge
from .repositories import RoomStore, SessionStore
from .routers import ingest, rooms, sessions, moderation


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    bridge = await create_bridge(settings)
    app.state.bridge = bridge
    app.state.rooms = RoomStore()
    app.state.sessions = SessionStore()
    app.state.websocket_authorizer = WebsocketAuthorizer(settings)
    try:
        yield
    finally:
        await bridge.aclose()


configure_logging("streaming")


def create_app() -> FastAPI:
    app = FastAPI(title="Streaming Service", lifespan=lifespan)
    settings = get_settings()
    install_entitlements_middleware(app, required_capabilities=[settings.entitlements_capability])
    app.add_middleware(RequestContextMiddleware, service_name="streaming")
    setup_metrics(app, service_name="streaming")
    app.include_router(rooms.router)
    app.include_router(sessions.router)
    app.include_router(ingest.router)
    app.include_router(moderation.router)

    @app.websocket("/ws/rooms/{room_id}")
    async def websocket_room(websocket: WebSocket, room_id: str):
        authorizer: WebsocketAuthorizer = app.state.websocket_authorizer
        await authorizer.authorize(websocket)
        await websocket.accept()
        bridge: StreamingBridge = app.state.bridge
        await bridge.register(room_id, websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await bridge.unregister(room_id, websocket)
        except Exception:
            await bridge.unregister(room_id, websocket)
            await websocket.close()
            raise

    return app


async def create_bridge(settings: Settings) -> StreamingBridge:
    backend = settings.pipeline_backend
    if backend == "memory":
        publisher = InMemoryPublisher()
        return StreamingBridge(publisher)
    if backend == "redis":  # pragma: no cover - requires Redis
        try:
            import redis.asyncio as redis_asyncio  # type: ignore
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError("redis.asyncio n'est pas installé") from exc

        client = redis_asyncio.from_url(settings.redis_url)
        publisher = RedisStreamPublisher(client)
        return StreamingBridge(publisher)
    if backend == "nats":  # pragma: no cover - requires NATS
        try:
            import nats
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError("nats-py n'est pas installé") from exc

        connection = await nats.connect(settings.nats_url)
        publisher = NatsJetStreamPublisher(connection)
        return StreamingBridge(publisher)
    raise RuntimeError(f"Backend {backend} inconnu")


app = create_app()


__all__ = ["app", "create_app", "create_bridge"]
