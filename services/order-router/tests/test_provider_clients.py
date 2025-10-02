from __future__ import annotations

import hashlib
import hmac
import httpx
import pytest
import respx

from providers.binance import BinanceClient, BinanceConfig
from providers.ibkr import IBKRClient, IBKRConfig


@respx.mock
def test_binance_client_signs_requests_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("providers.binance.time.time", lambda: 1_000_000.0)
    config = BinanceConfig(api_key="api-key", api_secret="secret", base_url="https://api.test")
    client = BinanceClient(config, max_retries=2, backoff_factor=0.0)

    responses = iter(
        [
            httpx.Response(500, text="error"),
            httpx.Response(
                200,
                json={
                    "orderId": 12345,
                    "status": "FILLED",
                    "executedQty": "1.0",
                    "price": "100.0",
                },
            ),
        ]
    )

    route = respx.post("https://api.test/api/v3/order").mock(side_effect=lambda request: next(responses))

    payload = client.place_order(
        symbol="btc/usdt",
        side="buy",
        order_type="limit",
        quantity=1.0,
        price=100.0,
        time_in_force="GTC",
    )

    client.close()

    assert payload["orderId"] == 12345
    assert route.call_count == 2

    last_request = route.calls[-1].request
    assert last_request.headers["X-MBX-APIKEY"] == "api-key"
    params = dict(last_request.url.params)
    assert params["symbol"] == "BTCUSDT"
    assert params["timestamp"] == "1000000000"
    expected_query = "&".join(f"{key}={params[key]}" for key in sorted(params) if key != "signature")
    expected_signature = hmac.new(b"secret", expected_query.encode("utf-8"), hashlib.sha256).hexdigest()
    assert params["signature"] == expected_signature


@respx.mock
def test_ibkr_client_reauthenticates_on_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("providers.ibkr.time.sleep", lambda _: None)
    config = IBKRConfig(
        api_key="ib-key",
        api_secret="ib-secret",
        base_url="https://ibkr.test",
        account_id="DU12345",
    )
    client = IBKRClient(config, max_retries=2, backoff_factor=0.0)

    session_route = respx.post("https://ibkr.test/session").mock(
        side_effect=[
            httpx.Response(200, json={"session": "token-1"}),
            httpx.Response(200, json={"session": "token-2"}),
        ]
    )

    order_calls: list[httpx.Response] = [
        httpx.Response(401, json={"error": "expired"}),
        httpx.Response(
            200,
            json={
                "orderId": "IB-1",
                "status": "Filled",
                "filledQuantity": 10,
                "avgPrice": 101.5,
            },
        ),
    ]
    order_route = respx.post("https://ibkr.test/iserver/account/DU12345/order").mock(
        side_effect=lambda request: order_calls.pop(0)
    )

    payload = client.place_order(
        symbol="aapl",
        side="buy",
        quantity=10,
        order_type="limit",
        price=101.5,
        time_in_force="GTC",
    )

    client.close()

    assert payload["orderId"] == "IB-1"
    assert order_route.call_count == 2
    assert session_route.call_count == 2
    assert payload["filledQuantity"] == 10
    assert payload["status"] == "Filled"
