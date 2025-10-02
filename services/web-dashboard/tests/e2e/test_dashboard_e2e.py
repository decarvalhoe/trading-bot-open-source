from __future__ import annotations

import json
import re

import pytest
from playwright.async_api import Page, expect

from libs.portfolio import encode_portfolio_key, encode_position_key


pytestmark = pytest.mark.asyncio

MOCK_WEBSOCKET_INIT = """
(() => {
  const sockets = [];

  class MockWebSocket {
    constructor(url) {
      this.url = url;
      this.readyState = MockWebSocket.CONNECTING;
      this.onopen = null;
      this.onclose = null;
      this.onmessage = null;
      this.onerror = null;
      sockets.push(this);
      setTimeout(() => {
        this.readyState = MockWebSocket.OPEN;
        if (typeof this.onopen === 'function') {
          this.onopen({ target: this });
        }
      }, 0);
    }

    send() {}

    close() {
      this.readyState = MockWebSocket.CLOSED;
      if (typeof this.onclose === 'function') {
        this.onclose({ target: this });
      }
    }
  }

  MockWebSocket.CONNECTING = 0;
  MockWebSocket.OPEN = 1;
  MockWebSocket.CLOSING = 2;
  MockWebSocket.CLOSED = 3;

  window.__mockSockets = sockets;
  window.__emitMockMessage = (payload) => {
    const message = typeof payload === 'string' ? payload : JSON.stringify(payload);
    sockets.forEach((socket) => {
      if (typeof socket.onmessage === 'function') {
        socket.onmessage({ data: message, target: socket });
      }
    });
  };

  window.WebSocket = MockWebSocket;
})();
"""


@pytest.fixture
async def mock_streaming(page: Page):
    """Intercept WebSocket handshake calls and expose helpers to emit updates."""

    async def _handle_handshake(route, _request):
        await route.fulfill(
            status=200,
            headers={"content-type": "application/json"},
            body=json.dumps({"websocket_url": "ws://mocked/stream"}),
        )

    await page.route("**/rooms/**/connection", _handle_handshake)
    await page.add_init_script(MOCK_WEBSOCKET_INIT)


async def test_dashboard_displays_metrics(page: Page, dashboard_base_url: str, mock_streaming):
    await page.goto(f"{dashboard_base_url}/dashboard", wait_until="networkidle")

    await expect(page.get_by_role("heading", name="Performance")).to_be_visible()
    metrics_list = page.get_by_role("list", name="Performance")
    await expect(metrics_list.get_by_role("listitem").filter(has_text="P&L courant")).to_contain_text("$")
    await expect(page.get_by_role("img", name="Graphique des valeurs cumulées des portefeuilles")).to_be_visible()


async def test_dashboard_updates_transactions_from_websocket(
    page: Page, dashboard_base_url: str, mock_streaming
):
    await page.goto(f"{dashboard_base_url}/dashboard", wait_until="networkidle")

    update = {
        "resource": "transactions",
        "items": [
            {
                "timestamp": "2024-04-01T12:00:00Z",
                "portfolio": "Momentum",
                "symbol": "ADA",
                "side": "buy",
                "quantity": 12,
                "price": 1.23,
            }
        ],
    }

    await page.evaluate("payload => window.__emitMockMessage(payload)", update)

    await expect(page.locator("td[data-label='Symbole']", has_text="ADA")).to_be_visible()
    await expect(page.locator("td[data-label='Sens'] span", has_text=re.compile("Buy", re.I))).to_be_visible()


async def test_dashboard_exposes_accessible_landmarks(page: Page, dashboard_base_url: str, mock_streaming):
    await page.goto(f"{dashboard_base_url}/dashboard", wait_until="networkidle")

    await expect(page.get_by_role("heading", level=1, name=re.compile("Vue d'ensemble", re.I))).to_be_visible()
    await expect(page.get_by_role("main")).to_be_visible()
    await expect(page.get_by_role("list", name="Performance")).to_have_attribute("aria-describedby", "metrics-title")
    await expect(page.get_by_role("grid", name="Transactions récentes")).to_have_attribute(
        "aria-describedby", "transactions-title"
    )


async def test_dashboard_updates_positions_after_closing(page: Page, dashboard_base_url: str, mock_streaming):
    growth_id = encode_portfolio_key("alice")
    income_id = encode_portfolio_key("bob")
    msft_id = encode_position_key("alice", "MSFT")
    tlt_id = encode_position_key("bob", "TLT")
    xom_id = encode_position_key("bob", "XOM")

    async def _handle_close(route, request):
        body = await request.json()
        assert body.get("target_quantity") == 0
        payload = {
            "order": {
                "order_id": "close-1",
                "status": "filled",
                "broker": "binance",
                "venue": "binance.spot",
                "symbol": "AAPL",
                "side": "sell",
                "quantity": 12,
                "filled_quantity": 12,
                "avg_price": 178.4,
                "submitted_at": "2024-05-01T12:00:00Z",
            },
            "positions": {
                "items": [
                    {
                        "id": growth_id,
                        "name": "Growth",
                        "owner": "alice",
                        "total_value": 5 * 310.6,
                        "holdings": [
                            {
                                "id": msft_id,
                                "portfolio_id": growth_id,
                                "portfolio": "alice",
                                "account_id": "alice",
                                "symbol": "MSFT",
                                "quantity": 5,
                                "average_price": 298.1,
                                "current_price": 310.6,
                                "market_value": 5 * 310.6,
                            }
                        ],
                    },
                    {
                        "id": income_id,
                        "name": "Income",
                        "owner": "bob",
                        "total_value": 20 * 98.2 + 15 * 105.7,
                        "holdings": [
                            {
                                "id": tlt_id,
                                "portfolio_id": income_id,
                                "portfolio": "bob",
                                "account_id": "bob",
                                "symbol": "TLT",
                                "quantity": 20,
                                "average_price": 100.5,
                                "current_price": 98.2,
                                "market_value": 20 * 98.2,
                            },
                            {
                                "id": xom_id,
                                "portfolio_id": income_id,
                                "portfolio": "bob",
                                "account_id": "bob",
                                "symbol": "XOM",
                                "quantity": 15,
                                "average_price": 88.5,
                                "current_price": 105.7,
                                "market_value": 15 * 105.7,
                            },
                        ],
                    },
                ],
                "as_of": "2024-05-01T12:00:00Z",
            },
        }
        await route.fulfill(
            status=200,
            headers={"content-type": "application/json"},
            body=json.dumps(payload),
        )

    await page.route("**/positions/**/close", _handle_close)

    await page.goto(f"{dashboard_base_url}/dashboard", wait_until="networkidle")

    close_button = page.get_by_role("button", name="Fermer").first
    async with page.expect_response("**/positions/**/close"):
        await close_button.click()

    await expect(
        page.locator("td[data-label='Symbole']").filter(has_text="AAPL")
    ).to_have_count(0)

