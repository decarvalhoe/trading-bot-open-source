export const predefinedPrompts = [
  {
    id: "breakout",
    label: "Breakout intraday",
    prompt:
      "Identifie les cassures de range sur BTC/USDT en 15 minutes avec confirmation de volume.",
  },
  {
    id: "mean_reversion",
    label: "Retour à la moyenne",
    prompt:
      "Stratégie de retour à la moyenne sur ETH en 1h avec RSI et bandes de Bollinger.",
  },
  {
    id: "trend_following",
    label: "Suivi de tendance",
    prompt:
      "Suivi de tendance daily sur indices avec croisements de moyennes mobiles et trailing stop.",
  },
];

export const indicatorSuggestions = [
  "RSI",
  "MACD",
  "EMA 20",
  "EMA 50",
  "Bollinger Bands",
  "VWAP",
  "SuperTrend",
  "OBV",
];
