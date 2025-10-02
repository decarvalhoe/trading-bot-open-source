import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { TradingViewPanel } from "../src/components/TradingViewPanel.jsx";

const BASE_CONFIG = {
  api_key: "demo-key",
  library_url: "https://cdn.example.com/charting_library.js",
  default_symbol: "BINANCE:ETHUSDT",
  symbol_map: { trend: "BINANCE:BTCUSDT" },
  overlays: [
    {
      id: "sma-20",
      title: "SMA 20",
      type: "indicator",
      settings: { inputs: [20], overlay: true, options: { color: "#2563eb" } },
    },
  ],
};

function setupFetchMock() {
  const mock = vi.fn(async (url, options = {}) => {
    if (!options.method || options.method === "GET") {
      return {
        ok: true,
        async json() {
          return BASE_CONFIG;
        },
      };
    }
    if (options.method === "PUT") {
      const body = JSON.parse(options.body || "{}");
      return {
        ok: true,
        async json() {
          return { ...BASE_CONFIG, overlays: body.overlays || [] };
        },
      };
    }
    return {
      ok: false,
      async json() {
        return {};
      },
    };
  });
  global.fetch = mock;
  return mock;
}

function setupTradingViewMock() {
  const chart = {
    createStudy: vi.fn(),
    createShape: vi.fn(),
  };
  const widget = {
    onChartReady(callback) {
      callback();
    },
    chart() {
      return chart;
    },
    setSymbol: vi.fn((symbol, cb) => {
      if (cb) {
        cb();
      }
    }),
    remove: vi.fn(),
  };
  global.TradingView = {
    widget: vi.fn(() => widget),
  };
  return { widget, chart };
}

afterEach(() => {
  vi.restoreAllMocks();
  delete global.fetch;
  delete global.TradingView;
});

test("initialise TradingView avec le symbole mappé et les overlays", async () => {
  const fetchMock = setupFetchMock();
  const { chart, widget } = setupTradingViewMock();
  const onSymbolChange = vi.fn();

  render(
    <TradingViewPanel
      selectedStrategy={{ id: "alpha", strategy_type: "trend" }}
      symbol=""
      onSymbolChange={onSymbolChange}
    />
  );

  await waitFor(() => {
    expect(global.TradingView.widget).toHaveBeenCalled();
  });

  expect(widget.setSymbol).toHaveBeenCalledWith("BINANCE:BTCUSDT", expect.any(Function));
  expect(onSymbolChange).toHaveBeenCalledWith("BINANCE:BTCUSDT");
  expect(chart.createStudy).toHaveBeenCalledWith("SMA 20", true, [20], { color: "#2563eb" });
  expect(fetchMock).toHaveBeenCalledWith(
    "/config/tradingview",
    expect.objectContaining({ headers: { Accept: "application/json" } })
  );
});

test("ajoute un overlay et persiste la configuration", async () => {
  const fetchMock = setupFetchMock();
  const { chart } = setupTradingViewMock();
  const user = userEvent.setup();

  render(
    <TradingViewPanel
      selectedStrategy={{ id: "beta", strategy_type: "trend" }}
      symbol=""
      onSymbolChange={() => {}}
    />
  );

  const input = await screen.findByPlaceholderText("RSI");
  await user.clear(input);
  await user.type(input, "RSI 9");
  const button = screen.getByRole("button", { name: /ajouter l'overlay/i });
  await user.click(button);

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/config/tradingview",
      expect.objectContaining({ method: "PUT" })
    );
  });

  const lastCall = fetchMock.mock.calls.find((call) => call[1] && call[1].method === "PUT");
  expect(lastCall).toBeTruthy();
  const body = JSON.parse(lastCall[1].body);
  expect(body.overlays[body.overlays.length - 1].title).toBe("RSI 9");

  await waitFor(() => {
    expect(screen.getByText(/Overlay enregistré/i)).toBeInTheDocument();
  });

  expect(chart.createStudy).toHaveBeenCalled();
});
