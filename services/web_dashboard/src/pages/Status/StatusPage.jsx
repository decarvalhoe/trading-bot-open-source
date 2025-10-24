import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { bootstrap } from "../../bootstrap";
import useApi from "../../hooks/useApi.js";
import useWebSocket from "../../hooks/useWebSocket.js";

function normaliseStatusPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  if (Array.isArray(payload.services) || payload.checked_at) {
    return payload;
  }
  if (payload.payload && typeof payload.payload === "object") {
    return normaliseStatusPayload(payload.payload);
  }
  if (payload.detail && typeof payload.detail === "object") {
    return normaliseStatusPayload(payload.detail);
  }
  return null;
}

export default function StatusPage() {
  const { t } = useTranslation();
  const initialData = bootstrap?.data?.status || {};
  const initialServices = initialData.services || [];
  const initialCheckedAt = initialData.checked_at || null;
  const statusEndpoint =
    initialData.endpoint || bootstrap?.config?.status?.endpoint || "/status/overview";
  const { client, useQuery, queryClient } = useApi();
  const { subscribe, isConnected } = useWebSocket();
  const queryKey = useMemo(() => ["status", statusEndpoint], [statusEndpoint]);
  const [services, setServices] = useState(initialServices);
  const [checkedAt, setCheckedAt] = useState(initialCheckedAt);

  const {
    data = { services: initialServices, checked_at: initialCheckedAt },
    isFetching,
    refetch,
  } = useQuery({
    queryKey,
    enabled: Boolean(statusEndpoint),
    initialData: { services: initialServices, checked_at: initialCheckedAt },
    refetchInterval: isConnected ? false : 20000,
    refetchOnWindowFocus: !isConnected,
    refetchIntervalInBackground: !isConnected,
    queryFn: async () => {
      const payload = await client.request(statusEndpoint, {
        method: "GET",
        headers: { Accept: "application/json" },
      });
      return {
        services: Array.isArray(payload?.services) ? payload.services : [],
        checked_at: payload?.checked_at || null,
      };
    },
  });

  useEffect(() => {
    setServices(Array.isArray(data.services) ? data.services : []);
    setCheckedAt(data.checked_at || null);
  }, [data.services, data.checked_at]);

  useEffect(() => {
    const unsubscribe = subscribe(["status", "status.update", "monitoring"], (event) => {
      const detail =
        normaliseStatusPayload(event.payload) || normaliseStatusPayload(event.message?.payload);
      if (!detail) {
        return;
      }
      if (Array.isArray(detail.services)) {
        setServices(detail.services);
      }
      if (detail.checked_at) {
        setCheckedAt(detail.checked_at);
      }
      queryClient.setQueryData(queryKey, (previous = { services: [], checked_at: null }) => ({
        services: Array.isArray(detail.services) ? detail.services : previous.services,
        checked_at: detail.checked_at || previous.checked_at || null,
      }));
    });
    return () => {
      unsubscribe();
    };
  }, [subscribe, queryClient, queryKey]);

  return (
    <div className="status-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Statut des services")}</h1>
        <p className="text text--muted">
          {t("Surveillez la disponibilité des services critiques et détectez rapidement les incidents.")}
        </p>
        <button
          type="button"
          className="button"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          {isFetching ? t("Actualisation…") : t("Rafraîchir")}
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
