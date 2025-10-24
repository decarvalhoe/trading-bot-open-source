import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import TradingViewPanel from "../components/TradingViewPanel.jsx";
import { bootstrap } from "../bootstrap";

export default function MarketPage() {
  const { t } = useTranslation();
  const marketConfig = bootstrap?.config?.market || {};
  const tradingConfig = bootstrap?.config?.trading || {};
  const defaultWatchlist = marketConfig.watchlist || tradingConfig.watchlist || [
    "BTCUSDT",
    "ETHUSDT",
    "EURUSD",
    "SPX500USD",
  ];

  const watchlist = useMemo(() => {
    if (!Array.isArray(defaultWatchlist)) {
      return ["BTCUSDT", "ETHUSDT", "EURUSD", "SPX500USD"];
    }
    const unique = Array.from(new Set(defaultWatchlist.filter((entry) => typeof entry === "string" && entry.trim())));
    return unique.length ? unique : ["BTCUSDT", "ETHUSDT", "EURUSD", "SPX500USD"];
  }, [defaultWatchlist]);

  const configEndpoint = marketConfig.tradingViewConfigEndpoint || tradingConfig.tradingViewConfigEndpoint || "/config/tradingview";
  const updateEndpoint = marketConfig.tradingViewUpdateEndpoint || tradingConfig.tradingViewUpdateEndpoint || "/config/tradingview";
  const initialSymbol = marketConfig.defaultSymbol || tradingConfig.defaultSymbol || watchlist[0] || "BTCUSDT";
  const [symbol, setSymbol] = useState(initialSymbol);
  const [customSymbol, setCustomSymbol] = useState("");

  const handleCustomSubmit = (event) => {
    event.preventDefault();
    if (!customSymbol.trim()) {
      return;
    }
    setSymbol(customSymbol.trim().toUpperCase());
    setCustomSymbol("");
  };

  return (
    <div className="market-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Surveillance du marché")}</h1>
        <p className="text text--muted">
          {t("Visualisez vos actifs clés, comparez les tendances et affinez vos décisions de trading en direct.")}
        </p>
      </header>

      <section className="market-controls" aria-labelledby="market-watchlist-title">
        <h2 id="market-watchlist-title" className="heading heading--lg">
          {t("Sélection rapide")}
        </h2>
        <div className="watchlist-controls">
          <label className="form-field">
            <span className="form-field__label">{t("Symboles favoris")}</span>
            <select value={symbol} onChange={(event) => setSymbol(event.target.value)}>
              {watchlist.map((entry) => (
                <option key={entry} value={entry}>
                  {entry}
                </option>
              ))}
            </select>
          </label>
          <form className="form-inline" onSubmit={handleCustomSubmit}>
            <label className="form-field">
              <span className="form-field__label">{t("Symbole personnalisé")}</span>
              <input
                type="text"
                value={customSymbol}
                onChange={(event) => setCustomSymbol(event.target.value)}
                placeholder={t("Exemple : AAPL, BTCUSDT")}
              />
            </label>
            <button type="submit" className="button">
              {t("Afficher")}
            </button>
          </form>
        </div>
      </section>

      <section className="market-chart" aria-labelledby="market-chart-title">
        <h2 id="market-chart-title" className="visually-hidden">
          {t("Graphique TradingView")}
        </h2>
        <TradingViewPanel
          symbol={symbol}
          onSymbolChange={(next) => setSymbol(next)}
          configEndpoint={configEndpoint}
          updateEndpoint={updateEndpoint}
        />
      </section>
    </div>
  );
}
