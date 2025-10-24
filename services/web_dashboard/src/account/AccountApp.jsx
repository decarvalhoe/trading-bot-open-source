import React, { useCallback, useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import {
  fetchBrokerCredentials,
  fetchSession,
  login,
  logout,
  normalizeSession,
  updateBrokerCredentials
} from "./api.js";

const BROKER_DEFINITIONS = [
  {
    id: "binance",
    label: "Binance",
    description:
      "Associez votre compte API Binance pour synchroniser ordres et soldes depuis le moteur d'orchestration.",
    fields: {
      apiKeyLabel: "Clé API (Binance)",
      apiSecretLabel: "Secret API (Binance)"
    }
  },
  {
    id: "ibkr",
    label: "Interactive Brokers (IBKR)",
    description:
      "Renseignez l'identifiant dédié aux API IBKR et le mot de passe d'application associé au portail client.",
    fields: {
      apiKeyLabel: "Identifiant API (IBKR)",
      apiSecretLabel: "Mot de passe API (IBKR)"
    }
  }
];

const EMPTY_FORM = { email: "", password: "", totp: "" };

function createEmptyBrokerEntry(brokerId, label) {
  return {
    broker: brokerId,
    label: label || brokerId.toUpperCase(),
    apiKey: "",
    apiSecret: "",
    apiKeyMasked: null,
    apiSecretMasked: null,
    hasApiKey: false,
    hasApiSecret: false,
    updatedAt: null,
    dirtyFields: { apiKey: false, apiSecret: false }
  };
}

function buildInitialBrokerState() {
  const state = {};
  BROKER_DEFINITIONS.forEach((definition) => {
    state[definition.id] = createEmptyBrokerEntry(definition.id, definition.label);
  });
  return state;
}

function buildBrokerStateFromPayload(payload) {
  const base = buildInitialBrokerState();
  const next = { ...base };
  if (!payload || !Array.isArray(payload.credentials)) {
    return next;
  }
  payload.credentials.forEach((item) => {
    if (!item || typeof item.broker !== "string") {
      return;
    }
    const brokerId = item.broker;
    const existing = next[brokerId] || createEmptyBrokerEntry(brokerId);
    next[brokerId] = {
      ...existing,
      apiKey: "",
      apiSecret: "",
      apiKeyMasked: item.api_key_masked || null,
      apiSecretMasked: item.api_secret_masked || null,
      hasApiKey: Boolean(item.has_api_key),
      hasApiSecret: Boolean(item.has_api_secret),
      updatedAt: item.updated_at || null,
      dirtyFields: { apiKey: false, apiSecret: false }
    };
  });
  return next;
}

function formatUpdatedAt(value) {
  if (!value) {
    return null;
  }
  try {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat("fr-FR", {
      dateStyle: "medium",
      timeStyle: "short"
    }).format(parsed);
  } catch (error) {
    return value;
  }
}

function useSession(endpoints) {
  const [state, setState] = useState({ status: "loading", user: null, error: null });

  const load = async () => {
    setState((prev) => ({ ...prev, status: "loading" }));
    try {
      const session = normalizeSession(await fetchSession(endpoints.session));
      if (session.authenticated) {
        setState({ status: "ready", user: session.user, error: null });
      } else {
        setState({ status: "anonymous", user: null, error: null });
      }
    } catch (error) {
      setState({ status: "error", user: null, error: error.message || "Erreur inattendue" });
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoints.session]);

  return [state, load, setState];
}

function AccountApp({ endpoints, onSessionChange }) {
  const [sessionState, reloadSession, setSessionState] = useSession(endpoints);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [brokerState, setBrokerState] = useState(() => buildInitialBrokerState());
  const [brokerLoading, setBrokerLoading] = useState(false);
  const [brokerError, setBrokerError] = useState(null);
  const [brokerSuccess, setBrokerSuccess] = useState(null);
  const [brokerSubmitting, setBrokerSubmitting] = useState(false);

  useEffect(() => {
    if (typeof onSessionChange === "function") {
      onSessionChange(sessionState);
    }
  }, [sessionState, onSessionChange]);

  const isAuthenticated = sessionState.status === "ready" && !!sessionState.user;
  const isAnonymous = sessionState.status === "anonymous" || sessionState.status === "ready";

  const userLabel = useMemo(() => {
    if (!sessionState.user) {
      return null;
    }
    const { email, id } = sessionState.user;
    if (email && id) {
      return `${email} (#${id})`;
    }
    return email || `Utilisateur ${id}`;
  }, [sessionState.user]);

  const knownBrokerIds = useMemo(
    () => BROKER_DEFINITIONS.map((definition) => definition.id),
    []
  );

  const extraBrokerIds = useMemo(
    () =>
      Object.keys(brokerState).filter(
        (brokerId) => !knownBrokerIds.includes(brokerId)
      ),
    [brokerState, knownBrokerIds]
  );

  const hasBrokerChanges = useMemo(
    () =>
      Object.values(brokerState).some(
        (entry) => entry.dirtyFields.apiKey || entry.dirtyFields.apiSecret
      ),
    [brokerState]
  );

  const loadBrokerCredentials = useCallback(async () => {
    if (!endpoints.brokerCredentials) {
      return;
    }
    if (!isAuthenticated) {
      setBrokerState(buildInitialBrokerState());
      setBrokerError(null);
      setBrokerSuccess(null);
      setBrokerLoading(false);
      return;
    }
    setBrokerLoading(true);
    setBrokerSuccess(null);
    setBrokerError(null);
    try {
      const payload = await fetchBrokerCredentials(endpoints.brokerCredentials);
      setBrokerState(buildBrokerStateFromPayload(payload));
    } catch (error) {
      setBrokerError(
        error.message || "Impossible de récupérer les identifiants broker"
      );
    } finally {
      setBrokerLoading(false);
    }
  }, [endpoints.brokerCredentials, isAuthenticated]);

  useEffect(() => {
    loadBrokerCredentials();
  }, [loadBrokerCredentials]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      const payload = await login(endpoints.login, {
        email: form.email,
        password: form.password,
        totp: form.totp ? form.totp.trim() : undefined
      });
      const session = normalizeSession(payload);
      if (session.authenticated) {
        setForm(EMPTY_FORM);
        setSessionState({ status: "ready", user: session.user, error: null });
      } else {
        await reloadSession();
      }
    } catch (error) {
      setFormError(error.message || "Impossible de se connecter");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogout() {
    setFormError(null);
    try {
      await logout(endpoints.logout);
      setSessionState({ status: "anonymous", user: null, error: null });
    } catch (error) {
      setFormError(error.message || "Impossible de se déconnecter");
    }
  }

  const handleBrokerFieldChange = useCallback(
    (brokerId, field, value) => {
      setBrokerState((prev) => {
        const existing = prev[brokerId] || createEmptyBrokerEntry(brokerId);
        return {
          ...prev,
          [brokerId]: {
            ...existing,
            [field]: value,
            dirtyFields: {
              ...existing.dirtyFields,
              [field]: true
            }
          }
        };
      });
      setBrokerSuccess(null);
      setBrokerError(null);
    },
    [setBrokerError, setBrokerSuccess]
  );

  function renderBrokerSection(definition, entry) {
    const resolvedEntry = entry || createEmptyBrokerEntry(definition.id, definition.label);
    const displayLabel = definition.label || resolvedEntry.label;
    const apiKeyLabel =
      (definition.fields && definition.fields.apiKeyLabel) || `Clé API (${displayLabel})`;
    const apiSecretLabel =
      (definition.fields && definition.fields.apiSecretLabel) || `Secret API (${displayLabel})`;
    const updatedLabel = formatUpdatedAt(resolvedEntry.updatedAt);
    return (
      <fieldset key={definition.id} className="account-broker__section">
        <legend className="heading heading--md">{displayLabel}</legend>
        {definition.description && (
          <p className="text text--muted">{definition.description}</p>
        )}
        <div className="form-grid">
          <label className="designer-field">
            <span className="designer-field__label text text--muted">{apiKeyLabel}</span>
            <input
              type="text"
              autoComplete="off"
              value={resolvedEntry.apiKey}
              onChange={(event) =>
                handleBrokerFieldChange(resolvedEntry.broker, "apiKey", event.target.value)
              }
              placeholder={
                resolvedEntry.hasApiKey && resolvedEntry.apiKeyMasked
                  ? resolvedEntry.apiKeyMasked
                  : "Votre clé publique"
              }
            />
            {resolvedEntry.hasApiKey && resolvedEntry.apiKeyMasked && (
              <span className="text text--muted account-broker__mask">
                Clé enregistrée : {resolvedEntry.apiKeyMasked}
              </span>
            )}
          </label>
          <label className="designer-field">
            <span className="designer-field__label text text--muted">{apiSecretLabel}</span>
            <input
              type="password"
              autoComplete="off"
              value={resolvedEntry.apiSecret}
              onChange={(event) =>
                handleBrokerFieldChange(resolvedEntry.broker, "apiSecret", event.target.value)
              }
              placeholder={
                resolvedEntry.hasApiSecret && resolvedEntry.apiSecretMasked
                  ? resolvedEntry.apiSecretMasked
                  : "Votre secret API"
              }
            />
            {resolvedEntry.hasApiSecret && resolvedEntry.apiSecretMasked && (
              <span className="text text--muted account-broker__mask">
                Secret enregistré : {resolvedEntry.apiSecretMasked}
              </span>
            )}
          </label>
        </div>
        {updatedLabel && (
          <p className="text text--muted account-broker__meta">
            Dernière mise à jour&nbsp;: {updatedLabel}
          </p>
        )}
      </fieldset>
    );
  }

  async function handleBrokerSubmit(event) {
    event.preventDefault();
    if (brokerSubmitting || !isAuthenticated || !endpoints.brokerCredentials) {
      return;
    }
    setBrokerSuccess(null);
    const updates = [];
    Object.values(brokerState).forEach((entry) => {
      const update = { broker: entry.broker };
      let hasChange = false;
      if (entry.dirtyFields.apiKey) {
        const raw = entry.apiKey ?? "";
        const trimmed = typeof raw === "string" ? raw.trim() : "";
        update.api_key = trimmed === "" ? null : entry.apiKey;
        hasChange = true;
      }
      if (entry.dirtyFields.apiSecret) {
        const rawSecret = entry.apiSecret ?? "";
        const trimmedSecret = typeof rawSecret === "string" ? rawSecret.trim() : "";
        update.api_secret = trimmedSecret === "" ? null : entry.apiSecret;
        hasChange = true;
      }
      if (hasChange) {
        updates.push(update);
      }
    });
    if (updates.length === 0) {
      setBrokerSuccess("Aucune modification à enregistrer.");
      return;
    }
    setBrokerSubmitting(true);
    setBrokerError(null);
    try {
      const payload = await updateBrokerCredentials(endpoints.brokerCredentials, {
        credentials: updates
      });
      setBrokerState(buildBrokerStateFromPayload(payload));
      setBrokerSuccess("Identifiants broker mis à jour.");
    } catch (error) {
      setBrokerError(
        error.message || "Impossible d'enregistrer les identifiants broker"
      );
      setBrokerSuccess(null);
    } finally {
      setBrokerSubmitting(false);
    }
  }

  const renderStatus = () => {
    if (sessionState.status === "loading") {
      return (
        <div className="alert alert--info" role="status">
          Vérification de votre session…
        </div>
      );
    }
    if (sessionState.status === "error") {
      return (
        <div className="alert alert--error" role="alert">
          {sessionState.error}
        </div>
      );
    }
    if (isAuthenticated) {
      return (
        <div className="alert alert--success" role="status">
          Connecté en tant que <strong>{userLabel}</strong>
        </div>
      );
    }
    return null;
  };

  return (
    <>
      <section className="card" aria-labelledby="login-title">
        <div className="card__header">
          <h2 id="login-title" className="heading heading--lg">
            Connexion
          </h2>
          <p className="text text--muted">
            Authentifiez-vous pour débloquer les fonctions de sauvegarde et d'orchestration.
          </p>
        </div>
        <div className="card__body">
          {renderStatus()}
          {!isAuthenticated && (
            <form className="form-grid" onSubmit={handleSubmit}>
              <label className="designer-field">
                <span className="designer-field__label text text--muted">Adresse e-mail</span>
                <input
                  type="email"
                  name="email"
                  autoComplete="email"
                  required
                  value={form.email}
                  onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                />
              </label>
              <label className="designer-field">
                <span className="designer-field__label text text--muted">Mot de passe</span>
                <input
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  required
                  value={form.password}
                  onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                />
              </label>
              <label className="designer-field">
                <span className="designer-field__label text text--muted">Code TOTP (facultatif)</span>
                <input
                  type="text"
                  name="totp"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  autoComplete="one-time-code"
                  value={form.totp}
                  onChange={(event) => setForm((prev) => ({ ...prev, totp: event.target.value }))}
                />
              </label>
              {formError && (
                <p className="text text--danger" role="alert">
                  {formError}
                </p>
              )}
              <button type="submit" className="button button--primary" disabled={submitting}>
                {submitting ? "Connexion en cours…" : "Se connecter"}
              </button>
            </form>
          )}
          {isAuthenticated && (
            <div className="account-session__actions">
              <button type="button" className="button button--secondary" onClick={handleLogout}>
                Se déconnecter
              </button>
            </div>
          )}
        </div>
      </section>
      <section className="card" aria-labelledby="api-keys-title">
        <div className="card__header">
          <h2 id="api-keys-title" className="heading heading--lg">
            Clés API exchanges
          </h2>
          <p className="text text--muted">
            Stockez vos identifiants chiffrés. Ils seront synchronisés avec l'orchestrateur lors des déploiements.
          </p>
        </div>
        <div className="card__body">
          {isAuthenticated ? (
            <>
              {brokerError && (
                <div className="alert alert--error" role="alert">
                  {brokerError}
                </div>
              )}
              {brokerSuccess && (
                <div className="alert alert--success" role="status">
                  {brokerSuccess}
                </div>
              )}
              {brokerLoading ? (
                <p className="text text--muted">Chargement des identifiants broker…</p>
              ) : (
                <form className="account-broker-form" onSubmit={handleBrokerSubmit}>
                  {BROKER_DEFINITIONS.map((definition) =>
                    renderBrokerSection(definition, brokerState[definition.id])
                  )}
                  {extraBrokerIds.map((brokerId) => {
                    const entry = brokerState[brokerId];
                    const label = entry?.label || brokerId.toUpperCase();
                    const fallbackDefinition = {
                      id: brokerId,
                      label,
                      description: "Identifiants ajoutés depuis un broker personnalisé.",
                      fields: {
                        apiKeyLabel: `Clé API (${label})`,
                        apiSecretLabel: `Secret API (${label})`
                      }
                    };
                    return renderBrokerSection(fallbackDefinition, entry);
                  })}
                  <div className="account-broker__actions">
                    <button
                      type="submit"
                      className="button button--primary"
                      disabled={!hasBrokerChanges || brokerSubmitting}
                    >
                      {brokerSubmitting ? "Enregistrement…" : "Sauvegarder les identifiants"}
                    </button>
                  </div>
                  <p className="text text--muted account-broker__hint">
                    Les champs laissés vides conservent les valeurs existantes. Supprimez une clé en soumettant un champ vide.
                  </p>
                </form>
              )}
            </>
          ) : (
            <p className="text text--muted">
              Connectez-vous pour accéder à la gestion sécurisée de vos clés API exchanges.
            </p>
          )}
        </div>
      </section>
    </>
  );
}

AccountApp.propTypes = {
  endpoints: PropTypes.shape({
    session: PropTypes.string.isRequired,
    login: PropTypes.string.isRequired,
    logout: PropTypes.string.isRequired,
    brokerCredentials: PropTypes.string.isRequired
  }).isRequired,
  onSessionChange: PropTypes.func,
};

AccountApp.defaultProps = {
  onSessionChange: undefined,
};

export default AccountApp;
