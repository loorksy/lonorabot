import { I18nProvider } from "@lingui/react";
import { createRoot } from "react-dom/client";
import { ChartRenderBridge } from "./components/charts/ChartRenderBridge";
import { activateLocale, i18n } from "./i18n/config";
import "./styles.css";

activateLocale(new URLSearchParams(window.location.search).get("locale") === "ar" ? "ar" : "en");
const root = document.getElementById("root");
if (!root) throw new Error("root_element_missing");
createRoot(root).render(
  <I18nProvider i18n={i18n}>
    <ChartRenderBridge />
  </I18nProvider>,
);
