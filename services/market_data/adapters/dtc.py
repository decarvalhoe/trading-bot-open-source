from __future__ import annotations

import asyncio
import contextlib
import enum
import logging
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)


class DTCMessageType(enum.IntEnum):
    """Subset of message identifiers from the DTC specification."""

    LOGON_REQUEST = 1
    LOGON_RESPONSE = 2
    HEARTBEAT = 3
    LOGOFF = 5
    MARKET_DATA_SUBSCRIBE = 101
    MARKET_DATA_UNSUBSCRIBE = 102
    MARKET_DATA_UPDATE_TRADE = 103


@dataclass(slots=True)
class DTCConfig:
    host: str
    port: int
    client_user_id: str = ""
    client_password: str = ""
    client_name: str = "market-data-service"
    protocol_version: int = 8
    heartbeat_interval: int = 15
    default_exchange: str = ""


@dataclass(slots=True)
class _SymbolSubscription:
    symbol_id: int
    active: bool = False


class DTCAdapter:
    """Coroutine based client for the Sierra Chart DTC protocol."""

    _SEND_TIMEOUT = 2.0

    def __init__(self, config: DTCConfig) -> None:
        self._config = config
        self._connection_lock = asyncio.Lock()
        self._io_lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._next_symbol_id = 1
        self._subscriptions: dict[str, _SymbolSubscription] = {}

    async def connect(self) -> None:
        await self._ensure_connection(force=True)

    async def publish_ticks(self, ticks: Iterable[Any]) -> None:
        batch: list[Any] = list(ticks)
        if not batch:
            return
        await self._ensure_connection()
        for tick in batch:
            payload = await self._encode_trade_update(tick)
            await self._send_message(DTCMessageType.MARKET_DATA_UPDATE_TRADE, payload)

    async def close(self) -> None:
        async with self._connection_lock:
            if not self._connected:
                return
            try:
                await self._send_message(DTCMessageType.LOGOFF, b"", ensure_connected=False)
            except Exception:  # noqa: BLE001 - ensure closure even on framing issues
                logger.debug("Failed to send DTC logoff", exc_info=True)
            if self._writer is not None:
                self._writer.close()
                with contextlib.suppress(Exception):
                    await self._writer.wait_closed()
            self._reader = None
            self._writer = None
            self._connected = False
            for subscription in self._subscriptions.values():
                subscription.active = False

    async def subscribe(self, symbol: str) -> int:
        subscription = self._subscriptions.get(symbol)
        if subscription is None:
            subscription = _SymbolSubscription(symbol_id=self._next_symbol_id)
            self._next_symbol_id += 1
            self._subscriptions[symbol] = subscription
        if subscription.active:
            return subscription.symbol_id

        payload = self._encode_subscription(symbol, subscription.symbol_id)
        await self._send_message(DTCMessageType.MARKET_DATA_SUBSCRIBE, payload)
        subscription.active = True
        return subscription.symbol_id

    async def _encode_trade_update(self, tick: Any) -> bytes:
        data: Mapping[str, Any]
        if isinstance(tick, Mapping):
            data = tick
        else:
            data = getattr(tick, "__dict__", {})
        symbol = str(data.get("symbol", ""))
        if not symbol:
            raise ValueError("Tick payload must include a symbol")
        price_value = data.get("price")
        price = float(price_value) if price_value is not None else 0.0
        size_value = data.get("size")
        size = float(size_value) if size_value is not None else 0.0
        timestamp = data.get("timestamp")
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            timestamp = timestamp.astimezone(timezone.utc)
            epoch = int(timestamp.timestamp() * 1_000_000)
        elif timestamp is None:
            epoch = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        else:
            epoch = int(timestamp)

        symbol_id = await self.subscribe(symbol)
        return struct.pack("<IddQ", symbol_id, price, size, epoch)

    def _encode_subscription(self, symbol: str, symbol_id: int) -> bytes:
        exchange = self._config.default_exchange
        return (
            struct.pack("<II", symbol_id, symbol_id)
            + self._encode_string(symbol, 64)
            + self._encode_string(exchange, 32)
        )

    async def _ensure_connection(self, *, force: bool = False) -> None:
        if self._connected and not force and self._writer and not self._writer.is_closing():
            return
        async with self._connection_lock:
            if self._connected and not force and self._writer and not self._writer.is_closing():
                return
            await self._open_connection()

    async def _open_connection(self) -> None:
        logger.info(
            "Establishing DTC connection to %s:%s for %s",
            self._config.host,
            self._config.port,
            self._config.client_user_id or "anonymous",
        )
        self._reader, self._writer = await asyncio.open_connection(
            self._config.host, self._config.port
        )
        await self._perform_logon()
        self._connected = True
        for subscription in self._subscriptions.values():
            subscription.active = False
        await self._resubscribe()

    async def _perform_logon(self) -> None:
        payload = self._encode_logon_request()
        await self._send_message(DTCMessageType.LOGON_REQUEST, payload, ensure_connected=False)
        response_type, response_payload = await self._read_message()
        if response_type != DTCMessageType.LOGON_RESPONSE:
            raise ConnectionError(f"Unexpected DTC message {response_type} during logon")
        result_code, message = self._decode_logon_response(response_payload)
        if result_code != 1:
            raise PermissionError(f"DTC logon rejected: {message or 'unknown error'}")

    async def _resubscribe(self) -> None:
        if not self._subscriptions:
            return
        for symbol, subscription in self._subscriptions.items():
            payload = self._encode_subscription(symbol, subscription.symbol_id)
            await self._send_message(DTCMessageType.MARKET_DATA_SUBSCRIBE, payload, retry=False)
            subscription.active = True

    async def _send_message(
        self,
        message_type: DTCMessageType,
        payload: bytes,
        *,
        ensure_connected: bool = True,
        retry: bool = True,
    ) -> None:
        if ensure_connected:
            await self._ensure_connection()
        writer = self._writer
        if writer is None:
            raise ConnectionError("DTC connection is not available")
        message = self._frame_message(message_type, payload)
        caught_exc: Exception | None = None
        async with self._io_lock:
            try:
                writer.write(message)
                await asyncio.wait_for(writer.drain(), timeout=self._SEND_TIMEOUT)
            except (
                ConnectionError,
                asyncio.IncompleteReadError,
                BrokenPipeError,
                asyncio.TimeoutError,
            ) as exc:
                logger.warning("DTC send failed: %s", exc)
                caught_exc = exc
        if caught_exc is not None:
            await self._handle_disconnect()
            if retry:
                await self._ensure_connection(force=True)
                await self._send_message(
                    message_type,
                    payload,
                    ensure_connected=False,
                    retry=False,
                )
            else:
                raise caught_exc

    async def _handle_disconnect(self) -> None:
        self._connected = False
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._writer.wait_closed(), timeout=self._SEND_TIMEOUT)
        self._reader = None
        self._writer = None
        for subscription in self._subscriptions.values():
            subscription.active = False

    async def _read_message(self) -> tuple[DTCMessageType, bytes]:
        reader = self._reader
        if reader is None:
            raise ConnectionError("DTC connection is not available")
        header = await reader.readexactly(4)
        size, message_type = struct.unpack("<HH", header)
        if size < 4:
            raise ConnectionError("Invalid DTC message size")
        payload = await reader.readexactly(size - 4)
        return DTCMessageType(message_type), payload

    def _encode_logon_request(self) -> bytes:
        return (
            struct.pack("<I", self._config.protocol_version)
            + self._encode_string(self._config.client_user_id, 32)
            + self._encode_string(self._config.client_password, 32)
            + struct.pack("<H", self._config.heartbeat_interval)
            + self._encode_string(self._config.client_name, 32)
        )

    @staticmethod
    def _encode_string(value: str, length: int) -> bytes:
        data = value.encode("utf-8")[: length - 1] if length > 0 else b""
        return data + b"\x00" * (length - len(data))

    @staticmethod
    def _frame_message(message_type: DTCMessageType, payload: bytes) -> bytes:
        size = 4 + len(payload)
        return struct.pack("<HH", size, int(message_type)) + payload

    @staticmethod
    def _decode_logon_response(payload: bytes) -> tuple[int, str]:
        if len(payload) < 2:
            return 0, ""
        result_code = struct.unpack_from("<H", payload, 0)[0]
        text = payload[2:]
        text = text.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
        return result_code, text
