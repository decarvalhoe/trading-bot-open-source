import React from "react";

const RISK_LABELS = {
  info: { label: "Information", className: "badge--info" },
  warning: { label: "Avertissement", className: "badge--warning" },
  critical: { label: "Critique", className: "badge--critical" },
};

function formatTimestamp(value) {
  if (!value) {
    return "";
  }
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function AlertTable({ alerts, onEdit, onDelete, loading, pendingId }) {
  return (
    <div className="alerts-table">
      <div className="alerts-table__header">
        <h3 className="heading heading--md">Alertes actives</h3>
        <p className="text text--muted">Suivez les signaux générés par le moteur d'alertes.</p>
      </div>
      <div className="alerts-table__content" role="region" aria-live="polite">
        <table className="table alerts-table__grid">
          <thead>
            <tr>
              <th scope="col">Titre</th>
              <th scope="col">Risque</th>
              <th scope="col">Statut</th>
              <th scope="col">Créée</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {alerts.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <p className="text text--muted">
                    {loading ? "Chargement des alertes…" : "Aucune alerte enregistrée pour le moment."}
                  </p>
                </td>
              </tr>
            ) : (
              alerts.map((alert) => {
                const risk =
                  typeof alert.risk === "string"
                    ? alert.risk
                    : alert.risk?.value || "info";
                const riskMeta = RISK_LABELS[risk] || RISK_LABELS.info;
                return (
                  <tr key={alert.id}>
                    <td data-label="Titre">
                      <div className="alerts-table__title">{alert.title}</div>
                      <p className="alerts-table__detail">{alert.detail}</p>
                    </td>
                    <td data-label="Risque">
                      <span className={`badge ${riskMeta.className}`}>{riskMeta.label}</span>
                    </td>
                    <td data-label="Statut">
                      <span className={`badge ${alert.acknowledged ? "badge--neutral" : "badge--info"}`}>
                        {alert.acknowledged ? "Accusée" : "À traiter"}
                      </span>
                    </td>
                    <td data-label="Créée">{formatTimestamp(alert.created_at || alert.createdAt)}</td>
                    <td data-label="Actions" className="alerts-table__actions">
                      <button
                        type="button"
                        className="button button--ghost"
                        onClick={() => onEdit?.(alert)}
                        disabled={pendingId === alert.id}
                      >
                        Modifier
                      </button>
                      <button
                        type="button"
                        className="button button--danger"
                        onClick={() => onDelete?.(alert)}
                        disabled={pendingId === alert.id}
                      >
                        Supprimer
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default AlertTable;
