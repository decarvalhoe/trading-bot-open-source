import { useMemo } from "react";
import {
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

function formatLabel(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return String(timestamp);
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
        label: formatLabel(parsed),
      };
      entry[seriesKey] = value;
      if (typeof pnl === "number") {
        entry[`${seriesKey}__pnl`] = pnl;
      }
      points.set(iso, entry);
    });
  });

  const data = Array.from(points.values()).sort((a, b) => {
    const aTime = new Date(a.timestamp).getTime();
    const bTime = new Date(b.timestamp).getTime();
    return aTime - bTime;
  });

  return { data, seriesMeta };
}

export function PortfolioChart({ history = [], currency: fallbackCurrency = "$" }) {
  const { data, seriesMeta } = useMemo(() => normaliseHistory(history), [history]);

  const activeCurrency = useMemo(() => {
    if (!Array.isArray(history)) {
      return fallbackCurrency;
    }
    const match = history.find((item) => item && item.currency);
    return match?.currency || fallbackCurrency;
  }, [history, fallbackCurrency]);

  if (!seriesMeta.length || !data.length) {
    return (
      <div className="chart-container__status" role="status">
        Données historiques indisponibles pour le moment.
      </div>
    );
  }

  const tooltipContent = ({ active, payload, label }) => {
    if (!active || !payload?.length) {
      return null;
    }
    return (
      <div className="chart-tooltip">
        <p className="chart-tooltip__title">{label}</p>
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

  return (
    <ResponsiveContainer width="100%" height={320} debounce={200}>
      <LineChart data={data} margin={{ top: 20, right: 24, left: 12, bottom: 12 }}>
        <CartesianGrid stroke="#1f2a4d" strokeDasharray="4 8" />
        <XAxis
          dataKey="label"
          tick={{ fill: "#cbd5f5", fontSize: 12 }}
          axisLine={{ stroke: "#334155" }}
          tickLine={false}
        />
        <YAxis
          tickFormatter={(value) => formatCurrency(value, activeCurrency)}
          tick={{ fill: "#cbd5f5", fontSize: 12 }}
          axisLine={{ stroke: "#334155" }}
          tickLine={false}
          width={120}
        />
        <Tooltip content={tooltipContent} cursor={{ stroke: "#475569", strokeWidth: 1 }} />
        <Legend
          verticalAlign="top"
          align="right"
          wrapperStyle={{ color: "#cbd5f5" }}
          formatter={(_, entry) => {
            const meta = seriesMeta.find((item) => item.key === entry.dataKey);
            if (!meta) {
              return entry.value;
            }
            return meta.owner ? `${meta.label} · ${meta.owner}` : meta.label;
          }}
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
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export default PortfolioChart;
