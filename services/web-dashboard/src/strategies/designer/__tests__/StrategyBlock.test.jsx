/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import StrategyBlock from "../StrategyBlock.jsx";
import * as matchers from "@testing-library/jest-dom/matchers";

expect.extend(matchers.default ?? matchers);

describe("StrategyBlock advanced fields", () => {
  const baseActions = {
    onDrop: vi.fn(),
    onConfigChange: vi.fn(),
    onRemove: vi.fn(),
  };

  it("renders MACD indicator specific inputs", () => {
    render(
      <StrategyBlock
        node={{
          id: "macd-1",
          type: "indicator_macd",
          config: {
            source: "close",
            fastPeriod: "12",
            slowPeriod: "26",
            signalPeriod: "9",
          },
          children: [],
        }}
        section="conditions"
        {...baseActions}
      />
    );

    expect(screen.getByLabelText("Période rapide")).toHaveValue(12);
    expect(screen.getByLabelText("Période lente")).toHaveValue(26);
    expect(screen.getByLabelText("Période signal")).toHaveValue(9);
  });

  it("displays take-profit configuration fields", () => {
    render(
      <StrategyBlock
        node={{
          id: "tp-1",
          type: "take_profit",
          config: { mode: "percent", value: "5", size: "half" },
          children: [],
        }}
        section="actions"
        {...baseActions}
      />
    );

    expect(screen.getByLabelText("Type de cible")).toHaveValue("percent");
    expect(screen.getByLabelText("Valeur")).toHaveValue(5);
    expect(screen.getByLabelText("Part de la position")).toHaveValue("half");
  });
});
