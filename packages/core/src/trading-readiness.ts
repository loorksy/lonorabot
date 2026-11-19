/**
 * The agent's status line, its sheet and their labels, shared by Web and Mobile.
 *
 * Everything here renders the server's presentation-only readiness projection; nothing
 * in a client decides whether a trade may be sent. Arabic is first-class: tickers and
 * numbers are isolated (U+2068/U+2069) so they keep their order inside Arabic text.
 */
import type { TradingReadiness } from "@lonora/contracts";

type Language = "ar" | "en";
type Text = { readonly en: string; readonly ar: string };

function language(locale: string): Language {
  return locale.startsWith("ar") ? "ar" : "en";
}

/** Keep a ticker, number or time in its own direction inside the surrounding text. */
export function isolate(value: string): string {
  // An embedded isolate end or override would end the isolate early and reorder the
  // rest of the line, so the value's own direction controls are dropped first.
  return `⁨${value.replace(/[\u202a-\u202e\u2066-\u2069]/g, "")}⁩`;
}

/** The list separator of the owner's language: the Arabic comma only in Arabic. */
export function listSeparator(locale: string): string {
  return language(locale) === "ar" ? "، " : ", ";
}

export const tradingSafetyLabels = {
  en: {
    title: "Trading safety",
    open: "Trading safety: can it trade now",
    level: "Trading level",
    analysis: "No trading",
    supervised: "Ask me",
    autonomous: "On its own (signed)",
    grants: "Signed grant",
    fullDelegation: "Full delegation",
    allPairs: "All pairs on this account",
    untilStopped: "until you stop it",
    until: "until",
    manualIncluded: "Your own positions included",
    manualExcluded: "Your own positions excluded",
    unresolved: "Awaiting broker confirmation",
    noUnresolved: "No operation is waiting for the broker.",
    uncertainHint:
      "It will not be sent again. New risk on this market is held until it settles; exits stay allowed.",
    close: "Close",
  },
  ar: {
    title: "أمان التداول",
    open: "أمان التداول: هل يمكنه التداول الآن",
    level: "مستوى التداول",
    analysis: "لا يتداول",
    supervised: "يسألني أولًا",
    autonomous: "مستقل ضمن تفويضي الموقّع",
    grants: "تفويض موقّع",
    fullDelegation: "تفويض كامل",
    allPairs: "كل أزواج هذا الحساب",
    untilStopped: "حتى توقفه",
    until: "حتى",
    manualIncluded: "يشمل مراكزك اليدوية",
    manualExcluded: "لا يشمل مراكزك اليدوية",
    unresolved: "بانتظار تأكيد الوسيط",
    noUnresolved: "لا توجد عملية بانتظار الوسيط.",
    uncertainHint:
      "لن تُرسل مجددًا. المخاطرة الجديدة على هذا السوق معلّقة حتى تُحسم؛ يبقى الخروج متاحًا.",
    close: "إغلاق",
  },
} as const satisfies Record<Language, Record<string, string>>;
export type TradingSafetyText = (typeof tradingSafetyLabels)[Language];

export function tradingSafetyText(locale: string): TradingSafetyText {
  return tradingSafetyLabels[language(locale)];
}

/** A short local time today, otherwise day and time; isolated for Arabic text. */
export function readinessTime(iso: string, locale: string, now: Date = new Date()): string {
  const when = new Date(iso);
  const sameDay = when.toDateString() === now.toDateString();
  const formatted = when.toLocaleString(
    language(locale),
    sameDay
      ? { hour: "2-digit", minute: "2-digit" }
      : { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" },
  );
  return isolate(formatted);
}

/**
 * The one line: the agent's ladder level, or the strongest thing stopping it, in the
 * owner's language. Built only from the server's projection. ``accountName`` names the
 * grant's account when the owner has several (null keeps the line without it).
 */
export function tradingReadinessLine(
  readiness: TradingReadiness,
  locale: string,
  now: Date = new Date(),
  accountName: (id: string) => string | null = () => null,
): string {
  const lang = language(locale);
  const ar = lang === "ar";
  const params = readiness.params;
  const until = (iso: string | null | undefined, open: Text) =>
    iso ? `${ar ? "حتى" : "until"} ${readinessTime(iso, locale, now)}` : ar ? open.ar : open.en;
  switch (readiness.state) {
    case "no_trading":
      return ar ? "لا يتداول · تحليل فقط" : "No trading · analysis only";
    case "agent_paused":
      return ar ? "الوكيل متوقف مؤقتًا · لا صفقات جديدة" : "Agent paused · no new trades";
    case "uncertain": {
      const count = params.count ?? 1;
      const head = ar
        ? count === 1
          ? "عملية بانتظار تأكيد الوسيط"
          : `عمليات بانتظار تأكيد الوسيط: ${isolate(String(count))}`
        : count === 1
          ? "1 operation awaiting broker confirmation"
          : `${count} operations awaiting broker confirmation`;
      const symbol = params.symbol
        ? ar
          ? ` · المخاطرة الجديدة على ${isolate(params.symbol)} معلّقة`
          : ` · new risk on ${params.symbol} held`
        : "";
      return head + symbol;
    }
    case "ask_me":
      return ar ? "يسألك قبل كل صفقة" : "Asks you before each trade";
    case "on_its_own": {
      const accounts = params.account_count ?? 1;
      if (accounts > 1)
        // One grant per account: the line counts them, the sheet names each.
        return ar
          ? `يتداول باستقلال على ${isolate(String(accounts))} حسابات`
          : `Trades on its own on ${accounts} accounts`;
      const account = params.account_id ? accountName(params.account_id) : null;
      // Full delegation already says every pair, every action and the owner's positions.
      const markets = params.full_delegation
        ? tradingSafetyLabels[lang].fullDelegation
        : params.symbol_scope === "account"
          ? tradingSafetyLabels[lang].allPairs
          : (params.symbols ?? []).map(isolate).join(listSeparator(locale));
      const end = until(params.valid_until, { en: "until you stop it", ar: "حتى توقفه" });
      return `${ar ? "يتداول باستقلال" : "Trades on its own"}${account ? ` · ${isolate(account)}` : ""}${markets ? ` · ${markets}` : ""} · ${end}`;
    }
  }
}

/** The pill's tone: whether anything is stopping or holding new trades right now. */
export function tradingReadinessTone(
  readiness: TradingReadiness,
): "ready" | "asks" | "held" | "idle" {
  switch (readiness.state) {
    case "on_its_own":
      return "ready";
    case "ask_me":
      return "asks";
    case "no_trading":
      return "idle";
    default:
      return "held";
  }
}
