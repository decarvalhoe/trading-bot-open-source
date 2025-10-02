import { beforeEach, afterEach, expect, test, vi } from "vitest";

const SCRIPT_PATH = "../app/static/dashboard.js";

const originalFetch = global.fetch;
const originalWebSocket = global.WebSocket;

function buildBootstrapScript(data) {
  const script = document.createElement("script");
  script.id = "dashboard-bootstrap";
  script.type = "application/json";
  script.textContent = JSON.stringify(data);
  return script;
}

function mountBaseDom(context, streaming) {
  document.body.innerHTML = "";
  const root = document.createElement("div");
  root.appendChild(buildBootstrapScript({ context, streaming }));

  const setupsStatus = document.createElement("p");
  setupsStatus.id = "inplay-setups-status";
  setupsStatus.className = "inplay-setups__status text";
  root.appendChild(setupsStatus);

  const setupsGrid = document.createElement("div");
  setupsGrid.className = "inplay-setups__grid";
  root.appendChild(setupsGrid);

  root.appendChild(document.createElement("ul")).className = "portfolio-list";

  const transactionsTable = document.createElement("table");
  transactionsTable.setAttribute("aria-labelledby", "transactions-title");
  const tbody = document.createElement("tbody");
  transactionsTable.appendChild(tbody);
  transactionsTable.className = "card";
  root.appendChild(transactionsTable);

  root.appendChild(document.createElement("ul")).className = "alert-list";

  const strategyTable = document.createElement("table");
  const strategyBody = document.createElement("tbody");
  strategyBody.className = "strategy-table__body";
  strategyTable.appendChild(strategyBody);
  root.appendChild(strategyTable);

  const logs = document.createElement("ul");
  logs.id = "log-entries";
  root.appendChild(logs);

  document.body.appendChild(root);
}

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = "";
});

afterEach(() => {
  vi.restoreAllMocks();
  if (originalFetch) {
    global.fetch = originalFetch;
  } else {
    delete global.fetch;
  }
  if (originalWebSocket) {
    global.WebSocket = originalWebSocket;
  } else {
    delete global.WebSocket;
  }
  document.body.innerHTML = "";
});

const SAMPLE_CONTEXT = {
  portfolios: [],
  transactions: [],
  alerts: [],
  strategies: [],
  logs: [],
  setups: {
    fallback_reason: "Instantané statique utilisé faute de connexion au service InPlay.",
    watchlists: [
      {
        id: "demo-momentum",
        symbols: [
          {
            symbol: "AAPL",
            setups: [
              {
                strategy: "ORB",
                status: "pending",
                entry: 189.95,
                target: 192.1,
                stop: 187.8,
                probability: 0.64,
                updated_at: "2024-05-01T10:00:00Z",
              },
            ],
          },
          {
            symbol: "MSFT",
            setups: [
              {
                strategy: "Breakout",
                status: "validated",
                entry: 404.2,
                target: 409.5,
                stop: 398.7,
                probability: 0.58,
                updated_at: "2024-05-01T10:05:00Z",
              },
            ],
          },
        ],
      },
    ],
  },
};

test("affiche les setups initiaux et le message de fallback", async () => {
  mountBaseDom(SAMPLE_CONTEXT, {});

  await import(SCRIPT_PATH);

  const cards = document.querySelectorAll(".setup-card");
  expect(cards.length).toBe(2);
  expect(cards[0].querySelector(".setup-card__strategy").textContent).toBe("ORB");
  expect(cards[1].textContent).toContain("Breakout");

  const statusNode = document.getElementById("inplay-setups-status");
  expect(statusNode.textContent.trim()).toContain("Instantané statique");
});

