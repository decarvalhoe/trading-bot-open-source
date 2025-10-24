import React from "react";
import { useTranslation } from "react-i18next";
import AlertManager from "../alerts/AlertManager.jsx";
import AlertHistory from "../alerts/AlertHistory.jsx";
import { bootstrap } from "../bootstrap";

export default function AlertsPage() {
  const { t } = useTranslation();
  const alertsData = bootstrap?.data?.alerts || {};
  const alertsConfig = bootstrap?.config?.alerts || {};
  const activeEndpoint = alertsData.endpoint || alertsConfig.endpoint || "/alerts";
  const historyEndpoint = alertsData.historyEndpoint || alertsConfig.historyEndpoint || "/alerts/history";
  const token = alertsData.token || alertsConfig.token || "";
  const initialAlerts = alertsData.initialItems || alertsConfig.initialItems || [];

  return (
    <div className="alerts-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Gestion des alertes")}</h1>
        <p className="text text--muted">
          {t("Pilotez vos déclencheurs en direct, examinez l'historique et ajustez vos canaux de notification.")}
        </p>
      </header>

      <section className="alerts-section" aria-labelledby="alerts-active-title">
        <h2 id="alerts-active-title" className="heading heading--lg">
          {t("Alertes actives")}
        </h2>
        <AlertManager initialAlerts={initialAlerts} endpoint={activeEndpoint} authToken={token} />
      </section>

      <section className="alerts-section" aria-labelledby="alerts-history-title">
        <h2 id="alerts-history-title" className="heading heading--lg">
          {t("Historique des alertes")}
        </h2>
        <AlertHistory endpoint={historyEndpoint} />
      </section>
    </div>
  );
}
