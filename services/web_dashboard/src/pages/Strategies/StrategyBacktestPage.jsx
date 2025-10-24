import React from "react";
import { useTranslation } from "react-i18next";
import { StrategyBacktestConsole } from "../../strategies/backtest/index.js";
import { bootstrap } from "../../bootstrap";

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
    <div className="strategy-backtest-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Backtests de stratégies")}</h1>
        <p className="text text--muted">
          {t(
            "Sélectionnez un actif, une période et lancez un backtest pour visualiser les performances historiques."
          )}
        </p>
      </header>

      <StrategyBacktestConsole {...config} />
    </div>
  );
}
