import React, { useCallback, useEffect, useMemo, useState } from "react";
import AlertForm from "./AlertForm.jsx";
import AlertTable from "./AlertTable.jsx";
import useApi from "../hooks/useApi.js";
import useWebSocket from "../hooks/useWebSocket.js";

function generateId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `alert-${Math.random().toString(36).slice(2, 10)}`;
}

function normaliseRuleDefinition(rule, fallbackSymbol = "") {
  if (!rule || typeof rule !== "object") {
    return {
      symbol: fallbackSymbol,
      timeframe: null,
      conditions: {
        pnl: { enabled: false, operator: "below", value: null },
        drawdown: { enabled: false, operator: "above", value: null },
        indicators: [],
      },
    };
  }
  const symbol = typeof rule.symbol === "string" ? rule.symbol : fallbackSymbol;
  const conditions = rule.conditions || {};
  return {
    symbol: symbol || fallbackSymbol,
    timeframe: rule.timeframe || null,
    conditions: {
      pnl: {
        enabled: Boolean(conditions?.pnl?.enabled),
        operator: conditions?.pnl?.operator || "below",
        value:
          conditions?.pnl?.value !== undefined && conditions?.pnl?.value !== null
            ? Number(conditions.pnl.value)
            : null,
      },
      drawdown: {
        enabled: Boolean(conditions?.drawdown?.enabled),
        operator: conditions?.drawdown?.operator || "above",
        value:
          conditions?.drawdown?.value !== undefined && conditions?.drawdown?.value !== null
            ? Number(conditions.drawdown.value)
            : null,
      },
      indicators: Array.isArray(conditions?.indicators)
        ? conditions.indicators.map((indicator) => ({
            id: indicator.id || `indicator-${Math.random().toString(36).slice(2)}`,
            name: indicator.name || "RSI",
            operator: indicator.operator || "above",
            value:
              indicator.value !== undefined && indicator.value !== null
                ? Number(indicator.value)
                : 0,
            lookback:
              indicator.lookback !== undefined && indicator.lookback !== null
                ? Number(indicator.lookback)
                : null,
            enabled: indicator.enabled !== undefined ? Boolean(indicator.enabled) : true,
          }))
        : [],
    },
  };
}

function normaliseChannels(channels) {
  if (!Array.isArray(channels)) {
    return [];
  }
  return channels.map((channel, index) => ({
    type: channel?.type || "email",
    target: channel?.target || "",
    enabled: channel?.enabled !== undefined ? Boolean(channel.enabled) : true,
    _internalId: channel?.id || `channel-${index}`,
  }));
}

function normaliseAlert(alert) {
  if (!alert || typeof alert !== "object") {
    return null;
  }
  const risk = typeof alert.risk === "string" ? alert.risk : alert.risk?.value || "info";
  const createdAt = alert.created_at || alert.createdAt || new Date().toISOString();
  return {
    id: String(alert.id ?? alert.title ?? generateId()),
    title: alert.title || "Alerte",
    detail: alert.detail || "",
    risk,
    acknowledged: Boolean(alert.acknowledged),
    created_at: createdAt,
    rule: normaliseRuleDefinition(alert.rule, alert.symbol || ""),
    channels: normaliseChannels(alert.channels),
    throttle_seconds: Number.isFinite(alert.throttle_seconds)
      ? Number(alert.throttle_seconds)
      : 0,
  };
}

