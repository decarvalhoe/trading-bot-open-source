import React, { useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import { fetchSession, login, logout, normalizeSession } from "./api.js";

const EMPTY_FORM = { email: "", password: "", totp: "" };

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

function AccountApp({ endpoints }) {
  const [sessionState, reloadSession, setSessionState] = useSession(endpoints);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

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
            <p className="text">
              La gestion des clés API sera disponible prochainement. Vos identifiants seront chiffrés avant toute
              synchronisation.
            </p>
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
    logout: PropTypes.string.isRequired
  }).isRequired
};

export default AccountApp;
