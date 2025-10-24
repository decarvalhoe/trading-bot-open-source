import { render, screen } from "@testing-library/react";
import { act } from "react";
import i18next from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StatusPage from "../../src/pages/Status/StatusPage.jsx";
import apiClient from "../../src/lib/api.js";
import { getWebSocketClient } from "../../src/lib/websocket.js";

vi.mock("../../src/bootstrap", () => ({
  bootstrap: {
    data: {
      status: {
        services: [
          {
            name: "streaming",
            label: "Flux Streaming",
            status_label: "Opérationnel",
            status: "up",
            description: "Flux d'exécution en temps réel.",
            badge_variant: "success",
            health_url: "https://status.example.com/streaming",
          },
        ],
        checked_at: "2024-05-01T08:00:00Z",
        endpoint: "/status/overview",
      },
    },
    config: {},
  },
}));

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

describe("StatusPage", () => {
  beforeEach(() => {
    const client = getWebSocketClient();
    if (client?.subscribers?.clear) {
      client.subscribers.clear();
    }
    if (client?.statusListeners?.clear) {
      client.statusListeners.clear();
    }
    vi.spyOn(apiClient, "request").mockResolvedValue({
      services: [
        {
          name: "streaming",
          label: "Flux Streaming",
          status_label: "Opérationnel",
          status: "up",
          description: "Flux d'exécution en temps réel.",
          badge_variant: "success",
          health_url: "https://status.example.com/streaming",
        },
      ],
      checked_at: "2024-05-01T08:00:00Z",
    });
  });

  afterEach(() => {
    const client = getWebSocketClient();
    if (client?.subscribers?.clear) {
      client.subscribers.clear();
    }
    if (client?.statusListeners?.clear) {
      client.statusListeners.clear();
    }
    vi.restoreAllMocks();
  });

  it("met à jour le monitoring lors d'un message WebSocket", async () => {
    const i18n = await createTestI18n();

    await act(async () => {
      const queryClient = new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      });
      render(
        <QueryClientProvider client={queryClient}>
          <I18nextProvider i18n={i18n}>
            <StatusPage />
          </I18nextProvider>
        </QueryClientProvider>
      );
      await Promise.resolve();
    });

    expect(await screen.findByText(/Flux Streaming/i)).toBeInTheDocument();

    const client = getWebSocketClient();
    const updatedServices = [
      {
        name: "api-trading",
        label: "API Trading",
        status_label: "Incident majeur",
        status: "down",
        description: "Incident en cours sur l'API trading.",
        detail: "HTTP 503 renvoyé par le load balancer.",
        badge_variant: "critical",
        health_url: "https://status.example.com/api",
      },
    ];

    await act(async () => {
      client.publish("status.update", {
        services: updatedServices,
        checked_at: "2024-05-01T09:15:00Z",
      });
      await Promise.resolve();
    });

    expect(await screen.findByRole("heading", { name: /API Trading/i })).toBeInTheDocument();
    expect(screen.getByText(/Incident majeur/i)).toBeInTheDocument();
    expect(screen.getByText(/HTTP 503 renvoyé par le load balancer\./i)).toBeInTheDocument();
  });
});
