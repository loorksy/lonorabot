/**
 * The header safety pill, its sheet and the brake labels, shared by Web and Mobile.
 *
 * Everything here renders the server's presentation-only readiness projection; nothing
 * in a client decides whether a trade may be sent. Arabic is first-class: tickers and
 * numbers are isolated (U+2068/U+2069) so they keep their order inside Arabic text.
 */
import type {
  GlobalTrading,
  MoneyLimitName,
  MoneyLimits,
  RestrictionActionClass,
  TradingReadiness,
} from "@lonora/contracts";

type Language = "ar" | "en";
type Text = { readonly en: string; readonly ar: string };

function language(locale: string): Language {
  return locale.startsWith("ar") ? "ar" : "en";
}

/** Keep a ticker, number or time in its own direction inside the surrounding text. */
export function isolate(value: string): string {
  return `⁨${value}⁩`;
}

export const tradingSafetyLabels = {
  en: {
    title: "Trading safety",
    open: "Trading safety: can it trade now",
    stop: "Stop new trading",
    resume: "Resume trading",
    start: "Start trading",
    stopHint:
      "Stops new risk for every agent and your manual orders. Exits stay allowed: closing positions, cancelling orders and tightening stops.",
    resumeHint: "Resuming widens no authority: each agent still trades only within its level.",
    startHint: "Starting widens no authority: each agent still trades only within its level.",
    running: "New trading is running",
    stopped: "New trading is stopped",
    since: "since",
    neverStarted: "Trading has not been started yet.",
    level: "Trading level",
    analysis: "No trading",
    supervised: "Ask me",
    autonomous: "On its own (signed)",
    grants: "Signed grant",
    allPairs: "All pairs on this account",
    untilStopped: "until you stop it",
    until: "until",
    manualIncluded: "Your own positions included",
    manualExcluded: "Your own positions excluded",
    pauses: "Pauses",
    noPauses: "No pauses",
    allAgents: "All agents",
    thisAgent: "This agent",
    includesManual: "includes your manual orders",
    setByYou: "Set by you",
    fromYourMessage: "Recorded from your message",
    setByAgent: "Set by an agent",
    onlyYouLift: "Only you can lift a pause.",
    lift: "Lift pause",
    starts: "starts",
    noEnd: "no end time",
    moneyLimits: "Money limits",
    noMoneyLimit: "No money limit set",
    unresolved: "Awaiting broker confirmation",
    noUnresolved: "No operation is waiting for the broker.",
    uncertainHint:
      "It will not be sent again. New risk on this market is held until it settles; exits stay allowed.",
    exitsFrozen: "A freeze is active: exits are blocked too.",
    close: "Close",
    loading: "Loading…",
  },
  ar: {
    title: "أمان التداول",
    open: "أمان التداول: هل يمكنه التداول الآن",
    stop: "إيقاف الصفقات الجديدة",
    resume: "استئناف التداول",
    start: "بدء التداول",
    stopHint:
      "يوقف المخاطرة الجديدة لكل الوكلاء ولأوامرك اليدوية. يبقى الخروج متاحًا: إغلاق المراكز وإلغاء الأوامر وتقريب وقف الخسارة.",
    resumeHint: "الاستئناف لا يوسّع أي صلاحية: كل وكيل يبقى ضمن مستوى تداوله.",
    startHint: "البدء لا يوسّع أي صلاحية: كل وكيل يبقى ضمن مستوى تداوله.",
    running: "التداول الجديد يعمل",
    stopped: "التداول الجديد متوقف",
    since: "منذ",
    neverStarted: "لم يبدأ التداول بعد.",
    level: "مستوى التداول",
    analysis: "لا يتداول",
    supervised: "يسألني أولًا",
    autonomous: "مستقل ضمن تفويضي الموقّع",
    grants: "تفويض موقّع",
    allPairs: "كل أزواج هذا الحساب",
    untilStopped: "حتى توقفه",
    until: "حتى",
    manualIncluded: "يشمل مراكزك اليدوية",
    manualExcluded: "لا يشمل مراكزك اليدوية",
    pauses: "الإيقافات",
    noPauses: "لا توجد إيقافات",
    allAgents: "كل الوكلاء",
    thisAgent: "هذا الوكيل",
    includesManual: "يشمل أوامرك اليدوية",
    setByYou: "وضعته أنت",
    fromYourMessage: "سُجّل من رسالتك",
    setByAgent: "وضعه وكيل",
    onlyYouLift: "أنت وحدك من يرفع الإيقاف.",
    lift: "رفع الإيقاف",
    starts: "يبدأ",
    noEnd: "دون وقت انتهاء",
    moneyLimits: "الحدود المالية",
    noMoneyLimit: "لا حد مالي محدد",
    unresolved: "بانتظار تأكيد الوسيط",
    noUnresolved: "لا توجد عملية بانتظار الوسيط.",
    uncertainHint:
      "لن تُرسل مجددًا. المخاطرة الجديدة على هذا السوق معلّقة حتى تُحسم؛ يبقى الخروج متاحًا.",
    exitsFrozen: "يوجد تجميد نشط: الخروج محظور أيضًا.",
    close: "إغلاق",
    loading: "جارٍ التحميل…",
  },
} as const satisfies Record<Language, Record<string, string>>;
export type TradingSafetyText = (typeof tradingSafetyLabels)[Language];

