import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18next from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import AlertHistory from "../../src/alerts/AlertHistory.jsx";

function createFetchResponse(data, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  });
}

async function createTestI18n(language = "fr") {
  const instance = i18next.createInstance();
  await instance.use(initReactI18next).init({
    lng: language,
    fallbackLng: "fr",
    resources: {
      fr: { translation: {} },
      en: { translation: {} },
    },
    interpolation: { escapeValue: false },
  });
  return instance;
}

function renderWithI18n(ui, language = "fr") {
  return createTestI18n(language).then((i18n) =>
    render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>)
  );
}

describe("AlertHistory", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("affiche les entrées d'historique et gère la pagination", async () => {
    const firstPage = {
      items: [
        {
          id: 1,
          rule_name: "Breakout BTC",
          strategy: "Momentum",
          severity: "critical",
          symbol: "BTC",
          triggered_at: "2024-04-10T10:00:00Z",
          notification_type: "trigger",
          notification_channel: "email",
        },
        {
          id: 2,
          rule_name: "Reversal ETH",
          strategy: "Mean Reversion",
          severity: "warning",
          symbol: "ETH",
          triggered_at: "2024-04-10T09:00:00Z",
          notification_type: "trigger",
          notification_channel: "webhook",
        },
      ],
      pagination: { page: 1, page_size: 10, total: 3, pages: 2 },
      available_filters: { strategies: ["Momentum", "Mean Reversion"], severities: ["critical", "warning"] },
    };
    const secondPage = {
      items: [
        {
          id: 3,
          rule_name: "Liquidity alert",
          strategy: "Momentum",
          severity: "critical",
          symbol: "BTC",
          triggered_at: "2024-04-09T15:00:00Z",
          notification_type: "throttled",
          notification_channel: "email,push",
        },
      ],
      pagination: { page: 2, page_size: 10, total: 3, pages: 2 },
      available_filters: { strategies: ["Momentum", "Mean Reversion"], severities: ["critical", "warning"] },
    };

    global.fetch.mockResolvedValueOnce(createFetchResponse(firstPage));
    global.fetch.mockResolvedValueOnce(createFetchResponse(secondPage));

    const user = userEvent.setup();
    await renderWithI18n(<AlertHistory endpoint="/alerts/history" />);

    expect(await screen.findByText(/Breakout BTC/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /précédent/i })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /suivant/i }));

    await waitFor(() => {
      const lastCall = global.fetch.mock.calls.at(-1);
      expect(lastCall[0]).toBe("/alerts/history?page=2&page_size=10");
      expect(lastCall[1]).toMatchObject({
        headers: { Accept: "application/json" },
      });
    });
    expect(await screen.findByText(/Liquidity alert/)).toBeInTheDocument();
  });

  it("rafraîchit les données lorsque des filtres sont appliqués", async () => {
    const pagePayload = {
      items: [],
      pagination: { page: 1, page_size: 10, total: 0, pages: 1 },
      available_filters: { strategies: ["Momentum"], severities: ["critical"] },
    };

    global.fetch.mockResolvedValue(createFetchResponse(pagePayload));

    const user = userEvent.setup();
    await renderWithI18n(<AlertHistory endpoint="/alerts/history" />);

    expect(await screen.findByLabelText(/Sévérité/i)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/Sévérité/i), "critical");

    await waitFor(() => {
      const lastCall = global.fetch.mock.calls.at(-1);
      expect(lastCall[0]).toBe("/alerts/history?page=1&page_size=10&severity=critical");
      expect(lastCall[1]).toMatchObject({
        headers: { Accept: "application/json" },
      });
    });
  });
});
