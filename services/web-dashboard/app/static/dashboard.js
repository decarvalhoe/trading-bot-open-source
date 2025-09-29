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
    { portfolios: [], transactions: [], alerts: [], strategies: [], logs: [] };
  const streamingConfig = bootstrapData.streaming || {};
  const state = {
    current: JSON.parse(JSON.stringify(initialState)),
    fallback: JSON.parse(JSON.stringify(initialState)),
  };

  const alertsReactRoot = document.getElementById("alerts-manager");

  const selectors = {
    portfolios: document.querySelector(".portfolio-list"),
    transactions: document.querySelector(".card[aria-labelledby='transactions-title'] tbody"),
    alerts: alertsReactRoot ? null : document.querySelector(".alert-list"),
    strategies: document.querySelector(".strategy-table__body"),
    logs: document.getElementById("log-entries"),
    logFilter: document.getElementById("log-filter"),
  };

  const filters = {
    logStrategy: selectors.logFilter ? selectors.logFilter.value || "all" : "all",
  };

  if (selectors.logFilter) {
    selectors.logFilter.addEventListener("change", (event) => {
      filters.logStrategy = event.target.value;
      renderLogs();
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

  function renderPortfolios() {
    const container = selectors.portfolios;
    if (!container) {
      return;
    }
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

    const resource = payload.resource || payload.type;
    if (resource === "portfolios" && Array.isArray(payload.items)) {
      state.current.portfolios = payload.items;
      renderPortfolios();
    } else if (resource === "transactions" && Array.isArray(payload.items)) {
      state.current.transactions = payload.items;
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
