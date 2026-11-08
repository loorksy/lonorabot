/**
 * Owner action cards: one shared spec for Web and Mobile.
 *
 * A card renders only the server's facts (lonora_db.owner_actions), in the owner's
 * language; no agent text reaches it except a creation card's stored task, isolated and
 * labelled as the agent's task. Arabic is first-class: tickers, numbers and
 * times are isolated so they keep their order inside Arabic text. Nothing here decides
 * anything: the owner's tap goes to the owner-session decision route, which re-validates.
 */
import type {
  AttestedOutcome,
  CredentialTarget,
  EffectTier,
  OwnerAction,
  OwnerActionAccount,
  OwnerActionAgent,
  OwnerActionLimitField,
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
    createTitle: "Create an agent?",
    createHint: "It starts with no money authority. Nothing is created until you tap.",
    create: "Create agent",
    createdTitle: "Agent created",
    undo: "Undo",
    undoDeleteHint: "Undo removes it: it has not started any work yet.",
    undoPauseHint: "Undo pauses it: it already started work, which is kept.",
    askHint: "No money authority: every trade waits for your tap.",
    grantHint: "It trades on its own only inside the grant you signed.",
    noTradeHint: "It does not trade.",
    task: "Its task",
    templateTrading: "Trading agent",
    templateGeneral: "General agent",
    templateResearch: "Research agent",
    templateSupervisor: "Supervisor",
    agent: "Agent",
    focusPair: "Focus pair",
    on: "on",
    reportsTo: "Reports to",
    model: "Model",
    paused: "Paused",
    createdLine: "Agent created.",
    undoneDeleted: "Undone: the agent was removed.",
    undonePaused: "Undone: the agent was paused; its work is kept.",
    kept: "Kept.",
    agentRemoved: "This agent was already removed.",
    alreadyCreated: "This agent was already created. Nothing changed.",
    agentLimit: "You already have the most active agents allowed. Nothing changed.",
    reportToMissing: "An agent it reports to no longer exists. Nothing changed.",
    connectionChanged: "The broker account changed. Nothing changed.",
    supervises: "Supervises",
    superviseTitle: "Let it supervise?",
    supervisionTitle: "Supervision set",
    supervisor: "Supervisor",
    allow: "Allow",
    supervisionHint:
      "It reads their work and memory, messages them and can pause or resume their work. It never trades for them, never uses their grant and never lifts your brakes.",
    supervisionUndoHint: "Undo stops it at once.",
    supervisionSet: "Supervision set.",
    supervisionUndone: "Undone: supervision stopped.",
    supervisionKept: "Kept.",
    supervisionEnded: "This supervision already ended.",
    supervisionAlreadySet: "This supervision is already set. Nothing changed.",
    supervisionAgentMissing: "One of these agents no longer exists. Nothing changed.",
    stoppedTitle: "Supervision stopped",
    restore: "Restore",
    stoppedHint: "It no longer reads, messages or pauses their work. Restore sets it again.",
    restored: "Restored: supervision set again.",
    pauseTitle: "Paused by a supervisor",
    pausedBy: "Paused by",
    pausedWhat: "What",
    targetAgent: "The whole agent",
    targetRoutine: "Routine",
    targetWatch: "Watch",
    targetTask: "Task",
    pauseHint: "The agent cannot resume it on its own. Resume lifts the pause now.",
    pauseOwnerHolds: "You paused it too, so only you resume it.",
    pauseEnded: "This pause already ended.",
    resumeWork: "Resume",
    keepPaused: "Keep paused",
    resumedWork: "Resumed.",
    keptPaused: "Kept paused.",
    watchExpired: "This watch is past its expiry: move its expiry in the watch list to resume it.",
    trustTitle: "Trust this source?",
    trustReviewTitle: "This server's tools changed",
    trustServer: "MCP server",
    trustRepo: "GitHub repository",
    trustPublisher: "GitHub publisher",
    trustFeed: "News feed site",
    trustTools: "Tools",
    trustBlocked: "Blocked, can trade or move money",
    trustWrites: "May change something (only with non-financial writes)",
    trustSubscribe: "It also subscribes the feed for every agent.",
    trustHint:
      "Agents use it without asking again; you can remove it in Capabilities. It never carries money authority.",
    trustServerHint:
      "Read only runs just the tools that only read; non-financial writes runs them all. Tools that can trade or move money never run, and a changed tool waits for your review.",
    trustServerReadHint:
      "Its tools only read. Tools that can trade or move money never run, and a changed tool waits for your review.",
    trust: "Trust",
    trustRead: "Trust: read only",
    trustWrite: "Trust: non-financial writes",
    trusted: "Trusted.",
    trustedRead: "Trusted for reading.",
    trustedWrite: "Trusted for non-financial writes.",
    unnamedServer: "Unnamed server",
    alreadyTrusted: "This source is already trusted. Nothing changed.",
    serverMissing: "This server is no longer saved. Nothing changed.",
    serverChanged: "This server's address changed. Nothing changed; review it again.",
    nothingToTrust: "This server offers no tool that can be trusted.",
    feedSubscribed: "This feed is already subscribed.",
    serverChangedAgain: "The server changed again; the newer card replaces this one.",
    connectMcp: "Connect an MCP server",
    connectX: "Connect X",
    connectFeed: "Add a news feed",
    connectBrave: "Connect Brave web search",
    connectCalendar: "Connect an economic calendar",
    connectBroker: "Connect a broker account",
    connectHint:
      "What you type goes straight to the server: it never enters the chat or reaches an agent.",
    connectXHint:
      "Lonora reads X through web search, news feeds or an X MCP server you trust; it never uses your X account.",
    fieldName: "Name",
    fieldServerUrl: "Server URL",
    fieldFeedUrl: "Feed URL",
    fieldToken: "Access token (optional)",
    fieldApiKey: "API key",
    fieldAccount: "Account ID",
    fieldBrokerToken: "MetaApi token",
    connect: "Connect",
    connected: "Connected. Agents see only that it is configured.",
    alreadyConnected: "This is already connected. Nothing changed.",
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
    createTitle: "إنشاء وكيل؟",
    createHint: "يبدأ دون أي صلاحية مالية. لا يُنشأ شيء حتى تلمس.",
    create: "إنشاء الوكيل",
    createdTitle: "أُنشئ وكيل",
    undo: "تراجع",
    undoDeleteHint: "التراجع يزيله: لم يبدأ أي عمل بعد.",
    undoPauseHint: "التراجع يوقفه مؤقتًا: بدأ العمل، وسيبقى ما أنجزه.",
    askHint: "لا يملك صلاحية مالية: كل صفقة تنتظر لمستك.",
    grantHint: "يتداول وحده فقط ضمن التفويض الذي وقّعته.",
    noTradeHint: "لا يتداول.",
    task: "مهمته",
    templateTrading: "وكيل تداول",
    templateGeneral: "وكيل عام",
    templateResearch: "وكيل أبحاث",
    templateSupervisor: "وكيل إشراف",
    agent: "وكيل",
    focusPair: "زوج التركيز",
    on: "على",
    reportsTo: "يبلغ",
    model: "النموذج",
    paused: "متوقف",
    createdLine: "أُنشئ الوكيل.",
    undoneDeleted: "تم التراجع: أُزيل الوكيل.",
    undonePaused: "تم التراجع: أُوقف الوكيل مؤقتًا، وبقي ما أنجزه.",
    kept: "أُبقي الوكيل.",
    agentRemoved: "أُزيل هذا الوكيل مسبقًا.",
    alreadyCreated: "أُنشئ هذا الوكيل مسبقًا. لم يتغير شيء.",
    agentLimit: "لديك أكبر عدد مسموح من الوكلاء النشطين. لم يتغير شيء.",
    reportToMissing: "وكيل يبلغه هذا الوكيل لم يعد موجودًا. لم يتغير شيء.",
    connectionChanged: "تغيّر حساب الوسيط. لم يتغير شيء.",
    supervises: "يشرف على",
    superviseTitle: "السماح له بالإشراف؟",
    supervisionTitle: "تم تعيين الإشراف",
    supervisor: "المشرف",
    allow: "السماح",
    supervisionHint:
      "يقرأ عملهم وذاكرتهم ويراسلهم ويستطيع إيقاف عملهم أو استئنافه. لا يتداول عنهم أبدًا ولا يستخدم تفويضهم ولا يرفع فراملك.",
    supervisionUndoHint: "التراجع يوقفه فورًا.",
    supervisionSet: "تم تعيين الإشراف.",
    supervisionUndone: "تم التراجع: توقف الإشراف.",
    supervisionKept: "أُبقي.",
    supervisionEnded: "انتهى هذا الإشراف مسبقًا.",
    supervisionAlreadySet: "هذا الإشراف معيّن مسبقًا. لم يتغير شيء.",
    supervisionAgentMissing: "أحد هؤلاء الوكلاء لم يعد موجودًا. لم يتغير شيء.",
    stoppedTitle: "توقف الإشراف",
    restore: "استعادة",
    stoppedHint: "لم يعد يقرأ عملهم أو يراسلهم أو يوقفه. الاستعادة تعيده.",
    restored: "تمت الاستعادة: عاد الإشراف.",
    pauseTitle: "أوقفه مشرف مؤقتًا",
    pausedBy: "أوقفه",
    pausedWhat: "ما أُوقف",
    targetAgent: "الوكيل كله",
    targetRoutine: "مهمة مجدولة",
    targetWatch: "مراقبة",
    targetTask: "مهمة",
    pauseHint: "لا يستطيع الوكيل استئنافه بنفسه. الاستئناف يرفع الإيقاف الآن.",
    pauseOwnerHolds: "أوقفته أنت أيضًا، فلا يستأنفه غيرك.",
    pauseEnded: "انتهى هذا الإيقاف مسبقًا.",
    resumeWork: "استئناف",
    keepPaused: "إبقاؤه موقوفًا",
    resumedWork: "تم الاستئناف.",
    keptPaused: "بقي موقوفًا.",
    watchExpired: "انتهت مدة هذه المراقبة: مدّد مدتها من قائمة المراقبات لاستئنافها.",
    trustTitle: "الوثوق بهذا المصدر؟",
    trustReviewTitle: "تغيّرت أدوات هذا الخادم",
    trustServer: "خادم MCP",
    trustRepo: "مستودع على GitHub",
    trustPublisher: "ناشر على GitHub",
    trustFeed: "موقع موجز الأخبار",
    trustTools: "الأدوات",
    trustBlocked: "محظورة، تتداول أو تحرّك المال",
    trustWrites: "قد تغيّر شيئًا (مع الكتابة غير المالية فقط)",
    trustSubscribe: "ويشترك أيضًا في الموجز لكل الوكلاء.",
    trustHint:
      "يستخدمه الوكلاء دون أن يسألوك مجددًا، وتستطيع إزالته من القدرات. لا يحمل أي صلاحية مالية.",
    trustServerHint:
      "القراءة فقط تشغّل الأدوات التي تقرأ فحسب، والكتابة غير المالية تشغّلها كلها. الأدوات التي تتداول أو تحرّك المال لا تعمل أبدًا، وأي أداة تتغيّر تنتظر مراجعتك.",
    trustServerReadHint:
      "أدواته تقرأ فقط. الأدوات التي تتداول أو تحرّك المال لا تعمل أبدًا، وأي أداة تتغيّر تنتظر مراجعتك.",
    trust: "ثقة",
    trustRead: "ثقة: قراءة فقط",
    trustWrite: "ثقة: كتابة غير مالية",
    trusted: "صار موثوقًا.",
    trustedRead: "صار موثوقًا للقراءة.",
    trustedWrite: "صار موثوقًا للكتابة غير المالية.",
    unnamedServer: "خادم بلا اسم",
    alreadyTrusted: "هذا المصدر موثوق مسبقًا. لم يتغير شيء.",
    serverMissing: "لم يعد هذا الخادم محفوظًا. لم يتغير شيء.",
    serverChanged: "تغيّر عنوان هذا الخادم. لم يتغير شيء؛ راجعه من جديد.",
    nothingToTrust: "لا يقدّم هذا الخادم أي أداة يمكن الوثوق بها.",
    feedSubscribed: "هذا الموجز مشترك فيه مسبقًا.",
    serverChangedAgain: "تغيّر الخادم مجددًا؛ البطاقة الأحدث تحل محل هذه.",
    connectMcp: "ربط خادم MCP",
    connectX: "ربط X",
    connectFeed: "إضافة موجز أخبار",
    connectBrave: "ربط بحث Brave",
    connectCalendar: "ربط تقويم اقتصادي",
    connectBroker: "ربط حساب وسيط",
    connectHint: "ما تكتبه يذهب مباشرة إلى الخادم: لا يدخل المحادثة ولا يصل إلى أي وكيل.",
    connectXHint:
      "تقرأ لونورا X عبر البحث على الويب أو موجزات الأخبار أو خادم MCP لـ X تثق به، ولا تستخدم حسابك على X أبدًا.",
    fieldName: "الاسم",
    fieldServerUrl: "عنوان الخادم",
    fieldFeedUrl: "عنوان الموجز",
    fieldToken: "رمز الوصول (اختياري)",
    fieldApiKey: "مفتاح API",
    fieldAccount: "معرّف الحساب",
    fieldBrokerToken: "رمز MetaApi",
    connect: "ربط",
    connected: "تم الربط. لا يرى الوكلاء إلا أنه مُعدّ.",
    alreadyConnected: "هذا مربوط مسبقًا. لم يتغير شيء.",
  },
} as const satisfies Record<Language, Record<string, string>>;
export type OwnerActionText = (typeof ownerActionLabels)[Language];

