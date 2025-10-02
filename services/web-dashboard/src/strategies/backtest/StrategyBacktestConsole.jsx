import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import TradingViewPanel from "../../components/TradingViewPanel.jsx";

const PERIOD_OPTIONS = [
  { value: "15m", label: "15 minutes" },
  { value: "1h", label: "1 heure" },
  { value: "4h", label: "4 heures" },
  { value: "1d", label: "1 jour" },
];

function normaliseSummary(summary) {
  if (!summary || typeof summary !== "object") {
    return null;
  }
  const equityCurve = Array.isArray(summary.equity_curve)
    ? summary.equity_curve
    : [];
  const pnl =
    typeof summary.pnl === "number"
      ? summary.pnl
      : typeof summary.profit_loss === "number"
      ? summary.profit_loss
      : 0;
  const drawdown =
    typeof summary.drawdown === "number"
      ? summary.drawdown
      : typeof summary.max_drawdown === "number"
      ? summary.max_drawdown
      : 0;
  const totalReturn =
    typeof summary.total_return === "number" ? summary.total_return : 0;
  const initialBalance =
    typeof summary.initial_balance === "number" ? summary.initial_balance : 0;

  return {
    ...summary,
    equity_curve: equityCurve,
    pnl,
    drawdown,
    total_return: totalReturn,
    initial_balance: initialBalance,
  };
}

