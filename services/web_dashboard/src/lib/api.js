const DEFAULT_ENVIRONMENT = import.meta.env.VITE_API_ENV || import.meta.env.VITE_API_ENVIRONMENT || "local";

const ENVIRONMENT_URLS = {
  local: import.meta.env.VITE_API_URL_LOCAL,
  development: import.meta.env.VITE_API_URL_DEVELOPMENT,
  staging: import.meta.env.VITE_API_URL_STAGING,
  production: import.meta.env.VITE_API_URL_PRODUCTION,
  test: import.meta.env.VITE_API_URL_TEST,
};

const TOKEN_STORAGE_KEY =
  import.meta.env.VITE_API_TOKEN_STORAGE_KEY || "trading-bot-dashboard.jwt";

function normaliseBaseUrl(url) {
  if (!url) {
    return "";
  }
  return String(url).replace(/\/$/, "");
}

function isAbsoluteUrl(value) {
  return /^https?:\/\//i.test(value);
}

function buildQueryString(params = {}) {
  const entries = Object.entries(params).filter(([, value]) =>
    value !== undefined && value !== null && value !== ""
  );
  if (!entries.length) {
    return "";
  }
  const query = new URLSearchParams();
  entries.forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined && item !== null) {
          query.append(key, String(item));
        }
      });
      return;
    }
    query.set(key, String(value));
  });
  return query.toString();
}

function extractMessage(payload, fallback) {
  if (!payload) {
    return fallback;
  }
  if (typeof payload === "string") {
    return payload;
  }
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  if (payload.detail && typeof payload.detail.message === "string") {
    return payload.detail.message;
  }
  if (typeof payload.message === "string") {
    return payload.message;
  }
  return fallback;
}

