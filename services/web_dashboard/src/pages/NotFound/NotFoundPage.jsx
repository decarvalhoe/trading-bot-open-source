import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="not-found-page">
      <h1 className="heading heading--xl">{t("Page introuvable")}</h1>
      <p className="text text--muted">{t("La ressource demandée n'existe pas ou a été déplacée.")}</p>
      <Link className="button" to="/dashboard">
        {t("Retourner au tableau de bord")}
      </Link>
    </div>
  );
}
