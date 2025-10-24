import apiClient from "../lib/api.js";

export async function login(endpoint, credentials) {
  return apiClient.auth.login(credentials, { endpoint });
}

export async function fetchSession(endpoint) {
  return apiClient.auth.session({ endpoint });
}

export async function logout(endpoint) {
  return apiClient.auth.logout({ endpoint });
}

export async function fetchBrokerCredentials(endpoint) {
  return apiClient.request(endpoint, { method: "GET", credentials: "include" });
}

export async function updateBrokerCredentials(endpoint, payload) {
  return apiClient.request(endpoint, {
    method: "PUT",
    body: payload,
    credentials: "include"
  });
}

export function normalizeSession(payload) {
  if (!payload || typeof payload !== "object") {
    return { authenticated: false, user: null, token: null };
  }
  return {
    authenticated: Boolean(payload.authenticated),
    user: payload.user && typeof payload.user === "object" ? payload.user : null,
    token:
      typeof payload.token === "string"
        ? payload.token
        : typeof payload.access_token === "string"
        ? payload.access_token
        : null
  };
}