test("met à jour les setups lors d'un événement watchlist.update", async () => {
  const streaming = {
    handshake_url: "https://stream.example/rooms/public-room/connection",
    viewer_id: "viewer-1",
  };

  const fetchMock = vi
    .fn()
    .mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ websocket_url: "wss://stream.example/ws" }),
    });
  global.fetch = fetchMock;

  class FakeWebSocket {
    static instances = [];
    static OPEN = 1;
    static CLOSED = 3;

    constructor(url) {
      this.url = url;
      this.readyState = FakeWebSocket.OPEN;
      FakeWebSocket.instances.push(this);
      setTimeout(() => {
        if (typeof this.onopen === "function") {
          this.onopen();
        }
      }, 0);
    }

    send() {}

    close() {
      this.readyState = FakeWebSocket.CLOSED;
      if (typeof this.onclose === "function") {
        this.onclose();
      }
    }

    emit(message) {
      if (typeof this.onmessage === "function") {
        this.onmessage({ data: JSON.stringify(message) });
      }
    }
  }

  global.WebSocket = FakeWebSocket;

  mountBaseDom(SAMPLE_CONTEXT, streaming);

  await import(SCRIPT_PATH);
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(FakeWebSocket.instances.length).toBe(1);

  const socket = FakeWebSocket.instances[0];
  socket.emit({
    type: "watchlist.update",
    payload: {
      id: "demo-momentum",
      symbols: [
        {
          symbol: "AAPL",
          setups: [
            {
              strategy: "ORB",
              status: "validated",
              entry: 190.5,
              target: 194.0,
              stop: 188.0,
              probability: 0.7,
              updated_at: "2024-05-01T10:15:00Z",
            },
          ],
        },
      ],
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 0));

  const updatedCard = document.querySelector(".setup-card");
  expect(updatedCard.querySelector(".badge").textContent.trim()).toBe("Validated");
  const metrics = Array.from(updatedCard.querySelectorAll(".setup-card__metric-value"));
  expect(metrics[0].textContent).toBe("190.50");
  expect(metrics[1].textContent).toBe("194.00");
  expect(metrics[2].textContent).toBe("188.00");
  expect(metrics[3].textContent).toContain("70");

  const statusNode = document.getElementById("inplay-setups-status");
  expect(statusNode.textContent.trim()).toBe("Flux InPlay connecté.");
});

test("met à jour les portefeuilles en temps réel et restaure le fallback", async () => {
  const streaming = {
    handshake_url: "https://stream.example/rooms/public-room/connection",
    viewer_id: "viewer-portfolio",
  };

  const fetchMock = vi
    .fn()
    .mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ websocket_url: "wss://stream.example/ws" }),
    });
  global.fetch = fetchMock;

  class StreamingWebSocket {
    static instances = [];
    static OPEN = 1;
    static CLOSED = 3;

    constructor(url) {
      this.url = url;
      this.readyState = StreamingWebSocket.OPEN;
      StreamingWebSocket.instances.push(this);
      setTimeout(() => {
        if (typeof this.onopen === "function") {
          this.onopen();
        }
      }, 0);
    }

    send() {}

    close() {
      this.readyState = StreamingWebSocket.CLOSED;
      if (typeof this.onclose === "function") {
        this.onclose();
      }
    }

    emit(message) {
      if (typeof this.onmessage === "function") {
        this.onmessage({ data: JSON.stringify(message) });
      }
    }
  }

  global.WebSocket = StreamingWebSocket;

  const context = {
    ...SAMPLE_CONTEXT,
    portfolios: [
      {
        name: "Portefeuille Fallback",
        owner: "fallback",
        total_value: 1000,
        holdings: [
          {
            symbol: "AAPL",
            quantity: 5,
            average_price: 100,
            current_price: 120,
            market_value: 600,
          },
        ],
      },
    ],
    data_sources: { ...(SAMPLE_CONTEXT.data_sources || {}), portfolios: "fallback" },
  };

  mountBaseDom(context, streaming);

  await import(SCRIPT_PATH);
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(StreamingWebSocket.instances.length).toBe(1);
  const socket = StreamingWebSocket.instances[0];

  let items = document.querySelectorAll(".portfolio-list__item");
  expect(items.length).toBe(1);
  expect(items[0].textContent).toContain("Portefeuille Fallback");
  expect(document.querySelector(".portfolio-list").getAttribute("data-source")).toBe(
    "fallback"
  );

  socket.emit({
    payload: {
      resource: "portfolios",
      mode: "live",
      items: [
        {
          name: "Compte Alpha",
          owner: "alpha",
          total_value: 2500,
          holdings: [
            {
              symbol: "MSFT",
              quantity: 10,
              average_price: 230,
              current_price: 250,
              market_value: 2500,
            },
          ],
        },
      ],
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 0));

  items = document.querySelectorAll(".portfolio-list__item");
  expect(items.length).toBe(1);
  expect(items[0].textContent).toContain("Compte Alpha");
  expect(document.querySelector(".portfolio-list").getAttribute("data-source")).toBe(
    "live"
  );

  socket.close();
  await new Promise((resolve) => setTimeout(resolve, 0));

  items = document.querySelectorAll(".portfolio-list__item");
  expect(items.length).toBe(1);
  expect(items[0].textContent).toContain("Portefeuille Fallback");
  expect(document.querySelector(".portfolio-list").getAttribute("data-source")).toBe(
    "fallback"
  );
});
