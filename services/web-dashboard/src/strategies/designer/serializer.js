import YAML from "yaml";

import { BLOCK_DEFINITIONS, cloneDefaultConfig } from "./designerConstants.js";

const INDICATOR_TYPES = new Set([
  "indicator",
  "indicator_macd",
  "indicator_bollinger",
  "indicator_atr",
]);

function toConditionSchema(node) {
  if (!node) {
    return null;
  }
  if (node.type === "logic") {
    const mode = node.config.mode === "any" ? "any" : "all";
    const children = (node.children || [])
      .map(toConditionSchema)
      .filter((child) => child !== null);
    if (!children.length) {
      return null;
    }
    return { [mode]: children };
  }
  if (node.type === "group") {
    const children = (node.children || [])
      .map(toConditionSchema)
      .filter((child) => child !== null);
    if (!children.length) {
      return null;
    }
    return { all: children };
  }
  if (node.type === "negation") {
    const child = toConditionSchema((node.children || [])[0]);
    if (!child) {
      return null;
    }
    return { not: child };
  }
  if (node.type === "condition") {
    const base = {
      field: node.config.field || "close",
      operator: node.config.operator || "gt",
      value: normalizeValue(node.config.value),
    };
    const indicator = (node.children || []).find((child) => INDICATOR_TYPES.has(child.type));
    if (indicator) {
      base.field = buildIndicatorAlias(indicator.config, indicator.type);
    }
    return base;
  }
  if (node.type === "market_cross") {
    const indicators = (node.children || []).filter((child) => INDICATOR_TYPES.has(child.type));
    if (indicators.length < 2) {
      return null;
    }
    const left = indicators[0];
    const right = indicators[1];
    return {
      cross: {
        left: buildIndicatorAlias(left.config, left.type),
        right: buildIndicatorAlias(right.config, right.type),
        direction: node.config.direction === "below" ? "below" : "above",
        lookback: Number(node.config.lookback) || 1,
      },
    };
  }
  if (node.type === "market_volume") {
    const schema = {
      field: "volume",
      operator: node.config.operator || "gt",
      value: normalizeValue(node.config.value),
    };
    if (node.config.timeframe) {
      schema.timeframe = node.config.timeframe;
    }
    return schema;
  }
  if (INDICATOR_TYPES.has(node.type)) {
    return {
      field: buildIndicatorAlias(node.config, node.type),
      operator: "exists",
      value: true,
    };
  }
  return null;
}

function normalizeValue(value) {
  if (value === undefined || value === null) {
    return null;
  }
  const asNumber = Number(value);
  if (!Number.isNaN(asNumber) && String(value).trim() !== "") {
    return asNumber;
  }
  return value;
}

function buildIndicatorAlias(config = {}, type = "indicator") {
  const source = config.source || "close";
  if (type === "indicator_macd") {
    return `MACD(${source}, ${config.fastPeriod || "12"}, ${config.slowPeriod || "26"}, ${
      config.signalPeriod || "9"
    })`;
  }
  if (type === "indicator_bollinger") {
    return `BOLL(${source}, ${config.period || "20"}, ${config.deviation || "2"})`;
  }
  if (type === "indicator_atr") {
    return `ATR(${config.source || "hlc3"}, ${config.period || "14"}, ${
      config.smoothing || "14"
    })`;
  }
  const kind = (config.kind || "sma").toUpperCase();
  const period = config.period || "20";
  return `${kind}(${source}, ${period})`;
}