function formatCurrency(value, currency = "USD") {
  try {
    return new Intl.NumberFormat("fr-FR", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(value || 0);
  } catch (error) {
    return `${(value || 0).toFixed(2)} ${currency}`;
  }
}

function formatPercent(ratio) {
  const value = typeof ratio === "number" ? ratio * 100 : 0;
  return `${value.toFixed(2)} %`;
}

function buildEndpoint(template, strategyId) {
  if (!template || !strategyId) {
    return "";
  }
  return template.replace("__id__", encodeURIComponent(strategyId));
}

function StrategyBacktestConsole({
  strategiesEndpoint,
  runEndpointTemplate,
  uiEndpointTemplate,
  historyEndpointTemplate,
  defaultStrategyId = "",
  defaultSymbol = "BTCUSDT",
  historyPageSize = 5,
  tradingViewConfigEndpoint = "/config/tradingview",
  tradingViewUpdateEndpoint = "/config/tradingview",
}) {
  const [strategies, setStrategies] = useState([]);
  const [strategiesStatus, setStrategiesStatus] = useState("idle");
  const [selectedStrategy, setSelectedStrategy] = useState(defaultStrategyId);
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [timeframe, setTimeframe] = useState("1h");
  const [lookbackDays, setLookbackDays] = useState(30);
  const [initialBalance, setInitialBalance] = useState(10000);
  const [metrics, setMetrics] = useState(null);
  const [history, setHistory] = useState({ items: [], total: 0, page: 1 });
  const [historyStatus, setHistoryStatus] = useState("idle");
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const [error, setError] = useState(null);

  const selectedStrategyDetails = useMemo(
    () => strategies.find((item) => item.id === selectedStrategy) || null,
    [strategies, selectedStrategy]
  );

  const loadStrategies = useCallback(async () => {
    if (!strategiesEndpoint) {
      setStrategies([]);
      setStrategiesStatus("ready");
      return;
    }
    setStrategiesStatus("loading");
    try {
      const response = await fetch(strategiesEndpoint, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      const items = Array.isArray(payload.items)
        ? payload.items.filter((item) => item && item.id)
        : [];
      setStrategies(items);
      setStrategiesStatus("ready");
      setSelectedStrategy((current) => current || (items[0]?.id ?? ""));
    } catch (fetchError) {
      console.error("Impossible de charger les stratégies", fetchError);
      setStrategies([]);
      setStrategiesStatus("error");
      setError(fetchError);
    }
  }, [strategiesEndpoint]);

  useEffect(() => {
    loadStrategies();
  }, [loadStrategies]);

  const loadUiMetrics = useCallback(
    async (strategyId) => {
      if (!strategyId || !uiEndpointTemplate) {
        setMetrics(null);
        return;
      }
      const endpoint = buildEndpoint(uiEndpointTemplate, strategyId);
      try {
        const response = await fetch(endpoint, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        setMetrics(normaliseSummary(payload));
      } catch (loadError) {
        console.error("Impossible de charger les métriques du backtest", loadError);
      }
    },
    [uiEndpointTemplate]
  );

  const loadHistory = useCallback(
    async (strategyId, page = 1, append = false) => {
      if (!strategyId || !historyEndpointTemplate) {
        setHistory({ items: [], total: 0, page: 1 });
        return;
      }
      const endpoint = buildEndpoint(historyEndpointTemplate, strategyId);
      if (!endpoint) {
        return;
      }
      setHistoryStatus("loading");
      try {
        const url = new URL(endpoint, window.location.origin);
        url.searchParams.set("page", String(page));
        url.searchParams.set("page_size", String(historyPageSize));
        const response = await fetch(url.toString(), {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        const rawItems = Array.isArray(payload.items) ? payload.items : [];
        const mapped = rawItems
          .map((item) => normaliseSummary(item))
          .filter(Boolean);
        setHistory((previous) => ({
          page,
          total: typeof payload.total === "number" ? payload.total : mapped.length,
          items: append ? [...previous.items, ...mapped] : mapped,
        }));
        setHistoryStatus("ready");
      } catch (historyError) {
        console.error("Impossible de charger l'historique des backtests", historyError);
        setHistoryStatus("error");
      }
    },
    [historyEndpointTemplate, historyPageSize]
  );

  useEffect(() => {
    if (!selectedStrategy) {
      setMetrics(null);
      setHistory({ items: [], total: 0, page: 1 });
      return;
    }
    loadUiMetrics(selectedStrategy);
    loadHistory(selectedStrategy, 1, false);
  }, [selectedStrategy, loadUiMetrics, loadHistory]);

  const chartData = useMemo(() => {
    if (!metrics || !Array.isArray(metrics.equity_curve)) {
      return [];
    }
    return metrics.equity_curve.map((value, index) => ({
      index,
      equity: typeof value === "number" ? value : Number.parseFloat(value) || 0,
    }));
  }, [metrics]);

  const currency = useMemo(() => {
    if (metrics && metrics.metadata && metrics.metadata.currency) {
      return metrics.metadata.currency;
    }
    return "USD";
  }, [metrics]);

  const canRunBacktest = Boolean(selectedStrategy && symbol.trim());
  const canLoadMore = history.items.length < history.total;

  const handleSubmit = useCallback(
    async (event) => {
      event.preventDefault();
      if (!selectedStrategy) {
        setError(new Error("Aucune stratégie sélectionnée."));
        return;
      }
      const endpoint = buildEndpoint(runEndpointTemplate, selectedStrategy);
      if (!endpoint) {
        setError(new Error("Endpoint de backtest introuvable."));
        return;
      }
      setStatus("running");
      setMessage("");
      setError(null);
      const body = {
        symbol: symbol.trim(),
        timeframe,
        lookback_days: lookbackDays,
        initial_balance: initialBalance,
      };
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify(body),
        });
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          const messageDetail =
            detail && detail.message
              ? detail.message
              : `HTTP ${response.status}`;
          throw new Error(messageDetail);
        }
        const payload = await response.json();
        const normalised = normaliseSummary(payload);
        setMetrics(normalised);
        setStatus("success");
        setMessage("Backtest exécuté avec succès.");
        await loadUiMetrics(selectedStrategy);
        await loadHistory(selectedStrategy, 1, false);
      } catch (runError) {
        console.error("Échec de l'exécution du backtest", runError);
        setStatus("error");
        setError(runError);
      }
    },
    [
      selectedStrategy,
      runEndpointTemplate,
      symbol,
      timeframe,
      lookbackDays,
      initialBalance,
      loadUiMetrics,
      loadHistory,
    ]
  );

  const handleSyncedSymbolChange = useCallback(
    (nextSymbol) => {
      if (!nextSymbol) {
        return;
      }
      setSymbol(nextSymbol.toUpperCase());
    },
    []
  );

  const handleLoadMore = useCallback(() => {
    if (!selectedStrategy) {
      return;
    }
    loadHistory(selectedStrategy, history.page + 1, true);
  }, [selectedStrategy, history.page, loadHistory]);

  return (
    <div className="backtest-console">
      <form className="backtest-console__form" onSubmit={handleSubmit}>
        <div className="backtest-console__fields">
          <label className="designer-field">
            <span className="designer-field__label text text--muted">Stratégie</span>
            <select
              value={selectedStrategy}
              onChange={(event) => setSelectedStrategy(event.target.value)}
              disabled={strategiesStatus === "loading"}
            >
              {strategies.length === 0 && (
                <option value="" disabled>
                  {strategiesStatus === "loading"
                    ? "Chargement des stratégies…"
                    : "Aucune stratégie disponible"}
                </option>
              )}
              {strategies.map((strategy) => (
                <option key={strategy.id} value={strategy.id}>
                  {strategy.name || strategy.id}
                </option>
              ))}
            </select>
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">Actif</span>
            <input
              type="text"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value.toUpperCase())}
              placeholder="BTCUSDT"
            />
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">Période</span>
            <select
              value={timeframe}
              onChange={(event) => setTimeframe(event.target.value)}
            >
              {PERIOD_OPTIONS.map((period) => (
                <option key={period.value} value={period.value}>
                  {period.label}
                </option>
              ))}
            </select>
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">
              Fenêtre (jours)
            </span>
            <input
              type="number"
              min="1"
              max="180"
              value={lookbackDays}
              onChange={(event) =>
                setLookbackDays(Math.max(1, Number.parseInt(event.target.value, 10) || 1))
              }
            />
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">
              Capital initial
            </span>
            <input
              type="number"
              min="100"
              step="100"
              value={initialBalance}
              onChange={(event) =>
                setInitialBalance(Math.max(100, Number.parseFloat(event.target.value) || 100))
              }
            />
          </label>
        </div>
        <div className="backtest-console__actions">
          <button
            type="submit"
            className="button button--primary"
            disabled={!canRunBacktest || status === "running"}
          >
            {status === "running" ? "Backtest en cours…" : "Lancer le backtest"}
          </button>
        </div>
      </form>
      <section
        className="backtest-console__tradingview"
        aria-labelledby="backtest-tradingview-title"
      >
        <h3 id="backtest-tradingview-title" className="heading heading--md">
          Analyse graphique TradingView
        </h3>
        <TradingViewPanel
          configEndpoint={tradingViewConfigEndpoint}
          updateEndpoint={tradingViewUpdateEndpoint}
          selectedStrategy={selectedStrategyDetails}
          symbol={symbol}
          onSymbolChange={handleSyncedSymbolChange}
        />
      </section>

      {message && (
        <div className="backtest-console__message" role="status">
          {message}
        </div>
      )}
      {error && (
        <div className="backtest-console__error" role="alert">
          {error.message || "Une erreur est survenue lors du backtest."}
        </div>
      )}

      <section
        className="backtest-console__results"
        aria-labelledby="backtest-results-title"
      >
        <h3 id="backtest-results-title" className="heading heading--md">
          Résultat du dernier backtest
        </h3>
        {!metrics && (
          <p className="text text--muted">
            Lancez un backtest pour visualiser l'équity et les indicateurs de performance.
          </p>
        )}
        {metrics && (
          <>
            <ul className="backtest-console__metrics">
              <li>
                <strong>P&amp;L</strong>
                <span>{formatCurrency(metrics.pnl, currency)}</span>
              </li>
              <li>
                <strong>Rendement</strong>
                <span>{formatPercent(metrics.total_return)}</span>
              </li>
              <li>
                <strong>Max drawdown</strong>
                <span>{formatPercent(metrics.drawdown)}</span>
              </li>
            </ul>
            {chartData.length > 0 ? (
              <div className="backtest-console__chart" role="img" aria-label="Équity du backtest">
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="index" tickFormatter={(value) => `#${value}`} />
                    <YAxis tickFormatter={(value) => formatCurrency(value, currency)} />
                    <Tooltip
                      formatter={(value) => formatCurrency(value, currency)}
                      labelFormatter={(value) => `Point ${value}`}
                    />
                    <Line
                      type="monotone"
                      dataKey="equity"
                      stroke="#2563eb"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text text--muted">
                Les données d'équity ne sont pas disponibles pour ce backtest.
              </p>
            )}
          </>
        )}
      </section>

      <section
        className="backtest-console__history"
        aria-labelledby="backtest-history-title"
      >
        <h3 id="backtest-history-title" className="heading heading--md">
          Historique des backtests
        </h3>
        {historyStatus === "error" && (
          <p className="text text--muted" role="alert">
            Impossible de charger l'historique pour le moment.
          </p>
        )}
        {history.items.length === 0 && historyStatus !== "error" ? (
          <p className="text text--muted">
            Aucun backtest enregistré pour cette stratégie.
          </p>
        ) : (
          <ul className="backtest-console__history-list" aria-live="polite">
            {history.items.map((item, index) => (
              <li key={`${item.ran_at || index}-${index}`}>
                <div>
                  <strong>
                    {item.metadata && item.metadata.symbol
                      ? `${item.metadata.symbol}`
                      : "Backtest"}
                  </strong>
                  <span className="text text--muted">
                    {item.ran_at ? ` — ${new Date(item.ran_at).toLocaleString()}` : ""}
                  </span>
                </div>
                <div className="backtest-console__history-metrics">
                  <span>{formatCurrency(item.pnl, currency)}</span>
                  <span>{formatPercent(item.total_return)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
        {canLoadMore && (
          <div className="backtest-console__load-more">
            <button
              type="button"
              className="button button--secondary"
              onClick={handleLoadMore}
              disabled={historyStatus === "loading"}
            >
              {historyStatus === "loading" ? "Chargement…" : "Charger plus"}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

export default StrategyBacktestConsole;
