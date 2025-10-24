import { render, screen } from "@testing-library/react";
import { act } from "react";
import i18next from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import StatusPage from "../../src/pages/Status/StatusPage.jsx";
import { getWebSocketClient, resetWebSocketClient } from "../../src/lib/websocket.js";

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

function createFetchResponse(data, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
    headers: { get: () => "application/json" },
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

describe("StatusPage", () => {
  beforeEach(() => {
    resetWebSocketClient();
    global.fetch = vi.fn().mockImplementation(() =>
      createFetchResponse({
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
      })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  it("met à jour le monitoring lors d'un message WebSocket", async () => {
    const i18n = await createTestI18n();

    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <StatusPage />
        </I18nextProvider>
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

    act(() => {
      client.publish("status.update", {
        services: updatedServices,
        checked_at: "2024-05-01T09:15:00Z",
      });
    });

    expect(await screen.findByText(/API Trading/i)).toBeInTheDocument();
    expect(screen.getByText(/Incident majeur/i)).toBeInTheDocument();
    expect(screen.getByText(/HTTP 503 renvoyé par le load balancer\./i)).toBeInTheDocument();
  });
});
