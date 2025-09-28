from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Iterable, Protocol

try:  # Optional dependencies: redis / nats may not be installed during unit tests
    from redis.asyncio import Redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Redis = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import nats
    from nats.aio.msg import Msg
except Exception:  # pragma: no cover - optional dependency
    nats = None  # type: ignore
    Msg = Any  # type: ignore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StreamEvent:
    """Événement propagé sur le bus de streaming."""

    room_id: str
    payload: Dict[str, Any]
    source: str

    def model_dump(self) -> Dict[str, Any]:  # Compatible pydantic-like
        return {"room_id": self.room_id, "payload": self.payload, "source": self.source}


class Publisher(Protocol):
    async def publish(self, event: StreamEvent) -> None:
        ...

    async def subscribe(self) -> AsyncIterator[StreamEvent]:  # pragma: no cover - optional usage
        ...

    async def aclose(self) -> None:
        ...


class InMemoryPublisher:
    """Backend par défaut reposant sur asyncio.Queue."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        self._subscribers: set[asyncio.Queue[StreamEvent]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: StreamEvent) -> None:
        async with self._lock:
            if not self._subscribers:
                await self._queue.put(event)
            else:
                for queue in list(self._subscribers):
                    await queue.put(event)

    async def subscribe(self) -> AsyncIterator[StreamEvent]:
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
            while not self._queue.empty():
                await queue.put(self._queue.get_nowait())
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def aclose(self) -> None:
        async with self._lock:
            for queue in list(self._subscribers):
                queue.put_nowait(StreamEvent(room_id="__close__", payload={}, source="system"))
            self._subscribers.clear()
            while not self._queue.empty():
                self._queue.get_nowait()


class RedisStreamPublisher:
    """Implémentation basée sur Redis Streams."""

    def __init__(self, redis: Any, stream_key: str = "streaming.events") -> None:
        if Redis is None:
            raise RuntimeError("redis.asyncio n'est pas installé")
        self._redis = redis
        self._stream_key = stream_key
        self._group = "streaming_service"
        self._consumer = f"consumer-{id(self)}"

    async def publish(self, event: StreamEvent) -> None:
        payload = json.dumps(event.model_dump())
        await self._redis.xadd(self._stream_key, {"event": payload})

    async def subscribe(self) -> AsyncIterator[StreamEvent]:
        await self._redis.xgroup_create(name=self._stream_key, groupname=self._group, id="$", mkstream=True)
        while True:
            messages = await self._redis.xreadgroup(
                groupname=self._group,
                consumername=self._consumer,
                streams={self._stream_key: ">"},
                count=100,
                block=1000,
            )
            for _, entries in messages:
                for message_id, body in entries:
                    try:
                        payload = json.loads(body["event"])
                        yield StreamEvent(**payload)
                    finally:
                        await self._redis.xack(self._stream_key, self._group, message_id)

    async def aclose(self) -> None:
        await self._redis.close()


class NatsJetStreamPublisher:
    """Implémentation basée sur NATS JetStream."""

    def __init__(self, connection: Any, stream_name: str = "STREAMING_EVENTS") -> None:
        if nats is None:
            raise RuntimeError("nats-py n'est pas installé")
        self._connection = connection
        self._stream_name = stream_name
        self._subject = f"{stream_name}.updates"

    async def publish(self, event: StreamEvent) -> None:
        payload = json.dumps(event.model_dump()).encode()
        js = self._connection.jetstream()
        await js.publish(self._subject, payload)

    async def subscribe(self) -> AsyncIterator[StreamEvent]:
        js = self._connection.jetstream()
        sub = await js.subscribe(self._subject, durable="streaming-service")
        async for msg in sub.messages:  # pragma: no cover - requires running NATS
            payload = json.loads(msg.data.decode())
            yield StreamEvent(**payload)
            await msg.ack()

    async def aclose(self) -> None:
        await self._connection.close()


class StreamingBridge:
    """Relie le backend de publication aux websockets du service."""

    def __init__(self, publisher: Publisher) -> None:
        self._publisher = publisher
        self._connections: dict[str, set["StreamingConnection"]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, event: StreamEvent) -> None:
        await self._publisher.publish(event)
        await self._broadcast(event)

    async def _broadcast(self, event: StreamEvent) -> None:
        async with self._lock:
            for connection in list(self._connections.get(event.room_id, set())):
                await connection.send_json(event.model_dump())

    async def register(self, room_id: str, connection: "StreamingConnection") -> None:
        async with self._lock:
            self._connections.setdefault(room_id, set()).add(connection)

    async def unregister(self, room_id: str, connection: "StreamingConnection") -> None:
        async with self._lock:
            connections = self._connections.get(room_id)
            if not connections:
                return
            connections.discard(connection)
            if not connections:
                self._connections.pop(room_id, None)

    async def aclose(self) -> None:
        await self._publisher.aclose()
        async with self._lock:
            for connections in self._connections.values():
                for connection in list(connections):
                    await connection.close()
            self._connections.clear()


class StreamingConnection(Protocol):
    async def send_json(self, data: Dict[str, Any]) -> None:
        ...

    async def close(self) -> None:
        ...


async def stream_events_from_sources(
    bridge: StreamingBridge,
    *,
    sources: Iterable[AsyncIterator[StreamEvent]],
) -> None:
    """Agrège plusieurs flux d'événements et les injecte dans le pont."""

    async def consume(source: AsyncIterator[StreamEvent]) -> None:
        async for event in source:
            await bridge.publish(event)

    await asyncio.gather(*(consume(source) for source in sources))


__all__ = [
    "StreamEvent",
    "Publisher",
    "InMemoryPublisher",
    "RedisStreamPublisher",
    "NatsJetStreamPublisher",
    "StreamingBridge",
    "StreamingConnection",
    "stream_events_from_sources",
]
