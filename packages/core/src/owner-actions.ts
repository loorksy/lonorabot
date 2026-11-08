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
  OwnerAction,
  OwnerActionAccount,
  OwnerActionChallenge,
  OwnerActionDecision,
  OwnerActionLimitField,
} from "@lonora/contracts";
import { accountAuthorityLabels } from "./account-authority-labels";
import {
  isolate,
  moneyLimitLabel,
  moneyLimitsLine,
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
      "It will not be sent again. New risk on this market is held until you answer; any answer, Unknown included, releases this trade's hold. Exits still work.",
    resolveRecord: "Your answer is recorded as your statement, not as broker confirmation.",
    executed: "It executed",
    notExecuted: "It did not execute",
    unknown: "Unknown: release the hold",
    note: "Note (optional)",
    brokerReference: "Broker ticket (optional)",
    byYou: "your order",
    by: "by",
    at: "at",
    limitsTitle: "Change money limits",
    limitsOneTap: "This allows no more risk, so it takes one tap.",
    limitsPasskey: "This can allow more risk, so it needs your passkey.",
    currency: "Currency",
    tradingDay: "Trading day starts at midnight in",
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
    recordedUnknown:
      "Recorded: the outcome stays unknown. It will not be resent and no longer holds new risk on this market.",
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
    deviceName: accountAuthorityLabels.en.device,
    password: "Account password",
    grantTitle: "Let {agent} trade on its own",
    grantAgent: "this agent",
    markets: "Markets",
    allPairsAccount: "All pairs on this account",
    allActions: "Opens, closes and manages trades",
    actionsLine: "Actions",
    untilStopped: "Until you stop it",
    for12h: "For 12 hours",
    for24h: "For 24 hours",
    for7d: "For 7 days",
    ownExcluded: "Positions you opened yourself are excluded",
    ownIncluded: "Positions you opened yourself are included",
    includeOwn: "Include positions I opened myself",
    dailyLoss: "Daily loss limit",
    ofEquity: "of equity",
    suggested: "suggested",
    accountLimits: "Account money limits",
    noMoneyLimitChoice: "No money limit (my choice)",
    tradingStopped: "New trading is stopped",
    resumeToo: "Resume trading too",
    conflict:
      "{agent} already trades {markets} here on its own. Keeping both is fine: the account's limits bind them together.",
    stopOther: "Stop {agent} trading here",
    replaces: "Replaces its current grant on this account",
    grantHint:
      "Confirm with your passkey. Anything outside this grant still comes to you as an approval card.",
    oneRule:
      "Every agent can see and use everything you have connected to Lonora, but it places real trades only inside the grant you signed for it with your passkey and within your account limits. Anything that needs you arrives as a one-tap card in the chat, you can stop anything with one tap, and no agent, skill or plugin can ever widen your money authority.",
    authorize: "Authorize with passkey",
    signed: "Signed. It trades on its own inside this grant.",
    alreadySigned: "This is already signed. Nothing changed.",
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
    resolveHint:
      "لن تُرسل مجددًا. المخاطرة الجديدة على هذا السوق معلّقة حتى تجيب، وأي إجابة، ومنها «غير معروفة»، ترفع تعليق هذه الصفقة؛ يبقى الخروج متاحًا.",
    resolveRecord: "تُسجَّل إجابتك كتصريح منك، لا كتأكيد من الوسيط.",
    executed: "نُفذت",
    notExecuted: "لم تُنفذ",
    unknown: "غير معروفة — ارفع التعليق",
    note: "ملاحظة (اختيارية)",
    brokerReference: "رقم التذكرة لدى الوسيط (اختياري)",
    byYou: "أمرك",
    by: "من",
    at: "في",
    limitsTitle: "تغيير الحدود المالية",
    limitsOneTap: "هذا لا يسمح بمخاطرة أكبر، لذا يتم بلمسة واحدة.",
    limitsPasskey: "قد يسمح هذا بمخاطرة أكبر، لذا يحتاج مفتاح المرور.",
    currency: "العملة",
    tradingDay: "يبدأ يوم التداول عند منتصف الليل بتوقيت",
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
    recordedUnknown:
      "سُجّل: تبقى النتيجة غير معروفة. لن يُعاد إرسالها، ولم تعد تعلّق المخاطرة الجديدة على هذا السوق.",
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
    deviceName: accountAuthorityLabels.ar.device,
    password: "كلمة مرور الحساب",
    grantTitle: "دع {agent} يتداول بنفسه",
    grantAgent: "هذا الوكيل",
    markets: "الأسواق",
    allPairsAccount: "كل أزواج هذا الحساب",
    allActions: "يفتح الصفقات ويغلقها ويديرها",
    actionsLine: "العمليات",
    untilStopped: "حتى توقفه",
    for12h: "لمدة ١٢ ساعة",
    for24h: "لمدة ٢٤ ساعة",
    for7d: "لمدة ٧ أيام",
    ownExcluded: "لا يشمل المراكز التي فتحتها بنفسك",
    ownIncluded: "يشمل المراكز التي فتحتها بنفسك",
    includeOwn: "اشمل المراكز التي فتحتها بنفسي",
    dailyLoss: "حد الخسارة اليومية",
    ofEquity: "من السيولة",
    suggested: "مقترح",
    accountLimits: "الحدود المالية للحساب",
    noMoneyLimitChoice: "دون حد مالي (اختياري)",
    tradingStopped: "التداول الجديد متوقف",
    resumeToo: "استأنف التداول أيضًا",
    conflict: "{agent} يتداول {markets} هنا بنفسه. لا بأس ببقائهما معًا: حدود الحساب تلزمهما معًا.",
    stopOther: "أوقف تداول {agent} هنا",
    replaces: "يحل محل تفويضه الحالي على هذا الحساب",
    grantHint: "أكّد بمفتاح المرور. ما يخرج عن هذا التفويض يصلك كبطاقة موافقة.",
    oneRule:
      "كل وكيل يرى ويستخدم كل ما وصلته بلونورا، لكنه لا ينفّذ صفقة حقيقية إلا ضمن التفويض الذي وقّعته له بمفتاح المرور وضمن حدود حسابك؛ وما يحتاجك يصلك كبطاقة في المحادثة بلمسة واحدة، وتستطيع إيقاف أي شيء بلمسة، ولا يستطيع أي وكيل أو مهارة أو إضافة توسيع صلاحياتك المالية.",
    authorize: "التفويض بمفتاح المرور",
    signed: "وُقّع. يتداول بنفسه ضمن هذا التفويض.",
    alreadySigned: "هذا موقّع بالفعل. لم يتغير شيء.",
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
/** An owner switch on a card (a grant card's own positions, money limit, Resume, a
 * conflict); the client keeps its state and ``ownerActionChoices`` sends it. */
export type OwnerActionOption = { key: string; label: string; initial: boolean };
export type OwnerActionSpec = {
  title: string;
  /** Server facts, one per line, ready to render with dir="auto". */
  lines: string[];
  hint: string | null;
  /** Switches shown while pending; empty for every card but a grant card. */
  options: OwnerActionOption[];
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
      case "grant_authority":
        return text.signed;
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
    case "grant_already_active":
      return text.alreadySigned;
    case "expired":
      return text.expired;
    default:
      return card.status === "expired" ? text.expired : text.noLongerApplies;
  }
}

