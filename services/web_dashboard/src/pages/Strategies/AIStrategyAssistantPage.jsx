import React from "react";
import { useTranslation } from "react-i18next";
import { AIStrategyAssistant } from "../../strategies/assistant/index.js";
import { bootstrap } from "../../bootstrap";
import StrategyToolPageShell from "./StrategyToolPageShell.jsx";

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
    <StrategyToolPageShell
      className="strategy-assistant-page"
      title={t("Assistant IA pour stratégies")}
      description={t(
        "Décrivez votre idée en langage naturel pour obtenir des suggestions et un brouillon de stratégie."
      )}
    >
      <AIStrategyAssistant {...config} />
    </StrategyToolPageShell>
  );
}