export class ApiClient {
  constructor({ baseUrl, fetcher, tokenStorageKey } = {}) {
    this.baseUrl = normaliseBaseUrl(
      baseUrl ||
        import.meta.env.VITE_API_BASE_URL ||
        ENVIRONMENT_URLS[DEFAULT_ENVIRONMENT] ||
        ""
    );
    this.fetcher = typeof fetcher === "function" ? fetcher : fetch.bind(globalThis);
    this.tokenStorageKey = tokenStorageKey || TOKEN_STORAGE_KEY;
    this.token = this.#loadPersistedToken();

    this.auth = {
      login: (credentials, options = {}) =>
        this.request(options.endpoint || "/account/login", {
          method: "POST",
          body: credentials,
          credentials: "include",
          ...options,
        }),
      logout: (options = {}) =>
        this.request(options.endpoint || "/account/logout", {
          method: "POST",
          credentials: "include",
          ...options,
        }),
      session: (options = {}) =>
        this.request(options.endpoint || "/account/session", {
          method: "GET",
          credentials: "include",
          ...options,
        }),
    };

    this.alerts = {
      list: (options = {}) =>
        this.request(options.endpoint || "/alerts", {
          method: "GET",
          query: options.query,
          signal: options.signal,
        }),
      history: (options = {}) =>
        this.request(options.endpoint || "/alerts/history", {
          method: "GET",
          query: options.query,
          signal: options.signal,
        }),
      create: (payload, options = {}) =>
        this.request(options.endpoint || "/alerts", {
          method: "POST",
          body: payload,
        }),
      update: (id, payload, options = {}) => {
        const base = options.endpoint || "/alerts";
        return this.request(`${base}/${encodeURIComponent(id)}`, {
          method: "PUT",
          body: payload,
        });
      },
      remove: (id, options = {}) => {
        const base = options.endpoint || "/alerts";
        return this.request(`${base}/${encodeURIComponent(id)}`, {
          method: "DELETE",
        });
      },
      test: (payload, options = {}) =>
        this.request(options.endpoint || "/alerts/test", {
          method: "POST",
          body: payload,
        }),
    };

    this.marketplace = {
      listings: (options = {}) =>
        this.request(options.endpoint || "/marketplace/listings", {
          method: "GET",
          query: options.query,
          signal: options.signal,
        }),
      reviews: (id, options = {}) => {
        const base = options.endpoint || "/marketplace/listings";
        const endpoint = `${base}/${encodeURIComponent(id)}/reviews`;
        return this.request(endpoint, {
          method: "GET",
          signal: options.signal,
        });
      },
    };

    this.marketData = {
      price: (symbol, options = {}) => {
        const targetSymbol = (options.symbol ?? symbol ?? "").toString().trim();
        if (!targetSymbol) {
          return Promise.reject(new Error("Symbol is required"));
        }
        const endpoint = options.endpoint || `/market/${encodeURIComponent(targetSymbol)}/price`;
        const query = { ...(options.query || {}) };
        if (options.depth !== undefined && options.depth !== null) {
          query.depth = options.depth;
        }
        const finalQuery = Object.keys(query).length ? query : undefined;
        return this.request(endpoint, {
          method: "GET",
          signal: options.signal,
          query: finalQuery,
        });
      },
      orderBook: (symbol, options = {}) => {
        const targetSymbol = (options.symbol ?? symbol ?? "").toString().trim();
        if (!targetSymbol) {
          return Promise.reject(new Error("Symbol is required"));
        }
        const endpoint = options.endpoint || `/market/${encodeURIComponent(targetSymbol)}/order-book`;
        const query = { ...(options.query || {}) };
        if (options.depth !== undefined && options.depth !== null) {
          query.depth = options.depth;
        }
        const finalQuery = Object.keys(query).length ? query : undefined;
        return this.request(endpoint, {
          method: "GET",
          signal: options.signal,
          query: finalQuery,
        });
      },
    };

    this.reports = {
      list: (options = {}) =>
        this.request(options.endpoint || "/reports", {
          method: "GET",
          query: options.query,
          signal: options.signal,
        }),
      download: (endpoint, options = {}) =>
        this.request(endpoint, {
          method: "GET",
          headers: {
            Accept: "application/pdf,application/octet-stream",
            ...(options.headers || {}),
          },
          responseType: "blob",
          signal: options.signal,
        }),
    };

    this.strategies = {
      list: (options = {}) =>
        this.request(options.endpoint || "/strategies", {
          method: "GET",
          query: options.query,
          signal: options.signal,
        }),
      detail: (id, options = {}) =>
        this.request(`${options.endpoint || "/strategies"}/${encodeURIComponent(id)}`, {
          method: "GET",
          signal: options.signal,
        }),
      update: (id, payload, options = {}) =>
        this.request(`${options.endpoint || "/strategies"}/${encodeURIComponent(id)}`, {
          method: "PUT",
          body: payload,
        }),
      create: (payload, options = {}) =>
        this.request(options.endpoint || "/strategies", {
          method: "POST",
          body: payload,
        }),
      remove: (id, options = {}) =>
        this.request(`${options.endpoint || "/strategies"}/${encodeURIComponent(id)}`, {
          method: "DELETE",
        }),
      runBacktest: (payload, options = {}) =>
        this.request(options.endpoint || "/strategies/backtests", {
          method: "POST",
          body: payload,
        }),
      runLive: (payload, options = {}) =>
        this.request(options.endpoint || "/strategies/run", {
          method: "POST",
          body: payload,
        }),
      history: (options = {}) =>
        this.request(options.endpoint || "/strategies/history", {
          method: "GET",
          query: options.query,
        }),
    };

    this.orders = {
      list: (options = {}) =>
        this.request(options.endpoint || "/orders", {
          method: "GET",
          query: options.query,
          signal: options.signal,
        }),
      create: (payload, options = {}) =>
        this.request(options.endpoint || "/orders", {
          method: "POST",
          body: payload,
        }),
      cancel: (id, options = {}) =>
        this.request(`${options.endpoint || "/orders"}/${encodeURIComponent(id)}`, {
          method: "DELETE",
        }),
    };

    this.dashboard = {
      context: (options = {}) =>
        this.request(options.endpoint || "/dashboard/context", {
          method: "GET",
          signal: options.signal,
        }),
      history: (options = {}) =>
        this.request(options.endpoint || "/portfolios/history", {
          method: "GET",
          signal: options.signal,
        }),
    };

    this.onboarding = {
      fetch: (endpoint, options = {}) =>
        this.request(endpoint, {
          method: "GET",
          signal: options.signal,
        }),
      update: (endpoint, payload, options = {}) =>
        this.request(endpoint, {
          method: options.method || "POST",
          body: payload,
          signal: options.signal,
        }),
    };
  }

