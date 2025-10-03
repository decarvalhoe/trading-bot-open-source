from __future__ import annotations

import asyncio
import math
import struct
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from services.market_data.adapters import DTCAdapter, DTCConfig

HEADER_STRUCT = struct.Struct("<HH")
LOGON_REQUEST_STRUCT = struct.Struct("<H32s32s64sH")
LOGON_RESPONSE_STRUCT = struct.Struct("<H64s")
SUBSCRIBE_REQUEST_STRUCT = struct.Struct("<I32s32sB")
SUBSCRIBE_RESPONSE_STRUCT = struct.Struct("<I32s32sB64s")
TRADE_UPDATE_STRUCT = struct.Struct("<I32s32sddd")

LOGON_REQUEST = 1
LOGON_RESPONSE = 2
LOGOFF = 5
MARKET_DATA_SUBSCRIBE = 101
MARKET_DATA_SUBSCRIPTION_RESPONSE = 102
MARKET_DATA_UPDATE_TRADE = 103


def _encode_string(value: str, length: int) -> bytes:
    encoded = value.encode("utf-8")[: max(length - 1, 0)]
    return encoded + b"\x00" * (length - len(encoded))


def _decode_string(value: bytes) -> str:
    return value.split(b"\x00", 1)[0].decode("utf-8")


def _pack_message(message_type: int, payload: bytes) -> bytes:
    return HEADER_STRUCT.pack(HEADER_STRUCT.size + len(payload), message_type) + payload


async def _read_message(reader: asyncio.StreamReader) -> Tuple[int, bytes]:
    header = await reader.readexactly(HEADER_STRUCT.size)
    size, message_type = HEADER_STRUCT.unpack(header)
    payload = await reader.readexactly(size - HEADER_STRUCT.size)
    return message_type, payload


