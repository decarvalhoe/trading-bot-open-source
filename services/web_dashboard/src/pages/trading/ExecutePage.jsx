import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import useApi from "../../hooks/useApi.js";
import TradingViewPanel from "../../components/TradingViewPanel.jsx";
import { bootstrap } from "../../bootstrap";

const ORDER_TYPES = [
  { value: "market", label: "Au marché" },
  { value: "limit", label: "Limite" },
  { value: "stop", label: "Stop" },
];

const SIDES = [
  { value: "buy", label: "Achat" },
  { value: "sell", label: "Vente" },
];

function buildInitialForm() {
  const tradingConfig = bootstrap?.config?.trading || {};
  const defaults = tradingConfig.executionDefaults || {};
  return {
    symbol: defaults.symbol || "BTCUSDT",
    venue: defaults.venue || "binance", // keep compatibility with execution API
    broker: defaults.broker || "paper", // default alias for sandbox broker
    side: defaults.side || "buy",
    orderType: defaults.orderType || "limit",
    quantity: defaults.quantity ?? 0.01,
    price: defaults.price ?? 0,
    timeInForce: defaults.timeInForce || "GTC",
  };
}

export default function ExecutePage() {
  const { t } = useTranslation();
  const { orders, useMutation } = useApi();
  const [form, setForm] = useState(() => buildInitialForm());
  const [statusMessage, setStatusMessage] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const requiresPrice = useMemo(() => form.orderType === "limit" || form.orderType === "stop", [form.orderType]);

  const mutation = useMutation({
    mutationFn: async (payload) => orders.create(payload),
    onSuccess: (report) => {
      setStatusMessage(report?.status || t("Ordre soumis avec succès."));
      setErrorMessage(null);
    },
    onError: (error) => {
      setStatusMessage(null);
      setErrorMessage(error?.message || t("Impossible de transmettre l'ordre."));
    },
  });

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((previous) => ({
      ...previous,
      [name]: name === "quantity" || name === "price" ? Number.parseFloat(value || "0") : value,
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setStatusMessage(null);
    setErrorMessage(null);

    const payload = {
      symbol: form.symbol,
      venue: form.venue,
      broker: form.broker,
      side: form.side,
      order_type: form.orderType,
      quantity: Number(form.quantity),
      time_in_force: form.timeInForce,
    };

    if (requiresPrice) {
      payload.limit_price = Number(form.price);
    }

    try {
      await mutation.mutateAsync(payload);
    } catch (error) {
      // handled in onError
    }
  };

  return (
    <div className="execute-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Exécution manuelle")}</h1>
        <p className="text text--muted">
          {t("Soumettez un ordre ponctuel vers le routeur pour déclencher une exécution contrôlée.")}
        </p>
      </header>

      <div className="execute-layout">
        <section className="execute-layout__form" aria-labelledby="execution-form-title">
          <h2 id="execution-form-title" className="heading heading--lg">
            {t("Paramètres de l'ordre")}
          </h2>
          <form className="form" onSubmit={handleSubmit}>
            <div className="form-grid">
              <label className="form-field">
                <span className="form-field__label">{t("Symbole")}</span>
                <input
                  type="text"
                  name="symbol"
                  value={form.symbol}
                  onChange={handleChange}
                  placeholder="BTCUSDT"
                />
              </label>
              <label className="form-field">
                <span className="form-field__label">{t("Broker")}</span>
                <input
                  type="text"
                  name="broker"
                  value={form.broker}
                  onChange={handleChange}
                  placeholder="paper"
                />
              </label>
              <label className="form-field">
                <span className="form-field__label">{t("Venue")}</span>
                <input
                  type="text"
                  name="venue"
                  value={form.venue}
                  onChange={handleChange}
                  placeholder="binance"
                />
              </label>
              <label className="form-field">
                <span className="form-field__label">{t("Direction")}</span>
                <select name="side" value={form.side} onChange={handleChange}>
                  {SIDES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {t(option.label)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span className="form-field__label">{t("Type d'ordre")}</span>
                <select name="orderType" value={form.orderType} onChange={handleChange}>
                  {ORDER_TYPES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {t(option.label)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span className="form-field__label">{t("Quantité")}</span>
                <input
                  type="number"
                  name="quantity"
                  min="0"
                  step="0.0001"
                  value={form.quantity}
                  onChange={handleChange}
                />
              </label>
              {requiresPrice ? (
                <label className="form-field">
                  <span className="form-field__label">{t("Prix")}</span>
                  <input
                    type="number"
                    name="price"
                    min="0"
                    step="0.0001"
                    value={form.price}
                    onChange={handleChange}
                  />
                </label>
              ) : null}
              <label className="form-field">
                <span className="form-field__label">{t("Time in force")}</span>
                <input
                  type="text"
                  name="timeInForce"
                  value={form.timeInForce}
                  onChange={handleChange}
                  placeholder="GTC"
                />
              </label>
            </div>
            <button type="submit" className="button button--primary" disabled={mutation.isLoading}>
              {mutation.isLoading ? t("Envoi en cours…") : t("Envoyer l'ordre")}
            </button>
          </form>
          {statusMessage ? (
            <p className="text text--success" role="status">
              {statusMessage}
            </p>
          ) : null}
          {errorMessage ? (
            <p className="text text--critical" role="alert">
              {errorMessage}
            </p>
          ) : null}
        </section>
        <section className="execute-layout__chart" aria-labelledby="execution-chart-title">
          <h2 id="execution-chart-title" className="heading heading--lg">
            {t("Analyse graphique")}
          </h2>
          <TradingViewPanel symbol={form.symbol} onSymbolChange={(next) => setForm((current) => ({ ...current, symbol: next }))} />
        </section>
      </div>
    </div>
  );
}
