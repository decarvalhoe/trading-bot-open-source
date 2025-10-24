import { beforeEach, describe, expect, it, vi } from "vitest";

const STORAGE_KEY = "web-dashboard.language";

const bootstrapPayload = {
  language: "fr",
  translations: {
    fr: { greeting: "Bonjour" },
    en: { greeting: "Hello" },
  },
  languages: ["fr", "en"],
};

function mountBootstrap(payload = bootstrapPayload) {
  const script = document.createElement("script");
  script.id = "i18n-bootstrap";
  script.type = "application/json";
  script.textContent = JSON.stringify(payload);
  document.body.appendChild(script);
}

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = "";
  window.localStorage.clear();
});

describe("i18n configuration", () => {
  it("prefers the persisted language when available", async () => {
    mountBootstrap();
    window.localStorage.setItem(STORAGE_KEY, "en");

    const module = await import("./config.js");
    const i18n = module.default;

    expect(i18n.language).toBe("en");
  });

  it("falls back to the bootstrap language when persistence is absent", async () => {
    mountBootstrap();

    const module = await import("./config.js");
    const i18n = module.default;

    expect(i18n.language).toBe("fr");
  });

  it("ignores persisted values that are not supported", async () => {
    mountBootstrap();
    window.localStorage.setItem(STORAGE_KEY, "de");

    const module = await import("./config.js");
    const i18n = module.default;

    expect(i18n.language).toBe("fr");
  });
});
