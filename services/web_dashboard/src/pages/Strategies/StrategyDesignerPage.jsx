import React from "react";
import { useTranslation } from "react-i18next";
import { StrategyDesigner } from "../../strategies/designer/index.js";
import { bootstrap } from "../../bootstrap";
import StrategyToolPageShell from "./StrategyToolPageShell.jsx";

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
    <StrategyToolPageShell
      className="strategy-designer-page"
      title={t("Éditeur de stratégies")}
      description={t(
        "Assemblez blocs de conditions, indicateurs et actions pour concevoir votre stratégie algorithmique."
      )}
    >
      <StrategyDesigner {...config} />
    </StrategyToolPageShell>
  );
}
