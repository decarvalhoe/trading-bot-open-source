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

const TIMEFRAME_OPTIONS = [
  { value: "15m", label: "15 minutes" },
  { value: "1h", label: "1 heure" },
  { value: "4h", label: "4 heures" },
  { value: "1d", label: "1 jour" },
];

function buildEndpoint(template, identifier) {
  if (!template || !identifier) {
    return "";
  }
  return template.replace("__id__", encodeURIComponent(identifier));
}

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
    typeof summary.initial_balance === "number"
      ? summary.initial_balance
      : 0;
  const identifier =
    typeof summary.id === "number" || typeof summary.id === "string"
      ? summary.id
      : null;
  const artifacts = Array.isArray(summary.artifacts)
    ? summary.artifacts
    : [];
  return {
    ...summary,
    equity_curve: equityCurve,
    pnl,
    drawdown,
    total_return: totalReturn,
    initial_balance: initialBalance,
    id: identifier,
    artifacts,
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

function buildParameters(fastLength, slowLength, positionSize) {
  const size = Math.max(0.001, Number.parseFloat(positionSize) || 1);
  return {
    definition: {
      rules: [
        {
          when: {
            all: [
              { field: "trend_up", operator: "eq", value: true },
              { field: "above_fast_ma", operator: "eq", value: true },
            ],
          },
          signal: { action: "buy", size },
        },
        {
          when: {
            any: [
              { field: "trend_up", operator: "eq", value: false },
              { field: "below_fast_ma", operator: "eq", value: true },
            ],
          },
          signal: { action: "sell", size },
        },
      ],
    },
    fast_length: fastLength,
    slow_length: slowLength,
    position_size: size,
  };
}

function buildMetadata(formValues) {
  return {
    symbol: formValues.symbol,
    timeframe: formValues.timeframe,
    lookback_days: formValues.lookbackDays,
    fast_length: formValues.fastLength,
    slow_length: formValues.slowLength,
    position_size: formValues.positionSize,
    strategy_name: formValues.name,
  };
}

function parseArtifacts(artifacts) {
  if (!Array.isArray(artifacts)) {
    return [];
  }
  return artifacts
    .map((artifact) => {
      if (!artifact || typeof artifact !== "object") {
        return null;
      }
      const type = artifact.type || "artifact";
      const path = artifact.path || "";
      const contentType = artifact.content_type || "text/plain";
      const content = artifact.content ?? "";
      return { type, path, contentType, content };
    })
    .filter(Boolean);
}

function OneClickStrategyBuilder({
  saveEndpoint,
  runEndpoint,
  historyEndpointTemplate,
  backtestDetailTemplate,
  defaults,
}) {
  const [formValues, setFormValues] = useState(() => ({
    name: (defaults && defaults.name) || "Tendance BTCUSDT",
    symbol: (defaults && defaults.symbol) || "BTCUSDT",
    timeframe: (defaults && defaults.timeframe) || "1h",
    lookbackDays: (defaults && defaults.lookback_days) || 60,
    initialBalance: (defaults && defaults.initial_balance) || 10000,
    fastLength: (defaults && defaults.fast_length) || 5,
    slowLength: (defaults && defaults.slow_length) || 20,
    positionSize: (defaults && defaults.position_size) || 1,
  }));
  const [status, setStatus] = useState({ phase: "idle", message: "" });
  const [error, setError] = useState(null);
  const [strategyId, setStrategyId] = useState("");
  const [lastRun, setLastRun] = useState(null);
  const [artifacts, setArtifacts] = useState([]);
  const [history, setHistory] = useState({ items: [], total: 0, page: 1 });
  const [historyStatus, setHistoryStatus] = useState("idle");

  const canSubmit = Boolean(saveEndpoint && runEndpoint);

  const chartData = useMemo(() => {
    if (!lastRun || !Array.isArray(lastRun.equity_curve)) {
      return [];
    }
    return lastRun.equity_curve.map((value, index) => ({
      index,
      equity: typeof value === "number" ? value : Number.parseFloat(value) || 0,
    }));
  }, [lastRun]);

  const currency = useMemo(() => {
    if (lastRun && lastRun.metadata && lastRun.metadata.currency) {
      return lastRun.metadata.currency;
    }
    return "USD";
  }, [lastRun]);

  const loadHistory = useCallback(
    async (id) => {
      if (!id || !historyEndpointTemplate) {
        setHistory({ items: [], total: 0, page: 1 });
        return;
      }
      const endpoint = buildEndpoint(historyEndpointTemplate, id);
      if (!endpoint) {
        return;
      }
      setHistoryStatus("loading");
      try {
        const response = await fetch(endpoint, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        const items = Array.isArray(payload.items)
          ? payload.items.map((item) => normaliseSummary(item)).filter(Boolean)
          : [];
        setHistory({
          items,
          total: typeof payload.total === "number" ? payload.total : items.length,
          page: 1,
        });
        setHistoryStatus("ready");
      } catch (loadError) {
        console.error("Impossible de charger l'historique des backtests", loadError);
        setHistoryStatus("error");
      }
    },
    [historyEndpointTemplate]
  );

  const handleSelectBacktest = useCallback(
    async (backtestId) => {
      if (!backtestId || !backtestDetailTemplate) {
        return;
      }
      const endpoint = buildEndpoint(backtestDetailTemplate, backtestId);
      if (!endpoint) {
        return;
      }
      try {
        const response = await fetch(endpoint, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        const normalised = normaliseSummary(payload);
        if (normalised) {
          setLastRun(normalised);
          setArtifacts(parseArtifacts(normalised.artifacts));
        }
      } catch (loadError) {
        console.error("Impossible de récupérer le backtest", loadError);
        setError(loadError);
      }
    },
    [backtestDetailTemplate]
  );

  const handleSubmit = useCallback(
    async (event) => {
      event.preventDefault();
      if (!canSubmit) {
        setError(new Error("Configuration incomplète."));
        return;
      }
      setStatus({ phase: "saving", message: "Enregistrement de la stratégie…" });
      setError(null);
      try {
        const symbol = formValues.symbol.trim().toUpperCase();
        const name = formValues.name.trim() || "Stratégie tendance";
        const fastLength = Math.max(1, Number.parseInt(formValues.fastLength, 10) || 5);
        const slowLength = Math.max(
          fastLength + 1,
          Number.parseInt(formValues.slowLength, 10) || fastLength + 5
        );
        const positionSize = Math.max(
          0.001,
          Number.parseFloat(formValues.positionSize) || 1
        );
        const parameters = buildParameters(fastLength, slowLength, positionSize);
        const metadata = buildMetadata({
          ...formValues,
          symbol,
          name,
          fastLength,
          slowLength,
          positionSize,
        });
        const saveResponse = await fetch(saveEndpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({
            name,
            strategy_type: "declarative",
            parameters: {
              definition: parameters.definition,
              fast_length: parameters.fast_length,
              slow_length: parameters.slow_length,
              position_size: parameters.position_size,
            },
            metadata,
            enabled: false,
            tags: ["one-click"],
          }),
        });
        if (!saveResponse.ok) {
          const detail = await saveResponse.json().catch(() => null);
          const message = detail && detail.detail ? detail.detail : `HTTP ${saveResponse.status}`;
          throw new Error(
            Array.isArray(message)
              ? message.map((item) => item.msg || item.detail).join("; ")
              : typeof message === "string"
              ? message
              : "Échec de l'enregistrement de la stratégie."
          );
        }
        const savedPayload = await saveResponse.json().catch(() => ({}));
        const createdId = savedPayload.id || savedPayload.strategy_id || savedPayload.strategy?.id;
        if (!createdId) {
          throw new Error("Identifiant de stratégie introuvable dans la réponse.");
        }
        setStrategyId(String(createdId));
        setStatus({ phase: "running", message: "Backtest en cours…" });
        const runResponse = await fetch(runEndpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({
            strategy_id: createdId,
            symbol,
            timeframe: formValues.timeframe,
            lookback_days: formValues.lookbackDays,
            initial_balance: formValues.initialBalance,
            metadata,
          }),
        });
        if (!runResponse.ok) {
          const detail = await runResponse.json().catch(() => null);
          const message = detail && detail.detail ? detail.detail : `HTTP ${runResponse.status}`;
          throw new Error(
            typeof message === "string"
              ? message
              : "Échec de l'exécution du backtest."
          );
        }
        const runPayload = await runResponse.json();
        const normalised = normaliseSummary(runPayload);
        if (normalised) {
          setLastRun(normalised);
          setArtifacts(parseArtifacts(normalised.artifacts));
        }
        setStatus({ phase: "success", message: "Backtest exécuté avec succès." });
        await loadHistory(String(createdId));
      } catch (submitError) {
        console.error("Impossible de lancer le backtest one-click", submitError);
        setError(submitError);
        setStatus({ phase: "error", message: "Une erreur est survenue." });
      }
    },
    [canSubmit, formValues, loadHistory, runEndpoint, saveEndpoint]
  );

  useEffect(() => {
    if (strategyId) {
      loadHistory(strategyId);
    }
  }, [strategyId, loadHistory]);

  return (
    <div className="backtest-console">
      <form className="backtest-console__form" onSubmit={handleSubmit}>
        <div className="designer-field-grid">
          <label className="designer-field">
            <span className="designer-field__label text text--muted">Nom</span>
            <input
              type="text"
              value={formValues.name}
              onChange={(event) =>
                setFormValues((prev) => ({ ...prev, name: event.target.value }))
              }
              placeholder="Stratégie tendance"
            />
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">Actif</span>
            <input
              type="text"
              value={formValues.symbol}
              onChange={(event) =>
                setFormValues((prev) => ({
                  ...prev,
                  symbol: event.target.value.toUpperCase(),
                }))
              }
              placeholder="BTCUSDT"
            />
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">Période</span>
            <select
              value={formValues.timeframe}
              onChange={(event) =>
                setFormValues((prev) => ({ ...prev, timeframe: event.target.value }))
              }
            >
              {TIMEFRAME_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">Fenêtre (jours)</span>
            <input
              type="number"
              min="1"
              max="180"
              value={formValues.lookbackDays}
              onChange={(event) =>
                setFormValues((prev) => ({
                  ...prev,
                  lookbackDays: Math.max(
                    1,
                    Number.parseInt(event.target.value, 10) || prev.lookbackDays
                  ),
                }))
              }
            />
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">Capital initial</span>
            <input
              type="number"
              min="100"
              step="100"
              value={formValues.initialBalance}
              onChange={(event) =>
                setFormValues((prev) => ({
                  ...prev,
                  initialBalance:
                    Number.parseFloat(event.target.value) || prev.initialBalance,
                }))
              }
            />
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">MA courte</span>
            <input
              type="number"
              min="1"
              value={formValues.fastLength}
              onChange={(event) =>
                setFormValues((prev) => ({
                  ...prev,
                  fastLength: Math.max(
                    1,
                    Number.parseInt(event.target.value, 10) || prev.fastLength
                  ),
                }))
              }
            />
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">MA longue</span>
            <input
              type="number"
              min={Number(formValues.fastLength) + 1}
              value={formValues.slowLength}
              onChange={(event) =>
                setFormValues((prev) => ({
                  ...prev,
                  slowLength: Math.max(
                    Number(prev.fastLength) + 1,
                    Number.parseInt(event.target.value, 10) || prev.slowLength
                  ),
                }))
              }
            />
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">Taille de position</span>
            <input
              type="number"
              min="0.001"
              step="0.001"
              value={formValues.positionSize}
              onChange={(event) =>
                setFormValues((prev) => ({
                  ...prev,
                  positionSize:
                    Number.parseFloat(event.target.value) || prev.positionSize,
                }))
              }
            />
          </label>
        </div>
        <div className="backtest-console__actions">
          <button
            type="submit"
            className="button button--primary"
            disabled={status.phase === "saving" || status.phase === "running" || !canSubmit}
          >
            {status.phase === "saving"
              ? "Enregistrement…"
              : status.phase === "running"
              ? "Backtest en cours…"
              : "Enregistrer et backtester"}
          </button>
        </div>
      </form>

      {status.message && (
        <div className="backtest-console__message" role="status">
          {status.message}
        </div>
      )}
      {error && (
        <div className="backtest-console__error" role="alert">
          {error.message || "Une erreur est survenue lors du backtest."}
        </div>
      )}

      <section className="backtest-console__results" aria-labelledby="one-click-results">
        <h3 id="one-click-results" className="heading heading--md">
          Résultat du dernier backtest
        </h3>
        {!lastRun && (
          <p className="text text--muted">
            Lancez un backtest pour visualiser l'équity et les performances.
          </p>
        )}
        {lastRun && (
          <>
            <ul className="backtest-console__metrics">
              <li>
                <strong>P&amp;L</strong>
                <span>{formatCurrency(lastRun.pnl, currency)}</span>
              </li>
              <li>
                <strong>Rendement</strong>
                <span>{formatPercent(lastRun.total_return)}</span>
              </li>
              <li>
                <strong>Max drawdown</strong>
                <span>{formatPercent(lastRun.drawdown)}</span>
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
                      stroke="#38bdf8"
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
            <section
              className="backtest-console__artifacts"
              aria-labelledby="one-click-artifacts"
            >
              <h4 id="one-click-artifacts" className="heading heading--md">
                Artefacts
              </h4>
              {artifacts.length === 0 ? (
                <p className="text text--muted">
                  Aucun artefact disponible pour ce backtest.
                </p>
              ) : (
                <ul className="backtest-console__history-list">
                  {artifacts.map((artifact, index) => (
                    <li key={`${artifact.type}-${index}`}>
                      <div>
                        <strong>{artifact.type}</strong>
                        {artifact.path && (
                          <span className="text text--muted"> — {artifact.path}</span>
                        )}
                      </div>
                      <pre className="designer-preview">
                        {typeof artifact.content === "object"
                          ? JSON.stringify(artifact.content, null, 2)
                          : String(artifact.content || "")}
                      </pre>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </section>

      <section className="backtest-console__history" aria-labelledby="one-click-history">
        <h3 id="one-click-history" className="heading heading--md">
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
            {history.items.map((item) => (
              <li key={`${item.id || item.ran_at}`}> 
                <div>
                  <strong>
                    {item.metadata && item.metadata.symbol
                      ? item.metadata.symbol
                      : "Backtest"}
                  </strong>
                  <span className="text text--muted">
                    {item.ran_at ? ` — ${new Date(item.ran_at).toLocaleString()}` : ""}
                  </span>
                </div>
                <div className="backtest-console__history-metrics">
                  <span>{formatCurrency(item.pnl, currency)}</span>
                  <span>{formatPercent(item.total_return)}</span>
                  {item.id && (
                    <button
                      type="button"
                      className="button button--secondary"
                      onClick={() => handleSelectBacktest(item.id)}
                    >
                      Voir
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default OneClickStrategyBuilder;
