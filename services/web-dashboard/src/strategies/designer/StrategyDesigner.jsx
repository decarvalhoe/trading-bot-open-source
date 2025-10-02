import React, { useMemo, useRef, useState } from "react";
import BlockPalette from "./BlockPalette.jsx";
import DesignerCanvas from "./DesignerCanvas.jsx";
import { BLOCK_DEFINITIONS, cloneDefaultConfig } from "./designerConstants.js";
import { buildExports } from "./serializer.js";

const INDICATOR_TYPES = new Set(
  Object.keys(BLOCK_DEFINITIONS).filter((type) => type.startsWith("indicator"))
);

const OPERATOR_SIGNS = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  eq: "=",
  neq: "≠",
};

function asNumber(value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }
  const numeric = Number(value);
  return Number.isNaN(numeric) ? null : numeric;
}

function checkRequirements(node, definition, path, errors) {
  const validation = definition?.validation || {};
  const config = node?.config || {};
  const children = Array.isArray(node?.children) ? node.children : [];

  const requirements = Array.isArray(validation.required) ? validation.required : [];
  for (const requirement of requirements) {
    const field = typeof requirement === "string" ? requirement : requirement.field;
    const label =
      typeof requirement === "string"
        ? requirement
        : requirement.label || requirement.field || requirement.toString();
    const value = config[field];
    const isEmpty =
      value === undefined ||
      value === null ||
      (typeof value === "string" && value.trim() === "");
    if (isEmpty) {
      errors.push(`${path} — ${definition.label}: le champ « ${label} » est requis.`);
    }
  }

  if (
    typeof validation.minChildren === "number" &&
    children.length < validation.minChildren
  ) {
    errors.push(
      `${path} — ${definition.label}: au moins ${validation.minChildren} bloc(s) enfant sont requis.`
    );
  }

  if (
    typeof validation.maxChildren === "number" &&
    children.length > validation.maxChildren
  ) {
    errors.push(
      `${path} — ${definition.label}: maximum ${validation.maxChildren} bloc(s) enfant autorisés.`
    );
  }

  if (Array.isArray(definition.accepts)) {
    if (definition.accepts.length === 0 && children.length) {
      errors.push(`${path} — ${definition.label}: n'accepte pas de bloc enfant.`);
    } else if (definition.accepts.length > 0) {
      children.forEach((child, index) => {
        if (!definition.accepts.includes(child.type)) {
          const childLabel = BLOCK_DEFINITIONS[child.type]?.label || child.type;
          errors.push(
            `${path} — ${definition.label}: le bloc enfant #${index + 1} (${childLabel}) est incompatible.`
          );
        }
      });
    }
  }

  return children;
}

function validateIndicatorNode(node, path, errors) {
  const definition = BLOCK_DEFINITIONS[node.type];
  if (!definition) {
    errors.push(`${path}: type d'indicateur inconnu (${node.type}).`);
    return null;
  }
  checkRequirements(node, definition, path, errors);
  const config = node.config || {};

  switch (node.type) {
    case "indicator": {
      const kind = (config.kind || "sma").toUpperCase();
      const source = config.source || "source";
      const period = config.period || "?";
      return `${kind}(${source}, ${period})`;
    }
    case "indicator_macd": {
      const source = config.source || "source";
      return `MACD(${source}, ${config.fastPeriod || "?"}, ${config.slowPeriod || "?"}, ${
        config.signalPeriod || "?"
      })`;
    }
    case "indicator_bollinger": {
      const source = config.source || "source";
      return `BOLL(${source}, ${config.period || "?"}, ${config.deviation || "?"})`;
    }
    case "indicator_atr": {
      const source = config.source || "hlc3";
      return `ATR(${source}, ${config.period || "?"}, ${config.smoothing || "?"})`;
    }
    default:
      errors.push(`${path}: type d'indicateur non géré (${node.type}).`);
      return null;
  }
}

