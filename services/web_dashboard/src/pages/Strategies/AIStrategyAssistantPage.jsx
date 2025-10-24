import React from "react";
import { useTranslation } from "react-i18next";
import { AIStrategyAssistant } from "../../strategies/assistant/index.js";
import { bootstrap } from "../../bootstrap";

export default function AIStrategyAssistantPage() {
  const { t } = useTranslation();
  const strategiesData = bootstrap?.data?.strategies || {};
  const strategiesConfig = bootstrap?.config?.strategies || {};
  const config =
    bootstrap?.data?.aiStrategyAssistant ||
    bootstrap?.config?.aiStrategyAssistant ||
    strategiesData.assistant ||
    strategiesConfig.assistant ||
    {};

  return (
    <div className="strategy-assistant-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Assistant IA pour stratégies")}</h1>
        <p className="text text--muted">
          {t(
            "Décrivez votre idée en langage naturel pour obtenir des suggestions et un brouillon de stratégie."
          )}
        </p>
      </header>

      <AIStrategyAssistant {...config} />
    </div>
  );
}
