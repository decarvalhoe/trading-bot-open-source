import React, { useEffect, useId, useMemo, useRef, useState } from "react";

const scriptPromises = new Map();

function normaliseSymbol(symbol) {
  if (!symbol || typeof symbol !== "string") {
    return "";
  }
  return symbol.trim().toUpperCase();
}

function resolveSymbolFromMap(strategy, mapping) {
  if (!strategy || !mapping || typeof mapping !== "object") {
    return "";
  }
  const index = new Map();
  Object.entries(mapping).forEach(([key, value]) => {
    if (typeof key === "string" && typeof value === "string") {
      index.set(key.toLowerCase(), value);
    }
  });

  const candidates = [];
  if (strategy.id) {
    candidates.push(String(strategy.id));
  }
  if (strategy.name) {
    candidates.push(String(strategy.name));
  }
  if (strategy.strategy_type) {
    candidates.push(String(strategy.strategy_type));
  }
  candidates.push("__default__");

  for (const candidate of candidates) {
    const match = index.get(candidate.toLowerCase());
    if (match) {
      return match;
    }
  }
  return "";
}

function ensureTradingViewScript(url) {
  if (typeof window !== "undefined" && window.TradingView && typeof window.TradingView.widget === "function") {
    return Promise.resolve();
  }
  if (!url) {
    return Promise.reject(new Error("Aucun bundle TradingView disponible"));
  }
  if (scriptPromises.has(url)) {
    return scriptPromises.get(url);
  }
  const promise = new Promise((resolve, reject) => {
    if (typeof document === "undefined") {
      reject(new Error("Environnement non compatible avec le chargement du script TradingView"));
      return;
    }
    const script = document.createElement("script");
    script.src = url;
    script.type = "text/javascript";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = (event) => {
      reject(new Error("Impossible de charger la librairie TradingView"));
    };
    document.body.appendChild(script);
  });
  scriptPromises.set(url, promise);
  return promise;
}

async function persistOverlays(updateEndpoint, overlays) {
  const response = await fetch(updateEndpoint, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ overlays }),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (error) {
    payload = {};
  }
  if (!response.ok) {
    const detail = payload?.detail || payload?.message;
    const message = typeof detail === "string" ? detail : `HTTP ${response.status}`;
    throw new Error(message);
  }
  if (payload && Array.isArray(payload.overlays)) {
    return payload.overlays;
  }
  return overlays;
}

