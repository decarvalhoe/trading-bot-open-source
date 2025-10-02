from __future__ import annotations

import json
import re

import pytest
from playwright.async_api import Page, expect


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


async def test_portfolio_chart_zoom_and_exports(page: Page, dashboard_base_url: str, mock_streaming):
    await page.goto(f"{dashboard_base_url}/dashboard", wait_until="networkidle")

    zoom_status = page.get_by_role("status", name=re.compile("Affichage complet", re.I))
    await expect(zoom_status).to_be_visible()

    start_slider = page.get_by_label("Début du zoom")
    await start_slider.evaluate(
        "slider => { slider.value = '1'; slider.dispatchEvent(new Event('input', { bubbles: true })); slider.dispatchEvent(new Event('change', { bubbles: true })); }"
    )

    await expect(page.get_by_role("status", name=re.compile("Zoom", re.I))).to_be_visible()

    async with page.expect_download() as csv_download_info:
        await page.get_by_role("button", name="Exporter CSV").click()
    csv_download = await csv_download_info.value
    assert csv_download.suggested_filename.endswith(".csv")
    csv_bytes = await csv_download.content()
    assert b"Date" in csv_bytes

    async with page.expect_download() as png_download_info:
        await page.get_by_role("button", name=re.compile("Exporter PNG", re.I)).click()
    png_download = await png_download_info.value
    assert png_download.suggested_filename.endswith(".png")
