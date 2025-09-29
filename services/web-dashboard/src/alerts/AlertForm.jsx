import React, { useEffect, useState } from "react";

const DEFAULT_FORM = {
  title: "",
  detail: "",
  risk: "info",
  acknowledged: false,
};

const RISK_OPTIONS = [
  { value: "info", label: "Information" },
  { value: "warning", label: "Avertissement" },
  { value: "critical", label: "Critique" },
];

function AlertForm({ mode, initialAlert, onSubmit, onCancel, submitting, error }) {
  const [formData, setFormData] = useState(() => ({
    ...DEFAULT_FORM,
    ...(initialAlert ? normaliseInitial(initialAlert) : {}),
  }));

  useEffect(() => {
    setFormData({
      ...DEFAULT_FORM,
      ...(initialAlert ? normaliseInitial(initialAlert) : {}),
    });
  }, [initialAlert, mode]);

  function normaliseInitial(alert) {
    if (!alert) {
      return {};
    }
    return {
      title: alert.title || "",
      detail: alert.detail || "",
      risk: typeof alert.risk === "string" ? alert.risk : alert.risk?.value || "info",
      acknowledged: Boolean(alert.acknowledged),
    };
  }

  function handleChange(event) {
    const { name, value, type, checked } = event.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (!formData.title.trim() || !formData.detail.trim()) {
      return;
    }
    onSubmit?.({
      title: formData.title.trim(),
      detail: formData.detail.trim(),
      risk: formData.risk,
      acknowledged: Boolean(formData.acknowledged),
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