function validateConditionNode(node, path, errors) {
  const definition = BLOCK_DEFINITIONS[node.type];
  if (!definition) {
    errors.push(`${path}: type de condition inconnu (${node.type}).`);
    return null;
  }
  const children = checkRequirements(node, definition, path, errors);
  const config = node.config || {};

  switch (node.type) {
    case "condition": {
      let field = config.field || "champ";
      const indicatorChild = children.find((child) => INDICATOR_TYPES.has(child.type));
      if (indicatorChild) {
        const indicatorExpression = validateIndicatorNode(
          indicatorChild,
          `${path} > ${BLOCK_DEFINITIONS[indicatorChild.type]?.label || indicatorChild.type}`,
          errors
        );
        if (indicatorExpression) {
          field = indicatorExpression;
        }
      }
      const operator = OPERATOR_SIGNS[config.operator] || config.operator || "?";
      const value = config.value ?? "?";
      return `${field} ${operator} ${value}`;
    }
    case "market_cross": {
      const lookback = asNumber(config.lookback);
      if (lookback === null || lookback <= 0) {
        errors.push(
          `${path} — ${definition.label}: la fenêtre d'observation doit être un entier positif.`
        );
      }
      const [leftChild, rightChild] = children;
      if (leftChild && !INDICATOR_TYPES.has(leftChild.type)) {
        errors.push(
          `${path} — ${definition.label}: seuls des indicateurs peuvent être utilisés.`
        );
      }
      if (rightChild && !INDICATOR_TYPES.has(rightChild.type)) {
        errors.push(
          `${path} — ${definition.label}: seuls des indicateurs peuvent être utilisés.`
        );
      }
      const leftExpr =
        leftChild && INDICATOR_TYPES.has(leftChild.type)
          ? validateIndicatorNode(leftChild, `${path} > Indicateur #1`, errors)
          : null;
      const rightExpr =
        rightChild && INDICATOR_TYPES.has(rightChild.type)
          ? validateIndicatorNode(rightChild, `${path} > Indicateur #2`, errors)
          : null;
      if (!leftExpr || !rightExpr) {
        return null;
      }
      const direction = config.direction === "below" ? "croise sous" : "croise au-dessus";
      const lookbackLabel = config.lookback ? ` (fenêtre ${config.lookback})` : "";
      return `${leftExpr} ${direction} ${rightExpr}${lookbackLabel}`;
    }
    case "market_volume": {
      const numericValue = asNumber(config.value);
      if (numericValue === null || numericValue < 0) {
        errors.push(
          `${path} — ${definition.label}: le seuil de volume doit être un nombre positif.`
        );
      }
      const operator = OPERATOR_SIGNS[config.operator] || config.operator || "?";
      const timeframe = config.timeframe ? ` (${config.timeframe})` : "";
      return `Volume ${operator} ${config.value ?? "?"}${timeframe}`;
    }
    case "logic": {
      const joiner = config.mode === "any" ? " OU " : " ET ";
      const parts = children
        .map((child, index) =>
          validateConditionNode(child, `${path} > Bloc ${index + 1}`, errors)
        )
        .filter(Boolean);
      if (!parts.length) {
        return null;
      }
      return parts.map((part) => `(${part})`).join(joiner);
    }
    case "negation": {
      const [child] = children;
      if (!child) {
        return null;
      }
      const target = validateConditionNode(
        child,
        `${path} > ${BLOCK_DEFINITIONS[child.type]?.label || child.type}`,
        errors
      );
      return target ? `NON (${target})` : null;
    }
    case "group": {
      const parts = children
        .map((child, index) =>
          validateConditionNode(child, `${path} > Bloc ${index + 1}`, errors)
        )
        .filter(Boolean);
      if (!parts.length) {
        return null;
      }
      return `(${parts.join(" ET ")})`;
    }
    default:
      if (INDICATOR_TYPES.has(node.type)) {
        return validateIndicatorNode(node, path, errors);
      }
      errors.push(`${path}: type de condition non géré (${node.type}).`);
      return null;
  }
}

