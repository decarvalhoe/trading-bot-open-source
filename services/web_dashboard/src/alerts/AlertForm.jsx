import React, { useEffect, useState } from "react";

const BASE_CHANNELS = [
  { type: "email", target: "", enabled: false },
  { type: "push", target: "", enabled: false },
  { type: "webhook", target: "", enabled: false },
];

function createDefaultForm() {
  return {
    title: "",
    detail: "",
    risk: "info",
    acknowledged: false,
    rule: {
      symbol: "",
      timeframe: "",
      conditions: {
        pnl: { enabled: false, operator: "below", value: "" },
        drawdown: { enabled: false, operator: "above", value: "" },
        indicators: [],
      },
    },
    channels: BASE_CHANNELS.map((channel) => ({ ...channel })),
    throttle_minutes: 0,
  };
}

const RISK_OPTIONS = [
  { value: "info", label: "Information" },
  { value: "warning", label: "Avertissement" },
  { value: "critical", label: "Critique" },
];

function AlertForm({ mode, initialAlert, onSubmit, onCancel, submitting, error }) {
  const [formData, setFormData] = useState(() => {
    const base = createDefaultForm();
    if (!initialAlert) {
      return base;
    }
    return { ...base, ...normaliseInitial(initialAlert) };
  });

  useEffect(() => {
    setFormData(() => {
      const base = createDefaultForm();
      if (!initialAlert) {
        return base;
      }
      return { ...base, ...normaliseInitial(initialAlert) };
    });
  }, [initialAlert, mode]);

  function normaliseInitial(alert) {
    if (!alert) {
      return createDefaultForm();
    }
    const risk = typeof alert.risk === "string" ? alert.risk : alert.risk?.value || "info";
    const defaultForm = createDefaultForm();
    const rule =
      alert.rule && typeof alert.rule === "object" ? alert.rule : defaultForm.rule;
    const conditions = rule.conditions || defaultForm.rule.conditions;
    const normalisedChannels = Array.isArray(alert.channels)
      ? alert.channels.map((channel) => ({
          type: channel?.type || "email",
          target: channel?.target || "",
          enabled: channel?.enabled !== undefined ? Boolean(channel.enabled) : true,
        }))
      : defaultForm.channels;
    return {
      title: alert.title || "",
      detail: alert.detail || "",
      risk,
      acknowledged: Boolean(alert.acknowledged),
      rule: {
        symbol: rule.symbol || alert.symbol || "",
        timeframe: rule.timeframe || "",
        conditions: {
          pnl: {
            enabled: Boolean(conditions?.pnl?.enabled),
            operator: conditions?.pnl?.operator || "below",
            value:
              conditions?.pnl?.value !== undefined && conditions?.pnl?.value !== null
                ? String(conditions.pnl.value)
                : "",
          },
          drawdown: {
            enabled: Boolean(conditions?.drawdown?.enabled),
            operator: conditions?.drawdown?.operator || "above",
            value:
              conditions?.drawdown?.value !== undefined && conditions?.drawdown?.value !== null
                ? String(conditions.drawdown.value)
                : "",
          },
          indicators: Array.isArray(conditions?.indicators)
            ? conditions.indicators.map((indicator, index) => ({
                id: indicator.id || `indicator-${index}`,
                name: indicator.name || "RSI",
                operator: indicator.operator || "above",
                value:
                  indicator.value !== undefined && indicator.value !== null
                    ? String(indicator.value)
                    : "",
                lookback:
                  indicator.lookback !== undefined && indicator.lookback !== null
                    ? String(indicator.lookback)
                    : "",
                enabled:
                  indicator.enabled !== undefined ? Boolean(indicator.enabled) : true,
              }))
            : [],
        },
      },
      channels: normalisedChannels,
      throttle_minutes: Math.max(
        0,
        Math.round(Number(alert.throttle_seconds || alert.throttleMinutes || 0) / 60),
      ),
    };
  }

  function handleChange(event) {
    const { name, value, type, checked } = event.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  }

  function handleRuleFieldChange(field, value) {
    setFormData((prev) => ({
      ...prev,
      rule: {
        ...prev.rule,
        [field]: value,
      },
    }));
  }

  function handlePerformanceChange(metric, field, value) {
    setFormData((prev) => ({
      ...prev,
      rule: {
        ...prev.rule,
        conditions: {
          ...prev.rule.conditions,
          [metric]: {
            ...prev.rule.conditions[metric],
            [field]: field === "enabled" ? Boolean(value) : value,
          },
        },
      },
    }));
  }

  function handleIndicatorChange(index, field, value) {
    setFormData((prev) => {
      const indicators = prev.rule.conditions.indicators || [];
      const updated = indicators.map((indicator, i) => {
        if (i !== index) {
          return indicator;
        }
        return {
          ...indicator,
          [field]: field === "enabled" ? Boolean(value) : value,
        };
      });
      return {
        ...prev,
        rule: {
          ...prev.rule,
          conditions: {
            ...prev.rule.conditions,
            indicators: updated,
          },
        },
      };
    });
  }

  function handleAddIndicator() {
    setFormData((prev) => ({
      ...prev,
      rule: {
        ...prev.rule,
        conditions: {
          ...prev.rule.conditions,
          indicators: [
            ...prev.rule.conditions.indicators,
            {
              id: `indicator-${Math.random().toString(36).slice(2)}`,
              name: "RSI",
              operator: "below",
              value: "30",
              lookback: "14",
              enabled: true,
            },
          ],
        },
      },
    }));
  }

  function handleRemoveIndicator(index) {
    setFormData((prev) => ({
      ...prev,
      rule: {
        ...prev.rule,
        conditions: {
          ...prev.rule.conditions,
          indicators: prev.rule.conditions.indicators.filter((_, i) => i !== index),
        },
      },
    }));
  }

  function handleChannelToggle(index, field, value) {
    setFormData((prev) => ({
      ...prev,
      channels: prev.channels.map((channel, i) =>
        i === index ? { ...channel, [field]: field === "enabled" ? Boolean(value) : value } : channel,
      ),
    }));
  }

  function handleThrottleChange(value) {
    const minutes = Math.max(0, Number.isNaN(Number(value)) ? 0 : Number(value));
    setFormData((prev) => ({
      ...prev,
      throttle_minutes: minutes,
    }));
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (!formData.title.trim() || !formData.detail.trim()) {
      return;
    }
    const cleanedIndicators = (formData.rule.conditions.indicators || []).map((indicator) => ({
      id: indicator.id || `indicator-${Math.random().toString(36).slice(2)}`,
      name: indicator.name || "RSI",
      operator: indicator.operator || "below",
      value: indicator.value !== "" && indicator.value !== null ? Number(indicator.value) : 0,
      lookback:
        indicator.lookback !== "" && indicator.lookback !== null
          ? Number(indicator.lookback)
          : null,
      enabled: indicator.enabled !== undefined ? Boolean(indicator.enabled) : true,
    }));
    const payload = {
      title: formData.title.trim(),
      detail: formData.detail.trim(),
      risk: formData.risk,
      acknowledged: Boolean(formData.acknowledged),
      rule: {
        symbol: formData.rule.symbol.trim(),
        timeframe: formData.rule.timeframe ? formData.rule.timeframe.trim() : null,
        conditions: {
          pnl: {
            enabled: Boolean(formData.rule.conditions.pnl.enabled),
            operator: formData.rule.conditions.pnl.operator || "below",
            value:
              formData.rule.conditions.pnl.value !== "" &&
              formData.rule.conditions.pnl.value !== null
                ? Number(formData.rule.conditions.pnl.value)
                : null,
          },
          drawdown: {
            enabled: Boolean(formData.rule.conditions.drawdown.enabled),
            operator: formData.rule.conditions.drawdown.operator || "above",
            value:
              formData.rule.conditions.drawdown.value !== "" &&
              formData.rule.conditions.drawdown.value !== null
                ? Number(formData.rule.conditions.drawdown.value)
                : null,
          },
          indicators: cleanedIndicators,
        },
      },
      channels: formData.channels.map((channel) => ({
        type: channel.type,
        target: channel.target ? channel.target.trim() : null,
        enabled: Boolean(channel.enabled),
      })),
      throttle_seconds: Math.max(0, Math.round(Number(formData.throttle_minutes) * 60)),
    };
    if (!payload.rule.symbol) {
      return;
    }
    onSubmit?.({
      ...payload,
    });
  }

  return (
    <form className="alerts-form" onSubmit={handleSubmit}>
      <fieldset className="alerts-form__fieldset" disabled={submitting}>
        <legend className="sr-only">{mode === "edit" ? "Modifier l'alerte" : "Créer une alerte"}</legend>
        <div className="alerts-form__field">
          <label htmlFor="alert-title">Titre</label>
          <input
            id="alert-title"
            name="title"
            type="text"
            value={formData.title}
            onChange={handleChange}
            required
            placeholder="Synthèse de l'alerte"
          />
        </div>
        <div className="alerts-form__field">
          <label htmlFor="alert-detail">Description</label>
          <textarea
            id="alert-detail"
            name="detail"
            rows={3}
            value={formData.detail}
            onChange={handleChange}
            required
            placeholder="Détails permettant d'agir"
          />
        </div>
        <div className="alerts-form__row">
          <div className="alerts-form__field">
            <label htmlFor="alert-risk">Niveau de risque</label>
            <select id="alert-risk" name="risk" value={formData.risk} onChange={handleChange}>
              {RISK_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="alerts-form__checkbox">
            <label>
              <input
                type="checkbox"
                name="acknowledged"
                checked={formData.acknowledged}
                onChange={handleChange}
              />
              <span>Accusée</span>
            </label>
          </div>
        </div>

        <fieldset className="alerts-form__group">
          <legend>Définition de la règle</legend>
          <div className="alerts-form__field">
            <label htmlFor="alert-symbol">Symbole surveillé</label>
            <input
              id="alert-symbol"
              name="rule.symbol"
              type="text"
              value={formData.rule.symbol}
              onChange={(event) => handleRuleFieldChange("symbol", event.target.value)}
              required
              placeholder="ex: BTCUSDT"
            />
          </div>
          <div className="alerts-form__field">
            <label htmlFor="alert-timeframe">Période (optionnelle)</label>
            <input
              id="alert-timeframe"
              name="rule.timeframe"
              type="text"
              value={formData.rule.timeframe}
              onChange={(event) => handleRuleFieldChange("timeframe", event.target.value)}
              placeholder="ex: 1h"
            />
          </div>

          <div className="alerts-form__conditions">
            <h4 className="heading heading--sm">Conditions de performance</h4>
            <div className="alerts-form__row">
              <label className="alerts-form__checkbox">
                <input
                  type="checkbox"
                  checked={formData.rule.conditions.pnl.enabled}
                  onChange={(event) => handlePerformanceChange("pnl", "enabled", event.target.checked)}
                />
                <span>Activer P&L</span>
              </label>
              <select
                value={formData.rule.conditions.pnl.operator}
                onChange={(event) => handlePerformanceChange("pnl", "operator", event.target.value)}
                disabled={!formData.rule.conditions.pnl.enabled}
              >
                <option value="above">Supérieur ou égal</option>
                <option value="below">Inférieur ou égal</option>
              </select>
              <input
                type="number"
                step="0.01"
                value={formData.rule.conditions.pnl.value}
                onChange={(event) => handlePerformanceChange("pnl", "value", event.target.value)}
                placeholder="Seuil P&L"
                disabled={!formData.rule.conditions.pnl.enabled}
              />
            </div>
            <div className="alerts-form__row">
              <label className="alerts-form__checkbox">
                <input
                  type="checkbox"
                  checked={formData.rule.conditions.drawdown.enabled}
                  onChange={(event) =>
                    handlePerformanceChange("drawdown", "enabled", event.target.checked)
                  }
                />
                <span>Activer drawdown</span>
              </label>
              <select
                value={formData.rule.conditions.drawdown.operator}
                onChange={(event) =>
                  handlePerformanceChange("drawdown", "operator", event.target.value)
                }
                disabled={!formData.rule.conditions.drawdown.enabled}
              >
                <option value="above">Supérieur ou égal</option>
                <option value="below">Inférieur ou égal</option>
              </select>
              <input
                type="number"
                step="0.01"
                value={formData.rule.conditions.drawdown.value}
                onChange={(event) => handlePerformanceChange("drawdown", "value", event.target.value)}
                placeholder="Seuil drawdown"
                disabled={!formData.rule.conditions.drawdown.enabled}
              />
            </div>
          </div>

          <div className="alerts-form__indicators">
            <div className="alerts-form__indicators-header">
              <h4 className="heading heading--sm">Indicateurs techniques</h4>
              <button type="button" className="button button--ghost" onClick={handleAddIndicator}>
                Ajouter un indicateur
              </button>
            </div>
            {formData.rule.conditions.indicators.length === 0 ? (
              <p className="text text--muted">Aucun indicateur configuré.</p>
            ) : (
              <ul className="alerts-form__indicator-list">
                {formData.rule.conditions.indicators.map((indicator, index) => (
                  <li key={indicator.id || index} className="alerts-form__indicator-item">
                    <div className="alerts-form__row">
                      <label className="alerts-form__checkbox">
                        <input
                          type="checkbox"
                          checked={indicator.enabled !== false}
                          onChange={(event) =>
                            handleIndicatorChange(index, "enabled", event.target.checked)
                          }
                        />
                        <span>Actif</span>
                      </label>
                      <input
                        type="text"
                        value={indicator.name}
                        onChange={(event) => handleIndicatorChange(index, "name", event.target.value)}
                        placeholder="RSI"
                      />
                      <select
                        value={indicator.operator}
                        onChange={(event) =>
                          handleIndicatorChange(index, "operator", event.target.value)
                        }
                      >
                        <option value="above">Supérieur ou égal</option>
                        <option value="below">Inférieur ou égal</option>
                      </select>
                      <input
                        type="number"
                        step="0.01"
                        value={indicator.value}
                        onChange={(event) => handleIndicatorChange(index, "value", event.target.value)}
                        placeholder="Valeur"
                      />
                      <input
                        type="number"
                        step="1"
                        value={indicator.lookback}
                        onChange={(event) =>
                          handleIndicatorChange(index, "lookback", event.target.value)
                        }
                        placeholder="Période"
                      />
                      <button
                        type="button"
                        className="button button--danger"
                        onClick={() => handleRemoveIndicator(index)}
                      >
                        Retirer
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </fieldset>

        <fieldset className="alerts-form__group">
          <legend>Canaux de notification</legend>
          {formData.channels.map((channel, index) => (
            <div className="alerts-form__row" key={channel.type}>
              <label className="alerts-form__checkbox">
                <input
                  type="checkbox"
                  checked={channel.enabled}
                  onChange={(event) => handleChannelToggle(index, "enabled", event.target.checked)}
                />
                <span>{channel.type === "webhook" ? "Webhook" : channel.type === "push" ? "Push" : "Email"}</span>
              </label>
              <input
                type="text"
                value={channel.target}
                onChange={(event) => handleChannelToggle(index, "target", event.target.value)}
                placeholder={
                  channel.type === "webhook"
                    ? "https://example.com/webhook"
                    : channel.type === "push"
                    ? "Identifiant de device"
                    : "destinataire@domaine.com"
                }
              />
            </div>
          ))}
        </fieldset>

        <div className="alerts-form__field">
          <label htmlFor="alert-throttle">Fréquence minimale entre deux notifications (minutes)</label>
          <input
            id="alert-throttle"
            type="number"
            min="0"
            step="1"
            value={formData.throttle_minutes}
            onChange={(event) => handleThrottleChange(event.target.value)}
          />
        </div>

        {error ? (
          <p className="alerts-form__error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="alerts-form__actions">
          <button type="submit" className="button button--primary">
            {mode === "edit" ? "Mettre à jour" : "Créer"}
          </button>
          {mode === "edit" ? (
            <button type="button" className="button button--secondary" onClick={onCancel}>
              Annuler
            </button>
          ) : null}
        </div>
      </fieldset>
    </form>
  );
}

export default AlertForm;
