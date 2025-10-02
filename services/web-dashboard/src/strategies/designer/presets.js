export const STRATEGY_PRESETS = [
  {
    id: "momentum_breakout",
    label: "Cassure momentum",
    description:
      "Détecte une cassure haussière via le MACD accompagné d'un volume soutenu, puis sécurise la position.",
    format: "yaml",
    content: `name: Cassure Momentum
rules:
  - when:
      all:
        - field: MACD(close, 12, 26, 9)
          operator: gt
          value: 0
        - field: volume
          operator: gt
          value: 150000
          timeframe: 1h
    signal:
      action: buy
      size: 1
      steps:
        - type: order
          action: buy
          size: 1
        - type: take_profit
          mode: percent
          value: 6
          size: half
        - type: stop_loss
          mode: percent
          value: 2
metadata:
  preset: momentum_breakout
`,
  },
  {
    id: "mean_reversion",
    label: "Retour à la moyenne",
    description:
      "Vend lorsque le prix touche la bande haute de Bollinger et rouvre lors du retour vers la moyenne.",
    format: "yaml",
    content: `name: Retour à la moyenne
rules:
  - when:
      all:
        - field: BOLL(close, 20, 2)
          operator: gt
          value: close
        - field: ATR(hlc3, 14, 14)
          operator: lt
          value: 3
    signal:
      action: sell
      size: 1
      steps:
        - type: order
          action: sell
          size: 1
        - type: take_profit
          mode: price
          value: 0.5
          size: half
        - type: delay
          seconds: 3600
        - type: close_position
          side: all
metadata:
  preset: mean_reversion
`,
  },
  {
    id: "range_scalp",
    label: "Scalping de range",
    description:
      "Combine un signal RSI court terme et un volume faible pour capter les oscillations rapides.",
    format: "yaml",
    content: `name: Scalp Range
rules:
  - when:
      any:
        - field: RSI(close, 7)
          operator: lt
          value: 30
        - field: RSI(close, 7)
          operator: gt
          value: 70
    signal:
      action: buy
      size: 1
      steps:
        - type: order
          action: buy
          size: 1
        - type: alert
          channel: discord
          message: "Scalp déclenché"
metadata:
  preset: range_scalp
`,
  },
];

export function findPresetById(presetId) {
  return STRATEGY_PRESETS.find((preset) => preset.id === presetId) || null;
}

export function listPresetSummaries() {
  return STRATEGY_PRESETS.map(({ id, label, description }) => ({
    id,
    label,
    description,
  }));
}
