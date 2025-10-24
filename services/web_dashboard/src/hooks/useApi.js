import { useEffect, useMemo } from "react";
import {
  useMutation as useReactQueryMutation,
  useQuery as useReactQuery,
  useQueryClient,
} from "@tanstack/react-query";
import apiClient from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";

export function useApi(options = {}) {
  const context = typeof useAuth === "function" ? useAuth() : null;
  const providedToken = options.token;
  const token = providedToken ?? context?.token ?? context?.user?.token ?? null;
  const status = context?.status;
  const queryClient = useQueryClient();

  useEffect(() => {
    if (providedToken !== undefined) {
      if (providedToken) {
        apiClient.setToken(providedToken);
      } else {
        apiClient.clearToken();
      }
      return;
    }

    if (token) {
      apiClient.setToken(token);
      return;
    }

    if (status === "anonymous" || status === "error") {
      apiClient.clearToken();
    }
  }, [token, providedToken, status]);

  return useMemo(
    () => ({
      client: apiClient,
      auth: apiClient.auth,
      alerts: apiClient.alerts,
      reports: apiClient.reports,
      marketplace: apiClient.marketplace,
      marketData: apiClient.marketData,
      strategies: apiClient.strategies,
      orders: apiClient.orders,
      dashboard: apiClient.dashboard,
      onboarding: apiClient.onboarding,
      queryClient,
      useQuery: useReactQuery,
      useMutation: useReactQueryMutation,
    }),
    [queryClient]
  );
}

export default useApi;
