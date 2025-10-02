export const DATA_TRANSFER_FORMAT = "application/x-strategy-block";

export const BLOCK_DEFINITIONS = {
  condition: {
    type: "condition",
    label: "Condition",
    description:
      "Comparer un champ de marché à une valeur cible et définir le déclencheur d'une règle.",
    accepts: ["indicator", "logic", "condition"],
    category: "conditions",
    defaultConfig: {
      field: "close",
      operator: "gt",
      value: "100",
    },
  },
  indicator: {
    type: "indicator",
    label: "Indicateur",
    description:
      "Calculer une mesure technique (SMA, RSI, VWAP…) afin de l'utiliser dans une condition.",
    accepts: [],
    category: "conditions",
    defaultConfig: {
      source: "close",
      kind: "sma",
      period: "20",
    },
  },
  logic: {
    type: "logic",
    label: "Opérateur logique",
    description: "Regrouper plusieurs conditions avec un ET/OU imbriqué.",
    accepts: ["condition", "indicator", "logic"],
    category: "conditions",
    defaultConfig: {
      mode: "all",
    },
  },
  action: {
    type: "action",
    label: "Action d'exécution",
    description: "Déclencher un ordre ou une alerte via le moteur d'exécution.",
    accepts: [],
    category: "actions",
    defaultConfig: {
      action: "buy",
      size: "1",
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
  },
};

export function cloneDefaultConfig(type) {
  const definition = BLOCK_DEFINITIONS[type];
  if (!definition) {
    return {};
  }
  return JSON.parse(JSON.stringify(definition.defaultConfig || {}));
}
