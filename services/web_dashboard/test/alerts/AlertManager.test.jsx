import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import userEvent from "@testing-library/user-event";
import i18next from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import AlertManager from "../../src/alerts/AlertManager.jsx";

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

async function renderAlerts(props) {
  const user = userEvent.setup();
  const i18n = await createTestI18n();
  await act(async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AlertManager enableInitialFetch={false} {...props} />
      </I18nextProvider>
    );
    await Promise.resolve();
  });
  return user;
}

describe("AlertManager", () => {
  const initialAlerts = [
    {
      id: "maint-margin",
      title: "Maintenance margin nearing threshold",
      detail: "Portfolio Growth is at 82% of the allowed maintenance margin.",
      risk: "warning",
      acknowledged: false,
      created_at: "2024-04-01T10:00:00Z",
      rule: {
        symbol: "BTCUSDT",
        timeframe: "1h",
        conditions: {
          pnl: { enabled: true, operator: "below", value: -1500 },
          drawdown: { enabled: false, operator: "above", value: null },
          indicators: [],
        },
      },
      channels: [
        { type: "email", target: "risk@alpha.io", enabled: true },
        { type: "webhook", target: "https://hooks.alerts.test", enabled: false },
      ],
      throttle_seconds: 1800,
    },
  ];

  beforeEach(() => {
    global.fetch = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("affiche les alertes existantes et permet de basculer en mode édition", async () => {
    const user = await renderAlerts({
      initialAlerts,
      endpoint: "/alerts",
      authToken: "demo-token",
    });

    expect(await screen.findByText(/Maintenance margin nearing threshold/i)).toBeInTheDocument();

    const editButton = screen.getByRole("button", { name: /modifier/i });
    await user.click(editButton);

    const titleInput = screen.getByLabelText(/Titre/i);
    await waitFor(() => {
      expect(titleInput).toHaveValue("Maintenance margin nearing threshold");
    });

  });

  it("crée une nouvelle alerte via le moteur d'alertes", async () => {
    const createdAlert = {
      id: "drawdown",
      title: "Daily drawdown limit exceeded",
      detail: "Income portfolio dropped 6% over the last trading session.",
      risk: "critical",
      acknowledged: false,
      created_at: "2024-04-02T09:15:00Z",
      rule: {
        symbol: "ETHUSDT",
        timeframe: "4h",
        conditions: {
          pnl: { enabled: true, operator: "below", value: -500 },
          drawdown: { enabled: true, operator: "above", value: 5 },
          indicators: [],
        },
      },
      channels: [
        { type: "email", target: "ops@example.com", enabled: true },
        { type: "push", target: "desk-01", enabled: false },
      ],
      throttle_seconds: 900,
    };

    global.fetch = vi.fn().mockReturnValueOnce(createFetchResponse(createdAlert, 201));

    const user = await renderAlerts({
      initialAlerts,
      endpoint: "/alerts",
      authToken: "demo-token",
    });

    await user.clear(screen.getByLabelText(/Titre/i));
    await user.type(screen.getByLabelText(/Titre/i), "Daily drawdown limit exceeded");
    await user.clear(screen.getByLabelText(/Description/i));
    await user.type(
      screen.getByLabelText(/Description/i),
      "Income portfolio dropped 6% over the last trading session."
    );
    await user.selectOptions(screen.getByLabelText(/Niveau de risque/i), "critical");
    await user.clear(screen.getByLabelText(/Symbole surveillé/i));
    await user.type(screen.getByLabelText(/Symbole surveillé/i), "ETHUSDT");
    const pnlCheckbox = screen.getByLabelText(/Activer P&L/i);
    await user.click(pnlCheckbox);
    const pnlValue = screen.getByPlaceholderText(/Seuil P&L/i);
    await user.clear(pnlValue);
    await user.type(pnlValue, "-500");
    const drawdownCheckbox = screen.getByLabelText(/Activer drawdown/i);
    await user.click(drawdownCheckbox);
    const drawdownValue = screen.getByPlaceholderText(/Seuil drawdown/i);
    await user.clear(drawdownValue);
    await user.type(drawdownValue, "5");
    const webhookField = screen.getByPlaceholderText(/https:\/\/example.com\/webhook/i);
    await user.type(webhookField, "https://hooks.alerts.test/eth");
    const throttleInput = screen.getByLabelText(/Fréquence minimale/i);
    await user.clear(throttleInput);
    await user.type(throttleInput, "15");

    await user.click(screen.getByRole("button", { name: /créer/i }));

    await waitFor(() => {
      const lastCall = global.fetch.mock.calls.at(-1);
      expect(lastCall[0]).toBe("/alerts");
      expect(lastCall[1].method).toBe("POST");
      expect(lastCall[1].headers.Authorization).toBe("Bearer demo-token");
      const payload = JSON.parse(lastCall[1].body);
      expect(payload.title).toBe("Daily drawdown limit exceeded");
      expect(payload.rule.symbol).toBe("ETHUSDT");
      expect(payload.rule.conditions.pnl.enabled).toBe(true);
      expect(payload.channels).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ type: "email" }),
          expect.objectContaining({ type: "webhook", target: "https://hooks.alerts.test/eth" }),
        ]),
      );
      expect(payload.throttle_seconds).toBe(900);
    });

    expect(await screen.findByText(/Daily drawdown limit exceeded/i)).toBeInTheDocument();
  });

  it("affiche un message d'erreur lorsque la création échoue", async () => {
    global.fetch = vi.fn().mockReturnValueOnce(
      Promise.resolve({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: "Erreur inattendue" }),
        headers: { get: () => "application/json" },
      })
    );

    const user = await renderAlerts({
      initialAlerts,
      endpoint: "/alerts",
      authToken: "demo-token",
    });

    await user.clear(screen.getByLabelText(/Titre/i));
    await user.type(screen.getByLabelText(/Titre/i), "Nouvelle alerte");
    await user.clear(screen.getByLabelText(/Description/i));
    await user.type(screen.getByLabelText(/Description/i), "Impossible de joindre le moteur.");
    await user.clear(screen.getByLabelText(/Symbole surveillé/i));
    await user.type(screen.getByLabelText(/Symbole surveillé/i), "BTCUSDT");
    await user.click(screen.getByRole("button", { name: /créer/i }));

    const errorMessage = await screen.findByRole("alert");
    expect(errorMessage).toHaveTextContent(/erreur inattendue/i);
  });

  it("met à jour la liste à la réception d'un évènement temps réel", async () => {
    await renderAlerts({
      initialAlerts,
      endpoint: "/alerts",
      authToken: "demo-token",
    });

    const realtimeAlert = {
      id: "news",
      title: "Breaking news on AAPL",
      detail: "Apple announces quarterly earnings call for next Tuesday.",
      risk: "info",
      acknowledged: true,
      created_at: "2024-04-03T11:30:00Z",
      rule: {
        symbol: "AAPL",
        timeframe: null,
        conditions: { pnl: { enabled: false }, drawdown: { enabled: false }, indicators: [] },
      },
      channels: [],
    };

    await act(async () => {
      document.dispatchEvent(
        new CustomEvent("alerts:update", { detail: { items: [realtimeAlert], message: "Flux mis à jour" } })
      );
    });

    expect(await screen.findByText(/Breaking news on AAPL/i)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/Flux mis à jour/i);
  });
});
