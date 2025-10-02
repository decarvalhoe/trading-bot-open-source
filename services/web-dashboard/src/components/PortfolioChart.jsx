import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Brush,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const PALETTE = [
  "#38bdf8",
  "#22c55e",
  "#f97316",
  "#a855f7",
  "#eab308",
  "#ec4899",
];

function slugify(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .toLowerCase();
}

function formatCurrency(value, currencySymbol = "$") {
  const amount = Number.isFinite(Number(value)) ? Number(value) : 0;
  const formatted = amount.toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${formatted} ${currencySymbol}`.trim();
}

function formatSigned(value, currencySymbol = "$") {
  const amount = Number.isFinite(Number(value)) ? Number(value) : 0;
  const sign = amount >= 0 ? "+" : "-";
  return `${sign}${Math.abs(amount).toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currencySymbol}`.trim();
}

function formatLabel(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
}

export function normaliseHistory(items = []) {
  const points = new Map();
  const seriesMeta = [];

  items.forEach((series, index) => {
    if (!series || typeof series !== "object") {
      return;
    }
    const name = series.name || `Portfolio ${index + 1}`;
    const seriesKey = name;
    const color = PALETTE[index % PALETTE.length];
    const owner = series.owner || null;
    const currency = series.currency || "$";

    seriesMeta.push({
      key: seriesKey,
      label: name,
      owner,
      color,
      slug: slugify(name),
      currency,
    });

    (series.series || []).forEach((point) => {
      if (!point || typeof point !== "object") {
        return;
      }
      const timestamp = point.timestamp;
      const value = Number(point.value ?? point.balance ?? 0);
      const pnl = point.pnl;
      const parsed = new Date(timestamp);
      if (Number.isNaN(parsed.getTime())) {
        return;
      }
      const iso = parsed.toISOString();
      const entry = points.get(iso) || {
        timestamp: iso,
        timestampValue: parsed.getTime(),
        label: formatLabel(parsed),
      };
      entry[seriesKey] = value;
      if (typeof pnl === "number") {
        entry[`${seriesKey}__pnl`] = pnl;
      }
      points.set(iso, entry);
    });
  });

  const data = Array.from(points.values()).sort((a, b) => a.timestampValue - b.timestampValue);

  return { data, seriesMeta };
}

export function PortfolioChart({ history = [], currency: fallbackCurrency = "$" }) {
  const { data, seriesMeta } = useMemo(() => normaliseHistory(history), [history]);
  const chartContainerRef = useRef(null);
  const [activeSeriesKeys, setActiveSeriesKeys] = useState([]);
  const [range, setRange] = useState({ startIndex: 0, endIndex: 0 });
  const [viewDomain, setViewDomain] = useState(null);
  const [isExporting, setIsExporting] = useState(false);

  const activeCurrency = useMemo(() => {
    if (!Array.isArray(history)) {
      return fallbackCurrency;
    }
    const match = history.find((item) => item && item.currency);
    return match?.currency || fallbackCurrency;
  }, [history, fallbackCurrency]);

  useEffect(() => {
    const keys = seriesMeta.map((item) => item.key);
    setActiveSeriesKeys((current) => {
      if (!current.length) {
        return keys;
      }
      const available = new Set(keys);
      const filtered = current.filter((key) => available.has(key));
      return filtered.length ? filtered : keys;
    });
  }, [seriesMeta]);

  useEffect(() => {
    if (!data.length) {
      setRange({ startIndex: 0, endIndex: 0 });
      setViewDomain(null);
      return;
    }
    setRange({ startIndex: 0, endIndex: data.length - 1 });
    setViewDomain([data[0].timestampValue, data[data.length - 1].timestampValue]);
  }, [data]);

  if (!seriesMeta.length || !data.length) {
    return (
      <div className="chart-container__status" role="status">
        Données historiques indisponibles pour le moment.
      </div>
    );
  }

  const visibleSeriesMeta = useMemo(
    () => seriesMeta.filter((item) => activeSeriesKeys.includes(item.key)),
    [seriesMeta, activeSeriesKeys]
  );

  const zoomedData = useMemo(() => {
    if (!viewDomain || viewDomain.length !== 2) {
      return data;
    }
    const [start, end] = viewDomain;
    return data.filter((point) => {
      const value = point.timestampValue;
      return value >= start && value <= end;
    });
  }, [data, viewDomain]);

  const tooltipContent = ({ active, payload, label }) => {
    if (!active || !payload?.length) {
      return null;
    }
    const derivedLabel =
      typeof label === "number"
        ? formatLabel(label)
        : payload[0]?.payload?.label || String(label);
    return (
      <div className="chart-tooltip">
        <p className="chart-tooltip__title">{derivedLabel}</p>
        <ul className="chart-tooltip__list">
          {payload.map((entry) => {
            const meta = seriesMeta.find((item) => item.key === entry.dataKey);
            const pointPnl = entry.payload?.[`${entry.dataKey}__pnl`];
            return (
              <li key={entry.dataKey} className="chart-tooltip__item">
                <span className="chart-tooltip__label">
                  <span
                    aria-hidden="true"
                    style={{
                      display: "inline-block",
                      width: "0.75rem",
                      height: "0.75rem",
                      borderRadius: "9999px",
                      backgroundColor: entry.color || meta?.color || "#38bdf8",
                    }}
                  />
                  {meta?.label || entry.name || entry.dataKey}
                  {meta?.owner ? ` · ${meta.owner}` : ""}
                </span>
                <span className="chart-tooltip__value">
                  {formatCurrency(entry.value, activeCurrency)}
                  {typeof pointPnl === "number"
                    ? ` (${formatSigned(pointPnl, activeCurrency)})`
                    : ""}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    );
  };

  const handleSeriesToggle = useCallback((key) => {
    setActiveSeriesKeys((prev) => {
      if (prev.includes(key)) {
        if (prev.length === 1) {
          return prev;
        }
        return prev.filter((item) => item !== key);
      }
      return [...prev, key];
    });
  }, []);

  const handleLegendClick = useCallback(
    (entry) => {
      if (entry && entry.dataKey) {
        handleSeriesToggle(entry.dataKey);
      }
    },
    [handleSeriesToggle]
  );

  const handleRangeChange = useCallback(
    (next) => {
      if (!next) {
        return;
      }
      setRange((current) => {
        const maxIndex = data.length - 1;
        const startIndex = Math.max(0, Math.min(maxIndex, next.startIndex ?? current.startIndex));
        const endIndex = Math.max(startIndex, Math.min(maxIndex, next.endIndex ?? current.endIndex));
        const startPoint = data[startIndex];
        const endPoint = data[endIndex];
        if (startPoint && endPoint) {
          setViewDomain([startPoint.timestampValue, endPoint.timestampValue]);
        }
        return { startIndex, endIndex };
      });
    },
    [data]
  );

  const handleBrushChange = useCallback(
    (next) => {
      if (!next || typeof next.startIndex !== "number" || typeof next.endIndex !== "number") {
        return;
      }
      handleRangeChange({ startIndex: next.startIndex, endIndex: next.endIndex });
    },
    [handleRangeChange]
  );

  const handleStartSliderChange = useCallback(
    (event) => {
      const value = Number.parseInt(event.target.value, 10);
      handleRangeChange({ startIndex: Number.isNaN(value) ? 0 : value });
    },
    [handleRangeChange]
  );

  const handleEndSliderChange = useCallback(
    (event) => {
      const value = Number.parseInt(event.target.value, 10);
      handleRangeChange({ endIndex: Number.isNaN(value) ? data.length - 1 : value });
    },
    [handleRangeChange, data.length]
  );

  const handleResetZoom = useCallback(() => {
    if (!data.length) {
      return;
    }
    setRange({ startIndex: 0, endIndex: data.length - 1 });
    setViewDomain([data[0].timestampValue, data[data.length - 1].timestampValue]);
  }, [data]);

  const zoomLabel = useMemo(() => {
    if (!data.length) {
      return "Aucune donnée";
    }
    const startPoint = data[range.startIndex];
    const endPoint = data[range.endIndex];
    if (!startPoint || !endPoint) {
      return "Affichage complet";
    }
    const isFullRange =
      data[0].timestamp === startPoint.timestamp &&
      data[data.length - 1].timestamp === endPoint.timestamp;
    const startLabel = formatLabel(startPoint.timestampValue);
    const endLabel = formatLabel(endPoint.timestampValue);
    return isFullRange ? "Affichage complet" : `Zoom : ${startLabel} → ${endLabel}`;
  }, [data, range]);

  const handleExportCsv = useCallback(() => {
    if (!visibleSeriesMeta.length || !zoomedData.length) {
      return;
    }
    const headers = ["Date", ...visibleSeriesMeta.map((meta) => meta.label)];
    const rows = zoomedData.map((point) => [
      point.label,
      ...visibleSeriesMeta.map((meta) => {
        const value = point[meta.key];
        return Number.isFinite(value) ? value : "";
      }),
    ]);
    const serialiseCell = (cell) => {
      if (typeof cell === "number") {
        return cell.toString();
      }
      const text = String(cell ?? "");
      if (text.includes(";") || text.includes("\"")) {
        return `"${text.replace(/"/g, '""')}"`;
      }
      return text;
    };
    const csv = [headers, ...rows]
      .map((line) => line.map(serialiseCell).join(";"))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `portfolios-${new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-")}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }, [visibleSeriesMeta, zoomedData]);

  const exportSvgAsPng = useCallback(
    (node) =>
      new Promise((resolve, reject) => {
        const svgNode = node?.querySelector("svg");
        if (!svgNode) {
          reject(new Error("SVG introuvable"));
          return;
        }
        const cloned = svgNode.cloneNode(true);
        if (!cloned.getAttribute("xmlns")) {
          cloned.setAttribute("xmlns", "http://www.w3.org/2000/svg");
        }
        const serializer = new XMLSerializer();
        const svgString = serializer.serializeToString(cloned);
        const width = Number.parseFloat(cloned.getAttribute("width")) || svgNode.clientWidth || 800;
        const height = Number.parseFloat(cloned.getAttribute("height")) || svgNode.clientHeight || 320;
        const blob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const image = new Image();
        image.onload = () => {
          try {
            const canvas = document.createElement("canvas");
            canvas.width = width;
            canvas.height = height;
            const context = canvas.getContext("2d");
            if (!context) {
              throw new Error("Canvas context non disponible");
            }
            context.fillStyle = "#0f172a";
            context.fillRect(0, 0, canvas.width, canvas.height);
            context.drawImage(image, 0, 0, width, height);
            URL.revokeObjectURL(url);
            resolve(canvas.toDataURL("image/png"));
          } catch (canvasError) {
            URL.revokeObjectURL(url);
            reject(canvasError);
          }
        };
        image.onerror = (event) => {
          URL.revokeObjectURL(url);
          reject(event instanceof ErrorEvent ? event.error : new Error("Export PNG impossible"));
        };
        image.src = url;
      }),
    []
  );

  const handleExportPng = useCallback(async () => {
    if (!chartContainerRef.current) {
      return;
    }
    try {
      setIsExporting(true);
      const dataUrl = await exportSvgAsPng(chartContainerRef.current);
      const anchor = document.createElement("a");
      anchor.href = dataUrl;
      anchor.download = `portfolios-${new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-")}.png`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } catch (error) {
      console.error("Impossible d'exporter le graphique en PNG", error);
    } finally {
      setIsExporting(false);
    }
  }, [exportSvgAsPng]);

  return (
    <div className="portfolio-chart" ref={chartContainerRef}>
      <div className="chart-toolbar" role="group" aria-label="Options du graphique des portefeuilles">
        <div className="chart-toolbar__group chart-toolbar__series" role="group" aria-label="Sélection de portefeuilles">
          {seriesMeta.map((meta) => {
            const checkboxId = `portfolio-toggle-${meta.slug}`;
            return (
              <label key={meta.key} className="chart-toolbar__checkbox" htmlFor={checkboxId}>
                <input
                  id={checkboxId}
                  type="checkbox"
                  checked={activeSeriesKeys.includes(meta.key)}
                  onChange={() => handleSeriesToggle(meta.key)}
                />
                <span className="chart-toolbar__swatch" aria-hidden="true" style={{ backgroundColor: meta.color }} />
                <span>{meta.owner ? `${meta.label} · ${meta.owner}` : meta.label}</span>
              </label>
            );
          })}
        </div>
        <div className="chart-toolbar__actions">
          <div className="chart-toolbar__zoom" role="status" aria-live="polite">
            {zoomLabel}
          </div>
          <div className="chart-toolbar__sliders" role="group" aria-label="Contrôle du zoom">
            <label className="chart-toolbar__slider">
              <span>Début</span>
              <input
                type="range"
                min="0"
                max={Math.max(range.endIndex, 0)}
                value={range.startIndex}
                onInput={handleStartSliderChange}
                onChange={handleStartSliderChange}
                aria-label="Début du zoom"
              />
            </label>
            <label className="chart-toolbar__slider">
              <span>Fin</span>
              <input
                type="range"
                min={range.startIndex}
                max={Math.max(data.length - 1, range.startIndex)}
                value={range.endIndex}
                onInput={handleEndSliderChange}
                onChange={handleEndSliderChange}
                aria-label="Fin du zoom"
              />
            </label>
            <button type="button" className="button button--ghost" onClick={handleResetZoom}>
              Réinitialiser le zoom
            </button>
          </div>
          <div className="chart-toolbar__downloads" role="group" aria-label="Exports du graphique">
            <button
              type="button"
              className="button button--secondary"
              onClick={handleExportCsv}
              disabled={!visibleSeriesMeta.length || !zoomedData.length}
            >
              Exporter CSV
            </button>
            <button
              type="button"
              className="button button--secondary"
              onClick={handleExportPng}
              disabled={isExporting}
            >
              {isExporting ? "Export PNG…" : "Exporter PNG"}
            </button>
          </div>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={320} debounce={200}>
        <LineChart data={data} margin={{ top: 20, right: 24, left: 12, bottom: 12 }}>
          <CartesianGrid stroke="#1f2a4d" strokeDasharray="4 8" />
          <XAxis
            dataKey="timestampValue"
            type="number"
            domain={viewDomain || ["auto", "auto"]}
            tick={{ fill: "#cbd5f5", fontSize: 12 }}
            axisLine={{ stroke: "#334155" }}
            tickLine={false}
            tickFormatter={(value) => formatLabel(value)}
          />
          <YAxis
            tickFormatter={(value) => formatCurrency(value, activeCurrency)}
            tick={{ fill: "#cbd5f5", fontSize: 12 }}
            axisLine={{ stroke: "#334155" }}
            tickLine={false}
            width={120}
          />
          <Tooltip
            content={tooltipContent}
            cursor={{ stroke: "#475569", strokeWidth: 1 }}
            labelFormatter={(value) => formatLabel(value)}
          />
          <Legend
            verticalAlign="top"
            align="right"
            wrapperStyle={{ color: "#cbd5f5" }}
            onClick={handleLegendClick}
            formatter={(_, entry) => {
              const meta = seriesMeta.find((item) => item.key === entry.dataKey);
              if (!meta) {
                return entry.value;
              }
              return meta.owner ? `${meta.label} · ${meta.owner}` : meta.label;
            }}
          />
          <Brush
            dataKey="timestampValue"
            startIndex={range.startIndex}
            endIndex={range.endIndex}
            onChange={handleBrushChange}
            travellerWidth={12}
            height={24}
            stroke="#38bdf8"
            tickFormatter={(value) => formatLabel(value)}
          />
          {seriesMeta.map((meta) => (
            <Line
              key={meta.key}
              type="monotone"
              dataKey={meta.key}
              name={meta.label}
              stroke={meta.color}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              className={`portfolio-line portfolio-line--${meta.slug}`}
              legendType="circle"
              hide={!activeSeriesKeys.includes(meta.key)}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default PortfolioChart;
