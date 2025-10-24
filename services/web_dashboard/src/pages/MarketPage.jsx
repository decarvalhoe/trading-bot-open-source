import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import TradingViewPanel from "../components/TradingViewPanel.jsx";
import { bootstrap } from "../bootstrap";
import useApi from "../hooks/useApi.js";
import useWebSocket from "../hooks/useWebSocket.js";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card.jsx";

const DEFAULT_WATCHLIST = ["BTCUSDT", "ETHUSDT", "EURUSD", "SPX500USD"];
const DEFAULT_PRICE_TEMPLATE = "/market/{symbol}/price";
const DEFAULT_ORDER_BOOK_TEMPLATE = "/market/{symbol}/order-book";

function normaliseWatchlist(list) {
  if (!Array.isArray(list)) {
    return DEFAULT_WATCHLIST;
  }
  const cleaned = list
    .filter((item) => typeof item === "string" && item.trim())
    .map((item) => item.trim().toUpperCase());
  const unique = Array.from(new Set(cleaned));
  return unique.length ? unique : DEFAULT_WATCHLIST;
}

function resolveEndpoint(template, symbol) {
  if (!template) {
    return "";
  }
  if (!symbol) {
    return template.includes("{symbol}") ? template : template.replace(/\/$/, "");
  }
  const cleaned = template.replace(/\/{2,}/g, "/");
  if (cleaned.includes("{symbol}")) {
    return cleaned.replaceAll("{symbol}", encodeURIComponent(symbol));
  }
  const trimmed = cleaned.endsWith("/") ? cleaned.slice(0, -1) : cleaned;
  return `${trimmed}/${encodeURIComponent(symbol)}`;
}

function extractPayload(event) {
  if (!event) {
    return null;
  }
  if (event.payload && typeof event.payload === "object") {
    return event.payload;
  }
  if (event.detail && typeof event.detail === "object") {
    return event.detail;
  }
  if (event.data && typeof event.data === "object") {
    return event.data;
  }
  return event;
}

function parseNumber(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}

function normalisePricePayload(payload, fallbackSymbol) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  let price =
    parseNumber(payload.price) ??
    parseNumber(payload.last_price) ??
    parseNumber(payload.lastPrice) ??
    parseNumber(payload.last) ??
    parseNumber(payload.close) ??
    parseNumber(payload.mid);

  if (price == null && payload.bid && payload.ask) {
    const bid = parseNumber(payload.bid.price ?? payload.bid);
    const ask = parseNumber(payload.ask.price ?? payload.ask);
    if (bid != null && ask != null) {
      price = (bid + ask) / 2;
    }
  }

  if (price == null && payload.quote && typeof payload.quote === "object") {
    price = parseNumber(payload.quote.price ?? payload.quote.mid);
  }

  if (price == null) {
    return null;
  }

  const change =
    parseNumber(payload.change) ??
    parseNumber(payload.change_24h) ??
    parseNumber(payload.change24h) ??
    parseNumber(payload.delta);
  const changePercent =
    parseNumber(payload.change_percent) ??
    parseNumber(payload.changePercent) ??
    parseNumber(payload.change_24h_percent) ??
    parseNumber(payload.changePercent24h) ??
    parseNumber(payload.percent);
  const currency =
    payload.currency ??
    payload.quote_currency ??
    payload.quoteCurrency ??
    payload.quote_asset ??
    payload.quoteAsset ??
    null;
  const lastUpdate =
    payload.last_update ??
    payload.lastUpdate ??
    payload.timestamp ??
    payload.updated_at ??
    payload.updatedAt ??
    null;
  const symbol =
    (payload.symbol || payload.ticker || payload.instrument || payload.asset || fallbackSymbol || "").toString().toUpperCase();

  return {
    price,
    change,
    change_percent: changePercent,
    currency,
    last_update: lastUpdate,
    symbol,
  };
}

function normaliseLevels(levels) {
  if (!Array.isArray(levels)) {
    return [];
  }
  return levels
    .map((level) => {
      if (!level) {
        return null;
      }
      if (Array.isArray(level)) {
        if (level.length < 2) {
          return null;
        }
        const price = parseNumber(level[0]);
        const size = parseNumber(level[1]);
        if (price == null || size == null) {
          return null;
        }
        return { price, size };
      }
      const price = parseNumber(level.price ?? level.rate ?? level.value);
      const size = parseNumber(level.size ?? level.quantity ?? level.qty ?? level.amount ?? level.volume);
      if (price == null || size == null) {
        return null;
      }
      return { price, size };
    })
    .filter(Boolean);
}

