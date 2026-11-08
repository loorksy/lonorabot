/**
 * Owner action cards: one shared spec for Web and Mobile.
 *
 * A card renders only the server's facts (lonora_db.owner_actions), in the owner's
 * language; no agent text ever reaches it. Arabic is first-class: tickers, numbers and
 * times are isolated so they keep their order inside Arabic text. Nothing here decides
 * anything: the owner's tap goes to the owner-session decision route, which re-validates.
 */
import type {
  AttestedOutcome,
  MoneyLimitName,
  OwnerAction,
  OwnerActionAccount,
} from "@lonora/contracts";
import { accountAuthorityLabels } from "./account-authority-labels";
import {
  isolate,
  moneyLimitLabel,
  pauseClassLabel,
  readinessTime,
  tradingSafetyLabels,
} from "./trading-readiness";

type Language = "ar" | "en";

function language(locale: string): Language {
  return locale.startsWith("ar") ? "ar" : "en";
}

export const ownerActionLabels = {
  en: {
    resumeTitle: "Resume trading",
    resumeStopped: "New trading is stopped",
    resumeHint:
      "Resuming widens no authority: each agent still trades only within its level, grants and your limits.",
    resume: "Resume trading",
    notNow: "Not now",
    pausedEntries: "New entries paused",
    pausedRisk: "Only exits allowed",
    pausedFrozen: "Trading frozen",
    exitsAllowed: "Closing positions and tightening stops stay allowed.",
    exitsFrozen: "Exits are frozen too.",
    lift: "Lift pause",
    keep: "Keep it",
    allPairs: "all pairs",
    allAgents: "all agents",
    yourOrdersToo: "your manual orders too",
    untilLifted: "until you lift it",
    until: "until",
    starts: "starts",
    setByYou: "set by you",
    fromYourMessage: "from your message",
    setByAgent: "set by",
    anAgent: "an agent",
    resolveTitle: "The broker did not confirm this trade",
    resolveHint:
      "It will not be sent again. New risk on this market is held until you answer; exits still work.",
    resolveRecord: "Your answer is recorded as your statement, not as broker confirmation.",
    executed: "It executed",
    notExecuted: "It did not execute",
    unknown: "Still unknown",
    note: "Note (optional)",
    brokerReference: "Broker ticket (optional)",
    byYou: "your order",
    by: "by",
    at: "at",
    limitsTitle: "Change money limits",
    limitsOneTap: "Lowering or adding a limit takes one tap.",
    limitsPasskey: "This raises or removes a limit, so it needs your passkey.",
    notSet: "not set",
    removed: "removed",
    apply: "Apply",
    applyPasskey: "Confirm with passkey",
    cancel: "Cancel",
    account: "Account",
    simulation: "Simulation",
    brokerAccount: "Broker account",
    resumed: "Trading resumed.",
    lifted: "Pause lifted.",
    recordedExecuted: "Recorded: it executed (your statement, not broker confirmation).",
    recordedNotExecuted: "Recorded: it did not execute (your statement, not broker confirmation).",
    recordedUnknown: "Recorded: the outcome stays unknown. It will not be resent.",
    limitsSaved: "Money limits updated.",
    cancelled: "Dismissed. Nothing changed.",
    expired: "This card expired. Nothing changed.",
    alreadyEnded: "This pause already ended. Nothing changed.",
    alreadySettled: "This operation is already settled. Nothing changed.",
    alreadyRunning: "Trading is already running.",
    alreadySet: "These limits are already set.",
    doneElsewhere: "Done from another card.",
    noLongerApplies: "This no longer applies. Nothing changed.",
    passkeyUnsupported:
      "Passkey signing is unavailable here. Open Lonora in a supported browser or the app.",
    registerDevice: "Register this device first",
    password: "Account password",
  },
  ar: {
    resumeTitle: "استئناف التداول",
    resumeStopped: "التداول الجديد متوقف",
    resumeHint: "الاستئناف لا يوسّع أي صلاحية: يبقى كل وكيل ضمن مستواه وتفويضه وحدودك.",
    resume: "استئناف التداول",
    notNow: "ليس الآن",
    pausedEntries: "الصفقات الجديدة متوقفة",
    pausedRisk: "الخروج فقط مسموح",
    pausedFrozen: "التداول مجمّد",
    exitsAllowed: "يبقى إغلاق المراكز وتقريب وقف الخسارة متاحًا.",
    exitsFrozen: "الخروج مجمّد أيضًا.",
    lift: "رفع الإيقاف",
    keep: "إبقاؤه",
    allPairs: "كل الأزواج",
    allAgents: "كل الوكلاء",
    yourOrdersToo: "وأوامرك اليدوية أيضًا",
    untilLifted: "حتى ترفعه",
    until: "حتى",
    starts: "يبدأ",
    setByYou: "وضعته أنت",
    fromYourMessage: "من رسالتك",
    setByAgent: "وضعه",
    anAgent: "وكيل",
    resolveTitle: "الوسيط لم يؤكد هذه الصفقة",
    resolveHint: "لن تُرسل مجددًا. المخاطرة الجديدة على هذا السوق معلّقة حتى تجيب؛ يبقى الخروج متاحًا.",
    resolveRecord: "تُسجَّل إجابتك كتصريح منك، لا كتأكيد من الوسيط.",
    executed: "نُفذت",
    notExecuted: "لم تُنفذ",
    unknown: "لا أعرف بعد",
    note: "ملاحظة (اختيارية)",
    brokerReference: "رقم التذكرة لدى الوسيط (اختياري)",
    byYou: "أمرك",
    by: "من",
    at: "في",
    limitsTitle: "تغيير الحدود المالية",
    limitsOneTap: "خفض حد أو إضافته يتم بلمسة واحدة.",
    limitsPasskey: "هذا يرفع حدًا أو يزيله، لذا يحتاج مفتاح المرور.",
    notSet: "غير محدد",
    removed: "يُزال",
    apply: "تطبيق",
    applyPasskey: "تأكيد بمفتاح المرور",
    cancel: "إلغاء",
    account: "الحساب",
    simulation: "محاكاة",
    brokerAccount: "حساب الوسيط",
    resumed: "استؤنف التداول.",
    lifted: "رُفع الإيقاف.",
    recordedExecuted: "سُجّل: نُفذت (تصريحك، لا تأكيد من الوسيط).",
    recordedNotExecuted: "سُجّل: لم تُنفذ (تصريحك، لا تأكيد من الوسيط).",
    recordedUnknown: "سُجّل: تبقى النتيجة غير معروفة. لن تُعاد إرسالها.",
    limitsSaved: "حُدّثت الحدود المالية.",
    cancelled: "تم التجاهل. لم يتغير شيء.",
    expired: "انتهت صلاحية هذه البطاقة. لم يتغير شيء.",
    alreadyEnded: "انتهى هذا الإيقاف مسبقًا. لم يتغير شيء.",
    alreadySettled: "حُسمت هذه العملية مسبقًا. لم يتغير شيء.",
    alreadyRunning: "التداول يعمل بالفعل.",
    alreadySet: "هذه الحدود مضبوطة بالفعل.",
    doneElsewhere: "نُفذ من بطاقة أخرى.",
    noLongerApplies: "لم يعد هذا ساريًا. لم يتغير شيء.",
    passkeyUnsupported: "توقيع مفتاح المرور غير متاح هنا. افتح لونورا بمتصفح مدعوم أو التطبيق.",
    registerDevice: "سجّل هذا الجهاز أولًا",
    password: "كلمة مرور الحساب",
  },
} as const satisfies Record<Language, Record<string, string>>;
export type OwnerActionText = (typeof ownerActionLabels)[Language];