function validateActionNode(node, path, errors, warnings) {
  const definition = BLOCK_DEFINITIONS[node.type];
  if (!definition) {
    errors.push(`${path}: type d'action inconnu (${node.type}).`);
    return null;
  }
  const children = checkRequirements(node, definition, path, errors);
  if (children.length) {
    warnings.push(
      `${path} — ${definition.label}: les blocs enfants seront ignorés lors de l'exécution.`
    );
  }
  const config = node.config || {};

  switch (node.type) {
    case "action": {
      const action = (config.action || "").toUpperCase() || "ACTION";
      return `${action} x${config.size || "?"}`;
    }
    case "take_profit": {
      const valueNumber = asNumber(config.value);
      if (valueNumber === null || valueNumber <= 0) {
        errors.push(
          `${path} — ${definition.label}: renseignez une valeur numérique strictement positive.`
        );
      }
      if (config.size === "custom") {
        const customValue = asNumber(config.customSize);
        if (customValue === null || customValue <= 0) {
          errors.push(
            `${path} — ${definition.label}: la taille personnalisée doit être un nombre positif.`
          );
        }
      }
      const suffix = config.mode === "price" ? " (prix)" : "%";
      let sizeLabel = "";
      if (config.size === "half") {
        sizeLabel = " (50 %)";
      } else if (config.size === "custom") {
        sizeLabel = ` (${config.customSize || "?"})`;
      } else {
        sizeLabel = " (100 %)";
      }
      return `Take-profit ${config.value || "?"}${suffix}${sizeLabel}`;
    }
    case "stop_loss": {
      const valueNumber = asNumber(config.value);
      if (valueNumber === null || valueNumber <= 0) {
        errors.push(
          `${path} — ${definition.label}: renseignez une valeur numérique strictement positive.`
        );
      }
      const suffix = config.mode === "price" ? " (prix)" : "%";
      const trailing = config.trailing ? " (trailing)" : "";
      return `Stop-loss ${config.value || "?"}${suffix}${trailing}`;
    }
    case "close_position": {
      const mapping = {
        all: "Fermer toutes les positions",
        long: "Fermer les positions longues",
        short: "Fermer les positions courtes",
      };
      return mapping[config.side] || `Fermer (${config.side || "?"})`;
    }
    case "alert": {
      return `Alerte ${config.channel || "?"}: ${config.message || "?"}`;
    }
    case "delay": {
      const seconds = asNumber(config.seconds);
      if (seconds === null || seconds < 0) {
        errors.push(
          `${path} — ${definition.label}: le délai doit être un nombre positif.`
        );
      }
      return `Attendre ${config.seconds || "?"}s`;
    }
    default:
      errors.push(`${path}: type d'action non géré (${node.type}).`);
      return null;
  }
}

export function validateStrategy(conditions, actions) {
  const errors = [];
  const warnings = [];

  const conditionDescriptions = [];
  if (!conditions || !conditions.length) {
    errors.push("Ajoutez au moins une condition.");
  } else {
    conditions.forEach((node, index) => {
      const description = validateConditionNode(node, `Condition #${index + 1}`, errors);
      if (description) {
        conditionDescriptions.push(description);
      }
    });
  }

  const actionDescriptions = [];
  if (!actions || !actions.length) {
    errors.push("Ajoutez au moins une action.");
  } else {
    actions.forEach((node, index) => {
      const description = validateActionNode(node, `Action #${index + 1}`, errors, warnings);
      if (description) {
        actionDescriptions.push(description);
      }
    });
  }

  const conditionExpression =
    conditionDescriptions.length === 0
      ? null
      : conditionDescriptions.length === 1
      ? conditionDescriptions[0]
      : conditionDescriptions.map((desc) => `(${desc})`).join(" ET ");

  const actionSummary =
    actionDescriptions.length === 0
      ? null
      : actionDescriptions.join(" puis ");

  const rule =
    conditionExpression && actionSummary
      ? `${conditionExpression} ⇒ ${actionSummary}`
      : null;

  return {
    errors,
    warnings,
    conditionExpression,
    actionSummary,
    rule,
    isValid: errors.length === 0,
  };
}

function createNode(type, idRef) {
  const definition = BLOCK_DEFINITIONS[type];
  return {
    id: `node-${idRef.current++}`,
    type,
    label: definition ? definition.label : type,
    config: cloneDefaultConfig(type),
    children: [],
  };
}

function findNode(nodes, nodeId) {
  for (const node of nodes) {
    if (node.id === nodeId) {
      return node;
    }
    const child = findNode(node.children || [], nodeId);
    if (child) {
      return child;
    }
  }
  return null;
}

function appendNode(nodes, targetId, item) {
  if (!targetId) {
    return [...nodes, item];
  }
  let changed = false;
  const next = nodes.map((node) => {
    if (node.id === targetId) {
      changed = true;
      const children = Array.isArray(node.children) ? [...node.children, item] : [item];
      return { ...node, children };
    }
    if (node.children && node.children.length) {
      const updatedChildren = appendNode(node.children, targetId, item);
      if (updatedChildren !== node.children) {
        changed = true;
        return { ...node, children: updatedChildren };
      }
    }
    return node;
  });
  return changed ? next : nodes;
}

function updateNode(nodes, nodeId, updater) {
  let changed = false;
  const next = nodes.map((node) => {
    if (node.id === nodeId) {
      changed = true;
      return updater(node);
    }
    if (node.children && node.children.length) {
      const updatedChildren = updateNode(node.children, nodeId, updater);
      if (updatedChildren !== node.children) {
        changed = true;
        return { ...node, children: updatedChildren };
      }
    }
    return node;
  });
  return changed ? next : nodes;
}

