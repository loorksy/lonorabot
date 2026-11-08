/**
 * An agent's one status line and its watch list, shared by Web and Mobile.
 *
 * Everything here renders the server's live state (lonora_db.agent_state): the phase
 * and reason it derived from durable records, and its active watches. Nothing is
 * simulated. Arabic is first-class: tickers, numbers and times are isolated so they keep
 * their order inside Arabic text.
 */
import type { AgentLiveState, AgentWatchSummary } from "@lonora/contracts";
import type { AvatarStateId } from "./trading-avatar-motion";
import { isolate, readinessTime } from "./trading-readiness";

type Language = "ar" | "en";

function language(locale: string): Language {
  return locale.startsWith("ar") ? "ar" : "en";
}

export const agentStatusLabels = {
  en: {
    idle: "Idle",
    working: "Working",
    waiting: "Waiting",
    action_required: "Waiting for you",
    degraded: "Service needs attention",
    paused: "Paused",
    monitoring: "Monitoring",
    until: "until",
    more: "more",
    watches: "Watching",
    cancel: "Cancel",
    noExpiry: "until cancelled",
    above: "above",
    below: "below",
    cross_above: "crosses above",
    cross_below: "crosses below",
    changed: "changes",
    closed: "closes",
    opened: "opens",
    due: "event due",
    position: "Position",
    account: "Account",
    calendar: "Economic calendar",
    pattern: "pattern",
    balance: "balance",
    equity: "equity",
    margin: "margin",
    free_margin: "free margin",
    profit: "profit",
    volume: "volume",
  },
  ar: {
    idle: "خامل",
    working: "يعمل",
    waiting: "ينتظر",
    action_required: "بانتظارك",
    degraded: "الخدمة تحتاج إلى انتباه",
    paused: "متوقف",
    monitoring: "يراقب",
    until: "حتى",
    more: "أخرى",
    watches: "يراقب",
    cancel: "إلغاء",
    noExpiry: "حتى الإلغاء",
    above: "فوق",
    below: "تحت",
    cross_above: "يتجاوز صعودًا",
    cross_below: "يكسر هبوطًا",
    changed: "يتغير",
    closed: "يُغلق",
    opened: "يُفتح",
    due: "حدث مستحق",
    position: "المركز",
    account: "الحساب",
    calendar: "المفكرة الاقتصادية",
    pattern: "نمط",
    balance: "الرصيد",
    equity: "حقوق الملكية",
    margin: "الهامش",
    free_margin: "الهامش الحر",
    profit: "الربح",
    volume: "الحجم",
  },
} as const satisfies Record<Language, Record<string, string>>;
export type AgentStatusText = (typeof agentStatusLabels)[Language];

export function agentStatusText(locale: string): AgentStatusText {
  return agentStatusLabels[language(locale)];
}

const METRICS = ["balance", "equity", "margin", "free_margin", "profit", "volume"] as const;

function metricLabel(metric: string | null, text: AgentStatusText): string | null {
  const known = METRICS.find((name) => name === metric);
  return known ? text[known] : null;
}

/** What one watch waits for, e.g. "XAUUSD above 2100" or "RSI 1h XAUUSD crosses above 70". */
export function watchCondition(watch: AgentWatchSummary, locale: string): string {
  const text = agentStatusText(locale);
  const condition = watch.condition ? text[watch.condition] : "";
  const level = watch.level != null && watch.level !== "0" ? isolate(watch.level) : "";
  const symbol = watch.symbol ? isolate(watch.symbol) : "";
  switch (watch.kind) {
    case "calendar":
      return `${text.calendar} · ${text.due}`;
    case "account":
      return [text.account, metricLabel(watch.metric, text), condition, level]
        .filter(Boolean)
        .join(" ");
    case "position":
      return [text.position, symbol, metricLabel(watch.metric, text), condition, level]
        .filter(Boolean)
        .join(" ");
    case "indicator":
      return [
        watch.indicator ? isolate(watch.indicator.toUpperCase()) : "",
        watch.timeframe ? isolate(watch.timeframe) : "",
        symbol,
        condition,
        level,
      ]
        .filter(Boolean)
        .join(" ");
    case "dynamic":
      return [symbol, text.pattern].filter(Boolean).join(" ");
    default:
      return [symbol, condition, level].filter(Boolean).join(" ");
  }
}

/** "until 17:00", with the date when it is not today; "until cancelled" without expiry. */
export function watchUntil(
  watch: AgentWatchSummary,
  locale: string,
  now: Date = new Date(),
): string {
  const text = agentStatusText(locale);
  return watch.expires_at
    ? `${text.until} ${readinessTime(watch.expires_at, locale, now)}`
    : text.noExpiry;
}

/**
 * The agent's one status line: "Monitoring XAUUSD until 17:00 · 2 more" while it waits on
 * its watches, otherwise the plain state ("Working", "Waiting for you", "Paused").
 */
export function agentStatusLine(
  state: AgentLiveState,
  locale: string,
  now: Date = new Date(),
): string {
  const text = agentStatusText(locale);
  const watches = state.watches ?? [];
  if (state.phase !== "monitoring" || !watches.length) return text[state.state];
  const first = watches[0];
  if (!first) return text.monitoring;
  const subject = first.symbol ? isolate(first.symbol) : watchCondition(first, locale);
  const until = first.expires_at ? ` ${watchUntil(first, locale, now)}` : "";
  const rest = state.watch_count - 1;
  return `${text.monitoring} ${subject}${until}${rest > 0 ? ` · ${isolate(String(rest))} ${text.more}` : ""}`;
}

/**
 * The avatar between runs follows the server's phase: watching while it monitors,
 * asleep while paused, a warning when it needs the owner or a service, otherwise idle.
 */
export function liveAvatarState(state: AgentLiveState | null | undefined): AvatarStateId {
  if (!state) return "waiting";
  if (state.state === "paused") return "sleeping";
  if (state.state === "degraded" || state.state === "action_required") return "warning";
  if (state.state === "working") return "working";
  if (state.phase === "monitoring") return "inspecting";
  return "waiting";
}
