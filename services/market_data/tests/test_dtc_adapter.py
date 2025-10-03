from __future__ import annotations

import asyncio
import struct
from datetime import datetime, timezone
from typing import Any, Dict, List

from services.market_data.adapters.dtc import DTCAdapter, DTCConfig, DTCMessageType


def _encode_string(value: str, length: int) -> bytes:
    if length <= 0:
        return b""
    encoded = value.encode("utf-8")[: length - 1]
    return encoded + b"\x00" * (length - len(encoded))


def _frame(message_type: DTCMessageType, payload: bytes) -> bytes:
    return struct.pack("<HH", 4 + len(payload), int(message_type)) + payload


def _decode_string(buffer: bytes) -> str:
    return buffer.split(b"\x00", 1)[0].decode("utf-8")


def _decode_logon(payload: bytes) -> Dict[str, Any]:
    version = struct.unpack_from("<I", payload, 0)[0]
    username = _decode_string(payload[4:36])
    password = _decode_string(payload[36:68])
    heartbeat = struct.unpack_from("<H", payload, 68)[0]
    client_name = _decode_string(payload[70:102])
    return {
        "version": version,
        "username": username,
        "password": password,
        "heartbeat": heartbeat,
        "client_name": client_name,
    }


def _decode_subscription(payload: bytes) -> Dict[str, Any]:
    request_id, symbol_id = struct.unpack_from("<II", payload, 0)
    symbol = _decode_string(payload[8:72])
    exchange = _decode_string(payload[72:104])
    return {
        "request_id": request_id,
        "symbol_id": symbol_id,
        "symbol": symbol,
        "exchange": exchange,
    }


def _decode_trade_update(payload: bytes) -> Dict[str, Any]:
    symbol_id, price, size, epoch = struct.unpack("<IddQ", payload)
    return {
        "symbol_id": symbol_id,
        "price": price,
        "size": size,
        "epoch": epoch,
    }


class MockDTCServer:
    def __init__(
        self,
        *,
        drop_after_subscribe: bool = False,
        drop_after_update: bool = False,
    ) -> None:
        self.drop_after_subscribe = drop_after_subscribe
        self.drop_after_update = drop_after_update
        self.logons: List[Dict[str, Any]] = []
        self.subscriptions: List[Dict[str, Any]] = []
        self.updates: List[Dict[str, Any]] = []
        self.logoffs: int = 0
        self.connections = 0
        self._server: asyncio.AbstractServer | None = None
        self.port: int | None = None
        self._dropped_after_update = False

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_connection, "127.0.0.1", 0)
        sockets = self._server.sockets or []
        if not sockets:
            raise RuntimeError("failed to open mock DTC socket")
        self.port = sockets[0].getsockname()[1]

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.connections += 1
        connection_index = self.connections
        try:
            while True:
                header = await reader.readexactly(4)
                size, message_type = struct.unpack("<HH", header)
                payload = await reader.readexactly(size - 4)
                message = DTCMessageType(message_type)
                if message == DTCMessageType.LOGON_REQUEST:
                    self.logons.append(_decode_logon(payload))
                    writer.write(
                        _frame(
                            DTCMessageType.LOGON_RESPONSE,
                            struct.pack("<H", 1) + _encode_string("ok", 64),
                        )
                    )
                    await writer.drain()
                elif message == DTCMessageType.MARKET_DATA_SUBSCRIBE:
                    self.subscriptions.append(_decode_subscription(payload))
                    if self.drop_after_subscribe and connection_index == 1:
                        writer.transport.abort()
                        return
                elif message == DTCMessageType.MARKET_DATA_UPDATE_TRADE:
                    self.updates.append(_decode_trade_update(payload))
                    if self.drop_after_update and not self._dropped_after_update:
                        self._dropped_after_update = True
                        writer.transport.abort()
                        return
                elif message == DTCMessageType.LOGOFF:
                    self.logoffs += 1
                    writer.close()
                    await writer.wait_closed()
                    return
        except asyncio.IncompleteReadError:
            return


def test_dtc_adapter_handshake_and_publish() -> None:
    async def run() -> None:
        server = MockDTCServer()
        await server.start()
        assert server.port is not None

        adapter = DTCAdapter(
            DTCConfig(
                host="127.0.0.1",
                port=server.port,
                client_user_id="demo",
                client_password="secret",
                client_name="tester",
                default_exchange="CME",
            )
        )

        await adapter.connect()
        timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        await adapter.publish_ticks(
            [
                {
                    "symbol": "ESZ4",
                    "price": 4200.25,
                    "size": 2.0,
                    "timestamp": timestamp,
                }
            ]
        )
        await asyncio.sleep(0.05)
        await adapter.close()
        await asyncio.sleep(0.05)
        await server.close()

        assert len(server.logons) == 1
        assert server.logons[0]["username"] == "demo"
        assert server.logons[0]["password"] == "secret"
        assert server.logons[0]["client_name"] == "tester"
        assert len(server.subscriptions) == 1
        assert server.subscriptions[0]["symbol"] == "ESZ4"
        assert server.subscriptions[0]["exchange"] == "CME"
        assert len(server.updates) == 1
        assert server.updates[0]["symbol_id"] == server.subscriptions[0]["symbol_id"]
        assert server.updates[0]["price"] == 4200.25
        assert server.updates[0]["size"] == 2.0
        assert server.logoffs == 1

    asyncio.run(run())


def test_dtc_adapter_reconnects_after_disconnect() -> None:
    async def run() -> None:
        server = MockDTCServer()
        await server.start()
        assert server.port is not None

        adapter = DTCAdapter(
            DTCConfig(host="127.0.0.1", port=server.port, client_user_id="reconnect")
        )

        first_timestamp = datetime.now(timezone.utc)
        await adapter.publish_ticks(
            [
                {
                    "symbol": "NQZ4",
                    "price": 18000.5,
                    "size": 1.0,
                    "timestamp": first_timestamp,
                }
            ]
        )
        await asyncio.sleep(0.05)

        await adapter.close()
        await asyncio.sleep(0.05)

        second_timestamp = datetime.now(timezone.utc)
        await adapter.publish_ticks(
            [
                {
                    "symbol": "NQZ4",
                    "price": 18001.0,
                    "size": 1.5,
                    "timestamp": second_timestamp,
                }
            ]
        )
        await asyncio.sleep(0.05)
        await adapter.close()
        await asyncio.sleep(0.05)
        await server.close()

        assert server.connections >= 2
        assert len(server.logons) >= 2
        assert len(server.subscriptions) >= 2
        assert len(server.updates) == 2
        assert server.updates[-1]["price"] == 18001.0

    asyncio.run(run())
