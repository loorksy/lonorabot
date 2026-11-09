export function applyDirection(locale: string) {
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
}
export function isolated(value: string) {
  // The value's own direction controls would end the isolate early: drop them first.
  return `\u2068${value.replace(/[\u202a-\u202e\u2066-\u2069]/g, "")}\u2069`;
}
