import { useCallback, useEffect, useMemo, useState } from "react";
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

export default function OnboardingApp({
  progressEndpoint,
  stepTemplate,
  resetEndpoint,
  userId,
}) {
  const [progress, setProgress] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pendingStep, setPendingStep] = useState(null);
  const [isResetting, setIsResetting] = useState(false);

  const baseHeaders = useMemo(() => {
    const headers = { Accept: "application/json" };
    if (userId) {
      headers["X-User-Id"] = userId;
    }
    return headers;
  }, [userId]);

  const fetchProgress = useCallback(async () => {
    if (!progressEndpoint) {
      setError("Point d'accès onboarding non configuré.");
      setProgress(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
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
      setError("Impossible de récupérer la progression pour le moment.");
      setProgress(null);
    } finally {
      setIsLoading(false);
    }
  }, [progressEndpoint, baseHeaders]);

  const handleComplete = useCallback(
    async (stepId) => {
      const target = buildStepUrl(stepTemplate, stepId);
      if (!target) {
        setError("Impossible de déterminer l'étape à enregistrer.");
        return;
      }
      setPendingStep(stepId);
      setError(null);
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
        setError("Enregistrement de l'étape impossible. Réessayez.");
      } finally {
        setPendingStep(null);
      }
    },
    [baseHeaders, stepTemplate]
  );

  const handleReset = useCallback(async () => {
    if (!resetEndpoint) {
      setError("Point d'accès de réinitialisation manquant.");
      return;
    }
    setIsResetting(true);
    setError(null);
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
    } catch (err) {
      console.error("Impossible de réinitialiser le tutoriel", err);
      setError("Réinitialisation impossible. Merci de réessayer.");
    } finally {
      setIsResetting(false);
    }
  }, [baseHeaders, resetEndpoint]);

  useEffect(() => {
    fetchProgress();
  }, [fetchProgress]);

  const totalSteps = progress?.steps?.length ?? 0;
  const completedCount = progress?.completedSteps?.length ?? 0;
  const summaryText = totalSteps
    ? `${completedCount} / ${totalSteps} étapes complétées${
        progress?.isComplete ? " – Parcours terminé !" : ""
      }`
    : "Chargement du parcours d'onboarding";

  return (
    <section
      className="onboarding__container"
      aria-busy={isLoading || Boolean(pendingStep) || isResetting}
    >
      <header className="onboarding__header">
        <p className="onboarding__summary" role="status" aria-live="polite">
          {summaryText}
        </p>
        <button
          type="button"
          className="onboarding__restart"
          onClick={handleReset}
          disabled={isResetting || isLoading || !progress}
        >
          {isResetting ? "Réinitialisation…" : "Relancer le tutoriel"}
        </button>
      </header>
      {error ? (
        <p className="onboarding__error" role="alert">
          {error}
        </p>
      ) : null}
      {isLoading && !progress ? (
        <p className="onboarding__loading" role="status">
          Chargement du tutoriel…
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
                  (!progress.currentStepId && !progress.isComplete && index === completedCount));
              const statusLabel = isCompleted
                ? "Terminée"
                : isCurrent
                ? "Étape en cours"
                : "À faire";
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
                          <span className="sr-only">Aide sur {step.title}</span>
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
                      <summary>Voir la vidéo d'accompagnement</summary>
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
                  <div className="onboarding-step__actions">
                    <button
                      type="button"
                      className="onboarding-step__action"
                      onClick={() => handleComplete(step.id)}
                      disabled={isCompleted || pendingStep === step.id || isLoading}
                    >
                      {pendingStep === step.id
                        ? "Enregistrement…"
                        : `Marquer "${step.title}" comme terminé`}
                    </button>
                  </div>
                </li>
              );
            })}
          </ol>
          <p className="onboarding__footnote text text--muted">
            {progress.updatedAt
              ? `Dernière mise à jour : ${new Date(progress.updatedAt).toLocaleString("fr-FR")}`
              : "Suivez les étapes pour débloquer l'ensemble des fonctionnalités."}
          </p>
        </>
      ) : null}
    </section>
  );
}