export function ownerActionText(locale: string): OwnerActionText {
  return ownerActionLabels[language(locale)];
}

/** What a button sends: confirm (with an outcome for a resolve card) or cancel. */
export type OwnerActionButton = {
  key: "confirm" | "cancel" | AttestedOutcome;
  label: string;
  decision: "confirm" | "cancel";
  outcome?: AttestedOutcome;
  primary: boolean;
};
export type OwnerActionSpec = {
  title: string;
  /** Server facts, one per line, ready to render with dir="auto". */
  lines: string[];
  hint: string | null;
  /** Shown while pending; empty once the card is settled. */
  buttons: OwnerActionButton[];
  /** A resolve card offers an optional note and broker ticket. */
  notes: boolean;
  passkey: boolean;
  /** The settled line ("Trading resumed.", "This card expired. Nothing changed."). */
  outcome: string | null;
};

function accountLabel(
  account: OwnerActionAccount | undefined,
  text: OwnerActionText,
): string | null {
  if (!account) return null;
  if (account.label) return isolate(account.label);
  return account.provider === "simulation" ? text.simulation : text.brokerAccount;
}

function actionLabel(action: string | null, lang: Language): string {
  const labels = accountAuthorityLabels[lang] as Record<string, string>;
  return action ? (labels[action] ?? isolate(action)) : "";
}

