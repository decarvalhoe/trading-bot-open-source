import React from "react";
import { useTranslation } from "react-i18next";
import { StrategyBacktestConsole } from "../../strategies/backtest/index.js";
import { bootstrap } from "../../bootstrap";
import StrategyToolPageShell from "./StrategyToolPageShell.jsx";

export default function StrategyBacktestPage() {
  const { t } = useTranslation();
  const strategiesData = bootstrap?.data?.strategies || {};
  const strategiesConfig = bootstrap?.config?.strategies || {};
  const config =
    bootstrap?.data?.strategyBacktest ||
    bootstrap?.config?.strategyBacktest ||
    strategiesData.backtest ||
    strategiesConfig.backtest ||
    {};

  return (
    <StrategyToolPageShell
      className="strategy-backtest-page"
      title={t("Backtests de stratégies")}
      description={t(
        "Sélectionnez un actif, une période et lancez un backtest pour visualiser les performances historiques."
      )}
    >
      <StrategyBacktestConsole {...config} />
    </StrategyToolPageShell>
  );
}
