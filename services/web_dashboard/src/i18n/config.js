import i18next from "i18next";
import { initReactI18next } from "react-i18next";

export const LANGUAGE_STORAGE_KEY = "web-dashboard.language";

function readBootstrapTranslations() {
  const node = document.getElementById("i18n-bootstrap");
  if (!node || !node.textContent) {
    return {
      language: "fr",
      resources: {},
      languages: ["fr", "en"],
    };
  }
  try {
    const payload = JSON.parse(node.textContent);
    if (!payload || typeof payload !== "object") {
      return {
        language: "fr",
        resources: {},
        languages: ["fr", "en"],
      };
    }
    return {
      language: payload.language || "fr",
      resources: payload.translations || {},
      languages: Array.isArray(payload.languages) && payload.languages.length
        ? payload.languages
        : ["fr", "en"],
    };
  } catch (error) {
    return {
      language: "fr",
      resources: {},
      languages: ["fr", "en"],
    };
  }
}

const bootstrap = readBootstrapTranslations();

function readPersistedLanguage(languages) {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (!stored) {
      return null;
    }
    if (Array.isArray(languages) && languages.includes(stored)) {
      return stored;
    }
    return null;
  } catch (error) {
    return null;
  }
}

const supportedLanguages =
  Array.isArray(bootstrap.languages) && bootstrap.languages.length ? bootstrap.languages : ["fr", "en"];

const resources = Object.fromEntries(
  Object.entries(bootstrap.resources).map(([language, catalog]) => [
    language,
    { translation: catalog },
  ])
);

const persistedLanguage = readPersistedLanguage(supportedLanguages);
const fallbackLanguage = supportedLanguages.includes("fr") ? "fr" : supportedLanguages[0] || "fr";
const bootstrapLanguage =
  supportedLanguages.includes(bootstrap.language) && bootstrap.language ? bootstrap.language : fallbackLanguage;
const initialLanguage = persistedLanguage || bootstrapLanguage;

const i18n = i18next.createInstance();

if (!i18n.isInitialized) {
  i18n.use(initReactI18next).init({
    resources,
    lng: initialLanguage,
    fallbackLng: fallbackLanguage,
    supportedLngs: supportedLanguages,
    interpolation: {
      escapeValue: false,
    },
  });
}

export const availableLanguages = supportedLanguages;

export default i18n;
