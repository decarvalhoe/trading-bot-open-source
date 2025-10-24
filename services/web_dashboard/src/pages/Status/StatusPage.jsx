import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bootstrap } from "../../bootstrap";

export default function StatusPage() {
  const { t } = useTranslation();
  const initialData = bootstrap?.data?.status || {};
  const [services, setServices] = useState(initialData.services || []);
  const [checkedAt, setCheckedAt] = useState(initialData.checked_at || null);
  const statusEndpoint =
    initialData.endpoint || bootstrap?.config?.status?.endpoint || "/status/overview";

  const refresh = useCallback(async () => {
    try {
      const response = await fetch(statusEndpoint, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      if (Array.isArray(payload.services)) {
        setServices(payload.services);
      }
      if (payload.checked_at) {
        setCheckedAt(payload.checked_at);
      }
    } catch (error) {
      console.error("Impossible de rafraîchir le statut", error);
    }
  }, [statusEndpoint]);

  useEffect(() => {
    if (!services.length) {
      refresh();
    }
  }, [services.length, refresh]);

  return (
    <div className="status-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Statut des services")}</h1>
        <p className="text text--muted">
          {t("Surveillez la disponibilité des services critiques et détectez rapidement les incidents.")}
        </p>
        <button type="button" className="button" onClick={refresh}>
          {t("Rafraîchir")}
        </button>
      </header>

      {checkedAt && (
        <p className="text text--muted">
          {t("Dernière vérification : {{date}}", { date: new Date(checkedAt).toLocaleString() })}
        </p>
      )}

      <div className="status-grid">
        {services.map((service) => (
          <article key={service.name} className={`status-card status-card--${service.status}`}>
            <header className="status-card__header">
              <h2 className="heading heading--md">{service.label}</h2>
              <span className={`badge badge--${service.badge_variant || "neutral"}`}>{service.status_label}</span>
            </header>
            <p className="text text--muted">{service.description}</p>
            <p className="text text--muted">{service.health_url}</p>
            {service.detail && <p className="text text--critical">{service.detail}</p>}
          </article>
        ))}
      </div>
    </div>
  );
}
