import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bootstrap } from "../../bootstrap";

function FollowerTable({ copies }) {
  const { t } = useTranslation();
  if (!copies || copies.length === 0) {
    return <p className="text text--muted">{t("Aucune copie active pour le moment.")}</p>;
  }
  return (
    <table className="table follower-table">
      <thead>
        <tr>
          <th>{t("Stratégie")}</th>
          <th>{t("Leader")}</th>
          <th>{t("Levée")}</th>
          <th>{t("Capital alloué")}</th>
          <th>{t("Divergence (bps)")}</th>
          <th>{t("Dernière synchro")}</th>
        </tr>
      </thead>
      <tbody>
        {copies.map((copy) => (
          <tr key={copy.listing_id}>
            <td>{copy.strategy_name || t("Stratégie inconnue")}</td>
            <td>{copy.leader_id || "—"}</td>
            <td>{copy.leverage}</td>
            <td>{copy.allocated_capital != null ? copy.allocated_capital.toLocaleString() : "—"}</td>
            <td>{copy.divergence_bps != null ? copy.divergence_bps.toFixed(2) : "—"}</td>
            <td>{copy.last_synced_at ? new Date(copy.last_synced_at).toLocaleString() : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function FollowerDashboardPage() {
  const { t } = useTranslation();
  const [data, setData] = useState(bootstrap?.data?.followers || {});
  const endpoint = bootstrap?.config?.followers?.endpoint || "/dashboard/followers/context";

  useEffect(() => {
    if (data.copies && data.copies.length > 0) {
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (!cancelled) {
          setData(payload || {});
        }
      } catch (error) {
        if (!cancelled) {
          console.error("Impossible de charger le suivi des copies", error);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [data.copies, endpoint]);
  return (
    <div className="follower-dashboard">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Suivi des copies")}</h1>
        <p className="text text--muted">
          {t("Visualisez vos allocations de copy-trading et surveillez la divergence d'exécution.")}
        </p>
      </header>
      {data.fallback_reason && (
        <div className="alert alert--warning" role="alert">
          {data.fallback_reason}
        </div>
      )}
      <FollowerTable copies={data.copies || []} />
    </div>
  );
}
