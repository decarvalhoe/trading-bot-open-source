import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import useApi from "../../hooks/useApi.js";
import { bootstrap } from "../../bootstrap";

function normaliseOrders(payload, fallbackPageSize) {
  const ensureMetadata = (meta = {}) => ({
    total:
      meta.total ??
      meta.count ??
      meta.total_items ??
      meta.totalItems ??
      (Array.isArray(payload?.items) ? payload.items.length : 0),
    limit: meta.limit ?? meta.page_size ?? meta.pageSize ?? fallbackPageSize,
    offset:
      meta.offset ??
      (meta.page != null && meta.limit != null
        ? (meta.page - 1) * meta.limit
        : meta.start ?? 0),
  });

  if (!payload) {
    return { items: [], metadata: ensureMetadata() };
  }

  if (Array.isArray(payload.items)) {
    return { items: payload.items, metadata: ensureMetadata(payload.metadata || payload.pagination) };
  }

  if (Array.isArray(payload)) {
    return {
      items: payload,
      metadata: {
        total: payload.length,
        limit: fallbackPageSize,
        offset: 0,
      },
    };
  }

  return { items: [], metadata: ensureMetadata() };
}

function formatDateTime(value, locale = "fr-FR") {
  if (!value) {
    return "";
  }
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return typeof value === "string" ? value : String(value);
    }
    return date.toLocaleString(locale, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch (error) {
    return typeof value === "string" ? value : String(value);
  }
}

function formatNumber(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "-";
  }
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 8 }).format(Number(value));
}

