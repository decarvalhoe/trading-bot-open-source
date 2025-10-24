import React from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";

const NAV_LINKS = [
  { to: "/dashboard", labelKey: "Tableau de bord" },
  { to: "/marketplace", labelKey: "Marketplace" },
  { to: "/dashboard/followers", labelKey: "Suivi copies" },
  { to: "/strategies", labelKey: "Stratégies" },
  { to: "/strategies/new", labelKey: "Stratégie express" },
  { to: "/strategies/documentation", labelKey: "Documentation stratégies" },
  { to: "/help", labelKey: "Aide & formation" },
  { to: "/status", labelKey: "Statut services" },
  { to: "/account", labelKey: "Compte & API" },
];

function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const handleChange = (event) => {
    const value = event.target.value;
    const url = new URL(window.location.href);
    url.searchParams.set("lang", value);
    window.location.href = url.toString();
  };

  return (
    <label className="language-switcher">
      <span className="visually-hidden">{t("Langue")}</span>
      <select defaultValue={i18n.language} onChange={handleChange}>
        {i18n.languages?.map((code) => (
          <option key={code} value={code}>
            {code.toUpperCase()}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function DashboardLayout() {
  const { t } = useTranslation();
  const location = useLocation();
  const auth = useAuth();

  return (
    <div className="app-shell">
      <aside className="app-sidebar" aria-label={t("Navigation principale")}>
        <div className="app-sidebar__brand">Trading Bot</div>
        <nav className="app-sidebar__nav app-nav">
          {NAV_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} className={({ isActive }) => `app-nav__link${isActive ? " app-nav__link--active" : ""}`}>
              {t(link.labelKey)}
            </NavLink>
          ))}
        </nav>
        <LanguageSwitcher />
      </aside>
      <div className="app-content">
        <header className="layout__header">
          <div className="layout__header-meta">
            {auth.status === "authenticated" && auth.user && (
              <span className="layout__user">{auth.user.email || auth.user.id}</span>
            )}
            {auth.status === "authenticated" && (
              <button type="button" className="button button--ghost" onClick={auth.logout}>
                {t("Déconnexion")}
              </button>
            )}
          </div>
        </header>
        <main key={location.pathname} className="layout__main">
          <Outlet />
        </main>
        <footer className="layout__footer">
          <p className="text text--muted">{t("Données d'exemple pour la démonstration du service.")}</p>
        </footer>
      </div>
    </div>
  );
}
