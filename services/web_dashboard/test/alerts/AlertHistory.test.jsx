import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18next from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AlertHistory from "../../src/alerts/AlertHistory.jsx";
import apiClient from "../../src/lib/api.js";

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
  return createTestI18n(language).then((i18n) => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={i18n}>{ui}</I18nextProvider>
      </QueryClientProvider>,
    );
  });
}

describe("AlertHistory", () => {
  beforeEach(() => {
    vi.spyOn(apiClient.alerts, "history").mockResolvedValue({
      items: [],
      pagination: { page: 1, pages: 1, total: 0, page_size: 10 },
      available_filters: { strategies: [], severities: [] },
    });
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

    apiClient.alerts.history
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);

    const user = userEvent.setup();
    await renderWithI18n(<AlertHistory endpoint="/alerts/history" />);

    expect(await screen.findByText(/Breakout BTC/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /précédent/i })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /suivant/i }));

    await waitFor(() => {
      expect(apiClient.alerts.history).toHaveBeenLastCalledWith({
        endpoint: "/alerts/history",
        query: { page: 2, page_size: 10 },
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

    apiClient.alerts.history.mockResolvedValue(pagePayload);

    const user = userEvent.setup();
    await renderWithI18n(<AlertHistory endpoint="/alerts/history" />);

    const severitySelect = await screen.findByLabelText(/Sévérité/i);
    await screen.findByRole("option", { name: /critical/i });

    await user.selectOptions(severitySelect, "critical");

    await waitFor(() => {
      expect(apiClient.alerts.history).toHaveBeenLastCalledWith({
        endpoint: "/alerts/history",
        query: { page: 1, page_size: 10, severity: "critical" },
      });
    });
  });
});
