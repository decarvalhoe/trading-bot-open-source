import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import BlockPalette from "./BlockPalette.jsx";
import DesignerCanvas from "./DesignerCanvas.jsx";
import { BLOCK_DEFINITIONS, cloneDefaultConfig } from "./designerConstants.js";
import { buildExports, deserializeStrategy } from "./serializer.js";
import { STRATEGY_PRESETS, findPresetById } from "./presets.js";

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

function serializeNode(node) {
  return {
    type: node.type,
    config: node.config,
    children: Array.isArray(node.children)
      ? node.children.map((child) => serializeNode(child))
      : [],
  };
}

function hydrateNode(serialized, idRef) {
  const definition = BLOCK_DEFINITIONS[serialized.type];
  return {
    id: `node-${idRef.current++}`,
    type: serialized.type,
    label: definition ? definition.label : serialized.type,
    config: serialized.config ? { ...serialized.config } : cloneDefaultConfig(serialized.type),
    children: Array.isArray(serialized.children)
      ? serialized.children.map((child) => hydrateNode(child, idRef))
      : [],
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

function insertAfter(nodes, nodeId, newNode) {
  const index = nodes.findIndex((node) => node.id === nodeId);
  if (index !== -1) {
    const next = nodes.slice();
    next.splice(index + 1, 0, newNode);
    return next;
  }

  let changed = false;
  const mapped = nodes.map((node) => {
    if (node.children && node.children.length) {
      const updatedChildren = insertAfter(node.children, nodeId, newNode);
      if (updatedChildren !== node.children) {
        changed = true;
        return { ...node, children: updatedChildren };
      }
    }
    return node;
  });
  return changed ? mapped : nodes;
}

function computeLayout(nodes, depth = 0, startRow = 1, map = {}) {
  let row = startRow;
  nodes.forEach((node) => {
    map[node.id] = { row, column: depth };
    row += 1;
    if (node.children && node.children.length) {
      const childLayout = computeLayout(node.children, depth + 1, row, map);
      row = childLayout.nextRow;
    }
  });
  return { map, nextRow: row };
}

function normalizeSelection(state, selection) {
  if (!selection) {
    return null;
  }
  const nodes = state[selection.section];
  if (!nodes) {
    return null;
  }
  if (!selection.nodeId) {
    return selection;
  }
  return findNode(nodes, selection.nodeId) ? selection : null;
}

function historyPush(history, nextPresent) {
  const presentString = JSON.stringify(history.present);
  const nextString = JSON.stringify(nextPresent);
  if (presentString === nextString) {
    return history;
  }
  return {
    past: [...history.past, history.present],
    present: nextPresent,
    future: [],
  };
}

function historyUndo(history) {
  if (!history.past.length) {
    return history;
  }
  const previous = history.past[history.past.length - 1];
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future],
  };
}

function historyRedo(history) {
  if (!history.future.length) {
    return history;
  }
  const [next, ...rest] = history.future;
  return {
    past: [...history.past, history.present],
    present: next,
    future: rest,
  };
}

const initialHistory = {
  past: [],
  present: { conditions: [], actions: [] },
  future: [],
};

function designerReducer(state, action) {
  switch (action.type) {
    case "APPLY": {
      const nextPresent = action.updater(state.history.present);
      const nextHistory = historyPush(state.history, nextPresent);
      if (nextHistory === state.history) {
        return state;
      }
      return {
        ...state,
        history: nextHistory,
        selection: normalizeSelection(nextHistory.present, state.selection),
      };
    }
    case "SET_PRESENT": {
      const nextHistory = {
        past: action.resetHistory ? [] : state.history.past,
        present: action.present,
        future: [],
      };
      return {
        ...state,
        history: nextHistory,
        selection: normalizeSelection(action.present, state.selection),
      };
    }
    case "UNDO": {
      const history = historyUndo(state.history);
      if (history === state.history) {
        return state;
      }
      return {
        ...state,
        history,
        selection: normalizeSelection(history.present, state.selection),
      };
    }
    case "REDO": {
      const history = historyRedo(state.history);
      if (history === state.history) {
        return state;
      }
      return {
        ...state,
        history,
        selection: normalizeSelection(history.present, state.selection),
      };
    }
    case "SELECT": {
      return {
        ...state,
        selection: action.selection,
      };
    }
    case "CLEAR_SELECTION": {
      return {
        ...state,
        selection: null,
      };
    }
    case "COPY": {
      if (!state.selection?.nodeId) {
        return state;
      }
      const nodes = state.history.present[state.selection.section];
      const node = findNode(nodes, state.selection.nodeId);
      if (!node) {
        return state;
      }
      return {
        ...state,
        clipboard: JSON.stringify(serializeNode(node)),
      };
    }
    case "CLEAR_CLIPBOARD": {
      return {
        ...state,
        clipboard: null,
      };
    }
    case "SET_CLIPBOARD": {
      return {
        ...state,
        clipboard: action.clipboard,
      };
    }
    default:
      return state;
  }
}