def test_dtc_adapter_handshake_and_publish() -> None:
    async def run() -> Dict[str, Any]:
        events: Dict[str, Any] = {}
        close_event = asyncio.Event()

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                message_type, payload = await _read_message(reader)
                assert message_type == LOGON_REQUEST
                (
                    protocol_version,
                    username,
                    password,
                    client_name,
                    heartbeat,
                ) = LOGON_REQUEST_STRUCT.unpack(payload)
                events["logon"] = {
                    "protocol": protocol_version,
                    "username": _decode_string(username),
                    "password": _decode_string(password),
                    "client_name": _decode_string(client_name),
                    "heartbeat": heartbeat,
                }
                response_payload = LOGON_RESPONSE_STRUCT.pack(1, _encode_string("ok", 64))
                writer.write(_pack_message(LOGON_RESPONSE, response_payload))
                await writer.drain()

                message_type, payload = await _read_message(reader)
                assert message_type == MARKET_DATA_SUBSCRIBE
                request_id, symbol, exchange, subscribe_flag = SUBSCRIBE_REQUEST_STRUCT.unpack(
                    payload
                )
                events["subscribe"] = {
                    "request_id": request_id,
                    "symbol": _decode_string(symbol),
                    "exchange": _decode_string(exchange),
                    "subscribe": subscribe_flag,
                }
                ack_payload = SUBSCRIBE_RESPONSE_STRUCT.pack(
                    request_id,
                    symbol,
                    exchange,
                    0,
                    _encode_string("", 64),
                )
                writer.write(_pack_message(MARKET_DATA_SUBSCRIPTION_RESPONSE, ack_payload))
                await writer.drain()

                message_type, payload = await _read_message(reader)
                assert message_type == MARKET_DATA_UPDATE_TRADE
                (
                    trade_request_id,
                    trade_symbol,
                    trade_exchange,
                    price,
                    size,
                    epoch,
                ) = TRADE_UPDATE_STRUCT.unpack(payload)
                events["trade"] = {
                    "request_id": trade_request_id,
                    "symbol": _decode_string(trade_symbol),
                    "exchange": _decode_string(trade_exchange),
                    "price": price,
                    "size": size,
                    "epoch": epoch,
                }

                message_type, payload = await _read_message(reader)
                assert message_type == LOGOFF
                events["logoff"] = True
            finally:
                writer.close()
                await writer.wait_closed()
                close_event.set()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        server_task = asyncio.create_task(server.serve_forever())

        adapter = DTCAdapter(
            DTCConfig(
                host=host,
                port=port,
                client_user_id="client",
                client_password="secret",
                client_name="pytest",
            )
        )

        await adapter.connect()
        tick = {
            "symbol": "ES",
            "exchange": "CME",
            "price": 4200.25,
            "size": 1.5,
            "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        }
        await adapter.publish_ticks([tick])
        await adapter.close()

        await asyncio.wait_for(close_event.wait(), timeout=1.0)
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await server_task
        server.close()
        await server.wait_closed()
        return events

    events = asyncio.run(run())
    assert events["logon"]["username"] == "client"
    assert events["logon"]["client_name"] == "pytest"
    assert events["subscribe"]["symbol"] == "ES"
    assert events["trade"]["request_id"] == events["subscribe"]["request_id"]
    assert math.isclose(events["trade"]["price"], 4200.25)
    assert math.isclose(events["trade"]["size"], 1.5)


def test_dtc_adapter_reconnects_after_disconnect() -> None:
    async def run() -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "connections": 0,
            "prices": [],
            "subscriptions": [],
        }

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            state["connections"] += 1
            try:
                message_type, payload = await _read_message(reader)
                assert message_type == LOGON_REQUEST
                writer.write(_pack_message(LOGON_RESPONSE, LOGON_RESPONSE_STRUCT.pack(1, b"\x00" * 64)))
                await writer.drain()

                message_type, payload = await _read_message(reader)
                assert message_type == MARKET_DATA_SUBSCRIBE
                request_id, symbol, exchange, _ = SUBSCRIBE_REQUEST_STRUCT.unpack(payload)
                state["subscriptions"].append(
                    (state["connections"], _decode_string(symbol))
                )
                writer.write(
                    _pack_message(
                        MARKET_DATA_SUBSCRIPTION_RESPONSE,
                        SUBSCRIBE_RESPONSE_STRUCT.pack(
                            request_id,
                            symbol,
                            exchange,
                            0,
                            b"\x00" * 64,
                        ),
                    )
                )
                await writer.drain()

                message_type, payload = await _read_message(reader)
                assert message_type == MARKET_DATA_UPDATE_TRADE
                request_id, _, _, price, _, _ = TRADE_UPDATE_STRUCT.unpack(payload)
                state["prices"].append(price)

                if state["connections"] == 1:
                    writer.close()
                    writer.transport.abort()  # Forcefully terminate to simulate drop
                    await writer.wait_closed()
                    return

                try:
                    message_type, _ = await _read_message(reader)
                    if message_type == LOGOFF:
                        state["closed"] = True
                except asyncio.IncompleteReadError:
                    state["closed"] = True
            finally:
                if not writer.is_closing():
                    writer.close()
                await writer.wait_closed()
                if state.get("closed") and state["connections"] >= 2:
                    state["closed_after_logoff"] = True

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        server_task = asyncio.create_task(server.serve_forever())

        adapter = DTCAdapter(DTCConfig(host=host, port=port, client_user_id="client"))

        tick_one = {
            "symbol": "ES",
            "exchange": "CME",
            "price": 4200.25,
            "size": 1.0,
            "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        }
        tick_two = {
            "symbol": "ES",
            "exchange": "CME",
            "price": 4201.25,
            "size": 2.0,
            "timestamp": datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        }

        await adapter.publish_ticks([tick_one])
        await asyncio.sleep(0.05)
        await adapter.publish_ticks([tick_two])
        await adapter.close()
        await asyncio.sleep(0.05)
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await server_task
        server.close()
        await server.wait_closed()
        return state

    state = asyncio.run(run())
    assert state["connections"] >= 2
    assert state["subscriptions"][0][0] == 1
    assert state["subscriptions"][-1][0] == state["connections"]
    assert state["prices"] == [4200.25, 4201.25]
    assert state.get("closed_after_logoff") is True
