import { i18n } from "@lingui/core";
import { I18nProvider } from "@lingui/react";
import { brand } from "@lonora/ui-tokens";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ChartRenderBridge } from "./components/charts/ChartRenderBridge";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { activateLocale } from "./i18n/config";
import { A11Y_DEFAULTS, applyA11y, readDevicePref } from "./shell/settings/device-prefs";
import "./styles.css";

document.title = brand.name;
const rendererLocale =
  window.location.pathname === "/charts/render"
    ? new URLSearchParams(window.location.search).get("locale")
    : undefined;
activateLocale((rendererLocale ?? localStorage.getItem("lonora.locale")) === "en" ? "en" : "ar");
// «سهولة الاستخدام» applies from the first paint.
applyA11y(readDevicePref("a11y", A11Y_DEFAULTS));
const root = document.getElementById("root");
if (!root) throw new Error("root_element_missing");
ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <I18nProvider i18n={i18n}>
      <ErrorBoundary>
        <BrowserRouter>
          {window.location.pathname === "/charts/render" ? <ChartRenderBridge /> : <App />}
        </BrowserRouter>
      </ErrorBoundary>
    </I18nProvider>
  </React.StrictMode>,
);
