import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Tooltip from "./Tooltip.jsx";
import { mergeStepMetadata } from "./steps.js";

function normaliseProgress(payload) {
  const steps = mergeStepMetadata(payload?.steps);
  const completed = Array.isArray(payload?.completed_steps)
    ? payload.completed_steps.filter((stepId) =>
        steps.some((step) => step.id === stepId)
      )
    : [];
  const uniqueCompleted = [];
  completed.forEach((stepId) => {
    if (!uniqueCompleted.includes(stepId)) {
      uniqueCompleted.push(stepId);
    }
  });
  const isComplete =
    payload?.is_complete ?? uniqueCompleted.length >= steps.length;
  const nextFromPayload = payload?.current_step;
  const derivedNext = steps.find((step) => !uniqueCompleted.includes(step.id));
  const currentStepId = isComplete
    ? null
    : steps.find((step) => step.id === nextFromPayload)?.id || derivedNext?.id || null;

  return {
    userId: payload?.user_id ?? null,
    steps,
    completedSteps: uniqueCompleted,
    currentStepId,
    isComplete,
    updatedAt: payload?.updated_at ?? null,
    restartedAt: payload?.restarted_at ?? null,
  };
}

function buildStepUrl(template, stepId) {
  if (!template || !stepId) {
    return null;
  }
  return template.replace("__STEP__", encodeURIComponent(stepId));
}

function buildDeleteUrl(template, broker) {
  if (!template || !broker) {
    return null;
  }
  return template.replace("__BROKER__", encodeURIComponent(broker));
}

function normaliseCredentials(payload) {
  if (!payload || !Array.isArray(payload.credentials)) {
    return [];
  }
  return payload.credentials;
}

function mapTestResult(result, t) {
  if (!result) {
    return null;
  }
  const status = result.status || "unknown";
  const message = result.message;
  switch (status) {
    case "ok":
      return {
        tone: "success",
        message: message || t("Connexion réussie avec le broker."),
      };
    case "unauthorized":
      return {
        tone: "critical",
        message:
          message ||
          t(
            "Les identifiants fournis semblent incorrects. Vérifiez la casse et les droits API."
          ),
      };
    case "network_error":
      return {
        tone: "warning",
        message:
          message ||
          t(
            "Le test n'a pas abouti. Assurez-vous que le point d'accès du broker est joignable."
          ),
      };
    default:
      return {
        tone: "neutral",
        message: message || t("Résultat de test inattendu. Réessayez."),
      };
  }
}

