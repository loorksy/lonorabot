import { i18n } from "@lingui/core";
import { applyDirection } from "./direction";
import { messages as ar } from "./locales/ar/messages.po";
import { messages as en } from "./locales/en/messages.po";
export type Locale = "ar" | "en";
export function activateLocale(locale: Locale) {
  i18n.loadAndActivate({ locale, messages: locale === "ar" ? ar : en });
  applyDirection(locale);
  localStorage.setItem("lonora.locale", locale);
}
activateLocale(localStorage.getItem("lonora.locale") === "en" ? "en" : "ar");

export { i18n };
