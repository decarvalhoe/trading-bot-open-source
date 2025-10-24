const DEFAULT_OPTIONS = {
  reconnectDelay: 5000,
  maxReconnectDelay: 30000,
  autoReconnect: true,
  parse: (value) => JSON.parse(value),
};

function getDefaultUrl() {
  if (typeof import.meta !== "undefined" && import.meta?.env) {
    return import.meta.env.VITE_STREAMING_URL || "";
  }
  return "";
}

function normaliseEventTypes(message) {
  const types = new Set();
  if (!message) {
    return { eventTypes: ["message"], payload: message };
  }

  const candidate = (value) => {
    if (typeof value === "string" && value.trim()) {
      types.add(value.trim());
    }
  };

  candidate(message.type);
  candidate(message.event);
  candidate(message.channel);
  candidate(message.resource);

  const payload =
    message.payload ?? message.data ?? message.detail ?? (typeof message === "object" ? message : null);

  if (payload && typeof payload === "object") {
    candidate(payload.type);
    candidate(payload.event);
    candidate(payload.channel);
    candidate(payload.resource);
  }

  if (!types.size) {
    types.add("message");
  }

  return { eventTypes: Array.from(types), payload: payload ?? message };
}

function createError(message) {
  if (message instanceof Error) {
    return message;
  }
  const error = new Error(message || "Streaming connection error");
  error.name = "WebSocketError";
  return error;
}

export class WebSocketManager {
  constructor(url, options = {}) {
    this.url = url || getDefaultUrl();
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.autoReconnect = this.options.autoReconnect !== false;
    this.socket = null;
    this.reconnectTimer = null;
    this.manualClose = false;
    this.manualReconnect = false;
    this.reconnectAttempts = 0;
    this.status = "idle";
    this.lastError = null;
    this.subscribers = new Map();
    this.statusListeners = new Set();
  }

  updateOptions(options = {}) {
    this.options = { ...this.options, ...options };
    if (options.autoReconnect !== undefined) {
      this.autoReconnect = options.autoReconnect !== false;
    }
    if (options.url) {
      this.url = options.url;
    }
  }

  connect() {
    if (
      this.socket &&
      typeof globalThis !== "undefined" &&
      typeof globalThis.WebSocket === "function" &&
      (this.socket.readyState === globalThis.WebSocket.OPEN ||
        this.socket.readyState === globalThis.WebSocket.CONNECTING)
    ) {
      return;
    }

    if (!this.url) {
      const error = createError("Aucune URL de streaming configurée.");
      this.#updateStatus("error", error);
      return;
    }

    if (typeof globalThis === "undefined" || typeof globalThis.WebSocket !== "function") {
      const error = createError("WebSocket non pris en charge dans cet environnement.");
      this.#updateStatus("unsupported", error);
      return;
    }

    try {
      this.#updateStatus("connecting");
      const socket = new globalThis.WebSocket(this.url);
      this.socket = socket;

      socket.onopen = () => {
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
        this.reconnectAttempts = 0;
        this.#updateStatus("open");
      };

      socket.onmessage = (event) => {
        try {
          const data = typeof this.options.parse === "function" ? this.options.parse(event.data) : event.data;
          const { eventTypes, payload } = normaliseEventTypes(data);
          this.#notifySubscribers(eventTypes, payload, data);
        } catch (error) {
          console.error("Message WebSocket invalide", error);
        }
      };

      socket.onerror = () => {
        const error = createError("Erreur sur le flux temps réel");
        this.#updateStatus("error", error);
      };

      socket.onclose = (event) => {
        this.socket = null;
        const wasManualClose = this.manualClose;
        const requestedReconnect = this.manualReconnect;
        this.manualClose = false;
        this.manualReconnect = false;

        const closeError =
          event && event.code !== 1000
            ? createError(`Connexion fermée (code ${event.code})`)
            : null;

        if (closeError) {
          this.lastError = closeError;
        }

        this.#updateStatus("closed", closeError || this.lastError);

        if (requestedReconnect) {
          this.connect();
          return;
        }

        if (!wasManualClose && this.autoReconnect) {
          this.#scheduleReconnect();
        }
      };
    } catch (error) {
      this.#updateStatus("error", createError(error));
      this.#scheduleReconnect();
    }
  }

