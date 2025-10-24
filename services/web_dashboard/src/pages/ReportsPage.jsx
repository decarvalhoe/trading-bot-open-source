import React from "react";
import { useTranslation } from "react-i18next";
import useApi from "../hooks/useApi.js";
import ReportsList from "../reports/ReportsList.jsx";
import { bootstrap } from "../bootstrap";

function normaliseReportsPayload(payload) {
  if (!payload) {
    return [];
  }
  if (Array.isArray(payload.items)) {
    return payload.items;
  }
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload.results)) {
    return payload.results;
  }
  return [];
}

export default function ReportsPage() {
  const { t } = useTranslation();
  const { reports: reportsApi, useQuery } = useApi();
  const reportsData = bootstrap?.data?.reports || {};
  const reportsConfig = bootstrap?.config?.reports || {};
  const reportsEndpoint = reportsData.endpoint || reportsConfig.endpoint || "/reports";
  const pageSize = reportsConfig.pageSize || reportsData.pageSize || 10;

  const {
    data = { items: [] },
    isLoading,
    isError,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["reports", reportsEndpoint, pageSize],
    queryFn: async () => {
      const payload = await reportsApi.list({ endpoint: reportsEndpoint, query: { limit: pageSize } });
      return { items: normaliseReportsPayload(payload) };
    },
  });

  const items = normaliseReportsPayload(data);

  return (
    <div className="reports-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Centre de rapports")}</h1>
        <p className="text text--muted">
          {t("Téléchargez vos rapports quotidiens, hebdomadaires ou personnalisés générés par le moteur de reporting.")}
        </p>
        <div className="page-header__actions">
          <button type="button" className="button" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? t("Actualisation…") : t("Rafraîchir")}
          </button>
        </div>
      </header>

      {isLoading ? (
        <p className="text" role="status">
          {t("Chargement des rapports en cours…")}
        </p>
      ) : null}

      {isError ? (
        <p className="text text--critical" role="alert">
          {t("Impossible de récupérer la liste des rapports.")}
        </p>
      ) : null}

      {!isLoading && !isError ? <ReportsList reports={items} pageSize={pageSize} /> : null}
    </div>
  );
}
