import React, { Fragment, useMemo } from "react";
import PropTypes from "prop-types";
import { useTranslation } from "react-i18next";
import { Listbox, Transition } from "@headlessui/react";
import { CheckIcon, ChevronUpDownIcon, GlobeAltIcon } from "@heroicons/react/24/outline";
import i18nInstance, { LANGUAGE_STORAGE_KEY, availableLanguages } from "../i18n/config.js";

function persistLanguage(code) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, code);
  } catch (error) {
    // Ignored: persistence is a best-effort improvement only.
  }
}

function resolveLanguages() {
  if (Array.isArray(availableLanguages) && availableLanguages.length) {
    return availableLanguages;
  }
  if (Array.isArray(i18nInstance.languages) && i18nInstance.languages.length) {
    return i18nInstance.languages;
  }
  return [];
}

export default function LanguageSwitcher({ className }) {
  const { t, i18n } = useTranslation();

  const languages = useMemo(
    () =>
      resolveLanguages()
        .filter((code) => code && code !== "cimode")
        .map((code) => ({
          code,
          label: code.toUpperCase(),
        })),
    [i18n.language],
  );

  const activeLanguage = useMemo(
    () => languages.find((item) => item.code === (i18n.resolvedLanguage || i18n.language)) || languages[0],
    [i18n.language, i18n.resolvedLanguage, languages],
  );

  const handleSelect = (item) => {
    if (!item) {
      return;
    }
    persistLanguage(item.code);
    i18n.changeLanguage(item.code);
  };

  if (!languages.length) {
    return null;
  }

  return (
    <Listbox value={activeLanguage} onChange={handleSelect}>
      <div className={className}>
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

LanguageSwitcher.propTypes = {
  className: PropTypes.string,
};

LanguageSwitcher.defaultProps = {
  className: "",
};