function limitValue(name: OwnerActionLimitField, value: string | null, currency: string | null) {
  if (value == null) return null;
  if (name === "currency" || name === "trading_day_timezone") return isolate(value);
  return isolate(
    name.endsWith("_percent") ? `${value}%` : currency ? `${value} ${currency}` : value,
  );
}

function limitFieldLabel(name: OwnerActionLimitField, locale: string, text: OwnerActionText) {
  if (name === "currency") return text.currency;
  if (name === "trading_day_timezone") return text.tradingDay;
  return moneyLimitLabel(name, locale);
}

function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => values[key] ?? "");
}

function marketsLabel(
  scope: "selected" | "account",
  symbols: string[],
  text: OwnerActionText,
): string {
  return scope === "account" ? text.allPairsAccount : symbols.map(isolate).join("، ");
}

function grantCard(card: OwnerAction, locale: string, lang: Language) {
  const text = ownerActionLabels[lang];
  const facts = card.facts;
  const grant = facts.grant;
  const agent = grant?.agent_name ? isolate(grant.agent_name) : text.grantAgent;
  const lines: string[] = [];
  const options: OwnerActionOption[] = [];
  const hints: string[] = [];
  if (grant) {
    const account = accountLabel(facts.account, text);
    if (account) lines.push(`${text.account}: ${account}`);
    lines.push(`${text.markets}: ${marketsLabel(grant.symbol_scope, grant.symbols, text)}`);
    lines.push(
      grant.all_actions
        ? text.allActions
        : `${text.actionsLine}: ${grant.actions.map((item) => actionLabel(item, lang)).join("، ")}`,
    );
    lines.push(
      grant.duration === "12h"
        ? text.for12h
        : grant.duration === "24h"
          ? text.for24h
          : grant.duration === "7d"
            ? text.for7d
            : text.untilStopped,
    );
    lines.push(grant.allow_manual_positions ? text.ownIncluded : text.ownExcluded);
    options.push({ key: "manual", label: text.includeOwn, initial: grant.allow_manual_positions });
  }
  const daily = facts.money?.daily_loss;
  if (daily?.proposed) {
    const amount = isolate(daily.currency ? `${daily.proposed} ${daily.currency}` : daily.proposed);
    const basis = daily.percent
      ? ` (${daily.basis === "suggested" ? `${text.suggested}: ` : ""}${isolate(`${daily.percent}%`)} ${text.ofEquity})`
      : "";
    lines.push(`${text.dailyLoss}: ${amount}${basis}`);
    options.push({ key: "no_money_limit", label: text.noMoneyLimitChoice, initial: false });
    const others = facts.money?.limits;
    if (others?.configured) lines.push(`${text.accountLimits}: ${moneyLimitsLine(others, locale)}`);
  } else if (facts.money) {
    lines.push(`${text.accountLimits}: ${moneyLimitsLine(facts.money.limits, locale)}`);
  }
  if (facts.global_trading?.state === "stopped") {
    lines.push(text.tradingStopped);
    // Checked when the owner never started trading; after the owner's own Stop it waits.
    options.push({
      key: "resume",
      label: text.resumeToo,
      initial: facts.global_trading.changed_by === "default",
    });
  }
  for (const conflict of facts.conflicts ?? []) {
    const name = conflict.agent_name ? isolate(conflict.agent_name) : text.anAgent;
    lines.push(
      fill(text.conflict, {
        agent: name,
        markets: marketsLabel(conflict.symbol_scope, conflict.symbols, text),
      }),
    );
    options.push({
      key: `stop:${conflict.authority_id}`,
      label: fill(text.stopOther, { agent: name }),
      initial: false,
    });
  }
  if (facts.replaces) lines.push(text.replaces);
  hints.push(text.grantHint);
  if (facts.first_grant) hints.push(text.oneRule);
  return {
    title: fill(text.grantTitle, { agent }),
    lines,
    options,
    hint: hints.join(" "),
    buttons: [
      { key: "confirm", label: text.authorize, decision: "confirm", primary: true },
      { key: "cancel", label: text.notNow, decision: "cancel", primary: false },
    ] satisfies OwnerActionButton[],
  };
}

