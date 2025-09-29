import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PortfolioChart } from "../src/components/PortfolioChart.jsx";

const SAMPLE_HISTORY = [
  {
    name: "Growth",
    owner: "Alice",
    currency: "€",
    series: [
      { timestamp: "2024-03-01T00:00:00Z", value: 100000, pnl: 0 },
      { timestamp: "2024-03-02T00:00:00Z", value: 102500, pnl: 2500 },
      { timestamp: "2024-03-03T00:00:00Z", value: 104000, pnl: 4000 },
    ],
  },
  {
    name: "Income",
    owner: "Bob",
    currency: "€",
    series: [
      { timestamp: "2024-03-01T00:00:00Z", value: 56000, pnl: 0 },
      { timestamp: "2024-03-02T00:00:00Z", value: 56200, pnl: 200 },
      { timestamp: "2024-03-03T00:00:00Z", value: 55950, pnl: -50 },
    ],
  },
];

function renderChart() {
  const { container } = render(
    <div data-testid="chart-wrapper" style={{ width: "800px", height: "320px" }}>
      <PortfolioChart history={SAMPLE_HISTORY} currency="€" />
    </div>
  );

  const wrapper = container.querySelector("[data-testid='chart-wrapper']");
  Object.defineProperty(wrapper, "clientWidth", { value: 800, configurable: true });
  Object.defineProperty(wrapper, "clientHeight", { value: 320, configurable: true });
  Object.defineProperty(wrapper, "getBoundingClientRect", {
    value: () => ({ width: 800, height: 320, top: 0, left: 0, right: 800, bottom: 320 }),
  });

  return container;
}

test("affiche toutes les séries dans la légende", async () => {
  renderChart();

  await waitFor(() => {
    expect(screen.getByText(/Growth · Alice/i)).toBeInTheDocument();
    expect(screen.getByText(/Income · Bob/i)).toBeInTheDocument();
  });
});

test("affiche une info-bulle lors du survol d'une courbe", async () => {
  const container = renderChart();
  const user = userEvent.setup();

  await waitFor(() => {
    expect(container.querySelector(".portfolio-line--growth")).not.toBeNull();
  });

  const curve = container.querySelector(".portfolio-line--growth");
  await act(async () => {
    await user.hover(curve);
    fireEvent.mouseMove(curve, { clientX: 320, clientY: 160 });
  });

  await waitFor(() => {
    const tooltip = document.querySelector(".chart-tooltip");
    expect(tooltip).not.toBeNull();
    expect(tooltip.textContent).toMatch(/Growth/i);
    expect(tooltip.textContent).toMatch(/€\s*\(/);
  });
});
