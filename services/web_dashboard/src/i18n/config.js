import i18next from "i18next";
import { initReactI18next } from "react-i18next";

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

const resources = Object.fromEntries(
  Object.entries(bootstrap.resources).map(([language, catalog]) => [
    language,
    { translation: catalog },
  ])
);

if (!i18next.isInitialized) {
  i18next.use(initReactI18next).init({
    resources,
    lng: bootstrap.language,
    fallbackLng: "fr",
    interpolation: {
      escapeValue: false,
    },
  });
}

export const availableLanguages = bootstrap.languages;

export default i18next;
