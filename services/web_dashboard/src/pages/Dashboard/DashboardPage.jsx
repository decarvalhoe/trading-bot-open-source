import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import PortfolioChart from "../../components/PortfolioChart.jsx";
import AlertManager from "../../alerts/AlertManager.jsx";
import AlertHistory from "../../alerts/AlertHistory.jsx";
import ReportsList from "../../reports/ReportsList.jsx";
import OnboardingApp from "../../onboarding/OnboardingApp.jsx";
import { bootstrap } from "../../bootstrap";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card.jsx";
import { Badge } from "../../components/ui/badge.jsx";

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
  const valueClassName = tone ? `metric-card__value metric-card__value--${tone}` : "metric-card__value";
  return (
    <article className="metric-card" role="listitem">
      <p className="metric-card__label">{label}</p>
      <p className={valueClassName}>{value}</p>
      {badge ? <Badge variant={badge.variant}>{badge.label}</Badge> : null}
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
    <Card aria-labelledby="metrics-title">
      <CardHeader>
        <CardTitle id="metrics-title">{t("Performance")}</CardTitle>
        <CardDescription>
          {metrics.account && <span>Compte {metrics.account} · </span>}
          {metrics.as_of && <span>Mise à jour le {new Date(metrics.as_of).toLocaleDateString()}</span>}
        </CardDescription>
      </CardHeader>
      <CardContent>
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
      </CardContent>
    </Card>
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
      <Card aria-labelledby="onboarding-title">
        <CardHeader>
          <CardTitle id="onboarding-title">{t("Parcours d'onboarding")}</CardTitle>
          <CardDescription>
            {t("Connectez votre broker, définissez votre stratégie et testez-la avant le go-live.")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <OnboardingApp {...onboardingConfig} />
        </CardContent>
      </Card>

      <MetricsSection metrics={metrics} />

      <Card aria-labelledby="reports-title">
        <CardHeader>
          <CardTitle id="reports-title">{t("Rapports récents")}</CardTitle>
          <CardDescription>
            {t("Synthèse des rapports générés par le moteur de reporting.")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ReportsList reports={reports} pageSize={reportsPageSize} />
        </CardContent>
      </Card>

      <Card aria-labelledby="chart-title">
        <CardHeader>
          <CardTitle id="chart-title">{t("Historique de performance")}</CardTitle>
          <CardDescription>
            {t("Évolution quotidienne de la valeur totale par portefeuille.")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PortfolioChartSection endpoint={chartConfig.endpoint || "/portfolios/history"} currency={chartConfig.currency || "$"} />
        </CardContent>
      </Card>

      <Card aria-labelledby="alerts-title">
        <CardHeader>
          <CardTitle id="alerts-title">{t("Alertes actives")}</CardTitle>
          <CardDescription>
            {t("Déclenchements prioritaires provenant du moteur d'alertes.")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AlertManager initialAlerts={alertsConfig.initialItems || []} endpoint={alertsConfig.endpoint || "/alerts"} authToken={alertsConfig.token || ""} />
        </CardContent>
      </Card>

      <Card aria-labelledby="alerts-history-title">
        <CardHeader>
          <CardTitle id="alerts-history-title">{t("Historique")}</CardTitle>
          <CardDescription>
            {t("Déclenchements archivés par le moteur d'alertes.")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AlertHistory endpoint={alertsConfig.historyEndpoint || "/alerts/history"} />
        </CardContent>
      </Card>
    </div>
  );
}
