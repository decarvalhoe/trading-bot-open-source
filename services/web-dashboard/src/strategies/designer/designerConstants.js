export const DATA_TRANSFER_FORMAT = "application/x-strategy-block";

const CONDITION_INDICATOR_TYPES = ["indicator", "indicator_macd", "indicator_bollinger", "indicator_atr"];

export const BLOCK_DEFINITIONS = {
  condition: {
    type: "condition",
    label: "Condition",
    description:
      "Comparer un champ de marché à une valeur cible et définir le déclencheur d'une règle.",
    accepts: CONDITION_INDICATOR_TYPES,
    category: "conditions",
    defaultConfig: {
      field: "close",
      operator: "gt",
      value: "100",
    },
    validation: {
      required: [
        { field: "field", label: "Champ" },
        { field: "operator", label: "Opérateur" },
        { field: "value", label: "Valeur" },
      ],
      maxChildren: 1,
    },
  },
  market_cross: {
    type: "market_cross",
    label: "Croisement",
    description:
      "Détecter le croisement de deux indicateurs (ex. MACD vs moyenne mobile).",
    accepts: CONDITION_INDICATOR_TYPES,
    category: "conditions",
    defaultConfig: {
      direction: "above",
      lookback: "3",
    },
    validation: {
      required: [{ field: "direction", label: "Direction" }],
      minChildren: 2,
      maxChildren: 2,
    },
  },
  market_volume: {
    type: "market_volume",
    label: "Volume seuil",
    description: "Vérifier si le volume respecte un seuil donné sur un intervalle.",
    accepts: [],
    category: "conditions",
    defaultConfig: {
      operator: "gt",
      value: "100000",
      timeframe: "1h",
    },
    validation: {
      required: [
        { field: "operator", label: "Opérateur" },
        { field: "value", label: "Seuil" },
        { field: "timeframe", label: "Intervalle" },
      ],
    },
  },
  indicator: {
    type: "indicator",
    label: "Indicateur simple",
    description:
      "Calculer une mesure technique (SMA, RSI, VWAP…) afin de l'utiliser dans une condition.",
    accepts: [],
    category: "conditions",
    defaultConfig: {
      source: "close",
      kind: "sma",
      period: "20",
    },
    validation: {
      required: [
        { field: "source", label: "Source" },
        { field: "kind", label: "Type" },
        { field: "period", label: "Période" },
      ],
    },
  },
  indicator_macd: {
    type: "indicator_macd",
    label: "MACD",
    description: "Oscillateur MACD avec périodes rapide/lente et signal configurable.",
    accepts: [],
    category: "conditions",
    defaultConfig: {
      source: "close",
      fastPeriod: "12",
      slowPeriod: "26",
      signalPeriod: "9",
    },
    validation: {
      required: [
        { field: "source", label: "Source" },
        { field: "fastPeriod", label: "Période rapide" },
        { field: "slowPeriod", label: "Période lente" },
        { field: "signalPeriod", label: "Période signal" },
      ],
    },
  },
  indicator_bollinger: {
    type: "indicator_bollinger",
    label: "Bandes de Bollinger",
    description: "Bandes de volatilité basées sur une moyenne mobile et une déviation.",
    accepts: [],
    category: "conditions",
    defaultConfig: {
      source: "close",
      period: "20",
      deviation: "2",
    },
    validation: {
      required: [
        { field: "source", label: "Source" },
        { field: "period", label: "Période" },
        { field: "deviation", label: "Déviation" },
      ],
    },
  },
  indicator_atr: {
    type: "indicator_atr",
    label: "ATR",
    description: "Average True Range permettant d'évaluer la volatilité.",
    accepts: [],
    category: "conditions",
    defaultConfig: {
      source: "hlc3",
      period: "14",
      smoothing: "14",
    },
    validation: {
      required: [
        { field: "source", label: "Source" },
        { field: "period", label: "Période" },
        { field: "smoothing", label: "Lissage" },
      ],
    },
  },
  logic: {
    type: "logic",
    label: "Opérateur logique",
    description: "Regrouper plusieurs conditions avec un ET/OU imbriqué.",
    accepts: [
      "condition",
      "market_cross",
      "market_volume",
      "logic",
      "negation",
      "group",
    ],
    category: "conditions",
    defaultConfig: {
      mode: "all",
    },
    validation: {
      required: [{ field: "mode", label: "Mode" }],
      minChildren: 2,
    },
  },
  negation: {
    type: "negation",
    label: "Négation",
    description: "Inverser le résultat d'une condition (NON / NOT).",
    accepts: ["condition", "market_cross", "market_volume", "logic", "group"],
    category: "conditions",
    defaultConfig: {},
    validation: {
      minChildren: 1,
      maxChildren: 1,
    },
  },
  group: {
    type: "group",
    label: "Parenthèses",
    description: "Créer un sous-groupe afin de prioriser certaines conditions.",
    accepts: ["condition", "market_cross", "market_volume", "logic", "negation"],
    category: "conditions",
    defaultConfig: {},
    validation: {
      minChildren: 1,
    },
  },
  action: {
    type: "action",
    label: "Action d'exécution",
    description: "Déclencher un ordre via le moteur d'exécution.",
    accepts: [],
    category: "actions",
    defaultConfig: {
      action: "buy",
      size: "1",
    },
    validation: {
      required: [
        { field: "action", label: "Action" },
        { field: "size", label: "Taille" },
      ],
    },
  },
  take_profit: {
    type: "take_profit",
    label: "Take-profit",
    description: "Sécuriser les gains une fois qu'un objectif est atteint.",
    accepts: [],
    category: "actions",
    defaultConfig: {
      mode: "percent",
      value: "5",
      size: "full",
    },
    validation: {
      required: [
        { field: "mode", label: "Type de cible" },
        { field: "value", label: "Valeur" },
      ],
    },
  },
  stop_loss: {
    type: "stop_loss",
    label: "Stop-loss",
    description: "Limiter les pertes avec un seuil fixe ou suiveur.",
    accepts: [],
    category: "actions",
    defaultConfig: {
      mode: "percent",
      value: "2",
      trailing: false,
    },
    validation: {
      required: [
        { field: "mode", label: "Type de seuil" },
        { field: "value", label: "Valeur" },
      ],
    },
  },
  close_position: {
    type: "close_position",
    label: "Fermer la position",
    description: "Clôturer tout ou partie de la position ouverte.",
    accepts: [],
    category: "actions",
    defaultConfig: {
      side: "all",
    },
    validation: {
      required: [{ field: "side", label: "Cible" }],
    },
  },
  alert: {
    type: "alert",
    label: "Alerte",
    description: "Notifier une équipe ou un canal externe lors du déclenchement.",
    accepts: [],
    category: "actions",
    defaultConfig: {
      channel: "email",
      message: "Alerte stratégie",
    },
    validation: {
      required: [
        { field: "channel", label: "Canal" },
        { field: "message", label: "Message" },
      ],
    },
  },
  delay: {
    type: "delay",
    label: "Temporisation",
    description: "Attendre un délai défini avant l'étape suivante de la stratégie.",
    accepts: [],
    category: "actions",
    defaultConfig: {
      seconds: "60",
    },
    validation: {
      required: [{ field: "seconds", label: "Délai (secondes)" }],
    },
  },
};

export function cloneDefaultConfig(type) {
  const definition = BLOCK_DEFINITIONS[type];
  if (!definition) {
    return {};
  }
  return JSON.parse(JSON.stringify(definition.defaultConfig || {}));
}
