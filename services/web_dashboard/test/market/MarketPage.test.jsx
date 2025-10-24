import { act } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18next from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MarketPage from "../../src/pages/MarketPage.jsx";
import apiClient from "../../src/lib/api.js";

const subscribers = [];

function normaliseNumberFromText(text) {
  if (!text) {
    return Number.NaN;
  }
  const trimmed = text.trim();
  if (!trimmed) {
    return Number.NaN;
  }
  const hasComma = trimmed.includes(",");
  const hasDot = trimmed.includes(".");
  let normalised = trimmed;
  if (hasComma && hasDot) {
    normalised = normalised.replace(/,/g, "");
  } else if (hasComma && !hasDot) {
    normalised = normalised.replace(/,/g, ".");
  }
  normalised = normalised.replace(/[\s\u00A0]+/g, "");
  normalised = normalised.replace(/[^\d+\-.]/g, "");
  return Number(normalised);
}

vi.mock("../../src/components/TradingViewPanel.jsx", () => ({
  __esModule: true,
  default: ({ symbol }) => <div data-testid="tradingview-panel">Chart {symbol}</div>,
}));

vi.mock("../../src/bootstrap", () => ({
  bootstrap: {
    config: {
      market: {
        watchlist: ["BTCUSDT", "ETHUSDT"],
        defaultSymbol: "BTCUSDT",
        orderBookDepth: 3,
      },
      trading: {},
    },
  },
}));

vi.mock("../../src/hooks/useWebSocket.js", () => ({
  __esModule: true,
  default: vi.fn(() => ({
    status: "open",
    error: null,
    attempt: 0,
    isConnected: false,
    subscribe: (_types, handler) => {
      subscribers.push(handler);
      return () => {
        const index = subscribers.indexOf(handler);
        if (index >= 0) {
          subscribers.splice(index, 1);
        }
      };
    },
    publish: vi.fn(),
    reconnect: vi.fn(),
    disconnect: vi.fn(),
    client: null,
  })),
}));

async function createTestI18n(language = "fr") {
  const instance = i18next.createInstance();
  await instance.use(initReactI18next).init({
    lng: language,
    fallbackLng: "fr",
    resources: {
      fr: { translation: {} },
      en: { translation: {} },
    },
    interpolation: { escapeValue: false },
  });
  return instance;
}

describe("MarketPage", () => {
  let priceSpy;
  let orderBookSpy;

  beforeEach(() => {
    priceSpy = vi.spyOn(apiClient.marketData, "price");
    orderBookSpy = vi.spyOn(apiClient.marketData, "orderBook");
  });

  afterEach(() => {
    priceSpy.mockRestore();
    orderBookSpy.mockRestore();
    subscribers.splice(0, subscribers.length);
    vi.clearAllMocks();
  });

  it("renders live price and order book data", async () => {
    priceSpy.mockResolvedValue({
      symbol: "BTCUSDT",
      price: 12345.67,
      currency: "USD",
      change_percent: 1.23,
      last_update: "2024-05-01T10:00:00Z",
    });
    orderBookSpy.mockResolvedValue({
      symbol: "BTCUSDT",
      bids: [
        { price: 12345.5, size: 0.5 },
        { price: 12345.0, size: 0.4 },
      ],
      asks: [
        { price: 12346.0, size: 0.3 },
        { price: 12346.5, size: 0.25 },
      ],
      last_update: "2024-05-01T10:00:00Z",
    });

    const i18n = await createTestI18n();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    await act(async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <I18nextProvider i18n={i18n}>
            <MarketPage />
          </I18nextProvider>
        </QueryClientProvider>
      );
      await Promise.resolve();
    });

    expect(priceSpy).toHaveBeenCalledWith("BTCUSDT", { endpoint: "/market/BTCUSDT/price" });
    expect(orderBookSpy).toHaveBeenCalledWith("BTCUSDT", {
      endpoint: "/market/BTCUSDT/order-book",
      depth: 3,
    });

    const priceValue = await screen.findByTestId("market-price-value");
    const priceAmount = within(priceValue).getByTestId("market-price-amount");
    expect(normaliseNumberFromText(priceAmount.textContent)).toBeCloseTo(12345.67, 2);

    const orderBook = await screen.findByTestId("market-order-book");
    const cells = within(orderBook).getAllByRole("cell");
    expect(normaliseNumberFromText(cells[0].textContent)).toBeCloseTo(12345.5, 2);
    expect(normaliseNumberFromText(cells[1].textContent)).toBeCloseTo(0.5, 3);
    expect(normaliseNumberFromText(cells[2].textContent)).toBeCloseTo(12346.0, 2);

    queryClient.clear();
  });

  it("updates price and order book from streaming events", async () => {
    priceSpy.mockResolvedValue({
      symbol: "BTCUSDT",
      price: 12000.0,
      currency: "USD",
      change_percent: 0.5,
      last_update: "2024-05-01T10:00:00Z",
    });
    orderBookSpy.mockResolvedValue({
      symbol: "BTCUSDT",
      bids: [
        { price: 11999.5, size: 0.2 },
      ],
      asks: [
        { price: 12000.5, size: 0.3 },
      ],
      last_update: "2024-05-01T10:00:00Z",
    });

    const i18n = await createTestI18n();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    await act(async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <I18nextProvider i18n={i18n}>
            <MarketPage />
          </I18nextProvider>
        </QueryClientProvider>
      );
      await Promise.resolve();
    });

    await screen.findByTestId("market-price-value");
    expect(subscribers.length).toBeGreaterThan(0);
    const handler = subscribers[subscribers.length - 1];

    await act(async () => {
      handler({
        symbol: "BTCUSDT",
        price: 12500.55,
        change_percent: 1.2,
      });
      await Promise.resolve();
    });

    await waitFor(() => {
      const priceAmount = within(screen.getByTestId("market-price-value")).getByTestId("market-price-amount");
      expect(normaliseNumberFromText(priceAmount.textContent)).toBeCloseTo(12500.55, 2);
    });

    await act(async () => {
      handler({
        symbol: "BTCUSDT",
        bids: [
          { price: 12499.0, size: 0.9 },
        ],
        asks: [
          { price: 12501.0, size: 0.7 },
        ],
      });
      await Promise.resolve();
    });

    const orderBook = await screen.findByTestId("market-order-book");
    await waitFor(() => {
      const cells = within(orderBook).getAllByRole("cell");
      expect(normaliseNumberFromText(cells[0].textContent)).toBeCloseTo(12499.0, 2);
      expect(normaliseNumberFromText(cells[2].textContent)).toBeCloseTo(12501.0, 2);
    });

    queryClient.clear();
  });
});
