from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Annotated, Callable
from urllib.parse import urljoin

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect

from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics

from .config import Settings, get_settings
from .schemas import (
    SessionName,
    StrategyReportPayload,
    TickPayload,
    WatchlistSnapshot,
    WatchlistStreamEvent,
)
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

logger = logging.getLogger(__name__)


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
    app.state.inplay_state = state
    app.state.websocket_manager = manager
    app.add_middleware(RequestContextMiddleware, service_name="inplay")
    setup_metrics(app, service_name="inplay")

    async def get_state() -> InPlayState:
        return state

    async def get_manager() -> WebSocketManager:
        return manager

    def _normalise_base_url(value: str) -> str:
        return value if value.endswith("/") else f"{value}/"

    async def _fetch_json(
        client: httpx.AsyncClient, url: str, timeout: float
    ) -> dict[str, object] | None:
        try:
            response = await client.get(url, timeout=timeout)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            logger.warning("Requête HTTP échouée vers %s: %s", url, exc)
            return None
        except httpx.HTTPError as exc:
            logger.warning("Impossible d'appeler %s: %s", url, exc)
            return None

        payload = response.json()
        if isinstance(payload, dict):
            return payload
        logger.warning("Payload inattendu reçu depuis %s: %s", url, payload)
        return None

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/inplay/watchlists/{watchlist_id}", response_model=WatchlistSnapshot)
    async def get_watchlist(
        watchlist_id: str,
        session: Annotated[SessionName | None, Query()] = None,
        state: InPlayState = Depends(get_state),
    ) -> WatchlistSnapshot:
        try:
            return await state.get_watchlist(watchlist_id, session=session)
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

    @app.get(
        "/inplay/setups/{symbol}/{strategy}",
        response_model=StrategyReportPayload,
        tags=["inplay"],
    )
    async def get_strategy_report(
        symbol: str,
        strategy: str,
        state: InPlayState = Depends(get_state),
    ) -> StrategyReportPayload:
        setup = await state.get_strategy_setup(symbol, strategy)
        if setup is None:
            raise HTTPException(status_code=404, detail="Setup introuvable")

        reports_base = _normalise_base_url(settings.reports_base_url)
        market_base = _normalise_base_url(settings.market_data_base_url)
        reports_endpoint = urljoin(reports_base, f"symbols/{setup.symbol}/summary")
        market_endpoint = urljoin(market_base, f"spot/{setup.symbol}")

        async with httpx.AsyncClient() as client:
            report_task = _fetch_json(
                client,
                reports_endpoint,
                settings.reports_timeout_seconds,
            )
            market_task = _fetch_json(
                client,
                market_endpoint,
                settings.market_data_timeout_seconds,
            )
            report_payload, market_payload = await asyncio.gather(
                report_task,
                market_task,
                return_exceptions=False,
            )

        report_data = None
        risk_data = None
        if report_payload:
            report_section = report_payload.get("report")
            if isinstance(report_section, dict):
                report_data = report_section
            risk_section = report_payload.get("risk")
            if isinstance(risk_section, dict):
                risk_data = risk_section

        return StrategyReportPayload(
            symbol=setup.symbol,
            strategy=setup.strategy,
            session=setup.session,
            setup=setup,
            report=report_data,
            risk=risk_data,
            market=market_payload,
        )

    return app


app = create_app()

__all__ = ["app", "create_app", "SimulatedTickStream"]
