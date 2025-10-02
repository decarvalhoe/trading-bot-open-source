import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import ListingCard from "./ListingCard.jsx";

function buildQuery(filters) {
  const params = new URLSearchParams();
  if (filters.search) {
    params.set("search", filters.search);
  }
  if (filters.minPerformance) {
    params.set("min_performance", filters.minPerformance);
  }
  if (filters.maxRisk) {
    params.set("max_risk", filters.maxRisk);
  }
  if (filters.maxPrice) {
    params.set("max_price", filters.maxPrice);
  }
  if (filters.sort) {
    params.set("sort", filters.sort);
  }
  return params.toString();
}

function MarketplaceApp({ listingsEndpoint, reviewsEndpointTemplate }) {
  const { t } = useTranslation();
  const [filters, setFilters] = useState({
    search: "",
    minPerformance: "",
    maxRisk: "",
    maxPrice: "",
    sort: "created_desc",
  });
  const [state, setState] = useState({ status: "idle", items: [], error: null });

  const sortOptions = useMemo(
    () => [
      { value: "created_desc", label: t("Plus récents") },
      { value: "price_asc", label: t("Prix croissant") },
      { value: "price_desc", label: t("Prix décroissant") },
      { value: "performance_desc", label: t("Performance décroissante") },
      { value: "performance_asc", label: t("Performance croissante") },
      { value: "risk_asc", label: t("Risque croissant") },
      { value: "risk_desc", label: t("Risque décroissant") },
      { value: "rating_desc", label: t("Mieux notées") },
    ],
    [t]
  );

  useEffect(() => {
    const abort = new AbortController();
    async function load() {
      setState((prev) => ({ ...prev, status: "loading", error: null }));
      try {
        const query = buildQuery(filters);
        const response = await fetch(
          query ? `${listingsEndpoint}?${query}` : listingsEndpoint,
          {
            headers: { Accept: "application/json" },
            signal: abort.signal,
          }
        );
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (!abort.signal.aborted) {
          setState({ status: "ready", items: payload || [], error: null });
        }
      } catch (error) {
        if (!abort.signal.aborted) {
          console.error("Impossible de charger les listings", error);
          setState({ status: "error", items: [], error });
        }
      }
    }
    load();
    return () => abort.abort();
  }, [filters, listingsEndpoint]);

  const hasActiveFilters = useMemo(
    () =>
      Boolean(
        filters.search || filters.minPerformance || filters.maxRisk || filters.maxPrice || filters.sort !== "created_desc"
      ),
    [filters]
  );

  function handleInputChange(event) {
    const { name, value } = event.target;
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  function resetFilters() {
    setFilters({ search: "", minPerformance: "", maxRisk: "", maxPrice: "", sort: "created_desc" });
  }

  return (
    <div className="marketplace">
      <header className="marketplace__header">
        <h1 className="heading heading--xl">{t("Marketplace de stratégies")}</h1>
        <p className="text text--muted">
          {t("Comparez les stratégies publiées selon la performance, le profil de risque et le budget.")}
        </p>
      </header>

      <section className="marketplace__filters" aria-label={t("Filtres de recherche")}>
        <form
          className="marketplace-filters"
          onSubmit={(event) => {
            event.preventDefault();
          }}
        >
          <div className="marketplace-filters__row">
            <label className="marketplace-filters__field">
              <span className="marketplace-filters__label">{t("Rechercher")}</span>
              <input
                type="search"
                name="search"
                value={filters.search}
                onChange={handleInputChange}
                placeholder={t("Nom de stratégie")}
                className="input"
              />
            </label>
            <label className="marketplace-filters__field">
              <span className="marketplace-filters__label">{t("Performance min.")}</span>
              <input
                type="number"
                step="0.1"
                min="0"
                name="minPerformance"
                value={filters.minPerformance}
                onChange={handleInputChange}
                className="input"
              />
            </label>
            <label className="marketplace-filters__field">
              <span className="marketplace-filters__label">{t("Risque max.")}</span>
              <input
                type="number"
                step="0.1"
                min="0"
                name="maxRisk"
                value={filters.maxRisk}
                onChange={handleInputChange}
                className="input"
              />
            </label>
            <label className="marketplace-filters__field">
              <span className="marketplace-filters__label">{t("Prix max. (USD)")}</span>
              <input
                type="number"
                min="0"
                name="maxPrice"
                value={filters.maxPrice}
                onChange={handleInputChange}
                className="input"
              />
            </label>
            <label className="marketplace-filters__field">
              <span className="marketplace-filters__label">{t("Tri")}</span>
              <select name="sort" value={filters.sort} onChange={handleInputChange} className="input">
                {sortOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="marketplace-filters__actions">
            <button type="button" className="button button--ghost" onClick={resetFilters} disabled={!hasActiveFilters}>
              {t("Réinitialiser")}
            </button>
          </div>
        </form>
      </section>

      <section className="marketplace__results" aria-live="polite">
        {state.status === "loading" && <p className="text">{t("Chargement des listings…")}</p>}
        {state.status === "error" && (
          <p className="text text--critical">{t("Impossible de récupérer les listings pour le moment.")}</p>
        )}
        {state.status === "ready" && state.items.length === 0 && (
          <p className="text text--muted">{t("Aucune stratégie ne correspond à vos filtres.")}</p>
        )}
        {state.status === "ready" && state.items.length > 0 && (
          <div className="marketplace-grid" role="list">
            {state.items.map((listing) => (
              <ListingCard
                key={listing.id}
                listing={listing}
                reviewsEndpoint={reviewsEndpointTemplate.replace("__id__", String(listing.id))}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

export default MarketplaceApp;
