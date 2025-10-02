import React, { useMemo, useState } from "react";
import PropTypes from "prop-types";

import { indicatorSuggestions, predefinedPrompts } from "./prompts";

function toggleValue(values, candidate) {
  if (values.includes(candidate)) {
    return values.filter((value) => value !== candidate);
  }
  return [...values, candidate];
}

function parseTags(rawValue) {
  if (!rawValue) {
    return [];
  }
  return rawValue
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

export default function AIStrategyAssistant({
  generateEndpoint = "/strategies/generate",
  importEndpoint = "/strategies/import/assistant",
}) {
  const [formState, setFormState] = useState({
    prompt: "",
    selectedPrompt: "",
    preferredFormat: "yaml",
    riskProfile: "",
    timeframe: "",
    capital: "",
    indicators: [],
    notes: "",
  });
  const [status, setStatus] = useState({ state: "idle" });
  const [draft, setDraft] = useState(null);
  const [yamlContent, setYamlContent] = useState("");
  const [pythonContent, setPythonContent] = useState("");
  const [importName, setImportName] = useState("");
  const [importTags, setImportTags] = useState("");
  const [importEnabled, setImportEnabled] = useState(false);
  const [importStatus, setImportStatus] = useState({ state: "idle" });

  const indicatorChips = useMemo(
    () =>
      indicatorSuggestions.map((indicator) => ({
        label: indicator,
        selected: formState.indicators.includes(indicator),
      })),
    [formState.indicators],
  );

  async function handleSubmit(event) {
    event.preventDefault();
    setStatus({ state: "loading" });
    setImportStatus({ state: "idle" });

    const body = {
      prompt: formState.prompt,
      preferred_format: formState.preferredFormat,
      risk_profile: formState.riskProfile || undefined,
      timeframe: formState.timeframe || undefined,
      capital: formState.capital || undefined,
      indicators: formState.indicators,
      notes: formState.notes || undefined,
    };

    try {
      const response = await fetch(generateEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${response.status}`);
      }
      const payload = await response.json();
      setDraft(payload.draft);
      setYamlContent(payload.draft.yaml || "");
      setPythonContent(payload.draft.python || "");
      setImportName(payload.draft.metadata?.suggested_name || "");
      setStatus({ state: "ready" });
    } catch (error) {
      console.error("Impossible de générer la stratégie", error);
      setStatus({ state: "error", message: error.message });
    }
  }

  function handlePromptSelection(event) {
    const newPrompt = event.target.value;
    const predefined = predefinedPrompts.find((item) => item.id === newPrompt);
    setFormState((prev) => ({
      ...prev,
      selectedPrompt: newPrompt,
      prompt: predefined ? predefined.prompt : prev.prompt,
    }));
  }

  function handleIndicatorClick(indicator) {
    setFormState((prev) => ({
      ...prev,
      indicators: toggleValue(prev.indicators, indicator),
    }));
  }

  async function importDraft(format) {
    const content = format === "yaml" ? yamlContent : pythonContent;
    if (!content || content.trim().length === 0) {
      setImportStatus({ state: "error", message: "Contenu vide." });
      return;
    }
    setImportStatus({ state: "loading" });

    const body = {
      format,
      content,
      enabled: importEnabled,
      tags: parseTags(importTags),
    };
    if (importName.trim().length > 0) {
      body.name = importName.trim();
    }
    if (draft && draft.metadata) {
      body.metadata = draft.metadata;
    }

    try {
      const response = await fetch(importEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${response.status}`);
      }
      const created = await response.json();
      setImportStatus({ state: "success", strategy: created });
    } catch (error) {
      console.error("Import impossible", error);
      setImportStatus({ state: "error", message: error.message });
    }
  }

  return (
    <section className="ai-strategy-assistant">
      <h2>Assistant IA pour stratégies</h2>
      <p className="assistant__intro">
        Décrivez votre idée ou sélectionnez un prompt prédéfini pour générer un brouillon de
        stratégie au format YAML ou Python. Vous pouvez ensuite l'affiner avant de l'importer.
      </p>

      <form className="assistant__form" onSubmit={handleSubmit}>
        <div className="assistant__field">
          <label htmlFor="assistant-prompt-select">Prompts prédéfinis</label>
          <select
            id="assistant-prompt-select"
            value={formState.selectedPrompt}
            onChange={handlePromptSelection}
          >
            <option value="">Choisir un prompt…</option>
            {predefinedPrompts.map((prompt) => (
              <option key={prompt.id} value={prompt.id}>
                {prompt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="assistant__field">
          <label htmlFor="assistant-prompt">Description de la stratégie</label>
          <textarea
            id="assistant-prompt"
            value={formState.prompt}
            onChange={(event) =>
              setFormState((prev) => ({ ...prev, prompt: event.target.value }))
            }
            rows={4}
            placeholder="Ex: Détecter les cassures de tendance sur BTC avec confirmation du volume"
            required
          />
        </div>

        <div className="assistant__field">
          <label htmlFor="assistant-format">Format souhaité</label>
          <select
            id="assistant-format"
            value={formState.preferredFormat}
            onChange={(event) =>
              setFormState((prev) => ({ ...prev, preferredFormat: event.target.value }))
            }
          >
            <option value="yaml">YAML</option>
            <option value="python">Python</option>
            <option value="both">Les deux</option>
          </select>
        </div>

        <div className="assistant__grid">
          <div className="assistant__field">
            <label htmlFor="assistant-risk">Profil de risque</label>
            <input
              id="assistant-risk"
              type="text"
              value={formState.riskProfile}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, riskProfile: event.target.value }))
              }
              placeholder="Ex: modéré"
            />
          </div>
          <div className="assistant__field">
            <label htmlFor="assistant-timeframe">Timeframe</label>
            <input
              id="assistant-timeframe"
              type="text"
              value={formState.timeframe}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, timeframe: event.target.value }))
              }
              placeholder="Ex: 1h"
            />
          </div>
          <div className="assistant__field">
            <label htmlFor="assistant-capital">Capital</label>
            <input
              id="assistant-capital"
              type="text"
              value={formState.capital}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, capital: event.target.value }))
              }
              placeholder="Ex: 10 000 €"
            />
          </div>
        </div>

        <fieldset className="assistant__field">
          <legend>Indicateurs suggérés</legend>
          <div className="assistant__chips">
            {indicatorChips.map((chip) => (
              <button
                type="button"
                key={chip.label}
                className={chip.selected ? "assistant__chip assistant__chip--active" : "assistant__chip"}
                onClick={() => handleIndicatorClick(chip.label)}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="assistant__field">
          <label htmlFor="assistant-notes">Contraintes supplémentaires</label>
          <textarea
            id="assistant-notes"
            value={formState.notes}
            onChange={(event) =>
              setFormState((prev) => ({ ...prev, notes: event.target.value }))
            }
            rows={3}
            placeholder="Ex: Limiter le drawdown à 5%, privilégier les signaux multi-timeframe"
          />
        </div>

        <button className="assistant__submit" type="submit" disabled={status.state === "loading"}>
          {status.state === "loading" ? "Génération en cours…" : "Générer la stratégie"}
        </button>
        {status.state === "error" && <p className="assistant__error">{status.message}</p>}
      </form>

      {draft && (
        <section className="assistant__results">
          <h3>Proposition générée</h3>
          <p className="assistant__summary">{draft.summary}</p>
          {draft.warnings && draft.warnings.length > 0 && (
            <ul className="assistant__warnings">
              {draft.warnings.map((warning, index) => (
                <li key={index}>{warning}</li>
              ))}
            </ul>
          )}

          {draft.indicators && draft.indicators.length > 0 && (
            <p className="assistant__indicators">
              Indicateurs recommandés : <strong>{draft.indicators.join(", ")}</strong>
            </p>
          )}

          {draft.yaml !== null && (
            <div className="assistant__editor">
              <label htmlFor="assistant-yaml">Définition YAML</label>
              <textarea
                id="assistant-yaml"
                rows={12}
                value={yamlContent}
                onChange={(event) => setYamlContent(event.target.value)}
              />
            </div>
          )}

          {draft.python !== null && (
            <div className="assistant__editor">
              <label htmlFor="assistant-python">Implémentation Python</label>
              <textarea
                id="assistant-python"
                rows={12}
                value={pythonContent}
                onChange={(event) => setPythonContent(event.target.value)}
              />
            </div>
          )}

          <div className="assistant__import">
            <h4>Importer dans l'algo engine</h4>
            <div className="assistant__field">
              <label htmlFor="assistant-name">Nom de la stratégie</label>
              <input
                id="assistant-name"
                type="text"
                value={importName}
                onChange={(event) => setImportName(event.target.value)}
                placeholder="Ex: Breakout AI"
              />
            </div>
            <div className="assistant__field">
              <label htmlFor="assistant-tags">Tags (séparés par des virgules)</label>
              <input
                id="assistant-tags"
                type="text"
                value={importTags}
                onChange={(event) => setImportTags(event.target.value)}
                placeholder="momentum, IA"
              />
            </div>
            <label className="assistant__checkbox">
              <input
                type="checkbox"
                checked={importEnabled}
                onChange={(event) => setImportEnabled(event.target.checked)}
              />
              Activer immédiatement la stratégie
            </label>

            <div className="assistant__buttons">
              {draft.yaml !== null && (
                <button type="button" onClick={() => importDraft("yaml")}>
                  Importer la version YAML
                </button>
              )}
              {draft.python !== null && (
                <button type="button" onClick={() => importDraft("python")}>
                  Importer la version Python
                </button>
              )}
            </div>
            {importStatus.state === "loading" && <p>Import en cours…</p>}
            {importStatus.state === "error" && (
              <p className="assistant__error">{importStatus.message}</p>
            )}
            {importStatus.state === "success" && (
              <p className="assistant__success">
                Stratégie importée avec l'identifiant {importStatus.strategy.id}.
              </p>
            )}
          </div>
        </section>
      )}
    </section>
  );
}

AIStrategyAssistant.propTypes = {
  generateEndpoint: PropTypes.string,
  importEndpoint: PropTypes.string,
};
