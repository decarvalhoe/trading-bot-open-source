import React, { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import PortfolioChart from "./components/PortfolioChart.jsx";
import AlertManager from "./alerts/AlertManager.jsx";
import AlertHistory from "./alerts/AlertHistory.jsx";
import ReportsList from "./reports/ReportsList.jsx";
import { AIStrategyAssistant } from "./strategies/assistant/index.js";
import { StrategyDesigner, STRATEGY_PRESETS } from "./strategies/designer/index.js";
import { StrategyBacktestConsole } from "./strategies/backtest/index.js";

function loadBootstrapData() {
  const bootstrapNode = document.getElementById("dashboard-bootstrap");
  if (!bootstrapNode || !bootstrapNode.textContent) {
    return {};
  }
  try {
    return JSON.parse(bootstrapNode.textContent);
  } catch (error) {
    console.error("Impossible de parser la configuration du tableau de bord", error);
    return {};
  }
}

function PortfolioChartApp({ endpoint, currency }) {
  const [state, setState] = useState({ status: "loading", items: [], currency });

  useEffect(() => {
    let cancelled = false;

    async function loadHistory() {
      setState((prev) => ({ ...prev, status: "loading" }));
      try {
        const response = await fetch(endpoint, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (cancelled) {
          return;
        }
        const items = Array.isArray(payload.items) ? payload.items : [];
        setState({
          status: "ready",
          items,
          currency: payload.currency || currency,
        });
      } catch (error) {
        if (!cancelled) {
          console.error("Impossible de récupérer l'historique des portefeuilles", error);
          setState((prev) => ({ ...prev, status: "error", error }));
        }
      }
    }

    loadHistory();

    return () => {
      cancelled = true;
    };
  }, [endpoint, currency]);

  if (state.status === "loading") {
    return (
      <div className="chart-container__status" role="status">
        Chargement des données historiques…
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="chart-container__status" role="alert">
        Impossible de charger l'historique pour le moment.
      </div>
    );
  }

  return <PortfolioChart history={state.items} currency={state.currency || currency} />;
}

const bootstrap = loadBootstrapData();

const reportsContainer = document.getElementById("reports-center");
if (reportsContainer) {
  let initialReports = [];
  const rawReports = reportsContainer.dataset.reports || "[]";
  try {
    initialReports = JSON.parse(rawReports);
  } catch (error) {
    console.error("Impossible de parser la liste des rapports", error);
  }
  const sizeValue = Number.parseInt(reportsContainer.dataset.pageSize || "5", 10);
  const root = createRoot(reportsContainer);
  root.render(
    <StrictMode>
      <ReportsList reports={initialReports} pageSize={Number.isNaN(sizeValue) ? 5 : sizeValue} />
    </StrictMode>
  );
}

const chartContainer = document.getElementById("portfolio-chart");
if (chartContainer) {
  const endpoint = chartContainer.dataset.endpoint || "/portfolios/history";
  const currency = chartContainer.dataset.currency || "$";
  const root = createRoot(chartContainer);
  root.render(
    <StrictMode>
      <PortfolioChartApp endpoint={endpoint} currency={currency} />
    </StrictMode>
  );
}

const alertsContainer = document.getElementById("alerts-manager");
if (alertsContainer) {
  const dataset = alertsContainer.dataset || {};
  const endpoint = dataset.endpoint || "/alerts";
  const token = dataset.authToken || "";
  const initialAlerts =
    (bootstrap && bootstrap.context && Array.isArray(bootstrap.context.alerts)
      ? bootstrap.context.alerts
      : []) || [];
  const root = createRoot(alertsContainer);
  root.render(
    <StrictMode>
      <AlertManager initialAlerts={initialAlerts} endpoint={endpoint} authToken={token} />
    </StrictMode>
  );
}

const historyContainer = document.getElementById("alerts-history");
if (historyContainer) {
  const dataset = historyContainer.dataset || {};
  const endpoint = dataset.endpoint || "/alerts/history";
  const root = createRoot(historyContainer);
  root.render(
    <StrictMode>
      <AlertHistory endpoint={endpoint} />
    </StrictMode>
  );
}

const strategyDesignerRoot = document.getElementById("strategy-designer-root");
if (strategyDesignerRoot) {
  const dataset = strategyDesignerRoot.dataset || {};
  const saveEndpoint = dataset.saveEndpoint || "/strategies/save";
  const defaultName = dataset.defaultName || "Nouvelle stratégie";
  const defaultFormat = dataset.defaultFormat || "yaml";
  let initialFormat = defaultFormat;
  if (initialFormat !== "python") {
    initialFormat = "yaml";
  }
  let presetCatalog = STRATEGY_PRESETS;
  if (dataset.presets) {
    try {
      const parsed = JSON.parse(dataset.presets);
      if (Array.isArray(parsed) && parsed.length) {
        presetCatalog = parsed;
      }
    } catch (error) {
      console.error("Impossible de parser les modèles de stratégies", error);
    }
  }
  const root = createRoot(strategyDesignerRoot);
  root.render(
    <StrictMode>
      <StrategyDesigner
        saveEndpoint={saveEndpoint}
        defaultName={defaultName}
        defaultFormat={initialFormat}
        presets={presetCatalog}
      />
    </StrictMode>
  );
}

const assistantRoot = document.getElementById("ai-strategy-assistant-root");
if (assistantRoot) {
  const dataset = assistantRoot.dataset || {};
  const generateEndpoint = dataset.generateEndpoint || "/strategies/generate";
  const importEndpoint = dataset.importEndpoint || "/strategies/import";
  const root = createRoot(assistantRoot);
  root.render(
    <StrictMode>
      <AIStrategyAssistant
        generateEndpoint={generateEndpoint}
        importEndpoint={importEndpoint}
      />
    </StrictMode>
  );
}

const backtestRoot = document.getElementById("strategy-backtest-root");
if (backtestRoot) {
  const dataset = backtestRoot.dataset || {};
  const historyPageSize = Number.parseInt(dataset.historyPageSize || "5", 10);
  const root = createRoot(backtestRoot);
  root.render(
    <StrictMode>
      <StrategyBacktestConsole
        strategiesEndpoint={dataset.strategiesEndpoint || "/api/strategies"}
        runEndpointTemplate={dataset.runEndpointTemplate || "/api/strategies/__id__/backtest"}
        uiEndpointTemplate={dataset.uiEndpointTemplate || "/api/strategies/__id__/backtest/ui"}
        historyEndpointTemplate={
          dataset.historyEndpointTemplate || "/api/strategies/__id__/backtests"
        }
        defaultStrategyId={dataset.defaultStrategyId || ""}
        defaultSymbol={dataset.defaultSymbol || "BTCUSDT"}
        historyPageSize={Number.isNaN(historyPageSize) ? 5 : historyPageSize}
      />
    </StrictMode>
  );
}

export default PortfolioChartApp;