function toSignalSchema(nodes) {
  if (!nodes || !nodes.length) {
    return { action: "noop" };
  }
  const steps = [];
  for (const node of nodes) {
    if (node.type === "action") {
      steps.push({
        type: "order",
        action: node.config.action || "buy",
        size: Number(node.config.size) || 1,
      });
    } else if (node.type === "delay") {
      steps.push({ type: "delay", seconds: Number(node.config.seconds) || 0 });
    } else if (node.type === "take_profit") {
      const step = {
        type: "take_profit",
        mode: node.config.mode || "percent",
        value: Number(node.config.value) || 0,
        size: node.config.size || "full",
      };
      if (node.config.size === "custom") {
        step.customSize = Number(node.config.customSize) || 0;
      }
      steps.push(step);
    } else if (node.type === "stop_loss") {
      steps.push({
        type: "stop_loss",
        mode: node.config.mode || "percent",
        value: Number(node.config.value) || 0,
        trailing: Boolean(node.config.trailing),
      });
    } else if (node.type === "close_position") {
      steps.push({
        type: "close_position",
        side: node.config.side || "all",
      });
    } else if (node.type === "alert") {
      steps.push({
        type: "alert",
        channel: node.config.channel || "email",
        message: node.config.message || "",
      });
    }
  }
  const primary = steps.find((step) => step.type === "order");
  const signal = { steps };
  if (primary) {
    signal.action = primary.action;
    signal.size = primary.size;
  }
  if (!signal.action) {
    signal.action = "noop";
  }
  return signal;
}

function collectConditions(nodes) {
  if (!nodes || !nodes.length) {
    return {};
  }
  if (nodes.length === 1) {
    return toConditionSchema(nodes[0]) || {};
  }
  const collected = nodes.map(toConditionSchema).filter((child) => child !== null);
  if (!collected.length) {
    return {};
  }
  return { all: collected };
}

export function buildStrategyDocument(name, conditions, actions) {
  const when = collectConditions(conditions);
  const signal = toSignalSchema(actions);
  return {
    name: name || "Nouvelle stratégie",
    rules: [
      {
        when,
        signal,
      },
    ],
    metadata: {
      editor: "web-dashboard",
    },
  };
}

function createIdFactory(factory) {
  if (typeof factory === "function") {
    return () => factory();
  }
  let counter = 1;
  return () => `node-${counter++}`;
}

function normalizeConfigValue(key, value) {
  if (key === "trailing") {
    return Boolean(value);
  }
  if (value === undefined || value === null) {
    return "";
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
  }
  return String(value);
}

function createHydratedNode(type, configOverrides, children, createId) {
  const baseConfig = cloneDefaultConfig(type);
  const config = { ...baseConfig };
  Object.entries(configOverrides || {}).forEach(([key, value]) => {
    config[key] = normalizeConfigValue(key, value);
  });
  return {
    id: createId(),
    type,
    label: BLOCK_DEFINITIONS[type]?.label || type,
    config,
    children: Array.isArray(children) ? children : [],
  };
}

const MACD_PATTERN = /^MACD\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)$/i;
const BOLL_PATTERN = /^BOLL\(([^,]+),\s*([^,]+),\s*([^)]+)\)$/i;
const ATR_PATTERN = /^ATR\(([^,]+),\s*([^,]+),\s*([^)]+)\)$/i;
const GENERIC_INDICATOR_PATTERN = /^([A-Z0-9_]+)\(([^,]+),\s*([^)]+)\)$/i;

function parseIndicatorAlias(alias) {
  if (typeof alias !== "string") {
    return null;
  }
  const value = alias.trim();
  const macd = value.match(MACD_PATTERN);
  if (macd) {
    return {
      type: "indicator_macd",
      config: {
        source: macd[1].trim(),
        fastPeriod: macd[2].trim(),
        slowPeriod: macd[3].trim(),
        signalPeriod: macd[4].trim(),
      },
    };
  }
  const boll = value.match(BOLL_PATTERN);
  if (boll) {
    return {
      type: "indicator_bollinger",
      config: {
        source: boll[1].trim(),
        period: boll[2].trim(),
        deviation: boll[3].trim(),
      },
    };
  }
  const atr = value.match(ATR_PATTERN);
  if (atr) {
    return {
      type: "indicator_atr",
      config: {
        source: atr[1].trim(),
        period: atr[2].trim(),
        smoothing: atr[3].trim(),
      },
    };
  }
  const generic = value.match(GENERIC_INDICATOR_PATTERN);
  if (generic) {
    return {
      type: "indicator",
      config: {
        kind: generic[1].trim().toLowerCase(),
        source: generic[2].trim(),
        period: generic[3].trim(),
      },
    };
  }
  return null;
}

