import { describe, expect, it } from "vitest";
import { validateStrategy } from "../StrategyDesigner.jsx";

const indicator = (id, type, config) => ({ id, type, config, children: [] });

const emptyNode = (id, type, config = {}, children = []) => ({ id, type, config, children });

describe("validateStrategy", () => {
  it("accepts a complex configuration", () => {
    const conditions = [
      emptyNode("logic-1", "logic", { mode: "all" }, [
        emptyNode(
          "cond-1",
          "condition",
          { field: "close", operator: "gt", value: "100" },
          [indicator("ind-1", "indicator_macd", { source: "close", fastPeriod: "12", slowPeriod: "26", signalPeriod: "9" })]
        ),
        emptyNode(
          "cross-1",
          "market_cross",
          { direction: "above", lookback: "5" },
          [
            indicator("ind-2", "indicator_bollinger", { source: "close", period: "20", deviation: "2" }),
            indicator("ind-3", "indicator_atr", { source: "hlc3", period: "14", smoothing: "14" }),
          ]
        ),
        emptyNode(
          "neg-1",
          "negation",
          {},
          [
            emptyNode("vol-1", "market_volume", { operator: "gt", value: "100000", timeframe: "1h" }),
          ]
        ),
      ]),
    ];

    const actions = [
      emptyNode("act-1", "action", { action: "buy", size: "2" }),
      emptyNode("tp-1", "take_profit", { mode: "percent", value: "5", size: "half" }),
      emptyNode("sl-1", "stop_loss", { mode: "percent", value: "2", trailing: true }),
      emptyNode("alert-1", "alert", { channel: "email", message: "Condition atteinte" }),
    ];

    const result = validateStrategy(conditions, actions);

    expect(result.errors).toHaveLength(0);
    expect(result.rule).toContain("MACD");
    expect(result.rule).toContain("Take-profit");
    expect(result.rule).toContain("Stop-loss");
  });

  it("highlights missing configuration", () => {
    const conditions = [
      emptyNode(
        "cross-invalid",
        "market_cross",
        { direction: "above", lookback: "0" },
        [indicator("ind-err", "indicator_macd", { source: "", fastPeriod: "", slowPeriod: "", signalPeriod: "" })]
      ),
    ];
    const actions = [emptyNode("tp-invalid", "take_profit", { mode: "percent", value: "", size: "full" })];

    const result = validateStrategy(conditions, actions);

    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors.join(" ")).toMatch(/fenêtre d'observation/i);
    expect(result.errors.join(" ")).toMatch(/Take-profit/i);
  });
});