  setBaseUrl(baseUrl) {
    this.baseUrl = normaliseBaseUrl(baseUrl);
  }

  getBaseUrl() {
    return this.baseUrl;
  }

  setToken(token) {
    const next = token ? String(token) : "";
    this.token = next;
    this.#persistToken(next);
    return next;
  }

  getToken() {
    if (this.token) {
      return this.token;
    }
    this.token = this.#loadPersistedToken();
    return this.token;
  }

  clearToken() {
    this.token = "";
    this.#persistToken("");
  }

  buildUrl(path = "", query) {
    if (!path) {
      return this.baseUrl || "/";
    }
    const hasBase = Boolean(this.baseUrl);
    const trimmedPath = path.startsWith("/") ? path : `/${path}`;
    const resolved = isAbsoluteUrl(path)
      ? path
      : hasBase
      ? `${this.baseUrl}${trimmedPath}`
      : trimmedPath;
    if (!query || (typeof query === "object" && !Object.keys(query).length)) {
      return resolved;
    }
    const queryString = typeof query === "string" ? query : buildQueryString(query);
    if (!queryString) {
      return resolved;
    }
    return `${resolved}${resolved.includes("?") ? "&" : "?"}${queryString}`;
  }

  async request(path, options = {}) {
    const {
      method = "GET",
      body,
      headers = {},
      query,
      responseType = "json",
      credentials = undefined,
      signal,
      ...rest
    } = options;

    const url = this.buildUrl(path, query);

    const finalHeaders = new Headers({
      Accept: "application/json",
      ...headers,
    });

    const token = this.getToken();
    if (token && !finalHeaders.has("authorization")) {
      finalHeaders.set("Authorization", `Bearer ${token}`);
    }

    let payload = body;
    if (payload !== undefined && payload !== null && !(payload instanceof FormData) && !(payload instanceof Blob)) {
      finalHeaders.set("Content-Type", finalHeaders.get("Content-Type") || "application/json");
      payload = JSON.stringify(payload);
    }

    const response = await this.fetcher(url, {
      method,
      headers: finalHeaders,
      body: payload,
      credentials,
      signal,
      ...rest,
    });

    let parsed;
    if (responseType === "response") {
      parsed = response;
    } else if (responseType === "blob") {
      parsed = await response.blob();
    } else if (responseType === "text") {
      parsed = await response.text();
    } else {
      const contentType = response.headers?.get?.("content-type") || "";
      if (contentType.includes("application/json")) {
        parsed = await response.json();
      } else {
        const text = await response.text();
        try {
          parsed = text ? JSON.parse(text) : null;
        } catch (error) {
          parsed = text;
        }
      }
    }

    if (!response.ok) {
      const message = extractMessage(parsed, `HTTP ${response.status}`);
      const error = new Error(message);
      error.status = response.status;
      error.payload = parsed;
      throw error;
    }

    return parsed;
  }

  #persistToken(token) {
    if (typeof window === "undefined" || !window.localStorage) {
      return;
    }
    if (!this.tokenStorageKey) {
      return;
    }
    if (token) {
      window.localStorage.setItem(this.tokenStorageKey, token);
    } else {
      window.localStorage.removeItem(this.tokenStorageKey);
    }
  }

  #loadPersistedToken() {
    if (typeof window === "undefined" || !window.localStorage || !this.tokenStorageKey) {
      return "";
    }
    const persisted = window.localStorage.getItem(this.tokenStorageKey);
    return persisted || "";
  }
}

export const apiClient = new ApiClient();

export default apiClient;
