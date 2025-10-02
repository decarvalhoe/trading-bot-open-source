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
