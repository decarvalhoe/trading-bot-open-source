import React from "react";
import { useTranslation } from "react-i18next";
import { StrategyDesigner } from "../../strategies/designer/index.js";
import { StrategyBacktestConsole } from "../../strategies/backtest/index.js";
import { AIStrategyAssistant } from "../../strategies/assistant/index.js";
import { bootstrap } from "../../bootstrap";

export default function StrategiesPage() {
  const { t } = useTranslation();
  const strategiesData = bootstrap?.data?.strategies || {};
  const strategiesConfig = bootstrap?.config?.strategies || {};
  const designerConfig = strategiesData.designer || strategiesConfig.designer || {};
  const backtestConfig = strategiesData.backtest || strategiesConfig.backtest || {};
  const assistantConfig = strategiesData.assistant || strategiesConfig.assistant || {};

  return (
    <div className="strategies-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Composer une stratégie")}</h1>
        <p className="text text--muted">
          {t("Assemblez conditions, indicateurs et actions avant d'envoyer votre stratégie vers l'algo-engine.")}
        </p>
      </header>

      <section className="card card--designer" aria-labelledby="designer-card-title">
        <div className="card__header">
          <h2 id="designer-card-title" className="heading heading--lg">
            {t("Éditeur visuel")}
          </h2>
          <p className="text text--muted">
            {t("Faites glisser les blocs depuis la bibliothèque pour créer votre logique et déclencher des exécutions.")}
          </p>
        </div>
        <div className="card__body">
          <StrategyDesigner {...designerConfig} />
        </div>
      </section>

      <section className="card card--backtest" aria-labelledby="backtest-card-title">
        <div className="card__header">
          <h2 id="backtest-card-title" className="heading heading--lg">
            {t("Backtests")}
          </h2>
          <p className="text text--muted">
            {t("Sélectionnez un actif et une période pour exécuter un backtest et visualiser l'équity.")}
          </p>
        </div>
        <div className="card__body">
          <StrategyBacktestConsole {...backtestConfig} />
        </div>
      </section>

      <section className="card card--assistant" aria-labelledby="assistant-card-title">
        <div className="card__header">
          <h2 id="assistant-card-title" className="heading heading--lg">
            {t("Assistant IA")}
          </h2>
          <p className="text text--muted">
            {t("Décrivez votre idée en langage naturel pour obtenir un brouillon de stratégie prêt à être importé.")}
          </p>
        </div>
        <div className="card__body">
          <AIStrategyAssistant {...assistantConfig} />
        </div>
      </section>
    </div>
  );
}