function removeNode(nodes, nodeId) {
  let changed = false;
  const filtered = [];
  for (const node of nodes) {
    if (node.id === nodeId) {
      changed = true;
      continue;
    }
    let current = node;
    if (node.children && node.children.length) {
      const updatedChildren = removeNode(node.children, nodeId);
      if (updatedChildren !== node.children) {
        current = { ...node, children: updatedChildren };
        changed = true;
      }
    }
    filtered.push(current);
  }
  return changed ? filtered : nodes;
}

export default function StrategyDesigner({
  defaultName = "Nouvelle stratégie",
  defaultFormat = "yaml",
  saveEndpoint = "/strategies/save",
}) {
  const idRef = useRef(1);
  const [name, setName] = useState(defaultName);
  const [format, setFormat] = useState(defaultFormat === "python" ? "python" : "yaml");
  const [conditions, setConditions] = useState([]);
  const [actions, setActions] = useState([]);
  const [status, setStatus] = useState({ type: "idle", message: null });
  const [lastResponse, setLastResponse] = useState(null);

  const exports = useMemo(
    () => buildExports(name, conditions, actions),
    [name, conditions, actions]
  );
  const validation = useMemo(
    () => validateStrategy(conditions, actions),
    [conditions, actions]
  );

  const handleDrop = ({ section, targetId, type }) => {
    const definition = BLOCK_DEFINITIONS[type];
    if (!definition) {
      setStatus({ type: "error", message: "Type de bloc inconnu." });
      return;
    }
    if (section === "conditions" && definition.category !== "conditions") {
      setStatus({ type: "error", message: "Ce bloc ne peut pas être utilisé dans les conditions." });
      return;
    }
    if (section === "actions" && definition.category !== "actions") {
      setStatus({ type: "error", message: "Ce bloc ne peut pas être utilisé dans les actions." });
      return;
    }

    const collection = section === "conditions" ? conditions : actions;
    const parent = targetId ? findNode(collection, targetId) : null;
    if (targetId && (!parent || !BLOCK_DEFINITIONS[parent.type]?.accepts?.includes(type))) {
      setStatus({
        type: "error",
        message: "La cible ne peut pas contenir ce type de bloc.",
      });
      return;
    }

    const node = createNode(type, idRef);
    if (section === "conditions") {
      setConditions((prev) => appendNode(prev, targetId, node));
    } else {
      setActions((prev) => appendNode(prev, targetId, node));
    }
    setStatus({ type: "success", message: `${definition.label} ajouté.` });
  };

  const handleAdd = ({ type, section }) => {
    handleDrop({ section, targetId: null, type });
  };

  const handleConfigChange = ({ section, nodeId, config }) => {
    if (section === "conditions") {
      setConditions((prev) => updateNode(prev, nodeId, (node) => ({ ...node, config })));
    } else {
      setActions((prev) => updateNode(prev, nodeId, (node) => ({ ...node, config })));
    }
  };

  const handleRemove = ({ section, nodeId }) => {
    if (section === "conditions") {
      setConditions((prev) => removeNode(prev, nodeId));
    } else {
      setActions((prev) => removeNode(prev, nodeId));
    }
    setStatus({ type: "info", message: "Bloc supprimé." });
  };

  const handleSave = async (event) => {
    event.preventDefault();
    if (!name.trim()) {
      setStatus({ type: "error", message: "Le nom de la stratégie est obligatoire." });
      return;
    }
    if (validation.errors.length) {
      setStatus({
        type: "error",
        message: "Corrigez les erreurs de configuration avant de sauvegarder.",
      });
      return;
    }
    setStatus({ type: "saving", message: "Enregistrement en cours…" });
    setLastResponse(null);

    const payload = {
      name: name.trim(),
      format,
      code: format === "python" ? exports.python : exports.yaml,
    };

    try {
      const response = await fetch(saveEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        let detail = `Échec de l'enregistrement (HTTP ${response.status}).`;
        try {
          const body = await response.json();
          if (body && body.detail) {
            detail = Array.isArray(body.detail)
              ? body.detail.map((item) => item.msg || item.detail).join("; ")
              : typeof body.detail === "string"
              ? body.detail
              : JSON.stringify(body.detail);
          }
        } catch (error) {
          // ignore JSON parsing errors
        }
        setStatus({ type: "error", message: detail });
        return;
      }

      let data = null;
      try {
        data = await response.json();
      } catch (error) {
        data = null;
      }
      setLastResponse(data);
      setStatus({ type: "success", message: "Stratégie enregistrée avec succès." });
    } catch (error) {
      setStatus({
        type: "error",
        message: "Impossible de contacter le service de sauvegarde des stratégies.",
      });
    }
  };

  const validationState = validation.errors.length
    ? "error"
    : validation.warnings.length
    ? "warning"
    : "success";

  return (
    <form className="strategy-designer" onSubmit={handleSave} aria-labelledby="designer-title">
      <header className="strategy-designer__header">
        <div>
          <h1 id="designer-title" className="heading heading--lg">
            Éditeur de stratégies
          </h1>
          <p className="text text--muted">
            Composez vos règles en glissant-déposant des blocs puis exportez-les vers l'algo-engine.
          </p>
        </div>
        <div className="strategy-designer__actions">
          <label className="designer-field strategy-designer__name-field">
            <span className="designer-field__label text text--muted">Nom de la stratégie</span>
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </label>
          <label className="designer-field strategy-designer__format-field">
            <span className="designer-field__label text text--muted">Format d'export</span>
            <select value={format} onChange={(event) => setFormat(event.target.value)}>
              <option value="yaml">YAML</option>
              <option value="python">Python</option>
            </select>
          </label>
          <button type="submit" className="button button--primary">
            Enregistrer la stratégie
          </button>
        </div>
      </header>

      {status.message ? (
        <div
          className={`designer-status designer-status--${status.type}`}
          role={status.type === "error" ? "alert" : "status"}
          aria-live="polite"
        >
          {status.message}
        </div>
      ) : null}

      <div className="strategy-designer__layout">
        <BlockPalette onAdd={handleAdd} />
        <DesignerCanvas
          conditions={conditions}
          actions={actions}
          onDrop={handleDrop}
          onConfigChange={handleConfigChange}
          onRemove={handleRemove}
        />
        <section
          className="designer-panel designer-panel--validation"
          aria-labelledby="validation-title"
        >
          <div className="designer-panel__header">
            <h2 id="validation-title" className="heading heading--md">
              Validation temps réel
            </h2>
            <p className="text text--muted">
              Contrôlez la cohérence de la règle lors de la composition.
            </p>
          </div>
          <div className="designer-panel__body">
            <div
              className={`designer-validation designer-validation--${validationState}`}
              data-testid="designer-validation"
              role="region"
              aria-live="polite"
            >
              {validation.errors.length ? (
                <>
                  <h3 className="heading heading--sm">Erreurs de configuration</h3>
                  <ul>
                    {validation.errors.map((error, index) => (
                      <li key={index}>{error}</li>
                    ))}
                  </ul>
                  {validation.warnings.length ? (
                    <>
                      <h4 className="heading heading--xs">Avertissements</h4>
                      <ul>
                        {validation.warnings.map((warning, index) => (
                          <li key={`warning-${index}`}>{warning}</li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                </>
              ) : (
                <>
                  <p className="text">
                    Règle valide : vous pouvez sauvegarder ou exporter la stratégie.
                  </p>
                  {validation.rule ? (
                    <p className="text text--muted designer-validation__rule">{validation.rule}</p>
                  ) : null}
                  {validation.warnings.length ? (
                    <>
                      <h4 className="heading heading--xs">Avertissements</h4>
                      <ul>
                        {validation.warnings.map((warning, index) => (
                          <li key={`warning-${index}`}>{warning}</li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                </>
              )}
            </div>
          </div>
        </section>
        <section className="designer-panel designer-panel--preview" aria-labelledby="preview-title">
          <div className="designer-panel__header">
            <h2 id="preview-title" className="heading heading--md">
              Aperçu du code
            </h2>
            <p className="text text--muted">
              Utilisez les onglets YAML / Python pour vérifier le rendu avant sauvegarde.
            </p>
          </div>
          <div className="designer-panel__body">
            <textarea
              className="designer-preview"
              readOnly
              value={format === "python" ? exports.python : exports.yaml}
              data-testid="strategy-preview"
              aria-label={`Aperçu ${format}`}
            />
            {lastResponse ? (
              <details className="designer-response">
                <summary>Réponse du moteur</summary>
                <pre>{JSON.stringify(lastResponse, null, 2)}</pre>
              </details>
            ) : null}
          </div>
        </section>
      </div>
    </form>
  );
}
