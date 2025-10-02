import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

function formatDate(value, locale = "fr") {
  if (!value) {
    return "";
  }
  try {
    const date = new Date(value);
    return new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } catch (error) {
    return String(value);
  }
}

function AlertHistory({ endpoint = "/alerts/history" }) {
  const { t, i18n } = useTranslation();
  const [status, setStatus] = useState("idle");
  const [items, setItems] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 10 });
  const [filters, setFilters] = useState({ strategy: "", severity: "" });
  const [availableFilters, setAvailableFilters] = useState({ strategies: [], severities: [] });

  const queryParams = useMemo(() => {
    const params = new URLSearchParams();
    params.set("page", pagination.page);
    params.set("page_size", pagination.page_size || 10);
    if (filters.strategy) {
      params.set("strategy", filters.strategy);
    }
    if (filters.severity) {
      params.set("severity", filters.severity);
    }
    return params.toString();
  }, [pagination.page, pagination.page_size, filters.strategy, filters.severity]);

  useEffect(() => {
    async function loadHistory() {
      setStatus("loading");
      try {
        const url = `${endpoint}?${queryParams}`;
        const response = await fetch(url, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        setItems(Array.isArray(payload.items) ? payload.items : []);
        const paginationPayload = payload.pagination || {};
        setPagination((current) => ({
          page: paginationPayload.page || current.page,
          pages: paginationPayload.pages || paginationPayload.total_pages || 1,
          total: paginationPayload.total ?? current.total,
          page_size: paginationPayload.page_size || current.page_size,
        }));
        if (payload.available_filters) {
          setAvailableFilters({
            strategies: payload.available_filters.strategies || [],
            severities: payload.available_filters.severities || [],
          });
        }
        setStatus("ready");
      } catch (fetchError) {
        setStatus("error");
      }
    }

    loadHistory();
  }, [endpoint, queryParams]);

  const canPrevious = pagination.page > 1;
  const canNext = pagination.page < (pagination.pages || 1);

  function handleSeverityChange(event) {
    setFilters((current) => ({ ...current, severity: event.target.value }));
    setPagination((current) => ({ ...current, page: 1 }));
  }

  function handleStrategyChange(event) {
    setFilters((current) => ({ ...current, strategy: event.target.value }));
    setPagination((current) => ({ ...current, page: 1 }));
  }

  function handlePageSizeChange(event) {
    const size = Number.parseInt(event.target.value, 10) || 10;
    setPagination((current) => ({ ...current, page_size: size, page: 1 }));
  }

  function goToPreviousPage() {
    if (!canPrevious) {
      return;
    }
    setPagination((current) => ({ ...current, page: Math.max(1, current.page - 1) }));
  }

  function goToNextPage() {
    if (!canNext) {
      return;
    }
    setPagination((current) => ({ ...current, page: current.page + 1 }));
  }

  return (
    <section className="history-panel" aria-live="polite">
      <header className="history-panel__header">
        <h2 className="heading heading--lg">{t("Historique des alertes")}</h2>
        <p className="text text--muted">
          {t("Consultez les déclenchements passés et leurs métadonnées.")}
        </p>
      </header>
      <div className="history-panel__filters">
        <label className="form-field">
          <span className="form-field__label">{t("Sévérité")}</span>
          <select value={filters.severity} onChange={handleSeverityChange}>
            <option value="">{t("Toutes")}</option>
            {availableFilters.severities.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span className="form-field__label">{t("Stratégie")}</span>
          <select value={filters.strategy} onChange={handleStrategyChange}>
            <option value="">{t("Toutes")}</option>
            {availableFilters.strategies.map((strategy) => (
              <option key={strategy} value={strategy}>
                {strategy}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span className="form-field__label">{t("Entrées par page")}</span>
          <select value={pagination.page_size} onChange={handlePageSizeChange}>
            {[5, 10, 20, 50].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </div>
      {status === "loading" && (
        <p className="text" role="status">
          {t("Chargement de l'historique…")}
        </p>
      )}
      {status === "error" && (
        <p className="text text--critical" role="alert">
          {t("Impossible de récupérer l'historique pour le moment.")}
        </p>
      )}
      {status === "ready" && items.length === 0 && (
        <p className="text text--muted">
          {t("Aucun déclenchement enregistré pour ces filtres.")}
        </p>
      )}
      {items.length > 0 && (
        <div className="table-responsive">
          <table className="table history-table" role="grid">
            <thead>
              <tr>
                <th scope="col">{t("Déclenchée le")}</th>
                <th scope="col">{t("Type")}</th>
                <th scope="col">{t("Canal")}</th>
                <th scope="col">{t("Règle")}</th>
                <th scope="col">{t("Stratégie")}</th>
                <th scope="col">{t("Sévérité")}</th>
                <th scope="col">{t("Symbole")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((event) => (
                <tr key={event.id || `${event.trigger_id}-${event.rule_id}`}>
                  <td data-label={t("Déclenchée le")}>
                    {formatDate(event.triggered_at, i18n.language)}
                  </td>
                  <td data-label={t("Type")}>{event.notification_type || "trigger"}</td>
                  <td data-label={t("Canal")}>{event.notification_channel || "-"}</td>
                  <td data-label={t("Règle")}>{event.rule_name}</td>
                  <td data-label={t("Stratégie")}>{event.strategy}</td>
                  <td data-label={t("Sévérité")}>
                    <span className={`badge badge--${event.severity || "info"}`}>
                      {event.severity}
                    </span>
                  </td>
                  <td data-label={t("Symbole")}>{event.symbol}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <footer className="history-panel__footer">
        <button
          type="button"
          className="button button--ghost"
          onClick={goToPreviousPage}
          disabled={!canPrevious}
        >
          {t("Précédent")}
        </button>
        <span className="text text--muted">
          {t("Page {page} sur {pages} ({total} alertes)", {
            page: pagination.page,
            pages: pagination.pages || 1,
            total: pagination.total,
          })}
        </span>
        <button
          type="button"
          className="button button--ghost"
          onClick={goToNextPage}
          disabled={!canNext}
        >
          {t("Suivant")}
        </button>
      </footer>
    </section>
  );
}

export default AlertHistory;
