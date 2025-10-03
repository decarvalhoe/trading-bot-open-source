const DEFAULT_HEADERS = {
  Accept: "application/json",
  "Content-Type": "application/json"
};

async function parseError(response) {
  try {
    const payload = await response.json();
    if (payload && typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload && payload.detail && payload.detail.message) {
      return payload.detail.message;
    }
    if (payload && payload.message) {
      return payload.message;
    }
  } catch (error) {
    // Fallback to plain text below.
  }
  const text = await response.text();
  return text || `Erreur ${response.status}`;
}

async function requestJson(endpoint, options = {}) {
  const response = await fetch(endpoint, {
    credentials: "include",
    ...options,
    headers: {
      ...DEFAULT_HEADERS,
      ...(options.headers || {})
    }
  });

  if (!response.ok) {
    const message = await parseError(response);
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) {
    return null;
  }

  try {
    return await response.json();
  } catch (error) {
    throw new Error("Réponse du serveur invalide");
  }
}

export async function login(endpoint, credentials) {
  return requestJson(endpoint, {
    method: "POST",
    body: JSON.stringify(credentials)
  });
}

export async function fetchSession(endpoint) {
  return requestJson(endpoint, { method: "GET" });
}

export async function logout(endpoint) {
  return requestJson(endpoint, {
    method: "POST"
  });
}

export function normalizeSession(payload) {
  if (!payload || typeof payload !== "object") {
    return { authenticated: false, user: null };
  }
  return {
    authenticated: Boolean(payload.authenticated),
    user: payload.user && typeof payload.user === "object" ? payload.user : null
  };
}
