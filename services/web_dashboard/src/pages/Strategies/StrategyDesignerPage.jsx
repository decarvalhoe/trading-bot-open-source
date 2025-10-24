import React from "react";
import { useTranslation } from "react-i18next";
import { StrategyDesigner } from "../../strategies/designer/index.js";
import { bootstrap } from "../../bootstrap";

export default function StrategyDesignerPage() {
  const { t } = useTranslation();
  const strategiesData = bootstrap?.data?.strategies || {};
  const strategiesConfig = bootstrap?.config?.strategies || {};
  const config =
    bootstrap?.data?.strategyDesigner ||
    bootstrap?.config?.strategyDesigner ||
    strategiesData.designer ||
    strategiesConfig.designer ||
    {};

  return (
    <div className="strategy-designer-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Éditeur de stratégies")}</h1>
        <p className="text text--muted">
          {t(
            "Assemblez blocs de conditions, indicateurs et actions pour concevoir votre stratégie algorithmique."
          )}
        </p>
      </header>

      <StrategyDesigner {...config} />
    </div>
  );
}
