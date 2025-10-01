from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

os.environ.setdefault("TRADINGVIEW_HMAC_SECRET", "test-secret")

from services.market_data.app.main import app


def test_symbol_context_snapshot_contains_indicators() -> None:
    client = TestClient(app)
    response = client.get("/symbols/BTCUSDT/context")
    assert response.status_code == 200
    payload = response.json()

    assert payload["symbol"] == "BTCUSDT"
    assert payload["price"] > 0
    assert payload["volume"] > 0
    assert "indicators" in payload
    assert "moving_average" in payload["indicators"]
    assert "total_bid_volume" in payload and payload["total_bid_volume"] > 0


def test_streaming_endpoint_emits_market_events() -> None:
    with TestClient(app) as client:
        with client.stream("GET", "/streaming/BTCUSDT", params={"max_events": 3}) as response:
            assert response.status_code == 200
            events: list[dict[str, object]] = []
            for line in response.iter_lines():
                if not line:
                    continue
                events.append(json.loads(line))
                if len(events) >= 3:
                    break

    assert events, "Streaming endpoint should emit events"
    first = events[0]
    assert "price" in first and isinstance(first["price"], (int, float))
    assert any("moving_average" in (event.get("metadata") or {}) for event in events)
