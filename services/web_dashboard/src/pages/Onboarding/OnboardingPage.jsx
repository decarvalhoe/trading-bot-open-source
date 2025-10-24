import React from "react";
import { useTranslation } from "react-i18next";
import OnboardingApp from "../../onboarding/OnboardingApp.jsx";
import { bootstrap } from "../../bootstrap";

export default function OnboardingPage() {
  const { t } = useTranslation();
  const baseConfig = bootstrap?.config?.onboarding || {};
  const dashboardConfig = bootstrap?.data?.dashboard?.onboarding || {};
  const onboardingData = bootstrap?.data?.onboarding || {};
  const config = { ...baseConfig, ...dashboardConfig, ...onboardingData };

  return (
    <div className="onboarding-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Parcours d'onboarding")}</h1>
        <p className="text text--muted">
          {t(
            "Connectez votre broker, définissez votre mode de trading et complétez les étapes essentielles pour démarrer."
          )}
        </p>
      </header>

      <OnboardingApp {...config} />
    </div>
  );
}