function settledLine(card: OwnerAction, text: OwnerActionText): string | null {
  if (card.status === "pending") return null;
  if (card.status === "cancelled") return text.cancelled;
  if (card.status === "confirmed") {
    switch (card.kind) {
      case "resume_trading":
        return text.resumed;
      case "lift_restriction":
        return text.lifted;
      case "set_account_limits":
        return text.limitsSaved;
      case "resolve_operation":
        return card.result.outcome === "executed"
          ? text.recordedExecuted
          : card.result.outcome === "not_executed"
            ? text.recordedNotExecuted
            : text.recordedUnknown;
    }
  }
  switch (card.status_reason) {
    case "restriction_already_ended":
      return text.alreadyEnded;
    case "operation_already_settled":
      return text.alreadySettled;
    case "trading_already_running":
      return text.alreadyRunning;
    case "limits_already_set":
      return text.alreadySet;
    case "done_by_another_card":
      return text.doneElsewhere;
    case "expired":
      return text.expired;
    default:
      return card.status === "expired" ? text.expired : text.noLongerApplies;
  }
}

function limitValue(name: MoneyLimitName, value: string | null, currency: string | null) {
  if (value == null) return null;
  return isolate(
    name.endsWith("_percent") ? `${value}%` : currency ? `${value} ${currency}` : value,
  );
}

