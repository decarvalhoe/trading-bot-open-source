import React, { Fragment, useMemo } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Listbox, Transition } from "@headlessui/react";
import { ArrowRightOnRectangleIcon, CheckIcon, ChevronUpDownIcon, GlobeAltIcon } from "@heroicons/react/24/outline";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button.jsx";

const NAV_LINKS = [
  { to: "/dashboard", labelKey: "Tableau de bord" },
  { to: "/trading/orders", labelKey: "Ordres" },
  { to: "/trading/positions", labelKey: "Positions" },
  { to: "/trading/execute", labelKey: "Passer un ordre" },
  { to: "/market", labelKey: "Marché temps réel" },
  { to: "/alerts", labelKey: "Alertes" },
  { to: "/reports", labelKey: "Rapports" },
  { to: "/marketplace", labelKey: "Marketplace" },
  { to: "/dashboard/followers", labelKey: "Suivi copies" },
  { to: "/strategies", labelKey: "Stratégies" },
  { to: "/strategies/new", labelKey: "Stratégie express" },
  { to: "/strategies/documentation", labelKey: "Documentation stratégies" },
  { to: "/help", labelKey: "Aide & formation" },
  { to: "/status", labelKey: "Statut services" },
  { to: "/account/settings", labelKey: "Compte & API" },
];

function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const languages = useMemo(
    () =>
      (i18n.languages || []).map((code) => ({
        code,
        label: code.toUpperCase(),
      })),
    [i18n.languages],
  );

  const activeLanguage = languages.find((item) => item.code === i18n.language) || languages[0];

  const handleSelect = (item) => {
    const url = new URL(window.location.href);
    url.searchParams.set("lang", item.code);
    window.location.href = url.toString();
  };

  if (!languages.length) {
    return null;
  }

  return (
    <Listbox value={activeLanguage} onChange={handleSelect}>
      <div>
        <Listbox.Label className="visually-hidden">{t("Langue")}</Listbox.Label>
        <div className="relative mt-4">
          <Listbox.Button className="inline-flex w-full items-center justify-between gap-3 rounded-xl border border-slate-800/60 bg-slate-900/70 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-200 shadow-inner shadow-slate-950/40">
            <span className="inline-flex items-center gap-2">
              <GlobeAltIcon aria-hidden="true" className="h-4 w-4 text-slate-400" />
              {activeLanguage?.label}
            </span>
            <ChevronUpDownIcon aria-hidden="true" className="h-4 w-4 text-slate-500" />
          </Listbox.Button>
          <Transition
            as={Fragment}
            leave="transition ease-in duration-100"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <Listbox.Options className="absolute right-0 z-50 mt-2 w-40 overflow-hidden rounded-2xl border border-slate-800/60 bg-slate-900/90 p-1 text-xs text-slate-200 shadow-xl shadow-slate-950/50 backdrop-blur">
              {languages.map((item) => (
                <Listbox.Option
                  key={item.code}
                  value={item}
                  className={({ active }) =>
                    `flex cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-2 transition ${
                      active ? "bg-slate-800/70 text-white" : "text-slate-300"
                    }`
                  }
                >
                  {({ selected }) => (
                    <>
                      <span className="font-semibold">{item.label}</span>
                      {selected ? <CheckIcon aria-hidden="true" className="h-4 w-4" /> : null}
                    </>
                  )}
                </Listbox.Option>
              ))}
            </Listbox.Options>
          </Transition>
        </div>
      </div>
    </Listbox>
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
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => `app-nav__link${isActive ? " app-nav__link--active" : ""}`}
            >
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
              <Button type="button" variant="ghost" size="sm" onClick={auth.logout}>
                <ArrowRightOnRectangleIcon aria-hidden="true" className="h-4 w-4" />
                {t("Déconnexion")}
              </Button>
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
