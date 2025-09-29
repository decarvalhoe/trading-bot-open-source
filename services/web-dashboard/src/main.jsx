import React, { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import PortfolioChart from "./components/PortfolioChart.jsx";
import AlertManager from "./alerts/AlertManager.jsx";
import AlertHistory from "./alerts/AlertHistory.jsx";

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

export default PortfolioChartApp;