export default function OnboardingApp({
  progressEndpoint,
  stepTemplate,
  resetEndpoint,
  userId,
  credentialsEndpoint,
  credentialsSubmitEndpoint,
  credentialsTestEndpoint,
  credentialsDeleteTemplate,
  modeEndpoint,
  modeUpdateEndpoint,
}) {
  const { t, i18n } = useTranslation();
  const [progress, setProgress] = useState(null);
  const [isLoadingProgress, setIsLoadingProgress] = useState(true);
  const [progressError, setProgressError] = useState(null);
  const [pendingStep, setPendingStep] = useState(null);
  const [isResetting, setIsResetting] = useState(false);

  const [credentials, setCredentials] = useState([]);
  const [credentialsError, setCredentialsError] = useState(null);
  const [isLoadingCredentials, setIsLoadingCredentials] = useState(false);
  const [isSavingCredential, setIsSavingCredential] = useState(false);
  const [isTestingCredential, setIsTestingCredential] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [credentialForm, setCredentialForm] = useState({
    broker: "",
    apiKey: "",
    apiSecret: "",
  });

  const [modeState, setModeState] = useState({ mode: null, allowed_modes: [] });
  const [modeError, setModeError] = useState(null);
  const [isLoadingMode, setIsLoadingMode] = useState(false);
  const [isUpdatingMode, setIsUpdatingMode] = useState(false);

  const baseHeaders = useMemo(() => {
    const headers = { Accept: "application/json" };
    if (userId) {
      headers["X-User-Id"] = userId;
    }
    return headers;
  }, [userId]);

  const fetchProgress = useCallback(async () => {
    if (!progressEndpoint) {
      setProgressError(t("Point d'accès onboarding non configuré."));
      setProgress(null);
      setIsLoadingProgress(false);
      return;
    }
    setIsLoadingProgress(true);
    setProgressError(null);
    try {
      const response = await fetch(progressEndpoint, {
        method: "GET",
        headers: { ...baseHeaders },
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      setProgress(normaliseProgress(payload));
    } catch (err) {
      console.error("Impossible de charger la progression d'onboarding", err);
      setProgressError(t("Impossible de récupérer la progression pour le moment."));
      setProgress(null);
    } finally {
      setIsLoadingProgress(false);
    }
  }, [progressEndpoint, baseHeaders, t]);

  const fetchCredentials = useCallback(async () => {
    if (!credentialsEndpoint) {
      setCredentialsError(
        t("Point d'accès des identifiants non configuré.")
      );
      setCredentials([]);
      return;
    }
    setIsLoadingCredentials(true);
    setCredentialsError(null);
    try {
      const response = await fetch(credentialsEndpoint, {
        method: "GET",
        headers: { ...baseHeaders },
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      const list = normaliseCredentials(payload);
      setCredentials(list);
      setCredentialForm((prev) => {
        if (prev.broker) {
          return prev;
        }
        const firstBroker = list[0]?.broker || "binance";
        return { ...prev, broker: firstBroker };
      });
    } catch (err) {
      console.error("Impossible de charger les identifiants broker", err);
      setCredentialsError(
        t("Impossible de récupérer les identifiants pour le moment.")
      );
      setCredentials([]);
    } finally {
      setIsLoadingCredentials(false);
    }
  }, [credentialsEndpoint, baseHeaders, t]);

  const fetchMode = useCallback(async () => {
    if (!modeEndpoint) {
      setModeError(t("Point d'accès du mode non configuré."));
      setModeState({ mode: null, allowed_modes: [] });
      return;
    }
    setIsLoadingMode(true);
    setModeError(null);
    try {
      const response = await fetch(modeEndpoint, {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      setModeState({
        mode: payload?.mode || null,
        allowed_modes: Array.isArray(payload?.allowed_modes)
          ? payload.allowed_modes
          : ["sandbox", "dry_run"],
      });
    } catch (err) {
      console.error("Impossible de récupérer le mode d'exécution", err);
      setModeError(t("Impossible de récupérer le mode d'exécution."));
      setModeState({ mode: null, allowed_modes: [] });
    } finally {
      setIsLoadingMode(false);
    }
  }, [modeEndpoint, t]);

  const handleComplete = useCallback(
    async (stepId) => {
      const target = buildStepUrl(stepTemplate, stepId);
      if (!target) {
        setProgressError(t("Impossible de déterminer l'étape à enregistrer."));
        return;
      }
      setPendingStep(stepId);
      setProgressError(null);
      try {
        const response = await fetch(target, {
          method: "POST",
          headers: { ...baseHeaders },
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        setProgress(normaliseProgress(payload));
      } catch (err) {
        console.error("Impossible de marquer l'étape d'onboarding", err);
        setProgressError(t("Enregistrement de l'étape impossible. Réessayez."));
      } finally {
        setPendingStep(null);
      }
    },
    [baseHeaders, stepTemplate, t]
  );

  const handleReset = useCallback(async () => {
    if (!resetEndpoint) {
      setProgressError(t("Point d'accès de réinitialisation manquant."));
      return;
    }
    setIsResetting(true);
    setProgressError(null);
    try {
      const response = await fetch(resetEndpoint, {
        method: "POST",
        headers: { ...baseHeaders },
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      setProgress(normaliseProgress(payload));
      await fetchCredentials();
      await fetchMode();
    } catch (err) {
      console.error("Impossible de réinitialiser le tutoriel", err);
      setProgressError(t("Réinitialisation impossible. Merci de réessayer."));
    } finally {
      setIsResetting(false);
    }
  }, [baseHeaders, resetEndpoint, t, fetchCredentials, fetchMode]);

  const handleCredentialFieldChange = useCallback((event) => {
    const { name, value } = event.target;
    setCredentialForm((prev) => ({ ...prev, [name]: value }));
  }, []);

  const handleCredentialSave = useCallback(
    async (event) => {
      event.preventDefault();
      const submitUrl = credentialsSubmitEndpoint || credentialsEndpoint;
      if (!submitUrl) {
        setCredentialsError(t("Point d'accès des identifiants non configuré."));
        return;
      }
      if (!credentialForm.broker) {
        setCredentialsError(t("Le nom du broker est requis."));
        return;
      }
      setIsSavingCredential(true);
      setCredentialsError(null);
      setTestResult(null);
      try {
        const response = await fetch(submitUrl, {
          method: "POST",
          headers: {
            ...baseHeaders,
            "Content-Type": "application/json",
          },
          credentials: "same-origin",
          body: JSON.stringify({
            credentials: [
              {
                broker: credentialForm.broker,
                api_key: credentialForm.apiKey || null,
                api_secret: credentialForm.apiSecret || null,
              },
            ],
          }),
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        setCredentials(normaliseCredentials(payload));
        setCredentialForm((prev) => ({
          ...prev,
          apiKey: "",
          apiSecret: "",
        }));
      } catch (err) {
        console.error("Impossible d'enregistrer les identifiants broker", err);
        setCredentialsError(t("Enregistrement impossible. Merci de réessayer."));
      } finally {
        setIsSavingCredential(false);
      }
    },
    [
      credentialForm.broker,
      credentialForm.apiKey,
      credentialForm.apiSecret,
      credentialsEndpoint,
      credentialsSubmitEndpoint,
      baseHeaders,
      t,
    ]
  );

  const handleCredentialDelete = useCallback(
    async (broker) => {
      const target = buildDeleteUrl(credentialsDeleteTemplate, broker);
      if (!target) {
        setCredentialsError(t("Suppression impossible pour ce broker."));
        return;
      }
      setIsSavingCredential(true);
      setCredentialsError(null);
      try {
        const response = await fetch(target, {
          method: "DELETE",
          headers: { ...baseHeaders },
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        await fetchCredentials();
        setTestResult(null);
        setCredentialForm((prev) => {
          if (prev.broker && prev.broker.toLowerCase() === broker.toLowerCase()) {
            return { ...prev, broker: "", apiKey: "", apiSecret: "" };
          }
          return prev;
        });
      } catch (err) {
        console.error("Impossible de supprimer l'identifiant broker", err);
        setCredentialsError(t("Suppression impossible. Merci de réessayer."));
      } finally {
        setIsSavingCredential(false);
      }
    },
    [credentialsDeleteTemplate, baseHeaders, t, fetchCredentials]
  );

  const handleTestCredential = useCallback(async () => {
    if (!credentialsTestEndpoint) {
      setCredentialsError(t("Point d'accès de test non configuré."));
      return;
    }
    if (!credentialForm.broker) {
      setCredentialsError(t("Le nom du broker est requis."));
      return;
    }
    setIsTestingCredential(true);
    setCredentialsError(null);
    setTestResult(null);
    try {
      const payload = {
        broker: credentialForm.broker,
      };
      if (credentialForm.apiKey) {
        payload.api_key = credentialForm.apiKey;
      }
      if (credentialForm.apiSecret) {
        payload.api_secret = credentialForm.apiSecret;
      }
      const response = await fetch(credentialsTestEndpoint, {
        method: "POST",
        headers: {
          ...baseHeaders,
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const result = await response.json();
      setTestResult(result);
      await fetchCredentials();
    } catch (err) {
      console.error("Impossible de tester les identifiants broker", err);
      setCredentialsError(t("Test impossible pour le moment."));
    } finally {
      setIsTestingCredential(false);
    }
  }, [
    credentialsTestEndpoint,
    credentialForm.broker,
    credentialForm.apiKey,
    credentialForm.apiSecret,
    baseHeaders,
    t,
    fetchCredentials,
  ]);

  const handleModeChange = useCallback(
    async (nextMode) => {
      const target = modeUpdateEndpoint || modeEndpoint;
      if (!target) {
        setModeError(t("Point d'accès du mode non configuré."));
        return;
      }
      setIsUpdatingMode(true);
      setModeError(null);
      try {
        const response = await fetch(target, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          credentials: "same-origin",
          body: JSON.stringify({ mode: nextMode }),
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        setModeState({
          mode: payload?.mode || nextMode,
          allowed_modes: Array.isArray(payload?.allowed_modes)
            ? payload.allowed_modes
            : modeState.allowed_modes,
        });
      } catch (err) {
        console.error("Impossible de mettre à jour le mode d'exécution", err);
        setModeError(t("La mise à jour du mode a échoué. Réessayez."));
      } finally {
        setIsUpdatingMode(false);
      }
    },
    [modeUpdateEndpoint, modeEndpoint, t, modeState.allowed_modes]
  );

  useEffect(() => {
    fetchProgress();
  }, [fetchProgress]);

  useEffect(() => {
    fetchCredentials();
  }, [fetchCredentials]);

  useEffect(() => {
    fetchMode();
  }, [fetchMode]);

  const totalSteps = progress?.steps?.length ?? 0;
  const completedCount = progress?.completedSteps?.length ?? 0;
  const locale = useMemo(() => i18n.language || "fr", [i18n.language]);
  const hasLiveCredentials = useMemo(
    () =>
      credentials.some(
        (entry) => entry.has_api_key && entry.has_api_secret
      ),
    [credentials]
  );
  const modeOptions = useMemo(() => {
    const allowed =
      modeState.allowed_modes && modeState.allowed_modes.length
        ? modeState.allowed_modes
        : ["sandbox", "dry_run"];
    return allowed.map((value) => ({
      value,
      label:
        value === "dry_run"
          ? t("Dry-run (déterministe)")
          : value === "sandbox"
          ? t("Sandbox broker")
          : value,
    }));
  }, [modeState.allowed_modes, t]);
  const testFeedback = useMemo(
    () => mapTestResult(testResult, t),
    [testResult, t]
  );

  const summaryText = totalSteps
    ? progress?.isComplete
      ? t("{completed} / {total} étapes complétées – Parcours terminé !", {
          completed: completedCount,
          total: totalSteps,
        })
      : t("{completed} / {total} étapes complétées", {
          completed: completedCount,
          total: totalSteps,
        })
    : t("Chargement du parcours d'onboarding");

  const isBusy =
    isLoadingProgress ||
    isLoadingCredentials ||
    isLoadingMode ||
    Boolean(pendingStep) ||
    isResetting ||
    isSavingCredential ||
    isTestingCredential ||
    isUpdatingMode;

  return (
    <section className="onboarding__container" aria-busy={isBusy}>
      <header className="onboarding__header">
        <p className="onboarding__summary" role="status" aria-live="polite">
          {summaryText}
        </p>
        <button
          type="button"
          className="onboarding__restart"
          onClick={handleReset}
          disabled={isResetting || isLoadingProgress || !progress}
        >
          {isResetting ? t("Réinitialisation…") : t("Relancer le tutoriel")}
        </button>
      </header>
      {progressError ? (
        <p className="onboarding__error" role="alert">
          {progressError}
        </p>
      ) : null}
      {isLoadingProgress && !progress ? (
        <p className="onboarding__loading" role="status">
          {t("Chargement du tutoriel…")}
        </p>
      ) : null}
      {progress && totalSteps ? (
        <>
          <ol
            className="onboarding__steps"
            role="list"
            aria-labelledby="onboarding-title"
          >
            {progress.steps.map((step, index) => {
              const isCompleted = progress.completedSteps.includes(step.id);
              const isCurrent =
                !isCompleted &&
                (progress.currentStepId === step.id ||
                  (!progress.currentStepId &&
                    !progress.isComplete &&
                    index === completedCount));
              const statusLabel = isCompleted
                ? t("Terminée")
                : isCurrent
                ? t("Étape en cours")
                : t("À faire");
              return (
                <li
                  key={step.id}
                  className={`onboarding-step${
                    isCompleted ? " onboarding-step--completed" : ""
                  }${isCurrent ? " onboarding-step--current" : ""}`}
                  role="listitem"
                >
                  <div className="onboarding-step__header">
                    <h3 className="onboarding-step__title">
                      {step.title}
                      {step.tooltip ? (
                        <Tooltip label={step.tooltip}>
                          <span aria-hidden="true">?</span>
                          <span className="sr-only">
                            {t("Aide sur {title}", { title: step.title })}
                          </span>
                        </Tooltip>
                      ) : null}
                    </h3>
                    <span
                      className={`badge onboarding-step__status${
                        isCompleted
                          ? " badge--success"
                          : isCurrent
                          ? " badge--info"
                          : " badge--neutral"
                      }`}
                    >
                      {statusLabel}
                    </span>
                  </div>
                  <p className="onboarding-step__description">{step.description}</p>
                  {step.videoUrl ? (
                    <details className="onboarding-step__video">
                      <summary>{t("Voir la vidéo d'accompagnement")}</summary>
                      <div className="onboarding-step__video-frame">
                        <iframe
                          src={step.videoUrl}
                          title={step.videoTitle || step.title}
                          allow="accelerometer; autoplay; encrypted-media"
                          allowFullScreen
                        />
                      </div>
                    </details>
                  ) : null}
                  {step.id === "api-keys" ? (
                    <div className="onboarding-step__panel">
                      {credentialsError ? (
                        <p className="onboarding-step__error" role="alert">
                          {credentialsError}
                        </p>
                      ) : null}
                      <div className="onboarding-credentials">
                        <div className="onboarding-credentials__list">
                          {isLoadingCredentials ? (
                            <p className="onboarding-step__info">
                              {t("Chargement des identifiants…")}
                            </p>
                          ) : credentials.length ? (
                            <ul>
                              {credentials.map((entry) => (
                                <li
                                  key={entry.broker}
                                  className="onboarding-credentials__item"
                                >
                                  <div>
                                    <strong>{entry.broker}</strong>
                                    <p>
                                      {t("Clé")}: {entry.api_key_masked || t("Non fournie")}
                                    </p>
                                    <p>
                                      {t("Secret")}: {entry.api_secret_masked || t("Non fourni")}
                                    </p>
                                    {entry.last_test_status ? (
                                      <p className="onboarding-step__meta">
                                        {t("Dernier test")}: {entry.last_test_status}
                                        {entry.last_tested_at
                                          ? ` · ${new Intl.DateTimeFormat(locale, {
                                              dateStyle: "short",
                                              timeStyle: "short",
                                            }).format(new Date(entry.last_tested_at))}`
                                          : ""}
                                      </p>
                                    ) : null}
                                  </div>
                                  <button
                                    type="button"
                                    className="onboarding-step__action onboarding-step__action--secondary"
                                    onClick={() => handleCredentialDelete(entry.broker)}
                                    disabled={isSavingCredential || isTestingCredential}
                                  >
                                    {t("Supprimer")}
                                  </button>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="onboarding-step__info">
                              {t("Aucune clé enregistrée pour le moment.")}
                            </p>
                          )}
                        </div>
                        <form
                          className="onboarding-credentials__form"
                          onSubmit={handleCredentialSave}
                        >
                          <div className="form-field">
                            <label htmlFor="onboarding-broker">
                              {t("Broker")}
                            </label>
                            <input
                              id="onboarding-broker"
                              name="broker"
                              type="text"
                              value={credentialForm.broker}
                              onChange={handleCredentialFieldChange}
                              required
                            />
                          </div>
                          <div className="form-field">
                            <label htmlFor="onboarding-api-key">
                              {t("Clé API")}
                            </label>
                            <input
                              id="onboarding-api-key"
                              name="apiKey"
                              type="text"
                              value={credentialForm.apiKey}
                              onChange={handleCredentialFieldChange}
                              placeholder={t("Nouvelle valeur ou vide pour conserver")}
                            />
                          </div>
                          <div className="form-field">
                            <label htmlFor="onboarding-api-secret">
                              {t("Secret API")}
                            </label>
                            <input
                              id="onboarding-api-secret"
                              name="apiSecret"
                              type="password"
                              value={credentialForm.apiSecret}
                              onChange={handleCredentialFieldChange}
                              placeholder={t("Nouvelle valeur ou vide pour conserver")}
                            />
                          </div>
                          <div className="onboarding-credentials__actions">
                            <button
                              type="submit"
                              className="onboarding-step__action"
                              disabled={
                                isSavingCredential ||
                                !credentialForm.broker ||
                                !credentialsSubmitEndpoint
                              }
                            >
                              {isSavingCredential
                                ? t("Enregistrement…")
                                : t("Enregistrer")}
                            </button>
                            <button
                              type="button"
                              className="onboarding-step__action onboarding-step__action--secondary"
                              onClick={handleTestCredential}
                              disabled={
                                isTestingCredential ||
                                !credentialForm.broker ||
                                !credentialsTestEndpoint
                              }
                            >
                              {isTestingCredential
                                ? t("Test en cours…")
                                : t("Tester la connexion")}
                            </button>
                          </div>
                          {testFeedback ? (
                            <p
                              className={`onboarding-credentials__test onboarding-credentials__test--${testFeedback.tone}`}
                              role="status"
                            >
                              {testFeedback.message}
                            </p>
                          ) : null}
                        </form>
                      </div>
                    </div>
                  ) : null}
                  {step.id === "execution-mode" ? (
                    <div className="onboarding-step__panel">
                      {modeError ? (
                        <p className="onboarding-step__error" role="alert">
                          {modeError}
                        </p>
                      ) : null}
                      {isLoadingMode ? (
                        <p className="onboarding-step__info">
                          {t("Chargement du mode d'exécution…")}
                        </p>
                      ) : (
                        <fieldset className="onboarding-mode">
                          <legend>{t("Sélectionnez le mode d'exécution")}</legend>
                          {modeOptions.map((option) => (
                            <label
                              key={option.value}
                              className="onboarding-mode__option"
                            >
                              <input
                                type="radio"
                                name="execution-mode"
                                value={option.value}
                                checked={modeState.mode === option.value}
                                onChange={() => handleModeChange(option.value)}
                                disabled={isUpdatingMode}
                              />
                              <span>{option.label}</span>
                            </label>
                          ))}
                        </fieldset>
                      )}
                      <p className="onboarding-mode__status">
                        {hasLiveCredentials ? (
                          <span className="badge badge--info">
                            {t("Broker connecté")}
                          </span>
                        ) : (
                          <span className="badge badge--neutral">
                            {t("Simulation (deterministic)")}
                          </span>
                        )}
                      </p>
                      {isUpdatingMode ? (
                        <p className="onboarding-step__info">
                          {t("Mise à jour du mode…")}
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="onboarding-step__actions">
                    <button
                      type="button"
                      className="onboarding-step__action"
                      onClick={() => handleComplete(step.id)}
                      disabled={
                        isCompleted ||
                        pendingStep === step.id ||
                        isResetting ||
                        isSavingCredential ||
                        isTestingCredential ||
                        isUpdatingMode
                      }
                    >
                      {pendingStep === step.id
                        ? t("Validation…")
                        : isCompleted
                        ? t("Terminée")
                        : t("Marquer comme terminée")}
                    </button>
                  </div>
                </li>
              );
            })}
          </ol>
        </>
      ) : null}
    </section>
  );
}