  disconnect({ preventReconnect = false } = {}) {
    this.manualClose = preventReconnect;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      try {
        this.socket.close();
      } catch (error) {
        console.error("Impossible de fermer le WebSocket", error);
      }
    } else if (preventReconnect) {
      this.#updateStatus("closed", null);
      this.manualClose = false;
    }
  }

  reconnect() {
    this.manualReconnect = true;
    this.disconnect({ preventReconnect: true });
    if (!this.socket) {
      this.connect();
    }
  }

  subscribe(types, handler) {
    if (typeof handler !== "function") {
      return () => {};
    }

    const typeList = Array.isArray(types) && types.length ? types : ["*"];
    typeList.forEach((type) => {
      const key = type || "*";
      if (!this.subscribers.has(key)) {
        this.subscribers.set(key, new Set());
      }
      this.subscribers.get(key).add(handler);
    });

    return () => {
      typeList.forEach((type) => {
        const key = type || "*";
        const bucket = this.subscribers.get(key);
        if (!bucket) {
          return;
        }
        bucket.delete(handler);
        if (!bucket.size) {
          this.subscribers.delete(key);
        }
      });
    };
  }

  onStatusChange(listener) {
    if (typeof listener !== "function") {
      return () => {};
    }
    this.statusListeners.add(listener);
    listener({ status: this.status, error: this.lastError, attempt: this.reconnectAttempts });
    return () => {
      this.statusListeners.delete(listener);
    };
  }

  publish(eventType, payload, rawMessage) {
    if (!eventType) {
      return;
    }
    const raw =
      rawMessage && typeof rawMessage === "object"
        ? rawMessage
        : { type: eventType, payload: payload ?? null };
    this.#notifySubscribers([eventType], payload, raw);
  }

  dispose() {
    this.disconnect({ preventReconnect: true });
    this.subscribers.clear();
    this.statusListeners.clear();
    this.socket = null;
  }

  #scheduleReconnect() {
    if (!this.autoReconnect) {
      return;
    }
    if (this.reconnectTimer) {
      return;
    }
    this.reconnectAttempts += 1;
    const baseDelay = Number(this.options.reconnectDelay) || 1000;
    const maxDelay = Number(this.options.maxReconnectDelay) || baseDelay * 6;
    const delay = Math.min(baseDelay * 2 ** (this.reconnectAttempts - 1), maxDelay);
    this.#updateStatus("reconnecting", this.lastError);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  #notifySubscribers(eventTypes, payload, rawMessage) {
    const wildcardHandlers = this.subscribers.get("*");

    eventTypes.forEach((eventType) => {
      const handlers = new Set();
      const bucket = this.subscribers.get(eventType);
      if (bucket) {
        bucket.forEach((handler) => handlers.add(handler));
      }
      if (wildcardHandlers) {
        wildcardHandlers.forEach((handler) => handlers.add(handler));
      }
      handlers.forEach((handler) => {
        try {
          handler({ type: eventType, payload, message: rawMessage, manager: this });
        } catch (error) {
          console.error("Erreur dans un abonné WebSocket", error);
        }
      });
    });
  }

  #updateStatus(status, error = null) {
    this.status = status;
    if (error) {
      this.lastError = error;
    }
    const snapshot = { status, error: error || null, attempt: this.reconnectAttempts };
    this.statusListeners.forEach((listener) => {
      try {
        listener(snapshot);
      } catch (listenerError) {
        console.error("Erreur dans un écouteur de statut WebSocket", listenerError);
      }
    });
  }
}

let sharedClient;

export function getWebSocketClient(options = {}) {
  const url = options.url || getDefaultUrl();
  if (!sharedClient || sharedClient.url !== url) {
    sharedClient = new WebSocketManager(url, options);
  } else if (options && Object.keys(options).length) {
    sharedClient.updateOptions(options);
  }
  return sharedClient;
}

export function resetWebSocketClient() {
  if (sharedClient) {
    sharedClient.dispose();
  }
  sharedClient = undefined;
}

const defaultClient = getWebSocketClient();

export default defaultClient;
