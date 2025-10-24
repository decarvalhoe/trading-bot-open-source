import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import { bootstrap } from "../bootstrap";
import { fetchSession, login as apiLogin, logout as apiLogout } from "../account/api";

const AuthContext = createContext({
  status: "loading",
  user: null,
  error: null,
  login: async () => {},
  logout: async () => {},
});

const DEFAULT_ENDPOINTS = {
  login: "/account/login",
  logout: "/account/logout",
  session: "/account/session",
};

function resolveEndpoints() {
  const authConfig = bootstrap?.config?.auth || {};
  return {
    login: authConfig.loginEndpoint || DEFAULT_ENDPOINTS.login,
    logout: authConfig.logoutEndpoint || DEFAULT_ENDPOINTS.logout,
    session: authConfig.sessionEndpoint || DEFAULT_ENDPOINTS.session,
  };
}

export function AuthProvider({ children }) {
  const endpoints = useMemo(resolveEndpoints, []);
  const [state, setState] = useState({ status: "loading", user: null, error: null });

  const refreshSession = useCallback(async () => {
    setState((prev) => ({ ...prev, status: "loading" }));
    try {
      const session = await fetchSession(endpoints.session);
      if (session?.authenticated && session.user) {
        setState({ status: "authenticated", user: session.user, error: null });
      } else {
        setState({ status: "anonymous", user: null, error: null });
      }
    } catch (error) {
      setState({ status: "error", user: null, error: error.message || "Session invalide" });
    }
  }, [endpoints.session]);

  useEffect(() => {
    refreshSession();
  }, [refreshSession]);

  const login = useCallback(
    async (credentials) => {
      try {
        setState((prev) => ({ ...prev, status: "loading", error: null }));
        await apiLogin(endpoints.login, credentials);
        await refreshSession();
        return { ok: true };
      } catch (error) {
        setState({ status: "anonymous", user: null, error: error.message || "Connexion impossible" });
        return { ok: false, error };
      }
    },
    [endpoints.login, refreshSession]
  );

  const logout = useCallback(async () => {
    try {
      await apiLogout(endpoints.logout);
    } finally {
      await refreshSession();
    }
  }, [endpoints.logout, refreshSession]);

  const value = useMemo(
    () => ({
      ...state,
      login,
      logout,
      refresh: refreshSession,
      endpoints,
    }),
    [state, login, logout, refreshSession, endpoints]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

AuthProvider.propTypes = {
  children: PropTypes.node.isRequired,
};

export function useAuth() {
  return useContext(AuthContext);
}

export default AuthContext;
