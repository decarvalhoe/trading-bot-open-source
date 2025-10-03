from __future__ import annotations

import asyncio
import struct
from datetime import datetime, timezone
import logging
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)


HEADER_STRUCT = struct.Struct("<HH")
LOGON_REQUEST_STRUCT = struct.Struct("<H32s32s64sH")
LOGON_RESPONSE_STRUCT = struct.Struct("<H64s")
SUBSCRIBE_REQUEST_STRUCT = struct.Struct("<I32s32sB")
SUBSCRIBE_RESPONSE_STRUCT = struct.Struct("<I32s32sB64s")
TRADE_UPDATE_STRUCT = struct.Struct("<I32s32sddd")


class MessageType:
    LOGON_REQUEST = 1
    LOGON_RESPONSE = 2
    LOGOFF = 5
    MARKET_DATA_SUBSCRIBE = 101
    MARKET_DATA_SUBSCRIPTION_RESPONSE = 102
    MARKET_DATA_UPDATE_TRADE = 103


class LogonResult:
    SUCCESS = 1


@dataclass(slots=True)
class DTCConfig:
    host: str
    port: int
    client_user_id: str = ""
    client_password: str = ""
    client_name: str = "market-data-service"
    protocol_version: int = 8
    heartbeat_interval: int = 15
    reconnect_delay: float = 0.5
    handshake_timeout: float = 5.0


