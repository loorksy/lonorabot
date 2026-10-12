import { i18n } from "@lingui/core";
import { I18nProvider } from "@lingui/react";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { activateLocale } from "./i18n/config";
import "./styles.css";

activateLocale(localStorage.getItem("lonora.locale") === "en" ? "en" : "ar");
const root = document.getElementById("root");
if (!root) throw new Error("root_element_missing");
ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <I18nProvider i18n={i18n}>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </I18nProvider>
  </React.StrictMode>,
);