function PresetPalette({ presets, onApply }) {
  if (!Array.isArray(presets) || presets.length === 0) {
    return null;
  }

  return (
    <section className="designer-panel designer-panel--presets" aria-labelledby="presets-title">
      <div className="designer-panel__header">
        <h2 id="presets-title" className="heading heading--md">
          Modèles rapides
        </h2>
        <p className="text text--muted">
          Chargez une base préconfigurée puis personnalisez-la dans la composition.
        </p>
      </div>
      <div className="designer-panel__body" role="list" aria-label="Modèles de stratégies">
        {presets.map((preset) => (
          <article
            key={preset.id}
            className="palette-item palette-item--preset"
            role="listitem"
          >
            <header className="palette-item__header">
              <div>
                <span className="palette-item__title heading heading--sm">{preset.label}</span>
              </div>
              <button
                type="button"
                className="button button--ghost"
                onClick={() => onApply?.(preset.id)}
                data-testid={`preset-apply-${preset.id}`}
              >
                Charger
              </button>
            </header>
            <p className="palette-item__description text">{preset.description}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export default function StrategyDesigner({
  saveEndpoint = "/strategies/save",
  defaultName = "Nouvelle stratégie",
  defaultFormat = "yaml",
  presets = STRATEGY_PRESETS,
  initialStrategy = null,
}) {
  const idRef = useRef(1);
  const initialName = (initialStrategy?.name || "").trim() || defaultName;
  const initialFormatValue =
    initialStrategy?.source_format === "python"
      ? "python"
      : initialStrategy?.format === "python"
      ? "python"
      : defaultFormat === "python"
      ? "python"
      : "yaml";
  const initialStatus = initialStrategy?.status_message
    ? { type: initialStrategy.status_type || "success", message: initialStrategy.status_message }
    : { type: "idle", message: null };
  const [name, setName] = useState(initialName);
  const [format, setFormat] = useState(initialFormatValue);
  const [status, setStatus] = useState(initialStatus);
  const [lastResponse, setLastResponse] = useState(null);
  const [state, dispatch] = useReducer(designerReducer, {
    history: initialHistory,
    selection: null,
    clipboard: null,
  });

  const { conditions, actions } = state.history.present;
  const { selection, clipboard } = state;

  const exports = useMemo(
    () => buildExports(name, conditions, actions),
    [name, conditions, actions]
  );
  const validation = useMemo(
    () => validateStrategy(conditions, actions),
    [conditions, actions]
  );
  const presetList = useMemo(
    () => (Array.isArray(presets) ? presets : []),
    [presets]
  );
  const fileInputRef = useRef(null);
  const createNodeId = useCallback(() => `node-${idRef.current++}`, []);
  const initialHydrationRef = useRef(false);

  const applyChange = useCallback(
    (mutator) => {
      dispatch({
        type: "APPLY",
        updater: (present) => {
          const next = mutator(present);
          if (!next) {
            return present;
          }
          const nextConditions = Array.isArray(next.conditions)
            ? next.conditions
            : present.conditions;
          const nextActions = Array.isArray(next.actions) ? next.actions : present.actions;
          if (nextConditions === present.conditions && nextActions === present.actions) {
            return present;
          }
          return { conditions: nextConditions, actions: nextActions };
        },
      });
    },
    [dispatch]
  );

  const setPresent = useCallback(
    (present, { resetHistory = false } = {}) => {
      dispatch({ type: "SET_PRESENT", present, resetHistory });
    },
    [dispatch]
  );

  const clearTransientState = useCallback(() => {
    dispatch({ type: "CLEAR_SELECTION" });
    dispatch({ type: "CLEAR_CLIPBOARD" });
  }, [dispatch]);

  const applyHydrationResult = useCallback(
    (result, successMessage, fallbackName = "") => {
      const hasErrors = !result || (Array.isArray(result.errors) && result.errors.length > 0);
      if (hasErrors) {
        const message = result?.errors?.length
          ? result.errors.join(" ")
          : "Impossible d'importer la stratégie fournie.";
        setStatus({ type: "error", message });
        return false;
      }

      const nextPresent = {
        conditions: Array.isArray(result.conditions) ? result.conditions : [],
        actions: Array.isArray(result.actions) ? result.actions : [],
      };
      setPresent(nextPresent, { resetHistory: true });
      setFormat(result.format === "python" ? "python" : "yaml");
      const resolvedName = (result.name || "").trim() || (fallbackName || "").trim();
      if (resolvedName) {
        setName(resolvedName);
      }
      setLastResponse(null);
      setStatus({ type: "success", message: successMessage });
      clearTransientState();
      return true;
    },
    [clearTransientState, setPresent]
  );

  const handlePresetApply = useCallback(
    (presetId) => {
      const preset =
        presetList.find((item) => item.id === presetId) || findPresetById(presetId);
      if (!preset) {
        setStatus({ type: "error", message: "Modèle introuvable." });
        return;
      }
      const result = deserializeStrategy({
        code: preset.content,
        format: preset.format,
        createId: createNodeId,
      });
      applyHydrationResult(result, `Modèle « ${preset.label} » chargé.`, preset.label);
    },
    [applyHydrationResult, presetList, createNodeId]
  );

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelected = async (event) => {
    const { files } = event.target;
    const file = files && files[0];
    if (!file) {
      return;
    }

    const extension = file.name.split(".").pop()?.toLowerCase();
    let inferredFormat = "yaml";
    if (extension === "py" || file.type.includes("python")) {
      inferredFormat = "python";
    } else if (extension === "yaml" || extension === "yml") {
      inferredFormat = "yaml";
    }

    try {
      const content = await file.text();
      const result = deserializeStrategy({
        code: content,
        format: inferredFormat,
        createId: createNodeId,
      });
      const fallbackName = file.name.replace(/\.[^.]+$/, "").trim();
      applyHydrationResult(result, `Fichier « ${file.name} » importé.`, fallbackName);
    } catch (error) {
      setStatus({
        type: "error",
        message: "Impossible de lire le fichier sélectionné.",
      });
    } finally {
      if (event.target) {
        event.target.value = "";
      }
    }
  };

  useEffect(() => {
    if (!initialStrategy || initialHydrationRef.current) {
      return;
    }
    initialHydrationRef.current = true;

    const strategyCode =
      typeof initialStrategy.source === "string" ? initialStrategy.source : null;
    const strategyFormatRaw =
      typeof initialStrategy.source_format === "string"
        ? initialStrategy.source_format
        : typeof initialStrategy.format === "string"
        ? initialStrategy.format
        : null;
    const fallbackName = (initialStrategy.name || "").toString();
    const statusMessage =
      typeof initialStrategy.status_message === "string"
        ? initialStrategy.status_message
        : null;
    const statusType =
      typeof initialStrategy.status_type === "string"
        ? initialStrategy.status_type
        : "success";

    if (strategyCode && strategyFormatRaw) {
      const result = deserializeStrategy({
        code: strategyCode,
        format: strategyFormatRaw,
        createId: createNodeId,
      });
      const successMessage =
        statusMessage ||
        (fallbackName
          ? `Stratégie « ${fallbackName} » chargée.`
          : "Stratégie clonée chargée.");
      const applied = applyHydrationResult(result, successMessage, fallbackName);
      if (!applied && statusMessage) {
        setStatus({ type: statusType, message: statusMessage });
      }
    } else {
      if (fallbackName) {
        setName(fallbackName);
      }
      if (statusMessage) {
        setStatus({ type: statusType, message: statusMessage });
      }
      if (strategyFormatRaw) {
        setFormat(strategyFormatRaw === "python" ? "python" : "yaml");
      }
    }
  }, [initialStrategy, applyHydrationResult, createNodeId]);

  const handleSelect = useCallback(
    (nextSelection) => {
      if (!nextSelection) {
        dispatch({ type: "CLEAR_SELECTION" });
      } else {
        dispatch({ type: "SELECT", selection: nextSelection });
      }
    },
    [dispatch]
  );

  const handleDrop = useCallback(
    ({ section, targetId, type }) => {
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
      if (
        targetId &&
        (!parent || !BLOCK_DEFINITIONS[parent.type]?.accepts?.includes(type))
      ) {
        setStatus({
          type: "error",
          message: "La cible ne peut pas contenir ce type de bloc.",
        });
        return;
      }

      const item = createNode(type, idRef);
      applyChange((present) => ({
        ...present,
        [section]: appendNode(present[section], targetId, item),
      }));
      handleSelect({ section, nodeId: item.id });
      setStatus({ type: "idle", message: null });
    },
    [actions, applyChange, conditions, handleSelect]
  );

  const handleAdd = ({ section, type }) => {
    handleDrop({ section, targetId: null, type });
  };

  const handleConfigChange = useCallback(
    ({ section, nodeId, config }) => {
      applyChange((present) => ({
        ...present,
        [section]: updateNode(present[section], nodeId, (node) => ({
          ...node,
          config,
        })),
      }));
      setStatus({ type: "idle", message: null });
    },
    [applyChange]
  );

  const handleRemove = useCallback(
    ({ section, nodeId }) => {
      applyChange((present) => ({
        ...present,
        [section]: removeNode(present[section], nodeId),
      }));
      setStatus({ type: "idle", message: null });
    },
    [applyChange]
  );

  const copySelection = useCallback(
    (target) => {
      if (target) {
        handleSelect(target);
      }
      const current = target || selection;
      if (current?.nodeId) {
        dispatch({ type: "COPY" });
        setStatus({ type: "idle", message: null });
      }
    },
    [dispatch, handleSelect, selection]
  );

  const parseClipboard = useCallback(() => {
    if (!clipboard) {
      return null;
    }
    try {
      return JSON.parse(clipboard);
    } catch (error) {
      return null;
    }
  }, [clipboard]);

  const handlePaste = useCallback(
    ({ section, nodeId } = {}) => {
      const payload = parseClipboard();
      if (!payload) {
        setStatus({ type: "error", message: "Presse-papiers vide ou invalide." });
        return;
      }
      const target = section
        ? { section, nodeId }
        : selection || { section: "conditions", nodeId: null };
      const targetSection = target.section || "conditions";
      const definition = BLOCK_DEFINITIONS[payload.type];
      if (!definition) {
        setStatus({ type: "error", message: "Bloc inconnu dans le presse-papiers." });
        return;
      }
      if (targetSection === "conditions" && definition.category !== "conditions") {
        setStatus({ type: "error", message: "Ce bloc ne peut pas être collé dans les conditions." });
        return;
      }
      if (targetSection === "actions" && definition.category !== "actions") {
        setStatus({ type: "error", message: "Ce bloc ne peut pas être collé dans les actions." });
        return;
      }

      let created = null;
      let inserted = false;
      const createClone = () => {
        if (!created) {
          created = hydrateNode(payload, idRef);
        }
        return created;
      };

      applyChange((present) => {
        const source = present[targetSection] || [];
        if (target.nodeId) {
          const parent = findNode(source, target.nodeId);
          const accepts = BLOCK_DEFINITIONS[parent?.type]?.accepts || [];
          if (parent && accepts.includes(payload.type)) {
            inserted = true;
            const clone = createClone();
            return {
              ...present,
              [targetSection]: appendNode(source, target.nodeId, clone),
            };
          }
        }
        inserted = true;
        const clone = createClone();
        return {
          ...present,
          [targetSection]: [...source, clone],
        };
      });

      if (created && inserted) {
        handleSelect({ section: targetSection, nodeId: created.id });
        setStatus({ type: "idle", message: null });
      } else if (!inserted) {
        setStatus({ type: "error", message: "Impossible de coller le bloc ici." });
      }
    },
    [applyChange, handleSelect, parseClipboard, selection]
  );

  const handleDuplicate = useCallback(
    ({ section, nodeId }) => {
      const pool = section === "actions" ? actions : conditions;
      const original = findNode(pool, nodeId);
      if (!original) {
        return;
      }
      const serialized = serializeNode(original);
      let created = null;
      let inserted = false;
      applyChange((present) => {
        const source = present[section] || [];
        const clone = hydrateNode(serialized, idRef);
        created = clone;
        const next = insertAfter(source, nodeId, clone);
        if (next !== source) {
          inserted = true;
          return {
            ...present,
            [section]: next,
          };
        }
        inserted = true;
        return {
          ...present,
          [section]: [...source, clone],
        };
      });
      if (created && inserted) {
        handleSelect({ section, nodeId: created.id });
        dispatch({ type: "SET_CLIPBOARD", clipboard: JSON.stringify(serialized) });
        setStatus({ type: "idle", message: null });
      }
    },
    [actions, applyChange, conditions, dispatch, handleSelect]
  );

  const handleSectionFocus = useCallback(
    (section) => {
      handleSelect({ section, nodeId: null });
    },
    [handleSelect]
  );

  const handleClearSelection = useCallback(() => {
    dispatch({ type: "CLEAR_SELECTION" });
  }, [dispatch]);

  const canUndo = state.history.past.length > 0;
  const canRedo = state.history.future.length > 0;
  const hasClipboard = Boolean(clipboard);

  const handleUndo = useCallback(() => {
    if (canUndo) {
      dispatch({ type: "UNDO" });
    }
  }, [canUndo, dispatch]);

  const handleRedo = useCallback(() => {
    if (canRedo) {
      dispatch({ type: "REDO" });
    }
  }, [canRedo, dispatch]);

  useEffect(() => {
    const handleKeyDown = (event) => {
      const isMod = event.metaKey || event.ctrlKey;
      if (!isMod) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "z") {
        event.preventDefault();
        if (event.shiftKey) {
          handleRedo();
        } else {
          handleUndo();
        }
        return;
      }
      if (key === "y") {
        event.preventDefault();
        handleRedo();
        return;
      }
      if (key === "c") {
        if (selection?.nodeId) {
          event.preventDefault();
          copySelection();
        }
        return;
      }
      if (key === "v") {
        if (hasClipboard) {
          event.preventDefault();
          handlePaste();
        }
        return;
      }
      if (key === "d") {
        if (selection?.nodeId) {
          event.preventDefault();
          handleDuplicate(selection);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [copySelection, handleDuplicate, handlePaste, handleRedo, handleUndo, hasClipboard, selection]);

  const layoutMap = useMemo(() => {
    const base = computeLayout(conditions);
    const combined = computeLayout(actions, 0, base.nextRow, base.map);
    return combined.map;
  }, [actions, conditions]);

  const validationState = validation.errors.length
    ? "error"
    : validation.warnings.length
    ? "warning"
    : "success";

  const handleSave = async (event) => {
    event.preventDefault();
    if (!validation.isValid) {
      setStatus({
        type: "error",
        message: "Corrigez la configuration avant d'enregistrer.",
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
          <button
            type="button"
            className="button button--ghost"
            onClick={handleImportClick}
            data-testid="designer-import-button"
          >
            Importer un fichier
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".yaml,.yml,.py,.json,.txt"
            style={{ display: "none" }}
            onChange={handleFileSelected}
            data-testid="designer-file-input"
          />
          <button
            type="button"
            className="button button--ghost"
            onClick={handleUndo}
            disabled={!canUndo}
            data-testid="designer-undo-button"
          >
            Annuler
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={handleRedo}
            disabled={!canRedo}
            data-testid="designer-redo-button"
          >
            Rétablir
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={() => handlePaste()}
            disabled={!hasClipboard}
            data-testid="designer-paste-button"
          >
            Coller
          </button>
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
        <div className="designer-sidebar">
          <PresetPalette presets={presetList} onApply={handlePresetApply} />
          <BlockPalette onAdd={handleAdd} />
        </div>
        <DesignerCanvas
          conditions={conditions}
          actions={actions}
          layout={layoutMap}
          selection={selection}
          clipboardAvailable={hasClipboard}
          onDrop={handleDrop}
          onConfigChange={handleConfigChange}
          onRemove={handleRemove}
          onSelect={handleSelect}
          onSectionFocus={handleSectionFocus}
          onCopy={copySelection}
          onPaste={handlePaste}
          onDuplicate={handleDuplicate}
          onClearSelection={handleClearSelection}
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
