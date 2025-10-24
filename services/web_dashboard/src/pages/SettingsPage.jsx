import React from "react";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "../components/LanguageSwitcher.jsx";
import AccountSettingsPage from "./Account/AccountSettingsPage.jsx";

export default function SettingsPage() {
  const { t } = useTranslation();

  return (
    <div className="settings-page grid gap-8">
      <section className="card" aria-labelledby="language-preferences-title">
        <div className="card__header">
          <h1 id="language-preferences-title" className="heading heading--lg">
            {t("Préférences linguistiques")}
          </h1>
          <p className="text text--muted">
            {t("Choisissez la langue de l'interface. Votre sélection est mémorisée pour vos prochaines visites.")}
          </p>
        </div>
        <div className="card__body">
          <LanguageSwitcher className="max-w-xs" />
        </div>
      </section>

      <AccountSettingsPage />
    </div>
  );
}
