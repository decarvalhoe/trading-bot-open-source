import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import PortfolioChart from "../../components/PortfolioChart.jsx";
import AlertManager from "../../alerts/AlertManager.jsx";
import AlertHistory from "../../alerts/AlertHistory.jsx";
import ReportsList from "../../reports/ReportsList.jsx";
import OnboardingApp from "../../onboarding/OnboardingApp.jsx";
import { bootstrap } from "../../bootstrap";

function PortfolioChartSection({ endpoint, currency }) {
  const { t } = useTranslation();
  const [state, setState] = useState({ status: "idle", items: [], currency });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setState((prev) => ({ ...prev, status: "loading" }));
      try {
        const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (cancelled) {
          return;
        }
        setState({
          status: "ready",
          items: Array.isArray(payload.items) ? payload.items : [],
          currency: payload.currency || currency,
        });
      } catch (error) {
        if (!cancelled) {
          setState({ status: "error", items: [], currency, error });
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [endpoint, currency]);

  if (state.status === "loading") {
    return <p className="text text--muted">{t("Chargement des données historiques…")}</p>;
  }
  if (state.status === "error") {
    return <p className="text text--critical">{t("Impossible de charger l'historique pour le moment.")}</p>;
  }

  return <PortfolioChart history={state.items} currency={state.currency || currency} />;
}

function MetricsCard({ label, value, tone, badge }) {
  return (
    <article className="metric-card" role="listitem">
      <p className="metric-card__label">{label}</p>
      <p className={`metric-card__value${tone ? ` metric-card__value--${tone}` : ""}`}>{value}</p>
      {badge && <span className={`badge badge--${badge.variant}`}>{badge.label}</span>}
    </article>
  );
}

function MetricsSection({ metrics }) {
  const { t } = useTranslation();
  if (!metrics) {
    return null;
  }

  const { currency = "$" } = metrics;
  const pnlPositive = (metrics.current_pnl || 0) >= 0;
  const cumulativePositive = (metrics.cumulative_return || 0) >= 0;
  let sharpeBadge = { variant: "neutral", label: t("ND") };
  if (metrics.sharpe_ratio != null) {
    if (metrics.sharpe_ratio >= 1.5) {
      sharpeBadge = { variant: "success", label: t("Excellent") };
    } else if (metrics.sharpe_ratio >= 1.0) {
      sharpeBadge = { variant: "info", label: t("Solide") };
    } else if (metrics.sharpe_ratio >= 0) {
      sharpeBadge = { variant: "warning", label: t("À surveiller") };
    } else {
      sharpeBadge = { variant: "critical", label: t("Sous la cible") };
    }
  }

  return (
    <section className="card card--metrics" aria-labelledby="metrics-title">
      <div className="card__header">
        <h2 id="metrics-title" className="heading heading--lg">
          {t("Performance")}
        </h2>
        <p className="text text--muted">
          {metrics.account && <span>Compte {metrics.account} · </span>}
          {metrics.as_of && <span>Mise à jour le {new Date(metrics.as_of).toLocaleDateString()}</span>}
        </p>
      </div>
      <div className="card__body">
        {metrics.available ? (
          <div className="metrics-grid" role="list" aria-describedby="metrics-title">
            <MetricsCard
              label={t("P&L courant")}
              value={`${metrics.current_pnl.toFixed(2)} ${currency}`}
              tone={pnlPositive ? "positive" : "negative"}
              badge={{ variant: pnlPositive ? "success" : "critical", label: pnlPositive ? t("Gain") : t("Perte") }}
            />
            <MetricsCard
              label={t("Drawdown")}
              value={`${metrics.current_drawdown.toFixed(2)} ${currency}`}
              tone="negative"
              badge={{ variant: "warning", label: t("Protection du capital") }}
            />
            <MetricsCard
              label={t("Rendement cumulatif")}
              value={metrics.cumulative_return_is_ratio ? `${(metrics.cumulative_return * 100).toFixed(2)} %` : `${metrics.cumulative_return.toFixed(2)} ${currency}`}
              tone={cumulativePositive ? "positive" : "negative"}
              badge={{ variant: cumulativePositive ? "success" : "critical", label: cumulativePositive ? t("En hausse") : t("En baisse") }}
            />
            <MetricsCard
              label={t("Sharpe annualisé")}
              value={metrics.sharpe_ratio != null ? metrics.sharpe_ratio.toFixed(2) : "—"}
              badge={sharpeBadge}
            />
          </div>
        ) : (
          <p className="text text--muted">{t("Les métriques de performance ne sont pas disponibles pour le moment.")}</p>
        )}
        {metrics.sample_size ? (
          <p className="text text--muted">
            {t("Basé sur {{count}} sessions", { count: metrics.sample_size })}
          </p>
        ) : null}
      </div>
    </section>
  );
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const dashboardData = bootstrap?.data?.dashboard || {};
  const [metrics, setMetrics] = useState(dashboardData.metrics || null);
  const [reports, setReports] = useState(dashboardData.reports?.items || []);
  const onboardingConfig = dashboardData.onboarding || bootstrap?.config?.onboarding || {};
  const alertsConfig = dashboardData.alerts || bootstrap?.config?.alerts || {};
  const reportsPageSize = dashboardData.reports?.pageSize || 5;
  const chartConfig = dashboardData.chart || bootstrap?.config?.dashboard?.chart || {};
  const contextEndpoint = bootstrap?.config?.dashboard?.contextEndpoint || "/dashboard/context";

  useEffect(() => {
    if (metrics && reports.length) {
      return;
    }
    let cancelled = false;
    async function loadContext() {
      try {
        const response = await fetch(contextEndpoint, { headers: { Accept: "application/json" } });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (!cancelled && payload) {
          if (payload.metrics) {
            setMetrics(payload.metrics);
          }
          if (Array.isArray(payload.reports)) {
            setReports(payload.reports);
          }
        }
      } catch (error) {
        if (!cancelled) {
          console.error("Impossible de charger le contexte du tableau de bord", error);
        }
      }
    }
    loadContext();
    return () => {
      cancelled = true;
    };
  }, [contextEndpoint, metrics, reports.length]);

  return (
    <div className="dashboard">
      <section className="card card--onboarding" aria-labelledby="onboarding-title">
        <div className="card__header">
          <h2 id="onboarding-title" className="heading heading--lg">
            {t("Parcours d'onboarding")}
          </h2>
          <p className="text text--muted">
            {t("Connectez votre broker, définissez votre stratégie et testez-la avant le go-live.")}
          </p>
        </div>
        <div className="card__body">
          <OnboardingApp {...onboardingConfig} />
        </div>
      </section>

      <MetricsSection metrics={metrics} />

      <section className="card" aria-labelledby="reports-title">
        <div className="card__header">
          <h2 id="reports-title" className="heading heading--lg">
            {t("Rapports récents")}
          </h2>
          <p className="text text--muted">{t("Synthèse des rapports générés par le moteur de reporting.")}</p>
        </div>
        <div className="card__body">
          <ReportsList reports={reports} pageSize={reportsPageSize} />
        </div>
      </section>

      <section className="card" aria-labelledby="chart-title">
        <div className="card__header">
          <h2 id="chart-title" className="heading heading--lg">
            {t("Historique de performance")}
          </h2>
          <p className="text text--muted">{t("Évolution quotidienne de la valeur totale par portefeuille.")}</p>
        </div>
        <div className="card__body">
          <PortfolioChartSection endpoint={chartConfig.endpoint || "/portfolios/history"} currency={chartConfig.currency || "$"} />
        </div>
      </section>

      <section className="card" aria-labelledby="alerts-title">
        <div className="card__header">
          <h2 id="alerts-title" className="heading heading--lg">
            {t("Alertes actives")}
          </h2>
          <p className="text text--muted">{t("Déclenchements prioritaires provenant du moteur d'alertes.")}</p>
        </div>
        <div className="card__body">
          <AlertManager initialAlerts={alertsConfig.initialItems || []} endpoint={alertsConfig.endpoint || "/alerts"} authToken={alertsConfig.token || ""} />
        </div>
      </section>

      <section className="card" aria-labelledby="alerts-history-title">
        <div className="card__header">
          <h2 id="alerts-history-title" className="heading heading--lg">
            {t("Historique")}
          </h2>
          <p className="text text--muted">{t("Déclenchements archivés par le moteur d'alertes.")}</p>
        </div>
        <div className="card__body">
          <AlertHistory endpoint={alertsConfig.historyEndpoint || "/alerts/history"} />
        </div>
      </section>
    </div>
  );
}
