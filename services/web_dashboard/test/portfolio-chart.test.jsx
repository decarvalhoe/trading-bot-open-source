import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, afterAll, beforeEach, vi } from "vitest";
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

const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;
const originalImage = global.Image;
const originalGetContext = HTMLCanvasElement.prototype.getContext;
const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;

const createObjectURLSpy = vi.fn(() => "blob:mock-url");
const revokeObjectURLSpy = vi.fn();
const getContextSpy = vi.fn(() => ({
  fillStyle: "",
  fillRect: vi.fn(),
  drawImage: vi.fn(),
}));
const toDataURLSpy = vi.fn(() => "data:image/png;base64,MOCK");
let anchorClickSpy;

beforeAll(() => {
  URL.createObjectURL = createObjectURLSpy;
  URL.revokeObjectURL = revokeObjectURLSpy;
  anchorClickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  class MockImage {
    constructor() {
      this.onload = null;
      this.onerror = null;
    }

    set src(_value) {
      if (typeof this.onload === "function") {
        this.onload();
      }
    }
  }
  global.Image = MockImage;
  HTMLCanvasElement.prototype.getContext = getContextSpy;
  HTMLCanvasElement.prototype.toDataURL = toDataURLSpy;
});

beforeEach(() => {
  vi.clearAllMocks();
});

afterAll(() => {
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
  global.Image = originalImage;
  HTMLCanvasElement.prototype.getContext = originalGetContext;
  HTMLCanvasElement.prototype.toDataURL = originalToDataURL;
  anchorClickSpy?.mockRestore();
});

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

test("permet de désélectionner une série via la barre d'outils", async () => {
  renderChart();
  const user = userEvent.setup();

  const growthToggle = await screen.findByLabelText(/Growth · Alice/i);
  const incomeToggle = await screen.findByLabelText(/Income · Bob/i);

  expect(growthToggle).toBeChecked();
  expect(incomeToggle).toBeChecked();

  await user.click(growthToggle);

  expect(growthToggle).not.toBeChecked();
  expect(incomeToggle).toBeChecked();
});

test("met à jour le libellé de zoom après modification de la plage", async () => {
  renderChart();

  const zoomStatus = await screen.findByText(/Affichage complet/i);
  const startSlider = screen.getByLabelText(/Début du zoom/i);

  fireEvent.input(startSlider, { target: { value: "1" } });

  await waitFor(() => {
    expect(zoomStatus.textContent).toMatch(/Zoom :/i);
  });
});

test("exporte les données visibles en CSV", async () => {
  renderChart();
  const user = userEvent.setup();

  await waitFor(() => {
    expect(document.querySelector(".recharts-surface")).not.toBeNull();
  });

  const csvButton = await screen.findByRole("button", { name: /Exporter CSV/i });
  await act(async () => {
    await user.click(csvButton);
  });

  await waitFor(() => {
    expect(createObjectURLSpy).toHaveBeenCalled();
  });

  const csvCall = createObjectURLSpy.mock.calls.find(
    ([argument]) => argument instanceof Blob && argument.type.includes("csv")
  );
  expect(csvCall).toBeTruthy();
  const blob = csvCall[0];
  expect(blob).toBeInstanceOf(Blob);
  expect(blob.type).toContain("csv");
  expect(blob.size).toBeGreaterThan(0);
  expect(anchorClickSpy).toHaveBeenCalled();
});

test("exporte le graphique au format PNG", async () => {
  renderChart();
  const user = userEvent.setup();

  await waitFor(() => {
    expect(document.querySelector(".recharts-surface")).not.toBeNull();
  });

  const pngButton = await screen.findByRole("button", { name: /Exporter PNG/i });
  await act(async () => {
    await user.click(pngButton);
  });

  await waitFor(() => {
    expect(toDataURLSpy).toHaveBeenCalledWith("image/png");
  });
  expect(anchorClickSpy).toHaveBeenCalled();
});