function TradingViewPanel({
  configEndpoint = "/config/tradingview",
  updateEndpoint = "/config/tradingview",
  selectedStrategy = null,
  symbol = "",
  onSymbolChange,
}) {
  const containerId = useId().replace(/[:]/g, "-");
  const containerRef = useRef(null);
  const widgetRef = useRef(null);
  const readyRef = useRef(false);
  const pendingSymbolRef = useRef("");
  const appliedOverlaysRef = useRef(new Set());
  const overlaysRef = useRef([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [config, setConfig] = useState(null);
  const [activeSymbol, setActiveSymbol] = useState(normaliseSymbol(symbol));
  const [overlays, setOverlays] = useState([]);
  const [overlayStatus, setOverlayStatus] = useState("idle");
  const [draftOverlay, setDraftOverlay] = useState({ title: "RSI", type: "indicator" });

  useEffect(() => {
    overlaysRef.current = overlays;
    if (!readyRef.current || !widgetRef.current) {
      return;
    }
    overlays.forEach((overlay) => {
      if (!overlay || !overlay.id) {
        return;
      }
      if (appliedOverlaysRef.current.has(overlay.id)) {
        return;
      }
      const chart = typeof widgetRef.current.chart === "function" ? widgetRef.current.chart() : null;
      if (!chart) {
        return;
      }
      if (overlay.type === "annotation") {
        if (typeof chart.createShape === "function") {
          const settings = overlay.settings && typeof overlay.settings === "object" ? overlay.settings : {};
          chart.createShape({
            text: overlay.title,
            shape: "label",
            ...settings,
          });
        }
      } else if (typeof chart.createStudy === "function") {
        const settings = overlay.settings && typeof overlay.settings === "object" ? overlay.settings : {};
        const inputs = Array.isArray(settings.inputs) ? settings.inputs : [];
        const options = settings.options && typeof settings.options === "object" ? settings.options : {};
        const overlayFlag = typeof settings.overlay === "boolean" ? settings.overlay : true;
        chart.createStudy(overlay.title, overlayFlag, inputs, options);
      }
      appliedOverlaysRef.current.add(overlay.id);
    });
  }, [overlays]);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setError(null);

    async function fetchConfig() {
      try {
        const response = await fetch(configEndpoint, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (cancelled) {
          return;
        }
        setConfig(payload);
        const storedOverlays = Array.isArray(payload.overlays) ? payload.overlays : [];
        setOverlays(storedOverlays);
        overlaysRef.current = storedOverlays;
        setStatus("ready");
      } catch (fetchError) {
        if (!cancelled) {
          setStatus("error");
          setError(fetchError);
        }
      }
    }

    fetchConfig();

    return () => {
      cancelled = true;
    };
  }, [configEndpoint]);

  useEffect(() => {
    if (status !== "ready" || !config || !containerRef.current) {
      return;
    }
    let disposed = false;

    async function initialiseWidget() {
      try {
        await ensureTradingViewScript(config.library_url);
        if (disposed) {
          return;
        }
        if (!window.TradingView || typeof window.TradingView.widget !== "function") {
          throw new Error("La librairie TradingView n'est pas disponible");
        }
        const initialSymbol = normaliseSymbol(
          activeSymbol ||
            resolveSymbolFromMap(selectedStrategy, config.symbol_map) ||
            config.default_symbol
        ) || "BINANCE:BTCUSDT";
        pendingSymbolRef.current = initialSymbol;
        const widget = window.TradingView.widget({
          symbol: initialSymbol,
          interval: "60",
          container: containerId,
          locale: "fr",
          autosize: true,
          timezone: "Etc/UTC",
          theme: "dark",
          studies_overrides: {},
        });
        widgetRef.current = widget;
        appliedOverlaysRef.current = new Set();
        if (typeof widget.onChartReady === "function") {
          widget.onChartReady(() => {
            if (disposed) {
              return;
            }
            readyRef.current = true;
            const targetSymbol = pendingSymbolRef.current || initialSymbol;
            if (targetSymbol && typeof widget.setSymbol === "function") {
              widget.setSymbol(targetSymbol, () => undefined);
            }
            overlaysRef.current.forEach((overlay) => {
              if (overlay && overlay.id) {
                const chart = typeof widget.chart === "function" ? widget.chart() : null;
                if (!chart) {
                  return;
                }
                if (overlay.type === "annotation") {
                  if (typeof chart.createShape === "function") {
                    const settings =
                      overlay.settings && typeof overlay.settings === "object"
                        ? overlay.settings
                        : {};
                    chart.createShape({
                      text: overlay.title,
                      shape: "label",
                      ...settings,
                    });
                  }
                } else if (typeof chart.createStudy === "function") {
                  const settings =
                    overlay.settings && typeof overlay.settings === "object" ? overlay.settings : {};
                  const inputs = Array.isArray(settings.inputs) ? settings.inputs : [];
                  const options =
                    settings.options && typeof settings.options === "object" ? settings.options : {};
                  const overlayFlag = typeof settings.overlay === "boolean" ? settings.overlay : true;
                  chart.createStudy(overlay.title, overlayFlag, inputs, options);
                }
                appliedOverlaysRef.current.add(overlay.id);
              }
            });
          });
        } else {
          readyRef.current = true;
        }
      } catch (initialisationError) {
        if (!disposed) {
          setStatus("error");
          setError(initialisationError);
        }
      }
    }

    initialiseWidget();

    return () => {
      disposed = true;
      readyRef.current = false;
      if (widgetRef.current && typeof widgetRef.current.remove === "function") {
        widgetRef.current.remove();
      }
      widgetRef.current = null;
      appliedOverlaysRef.current = new Set();
    };
  }, [status, config, containerId, activeSymbol, selectedStrategy]);

  const effectiveSymbol = useMemo(() => {
    if (!config) {
      return normaliseSymbol(symbol);
    }
    return (
      normaliseSymbol(symbol) ||
      normaliseSymbol(resolveSymbolFromMap(selectedStrategy, config.symbol_map)) ||
      normaliseSymbol(config.default_symbol)
    );
  }, [symbol, selectedStrategy, config]);

  useEffect(() => {
    if (!config) {
      return;
    }
    const resolved = effectiveSymbol || "";
    if (!resolved) {
      return;
    }
    if (resolved === activeSymbol) {
      pendingSymbolRef.current = resolved;
      return;
    }
    setActiveSymbol(resolved);
    pendingSymbolRef.current = resolved;
    if (readyRef.current && widgetRef.current && typeof widgetRef.current.setSymbol === "function") {
      widgetRef.current.setSymbol(resolved, () => undefined);
    }
    const parentSymbol = normaliseSymbol(symbol);
    if (onSymbolChange && resolved && resolved !== parentSymbol) {
      onSymbolChange(resolved);
    }
  }, [effectiveSymbol, config, activeSymbol, onSymbolChange, symbol]);

  const handleOverlaySubmit = async (event) => {
    event.preventDefault();
    const title = draftOverlay.title ? draftOverlay.title.trim() : "";
    if (!title) {
      return;
    }
    const overlayId = `overlay-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const baseSettings =
      draftOverlay.type === "annotation"
        ? { shape: "label", text: title }
        : { overlay: true, inputs: [], options: {} };
    const entry = {
      id: overlayId,
      title,
      type: draftOverlay.type,
      settings: baseSettings,
    };
    const previous = overlaysRef.current;
    const next = [...previous, entry];
    overlaysRef.current = next;
    setOverlays(next);
    setOverlayStatus("saving");
    try {
      const persisted = await persistOverlays(updateEndpoint, next);
      overlaysRef.current = persisted;
      setOverlays(persisted);
      setOverlayStatus("saved");
      setDraftOverlay({ title: "", type: draftOverlay.type });
    } catch (persistError) {
      overlaysRef.current = previous;
      setOverlays(previous);
      setOverlayStatus("error");
      console.error("Impossible de persister les overlays TradingView", persistError);
    }
  };

  if (status === "loading") {
    return (
      <div className="tradingview-panel" role="status">
        Chargement de la configuration TradingView…
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="tradingview-panel tradingview-panel--error" role="alert">
        Impossible d'initialiser le graphique TradingView.
      </div>
    );
  }

  return (
    <section className="tradingview-panel" aria-label="Graphique TradingView et overlays">
      <div
        id={containerId}
        ref={containerRef}
        className="tradingview-panel__chart"
        role="img"
        aria-label={`Graphique TradingView pour ${activeSymbol || "l'instrument sélectionné"}`}
      ></div>
      <form className="tradingview-panel__form" onSubmit={handleOverlaySubmit}>
        <label className="tradingview-panel__field">
          <span className="tradingview-panel__label">Nom de l'overlay</span>
          <input
            type="text"
            value={draftOverlay.title}
            onChange={(event) =>
              setDraftOverlay((current) => ({ ...current, title: event.target.value }))
            }
            placeholder="RSI"
          />
        </label>
        <label className="tradingview-panel__field">
          <span className="tradingview-panel__label">Type</span>
          <select
            value={draftOverlay.type}
            onChange={(event) =>
              setDraftOverlay((current) => ({ ...current, type: event.target.value }))
            }
          >
            <option value="indicator">Indicateur</option>
            <option value="annotation">Annotation</option>
          </select>
        </label>
        <button type="submit" className="button button--secondary">
          Ajouter l'overlay
        </button>
        {overlayStatus === "saving" && (
          <span className="tradingview-panel__status" role="status">
            Sauvegarde en cours…
          </span>
        )}
        {overlayStatus === "error" && (
          <span className="tradingview-panel__status tradingview-panel__status--error" role="alert">
            Impossible d'enregistrer l'overlay.
          </span>
        )}
        {overlayStatus === "saved" && (
          <span className="tradingview-panel__status tradingview-panel__status--success" role="status">
            Overlay enregistré.
          </span>
        )}
      </form>
      <ul className="tradingview-panel__overlays" aria-live="polite">
        {overlays.length === 0 && (
          <li className="tradingview-panel__overlays-empty">Aucun overlay enregistré.</li>
        )}
        {overlays.map((overlay) => (
          <li key={overlay.id} className="tradingview-panel__overlay">
            <strong>{overlay.title}</strong>
            <span className="tradingview-panel__overlay-type">
              {overlay.type === "annotation" ? "Annotation" : "Indicateur"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export { TradingViewPanel };
export default TradingViewPanel;
