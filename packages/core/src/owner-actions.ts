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
  GrantDelegation,
  OwnerAction,
  OwnerActionAccount,
  OwnerActionAgent,
  OwnerActionChallenge,
  OwnerActionDecision,
  OwnerActionGrantTerms,
  OwnerActionLimitField,
} from "@lonora/contracts";
import { accountAuthorityLabels } from "./account-authority-labels";
import { modelCard } from "./agent-model";
import {
  isolate,
  listSeparator,
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
    startTitle: "Start trading",
    startStopped: "New trading has not been started yet",
    startHint:
      "Starting widens no authority: every agent stays within its level, its grant and your limits, and exits are always allowed.",
    start: "Start trading",
    started: "Trading started.",
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
    sameOnAnotherCard: "The same grant waits on another card. Nothing changed.",
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
    noDailyLossChoice: "No daily loss limit (my choice)",
    keepCurrentLimit: "Keep my current limit",
    raiseNeedsCard:
      "You asked for {amount}: this card never raises the daily loss limit; raising it needs a limits card with your passkey.",
    tradingStopped: "New trading is stopped",
    resumeToo: "Resume trading too",
    conflict:
      "{agent} already trades {markets} here on its own. Keeping both is fine: the account's limits bind them together.",
    stopOther: "Stop {agent} trading on its own on this account",
    stoppedOthers: "Stopped on this account: {agents}.",
    replaces: "Replaces its current grant",
    capOrderVolume: "max {value} lots per order",
    capSymbolVolume: "max {value} lots per market",
    capPositions: "max {value} positions",
    capPendingOrders: "max {value} pending orders",
    capActions: "max {value} executions",
    capEquity: "equity floor {value}",
    boundedRule: "a stop loss on every entry, never loosened",
    noCaps: "no volume, position or activity caps",
    noBoundedRule: "no stop-loss rule",
    everyAction: "every trading action",
    ownIncludedShort: "positions you opened yourself included",
    untilStoppedShort: "until you stop it",
    for12hShort: "for 12 hours",
    for24hShort: "for 24 hours",
    for7dShort: "for 7 days",
    delegationCustom: "Custom",
    delegationFull: "Full delegation",
    customMeaning:
      "Custom: only the markets, actions and time shown here, with the daily loss limit shown; positions you opened yourself only if you switch them on.",
    fullMeaning:
      "Full delegation: every pair on this account and every action (open, close fully or partly, pending orders, change stop loss and take profit, cancel), positions you opened yourself too, until you stop it. This card sets no daily loss limit.",
    fullLimits:
      "Money limits you set on this account elsewhere stay in force; removing them is a separate step with your passkey.",
    grantHint:
      "Confirm with your passkey. Anything outside this grant still comes to you as an approval card.",
    oneRule:
      "Every agent can see and use everything you have connected to Lonora, but it places real trades only inside the grant you signed for it with your passkey and within your account limits. Anything that needs you arrives as a one-tap card in the chat, you can stop anything with one tap, and no agent, skill or plugin can ever widen your money authority.",
    authorize: "Authorize with passkey",
    signed: "Signed. It trades on its own inside this grant.",
    signedStopped:
      "Signed. New trading is still stopped, so it trades on its own inside this grant once you resume.",
    alreadySigned: "This is already signed. Nothing changed.",
    createTitle: "Create an agent?",
    createHint: "It starts with no money authority. Nothing is created until you tap.",
    create: "Create agent",
    createdTitle: "Agent created",
    undo: "Undo",
    undoDeleteHint: "Undo removes it: it has not started any work yet.",
    undoPauseHint: "Undo pauses it: it already started work, which is kept.",
    askHint: "No money authority: every trade waits for your tap.",
    createdGrantHint: "It trades on its own only inside the grant you signed.",
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
      "Read only runs just the tools that only read; non-financial writes runs them all. Tools that look like they trade or move money are blocked and never run, and a changed tool waits for your review. Money moves only through your grants.",
    trustServerReadHint:
      "Its tools only read. Tools that look like they trade or move money are blocked and never run, and a changed tool waits for your review.",
    trustServerBlockedHint:
      "It offers tools that look like they trade or move money. They are blocked, so only its reading tools can run. Money moves only through your grants.",
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
    connectModel: "Connect a model provider",
    modelHint:
      "The key is stored encrypted on your Lonora server and never enters the chat. Your models use it, and so can the commands your agents run in the workspace.",
    modelEndpointHint: "It is sent to the address above with every request.",
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
    secretTitle: "Secret",
    secretAskedBy: "Asked by {agent}",
    secretWorkspace:
      "Saved encrypted for your workspace. What you type never enters the chat or reaches an agent.",
    secretBroker:
      "Saved encrypted for your broker connection only; it never enters the workspace or reaches an agent.",
    secretSave: "Save",
    secretSaved: "Saved encrypted. No agent sees the values.",
    secretSavesAs: "Saved as {names}",
    secretReplaces: "Replaces the value saved as {names}",
    pauseNewToday: "Stop new trades today",
    pauseNewTodayHint: "Closing stays allowed",
    optional: "optional",
    noteShort: "Note",
    brokerRefShort: "Broker reference",
    addNote: "Add a note or the broker reference",
    deviceOnce: "A one-time step; after it, authorisations are signed with this device's passkey.",
    expiresIn: "The request expires in",
    statusPending: "Waiting for your decision",
    statusConfirmed: "Done",
    statusCancelled: "Cancelled",
    statusExpired: "Expired",
    statusSuperseded: "Replaced",
    renew: "New request",
    latest: "Show the latest",
    undone: "Undone",
    watchChangedTitle: "Watch extended",
    watchChangedHint:
      "The agent moved this watch's end without asking. Undo puts the earlier end back.",
    watchNoEnd: "until cancelled",
    watchUndone: "Undone: the watch ends as before.",
    watchChangedAgain: "This watch changed since. Nothing to undo.",
    watchRemoved: "This watch no longer exists.",
    stopTightenedTitle: "Stop loss tightened",
    stopLoss: "Stop loss",
    stopTightenedLine: "Stop loss tightened. No undo: loosening it again would be a new order.",
  },
  ar: {
    resumeTitle: "استئناف التداول",
    resumeStopped: "التداول الجديد متوقف",
    resumeHint: "الاستئناف لا يوسّع أي صلاحية: يبقى كل وكيل ضمن مستواه وتفويضه وحدودك.",
    resume: "استئناف التداول",
    startTitle: "بدء التداول",
    startStopped: "لم يبدأ التداول الجديد بعد",
    startHint:
      "البدء لا يوسّع أي صلاحية: يبقى كل وكيل ضمن مستواه وتفويضه وحدودك، والخروج متاح دائمًا.",
    start: "بدء التداول",
    started: "بدأ التداول.",
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
    sameOnAnotherCard: "التفويض نفسه ينتظر في بطاقة أخرى. لم يتغير شيء.",
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
    ofEquity: "من حقوق الملكية",
    suggested: "مقترح",
    accountLimits: "الحدود المالية للحساب",
    noMoneyLimitChoice: "بلا حد مالي، بقرار مني",
    noDailyLossChoice: "بلا حد للخسارة اليومية، بقرار مني",
    keepCurrentLimit: "أبقِ حدي الحالي",
    raiseNeedsCard:
      "طلبت {amount}: هذه البطاقة لا ترفع حد الخسارة اليومية أبدًا؛ رفعه يحتاج بطاقة حدود بمفتاح المرور.",
    tradingStopped: "التداول الجديد متوقف",
    resumeToo: "استأنف التداول أيضًا",
    conflict: "{agent} يتداول {markets} هنا بنفسه. لا بأس ببقائهما معًا: حدود الحساب تلزمهما معًا.",
    stopOther: "أوقف تداول {agent} بنفسه على هذا الحساب",
    stoppedOthers: "أُوقف على هذا الحساب: {agents}.",
    replaces: "يحل محل تفويضه الحالي",
    capOrderVolume: "حد حجم الأمر {value} لوت",
    capSymbolVolume: "حد حجم السوق {value} لوت",
    capPositions: "حد الصفقات {value}",
    capPendingOrders: "حد الأوامر المعلّقة {value}",
    capActions: "حد التنفيذات {value}",
    capEquity: "حد حقوق الملكية {value}",
    boundedRule: "وقف خسارة لكل دخول دون توسيعه",
    noCaps: "دون حدود للحجم أو الصفقات أو النشاط",
    noBoundedRule: "دون شرط وقف الخسارة",
    everyAction: "كل عمليات التداول",
    ownIncludedShort: "يشمل المراكز التي فتحتها بنفسك",
    untilStoppedShort: "حتى توقفه",
    for12hShort: "لمدة ١٢ ساعة",
    for24hShort: "لمدة ٢٤ ساعة",
    for7dShort: "لمدة ٧ أيام",
    delegationCustom: "مخصص",
    delegationFull: "تفويض كامل",
    customMeaning:
      "مخصص: الأسواق والعمليات والمدة الظاهرة هنا فقط، مع حد الخسارة اليومية الظاهر؛ ولا تُشمل المراكز التي فتحتها بنفسك إلا إذا فعّلتها.",
    fullMeaning:
      "تفويض كامل: كل أزواج هذا الحساب وكل العمليات (الفتح، والإغلاق الكلي أو الجزئي، والأوامر المعلّقة، وتعديل وقف الخسارة وجني الربح، والإلغاء)، والمراكز التي فتحتها بنفسك أيضًا، حتى توقفه. لا تضع هذه البطاقة حدًا للخسارة اليومية.",
    fullLimits:
      "تبقى الحدود المالية التي ضبطتها لهذا الحساب في مكان آخر نافذة؛ وإزالتها خطوة منفصلة بمفتاح المرور.",
    grantHint: "أكّد بمفتاح المرور. ما يخرج عن هذا التفويض يصلك كبطاقة موافقة.",
    oneRule:
      "كل وكيل يرى ويستخدم كل ما وصلته بلونورا، لكنه لا ينفّذ صفقة حقيقية إلا ضمن التفويض الذي وقّعته له بمفتاح المرور وضمن حدود حسابك؛ وما يحتاجك يصلك كبطاقة في المحادثة بلمسة واحدة، وتستطيع إيقاف أي شيء بلمسة، ولا يستطيع أي وكيل أو مهارة أو إضافة توسيع صلاحياتك المالية.",
    authorize: "التفويض بمفتاح المرور",
    signed: "وُقّع. يتداول بنفسه ضمن هذا التفويض.",
    signedStopped:
      "وُقّع. التداول الجديد ما زال متوقفًا، فيتداول بنفسه ضمن هذا التفويض بعد أن تستأنف.",
    alreadySigned: "هذا موقّع بالفعل. لم يتغير شيء.",
    createTitle: "إنشاء وكيل؟",
    createHint: "يبدأ دون أي صلاحية مالية. لا يُنشأ شيء حتى تلمس.",
    create: "إنشاء الوكيل",
    createdTitle: "أُنشئ وكيل",
    undo: "تراجع",
    undoDeleteHint: "التراجع يزيله: لم يبدأ أي عمل بعد.",
    undoPauseHint: "التراجع يوقفه مؤقتًا: بدأ العمل، وسيبقى ما أنجزه.",
    askHint: "لا يملك صلاحية مالية: كل صفقة تنتظر لمستك.",
    createdGrantHint: "يتداول وحده فقط ضمن التفويض الذي وقّعته.",
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
      "القراءة فقط تشغّل الأدوات التي تقرأ فحسب، والكتابة غير المالية تشغّلها كلها. الأدوات التي يبدو أنها تتداول أو تحرّك المال محظورة ولا تعمل أبدًا، وأي أداة تتغيّر تنتظر مراجعتك. المال لا يتحرك إلا ضمن تفويضاتك.",
    trustServerReadHint:
      "أدواته تقرأ فقط. الأدوات التي يبدو أنها تتداول أو تحرّك المال محظورة ولا تعمل أبدًا، وأي أداة تتغيّر تنتظر مراجعتك.",
    trustServerBlockedHint:
      "يقدّم أدوات يبدو أنها تتداول أو تحرّك المال. هي محظورة، فلا تعمل إلا أدواته التي تقرأ. المال لا يتحرك إلا ضمن تفويضاتك.",
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
    connectModel: "ربط مزوّد نماذج",
    modelHint:
      "يُحفظ المفتاح مشفّراً على خادم Lonora ولا يدخل المحادثة. تستخدمه نماذجك، وتستطيع استخدامه الأوامر التي يشغّلها وكلاؤك في مساحة العمل.",
    modelEndpointHint: "ويُرسَل إلى العنوان أعلاه مع كل طلب.",
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
    secretTitle: "بيانات سرّية",
    secretAskedBy: "يطلبها {agent}",
    secretWorkspace: "تُحفظ مشفّرة لمساحة العمل. ما تكتبه لا يدخل المحادثة ولا يصل إلى أي وكيل.",
    secretBroker: "تُحفظ مشفّرة لاتصال الوسيط فقط، ولا تدخل مساحة العمل ولا تصل إلى أي وكيل.",
    secretSave: "حفظ",
    secretSaved: "حُفظت مشفّرة. لا يرى أي وكيل القيم.",
    secretSavesAs: "تُحفظ باسم {names}",
    secretReplaces: "تحلّ محل القيمة المحفوظة باسم {names}",
    pauseNewToday: "أوقف الصفقات الجديدة اليوم",
    pauseNewTodayHint: "الإغلاق مسموح",
    optional: "اختياري",
    noteShort: "ملاحظة",
    brokerRefShort: "مرجع الوسيط",
    addNote: "إضافة ملاحظة أو مرجع الوسيط",
    deviceOnce: "خطوة لمرة واحدة؛ بعدها تُوقَّع التفويضات بمفتاح المرور على هذا الجهاز.",
    expiresIn: "ينتهي الطلب خلال",
    statusPending: "بانتظار قرارك",
    statusConfirmed: "تم",
    statusCancelled: "أُلغي",
    statusExpired: "انتهت المهلة",
    statusSuperseded: "استُبدل",
    renew: "طلب جديد",
    latest: "عرض الأحدث",
    undone: "تم التراجع",
    watchChangedTitle: "مُدّدت مراقبة",
    watchChangedHint: "مدّد الوكيل نهاية هذه المراقبة دون أن يسأل. «تراجع» يعيد النهاية السابقة.",
    watchNoEnd: "حتى الإلغاء",
    watchUndone: "تم التراجع: تنتهي المراقبة كما كانت.",
    watchChangedAgain: "تغيّرت هذه المراقبة بعد ذلك. لا شيء للتراجع عنه.",
    watchRemoved: "لم تعد هذه المراقبة موجودة.",
    stopTightenedTitle: "شُدّ وقف الخسارة",
    stopLoss: "وقف الخسارة",
    stopTightenedLine: "شُدّ وقف الخسارة. لا تراجع: إرخاؤه من جديد أمر جديد.",
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
/** An owner switch on a card (a grant card's own positions, money limit, Resume, a
 * conflict); the client keeps its state and ``ownerActionChoices`` sends it. An option
 * with ``choice`` is one of a group of which exactly one is selected (a grant card's
 * Custom or Full delegation): it is shown as a radio, ``initial`` is the server's stored
 * choice, and selecting it sends ``ownerActionChoose`` at once. ``detail`` says plainly
 * what the selected choice means. */
export type OwnerActionOption = {
  key: string;
  label: string;
  initial: boolean;
  choice?: { group: "delegation"; value: GrantDelegation };
  detail?: string;
};
/** One field of a Secret card's form in the owner's language; ``password`` masks it. */
export type SecretFormField = {
  key: string;
  label: string;
  type: "password" | "text" | "url";
  required: boolean;
};
/** A Secret card's form while it waits; ``submitSecret`` posts its values. */
export type SecretForm = { fields: SecretFormField[]; submit: string };
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
  /** A Secret card's form while it waits (submitted by the client itself). */
  secret: SecretForm | null;
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

function settledLine(card: OwnerAction, text: OwnerActionText, lang: Language): string | null {
  if (card.status === "pending") return null;
  if (card.status === "cancelled")
    return card.kind === "agent_created" || card.kind === "watch_changed"
      ? text.kept
      : card.kind === "supervision_created" || card.kind === "supervision_stopped"
        ? text.supervisionKept
        : card.kind === "supervision_paused"
          ? text.keptPaused
          : text.cancelled;
  if (card.status === "confirmed") {
    switch (card.kind) {
      case "grant_authority": {
        const stopped = card.result.stopped_agents ?? [];
        // The card shows what was signed; while Stop new trading holds, it waits for Resume.
        const stoppedStill =
          card.facts.global_trading?.state === "stopped" && card.result.resumed !== true;
        const signed = stoppedStill ? text.signedStopped : text.signed;
        return stopped.length
          ? `${signed} ${fill(text.stoppedOthers, { agents: stopped.map(isolate).join(listSeparator(lang)) })}`
          : signed;
      }
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
        return card.result.started === true ? text.started : text.resumed;
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
      case "secret":
        return card.facts.secret?.connect ? text.connected : text.secretSaved;
      case "watch_changed":
        return text.watchUndone;
      case "stop_tightened":
        return text.stopTightenedLine;
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
    case "same_choice_on_another_card":
      return text.sameOnAnotherCard;
    case "grant_already_active":
      return text.alreadySigned;
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
    case "watch_changed_again":
      return text.watchChangedAgain;
    case "watch_removed":
      return text.watchRemoved;
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

function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => values[key] ?? "");
}

function marketsLabel(
  scope: "selected" | "account",
  symbols: string[],
  text: OwnerActionText,
  lang: Language,
): string {
  return scope === "account"
    ? text.allPairsAccount
    : symbols.map(isolate).join(listSeparator(lang));
}

function actionsLabel(actions: string[], lang: Language): string {
  return actions.map((item) => actionLabel(item, lang)).join(listSeparator(lang));
}

/** The arrow of a change points along the reading direction: right to left in Arabic. */
function arrow(lang: Language): string {
  return lang === "ar" ? "←" : "→";
}

type GrantDuration = NonNullable<OwnerAction["facts"]["grant"]>["duration"];

function durationShort(duration: GrantDuration, text: OwnerActionText): string {
  return duration === "12h"
    ? text.for12hShort
    : duration === "24h"
      ? text.for24hShort
      : duration === "7d"
        ? text.for7dShort
        : text.untilStoppedShort;
}

function sameActions(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((item) => right.includes(item));
}

/**
 * The replaced grant and what replacing it changes, in one line: every cap, protection,
 * market, action and expiry it had, then the new grant's side of each of them. A cap
 * or protection that goes away is said plainly, so no effect of the tap is hidden.
 */
function replacesLine(
  old: OwnerActionGrantTerms,
  grant: NonNullable<OwnerAction["facts"]["grant"]>,
  currency: string | null,
  text: OwnerActionText,
  lang: Language,
  locale: string,
  now: Date,
): string {
  const value = (amount: string | number, unit = "") => isolate(`${amount}${unit}`);
  const before = [marketsLabel(old.symbol_scope, old.symbols, text, lang)];
  if (!old.all_actions) before.push(`${text.actionsLine}: ${actionsLabel(old.actions, lang)}`);
  const caps: Array<[string | number | null, string, string]> = [
    [old.maximum_order_volume, text.capOrderVolume, ""],
    [old.maximum_symbol_volume, text.capSymbolVolume, ""],
    [old.maximum_positions, text.capPositions, ""],
    [old.maximum_pending_orders, text.capPendingOrders, ""],
    [old.maximum_actions, text.capActions, ""],
    [old.minimum_equity, text.capEquity, currency ? ` ${currency}` : ""],
  ];
  const capped = caps.filter(([amount]) => amount != null);
  for (const [amount, template, unit] of capped)
    before.push(fill(template, { value: value(amount ?? "", unit) }));
  if (old.management_mode === "bounded") before.push(text.boundedRule);
  const timed = old.valid_until != null || grant.duration !== "until_stopped";
  if (timed)
    before.push(
      old.valid_until
        ? `${text.until} ${readinessTime(old.valid_until, locale, now)}`
        : text.untilStoppedShort,
    );
  if (old.allow_manual_positions) before.push(text.ownIncludedShort);
  const after = [marketsLabel(grant.symbol_scope, grant.symbols, text, lang)];
  if (!sameActions(old.actions, grant.actions))
    after.push(
      grant.all_actions
        ? text.everyAction
        : `${text.actionsLine}: ${actionsLabel(grant.actions, lang)}`,
    );
  if (capped.length) after.push(text.noCaps);
  if (old.management_mode === "bounded") after.push(text.noBoundedRule);
  if (timed) after.push(durationShort(grant.duration, text));
  return `${text.replaces}: ${before.join(" · ")} ${arrow(lang)} ${after.join(" · ")}`;
}

function grantCard(card: OwnerAction, locale: string, lang: Language, now: Date) {
  const text = ownerActionLabels[lang];
  const facts = card.facts;
  const grant = facts.grant;
  const agent = grant?.agent_name ? isolate(grant.agent_name) : text.grantAgent;
  const lines: string[] = [];
  const options: OwnerActionOption[] = [];
  const hints: string[] = [];
  const delegation = grantDelegation(card);
  const pending = card.status === "pending";
  if (grant && pending && grant.full_available === true)
    // One choice in the card's list, Custom selected unless the card says otherwise; the
    // selected one says plainly what it means.
    for (const value of ["custom", "full"] as const)
      options.push({
        key: `delegation:${value}`,
        label: value === "full" ? text.delegationFull : text.delegationCustom,
        initial: delegation === value,
        choice: { group: "delegation", value },
        ...(delegation === value
          ? {
              detail:
                value === "full" ? `${text.fullMeaning} ${text.fullLimits}` : text.customMeaning,
            }
          : {}),
      });
  if (grant) {
    // Signed: the label follows the signed terms, as the readiness line and safety sheet
    // read them, so a Custom card that signed exactly Full's terms says so too.
    if (!pending && (delegation === "full" || (card.status === "confirmed" && fullTerms(grant))))
      lines.push(text.delegationFull);
    const account = accountLabel(facts.account, text);
    if (account) lines.push(`${text.account}: ${account}`);
    lines.push(`${text.markets}: ${marketsLabel(grant.symbol_scope, grant.symbols, text, lang)}`);
    lines.push(
      grant.all_actions
        ? text.allActions
        : `${text.actionsLine}: ${actionsLabel(grant.actions, lang)}`,
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
    if (pending && delegation === "custom")
      // The switch states it; a fixed line beside it would contradict a ticked switch.
      options.push({
        key: "manual",
        label: text.includeOwn,
        initial: grant.allow_manual_positions,
      });
    // Full delegation always includes them: a line, never a switch.
    else lines.push(grant.allow_manual_positions ? text.ownIncluded : text.ownExcluded);
  }
  const money = facts.money;
  if (money) {
    const daily = money.daily_loss;
    const amount = (value: string) =>
      isolate(daily.currency ? `${value} ${daily.currency}` : value);
    // The daily loss has its own line; the account line shows every other limit.
    const rest = Object.fromEntries(
      Object.entries(money.limits.limits).filter(([name]) => name !== "max_daily_loss"),
    );
    const others = Object.keys(rest).length > 0;
    if (daily.proposed) {
      const basis = daily.percent
        ? ` (${daily.basis === "suggested" ? `${text.suggested}: ` : ""}${isolate(`${daily.percent}%`)} ${text.ofEquity})`
        : "";
      // An existing limit is only ever lowered, in one line from the current amount.
      const from = daily.current ? `${isolate(daily.current)} ${arrow(lang)} ` : "";
      lines.push(`${text.dailyLoss}: ${from}${amount(daily.proposed)}${basis}`);
      options.push(
        daily.current
          ? { key: "keep_limit", label: text.keepCurrentLimit, initial: false }
          : {
              key: "no_money_limit",
              label: others ? text.noDailyLossChoice : text.noMoneyLimitChoice,
              initial: false,
            },
      );
    } else if (daily.current) {
      lines.push(`${text.dailyLoss}: ${amount(daily.current)}`);
    }
    if (daily.requested_above)
      lines.push(fill(text.raiseNeedsCard, { amount: amount(daily.requested_above) }));
    if (others)
      lines.push(
        `${text.accountLimits}: ${moneyLimitsLine({ ...money.limits, limits: rest }, locale)}`,
      );
    else if (!daily.proposed && !daily.current)
      lines.push(`${text.accountLimits}: ${moneyLimitsLine(money.limits, locale)}`);
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
        markets: marketsLabel(conflict.symbol_scope, conflict.symbols, text, lang),
      }),
    );
    options.push({
      key: `stop:${conflict.authority_id}`,
      label: fill(text.stopOther, { agent: name }),
      initial: false,
    });
  }
  if (facts.replaces && grant)
    lines.push(
      replacesLine(
        facts.replaces,
        grant,
        money?.daily_loss.currency ?? null,
        text,
        lang,
        locale,
        now,
      ),
    );
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

/** A card's grant terms are Full delegation's (``full_delegation`` in
 * lonora_contracts.account_authority reads a card's envelope the same way: a card signs no
 * cap of its own): every pair on the account, every action, until stopped, the owner's own
 * positions too. */
function fullTerms(grant: NonNullable<OwnerAction["facts"]["grant"]>): boolean {
  return (
    grant.symbol_scope === "account" &&
    grant.all_actions &&
    grant.duration === "until_stopped" &&
    grant.allow_manual_positions
  );
}

/** A grant card's stored choice: Custom unless the server's draft says Full. */
function grantDelegation(card: OwnerAction): GrantDelegation {
  return card.facts.grant?.delegation === "full" ? "full" : "custom";
}

/** What selecting a choice option sends at once (the card's stored draft changes on the
 * server and nothing is signed); null for any other option. */
export function ownerActionChoose(option: OwnerActionOption): OwnerActionDecision | null {
  return option.choice ? { decision: "choose", delegation: option.choice.value } : null;
}

/** What a grant card's switches send: the passkey challenge carries the choice the card
 * shows (the server refuses it if the stored choice changed meanwhile) and the owner's
 * own positions switch under Custom (it is signed; Full always includes them); the
 * decision carries the rest. */
export function ownerActionChoices(
  card: OwnerAction,
  chosen: Readonly<Record<string, boolean>>,
): { challenge: OwnerActionChallenge; decision: Partial<OwnerActionDecision> } {
  if (card.kind !== "grant_authority") return { challenge: {}, decision: {} };
  const options = grantCard(card, "en", "en", new Date()).options;
  // Only switches the card shows now count: one ticked under Custom says nothing after
  // the owner chose Full delegation, which has no daily loss line to opt out of.
  const value = (key: string, initial: boolean) =>
    options.some((item) => item.key === key) && (chosen[key] ?? initial);
  const initial = (key: string) => options.find((item) => item.key === key)?.initial ?? false;
  const decision: Partial<OwnerActionDecision> = {
    // Either opt-out leaves the account's daily loss limit exactly as it is.
    money_limit: value("no_money_limit", false) || value("keep_limit", false) ? "none" : "apply",
    resume_trading: options.some((item) => item.key === "resume")
      ? value("resume", initial("resume"))
      : false,
    stop_authorities: options
      .filter((item) => item.key.startsWith("stop:") && value(item.key, false))
      .map((item) => item.key.slice("stop:".length)),
  };
  return {
    challenge:
      grantDelegation(card) === "full"
        ? { delegation: "full" }
        : { delegation: "custom", allow_manual_positions: value("manual", initial("manual")) },
    decision,
  };
}

const TEMPLATE_LABEL = {
  trading: "templateTrading",
  general: "templateGeneral",
  research: "templateResearch",
  supervisor: "templateSupervisor",
} as const;

/** Agent names, each isolated, joined with the language's list comma. */
function nameList(names: string[], lang: Language): string {
  return names.map(isolate).join(listSeparator(lang));
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
  // A server with a blocked tool runs only its reading tools, so no write is listed.
  if (source.writes?.length && !source.blocked?.length)
    lines.push(`${text.trustWrites}: ${nameList(source.writes, lang)}`);
  if (source.blocked?.length) lines.push(`${text.trustBlocked}: ${nameList(source.blocked, lang)}`);
  if (source.subscribe) lines.push(text.trustSubscribe);
  return lines;
}

function connectTitle(
  target: CredentialTarget,
  service: "x" | null | undefined,
  text: OwnerActionText,
): string {
  if (service === "x") return text.connectX;
  return {
    mcp_server: text.connectMcp,
    news_feed: text.connectFeed,
    brave_search: text.connectBrave,
    economic_calendar: text.connectCalendar,
    broker: text.connectBroker,
    model_provider: text.connectModel,
  }[target];
}

/** A Secret card's form: the agent's own labels, or ours for a connecting card's role. */
function secretForm(
  secret: NonNullable<OwnerAction["facts"]["secret"]>,
  text: OwnerActionText,
): SecretForm {
  const roles = {
    token: text.fieldToken,
    api_key: text.fieldApiKey,
    feed_url: text.fieldFeedUrl,
    metaapi_token: text.fieldBrokerToken,
  };
  return {
    fields: secret.fields.map((field) => ({
      key: field.key,
      label: field.label ?? (field.role ? roles[field.role] : field.key),
      type: field.secret ? "password" : field.role === "feed_url" ? "url" : "text",
      required: field.required ?? true,
    })),
    submit: secret.connect ? text.connect : text.secretSave,
  };
}

/**
 * Save a Secret card: the owner's values go to the card's own route, which stores them
 * encrypted and settles the card in one transaction; it answers with the card as saved.
 */
export async function submitSecret<Card>(
  post: (path: string, body: unknown) => Promise<Card>,
  cardId: string,
  values: Record<string, string>,
): Promise<Card> {
  return post(`/owner-actions/${encodeURIComponent(cardId)}/secret`, { values });
}

/** What the agent may do with money, by its level now (a grant may be signed later). */
function authorityHint(level: OwnerActionAgent["level"], text: OwnerActionText): string {
  if (level === "autonomous") return text.createdGrantHint;
  if (level === "analysis") return text.noTradeHint;
  return text.askHint;
}

/** The whole card for one locale: title, fact lines, hint, buttons and settled line. */
export function ownerActionCard(
  card: OwnerAction,
  locale: string,
  now: Date = new Date(),
): OwnerActionSpec {
  if (card.kind === "agent_model" || card.kind === "agent_model_changed") {
    // A model card (W15-10): one tap, never a passkey, nothing financial.
    const model = modelCard(card, locale);
    return {
      title: model.title,
      lines: model.lines,
      hint: model.hint,
      options: [],
      buttons: model.buttons.map((item) => ({ ...item, decision: item.key })),
      notes: false,
      secret: null,
      passkey: false,
      outcome: model.outcome,
    };
  }
  const lang = language(locale);
  const text = ownerActionLabels[lang];
  const facts = card.facts;
  const account = facts.several_accounts ? accountLabel(facts.account, text) : null;
  const lines: string[] = [];
  let title: string = text.resumeTitle;
  let hint: string | null = null;
  let buttons: OwnerActionButton[] = [];
  let options: OwnerActionOption[] = [];
  let form: SecretForm | null = null;
  const pair = (confirm: string, cancel: string): OwnerActionButton[] => [
    { key: "confirm", label: confirm, decision: "confirm", primary: true },
    { key: "cancel", label: cancel, decision: "cancel", primary: false },
  ];
  switch (card.kind) {
    case "grant_authority": {
      const grant = grantCard(card, locale, lang, now);
      title = grant.title;
      lines.push(...grant.lines);
      hint = grant.hint;
      buttons = grant.buttons;
      options = grant.options;
      break;
    }
    case "resume_trading": {
      const trading = facts.global_trading;
      // Never started on this install: the card says Start, as the safety sheet does.
      const start = trading?.changed_by === "default";
      if (start) title = text.startTitle;
      if (trading?.state === "stopped")
        lines.push(
          start
            ? text.startStopped
            : trading.since
              ? `${text.resumeStopped} · ${tradingSafetyLabels[lang].since} ${readinessTime(trading.since, locale, now)}`
              : text.resumeStopped,
        );
      hint = start ? text.startHint : text.resumeHint;
      buttons = pair(start ? text.start : text.resume, text.notNow);
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
    case "watch_changed": {
      title = text.watchChangedTitle;
      const watch = facts.watch;
      if (watch) {
        const end = (value: string | null) =>
          value ? `${text.until} ${readinessTime(value, locale, now)}` : text.watchNoEnd;
        lines.push(
          [
            ...(watch.symbol ? [isolate(watch.symbol)] : []),
            `${end(watch.previous_expires_at)} ${arrow(lang)} ${end(watch.expires_at)}`,
          ].join(" · "),
        );
      }
      if (!watch?.active) {
        // Changed again or removed since: the notice can only be dismissed.
        hint = watch ? text.watchChangedAgain : text.watchRemoved;
        buttons = [{ key: "cancel", label: text.keep, decision: "cancel", primary: false }];
        break;
      }
      hint = text.watchChangedHint;
      buttons = [
        { key: "confirm", label: text.undo, decision: "confirm", primary: false },
        { key: "cancel", label: text.keep, decision: "cancel", primary: false },
      ];
      break;
    }
    case "stop_tightened": {
      // A notice only (Q31): recorded settled, nothing to tap.
      title = text.stopTightenedTitle;
      const stop = facts.stop;
      if (stop)
        lines.push(
          `${isolate(stop.symbol)} · ${text.stopLoss}: ${
            stop.previous_stop_loss ? isolate(stop.previous_stop_loss) : text.notSet
          } ${arrow(lang)} ${isolate(stop.stop_loss)}`,
        );
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
      if (source?.kind === "mcp_server" && (!source.writes?.length || source.blocked?.length)) {
        // Every tool only reads, or the server offers a tool that can trade or move money
        // (then only its reading tools may run): one tap, nothing to choose.
        hint = source.blocked?.length ? text.trustServerBlockedHint : text.trustServerReadHint;
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
    case "secret": {
      const secret = facts.secret;
      title = secret?.connect
        ? connectTitle(secret.connect, secret.service, text)
        : text.secretTitle;
      if (secret) {
        // The label, field labels and details are the agent's words; every other word is ours.
        if (secret.label) lines.push(isolate(secret.label));
        const details = secret.details ?? {};
        if (details.name && secret.connect !== "brave_search")
          lines.push(`${text.fieldName}: ${isolate(details.name)}`);
        if (details.url) lines.push(`${text.fieldServerUrl}: ${isolate(details.url)}`);
        if (details.metaapi_account_id)
          lines.push(`${text.fieldAccount}: ${isolate(details.metaapi_account_id)}`);
        if (secret.agent_name)
          lines.push(fill(text.secretAskedBy, { agent: isolate(secret.agent_name) }));
        // Where each value goes, and the saved values it would replace: never silently.
        if (secret.saves_as?.length)
          lines.push(fill(text.secretSavesAs, { names: nameList(secret.saves_as, lang) }));
        if (secret.replaces?.length)
          lines.push(fill(text.secretReplaces, { names: nameList(secret.replaces, lang) }));
        hint =
          secret.connect === "model_provider"
            ? details.url
              ? `${text.modelHint} ${text.modelEndpointHint}`
              : text.modelHint
            : secret.destination === "broker"
              ? text.secretBroker
              : !secret.connect
                ? text.secretWorkspace
                : secret.service === "x"
                  ? `${text.connectHint} ${text.connectXHint}`
                  : text.connectHint;
        form = secretForm(secret, text);
      }
      // Save is the form's own submit: the values go to the card's route, never here.
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
    options: pending ? options : [],
    buttons: pending ? buttons : [],
    notes: pending && card.kind === "resolve_operation",
    secret: pending ? form : null,
    passkey: pending && card.requires_passkey,
    outcome: settledLine(card, text, lang),
  };
}

/** A refusal that means the card changed on another screen (a grant card's choice): the
 * client reads the card again so it shows what the passkey would sign now. */
export const OWNER_ACTION_CHANGED = "owner_action_card_changed";

/** The card as the server reads it now (null when it is gone), through the same list
 * route Web and Mobile already read their conversation's cards from. */
export async function rereadOwnerAction(
  get: (path: string) => Promise<OwnerAction[]>,
  row: OwnerAction,
): Promise<OwnerAction | null> {
  if (!row.thread_id) return null;
  const rows = await get(`/owner-actions?thread_id=${encodeURIComponent(row.thread_id)}`);
  return rows.find((item) => item.id === row.id) ?? null;
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
  allowed_models_full: {
    en: "You already allow the most models. Remove one in Model settings first.",
    ar: "سمحت بأقصى عدد من النماذج. أزل واحدًا من إعدادات النماذج أولًا.",
  },
  owner_action_not_needed_grant_already_active: {
    en: "This is already signed.",
    ar: "هذا موقّع بالفعل.",
  },
  owner_action_full_delegation_unavailable: {
    en: "Full delegation covers every pair on the account; this agent trades only its own pair. Use Custom.",
    ar: "التفويض الكامل يشمل كل أزواج الحساب، وهذا الوكيل يتداول زوجه فقط. استخدم مخصص.",
  },
  owner_action_full_delegation_terms_fixed: {
    en: "Full delegation always includes positions you opened yourself. Choose Custom to exclude them.",
    ar: "التفويض الكامل يشمل دائمًا المراكز التي فتحتها بنفسك. اختر مخصص لاستثنائها.",
  },
  owner_action_delegation_required: {
    en: "Choose Custom or Full delegation.",
    ar: "اختر مخصص أو تفويض كامل.",
  },
  owner_action_card_changed: {
    en: "This card changed on another screen. It now shows the current choice; check it and tap again.",
    ar: "تغيّرت هذه البطاقة من شاشة أخرى، وهي تعرض الآن الاختيار الحالي؛ راجعها ثم اضغط مجددًا.",
  },
  owner_action_choice_unsupported: {
    en: "This card has no such choice.",
    ar: "لا يوجد هذا الخيار في هذه البطاقة.",
  },
  execution_policy_passkey_required: {
    en: "Raising or removing a money limit needs your passkey.",
    ar: "رفع حد مالي أو إزالته يحتاج مفتاح المرور.",
  },
  execution_policy_passkey_not_needed: {
    en: "This change allows no more risk, so it needs no passkey.",
    ar: "هذا التغيير لا يسمح بمخاطرة أكبر، فلا يحتاج مفتاح المرور.",
  },
  owner_action_tier_required: {
    en: "Choose what its tools may do.",
    ar: "اختر ما يُسمح لأدواته بفعله.",
  },
  trusted_source_write_blocked: {
    en: "This server offers tools that look like they trade or move money, so only its reading tools can run.",
    ar: "يقدّم هذا الخادم أدوات يبدو أنها تتداول أو تحرّك المال، فلا تعمل إلا أدواته التي تقرأ.",
  },
  owner_action_secret_values_invalid: {
    en: "Fill in every required field.",
    ar: "املأ كل حقل مطلوب.",
  },
  owner_action_not_renewable: {
    en: "This card can no longer be asked again. Nothing changed.",
    ar: "لم يعد ممكنًا طلب هذه البطاقة من جديد. لم يتغير شيء.",
  },
  owner_action_pause_unsupported: {
    en: "This card cannot pause new trades.",
    ar: "لا تستطيع هذه البطاقة إيقاف الصفقات الجديدة.",
  },
  trade_approval_expired: {
    en: "This request expired. Ask for a new one.",
    ar: "انتهت مدة هذا الطلب. اطلب طلبًا جديدًا.",
  },
  trade_approval_not_renewable: {
    en: "This request is still waiting or was already answered.",
    ar: "هذا الطلب ما زال بانتظارك أو سبقت الإجابة عليه.",
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

// The notices whose «تراجع» is their confirm decision; the others (stop_tightened) are records.
const UNDOABLE_NOTICES = new Set<string>([
  "agent_model_changed",
  "agent_created",
  "supervision_created",
  "watch_changed",
]);

/** A settled notice reads «تم التراجع» only when its confirm was the owner's Undo (Q31); a
    settled stop_tightened record was applied, never undone. */
export function noticeUndone(card: Pick<OwnerAction, "kind" | "status">): boolean {
  return card.status === "confirmed" && UNDOABLE_NOTICES.has(card.kind);
}