export function ownerActionText(locale: string): OwnerActionText {
  return ownerActionLabels[language(locale)];
}

/** What a button sends: confirm (with an outcome for a resolve card, or the tier an MCP
 * server is trusted for) or cancel. */
export type OwnerActionButton = {
  key: "confirm" | "cancel" | "trust_write" | AttestedOutcome;
  label: string;
  decision: "confirm" | "cancel";
  outcome?: AttestedOutcome;
  tier?: EffectTier;
  primary: boolean;
};
/** One field of a credential card's secure form; its value goes only to the owner API. */
export type CredentialField = {
  key: "name" | "url" | "secret" | "account";
  label: string;
  type: "text" | "url" | "password";
  required: boolean;
  /** Addresses, ids and keys read left to right inside Arabic text. */
  ltr: boolean;
  initial: string;
};
export type CredentialForm = {
  target: CredentialTarget;
  fields: CredentialField[];
  submit: string;
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
  /** A credential card's secure form while it waits (submitted by the client itself). */
  credential: CredentialForm | null;
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
  if (card.status === "cancelled")
    return card.kind === "agent_created"
      ? text.kept
      : card.kind === "supervision_created" || card.kind === "supervision_stopped"
        ? text.supervisionKept
        : card.kind === "supervision_paused"
          ? text.keptPaused
          : text.cancelled;
  if (card.status === "confirmed") {
    switch (card.kind) {
      case "create_agent":
        return text.createdLine;
      case "agent_created":
        return card.result.undo === "deleted" ? text.undoneDeleted : text.undonePaused;
      case "supervise":
        return text.supervisionSet;
      case "supervision_created":
        return text.supervisionUndone;
      case "supervision_stopped":
        return text.restored;
      case "supervision_paused":
        return text.resumedWork;
      case "resume_trading":
        return text.resumed;
      case "lift_restriction":
        return text.lifted;
      case "set_account_limits":
        return text.limitsSaved;
      case "trust_source":
        // Read only matters only when some tool may change something.
        return card.result.tier === "write_nonfinancial"
          ? text.trustedWrite
          : card.facts.source?.kind === "mcp_server" && card.result.writes
            ? text.trustedRead
            : text.trusted;
      case "connect_credential":
        return text.connected;
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
    case "agent_already_removed":
      return text.agentRemoved;
    case "agent_already_created":
      return text.alreadyCreated;
    case "agent_limit_reached":
      return text.agentLimit;
    case "agent_report_to_missing":
      return text.reportToMissing;
    case "broker_connection_changed":
      return text.connectionChanged;
    case "supervision_ended":
      return text.supervisionEnded;
    case "supervision_already_set":
      return text.supervisionAlreadySet;
    case "supervision_agent_missing":
      return text.supervisionAgentMissing;
    case "supervision_pause_ended":
      return text.alreadyEnded;
    case "watch_expired":
      return text.watchExpired;
    case "source_already_trusted":
      return text.alreadyTrusted;
    case "mcp_connection_missing":
      return text.serverMissing;
    case "mcp_connection_changed":
      return text.serverChanged;
    case "mcp_nothing_to_trust":
      return text.nothingToTrust;
    case "feed_already_subscribed":
      return text.feedSubscribed;
    case "server_changed_again":
      return text.serverChangedAgain;
    case "credential_already_configured":
      return text.alreadyConnected;
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

const TEMPLATE_LABEL = {
  trading: "templateTrading",
  general: "templateGeneral",
  research: "templateResearch",
  supervisor: "templateSupervisor",
} as const;

/** Agent names, each isolated, joined with the language's list comma. */
function nameList(names: string[], lang: Language): string {
  return names.map(isolate).join(lang === "ar" ? "، " : ", ");
}

/** A supervision card's lines: the supervisor and the agents it supervises. */
function supervisionLines(card: OwnerAction, lang: Language, text: OwnerActionText): string[] {
  const supervision = card.facts.supervision;
  if (!supervision) return [];
  const lines: string[] = [];
  if (supervision.supervisor_name)
    lines.push(`${text.supervisor}: ${isolate(supervision.supervisor_name)}`);
  if (supervision.supervised_names.length)
    lines.push(`${text.supervises}: ${nameList(supervision.supervised_names, lang)}`);
  return lines;
}

const TARGET_LABEL = {
  agent: "targetAgent",
  routine: "targetRoutine",
  watch: "targetWatch",
  task: "targetTask",
} as const;

/** A pause card's lines: who paused it, whose work, and which item (its own label). */
function pauseLines(card: OwnerAction, text: OwnerActionText): string[] {
  const pause = card.facts.supervision;
  if (!pause) return [];
  const lines: string[] = [];
  const by = pause.supervisor_name ? isolate(pause.supervisor_name) : text.anAgent;
  lines.push(
    `${text.pausedBy}: ${by}${pause.from_owner_message ? ` · ${text.fromYourMessage}` : ""}`,
  );
  const agent = pause.supervised_names[0];
  if (agent) lines.push(`${text.agent}: ${isolate(agent)}`);
  if (pause.target) {
    const label = pause.target_label ? ` · ${isolate(pause.target_label)}` : "";
    lines.push(`${text.pausedWhat}: ${text[TARGET_LABEL[pause.target]]}${label}`);
  }
  return lines;
}

/** A creation card's lines: name and template, focus pair, ladder, links, model and task. */
function agentLines(
  card: OwnerAction,
  account: string | null,
  lang: Language,
  text: OwnerActionText,
): string[] {
  const agent = card.facts.agent;
  if (!agent) return [];
  const lines: string[] = [];
  // Each line starts with a word in the owner's language, so a name or ticker at the
  // start never turns an Arabic line left to right.
  const name = agent.name ? isolate(agent.name) : "";
  const template = agent.template ? text[TEMPLATE_LABEL[agent.template]] : text.agent;
  lines.push([template, name, agent.paused ? text.paused : null].filter(Boolean).join(" · "));
  if (agent.symbol)
    lines.push(
      `${text.focusPair}: ${isolate(agent.symbol)}${account ? ` ${text.on} ${account}` : ""}`,
    );
  if (agent.level)
    lines.push(`${tradingSafetyLabels[lang].level}: ${tradingSafetyLabels[lang][agent.level]}`);
  if (agent.report_to?.length) lines.push(`${text.reportsTo}: ${nameList(agent.report_to, lang)}`);
  if (agent.supervises?.length)
    lines.push(`${text.supervises}: ${nameList(agent.supervises, lang)}`);
  if (agent.model) lines.push(`${text.model}: ${isolate(agent.model)}`);
  // The stored task, word for word, on one line and isolated: it is the agent's
  // standing instruction, so the owner sees exactly what the tap keeps.
  const task = agent.responsibility?.split(/\s+/).filter(Boolean).join(" ");
  if (task) lines.push(`${text.task}: ${isolate(task)}`);
  return lines;
}

const SOURCE_LABEL = {
  mcp_server: "trustServer",
  github_repo: "trustRepo",
  github_owner: "trustPublisher",
  feed_domain: "trustFeed",
} as const;

/** A trust card's lines: which source, the tools it would trust and those it blocks. */
function sourceLines(card: OwnerAction, lang: Language, text: OwnerActionText): string[] {
  const source = card.facts.source;
  if (!source) return [];
  const label = source.label
    ? isolate(source.label)
    : source.kind === "mcp_server"
      ? text.unnamedServer
      : "";
  const lines = [`${text[SOURCE_LABEL[source.kind]]}: ${label}`];
  if (source.tools?.length) lines.push(`${text.trustTools}: ${nameList(source.tools, lang)}`);
  if (source.writes?.length) lines.push(`${text.trustWrites}: ${nameList(source.writes, lang)}`);
  if (source.blocked?.length) lines.push(`${text.trustBlocked}: ${nameList(source.blocked, lang)}`);
  if (source.subscribe) lines.push(text.trustSubscribe);
  return lines;
}

function credentialTitle(
  credential: { target: CredentialTarget; service: "x" | null },
  text: OwnerActionText,
): string {
  if (credential.service === "x") return text.connectX;
  return {
    mcp_server: text.connectMcp,
    news_feed: text.connectFeed,
    brave_search: text.connectBrave,
    economic_calendar: text.connectCalendar,
    broker: text.connectBroker,
  }[credential.target];
}

/** The secure form of a credential card: which fields, in the owner's language. */
export function credentialForm(
  credential: { target: CredentialTarget; service: "x" | null },
  text: OwnerActionText,
): CredentialForm {
  const name = (initial: string): CredentialField => ({
    key: "name",
    label: text.fieldName,
    type: "text",
    required: true,
    ltr: false,
    initial,
  });
  const url = (label: string): CredentialField => ({
    key: "url",
    label,
    type: "url",
    required: true,
    ltr: true,
    initial: "",
  });
  const secret = (label: string, required: boolean): CredentialField => ({
    key: "secret",
    label,
    type: "password",
    required,
    ltr: true,
    initial: "",
  });
  const account: CredentialField = {
    key: "account",
    label: text.fieldAccount,
    type: "text",
    required: true,
    ltr: true,
    initial: "",
  };
  const fields: CredentialField[] = {
    mcp_server: [
      name(credential.service === "x" ? "X" : ""),
      url(text.fieldServerUrl),
      secret(text.fieldToken, false),
    ],
    news_feed: [name(""), url(text.fieldFeedUrl)],
    economic_calendar: [name(""), url(text.fieldFeedUrl)],
    brave_search: [name("Brave Search"), secret(text.fieldApiKey, true)],
    broker: [account, secret(text.fieldBrokerToken, true)],
  }[credential.target];
  return { target: credential.target, fields, submit: text.connect };
}

/** A minimal POST for the client's API (Web or Mobile); it returns the created record. */
export type CredentialPost = (path: string, body: unknown) => Promise<{ id: string }>;

/**
 * Submit a credential card's form straight to the owner API and say what it created.
 * The secret goes to /integrations/secrets (stored encrypted, only its id is kept) or,
 * for a broker, to /trading/connections; it is never sent to the card or a chat route.
 */
export async function submitCredential(
  post: CredentialPost,
  target: CredentialTarget,
  values: Partial<Record<CredentialField["key"], string>>,
): Promise<{ resource: "integration" | "mcp" | "broker"; id: string }> {
  const name = (values.name ?? "").trim();
  const secret = values.secret ?? "";
  const stored = async () =>
    secret
      ? (await post("/integrations/secrets", { name: name || target, value: secret })).id
      : null;
  if (target === "broker") {
    const account = await post("/trading/connections", {
      provider: "metaapi",
      account_id: (values.account ?? "").trim(),
      region: null,
      enabled: true,
      secret_id: null,
      api_key: secret,
    });
    return { resource: "broker", id: account.id };
  }
  if (target === "mcp_server") {
    const secret_id = await stored();
    const server = await post("/mcp", {
      payload: {
        name,
        url: (values.url ?? "").trim(),
        transport: "http",
        command: [],
        secret_id,
        enabled: true,
      },
      agent_id: null,
      thread_id: null,
    });
    return { resource: "mcp", id: server.id };
  }
  const secret_id = target === "brave_search" ? await stored() : null;
  const integration = await post("/integrations", {
    payload: {
      type: target,
      name,
      url: target === "brave_search" ? null : (values.url ?? "").trim(),
      secret_id,
      enabled: true,
    },
    agent_id: null,
    thread_id: null,
  });
  return { resource: "integration", id: integration.id };
}

/** What the agent may do with money, by its level now (a grant may be signed later). */
function authorityHint(level: OwnerActionAgent["level"], text: OwnerActionText): string {
  if (level === "autonomous") return text.grantHint;
  if (level === "analysis") return text.noTradeHint;
  return text.askHint;
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
  let form: CredentialForm | null = null;
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
    case "create_agent": {
      title = text.createTitle;
      lines.push(...agentLines(card, account, lang, text));
      hint = text.createHint;
      buttons = pair(text.create, text.notNow);
      break;
    }
    case "agent_created": {
      title = text.createdTitle;
      const agent = facts.agent;
      lines.push(...agentLines(card, account, lang, text));
      if (!agent?.exists) {
        // Removed elsewhere: the card can only be dismissed.
        hint = text.agentRemoved;
        buttons = [{ key: "cancel", label: text.keep, decision: "cancel", primary: false }];
        break;
      }
      hint = `${authorityHint(agent.level, text)} ${
        facts.undo === "delete" ? text.undoDeleteHint : text.undoPauseHint
      }`;
      buttons = [
        { key: "confirm", label: text.undo, decision: "confirm", primary: false },
        { key: "cancel", label: text.keep, decision: "cancel", primary: false },
      ];
      break;
    }
    case "supervise": {
      title = text.superviseTitle;
      lines.push(...supervisionLines(card, lang, text));
      hint = text.supervisionHint;
      buttons = pair(text.allow, text.notNow);
      break;
    }
    case "supervision_created": {
      title = text.supervisionTitle;
      lines.push(...supervisionLines(card, lang, text));
      if (!card.facts.supervision?.active) {
        // Revoked elsewhere (the profile): the card can only be dismissed.
        hint = text.supervisionEnded;
        buttons = [{ key: "cancel", label: text.keep, decision: "cancel", primary: false }];
        break;
      }
      hint = `${text.supervisionHint} ${text.supervisionUndoHint}`;
      buttons = [
        { key: "confirm", label: text.undo, decision: "confirm", primary: false },
        { key: "cancel", label: text.keep, decision: "cancel", primary: false },
      ];
      break;
    }
    case "supervision_stopped": {
      title = text.stoppedTitle;
      lines.push(...supervisionLines(card, lang, text));
      if (!card.facts.supervision?.active) {
        // Set again elsewhere (the profile, a card): the card can only be dismissed.
        hint = text.supervisionAlreadySet;
        buttons = [{ key: "cancel", label: text.keep, decision: "cancel", primary: false }];
        break;
      }
      hint = text.stoppedHint;
      buttons = [
        { key: "confirm", label: text.restore, decision: "confirm", primary: false },
        { key: "cancel", label: text.keep, decision: "cancel", primary: false },
      ];
      break;
    }
    case "supervision_paused": {
      title = text.pauseTitle;
      lines.push(...pauseLines(card, text));
      if (!card.facts.supervision?.active) {
        // Resumed elsewhere (the supervisor, the owner): the card can only be dismissed.
        hint = text.pauseEnded;
        buttons = [{ key: "cancel", label: text.keep, decision: "cancel", primary: false }];
        break;
      }
      hint = card.facts.supervision.owner_holds ? text.pauseOwnerHolds : text.pauseHint;
      buttons = pair(text.resumeWork, text.keepPaused);
      break;
    }
    case "trust_source": {
      const source = facts.source;
      title = source?.review ? text.trustReviewTitle : text.trustTitle;
      lines.push(...sourceLines(card, lang, text));
      if (source?.kind === "mcp_server" && !source.writes?.length) {
        // Every tool only reads: one tap, nothing to choose.
        hint = text.trustServerReadHint;
        buttons = [
          { key: "confirm", label: text.trust, decision: "confirm", tier: "read", primary: true },
          { key: "cancel", label: text.notNow, decision: "cancel", primary: false },
        ];
        break;
      }
      if (source?.kind === "mcp_server") {
        hint = text.trustServerHint;
        buttons = [
          {
            key: "confirm",
            label: text.trustRead,
            decision: "confirm",
            tier: "read",
            primary: true,
          },
          {
            key: "trust_write",
            label: text.trustWrite,
            decision: "confirm",
            tier: "write_nonfinancial",
            primary: false,
          },
          { key: "cancel", label: text.notNow, decision: "cancel", primary: false },
        ];
        break;
      }
      hint = text.trustHint;
      buttons = pair(text.trust, text.notNow);
      break;
    }
    case "connect_credential": {
      const credential = facts.credential;
      title = credential ? credentialTitle(credential, text) : text.connectMcp;
      hint =
        credential?.service === "x" ? `${text.connectHint} ${text.connectXHint}` : text.connectHint;
      if (credential) form = credentialForm(credential, text);
      // Connect is the form's own submit: the value goes to the owner API, never here.
      buttons = [{ key: "cancel", label: text.notNow, decision: "cancel", primary: false }];
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
    buttons: pending ? buttons : [],
    notes: pending && card.kind === "resolve_operation",
    credential: pending ? form : null,
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
  owner_action_tier_required: {
    en: "Choose what its tools may do.",
    ar: "اختر ما يُسمح لأدواته بفعله.",
  },
  owner_action_connection_required: {
    en: "Fill in the form to connect it.",
    ar: "املأ النموذج لربطه.",
  },
  owner_action_connection_mismatch: {
    en: "That connection does not match this card.",
    ar: "هذا الربط لا يطابق هذه البطاقة.",
  },
  mcp_owner_trust_disabled: {
    en: "This server's operator allows only declared MCP tools.",
    ar: "مشغّل هذا الخادم يسمح فقط بأدوات MCP المعلنة.",
  },
  mcp_tools_changed: {
    en: "The server's tools changed since you looked. Review them again.",
    ar: "تغيّرت أدوات الخادم منذ نظرت إليها. راجعها من جديد.",
  },
  mcp_nothing_to_trust: {
    en: "This server offers no tool that can be trusted.",
    ar: "لا يقدّم هذا الخادم أي أداة يمكن الوثوق بها.",
  },
  news_feed_url_invalid: {
    en: "Enter a public https:// feed address.",
    ar: "أدخل عنوان موجز عامًا يبدأ بـ https://.",
  },
};

/** Owner text for a card decision's refusal, shared by Web and Mobile; null if not one. */
export function ownerActionError(code: string | null | undefined, locale: string): string | null {
  const entry = code ? errors[code] : undefined;
  return entry ? entry[language(locale)] : null;
}