/** What a grant card's switches send: the passkey challenge carries the owner's own
 * positions choice (it is signed); the decision carries the rest. */
export function ownerActionChoices(
  card: OwnerAction,
  chosen: Readonly<Record<string, boolean>>,
): { challenge: OwnerActionChallenge; decision: Partial<OwnerActionDecision> } {
  if (card.kind !== "grant_authority") return { challenge: {}, decision: {} };
  const value = (key: string, initial: boolean) => chosen[key] ?? initial;
  const options = grantCard(card, "en", "en").options;
  const initial = (key: string) => options.find((item) => item.key === key)?.initial ?? false;
  const decision: Partial<OwnerActionDecision> = {
    money_limit: value("no_money_limit", false) ? "none" : "apply",
    resume_trading: options.some((item) => item.key === "resume")
      ? value("resume", initial("resume"))
      : false,
    stop_authorities: options
      .filter((item) => item.key.startsWith("stop:") && value(item.key, false))
      .map((item) => item.key.slice("stop:".length)),
  };
  return {
    challenge: { allow_manual_positions: value("manual", initial("manual")) },
    decision,
  };
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
  let options: OwnerActionOption[] = [];
  const pair = (confirm: string, cancel: string): OwnerActionButton[] => [
    { key: "confirm", label: confirm, decision: "confirm", primary: true },
    { key: "cancel", label: cancel, decision: "cancel", primary: false },
  ];
  switch (card.kind) {
    case "grant_authority": {
      const grant = grantCard(card, locale, lang);
      title = grant.title;
      lines.push(...grant.lines);
      hint = grant.hint;
      buttons = grant.buttons;
      options = grant.options;
      break;
    }
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
      // Every field the card would change has a line, its currency and day included.
      for (const change of facts.changes ?? []) {
        const from =
          limitValue(change.name, change.from, facts.current?.currency ?? null) ?? text.notSet;
        const to = limitValue(change.name, change.to, currency) ?? text.removed;
        // The arrow points along the reading direction: right to left in Arabic.
        lines.push(
          `${limitFieldLabel(change.name, locale, text)}: ${from} ${lang === "ar" ? "←" : "→"} ${to}`,
        );
      }
      if (account) lines.push(`${text.account}: ${account}`);
      if (facts.no_longer_applies) {
        // The limits moved on since the card was raised: it can only be dismissed.
        hint = text.noLongerApplies;
        buttons = [{ key: "cancel", label: text.cancel, decision: "cancel", primary: false }];
        break;
      }
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
    options: pending ? options : [],
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
  owner_action_challenge_required: {
    en: "Confirm with your passkey on this card.",
    ar: "أكّد بمفتاح المرور من هذه البطاقة.",
  },
  owner_action_conflict_not_found: {
    en: "That agent no longer trades here on its own. Nothing changed.",
    ar: "لم يعد ذلك الوكيل يتداول هنا بنفسه. لم يتغير شيء.",
  },
  owner_action_not_needed_grant_already_active: {
    en: "This is already signed.",
    ar: "هذا موقّع بالفعل.",
  },
  execution_policy_passkey_required: {
    en: "Raising or removing a money limit needs your passkey.",
    ar: "رفع حد مالي أو إزالته يحتاج مفتاح المرور.",
  },
  execution_policy_passkey_not_needed: {
    en: "This change allows no more risk, so it needs no passkey.",
    ar: "هذا التغيير لا يسمح بمخاطرة أكبر، فلا يحتاج مفتاح المرور.",
  },
};

/** Owner text for a card decision's refusal, shared by Web and Mobile; null if not one. */
export function ownerActionError(code: string | null | undefined, locale: string): string | null {
  const entry = code ? errors[code] : undefined;
  return entry ? entry[language(locale)] : null;
}