function hydrateConditionSchema(schema, createId, errors, path = "condition") {
  if (!schema || typeof schema !== "object") {
    errors.push(`${path}: bloc de condition invalide.`);
    return null;
  }

  if (Array.isArray(schema)) {
    if (!schema.length) {
      errors.push(`${path}: la condition est vide.`);
      return null;
    }
    const children = schema
      .map((item, index) => hydrateConditionSchema(item, createId, errors, `${path}[${index}]`))
      .filter(Boolean);
    if (!children.length) {
      return null;
    }
    return createHydratedNode("logic", { mode: "all" }, children, createId);
  }

  if (schema.any || schema.all) {
    const collectionKey = Array.isArray(schema.any) ? "any" : "all";
    const rawChildren = Array.isArray(schema[collectionKey]) ? schema[collectionKey] : [];
    const children = rawChildren
      .map((child, index) =>
        hydrateConditionSchema(child, createId, errors, `${path}.${collectionKey}[${index}]`)
      )
      .filter(Boolean);
    if (!children.length) {
      errors.push(`${path}: aucune sous-condition valide n'a été trouvée.`);
      return null;
    }
    const mode = collectionKey === "any" ? "any" : "all";
    return createHydratedNode("logic", { mode }, children, createId);
  }

  if (schema.not !== undefined) {
    const child = hydrateConditionSchema(schema.not, createId, errors, `${path}.not`);
    if (!child) {
      errors.push(`${path}: la négation n'a pas de bloc valide.`);
      return null;
    }
    return createHydratedNode("negation", {}, [child], createId);
  }

  if (schema.cross) {
    if (!isObject(schema.cross)) {
      errors.push(`${path}: le croisement est mal formé.`);
      return null;
    }
    const { left, right, direction, lookback } = schema.cross;
    const indicatorNodes = [];
    const leftIndicator = parseIndicatorAlias(left);
    if (leftIndicator) {
      indicatorNodes.push(
        createHydratedNode(leftIndicator.type, leftIndicator.config, [], createId)
      );
    } else if (left) {
      errors.push(`${path}: indicateur de gauche inconnu (${left}).`);
    }
    const rightIndicator = parseIndicatorAlias(right);
    if (rightIndicator) {
      indicatorNodes.push(
        createHydratedNode(rightIndicator.type, rightIndicator.config, [], createId)
      );
    } else if (right) {
      errors.push(`${path}: indicateur de droite inconnu (${right}).`);
    }
    if (indicatorNodes.length < 2) {
      errors.push(`${path}: un croisement requiert deux indicateurs valides.`);
    }
    const config = {
      direction: direction === "below" ? "below" : "above",
    };
    if (lookback !== undefined) {
      config.lookback = lookback;
    }
    return createHydratedNode("market_cross", config, indicatorNodes.slice(0, 2), createId);
  }

  if (schema.operator === "exists" && schema.field) {
    const indicator = parseIndicatorAlias(schema.field);
    if (indicator) {
      return createHydratedNode(indicator.type, indicator.config, [], createId);
    }
  }

  if (schema.field && typeof schema.field === "string") {
    if (schema.field.trim().toLowerCase() === "volume") {
      const config = {
        operator: schema.operator || "gt",
        value: schema.value,
        timeframe: schema.timeframe,
      };
      return createHydratedNode("market_volume", config, [], createId);
    }
    const indicator = parseIndicatorAlias(schema.field);
    const children = [];
    const config = {
      field: schema.field,
      operator: schema.operator || "gt",
      value: schema.value,
    };
    if (indicator) {
      children.push(createHydratedNode(indicator.type, indicator.config, [], createId));
      const defaultField = cloneDefaultConfig("condition").field;
      config.field = defaultField || "close";
    }
    return createHydratedNode("condition", config, children, createId);
  }

  errors.push(`${path}: condition non reconnue.`);
  return null;
}

function hydrateConditions(when, createId, errors) {
  if (!when || typeof when !== "object" || Object.keys(when).length === 0) {
    return [];
  }
  const node = hydrateConditionSchema(when, createId, errors, "when");
  if (!node) {
    return [];
  }
  return [node];
}

