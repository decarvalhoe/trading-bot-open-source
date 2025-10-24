import React from "react";
import { useTranslation } from "react-i18next";
import { OneClickStrategyBuilder } from "../../strategies/simple/index.js";
import { bootstrap } from "../../bootstrap";

export default function StrategyExpressPage() {
  const { t } = useTranslation();
  const config =
    bootstrap?.data?.strategyExpress || bootstrap?.config?.strategyExpress || {};

  return (
    <div className="strategy-express-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Stratégie express")}</h1>
        <p className="text text--muted">
          {t("Créez une stratégie en quelques clics et lancez un backtest instantané.")}
        </p>
      </header>
      <OneClickStrategyBuilder {...config} />
    </div>
  );
}