function normaliseOrderBookPayload(payload, fallbackSymbol) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const bids = normaliseLevels(payload.bids ?? payload.buy ?? payload.depth?.bids ?? payload.levels?.bids);
  const asks = normaliseLevels(payload.asks ?? payload.sell ?? payload.depth?.asks ?? payload.levels?.asks);
  if (!bids.length && !asks.length) {
    return null;
  }
  const symbol =
    (payload.symbol || payload.ticker || payload.instrument || fallbackSymbol || "").toString().toUpperCase();
  const lastUpdate =
    payload.last_update ?? payload.lastUpdate ?? payload.timestamp ?? payload.updated_at ?? payload.updatedAt ?? null;
  return {
    bids,
    asks,
    symbol,
    last_update: lastUpdate,
  };
}

function formatPrice(value, currency) {
  const numeric = parseNumber(value);
  if (numeric == null) {
    return null;
  }
  if (currency) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 8,
      }).format(numeric);
    } catch (error) {
      return `${numeric.toFixed(2)} ${currency}`;
    }
  }
  const minimumFractionDigits = numeric < 1 ? 4 : 2;
  return numeric.toLocaleString(undefined, {
    minimumFractionDigits,
    maximumFractionDigits: Math.max(minimumFractionDigits, 6),
  });
}

function formatSize(value) {
  const numeric = parseNumber(value);
  if (numeric == null) {
    return "-";
  }
  if (numeric === 0) {
    return "0";
  }
  const options =
    numeric >= 100
      ? { maximumFractionDigits: 2 }
      : numeric >= 1
      ? { minimumFractionDigits: 2, maximumFractionDigits: 4 }
      : { minimumFractionDigits: 4, maximumFractionDigits: 8 };
  return numeric.toLocaleString(undefined, options);
}

function formatChange(value, percent) {
  const numericValue = parseNumber(value);
  const numericPercent = parseNumber(percent);
  const parts = [];
  if (numericValue != null) {
    const prefix = numericValue > 0 ? "+" : numericValue < 0 ? "" : "";
    parts.push(`${prefix}${numericValue.toFixed(2)}`);
  }
  if (numericPercent != null) {
    const prefix = numericPercent > 0 ? "+" : numericPercent < 0 ? "" : "";
    parts.push(`${prefix}${numericPercent.toFixed(2)}%`);
  }
  return parts.join(" · ");
}

