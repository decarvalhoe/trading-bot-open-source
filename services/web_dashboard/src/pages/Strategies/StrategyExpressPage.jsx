import React from "react";
import { useTranslation } from "react-i18next";
import { OneClickStrategyBuilder } from "../../strategies/simple/index.js";
import { bootstrap } from "../../bootstrap";
import StrategyToolPageShell from "./StrategyToolPageShell.jsx";

export default function StrategyExpressPage() {
  const { t } = useTranslation();
  const config =
    bootstrap?.data?.strategyExpress || bootstrap?.config?.strategyExpress || {};

  return (
    <StrategyToolPageShell
      className="strategy-express-page"
      title={t("Stratégie express")}
      description={t("Créez une stratégie en quelques clics et lancez un backtest instantané.")}
    >
      <OneClickStrategyBuilder {...config} />
    </StrategyToolPageShell>
  );
}
