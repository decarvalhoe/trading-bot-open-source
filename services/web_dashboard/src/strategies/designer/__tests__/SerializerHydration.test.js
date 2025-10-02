import { describe, expect, it } from "vitest";

import { deserializeStrategy } from "../serializer.js";

function createDeterministicIdFactory() {
  let counter = 1;
  return () => `node-${counter++}`;
}

describe("deserializeStrategy", () => {
  it("hydrates a YAML strategy into block trees", () => {
    const yaml = `name: Momentum YAML
rules:
  - when:
      all:
        - field: close
          operator: gt
          value: 150
        - field: MACD(close, 12, 26, 9)
          operator: exists
          value: true
    signal:
      action: buy
      size: 1
      steps:
        - type: order
          action: buy
          size: 1
        - type: stop_loss
          mode: percent
          value: 3
metadata:
  preset: momentum_yaml
`;

    const result = deserializeStrategy({
      code: yaml,
      format: "yaml",
      createId: createDeterministicIdFactory(),
    });

    expect(result.errors).toEqual([]);
    expect(result.format).toBe("yaml");
    expect(result.name).toBe("Momentum YAML");
    expect(result.conditions).toHaveLength(1);

    const rootCondition = result.conditions[0];
    expect(rootCondition.type).toBe("logic");
    expect(rootCondition.children).toHaveLength(2);
    expect(rootCondition.children[0]).toMatchObject({ type: "condition" });
    expect(rootCondition.children[1]).toMatchObject({ type: "indicator_macd" });

    expect(result.actions).toHaveLength(2);
    expect(result.actions[0]).toMatchObject({ type: "action", config: { action: "buy", size: "1" } });
    expect(result.actions[1]).toMatchObject({ type: "stop_loss", config: { mode: "percent", value: "3" } });
  });

  it("supports Python strategy definitions", () => {
    const python = `STRATEGY = {
  "name": "Python Strategy",
  "metadata": {"source": "python"},
  "rules": [
    {
      "when": {"field": "volume", "operator": "gt", "value": 3200, "timeframe": "1h"},
      "signal": {
        "action": "sell",
        "size": 2,
        "steps": [
          {"type": "order", "action": "sell", "size": 2},
          {"type": "delay", "seconds": 30}
        ]
      }
    }
  ]
}
`;

    const result = deserializeStrategy({
      code: python,
      format: "python",
      createId: createDeterministicIdFactory(),
    });

    expect(result.errors).toEqual([]);
    expect(result.format).toBe("python");
    expect(result.name).toBe("Python Strategy");
    expect(result.metadata).toMatchObject({ source: "python" });
    expect(result.conditions).toHaveLength(1);

    const volumeNode = result.conditions[0];
    expect(volumeNode.type).toBe("market_volume");
    expect(volumeNode.config).toMatchObject({ operator: "gt", value: "3200", timeframe: "1h" });

    expect(result.actions).toHaveLength(2);
    expect(result.actions[0]).toMatchObject({ type: "action", config: { action: "sell", size: "2" } });
    expect(result.actions[1]).toMatchObject({ type: "delay", config: { seconds: "30" } });
  });

  it("returns validation errors for malformed documents", () => {
    const result = deserializeStrategy({
      code: "name: Invalid\nrules: [",
      format: "yaml",
      createId: createDeterministicIdFactory(),
    });

    expect(result.document).toBeUndefined();
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.conditions).toEqual([]);
    expect(result.actions).toEqual([]);
  });
});
