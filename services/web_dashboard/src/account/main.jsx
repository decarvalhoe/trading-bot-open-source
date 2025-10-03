import React from "react";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import AccountApp from "./AccountApp.jsx";
import i18n from "../i18n/config.js";

function bootstrap() {
  const container = document.getElementById("account-app");
  if (!container) {
    return;
  }

  const { sessionEndpoint, loginEndpoint, logoutEndpoint } = container.dataset;
  if (!sessionEndpoint || !loginEndpoint || !logoutEndpoint) {
    console.error("Endpoints manquants pour initialiser la gestion de compte");
    return;
  }

  const root = createRoot(container);
  root.render(
    <React.StrictMode>
      <I18nextProvider i18n={i18n}>
        <AccountApp
          endpoints={{
            session: sessionEndpoint,
            login: loginEndpoint,
            logout: logoutEndpoint
          }}
        />
      </I18nextProvider>
    </React.StrictMode>
  );
}

bootstrap();
