import React, { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import PortfolioChart from "./components/PortfolioChart.jsx";
import AlertManager from "./alerts/AlertManager.jsx";
import AlertHistory from "./alerts/AlertHistory.jsx";
import ReportsList from "./reports/ReportsList.jsx";
import { AIStrategyAssistant } from "./strategies/assistant/index.js";
import { StrategyDesigner, STRATEGY_PRESETS } from "./strategies/designer/index.js";
import { StrategyBacktestConsole } from "./strategies/backtest/index.js";
import { OneClickStrategyBuilder } from "./strategies/simple/index.js";
import MarketplaceApp from "./marketplace/MarketplaceApp.jsx";
import OnboardingApp from "./onboarding/OnboardingApp.jsx";
import { I18nextProvider, useTranslation } from "react-i18next";
import i18n from "./i18n/config.js";

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
  const { t } = useTranslation();
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
        {t("Chargement des données historiques…")}
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="chart-container__status" role="alert">
        {t("Impossible de charger l'historique pour le moment.")}
      </div>
    );
  }

  return <PortfolioChart history={state.items} currency={state.currency || currency} />;
}

const bootstrap = loadBootstrapData();

function renderWithI18n(root, element) {
  root.render(
    <StrictMode>
      <I18nextProvider i18n={i18n}>{element}</I18nextProvider>
    </StrictMode>
  );
}

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
  renderWithI18n(
    root,
    <ReportsList reports={initialReports} pageSize={Number.isNaN(sizeValue) ? 5 : sizeValue} />
  );
}

const chartContainer = document.getElementById("portfolio-chart");
if (chartContainer) {
  const endpoint = chartContainer.dataset.endpoint || "/portfolios/history";
  const currency = chartContainer.dataset.currency || "$";
  const root = createRoot(chartContainer);
  renderWithI18n(root, <PortfolioChartApp endpoint={endpoint} currency={currency} />);
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
  renderWithI18n(
    root,
    <AlertManager initialAlerts={initialAlerts} endpoint={endpoint} authToken={token} />
  );
}

const historyContainer = document.getElementById("alerts-history");
if (historyContainer) {
  const dataset = historyContainer.dataset || {};
  const endpoint = dataset.endpoint || "/alerts/history";
  const root = createRoot(historyContainer);
  renderWithI18n(root, <AlertHistory endpoint={endpoint} />);
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
  let initialStrategy = null;
  if (dataset.initialStrategy) {
    try {
      const parsed = JSON.parse(dataset.initialStrategy);
      if (parsed && typeof parsed === "object") {
        initialStrategy = parsed;
      }
    } catch (error) {
      console.error("Impossible de parser la stratégie initiale", error);
    }
  }
  const root = createRoot(strategyDesignerRoot);
  renderWithI18n(
    root,
    <StrategyDesigner
      saveEndpoint={saveEndpoint}
      defaultName={defaultName}
      defaultFormat={initialFormat}
      presets={presetCatalog}
      initialStrategy={initialStrategy}
    />
  );
}

const oneClickRoot = document.getElementById("strategy-one-click-root");
if (oneClickRoot) {
  const dataset = oneClickRoot.dataset || {};
  let defaults = {};
  if (dataset.defaults) {
    try {
      const parsed = JSON.parse(dataset.defaults);
      if (parsed && typeof parsed === "object") {
        defaults = parsed;
      }
    } catch (error) {
      console.error("Impossible de parser les valeurs par défaut de la stratégie one-click", error);
    }
  }
  const root = createRoot(oneClickRoot);
  renderWithI18n(
    root,
    <OneClickStrategyBuilder
      saveEndpoint={dataset.saveEndpoint || "/strategies/save"}
      runEndpoint={dataset.runEndpoint || "/backtests/run"}
      historyEndpointTemplate={dataset.historyEndpointTemplate || ""}
      backtestDetailTemplate={dataset.backtestDetailTemplate || ""}
      defaults={defaults}
    />
  );
}

const marketplaceRoot = document.getElementById("marketplace-root");
if (marketplaceRoot) {
  const dataset = marketplaceRoot.dataset || {};
  const root = createRoot(marketplaceRoot);
  renderWithI18n(
    root,
    <MarketplaceApp
      listingsEndpoint={dataset.endpoint || "/marketplace/listings"}
      reviewsEndpointTemplate={
        dataset.reviewsEndpointTemplate || "/marketplace/listings/__id__/reviews"
      }
    />
  );
}

const assistantRoot = document.getElementById("ai-strategy-assistant-root");
if (assistantRoot) {
  const dataset = assistantRoot.dataset || {};
  const generateEndpoint = dataset.generateEndpoint || "/strategies/generate";
  const importEndpoint = dataset.importEndpoint || "/strategies/import";
  const root = createRoot(assistantRoot);
  renderWithI18n(
    root,
    <AIStrategyAssistant generateEndpoint={generateEndpoint} importEndpoint={importEndpoint} />
  );
}

const backtestRoot = document.getElementById("strategy-backtest-root");
if (backtestRoot) {
  const dataset = backtestRoot.dataset || {};
  const historyPageSize = Number.parseInt(dataset.historyPageSize || "5", 10);
  const root = createRoot(backtestRoot);
  renderWithI18n(
    root,
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
      tradingViewConfigEndpoint={
        dataset.tradingviewConfigEndpoint || "/config/tradingview"
      }
      tradingViewUpdateEndpoint={
        dataset.tradingviewUpdateEndpoint || "/config/tradingview"
      }
    />
  );
}

export default PortfolioChartApp;
const onboardingContainer = document.getElementById("onboarding-root");
if (onboardingContainer) {
  const dataset = onboardingContainer.dataset || {};
  const root = createRoot(onboardingContainer);
  renderWithI18n(
    root,
    <OnboardingApp
      progressEndpoint={dataset.progressEndpoint || ""}
      stepTemplate={dataset.stepTemplate || ""}
      resetEndpoint={dataset.resetEndpoint || ""}
      userId={dataset.userId || ""}
    />
  );
}

function setupLanguageSelector() {
  const selector = document.querySelector("[data-language-selector]");
  if (!selector) {
    return;
  }
  selector.addEventListener("change", (event) => {
    const { value } = event.target;
    if (!value) {
      return;
    }
    i18n.changeLanguage(value);
    document.documentElement.setAttribute("lang", value);
    const cookieValue = `dashboard_lang=${value};path=/;max-age=${60 * 60 * 24 * 365}`;
    document.cookie = cookieValue;
    const url = new URL(window.location.href);
    url.searchParams.set("lang", value);
    window.location.assign(url.toString());
  });
}

setupLanguageSelector();