export default function MarketPage() {
  const { t } = useTranslation();
  const { marketData, useQuery, queryClient } = useApi();
  const { subscribe, isConnected } = useWebSocket();
  const marketConfig = bootstrap?.config?.market || {};
  const tradingConfig = bootstrap?.config?.trading || {};
  const defaultWatchlist =
    marketConfig.watchlist ||
    tradingConfig.watchlist ||
    DEFAULT_WATCHLIST;

  const watchlist = useMemo(() => normaliseWatchlist(defaultWatchlist), [defaultWatchlist]);

  const configEndpoint =
    marketConfig.tradingViewConfigEndpoint ||
    tradingConfig.tradingViewConfigEndpoint ||
    "/config/tradingview";
  const updateEndpoint =
    marketConfig.tradingViewUpdateEndpoint ||
    tradingConfig.tradingViewUpdateEndpoint ||
    "/config/tradingview";
  const initialSymbol =
    marketConfig.defaultSymbol ||
    tradingConfig.defaultSymbol ||
    watchlist[0] ||
    DEFAULT_WATCHLIST[0];
  const [symbol, setSymbol] = useState(initialSymbol);
  const [customSymbol, setCustomSymbol] = useState("");

  const symbolUpperCase = useMemo(
    () => (symbol ? symbol.toString().trim().toUpperCase() : ""),
    [symbol]
  );

  const priceEndpointTemplate =
    marketConfig.priceEndpointTemplate ||
    marketConfig.priceEndpoint ||
    DEFAULT_PRICE_TEMPLATE;
  const orderBookEndpointTemplate =
    marketConfig.orderBookEndpointTemplate ||
    marketConfig.orderBookEndpoint ||
    DEFAULT_ORDER_BOOK_TEMPLATE;
  const orderBookDepth = Math.max(Number(marketConfig.orderBookDepth) || 10, 1);

  const priceEndpoint = useMemo(
    () => resolveEndpoint(priceEndpointTemplate, symbolUpperCase),
    [priceEndpointTemplate, symbolUpperCase]
  );
  const orderBookEndpoint = useMemo(
    () => resolveEndpoint(orderBookEndpointTemplate, symbolUpperCase),
    [orderBookEndpointTemplate, symbolUpperCase]
  );

  const priceQueryKey = useMemo(() => ["market", "price", symbolUpperCase], [symbolUpperCase]);
  const orderBookQueryKey = useMemo(
    () => ["market", "order-book", symbolUpperCase, orderBookDepth],
    [symbolUpperCase, orderBookDepth]
  );

  const {
    data: priceData = {},
    isLoading: isPriceLoading,
    isError: isPriceError,
  } = useQuery({
    queryKey: priceQueryKey,
    enabled: Boolean(symbolUpperCase && priceEndpoint && marketData?.price),
    refetchInterval: isConnected ? false : 15000,
    refetchOnWindowFocus: !isConnected,
    refetchIntervalInBackground: !isConnected,
    queryFn: async () => {
      const payload = await marketData.price(symbolUpperCase, {
        endpoint: priceEndpoint,
      });
      const normalised = normalisePricePayload(payload, symbolUpperCase);
      if (normalised) {
        return { ...payload, ...normalised };
      }
      return payload || {};
    },
  });

  const {
    data: orderBookData = { bids: [], asks: [] },
    isLoading: isOrderBookLoading,
    isError: isOrderBookError,
  } = useQuery({
    queryKey: orderBookQueryKey,
    enabled: Boolean(symbolUpperCase && orderBookEndpoint && marketData?.orderBook),
    refetchInterval: isConnected ? false : 30000,
    refetchOnWindowFocus: !isConnected,
    refetchIntervalInBackground: !isConnected,
    initialData: () => ({ bids: [], asks: [] }),
    queryFn: async () => {
      const payload = await marketData.orderBook(symbolUpperCase, {
        endpoint: orderBookEndpoint,
        depth: orderBookDepth,
      });
      const normalised = normaliseOrderBookPayload(payload, symbolUpperCase);
      if (normalised) {
        return { bids: [], asks: [], ...payload, ...normalised };
      }
      if (payload && typeof payload === "object") {
        return { bids: [], asks: [], ...payload };
      }
      return { bids: [], asks: [] };
    },
  });

  useEffect(() => {
    if (!symbolUpperCase) {
      return undefined;
    }
    const unsubscribe = subscribe(
      [
        "market.price",
        `market.${symbolUpperCase}.price`,
        "market.quote",
        `market.${symbolUpperCase}.quote`,
        "orderbook.update",
        `orderbook.${symbolUpperCase}.update`,
      ],
      (event) => {
        const payload = extractPayload(event);
        if (!payload) {
          return;
        }
        const eventSymbol =
          (payload.symbol || payload.ticker || payload.instrument || payload.asset || symbolUpperCase)
            .toString()
            .toUpperCase();
        if (eventSymbol !== symbolUpperCase) {
          return;
        }
        const priceUpdate = normalisePricePayload(payload, symbolUpperCase);
        if (priceUpdate) {
          queryClient.setQueryData(priceQueryKey, (previous = {}) => ({
            ...previous,
            ...payload,
            ...priceUpdate,
          }));
        }
        const orderBookUpdate = normaliseOrderBookPayload(payload, symbolUpperCase);
        if (orderBookUpdate) {
          queryClient.setQueryData(orderBookQueryKey, (previous = { bids: [], asks: [] }) => ({
            ...previous,
            ...payload,
            ...orderBookUpdate,
          }));
        }
      }
    );
    return typeof unsubscribe === "function" ? unsubscribe : undefined;
  }, [subscribe, symbolUpperCase, queryClient, priceQueryKey, orderBookQueryKey]);

  const handleCustomSubmit = (event) => {
    event.preventDefault();
    if (!customSymbol.trim()) {
      return;
    }
    setSymbol(customSymbol.trim().toUpperCase());
    setCustomSymbol("");
  };

  const priceDisplay = formatPrice(priceData.price, priceData.currency);
  const changeLabel = formatChange(
    priceData.change ?? priceData.change_24h,
    priceData.change_percent ?? priceData.changePercent ?? priceData.change_24h_percent
  );
  const changeToneValue = parseNumber(
    priceData.change ?? priceData.change_24h ?? priceData.change_percent ?? priceData.changePercent
  );
  const changeTone = changeToneValue != null ? (changeToneValue >= 0 ? "positive" : "negative") : "neutral";

  const bids = Array.isArray(orderBookData?.bids) ? orderBookData.bids : [];
  const asks = Array.isArray(orderBookData?.asks) ? orderBookData.asks : [];
  const rowCount = Math.min(Math.max(bids.length, asks.length), orderBookDepth);
  const orderBookRows = useMemo(() => {
    if (!rowCount) {
      return [];
    }
    const rows = [];
    for (let index = 0; index < rowCount; index += 1) {
      rows.push({
        bid: bids[index] ?? null,
        ask: asks[index] ?? null,
      });
    }
    return rows;
  }, [rowCount, bids, asks]);

  return (
    <div className="market-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Surveillance du marché")}</h1>
        <p className="text text--muted">
          {t("Visualisez vos actifs clés, comparez les tendances et affinez vos décisions de trading en direct.")}
        </p>
      </header>

      <section className="market-controls" aria-labelledby="market-watchlist-title">
        <h2 id="market-watchlist-title" className="heading heading--lg">
          {t("Sélection rapide")}
        </h2>
        <div className="watchlist-controls">
          <label className="form-field">
            <span className="form-field__label">{t("Symboles favoris")}</span>
            <select value={symbol} onChange={(event) => setSymbol(event.target.value)}>
              {watchlist.map((entry) => (
                <option key={entry} value={entry}>
                  {entry}
                </option>
              ))}
            </select>
          </label>
          <form className="form-inline" onSubmit={handleCustomSubmit}>
            <label className="form-field">
              <span className="form-field__label">{t("Symbole personnalisé")}</span>
              <input
                type="text"
                value={customSymbol}
                onChange={(event) => setCustomSymbol(event.target.value)}
                placeholder={t("Exemple : AAPL, BTCUSDT")}
              />
            </label>
            <button type="submit" className="button">
              {t("Afficher")}
            </button>
          </form>
        </div>
      </section>

      <section className="market-chart" aria-labelledby="market-chart-title">
        <h2 id="market-chart-title" className="visually-hidden">
          {t("Graphique TradingView")}
        </h2>
        <TradingViewPanel
          symbol={symbolUpperCase || symbol}
          onSymbolChange={(next) => setSymbol(next)}
          configEndpoint={configEndpoint}
          updateEndpoint={updateEndpoint}
        />
      </section>

      <section className="market-intelligence" aria-labelledby="market-intelligence-title">
        <h2 id="market-intelligence-title" className="visually-hidden">
          {t("Indicateurs temps réel")}
        </h2>
        <div className="market-intelligence__grid">
          <Card aria-live="polite">
            <CardHeader>
              <CardTitle>{t("Prix en direct")}</CardTitle>
              <CardDescription>
                {symbolUpperCase ? t("Dernière mise à jour pour {{symbol}}", { symbol: symbolUpperCase }) : null}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isPriceLoading ? (
                <p className="text text--muted">{t("Chargement du prix actuel…")}</p>
              ) : isPriceError ? (
                <p className="text text--critical">{t("Impossible de charger le prix actuel.")}</p>
              ) : priceDisplay ? (
                <div className="market-price" data-testid="market-price-value">
                  <p
                    className={`heading heading--xl market-price__value market-price__value--${changeTone}`}
                    data-testid="market-price-amount"
                  >
                    {priceDisplay}
                  </p>
                  {changeLabel ? (
                    <p className="text market-price__change">{changeLabel}</p>
                  ) : null}
                  {priceData.last_update ? (
                    <p className="text text--muted market-price__timestamp">
                      {t("Mise à jour à {{time}}", {
                        time: new Date(priceData.last_update).toLocaleTimeString(),
                      })}
                    </p>
                  ) : null}
                </div>
              ) : (
                <p className="text text--muted">{t("Aucune donnée de prix disponible pour le moment.")}</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("Carnet d'ordres")}</CardTitle>
              <CardDescription>
                {t("Top {{depth}} niveaux", { depth: orderBookDepth })}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isOrderBookLoading ? (
                <p className="text text--muted">{t("Chargement du carnet d'ordres…")}</p>
              ) : isOrderBookError ? (
                <p className="text text--critical">{t("Impossible de charger le carnet d'ordres.")}</p>
              ) : orderBookRows.length ? (
                <div className="order-book" data-testid="market-order-book">
                  <table className="order-book__table">
                    <thead>
                      <tr>
                        <th scope="col">{t("Bid")}</th>
                        <th scope="col">{t("Quantité")}</th>
                        <th scope="col">{t("Ask")}</th>
                        <th scope="col">{t("Quantité")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orderBookRows.map((row, index) => (
                        <tr key={`order-book-row-${index}`}>
                          <td>{row.bid ? formatPrice(row.bid.price, priceData.currency) : "-"}</td>
                          <td>{row.bid ? formatSize(row.bid.size) : "-"}</td>
                          <td>{row.ask ? formatPrice(row.ask.price, priceData.currency) : "-"}</td>
                          <td>{row.ask ? formatSize(row.ask.size) : "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {orderBookData.last_update ? (
                    <p className="text text--muted order-book__timestamp">
                      {t("Dernière mise à jour à {{time}}", {
                        time: new Date(orderBookData.last_update).toLocaleTimeString(),
                      })}
                    </p>
                  ) : null}
                </div>
              ) : (
                <p className="text text--muted">{t("Aucune profondeur disponible pour ce symbole.")}</p>
              )}
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