function normaliseList(alerts) {
  if (!Array.isArray(alerts)) {
    return [];
  }
  return alerts
    .map((item) => normaliseAlert(item))
    .filter(Boolean)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

function extractRealtimeDetail(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  if (Array.isArray(payload.items) || payload.message || payload.type) {
    return payload;
  }
  if (payload.payload && typeof payload.payload === "object") {
    return extractRealtimeDetail(payload.payload);
  }
  if (payload.detail && typeof payload.detail === "object") {
    return extractRealtimeDetail(payload.detail);
  }
  return null;
}

function AlertManager({
  initialAlerts = [],
  endpoint = "/alerts",
  authToken = "",
  enableInitialFetch = true,
}) {
  const baseEndpoint = useMemo(() => endpoint.replace(/\/$/, ""), [endpoint]);
  const apiOptions = authToken ? { token: authToken } : {};
  const { alerts: alertsApi, useQuery, useMutation, queryClient } = useApi(apiOptions);
  const { subscribe, isConnected, status: streamingStatus, error: streamingError } = useWebSocket();
  const queryKey = useMemo(() => ["alerts", baseEndpoint], [baseEndpoint]);
  const [alerts, setAlerts] = useState(() => normaliseList(initialAlerts));
  const [formMode, setFormMode] = useState("create");
  const [activeAlert, setActiveAlert] = useState(null);
  const [formError, setFormError] = useState(null);
  const [banner, setBanner] = useState(null);
  const [pendingId, setPendingId] = useState(null);

  const fetchEnabled = enableInitialFetch && Boolean(baseEndpoint);
  const pollingInterval = isConnected ? false : 15000;

  const {
    data: fetchedAlerts = normaliseList(initialAlerts),
    isFetching,
    isLoading,
    error: fetchError,
    refetch,
  } = useQuery({
    queryKey,
    enabled: fetchEnabled,
    initialData: normaliseList(initialAlerts),
    refetchInterval: pollingInterval,
    refetchOnWindowFocus: !isConnected,
    refetchIntervalInBackground: !isConnected,
    queryFn: async () => {
      const payload = await alertsApi.list({ endpoint: baseEndpoint });
      const items = Array.isArray(payload?.items)
        ? payload.items
        : Array.isArray(payload)
        ? payload
        : [];
      return normaliseList(items);
    },
  });

  useEffect(() => {
    setAlerts(fetchedAlerts);
  }, [fetchedAlerts]);

  useEffect(() => {
    if (fetchError) {
      setBanner({
        type: "error",
        message: fetchError.message || "Impossible de récupérer les alertes.",
      });
    }
  }, [fetchError]);

  useEffect(() => {
    const applyRealtimeUpdate = (detail) => {
      if (!detail || !Array.isArray(detail.items)) {
        return;
      }
      const nextAlerts = normaliseList(detail.items);
      setAlerts(nextAlerts);
      queryClient.setQueryData(queryKey, nextAlerts);
      if (detail.message) {
        const type = detail.type || "info";
        setBanner({ type, message: detail.message });
      }
    };

    const unsubscribeUpdates = subscribe(["alerts", "alerts.update"], (event) => {
      const detail =
        extractRealtimeDetail(event.payload) || extractRealtimeDetail(event.message?.payload);
      if (detail) {
        applyRealtimeUpdate(detail);
      }
    });

    const unsubscribeFallback = subscribe(["alerts.fallback"], (event) => {
      const detail =
        extractRealtimeDetail(event.payload) || extractRealtimeDetail(event.message?.payload);
      if (detail) {
        applyRealtimeUpdate(detail);
        const message =
          detail.message || "Connexion temps réel indisponible. Données issues du dernier instantané.";
        setBanner({ type: detail.type || "warning", message });
      }
    });

    const unsubscribeErrors = subscribe(["alerts.error"], (event) => {
      const detail =
        extractRealtimeDetail(event.payload) || extractRealtimeDetail(event.message?.payload);
      const message = detail?.message || "Connexion temps réel impossible pour les alertes.";
      setBanner({ type: "error", message });
    });

    return () => {
      unsubscribeUpdates();
      unsubscribeFallback();
      unsubscribeErrors();
    };
  }, [queryClient, queryKey, subscribe]);

  useEffect(() => {
    if (!isConnected && (streamingStatus === "error" || streamingStatus === "unsupported")) {
      if (streamingError) {
        setBanner((current) => current || { type: "error", message: streamingError.message });
      } else {
        setBanner((current) =>
          current || {
            type: "warning",
            message: "Flux temps réel indisponible. Rafraîchissement par sondage activé.",
          }
        );
      }
    }
  }, [isConnected, streamingStatus, streamingError]);

  const createAlert = useMutation({
    mutationFn: (data) => alertsApi.create(data, { endpoint: baseEndpoint }),
    onSuccess: (result) => {
      const created = normaliseAlert(result);
      if (created) {
        setAlerts((previous) => normaliseList([created, ...previous]));
        queryClient.setQueryData(queryKey, (previous) =>
          normaliseList([created, ...(Array.isArray(previous) ? previous : [])])
        );
      }
      queryClient.invalidateQueries({ queryKey });
      setBanner({ type: "success", message: "Alerte créée avec succès." });
      setFormMode("create");
      setActiveAlert(null);
      setFormError(null);
    },
    onError: (error) => {
      setFormError(error.message || "Impossible de créer l'alerte.");
    },
  });

  const updateAlert = useMutation({
    mutationFn: (data) => {
      if (!activeAlert) {
        throw new Error("Alerte introuvable.");
      }
      return alertsApi.update(activeAlert.id, data, { endpoint: baseEndpoint });
    },
    onSuccess: (result) => {
      const updated = normaliseAlert({ ...activeAlert, ...result });
      if (updated) {
        setAlerts((previous) =>
          normaliseList(
            previous.map((item) => (item.id === updated.id ? { ...item, ...updated } : item))
          )
        );
        queryClient.setQueryData(queryKey, (previous) =>
          normaliseList(
            (Array.isArray(previous) ? previous : []).map((item) =>
              item.id === updated.id ? { ...item, ...updated } : item
            )
          )
        );
      }
      queryClient.invalidateQueries({ queryKey });
      setBanner({ type: "success", message: "Alerte mise à jour." });
      setFormMode("create");
      setActiveAlert(null);
      setFormError(null);
    },
    onError: (error) => {
      setFormError(error.message || "Impossible de mettre à jour l'alerte.");
    },
  });

  const deleteAlert = useMutation({
    mutationFn: (alertId) => alertsApi.remove(alertId, { endpoint: baseEndpoint }),
    onSuccess: (_, alertId) => {
      setAlerts((previous) => previous.filter((item) => item.id !== alertId));
      queryClient.setQueryData(queryKey, (previous) =>
        normaliseList((Array.isArray(previous) ? previous : []).filter((item) => item.id !== alertId))
      );
      setBanner({ type: "success", message: "Alerte supprimée." });
      if (activeAlert && activeAlert.id === alertId) {
        setFormMode("create");
        setActiveAlert(null);
      }
    },
    onError: (error) => {
      setBanner({ type: "error", message: error.message || "Impossible de supprimer l'alerte." });
    },
    onSettled: () => {
      setPendingId(null);
      queryClient.invalidateQueries({ queryKey });
    },
  });

  const handleCreate = useCallback(
    async (data) => {
      try {
        await createAlert.mutateAsync(data);
      } catch (error) {
        // l'erreur est gérée dans onError
      }
    },
    [createAlert]
  );

  const handleEdit = useCallback((alert) => {
    setFormMode("edit");
    setActiveAlert(alert);
    setFormError(null);
    setBanner(null);
  }, []);

  const handleCancelEdit = useCallback(() => {
    setFormMode("create");
    setActiveAlert(null);
    setFormError(null);
  }, []);

  const handleUpdate = useCallback(
    async (data) => {
      try {
        await updateAlert.mutateAsync(data);
      } catch (error) {
        // handled by onError
      }
    },
    [updateAlert]
  );

  const handleDelete = useCallback(
    async (alert) => {
      if (!alert) {
        return;
      }
      const confirmed =
        typeof window !== "undefined" ? window.confirm(`Supprimer l'alerte "${alert.title}" ?`) : true;
      if (!confirmed) {
        return;
      }
      setPendingId(alert.id);
      try {
        await deleteAlert.mutateAsync(alert.id);
      } catch (error) {
        // handled by onError
      }
    },
    [deleteAlert]
  );

  const loading = fetchEnabled && (isLoading || (isFetching && alerts.length === 0));
  const submitting = createAlert.isPending || updateAlert.isPending;

  return (
    <section className="alerts-manager" aria-labelledby="alerts-title">
      {banner ? (
        <div
          className={`alerts-manager__banner alerts-manager__banner--${banner.type}`}
          role={banner.type === "error" ? "alert" : "status"}
        >
          {banner.message}
        </div>
      ) : null}
      <div className="alerts-manager__grid">
        <div className="alerts-manager__form">
          <h3 className="heading heading--md">
            {formMode === "edit" ? "Modifier l'alerte" : "Créer une alerte"}
          </h3>
          <AlertForm
            mode={formMode}
            initialAlert={activeAlert}
            onSubmit={formMode === "edit" ? handleUpdate : handleCreate}
            onCancel={handleCancelEdit}
            submitting={submitting}
            error={formError}
          />
        </div>
        <div className="alerts-manager__list">
          <AlertTable
            alerts={alerts}
            loading={loading}
            onEdit={handleEdit}
            onDelete={handleDelete}
            pendingId={pendingId}
          />
        </div>
      </div>
    </section>
  );
}

export default AlertManager;