class DTCAdapter:
    """Coroutine based client for the Sierra Chart DTC protocol."""

    def __init__(self, config: DTCConfig) -> None:
        self._config = config
        self._lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._subscriptions: dict[tuple[str, str], int] = {}
        self._next_request_id = 1

    async def connect(self) -> None:
        async with self._lock:
            if self._connected:
                return

            logger.info(
                "Establishing DTC connection to %s:%s for %s",
                self._config.host,
                self._config.port,
                self._config.client_user_id or "anonymous",
            )

            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._config.host, self._config.port),
                    timeout=self._config.handshake_timeout,
                )
            except Exception as exc:  # noqa: BLE001
                raise ConnectionError("Failed to open DTC TCP connection") from exc

            self._reader = reader
            self._writer = writer

            try:
                await self._send_message(
                    MessageType.LOGON_REQUEST,
                    LOGON_REQUEST_STRUCT.pack(
                        self._config.protocol_version,
                        self._encode_string(self._config.client_user_id, 32),
                        self._encode_string(self._config.client_password, 32),
                        self._encode_string(self._config.client_name, 64),
                        self._config.heartbeat_interval,
                    ),
                )

                message_type, payload = await asyncio.wait_for(
                    self._read_message(),
                    timeout=self._config.handshake_timeout,
                )
            except Exception:  # noqa: BLE001
                await self._reset_connection()
                raise

            if message_type != MessageType.LOGON_RESPONSE:
                await self._reset_connection()
                raise ConnectionError(
                    f"Expected LOGON_RESPONSE from DTC server, received {message_type}"
                )

            result_code, text = LOGON_RESPONSE_STRUCT.unpack(
                payload[: LOGON_RESPONSE_STRUCT.size]
            )

            if result_code != LogonResult.SUCCESS:
                await self._reset_connection()
                message = self._decode_string(text)
                raise PermissionError(message or "DTC logon rejected")

            self._subscriptions.clear()
            self._next_request_id = 1
            self._connected = True

    async def publish_ticks(self, ticks: Iterable[Any]) -> None:
        batch = list(ticks)
        if not batch:
            return

        for attempt in range(2):
            try:
                await self._ensure_connected()
                async with self._send_lock:
                    for tick in batch:
                        symbol, exchange = self._extract_symbol_exchange(tick)
                        request_id = await self._ensure_subscription(symbol, exchange)
                        payload = self._serialise_tick(tick, symbol, exchange, request_id)
                        await self._send_message(
                            MessageType.MARKET_DATA_UPDATE_TRADE,
                            payload,
                        )
                return
            except (asyncio.IncompleteReadError, ConnectionError, OSError) as exc:
                logger.warning("DTC publish attempt %s failed: %s", attempt + 1, exc)
                await self._reset_connection()
                if attempt == 0:
                    await asyncio.sleep(self._config.reconnect_delay)
                    continue
                raise

    async def close(self) -> None:
        async with self._lock:
            if not self._connected:
                return

            try:
                await self._send_message(MessageType.LOGOFF, b"")
            except Exception:  # noqa: BLE001 - best effort shutdown
                logger.debug("Failed to send DTC logoff", exc_info=True)

            await self._reset_connection()

    async def _ensure_connected(self) -> None:
        if self._connected:
            reader = self._reader
            writer = self._writer
            if reader is not None and reader.at_eof():
                await self._reset_connection()
            elif writer is not None and writer.is_closing():
                await self._reset_connection()
        if not self._connected:
            await self.connect()

    async def _send_message(self, message_type: int, payload: bytes) -> None:
        writer = self._writer
        if writer is None:
            raise ConnectionError("DTC connection is not established")
        if writer.is_closing():
            raise ConnectionError("DTC transport is closing")

        size = HEADER_STRUCT.size + len(payload)
        writer.write(HEADER_STRUCT.pack(size, message_type) + payload)
        await writer.drain()

    async def _read_message(self) -> tuple[int, bytes]:
        reader = self._reader
        if reader is None:
            raise ConnectionError("DTC connection is not established")

        header = await reader.readexactly(HEADER_STRUCT.size)
        size, message_type = HEADER_STRUCT.unpack(header)
        if size < HEADER_STRUCT.size:
            raise ConnectionError("Malformed DTC frame received")
        payload = await reader.readexactly(size - HEADER_STRUCT.size)
        return message_type, payload

    async def _ensure_subscription(self, symbol: str, exchange: str) -> int:
        key = (symbol, exchange)
        if key in self._subscriptions:
            return self._subscriptions[key]

        request_id = self._next_request_id
        self._next_request_id += 1

        await self._send_message(
            MessageType.MARKET_DATA_SUBSCRIBE,
            SUBSCRIBE_REQUEST_STRUCT.pack(
                request_id,
                self._encode_string(symbol, 32),
                self._encode_string(exchange, 32),
                1,
            ),
        )

        message_type, payload = await asyncio.wait_for(
            self._read_message(),
            timeout=self._config.handshake_timeout,
        )

        if message_type != MessageType.MARKET_DATA_SUBSCRIPTION_RESPONSE:
            raise ConnectionError(
                f"Expected subscription response, received message type {message_type}"
            )

        (
            response_id,
            response_symbol,
            response_exchange,
            result_code,
            reason,
        ) = SUBSCRIBE_RESPONSE_STRUCT.unpack(payload[: SUBSCRIBE_RESPONSE_STRUCT.size])

        if response_id != request_id:
            raise ConnectionError("Mismatched subscription response identifier")

        if result_code != 0:
            text = self._decode_string(reason)
            raise RuntimeError(text or "DTC subscription rejected")

        self._subscriptions[key] = request_id
        return request_id

    async def _reset_connection(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        self._connected = False
        self._subscriptions.clear()
        self._next_request_id = 1

        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001 - defensive
                logger.debug("Error waiting for DTC connection to close", exc_info=True)

    def _serialise_tick(
        self,
        tick: Any,
        symbol: str,
        exchange: str,
        request_id: int,
    ) -> bytes:
        price = float(self._extract_field(tick, "price", 0.0))
        size = float(self._extract_field(tick, "size", 0.0) or 0.0)
        timestamp = self._extract_field(tick, "timestamp", None)
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            epoch = timestamp.timestamp()
        else:
            epoch = float(timestamp) if timestamp is not None else datetime.now(timezone.utc).timestamp()

        return TRADE_UPDATE_STRUCT.pack(
            request_id,
            self._encode_string(symbol, 32),
            self._encode_string(exchange, 32),
            price,
            size,
            epoch,
        )

    def _extract_symbol_exchange(self, tick: Any) -> tuple[str, str]:
        symbol = self._extract_field(tick, "symbol", "")
        exchange = self._extract_field(tick, "exchange", "")
        if not symbol:
            raise ValueError("Tick payload missing symbol field")
        return str(symbol), str(exchange)

    @staticmethod
    def _extract_field(tick: Any, name: str, default: Any) -> Any:
        if isinstance(tick, Mapping):
            return tick.get(name, default)
        return getattr(tick, name, default)

    @staticmethod
    def _encode_string(value: str, length: int) -> bytes:
        encoded = value.encode("utf-8")[: max(length - 1, 0)]
        return encoded + b"\x00" * (length - len(encoded))

    @staticmethod
    def _decode_string(value: bytes) -> str:
        return value.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
