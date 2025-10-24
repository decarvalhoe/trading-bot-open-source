import React, { useEffect, useMemo, useState } from "react";
import useApi from "../hooks/useApi.js";

const STATUS_PRESENTATION = {
  success: { label: "Terminé", className: "badge--success" },
  completed: { label: "Terminé", className: "badge--success" },
  ready: { label: "Prêt", className: "badge--success" },
  running: { label: "En cours", className: "badge--info" },
  processing: { label: "En cours", className: "badge--info" },
  pending: { label: "En file", className: "badge--warning" },
  queued: { label: "En file", className: "badge--warning" },
  failure: { label: "Échec", className: "badge--critical" },
  failed: { label: "Échec", className: "badge--critical" },
};

function normaliseReport(entry, index) {
  if (!entry || typeof entry !== "object") {
    return null;
  }
  const reportType =
    entry.report_type || entry.reportType || entry.title || "Rapport personnalisé";
  const period = entry.period || entry.coverage || null;
  const generatedAt = entry.generated_at || entry.generatedAt || null;
  const downloadUrl = entry.download_url || entry.downloadUrl || null;
  const filename = entry.filename || entry.fileName || null;
  const status = entry.status || entry.state || null;
  const identifier =
    entry.id || entry.identifier || entry.uid || entry.uuid || entry.slug || null;
  const uid = identifier ? String(identifier) : `report-${index}`;
  return {
    uid,
    identifier: identifier ? String(identifier) : null,
    reportType,
    period,
    generatedAt,
    downloadUrl,
    filename,
    status,
  };
}

function formatDate(value) {
  if (!value) {
    return null;
  }
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return typeof value === "string" ? value : String(value);
  }
  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function resolveStatus(status) {
  if (!status || typeof status !== "string") {
    return null;
  }
  const key = status.toLowerCase();
  if (STATUS_PRESENTATION[key]) {
    return STATUS_PRESENTATION[key];
  }
  return { label: status, className: "badge--info" };
}

function ensurePageSize(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return 5;
  }
  return Math.max(1, Math.floor(numeric));
}

async function triggerDownload(report, setError, setDownloading, downloadReport) {
  const { downloadUrl, reportType, filename, uid } = report;
  if (!downloadUrl) {
    setError("Téléchargement indisponible pour ce rapport.");
    return;
  }
  setError(null);
  setDownloading(uid);
  try {
    const blob = await downloadReport(downloadUrl);
    if (typeof window === "undefined") {
      return;
    }
    const navigatorUrl = window.URL || URL;
    if (navigatorUrl && typeof navigatorUrl.createObjectURL === "function") {
      const objectUrl = navigatorUrl.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename || `${reportType.replace(/\s+/g, "-").toLowerCase()}.bin`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      if (typeof navigatorUrl.revokeObjectURL === "function") {
        navigatorUrl.revokeObjectURL(objectUrl);
      }
    } else if (typeof window.open === "function") {
      window.open(downloadUrl, "_blank", "noopener");
    }
  } catch (error) {
    console.error("Impossible de télécharger le rapport", error);
    setError("Téléchargement impossible pour le moment.");
  } finally {
    setDownloading(null);
  }
}

function ReportsList({ reports = [], pageSize = 5 }) {
  const { reports: reportsApi } = useApi();
  const normalisedReports = useMemo(() => {
    if (!Array.isArray(reports)) {
      return [];
    }
    return reports
      .map((entry, index) => normaliseReport(entry, index))
      .filter(Boolean);
  }, [reports]);

  const size = ensurePageSize(pageSize);
  const [page, setPage] = useState(0);
  const [downloading, setDownloading] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setPage(0);
  }, [normalisedReports.length, size]);

  useEffect(() => {
    setError(null);
  }, [page]);

  const totalPages = Math.max(1, Math.ceil(normalisedReports.length / size));
  const clampedPage = Math.min(page, totalPages - 1);
  const start = clampedPage * size;
  const currentItems = normalisedReports.slice(start, start + size);

  const handlePrevious = () => {
    setPage((current) => Math.max(0, current - 1));
  };

  const handleNext = () => {
    setPage((current) => Math.min(totalPages - 1, current + 1));
  };

  const handleDownload = (report) => {
    triggerDownload(report, setError, setDownloading, (endpoint) => reportsApi.download(endpoint));
  };

  if (!normalisedReports.length) {
    return (
      <div className="reports-center">
        <p className="text text--muted">Aucun rapport disponible pour le moment.</p>
        {error ? (
          <p role="alert" className="reports-error">
            {error}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="reports-center">
      <ul className="reports-list" role="list">
        {currentItems.map((report) => {
          const status = resolveStatus(report.status);
          const generated = formatDate(report.generatedAt);
          const isDownloading = downloading === report.uid;
          return (
            <li className="reports-list__item" role="listitem" key={report.uid}>
              <div className="reports-list__meta">
                <span className="reports-list__title heading heading--md">
                  {report.reportType}
                </span>
                <p className="reports-list__period text text--muted">
                  {report.period ? `Période : ${report.period}` : "Période non précisée"}
                  {generated ? ` · Généré le ${generated}` : ""}
                </p>
                {status ? (
                  <span className={`badge ${status.className} reports-list__status`}>
                    {status.label}
                  </span>
                ) : null}
              </div>
              <div className="reports-list__actions">
                <button
                  type="button"
                  className="button button--primary"
                  onClick={() => handleDownload(report)}
                  disabled={!report.downloadUrl || isDownloading}
                >
                  {isDownloading ? "Téléchargement…" : "Télécharger"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      <div className="reports-pagination">
        <span>
          Page {clampedPage + 1} / {totalPages}
        </span>
        <div className="reports-pagination__controls">
          <button
            type="button"
            className="button button--ghost"
            onClick={handlePrevious}
            disabled={clampedPage === 0}
          >
            Précédent
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={handleNext}
            disabled={clampedPage >= totalPages - 1}
          >
            Suivant
          </button>
        </div>
      </div>
      {error ? (
        <p role="alert" className="reports-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export default ReportsList;
