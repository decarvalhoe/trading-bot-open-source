import React from "react";
import { useTranslation } from "react-i18next";
import useApi from "../../hooks/useApi.js";
import { bootstrap } from "../../bootstrap";

function normalisePortfolios(entries) {
  if (!Array.isArray(entries)) {
    return [];
  }
  return entries.map((portfolio, index) => ({
    id: portfolio.id || `portfolio-${index}`,
    name: portfolio.name || portfolio.id || `Portefeuille #${index + 1}`,
    owner: portfolio.owner || portfolio.account_id || "",
    totalValue: portfolio.total_value ?? portfolio.totalValue ?? 0,
    holdings: Array.isArray(portfolio.holdings) ? portfolio.holdings : [],
  }));
}

function formatNumber(value, options = {}) {
  if (value == null || Number.isNaN(Number(value))) {
    return "-";
  }
  return new Intl.NumberFormat("fr-FR", options).format(Number(value));
}

function formatDate(value, locale = "fr-FR") {
  if (!value) {
    return null;
  }
  try {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return typeof value === "string" ? value : String(value);
    }
    return parsed.toLocaleString(locale, {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (error) {
    return typeof value === "string" ? value : String(value);
  }
}

export default function PositionsPage() {
  const { t, i18n } = useTranslation();
  const { dashboard, useQuery } = useApi();
  const tradingConfig = bootstrap?.config?.trading || {};
  const dashboardConfig = bootstrap?.config?.dashboard || {};
  const contextEndpoint =
    tradingConfig.positionsEndpoint ||
    dashboardConfig.positionsEndpoint ||
    dashboardConfig.contextEndpoint ||
    "/dashboard/context";

  const {
    data = { portfolios: [], asOf: null },
    isLoading,
    isError,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["positions", contextEndpoint],
    queryFn: async () => {
      const payload = await dashboard.context({ endpoint: contextEndpoint });
      return {
        portfolios: normalisePortfolios(payload?.portfolios),
        asOf: payload?.as_of || payload?.timestamp || payload?.updated_at || null,
      };
    },
  });

  const portfolios = normalisePortfolios(data.portfolios);
  const asOf = data.asOf;

  return (
    <div className="positions-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Portefeuilles et positions")}</h1>
        <p className="text text--muted">
          {t("Surveillez votre exposition agrégée par portefeuille et contrôlez la valorisation en cours.")}
        </p>
        <div className="page-header__actions">
          <button type="button" className="button" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? t("Actualisation…") : t("Rafraîchir")}
          </button>
        </div>
      </header>

      {asOf ? (
        <p className="text text--muted">
          {t("Instantané arrêté au {{date}}", { date: formatDate(asOf, i18n.language) })}
        </p>
      ) : null}

      {isLoading ? (
        <p className="text" role="status">
          {t("Chargement des positions en cours…")}
        </p>
      ) : null}

      {isError ? (
        <p className="text text--critical" role="alert">
          {t("Impossible de récupérer les positions pour le moment.")}
        </p>
      ) : null}

      <div className="positions-grid">
        {portfolios.map((portfolio) => (
          <article key={portfolio.id} className="positions-card">
            <header className="positions-card__header">
              <h2 className="heading heading--lg">{portfolio.name}</h2>
              {portfolio.owner ? <p className="text text--muted">{portfolio.owner}</p> : null}
              <p className="heading heading--md">
                {t("Valeur totale : {{value}}", {
                  value: formatNumber(portfolio.totalValue, { style: "currency", currency: "USD" }),
                })}
              </p>
            </header>
            {portfolio.holdings.length ? (
              <div className="table-responsive">
                <table className="table table--dense" role="grid">
                  <thead>
                    <tr>
                      <th scope="col">{t("Symbole")}</th>
                      <th scope="col">{t("Quantité")}</th>
                      <th scope="col">{t("Prix moyen")}</th>
                      <th scope="col">{t("Prix courant")}</th>
                      <th scope="col">{t("Valeur de marché")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.holdings.map((holding) => (
                      <tr key={holding.id || `${portfolio.id}-${holding.symbol}`}> 
                        <td data-label={t("Symbole")}>{holding.symbol || "-"}</td>
                        <td data-label={t("Quantité")}>{formatNumber(holding.quantity, { maximumFractionDigits: 6 })}</td>
                        <td data-label={t("Prix moyen")}>
                          {formatNumber(holding.average_price, { style: "currency", currency: "USD" })}
                        </td>
                        <td data-label={t("Prix courant")}>
                          {formatNumber(holding.current_price, { style: "currency", currency: "USD" })}
                        </td>
                        <td data-label={t("Valeur de marché")}>
                          {formatNumber(holding.market_value, { style: "currency", currency: "USD" })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text text--muted">{t("Aucune position ouverte pour ce portefeuille.")}</p>
            )}
          </article>
        ))}
      </div>

      {!isLoading && !isError && portfolios.length === 0 ? (
        <p className="text text--muted">{t("Aucun portefeuille disponible pour le moment.")}</p>
      ) : null}
    </div>
  );
}
