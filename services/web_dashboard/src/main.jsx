import React, { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import App from "./App.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import i18n from "./i18n/config.js";
import "./index.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});

document.documentElement.classList.add("dark");

const container = document.getElementById("root");

if (!container) {
  throw new Error("Impossible de trouver l'élément #root pour monter l'application.");
}

const root = createRoot(container);

root.render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </I18nextProvider>
  </StrictMode>
);