export function tradingSafetyText(locale: string): TradingSafetyText {
  return tradingSafetyLabels[language(locale)];
}

/**
 * The sheet's one brake: Stop while new trading runs; while it is stopped, Start when the
 * owner never started it (the first-run default) and Resume after the owner stopped it.
 */
export function tradingBrake(
  trading: GlobalTrading,
  locale: string,
): { stopped: boolean; status: string; hint: string; action: string } {
  const text = tradingSafetyText(locale);
  if (trading.state === "running")
    return { stopped: false, status: text.running, hint: text.stopHint, action: text.stop };
  if (trading.changed_by === "default")
    return { stopped: true, status: text.neverStarted, hint: text.startHint, action: text.start };
  return { stopped: true, status: text.stopped, hint: text.resumeHint, action: text.resume };
}

const pauseClass: Readonly<Record<RestrictionActionClass, Text>> = {
  no_new_entries: { en: "no new entries", ar: "لا صفقات جديدة" },
  no_risk_increase: { en: "exits only", ar: "الخروج فقط" },
  all_mutations: { en: "frozen, exits too", ar: "تجميد كامل، والخروج أيضًا" },
};

const moneyLimitNames: Readonly<Record<MoneyLimitName, Text>> = {
  max_daily_loss: { en: "Daily loss", ar: "الخسارة اليومية" },
  max_trade_risk: { en: "Risk per trade", ar: "المخاطرة لكل صفقة" },
  max_trade_risk_equity_percent: {
    en: "Risk per trade, % of equity",
    ar: "المخاطرة لكل صفقة، ٪ من السيولة",
  },
  max_open_risk: { en: "Total open risk", ar: "إجمالي المخاطرة المفتوحة" },
  max_open_risk_equity_percent: {
    en: "Total open risk, % of equity",
    ar: "إجمالي المخاطرة المفتوحة، ٪ من السيولة",
  },
  min_free_margin: { en: "Free-margin floor", ar: "الحد الأدنى للهامش الحر" },
};

export function moneyLimitLabel(name: MoneyLimitName, locale: string): string {
  return moneyLimitNames[name][language(locale)];
}

export function pauseClassLabel(value: RestrictionActionClass, locale: string): string {
  return pauseClass[value][language(locale)];
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

/** "Daily loss 300 USD · Risk per trade 1%" or "No money limit set". */
export function moneyLimitsLine(value: MoneyLimits, locale: string): string {
  const lang = language(locale);
  const entries = Object.entries(value.limits) as Array<[MoneyLimitName, string]>;
  if (!value.configured || !entries.length) return tradingSafetyLabels[lang].noMoneyLimit;
  return entries
    .map(([name, amount]) => {
      const unit = name.endsWith("_percent") ? "%" : value.currency ? ` ${value.currency}` : "";
      return `${moneyLimitNames[name][lang]} ${isolate(amount + unit)}`;
    })
    .join(" · ");
}

/**
 * The one line: the agent's ladder level, or the strongest thing stopping it, in the
 * owner's language. Built only from the server's projection. ``accountName`` names the
 * paused account when the owner has several (null keeps the line without it).
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
    case "stopped":
      // A freeze also blocks exits: the line never claims what the sheet denies.
      if (!readiness.exits_allowed)
        return ar
          ? "التداول الجديد متوقف · والخروج مجمّد أيضًا"
          : "New trading stopped · exits frozen too";
      return ar ? "التداول الجديد متوقف · الخروج متاح" : "New trading stopped · exits allowed";
    case "paused": {
      const kind = pauseClassLabel(params.action_class ?? "no_new_entries", locale);
      const account = params.account_id ? accountName(params.account_id) : null;
      const where =
        (params.symbol ? ` ${ar ? "على" : "on"} ${isolate(params.symbol)}` : "") +
        (account ? ` (${isolate(account)})` : "");
      const end = until(params.valid_until, { en: "until you lift it", ar: "حتى ترفعه" });
      return ar ? `إيقاف${where}: ${kind} · ${end}` : `Paused${where}: ${kind} · ${end}`;
    }
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
      const markets =
        params.symbol_scope === "account"
          ? tradingSafetyLabels[lang].allPairs
          : (params.symbols ?? []).map(isolate).join(ar ? "، " : ", ");
      const end = until(params.valid_until, { en: "until you stop it", ar: "حتى توقفه" });
      const money =
        params.money_limit_set === false ? ` · ${tradingSafetyLabels[lang].noMoneyLimit}` : "";
      return `${ar ? "يتداول باستقلال" : "Trades on its own"}${markets ? ` · ${markets}` : ""} · ${end}${money}`;
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