/** The whole card for one locale: title, fact lines, hint, buttons and settled line. */
export function ownerActionCard(
  card: OwnerAction,
  locale: string,
  now: Date = new Date(),
): OwnerActionSpec {
  const lang = language(locale);
  const text = ownerActionLabels[lang];
  const facts = card.facts;
  const account = facts.several_accounts ? accountLabel(facts.account, text) : null;
  const lines: string[] = [];
  let title: string = text.resumeTitle;
  let hint: string | null = null;
  let buttons: OwnerActionButton[] = [];
  const pair = (confirm: string, cancel: string): OwnerActionButton[] => [
    { key: "confirm", label: confirm, decision: "confirm", primary: true },
    { key: "cancel", label: cancel, decision: "cancel", primary: false },
  ];
  switch (card.kind) {
    case "resume_trading": {
      const trading = facts.global_trading;
      if (trading?.state === "stopped")
        lines.push(
          trading.since
            ? `${text.resumeStopped} · ${tradingSafetyLabels[lang].since} ${readinessTime(trading.since, locale, now)}`
            : text.resumeStopped,
        );
      hint = text.resumeHint;
      buttons = pair(text.resume, text.notNow);
      break;
    }
    case "lift_restriction": {
      const pause = facts.restriction;
      title =
        pause?.action_class === "all_mutations"
          ? text.pausedFrozen
          : pause?.action_class === "no_risk_increase"
            ? text.pausedRisk
            : text.pausedEntries;
      if (pause) {
        const who = pause.all_agents
          ? text.allAgents
          : pause.agent_name
            ? isolate(pause.agent_name)
            : text.anAgent;
        const scope = [
          pause.symbol ? isolate(pause.symbol) : text.allPairs,
          who,
          ...(pause.includes_owner_manual ? [text.yourOrdersToo] : []),
          ...(account ? [account] : []),
        ];
        lines.push(`${pauseClassLabel(pause.action_class, locale)} · ${scope.join(" · ")}`);
        const when =
          pause.state === "scheduled"
            ? `${text.starts} ${readinessTime(pause.valid_from, locale, now)}`
            : pause.valid_until
              ? `${text.until} ${readinessTime(pause.valid_until, locale, now)}`
              : text.untilLifted;
        const source =
          pause.source === "owner_ui"
            ? text.setByYou
            : pause.source === "owner_message"
              ? text.fromYourMessage
              : `${text.setByAgent} ${pause.set_by_agent_name ? isolate(pause.set_by_agent_name) : text.anAgent}`;
        lines.push(`${when} · ${source}`);
        hint = pause.action_class === "all_mutations" ? text.exitsFrozen : text.exitsAllowed;
      }
      buttons = pair(text.lift, text.keep);
      break;
    }
    case "resolve_operation": {
      title = text.resolveTitle;
      const operation = facts.operation;
      if (operation) {
        const what = [
          actionLabel(operation.action, lang),
          ...(operation.volume ? [isolate(operation.volume)] : []),
          ...(operation.symbol ? [isolate(operation.symbol)] : []),
        ].join(" ");
        const when = operation.submitted_at
          ? ` · ${text.at} ${readinessTime(operation.submitted_at, locale, now)}`
          : "";
        const who = operation.by_owner
          ? text.byYou
          : `${text.by} ${operation.by_agent_name ? isolate(operation.by_agent_name) : text.anAgent}`;
        lines.push(`${what}${when} · ${who}`);
        if (account) lines.push(`${text.account}: ${account}`);
      }
      hint = `${text.resolveHint} ${text.resolveRecord}`;
      buttons = [
        {
          key: "executed",
          label: text.executed,
          decision: "confirm",
          outcome: "executed",
          primary: false,
        },
        {
          key: "not_executed",
          label: text.notExecuted,
          decision: "confirm",
          outcome: "not_executed",
          primary: false,
        },
        {
          key: "unknown",
          label: text.unknown,
          decision: "confirm",
          outcome: "unknown",
          primary: false,
        },
      ];
      break;
    }
    case "set_account_limits": {
      title = text.limitsTitle;
      const currency = facts.proposed?.currency ?? facts.current?.currency ?? null;
      for (const change of facts.changes ?? []) {
        const from =
          limitValue(change.name, change.from, facts.current?.currency ?? null) ?? text.notSet;
        const to = limitValue(change.name, change.to, currency) ?? text.removed;
        // The arrow points along the reading direction: right to left in Arabic.
        lines.push(
          `${moneyLimitLabel(change.name, locale)}: ${from} ${lang === "ar" ? "←" : "→"} ${to}`,
        );
      }
      if (account) lines.push(`${text.account}: ${account}`);
      hint = card.requires_passkey ? text.limitsPasskey : text.limitsOneTap;
      buttons = pair(card.requires_passkey ? text.applyPasskey : text.apply, text.cancel);
      break;
    }
  }
  const pending = card.status === "pending";
  return {
    title,
    lines,
    hint: pending ? hint : null,
    buttons: pending ? buttons : [],
    notes: pending && card.kind === "resolve_operation",
    passkey: pending && card.requires_passkey,
    outcome: settledLine(card, text),
  };
}

/** A newer status never goes back to pending when an older read arrives late. */
export function mergeOwnerAction(previous: OwnerAction, next: OwnerAction): OwnerAction {
  if (previous.status !== "pending" && next.status === "pending") return previous;
  return next;
}

const errors: Readonly<Record<string, { en: string; ar: string }>> = {
  owner_action_passkey_required: {
    en: "This change needs your passkey.",
    ar: "هذا التغيير يحتاج مفتاح المرور.",
  },
  owner_action_passkey_not_needed: {
    en: "This card does not need a passkey.",
    ar: "هذه البطاقة لا تحتاج مفتاح المرور.",
  },
  owner_action_already_decided: {
    en: "This card was already answered.",
    ar: "سبقت الإجابة على هذه البطاقة.",
  },
  owner_action_expired_or_decided: {
    en: "This card is no longer waiting for you.",
    ar: "لم تعد هذه البطاقة بانتظارك.",
  },
  owner_action_outcome_required: {
    en: "Choose whether it executed.",
    ar: "اختر هل نُفذت.",
  },
  owner_action_not_found: {
    en: "This card no longer exists.",
    ar: "لم تعد هذه البطاقة موجودة.",
  },
  owner_action_limits_invalid: {
    en: "These limits are not valid for this account.",
    ar: "هذه الحدود غير صالحة لهذا الحساب.",
  },
};

/** Owner text for a card decision's refusal, shared by Web and Mobile; null if not one. */
export function ownerActionError(code: string | null | undefined, locale: string): string | null {
  const entry = code ? errors[code] : undefined;
  return entry ? entry[language(locale)] : null;
}