export default function OrdersPage() {
  const { t, i18n } = useTranslation();
  const { orders, useQuery } = useApi();
  const tradingConfig = bootstrap?.config?.trading || {};
  const defaultPageSize = tradingConfig.ordersPageSize || 25;
  const ordersEndpoint = tradingConfig.ordersEndpoint || "/orders";
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  const [filters, setFilters] = useState({ account: "", symbol: "", status: "" });

  const queryParameters = useMemo(
    () => ({
      limit: pageSize,
      offset: page * pageSize,
      ...(filters.account ? { account_id: filters.account } : {}),
      ...(filters.symbol ? { symbol: filters.symbol } : {}),
      ...(filters.status ? { status: filters.status } : {}),
    }),
    [page, pageSize, filters.account, filters.symbol, filters.status],
  );

  const { data = { items: [], metadata: { total: 0, limit: pageSize, offset: 0 } }, isLoading, isError, isFetching, refetch } =
    useQuery({
      queryKey: ["orders", ordersEndpoint, queryParameters],
      keepPreviousData: true,
      queryFn: async () => {
        const payload = await orders.list({ endpoint: ordersEndpoint, query: queryParameters });
        return normaliseOrders(payload, pageSize);
      },
    });

  const items = Array.isArray(data.items) ? data.items : [];
  const metadata = data.metadata || { total: items.length, limit: pageSize, offset: page * pageSize };
  const totalPages = Math.max(1, Math.ceil((metadata.total || 0) / (metadata.limit || pageSize)));
  const currentPage = Math.min(totalPages - 1, Math.max(0, Math.floor((metadata.offset || 0) / (metadata.limit || pageSize))));

  const canPrevious = currentPage > 0;
  const canNext = currentPage < totalPages - 1;

  const handleFilterChange = (event) => {
    const { name, value } = event.target;
    setFilters((previous) => ({ ...previous, [name]: value }));
    setPage(0);
  };

  const handlePageSizeChange = (event) => {
    const size = Number.parseInt(event.target.value, 10) || defaultPageSize;
    setPageSize(size);
    setPage(0);
  };

  const goToPrevious = () => {
    if (canPrevious) {
      setPage((current) => Math.max(0, current - 1));
    }
  };

  const goToNext = () => {
    if (canNext) {
      setPage((current) => Math.min(totalPages - 1, current + 1));
    }
  };

  return (
    <div className="orders-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Journal des ordres")}</h1>
        <p className="text text--muted">
          {t("Analysez les ordres routés, leurs statuts et les remplissages associés en temps réel.")}
        </p>
        <div className="page-header__actions">
          <button type="button" className="button" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? t("Actualisation…") : t("Rafraîchir")}
          </button>
        </div>
      </header>

      <section aria-labelledby="orders-filters" className="orders-page__filters">
        <h2 id="orders-filters" className="visually-hidden">
          {t("Filtres des ordres")}
        </h2>
        <div className="filters-grid">
          <label className="form-field">
            <span className="form-field__label">{t("Compte")}</span>
            <input
              type="text"
              name="account"
              value={filters.account}
              onChange={handleFilterChange}
              placeholder={t("Identifiant de compte")}
            />
          </label>
          <label className="form-field">
            <span className="form-field__label">{t("Symbole")}</span>
            <input
              type="text"
              name="symbol"
              value={filters.symbol}
              onChange={handleFilterChange}
              placeholder={t("Exemple : BTCUSDT")}
            />
          </label>
          <label className="form-field">
            <span className="form-field__label">{t("Statut")}</span>
            <input
              type="text"
              name="status"
              value={filters.status}
              onChange={handleFilterChange}
              placeholder={t("Exemple : filled, cancelled")}
            />
          </label>
          <label className="form-field">
            <span className="form-field__label">{t("Entrées par page")}</span>
            <select value={pageSize} onChange={handlePageSizeChange}>
              {[10, 25, 50, 100].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {isLoading && items.length === 0 ? (
        <p className="text" role="status">
          {t("Chargement des ordres en cours…")}
        </p>
      ) : null}
      {isError ? (
        <p className="text text--critical" role="alert">
          {t("Impossible de récupérer le journal des ordres pour le moment.")}
        </p>
      ) : null}

      <div className="table-responsive">
        <table className="table" role="grid">
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">{t("Compte")}</th>
              <th scope="col">{t("Symbole")}</th>
              <th scope="col">{t("Côté")}</th>
              <th scope="col">{t("Type")}</th>
              <th scope="col">{t("Quantité")}</th>
              <th scope="col">{t("Rempli")}</th>
              <th scope="col">{t("Prix limite")}</th>
              <th scope="col">{t("Statut")}</th>
              <th scope="col">{t("Soumis le")}</th>
              <th scope="col">{t("Tags")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((order) => (
              <tr key={order.id}>
                <td data-label="ID">{order.id}</td>
                <td data-label={t("Compte")}>{order.account_id || "-"}</td>
                <td data-label={t("Symbole")}>{order.symbol || "-"}</td>
                <td data-label={t("Côté")}>{order.side || "-"}</td>
                <td data-label={t("Type")}>{order.order_type || "-"}</td>
                <td data-label={t("Quantité")}>{formatNumber(order.quantity)}</td>
                <td data-label={t("Rempli")}>{formatNumber(order.filled_quantity)}</td>
                <td data-label={t("Prix limite")}>
                  {order.limit_price != null ? formatNumber(order.limit_price) : "-"}
                </td>
                <td data-label={t("Statut")}>
                  <span className={`badge badge--${order.status || "neutral"}`}>{order.status || "-"}</span>
                </td>
                <td data-label={t("Soumis le")}>{formatDateTime(order.submitted_at || order.created_at, i18n.language)}</td>
                <td data-label={t("Tags")}>
                  {Array.isArray(order.tags) && order.tags.length > 0 ? order.tags.join(", ") : "-"}
                </td>
              </tr>
            ))}
            {!items.length && !isLoading && !isError ? (
              <tr>
                <td colSpan={11}>
                  <p className="text text--muted">{t("Aucun ordre trouvé pour ces critères.")}</p>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <footer className="table-footer">
        <div className="pagination">
          <button type="button" className="button" onClick={goToPrevious} disabled={!canPrevious}>
            {t("Précédent")}
          </button>
          <span className="pagination__meta">
            {t("Page {{current}} sur {{total}}", { current: currentPage + 1, total: totalPages })}
          </span>
          <button type="button" className="button" onClick={goToNext} disabled={!canNext}>
            {t("Suivant")}
          </button>
        </div>
        <p className="text text--muted">
          {t("{{count}} ordres au total", { count: metadata.total || 0 })}
        </p>
      </footer>
    </div>
  );
}
