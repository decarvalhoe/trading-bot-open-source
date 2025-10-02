(function () {
  const bootstrapNode = document.getElementById("dashboard-bootstrap");
  if (!bootstrapNode || !bootstrapNode.textContent) {
    return;
  }

  let bootstrapData;
  try {
    bootstrapData = JSON.parse(bootstrapNode.textContent);
  } catch (error) {
    console.error("Impossible de parser la configuration du tableau de bord", error);
    return;
  }

  const initialState =
    bootstrapData.context ||
    {
      portfolios: [],
      transactions: [],
      alerts: [],
      strategies: [],
      logs: [],
      setups: { watchlists: [], fallback_reason: null },
      data_sources: {},
    };
  const streamingConfig = bootstrapData.streaming || {};
  const state = {
    current: JSON.parse(JSON.stringify(initialState)),
    fallback: JSON.parse(JSON.stringify(initialState)),
    setupsFallbackActive: false,
    sessionSnapshots: Object.create(null),
    received: { portfolios: false },
  };

  function ensureSetupsContainer(target) {
    if (!target.setups || typeof target.setups !== "object") {
      target.setups = { watchlists: [], fallback_reason: null };
      return target.setups;
    }
    const fallbackReason =
      target.setups.fallback_reason ?? target.setups.fallbackReason ?? null;
    let watchlists = target.setups.watchlists ?? target.setups.watchLists;
    if (!Array.isArray(watchlists)) {
      watchlists = [];
    }
    target.setups = { watchlists, fallback_reason: fallbackReason };
    return target.setups;
  }

  ensureSetupsContainer(state.current);
  ensureSetupsContainer(state.fallback);
  state.setupsFallbackActive = false;

  const alertsReactRoot = document.getElementById("alerts-manager");

  const selectors = {
    portfolios: document.querySelector(".portfolio-list"),
    transactions: document.querySelector(".card[aria-labelledby='transactions-title'] tbody"),
    alerts: alertsReactRoot ? null : document.querySelector(".alert-list"),
    strategies: document.querySelector(".strategy-table__body"),
    logs: document.getElementById("log-entries"),
    logFilter: document.getElementById("log-filter"),
    setups: document.querySelector(".inplay-setups__grid"),
    setupsStatus: document.getElementById("inplay-setups-status"),
    sessionFilter: document.getElementById("session-filter"),
  };

  const datasetNotices = {
    portfolios: {
      getContainer: () => selectors.portfolios,
      message:
        "Mode dégradé : les portefeuilles sont issus du dernier instantané disponible (order-router indisponible).",
    },
    transactions: {
      getContainer: () => selectors.transactions,
      message:
        "Mode dégradé : transactions simulées car l'historique du routeur d'ordres est inaccessible.",
    },
  };

  function getDatasetSource(dataset) {
    if (!state.current.data_sources || typeof state.current.data_sources !== "object") {
      return "unknown";
    }
    return state.current.data_sources[dataset] || "unknown";
  }

  function updateDatasetSource(dataset, mode) {
    if (!dataset) {
      return;
    }
    if (!state.current.data_sources || typeof state.current.data_sources !== "object") {
      state.current.data_sources = {};
    }
    if (mode) {
      state.current.data_sources[dataset] = mode;
    }
  }

  function updateDatasetNotice(dataset) {
    const descriptor = datasetNotices[dataset];
    if (!descriptor) {
      return;
    }
    const container = descriptor.getContainer ? descriptor.getContainer() : null;
    if (!container || !(container instanceof HTMLElement)) {
      return;
    }
    const status = getDatasetSource(dataset);
    const isFallback = status === "fallback" || status === "degraded";
    container.setAttribute("data-source", status);
    const cardBody = container.closest(".card__body");
    if (!cardBody) {
      return;
    }
    let notice = cardBody.querySelector(`[data-role='${dataset}-status']`);
    if (isFallback) {
      if (!notice) {
        notice = document.createElement("p");
        notice.dataset.role = `${dataset}-status`;
        notice.className = "text text--muted dataset-status dataset-status--warning";
        cardBody.insertBefore(notice, cardBody.firstChild);
      }
      notice.textContent = descriptor.message;
    } else if (notice) {
      notice.remove();
    }
  }

  const filters = {
    logStrategy: selectors.logFilter ? selectors.logFilter.value || "all" : "all",
    session: selectors.sessionFilter ? selectors.sessionFilter.value || "all" : "all",
  };

  const sessionLabels = {
    london: "Londres",
    new_york: "New York",
    asia: "Asie",
  };

  if (selectors.logFilter) {
    selectors.logFilter.addEventListener("change", (event) => {
      filters.logStrategy = event.target.value;
      renderLogs();
    });
  }

  if (selectors.sessionFilter) {
    selectors.sessionFilter.addEventListener("change", (event) => {
      const value = event.target.value || "all";
      filters.session = value;
      if (filters.session !== "all") {
        refreshSessionSnapshots(filters.session);
      } else {
        renderSetups();
      }
    });
  }

  function formatCurrency(value) {
    if (typeof value !== "number") {
      value = Number(value || 0);
    }
    return `${value.toFixed(2)} $`;
  }

  function formatTimestamp(value) {
    if (!value) {
      return "";
    }
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return date.toLocaleString("fr-FR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatProbability(value) {
    if (value === null || value === undefined) {
      return "—";
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return "—";
    }
    if (numeric >= 0 && numeric <= 1) {
      return `${Math.round(numeric * 100)} %`;
    }
    return `${Math.round(numeric)} %`;
  }

  function formatSessionLabel(value) {
    if (!value) {
      return "";
    }
    const key = value.toString().toLowerCase();
    if (Object.prototype.hasOwnProperty.call(sessionLabels, key)) {
      return sessionLabels[key];
    }
    return key
      .replace(/_/g, " ")
      .replace(/\b\w/g, (match) => match.toUpperCase());
  }

  function renderPortfolios() {
    const container = selectors.portfolios;
    if (!container) {
      return;
    }
    if (
      (!Array.isArray(state.current.portfolios) || state.current.portfolios.length === 0) &&
      !state.received.portfolios &&
      Array.isArray(state.fallback.portfolios)
    ) {
      state.current.portfolios = JSON.parse(JSON.stringify(state.fallback.portfolios));
    }
    updateDatasetNotice("portfolios");
    container.innerHTML = "";
    state.current.portfolios.forEach((portfolio) => {
      const item = document.createElement("li");
      item.className = "portfolio-list__item";
      item.innerHTML = `
        <div class="portfolio-list__title">
          <span class="badge badge--neutral" aria-label="Nom du portefeuille">${portfolio.name}</span>
          <span class="text text--muted">Géré par ${portfolio.owner}</span>
        </div>
        <div class="portfolio-list__value" aria-label="Valeur totale">
          ${formatCurrency(portfolio.total_value ?? portfolio.totalValue ?? (portfolio.holdings || []).reduce((sum, holding) => sum + (holding.quantity || 0) * (holding.current_price || holding.currentPrice || 0), 0))}
        </div>
        <table class="table" role="grid" aria-label="Positions du portefeuille ${portfolio.name}">
          <thead>
            <tr>
              <th scope="col">Symbole</th>
              <th scope="col">Quantité</th>
              <th scope="col">Px. moyen</th>
              <th scope="col">Px. actuel</th>
              <th scope="col">Valeur</th>
            </tr>
          </thead>
          <tbody>
            ${(portfolio.holdings || [])
              .map((holding) => {
                const quantity = Number(holding.quantity || 0);
                const averagePrice = Number(holding.average_price ?? holding.averagePrice ?? 0);
                const currentPrice = Number(holding.current_price ?? holding.currentPrice ?? 0);
                const marketValue = Number(holding.market_value ?? holding.marketValue ?? quantity * currentPrice);
                return `
                  <tr>
                    <td data-label="Symbole">${holding.symbol}</td>
                    <td data-label="Quantité">${quantity.toFixed(2)}</td>
                    <td data-label="Prix moyen">${formatCurrency(averagePrice)}</td>
                    <td data-label="Prix actuel">${formatCurrency(currentPrice)}</td>
                    <td data-label="Valeur">${formatCurrency(marketValue)}</td>
                  </tr>
                `;
              })
              .join("")}
          </tbody>
        </table>
      `;
      container.appendChild(item);
    });
  }

  function renderTransactions() {
    const container = selectors.transactions;
    if (!container) {
      return;
    }
    updateDatasetNotice("transactions");
    container.innerHTML = "";
    state.current.transactions.forEach((transaction) => {
      const row = document.createElement("tr");
      const quantity = Number(transaction.quantity || 0);
      const price = Number(transaction.price || 0);
      const side = (transaction.side || "").toLowerCase();
      const badgeClass = side === "buy" ? "success" : "warning";
      row.innerHTML = `
        <td data-label="Horodatage">${formatTimestamp(transaction.timestamp)}</td>
        <td data-label="Portefeuille">${transaction.portfolio}</td>
        <td data-label="Symbole">${transaction.symbol}</td>
        <td data-label="Sens">
          <span class="badge badge--${badgeClass}">${side.charAt(0).toUpperCase()}${side.slice(1)}</span>
        </td>
        <td data-label="Quantité">${quantity.toFixed(2)}</td>
        <td data-label="Prix">${formatCurrency(price)}</td>
      `;
      container.appendChild(row);
    });
  }

  function renderAlerts() {
    const container = selectors.alerts;
    if (!container) {
      return;
    }
    container.innerHTML = "";
    state.current.alerts.forEach((alert) => {
      const risk = (alert.risk && alert.risk.value) || alert.risk || "info";
      const createdAt = formatTimestamp(alert.created_at || alert.createdAt);
      const acknowledged = Boolean(alert.acknowledged);
      const item = document.createElement("li");
      item.className = "alert-list__item";
      const badgeClass = risk === "critical" ? "critical" : risk === "warning" ? "warning" : "info";
      item.innerHTML = `
        <div class="alert-list__status">
          <span class="badge badge--${badgeClass}">
            ${risk.charAt(0).toUpperCase()}${risk.slice(1)}
          </span>
        </div>
        <div class="alert-list__content">
          <h3 class="heading heading--md">${alert.title}</h3>
          <p class="text">${alert.detail}</p>
          <p class="text text--muted">
            Créée ${createdAt}
            · <span class="badge badge--${acknowledged ? "neutral" : "info"}" aria-label="${acknowledged ? "Alerte confirmée" : "Alerte non confirmée"}">
              ${acknowledged ? "Accusée" : "À traiter"}
            </span>
          </p>
        </div>
      `;
      container.appendChild(item);
    });
  }

  function updateSetupsStatus(message, tone = "info") {
    const statusNode = selectors.setupsStatus;
    if (!statusNode) {
      return;
    }
    const toneClass = tone ? ` inplay-setups__status--${tone}` : "";
    statusNode.className = `inplay-setups__status text${toneClass}`;
    statusNode.textContent = message || "";
  }

  function sanitiseSetupStatus(value) {
    if (!value) {
      return "pending";
    }
    if (typeof value === "string") {
      return value.toLowerCase();
    }
    if (value && typeof value === "object" && typeof value.value === "string") {
      return value.value.toLowerCase();
    }
    return "pending";
  }

  function sanitiseStrategySetup(raw) {
    if (!raw || typeof raw !== "object") {
      return null;
    }
    const strategy = (raw.strategy || raw.name || "").toString().trim();
    if (!strategy) {
      return null;
    }
    const entry = raw.entry ?? raw.entry_price ?? raw.entryPrice;
    const target = raw.target ?? raw.target_price ?? raw.targetPrice;
    const stop = raw.stop ?? raw.stop_price ?? raw.stopPrice;
    const probability = raw.probability ?? raw.confidence ?? raw.score;
    const updatedAt =
      raw.updated_at || raw.updatedAt || raw.received_at || raw.receivedAt || null;
    const sessionRaw =
      raw.session || raw.session_name || raw.sessionName || raw.market || null;
    let session = null;
    if (typeof sessionRaw === "string" && sessionRaw.trim()) {
      session = sessionRaw.trim().toLowerCase();
    }
    const reportUrlRaw = raw.report_url || raw.reportUrl || null;
    let reportUrl = null;
    if (typeof reportUrlRaw === "string" && reportUrlRaw.trim()) {
      reportUrl = reportUrlRaw.trim();
    }

    return {
      strategy,
      status: sanitiseSetupStatus(raw.status),
      entry: entry !== undefined && entry !== null ? Number(entry) : null,
      target: target !== undefined && target !== null ? Number(target) : null,
      stop: stop !== undefined && stop !== null ? Number(stop) : null,
      probability:
        probability !== undefined && probability !== null
          ? Number(probability)
          : null,
      updated_at: updatedAt,
      session,
      report_url: reportUrl,
    };
  }

  function sanitiseSymbolSetups(raw) {
    if (!raw || typeof raw !== "object") {
      return null;
    }
    const symbol = (raw.symbol || raw.ticker || "").toString().trim();
    if (!symbol) {
      return null;
    }
    const rawSetups = Array.isArray(raw.setups) ? raw.setups : [];
    const setups = rawSetups
      .map((setup) => sanitiseStrategySetup(setup))
      .filter((setup) => setup !== null);
    return { symbol, setups };
  }

  function sanitiseWatchlistSnapshot(raw, fallbackId) {
    if (!raw || typeof raw !== "object") {
      return null;
    }
    const identifier =
      (raw.id || raw.watchlist_id || raw.watchlistId || fallbackId || "")
        .toString()
        .trim();
    if (!identifier) {
      return null;
    }
    const rawSymbols = Array.isArray(raw.symbols) ? raw.symbols : [];
    const symbols = rawSymbols
      .map((symbol) => sanitiseSymbolSetups(symbol))
      .filter((symbol) => symbol !== null);
    return {
      id: identifier,
      updated_at: raw.updated_at || raw.updatedAt || null,
      symbols,
    };
  }

  function upsertWatchlist(target, snapshot) {
    const index = target.findIndex((entry) => entry && entry.id === snapshot.id);
    if (index >= 0) {
      target[index] = snapshot;
    } else {
      target.push(snapshot);
    }
  }

  function applyWatchlistSnapshot(snapshot) {
    const normalised = sanitiseWatchlistSnapshot(snapshot);
    if (!normalised) {
      return false;
    }
    ensureSetupsContainer(state.current);
    ensureSetupsContainer(state.fallback);
    upsertWatchlist(state.current.setups.watchlists, normalised);
    upsertWatchlist(
      state.fallback.setups.watchlists,
      JSON.parse(JSON.stringify(normalised))
    );
    state.current.setups.fallback_reason = null;
    state.fallback.setups.fallback_reason = null;
    state.setupsFallbackActive = false;
    updateSessionFilterOptions();
    if (state.sessionSnapshots && normalised.id) {
      Object.keys(state.sessionSnapshots).forEach((sessionKey) => {
        const cache = state.sessionSnapshots[sessionKey];
        if (!cache || typeof cache !== "object") {
          return;
        }
        if (cache[normalised.id]) {
          delete cache[normalised.id];
          if (!Object.keys(cache).length) {
            delete state.sessionSnapshots[sessionKey];
          }
        }
      });
    }
    return true;
  }

  function applyWatchlistPayload(payload) {
    if (!payload) {
      return false;
    }
    let applied = false;
    const candidates = [];
    if (Array.isArray(payload)) {
      candidates.push(...payload);
    } else {
      if (Array.isArray(payload.watchlists)) {
        candidates.push(...payload.watchlists);
      }
      if (Array.isArray(payload.items)) {
        candidates.push(...payload.items);
      }
      if (!candidates.length && (payload.symbols || payload.id || payload.watchlist_id)) {
        candidates.push(payload);
      }
    }

    candidates.forEach((candidate) => {
      if (applyWatchlistSnapshot(candidate)) {
        applied = true;
      }
    });

    if (applied) {
      renderSetups();
    }
    return applied;
  }

  function formatLevel(value) {
    if (value === null || value === undefined) {
      return "—";
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return "—";
    }
    return numeric.toFixed(2);
  }

  function appendMetric(metrics, label, value) {
    const dt = document.createElement("dt");
    dt.className = "setup-card__metric-label";
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.className = "setup-card__metric-value";
    dd.textContent = value;
    metrics.appendChild(dt);
    metrics.appendChild(dd);
  }

  function renderSetups() {
    const container = selectors.setups;
    if (!container) {
      return;
    }
    updateSessionFilterOptions();
    container.innerHTML = "";

    const setupsState = ensureSetupsContainer(state.current);
    const watchlists = Array.isArray(setupsState.watchlists)
      ? setupsState.watchlists
      : [];
    const fallbackReason =
      setupsState.fallback_reason ?? setupsState.fallbackReason ?? null;
    const sessionFilter = filters.session || "all";
    const overrides =
      sessionFilter !== "all" && state.sessionSnapshots
        ? state.sessionSnapshots[sessionFilter]
        : null;

    const watchlistEntries = [];
    const seenWatchlists = new Set();

    watchlists.forEach((watchlist) => {
      if (!watchlist || typeof watchlist !== "object") {
        return;
      }
      const watchlistId = (watchlist.id || "").toString();
      const override = overrides && watchlistId ? overrides[watchlistId] : null;
      watchlistEntries.push({
        id: watchlistId || (override && override.id) || "",
        symbols: Array.isArray(watchlist.symbols) ? watchlist.symbols : [],
        override,
      });
      if (watchlistId) {
        seenWatchlists.add(watchlistId);
      }
    });

    if (overrides) {
      Object.keys(overrides).forEach((watchlistId) => {
        if (seenWatchlists.has(watchlistId)) {
          return;
        }
        const snapshot = overrides[watchlistId];
        if (!snapshot || typeof snapshot !== "object") {
          return;
        }
        watchlistEntries.push({
          id: watchlistId || (snapshot.id || ""),
          symbols: Array.isArray(snapshot.symbols) ? snapshot.symbols : [],
          override: snapshot,
        });
      });
    }

    let cardCount = 0;
    watchlistEntries.forEach((entry) => {
      const watchlistId = (entry.id || "").toString();
      const symbols = Array.isArray(entry.override?.symbols)
        ? entry.override.symbols
        : entry.symbols;
      symbols.forEach((symbolEntry) => {
        const symbol = symbolEntry && symbolEntry.symbol ? symbolEntry.symbol : "";
        const setups = Array.isArray(symbolEntry.setups)
          ? symbolEntry.setups
          : [];
        setups.forEach((setup) => {
          if (!setup || typeof setup !== "object") {
            return;
          }
          const setupSession =
            typeof setup.session === "string" && setup.session.trim()
              ? setup.session.trim().toLowerCase()
              : null;
          if (sessionFilter !== "all" && setupSession !== sessionFilter) {
            return;
          }
          const strategy = (setup.strategy || "").toString() || "Stratégie";
          const statusValue = (setup.status || "pending").toString().toLowerCase();
          let badgeClass = "badge--info";
          if (statusValue === "validated") {
            badgeClass = "badge--success";
          } else if (statusValue === "failed") {
            badgeClass = "badge--critical";
          } else if (statusValue !== "pending") {
            badgeClass = "badge--warning";
          }
          const statusLabel =
            statusValue.charAt(0).toUpperCase() + statusValue.slice(1);

          const card = document.createElement("article");
          card.className = "setup-card";
          card.setAttribute("role", "listitem");

          const header = document.createElement("div");
          header.className = "setup-card__header";
          const strategyNode = document.createElement("span");
          strategyNode.className = "setup-card__strategy heading heading--md";
          strategyNode.textContent = strategy;
          const statusBadge = document.createElement("span");
          statusBadge.className = `badge ${badgeClass}`;
          statusBadge.textContent = statusLabel;
          header.appendChild(strategyNode);
          header.appendChild(statusBadge);
          card.appendChild(header);

          const meta = document.createElement("p");
          meta.className = "setup-card__meta text text--muted";
          const parts = [];
          if (symbol) {
            parts.push(symbol);
          }
          if (watchlistId) {
            parts.push(`Watchlist ${watchlistId}`);
          }
          if (setupSession) {
            parts.push(`Session ${formatSessionLabel(setupSession)}`);
          }
          if (setup.updated_at) {
            const updated = formatTimestamp(setup.updated_at);
            if (updated) {
              parts.push(`Maj ${updated}`);
            }
          }
          meta.textContent = parts.join(" · ");
          card.appendChild(meta);

          const metrics = document.createElement("dl");
          metrics.className = "setup-card__metrics";
          appendMetric(metrics, "Entrée", formatLevel(setup.entry));
          appendMetric(metrics, "Cible", formatLevel(setup.target));
          appendMetric(metrics, "Stop", formatLevel(setup.stop));
          appendMetric(metrics, "Probabilité", formatProbability(setup.probability));
          card.appendChild(metrics);

          if (setup.report_url) {
            const actions = document.createElement("div");
            actions.className = "setup-card__actions";
            const reportLink = document.createElement("a");
            reportLink.className = "button button--secondary";
            reportLink.href = setup.report_url;
            reportLink.target = "_blank";
            reportLink.rel = "noopener noreferrer";
            reportLink.textContent = "Voir le rapport";
            actions.appendChild(reportLink);
            card.appendChild(actions);
          }

          container.appendChild(card);
          cardCount += 1;
        });
      });
    });

    if (!cardCount) {
      const empty = document.createElement("p");
      empty.className = "text text--muted inplay-setups__empty";
      let statusMessage;
      let statusLevel = "info";
      if (fallbackReason) {
        statusMessage =
          fallbackReason ||
          "Aucun setup en temps réel n'est disponible pour le moment.";
        statusLevel = "warning";
      } else if (sessionFilter !== "all") {
        statusMessage = `Aucun setup disponible pour la session ${formatSessionLabel(
          sessionFilter
        )}.`;
      } else {
        statusMessage = "Aucun setup en temps réel n'est disponible pour le moment.";
      }
      empty.textContent = statusMessage;
      container.appendChild(empty);
      updateSetupsStatus(statusMessage, statusLevel);
    } else if (state.setupsFallbackActive) {
      updateSetupsStatus(
        fallbackReason ||
          "Flux indisponible : affichage du dernier instantané connu.",
        "warning"
      );
    } else if (fallbackReason) {
      updateSetupsStatus(fallbackReason, "warning");
    } else {
      updateSetupsStatus("Flux InPlay connecté.", "success");
    }
  }

  function collectSessionsFromWatchlists(watchlists, target) {
    watchlists.forEach((watchlist) => {
      if (!watchlist || typeof watchlist !== "object") {
        return;
      }
      const symbols = Array.isArray(watchlist.symbols) ? watchlist.symbols : [];
      symbols.forEach((symbolEntry) => {
        if (!symbolEntry || typeof symbolEntry !== "object") {
          return;
        }
        const setups = Array.isArray(symbolEntry.setups)
          ? symbolEntry.setups
          : [];
        setups.forEach((setup) => {
          if (!setup || typeof setup !== "object") {
            return;
          }
          const sessionValue =
            typeof setup.session === "string" && setup.session.trim()
              ? setup.session.trim().toLowerCase()
              : null;
          if (sessionValue) {
            target.add(sessionValue);
          }
        });
      });
    });
  }

  function updateSessionFilterOptions() {
    const select = selectors.sessionFilter;
    if (!select) {
      return;
    }
    const available = new Set();
    const currentSetups = ensureSetupsContainer(state.current);
    const fallbackSetups = ensureSetupsContainer(state.fallback);
    collectSessionsFromWatchlists(
      Array.isArray(currentSetups.watchlists) ? currentSetups.watchlists : [],
      available
    );
    collectSessionsFromWatchlists(
      Array.isArray(fallbackSetups.watchlists) ? fallbackSetups.watchlists : [],
      available
    );
    if (state.sessionSnapshots) {
      Object.values(state.sessionSnapshots).forEach((cache) => {
        if (!cache || typeof cache !== "object") {
          return;
        }
        Object.values(cache).forEach((snapshot) => {
          if (!snapshot || typeof snapshot !== "object") {
            return;
          }
          collectSessionsFromWatchlists([snapshot], available);
        });
      });
    }

    const previous = filters.session || select.value || "all";
    Array.from(select.options).forEach((option) => {
      if (!option || !option.value) {
        return;
      }
      const value = option.value.toLowerCase();
      if (value === "all") {
        option.disabled = false;
        return;
      }
      option.disabled = !available.has(value);
    });

    const selectedOption = Array.from(select.options).find(
      (option) => option && option.value === previous
    );
    let nextValue = previous;
    if (selectedOption && selectedOption.disabled) {
      nextValue = "all";
    }
    if (!nextValue) {
      nextValue = "all";
    }
    select.value = nextValue;
    filters.session = nextValue;
  }

  function collectWatchlistIdsFromWatchlists(watchlists, target) {
    watchlists.forEach((watchlist) => {
      if (!watchlist || typeof watchlist !== "object") {
        return;
      }
      if (watchlist.id) {
        target.add(watchlist.id.toString());
      }
    });
  }

  async function refreshSessionSnapshots(sessionValue) {
    const targetSession = sessionValue || filters.session || "all";
    if (targetSession === "all") {
      renderSetups();
      return;
    }
    if (typeof fetch !== "function") {
      renderSetups();
      return;
    }

    const identifiers = new Set();
    const currentSetups = ensureSetupsContainer(state.current);
    const fallbackSetups = ensureSetupsContainer(state.fallback);
    collectWatchlistIdsFromWatchlists(
      Array.isArray(currentSetups.watchlists) ? currentSetups.watchlists : [],
      identifiers
    );
    collectWatchlistIdsFromWatchlists(
      Array.isArray(fallbackSetups.watchlists) ? fallbackSetups.watchlists : [],
      identifiers
    );
    if (state.sessionSnapshots) {
      Object.values(state.sessionSnapshots).forEach((cache) => {
        if (!cache || typeof cache !== "object") {
          return;
        }
        Object.values(cache).forEach((snapshot) => {
          if (!snapshot || typeof snapshot !== "object") {
            return;
          }
          collectWatchlistIdsFromWatchlists([snapshot], identifiers);
        });
      });
    }

    if (!identifiers.size) {
      renderSetups();
      return;
    }

    const results = Object.create(null);
    await Promise.all(
      Array.from(identifiers).map(async (watchlistId) => {
        try {
          const url = new URL(
            `/inplay/watchlists/${encodeURIComponent(watchlistId)}`,
            window.location.origin
          );
          url.searchParams.set("session", targetSession);
          const response = await fetch(url.toString(), {
            headers: { Accept: "application/json" },
          });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const payload = await response.json();
          const snapshot = sanitiseWatchlistSnapshot(payload, watchlistId);
          if (snapshot) {
            results[watchlistId] = snapshot;
          }
        } catch (error) {
          console.warn(
            `Impossible de charger la watchlist ${watchlistId} pour la session ${targetSession}`,
            error
          );
        }
      })
    );

    if (!Object.keys(results).length) {
      renderSetups();
      return;
    }

    if (!state.sessionSnapshots[targetSession]) {
      state.sessionSnapshots[targetSession] = Object.create(null);
    }
    Object.assign(state.sessionSnapshots[targetSession], results);
    renderSetups();
  }

  function updateLogFilterOptions() {
    const select = selectors.logFilter;
    if (!select) {
      return;
    }
    const previous = select.value || filters.logStrategy || "all";
    const options = new Map();
    options.set("all", "Toutes les stratégies");
    (state.current.strategies || []).forEach((strategy) => {
      if (!strategy || typeof strategy !== "object") {
        return;
      }
      const id = String(strategy.id || "");
      const name = strategy.name || id || "Stratégie";
      if (id) {
        options.set(id, name);
      }
    });

    select.innerHTML = "";
    options.forEach((label, value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    });

    if (options.has(previous)) {
      select.value = previous;
    } else {
      select.value = "all";
    }
    filters.logStrategy = select.value;
  }

  function renderStrategies() {
    const container = selectors.strategies;
    if (!container) {
      return;
    }
    container.innerHTML = "";
    const strategies = Array.isArray(state.current.strategies)
      ? state.current.strategies
      : [];
    if (!strategies.length) {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td colspan="5">
          <p class="text text--muted">Aucune stratégie enregistrée pour le moment.</p>
        </td>
      `;
      container.appendChild(row);
      updateLogFilterOptions();
      return;
    }

    strategies.forEach((strategy) => {
      if (!strategy || typeof strategy !== "object") {
        return;
      }
      const row = document.createElement("tr");
      const statusValue = (strategy.status && strategy.status.value) || strategy.status || "PENDING";
      let badgeClass = "badge--info";
      if (statusValue === "ACTIVE") {
        badgeClass = "badge--success";
      } else if (statusValue === "ERROR") {
        badgeClass = "badge--critical";
      } else if (statusValue === "PENDING") {
        badgeClass = "badge--info";
      } else {
        badgeClass = "badge--warning";
      }

      const lastExecution = strategy.last_execution || strategy.lastExecution || null;
      const submittedAt = lastExecution && (lastExecution.submitted_at || lastExecution.submittedAt);
      const submittedDate = submittedAt ? new Date(submittedAt) : null;
      const submittedText =
        submittedDate && !Number.isNaN(submittedDate.getTime())
          ? submittedDate.toLocaleString("fr-FR", {
              day: "2-digit",
              month: "2-digit",
              hour: "2-digit",
              minute: "2-digit",
            })
          : null;
      const executionStatus = lastExecution && (lastExecution.status || lastExecution.execution_status);
      const executionSymbol = lastExecution && (lastExecution.symbol || lastExecution.instrument);
      const executionOrderId = lastExecution && (lastExecution.order_id || lastExecution.orderId);

      row.innerHTML = `
        <td data-label="Nom">
          <div class="strategy-name">
            <span class="heading heading--md">${strategy.name || "Stratégie"}</span>
            ${strategy.strategy_type || strategy.strategyType ? `<span class="badge badge--neutral">${
              strategy.strategy_type || strategy.strategyType
            }</span>` : ""}
          </div>
        </td>
        <td data-label="Statut">
          <span class="badge ${badgeClass}">${statusValue}</span>
        </td>
        <td data-label="Dernière exécution">
          ${submittedText ? submittedText : '<span class="text text--muted">Aucune</span>'}
        </td>
        <td data-label="Détails">
          ${lastExecution
            ? `<p class="text text--muted">
                ${executionStatus ? executionStatus : ""}
                ${executionSymbol ? ` · ${executionSymbol}` : ""}
                ${executionOrderId ? ` · Ordre ${executionOrderId}` : ""}
              </p>`
            : '<span class="text text--muted">En attente d\'exécution</span>'}
        </td>
        <td data-label="Erreur récente">
          ${strategy.last_error || strategy.lastError
            ? `<p class="text text--critical">${strategy.last_error || strategy.lastError}</p>`
            : '<span class="text text--muted">—</span>'}
        </td>
      `;

      container.appendChild(row);
    });

    updateLogFilterOptions();
  }

  function normaliseLogEntry(entry) {
    if (!entry || typeof entry !== "object") {
      return null;
    }
    const timestampValue = entry.timestamp || entry.time || entry.created_at || entry.createdAt;
    const timestamp = timestampValue ? new Date(timestampValue) : null;
    if (!timestamp || Number.isNaN(timestamp.getTime())) {
      return null;
    }
    return {
      timestamp,
      message: entry.message || "",
      status: entry.status || entry.state || null,
      symbol: entry.symbol || null,
      orderId: entry.order_id || entry.orderId || null,
      strategyId: entry.strategy_id || entry.strategyId || null,
      strategyHint: entry.strategy_hint || entry.strategyHint || null,
    };
  }

  function renderLogs() {
    const container = selectors.logs;
    if (!container) {
      return;
    }
    container.innerHTML = "";
    const entries = Array.isArray(state.current.logs) ? state.current.logs : [];
    const normalised = entries
      .map((entry) => normaliseLogEntry(entry))
      .filter((entry) => entry !== null)
      .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());

    let rendered = 0;
    normalised.forEach((entry) => {
      if (
        filters.logStrategy !== "all" &&
        entry.strategyId &&
        entry.strategyId !== filters.logStrategy
      ) {
        return;
      }
      if (filters.logStrategy !== "all" && !entry.strategyId) {
        return;
      }
      const item = document.createElement("li");
      item.className = "log-console__item";
      item.dataset.strategy = entry.strategyId || "";
      const timestampText = entry.timestamp.toLocaleString("fr-FR", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      item.innerHTML = `
        <div class="log-console__meta">
          <time datetime="${entry.timestamp.toISOString()}">${timestampText}</time>
          ${entry.status ? `<span class="badge badge--neutral">${entry.status}</span>` : ""}
          ${entry.symbol ? `<span class="badge badge--info">${entry.symbol}</span>` : ""}
        </div>
        <p class="log-console__message">${entry.message || ""}</p>
      `;
      container.appendChild(item);
      rendered += 1;
    });

    if (!rendered) {
      const empty = document.createElement("li");
      empty.className = "log-console__item log-console__item--empty";
      empty.innerHTML = `
        <p class="text text--muted">En attente d'événements. Les exécutions apparaîtront ici en temps réel.</p>
      `;
      container.appendChild(empty);
    }
  }

  function renderAll() {
    renderSetups();
    renderStrategies();
    renderPortfolios();
    renderTransactions();
    if (selectors.alerts) {
      renderAlerts();
    }
    renderLogs();
  }

  let websocket;
  let reconnectTimer;
  const RECONNECT_DELAY = 5000;

  function closeWebsocket() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.close();
    }
    websocket = undefined;
  }

  function restoreFallback() {
    state.current = JSON.parse(JSON.stringify(state.fallback));
    ensureSetupsContainer(state.current);
    state.setupsFallbackActive = true;
    if (state.received && typeof state.received === "object") {
      state.received.portfolios = false;
    }
    renderAll();
    if (alertsReactRoot) {
      document.dispatchEvent(
        new CustomEvent("alerts:fallback", {
          detail: {
            items: Array.isArray(state.current.alerts) ? state.current.alerts : [],
            message:
              "Connexion temps réel indisponible. Les données affichées proviennent du dernier instantané.",
            type: "warning",
          },
        })
      );
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) {
      return;
    }
    reconnectTimer = setTimeout(() => {
      reconnectTimer = undefined;
      connect();
    }, RECONNECT_DELAY);
  }

  function applyUpdate(message) {
    const payload = message && message.payload ? message.payload : message;
    if (!payload || typeof payload !== "object") {
      return;
    }

    if (message && message.type === "watchlist.update" && message.payload) {
      if (applyWatchlistPayload(message.payload)) {
        return;
      }
    }

    if (payload && payload.type === "watchlist.update" && payload.payload) {
      if (applyWatchlistPayload(payload.payload)) {
        return;
      }
    }

    const resource = payload.resource || payload.type;
    if (resource === "portfolios" && Array.isArray(payload.items)) {
      const mode = payload.mode || payload.source || "live";
      updateDatasetSource("portfolios", mode);
      state.received.portfolios = true;
      if (mode === "fallback" || mode === "degraded") {
        state.fallback.portfolios = JSON.parse(JSON.stringify(payload.items));
        state.current.portfolios = JSON.parse(JSON.stringify(payload.items));
      } else {
        state.current.portfolios = payload.items;
      }
      renderPortfolios();
    } else if (resource === "transactions" && Array.isArray(payload.items)) {
      state.current.transactions = payload.items;
      updateDatasetSource("transactions", payload.mode || payload.source || "live");
      renderTransactions();
    } else if (resource === "alerts" && Array.isArray(payload.items)) {
      state.current.alerts = payload.items;
      if (alertsReactRoot) {
        const detail = { items: payload.items };
        if (payload.message) {
          detail.message = payload.message;
        }
        if (payload.type) {
          detail.type = payload.type;
        }
        document.dispatchEvent(new CustomEvent("alerts:update", { detail }));
      }
      if (selectors.alerts) {
        renderAlerts();
      }
    } else if (resource === "strategies" && Array.isArray(payload.items)) {
      state.current.strategies = payload.items;
      renderStrategies();
      renderLogs();
    } else if (resource === "inplay.watchlists" || resource === "inplay.setups") {
      const snapshot =
        payload.snapshot || payload.watchlists || payload.items || payload;
      applyWatchlistPayload(snapshot);
    } else if (resource === "logs" || resource === "executions") {
      const items = [];
      if (Array.isArray(payload.items)) {
        items.push(...payload.items);
      } else if (payload.entry) {
        items.push(payload.entry);
      } else if (!payload.resource && !payload.type) {
        items.push(payload);
      }
      if (!state.current.logs) {
        state.current.logs = [];
      }
      const combined = items.concat(state.current.logs);
      const unique = [];
      const seen = new Set();
      combined.forEach((entry) => {
        const normalised = normaliseLogEntry(entry);
        if (!normalised) {
          return;
        }
        const key = `${normalised.timestamp.toISOString()}-${normalised.orderId || "unknown"}`;
        if (seen.has(key)) {
          return;
        }
        seen.add(key);
        unique.push({
          timestamp: normalised.timestamp.toISOString(),
          message: normalised.message,
          status: normalised.status,
          symbol: normalised.symbol,
          order_id: normalised.orderId,
          strategy_id: normalised.strategyId,
          strategy_hint: normalised.strategyHint,
        });
      });
      state.current.logs = unique.slice(0, 200);
      renderLogs();
    }
  }

  async function connect() {
    if (!streamingConfig.handshake_url || !streamingConfig.viewer_id) {
      console.warn("Configuration du streaming incomplète, aucun WebSocket ouvert.");
      return;
    }
    try {
      const response = await fetch(streamingConfig.handshake_url, {
        headers: { "X-Customer-Id": streamingConfig.viewer_id },
      });
      if (!response.ok) {
        throw new Error(`Handshake échoué (${response.status})`);
      }
      const details = await response.json();
      if (!details.websocket_url) {
        throw new Error("Réponse de handshake incomplète");
      }
      closeWebsocket();
      websocket = new WebSocket(details.websocket_url);
      websocket.onopen = () => {
        if (reconnectTimer) {
          clearTimeout(reconnectTimer);
          reconnectTimer = undefined;
        }
      };
      websocket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          applyUpdate(payload);
        } catch (error) {
          console.error("Message WebSocket invalide", error);
        }
      };
      websocket.onclose = () => {
        restoreFallback();
        scheduleReconnect();
      };
      websocket.onerror = () => {
        websocket.close();
      };
    } catch (error) {
      console.error("Connexion WebSocket impossible", error);
      if (alertsReactRoot) {
        document.dispatchEvent(
          new CustomEvent("alerts:error", {
            detail: {
              message: "Connexion temps réel impossible pour les alertes.",
            },
          })
        );
      }
      restoreFallback();
      scheduleReconnect();
    }
  }

  renderAll();
  connect();
})();