function hydrateSignal(signal, createId, errors) {
  if (!signal || typeof signal !== "object") {
    errors.push("Signal invalide dans la stratégie importée.");
    return [];
  }
  const steps = Array.isArray(signal.steps) ? signal.steps : [];
  const nodes = [];

  const ensureActionFromSignal = () => {
    if (!nodes.some((node) => node.type === "action")) {
      nodes.unshift(
        createHydratedNode(
          "action",
          {
            action: signal.action || "buy",
            size: signal.size ?? 1,
          },
          [],
          createId,
        )
      );
    }
  };

  steps.forEach((step, index) => {
    if (!isObject(step)) {
      errors.push(`Étape de signal invalide à l'index ${index}.`);
      return;
    }
    switch (step.type) {
      case "order":
        nodes.push(
          createHydratedNode(
            "action",
            { action: step.action || signal.action || "buy", size: step.size ?? signal.size ?? 1 },
            [],
            createId,
          )
        );
        break;
      case "delay":
        nodes.push(
          createHydratedNode("delay", { seconds: step.seconds ?? 0 }, [], createId)
        );
        break;
      case "take_profit":
        nodes.push(
          createHydratedNode(
            "take_profit",
            {
              mode: step.mode || "percent",
              value: step.value ?? 0,
              size: step.size || "full",
              customSize: step.customSize ?? "",
            },
            [],
            createId,
          )
        );
        break;
      case "stop_loss":
        nodes.push(
          createHydratedNode(
            "stop_loss",
            {
              mode: step.mode || "percent",
              value: step.value ?? 0,
              trailing: Boolean(step.trailing),
            },
            [],
            createId,
          )
        );
        break;
      case "close_position":
        nodes.push(
          createHydratedNode(
            "close_position",
            { side: step.side || "all" },
            [],
            createId,
          )
        );
        break;
      case "alert":
        nodes.push(
          createHydratedNode(
            "alert",
            {
              channel: step.channel || "email",
              message: step.message || "",
            },
            [],
            createId,
          )
        );
        break;
      default:
        errors.push(`Type d'action inconnu: ${step.type}`);
        break;
    }
  });

  if (!steps.length && (signal.action || signal.size)) {
    ensureActionFromSignal();
  }

  if (!nodes.length) {
    ensureActionFromSignal();
  }

  return nodes;
}

function extractPythonMapping(content) {
  const firstBrace = content.indexOf("{");
  if (firstBrace === -1) {
    throw new Error("Aucun dictionnaire trouvé dans le fichier Python.");
  }
  let depth = 0;
  for (let index = firstBrace; index < content.length; index += 1) {
    const char = content[index];
    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return content.slice(firstBrace, index + 1);
      }
    }
  }
  throw new Error("Parenthèses non équilibrées dans le fichier Python.");
}

function parsePythonDocument(content) {
  const body = extractPythonMapping(content);
  const normalized = body
    .replace(/\bTrue\b/g, "true")
    .replace(/\bFalse\b/g, "false")
    .replace(/\bNone\b/g, "null");
  return YAML.parse(normalized);
}

export function parseStrategyDocument(content, format = "yaml") {
  const errors = [];
  if (!content || !content.trim()) {
    errors.push("Le contenu de la stratégie est vide.");
    return { document: null, errors };
  }

  const normalizedFormat = format === "python" ? "python" : "yaml";
  let document = null;
  try {
    if (normalizedFormat === "python") {
      document = parsePythonDocument(content);
    } else {
      document = YAML.parse(content);
    }
  } catch (error) {
    errors.push("Impossible d'analyser le fichier de stratégie fourni.");
    return { document: null, errors };
  }

  if (!isObject(document)) {
    errors.push("Le document de stratégie doit être un objet JSON/YAML valide.");
    return { document: null, errors };
  }

  return { document, errors };
}

