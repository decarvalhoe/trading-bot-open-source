import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import PortfolioChart from "../../components/PortfolioChart.jsx";
import AlertManager from "../../alerts/AlertManager.jsx";
import AlertHistory from "../../alerts/AlertHistory.jsx";
import ReportsList from "../../reports/ReportsList.jsx";
import OnboardingApp from "../../onboarding/OnboardingApp.jsx";
import { bootstrap } from "../../bootstrap";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card.jsx";
import { Badge } from "../../components/ui/badge.jsx";
import useApi from "../../hooks/useApi.js";
import useWebSocket from "../../hooks/useWebSocket.js";

function extractHistoryPayload(payload) {
  if (!payload) {
    return null;
  }
  if (Array.isArray(payload.items)) {
    return payload;
  }
  if (Array.isArray(payload)) {
    return { items: payload };
  }
  if (payload.payload && typeof payload.payload === "object") {
    return extractHistoryPayload(payload.payload);
  }
  if (payload.detail && typeof payload.detail === "object") {
    return extractHistoryPayload(payload.detail);
  }
  return null;
}

function PortfolioChartSection({ endpoint, currency }) {
  const { t } = useTranslation();
  const { dashboard, useQuery, queryClient } = useApi();
  const { subscribe, isConnected } = useWebSocket();
  const queryKey = useMemo(() => ["dashboard", "history", endpoint], [endpoint]);
  const [history, setHistory] = useState([]);
  const [currentCurrency, setCurrentCurrency] = useState(currency);
  const {
    data = { items: [], currency },
    isLoading,
    isError,
  } = useQuery({
    queryKey,
    enabled: Boolean(endpoint),
    initialData: { items: [], currency },
    refetchInterval: isConnected ? false : 30000,
    refetchOnWindowFocus: !isConnected,
    refetchIntervalInBackground: !isConnected,
    queryFn: async () => {
      const payload = await dashboard.history({ endpoint });
      if (payload && Array.isArray(payload.items)) {
        return {
          items: payload.items,
          currency: payload.currency || currency,
        };
      }
      if (Array.isArray(payload)) {
        return { items: payload, currency };
      }
      return { items: [], currency };
    },
  });

  useEffect(() => {
    const items = Array.isArray(data.items) ? data.items : [];
    setHistory(items);
    setCurrentCurrency(data.currency || currency);
  }, [data.items, data.currency, currency]);

  useEffect(() => {
    const unsubscribe = subscribe(
      ["portfolios", "portfolios.update", "portfolio.history", "trading.history"],
      (event) => {
        const detail =
          extractHistoryPayload(event.payload) || extractHistoryPayload(event.message?.payload);
        if (!detail || !Array.isArray(detail.items)) {
          return;
        }
        setHistory(detail.items);
        if (detail.currency) {
          setCurrentCurrency(detail.currency);
        }
        queryClient.setQueryData(queryKey, (previous = { items: [], currency }) => ({
          items: detail.items,
          currency: detail.currency || previous.currency || currency,
        }));
      }
    );
    return () => {
      unsubscribe();
    };
  }, [subscribe, queryClient, queryKey, currency]);

  if (isLoading) {
    return <p className="text text--muted">{t("Chargement des données historiques…")}</p>;
  }
  if (isError) {
    return <p className="text text--critical">{t("Impossible de charger l'historique pour le moment.")}</p>;
  }

  return <PortfolioChart history={history} currency={currentCurrency || currency} />;
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
  const { dashboard, useQuery } = useApi();
  const dashboardData = bootstrap?.data?.dashboard || {};
  const onboardingConfig = dashboardData.onboarding || bootstrap?.config?.onboarding || {};
  const alertsConfig = dashboardData.alerts || bootstrap?.config?.alerts || {};
  const reportsPageSize = dashboardData.reports?.pageSize || 5;
  const chartConfig = dashboardData.chart || bootstrap?.config?.dashboard?.chart || {};
  const contextEndpoint = bootstrap?.config?.dashboard?.contextEndpoint || "/dashboard/context";

  const initialContext = useMemo(
    () => ({
      metrics: dashboardData.metrics || null,
      reports: dashboardData.reports?.items || [],
    }),
    [dashboardData.metrics, dashboardData.reports?.items]
  );

  const { data: context = initialContext } = useQuery({
    queryKey: ["dashboard", "context", contextEndpoint],
    enabled: Boolean(contextEndpoint),
    initialData: initialContext,
    queryFn: async () => {
      const payload = await dashboard.context({ endpoint: contextEndpoint });
      return {
        metrics: payload?.metrics || null,
        reports: Array.isArray(payload?.reports) ? payload.reports : [],
      };
    },
  });

  const metrics = context.metrics || initialContext.metrics;
  const reports = context.reports || initialContext.reports;

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
