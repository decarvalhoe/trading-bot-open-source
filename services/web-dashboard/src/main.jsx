import React, { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import PortfolioChart from "./components/PortfolioChart.jsx";

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

const container = document.getElementById("portfolio-chart");
if (container) {
  const endpoint = container.dataset.endpoint || "/portfolios/history";
  const currency = container.dataset.currency || "$";
  const root = createRoot(container);
  root.render(
    <StrictMode>
      <PortfolioChartApp endpoint={endpoint} currency={currency} />
    </StrictMode>
  );
}

export default PortfolioChartApp;