export function hydrateStrategyDocument(document, createId) {
  const errors = [];
  if (!isObject(document)) {
    errors.push("Le document de stratégie doit être un objet.");
    return { name: "", metadata: {}, conditions: [], actions: [], errors };
  }

  const idFactory = createIdFactory(createId);
  const rules = Array.isArray(document.rules) ? document.rules : [];
  if (!rules.length) {
    errors.push("La stratégie ne contient aucune règle.");
    return { name: document.name || "", metadata: document.metadata || {}, conditions: [], actions: [], errors };
  }

  const primaryRule = rules[0];
  if (!isObject(primaryRule)) {
    errors.push("La règle principale est invalide.");
    return { name: document.name || "", metadata: document.metadata || {}, conditions: [], actions: [], errors };
  }

  const conditions = hydrateConditions(primaryRule.when || {}, idFactory, errors);
  const actions = hydrateSignal(primaryRule.signal || {}, idFactory, errors);

  return {
    name: typeof document.name === "string" ? document.name : "",
    metadata: isObject(document.metadata) ? document.metadata : {},
    conditions,
    actions,
    errors,
  };
}

export function deserializeStrategy({ code, format = "yaml", createId } = {}) {
  const parseResult = parseStrategyDocument(code, format);
  const hydration = parseResult.document
    ? hydrateStrategyDocument(parseResult.document, createId)
    : { name: "", metadata: {}, conditions: [], actions: [], errors: [] };

  return {
    name: hydration.name,
    metadata: hydration.metadata,
    conditions: hydration.conditions,
    actions: hydration.actions,
    format: format === "python" ? "python" : "yaml",
    errors: [...parseResult.errors, ...hydration.errors],
  };
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function indent(level) {
  return "  ".repeat(level);
}

function toYamlValue(value, level) {
  if (Array.isArray(value)) {
    if (!value.length) {
      return "[]";
    }
    return `\n${value
      .map((item) => `${indent(level + 1)}- ${formatYamlValue(item, level + 1)}`)
      .join("\n")}`;
  }
  if (isObject(value)) {
    const entries = Object.entries(value);
    if (!entries.length) {
      return "{}";
    }
    return `\n${entries
      .map(([key, val]) => `${indent(level + 1)}${key}: ${formatYamlValue(val, level + 1)}`)
      .join("\n")}`;
  }
  if (typeof value === "string") {
    if (/[:\n#-]/.test(value)) {
      return `'${value.replace(/'/g, "''")}'`;
    }
    return value;
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (value === null || value === undefined) {
    return "null";
  }
  return String(value);
}

function formatYamlValue(value, level) {
  if (Array.isArray(value)) {
    if (!value.length) {
      return "[]";
    }
    const items = value
      .map((item) => {
        const formatted = formatYamlValue(item, level + 1);
        if (Array.isArray(item) || isObject(item)) {
          return `\n${indent(level + 2)}${formatted.trimStart()}`;
        }
        return formatted;
      })
      .map((item, index) => {
        const raw = value[index];
        if (Array.isArray(raw) || isObject(raw)) {
          return `${indent(level + 1)}- ${item.trimStart()}`;
        }
        return `${indent(level + 1)}- ${item}`;
      });
    return `\n${items.join("\n")}`;
  }
  if (isObject(value)) {
    const entries = Object.entries(value);
    if (!entries.length) {
      return "{}";
    }
    return `\n${entries
      .map(([key, val]) => `${indent(level + 1)}${key}: ${formatYamlValue(val, level + 1)}`)
      .join("\n")}`;
  }
  return toYamlValue(value, level);
}

export function toYaml(document) {
  const entries = Object.entries(document || {});
  return entries
    .map(([key, value]) => `${key}: ${formatYamlValue(value, 0)}`)
    .join("\n");
}

export function toPython(document) {
  const json = JSON.stringify(document || {}, null, 2)
    .replace(/true/g, "True")
    .replace(/false/g, "False")
    .replace(/null/g, "None");
  return `STRATEGY = ${json}`;
}

export function buildExports(name, conditions, actions) {
  const document = buildStrategyDocument(name, conditions, actions);
  return {
    document,
    yaml: toYaml(document),
    python: toPython(document),
  };
}
