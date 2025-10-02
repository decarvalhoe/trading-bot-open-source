import React, { useCallback, useEffect, useMemo, useState } from "react";
import AlertForm from "./AlertForm.jsx";
import AlertTable from "./AlertTable.jsx";

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

function AlertManager({
  initialAlerts = [],
  endpoint = "/alerts",
  authToken = "",
  enableInitialFetch = true,
}) {
  const [alerts, setAlerts] = useState(() => normaliseList(initialAlerts));
  const [loading, setLoading] = useState(false);
  const [formMode, setFormMode] = useState("create");
  const [activeAlert, setActiveAlert] = useState(null);
  const [formError, setFormError] = useState(null);
  const [banner, setBanner] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [pendingId, setPendingId] = useState(null);

  const baseEndpoint = useMemo(() => endpoint.replace(/\/$/, ""), [endpoint]);

  const buildHeaders = useCallback(
    (withBody = false) => {
      const headers = {
        Accept: "application/json",
      };
      if (withBody) {
        headers["Content-Type"] = "application/json";
      }
      if (authToken) {
        headers.Authorization = `Bearer ${authToken}`;
      }
      return headers;
    },
    [authToken]
  );

  const request = useCallback(
    async (method, resource = "", body) => {
      const path = resource ? `/${String(resource).replace(/^\//, "")}` : "";
      const url = `${baseEndpoint}${path}`;
      const response = await fetch(url, {
        method,
        headers: buildHeaders(body !== undefined),
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      let payload = null;
      const contentType = response.headers?.get?.("content-type") || "";
      if (contentType.includes("application/json")) {
        payload = await response.json();
      }
      if (!response.ok) {
        const detail = payload?.detail || payload?.message || payload?.error;
        const error = new Error(detail || "Le service d'alertes a renvoyé une erreur.");
        error.status = response.status;
        throw error;
      }
      return payload || {};
    },
    [baseEndpoint, buildHeaders]
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await request("GET");
      if (payload && Array.isArray(payload.items)) {
        setAlerts(normaliseList(payload.items));
      }
      setBanner(null);
    } catch (error) {
      setBanner({
        type: "error",
        message: error.message || "Impossible de récupérer les alertes.",
      });
    } finally {
      setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    if (!enableInitialFetch) {
      return;
    }
    refresh();
  }, [refresh, enableInitialFetch]);

  useEffect(() => {
    function handleRealtimeUpdate(event) {
      const detail = event.detail;
      if (!detail || !Array.isArray(detail.items)) {
        return;
      }
      setAlerts(normaliseList(detail.items));
      if (detail.message) {
        const type = detail.type || "info";
        setBanner({ type, message: detail.message });
      }
    }

    function handleRealtimeError(event) {
      const message = event.detail?.message || "Flux temps réel indisponible.";
      setBanner({ type: "error", message });
    }

    document.addEventListener("alerts:update", handleRealtimeUpdate);
    document.addEventListener("alerts:fallback", handleRealtimeUpdate);
    document.addEventListener("alerts:error", handleRealtimeError);
    return () => {
      document.removeEventListener("alerts:update", handleRealtimeUpdate);
      document.removeEventListener("alerts:fallback", handleRealtimeUpdate);
      document.removeEventListener("alerts:error", handleRealtimeError);
    };
  }, []);

  const handleCreate = useCallback(
    async (data) => {
      setSubmitting(true);
      setFormError(null);
      try {
        const payload = await request("POST", "", data);
        const created = normaliseAlert(payload);
        setAlerts((previous) => {
          if (!created) {
            return previous;
          }
          const existingIndex = previous.findIndex((item) => item.id === created.id);
          if (existingIndex >= 0) {
            const clone = [...previous];
            clone[existingIndex] = { ...clone[existingIndex], ...created };
            return normaliseList(clone);
          }
          return normaliseList([created, ...previous]);
        });
        setBanner({ type: "success", message: "Alerte créée avec succès." });
        setFormMode("create");
        setActiveAlert(null);
      } catch (error) {
        setFormError(error.message || "Impossible de créer l'alerte.");
      } finally {
        setSubmitting(false);
      }
    },
    [request]
  );

  const handleEdit = useCallback((alert) => {
    setFormMode("edit");
    setActiveAlert(alert);
    setFormError(null);
  }, []);

  const handleCancelEdit = useCallback(() => {
    setFormMode("create");
    setActiveAlert(null);
    setFormError(null);
  }, []);

  const handleUpdate = useCallback(
    async (data) => {
      if (!activeAlert) {
        return;
      }
      setSubmitting(true);
      setFormError(null);
      try {
        const payload = await request("PUT", activeAlert.id, data);
        const updated = normaliseAlert({ ...activeAlert, ...payload });
        setAlerts((previous) => {
          if (!updated) {
            return previous;
          }
          const index = previous.findIndex((item) => item.id === activeAlert.id);
          if (index < 0) {
            return previous;
          }
          const clone = [...previous];
          clone[index] = { ...clone[index], ...updated };
          return normaliseList(clone);
        });
        setBanner({ type: "success", message: "Alerte mise à jour." });
        setFormMode("create");
        setActiveAlert(null);
      } catch (error) {
        setFormError(error.message || "Impossible de mettre à jour l'alerte.");
      } finally {
        setSubmitting(false);
      }
    },
    [activeAlert, request]
  );

  const handleDelete = useCallback(
    async (alert) => {
      if (!alert) {
        return;
      }
      const confirmed = typeof window !== "undefined" ? window.confirm(`Supprimer l'alerte "${alert.title}" ?`) : true;
      if (!confirmed) {
        return;
      }
      setPendingId(alert.id);
      try {
        await request("DELETE", alert.id);
        setAlerts((previous) => previous.filter((item) => item.id !== alert.id));
        if (activeAlert && activeAlert.id === alert.id) {
          setFormMode("create");
          setActiveAlert(null);
        }
        setBanner({ type: "success", message: "Alerte supprimée." });
      } catch (error) {
        setBanner({ type: "error", message: error.message || "Impossible de supprimer l'alerte." });
      } finally {
        setPendingId(null);
      }
    },
    [activeAlert, request]
  );

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
