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
  GrantDelegation,
  OwnerAction,
  OwnerActionAccount,
  OwnerActionChallenge,
  OwnerActionDecision,
  TradingMode,
} from "@lonora/contracts";
import { tradeActionLabels } from "./trade-action-labels";
import { isolate, listSeparator, readinessTime } from "./trading-readiness";

type Language = "ar" | "en";

function language(locale: string): Language {
  return locale.startsWith("ar") ? "ar" : "en";
}

export const ownerActionLabels = {
  en: {
    mandateTitle: "Trading mode",
    mandateNow: "Now",
    modeFull: "Full",
    modeAsk: "Ask",
    modeFullLine: "Trades on its own and reports afterwards.",
    modeAskLine:
      "Every trade that adds risk waits for your approval; closing and tightening a stop do not.",
    modeAskClause: "Every trade that adds risk waits for your approval",
    modeFullClause: "It trades on its own and reports afterwards",
    unresolvedOne: "One unconfirmed operation is waiting for you",
    unresolvedMany: "{n} unconfirmed operations are waiting for you",
    withdrawnOne: "one approval request withdrawn",
    withdrawnTwo: "two approval requests withdrawn",
    withdrawnMany: "{n} approval requests withdrawn",
    mandateToFull: "Full lets it trade on its own. You can switch it back here at any time.",
    mandateToAsk: "Ask makes every trade that adds risk wait for your approval.",
    mandateGrantStays:
      "Its signed grant still lets it trade within the grant's terms until you revoke it.",
    mandatePreviousGrant: "Its earlier signed grant ({grant}) has ended; this card replaces it.",
    mandatePreviousGrants:
      "Its earlier signed grants ({grants}) have ended; this card replaces them.",
    mandatePreviousFull: "Full delegation",
    mandatePreviousAllPairs: "every pair on the account",
    mandateGone: "This agent no longer exists.",
    notNow: "Not now",
    keep: "Keep it",
    until: "until",
    fromYourMessage: "from your message",
    anAgent: "an agent",
    settleKind: "Unconfirmed operation",
    resolveTitle: "The broker did not confirm this trade",
    // The hold the server keeps (admission: an unresolved operation holds new risk on its
    // market), in the safety capsule's own words (trading-readiness).
    resolveHint:
      "It will not be sent again. New risk on this market is held until it settles; exits stay allowed.",
    resolveRecord: "Your answer is recorded as your statement, not as broker confirmation.",
    executed: "It executed",
    notExecuted: "It did not execute",
    unknown: "Unknown",
    byYou: "your order",
    by: "by",
    at: "at",
    account: "Account",
    simulation: "Simulation",
    brokerAccount: "Broker account",
    recordedExecuted: "Recorded: it executed (your statement, not broker confirmation).",
    recordedNotExecuted: "Recorded: it did not execute (your statement, not broker confirmation).",
    recordedUnknown:
      "Recorded: the outcome stays unknown and the broker is still checked. It will not be sent again.",
    cancelled: "Dismissed. Nothing changed.",
    expired: "This card expired. Nothing changed.",
    alreadyEnded: "This pause already ended. Nothing changed.",
    alreadySettled: "This operation is already settled. Nothing changed.",
    doneElsewhere: "Done from another card.",
    sameOnAnotherCard: "The same grant waits on another card. Nothing changed.",
    noLongerApplies: "This no longer applies. Nothing changed.",
    passkeyUnsupported:
      "Passkey signing is unavailable here. Open Lonora in a supported browser or the app.",
    registerDevice: "Register this device first",
    deviceName: "My device",
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
    conflict: "{agent} already trades {markets} here on its own. Keeping both is fine.",
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
      "Custom: only the markets, actions and time shown here; positions you opened yourself only if you switch them on.",
    fullMeaning:
      "Full delegation: every pair on this account and every action (open, close fully or partly, pending orders, change stop loss and take profit, cancel), positions you opened yourself too, until you stop it.",
    grantHint:
      "Confirm with your passkey. Anything outside this grant still comes to you as an approval card.",
    oneRule:
      "Every agent can see and use everything you have connected to Lonora, but it places real trades only inside the grant you signed for it with your passkey. Anything that needs you arrives as a one-tap card in the chat, you can stop anything with one tap, and no agent, skill or plugin can ever widen your money authority.",
    authorize: "Authorize with passkey",
    signed: "Signed. It trades on its own inside this grant.",
    alreadySigned: "This is already signed. Nothing changed.",
    agent: "Agent",
    agentRemoved: "This agent was already removed.",
    connectionChanged: "The broker account changed. Nothing changed.",
    pauseTitle: "Work paused",
    pausedBy: "Paused by",
    pausedWhat: "What",
    targetAgent: "The whole agent",
    targetRoutine: "Routine",
    targetWatch: "Watch",
    targetTask: "Task",
    pauseHint: "The agent cannot resume it on its own. Resume lifts the pause now.",
    pauseOwnerHolds: "This pause is yours: only you resume it.",
    pauseOwnerAsked:
      "You asked for this pause: it stays until you resume it, or an agent resumes it acting on your message in chat.",
    pauseEnded: "This pause already ended.",
    resumeWork: "Resume",
    keepPaused: "Keep paused",
    resumedWork: "Resumed.",
    keptPaused: "Kept paused.",
    watchExpired: "This watch is past its expiry: move its expiry in the watch list to resume it.",
    connectMcp: "Connect an MCP server",
    connectX: "Connect X",
    connectFeed: "Add a news feed",
    connectBrave: "Connect Brave web search",
    connectCalendar: "Connect an economic calendar",
    connectBroker: "Connect a broker account",
    connectModel: "Connect a model provider",
    modelHint:
      "The key is stored encrypted on your Lonora server and never enters the chat. Your models use it, and so do workspace commands that ask for it.",
    modelEndpointHint: "It is sent to the address you type, with every request.",
    connectHint:
      "What you type is saved encrypted on the server. It never enters the chat, and no agent sees it.",
    connectXHint:
      "Lonora reads X through web search, news feeds or an X MCP server you trust; it never uses your X account.",
    fieldName: "Name",
    fieldServerUrl: "Server URL",
    fieldFeedUrl: "Feed URL",
    fieldToken: "Access token (optional)",
    fieldApiKey: "API key",
    connect: "Connect",
    connected: "Connected. No agent sees what you typed.",
    alreadyConnected: "This is already connected. Nothing changed.",
    secretNameInUse: "A connection uses one of these names, so nothing was saved.",
    secretTitle: "Secret",
    secretAskedBy: "Asked by {agent}",
    secretWorkspace:
      "Saved encrypted for your workspace. What you type never enters the chat, and no agent sees it.",
    secretBroker:
      "Saved encrypted for your broker connection only. It never enters the chat or the workspace, and no agent sees it.",
    secretSave: "Save",
    secretSaved: "Saved encrypted. No agent sees the values.",
    secretSavesAs: "Saves: {fields}",
    secretReplaces: "Replaces what was saved before: {fields}",
    brokerConnectTitle: "Connect trading account",
    brokerRotateTitle: "New trading password",
    brokerTokenNew: "New MetaApi API token",
    brokerTokenTitle: "New MetaApi API token",
    brokerAccountLine: "Account {login} on server {server} ({platform})",
    brokerMoveLine: "Moves this connection from server {from} to {server}",
    brokerPassword: "Trading (master) password",
    brokerToken: "MetaApi API token (asked once)",
    brokerSaved: "Saved encrypted. Waiting for the broker login; Lonora will report the outcome.",
    brokerSending: "Saved encrypted. Lonora is sending it to MetaApi and will say what changed.",
    brokerConnected: "Connected. Lonora reported its balance in the conversation.",
    brokerLinked:
      "Saved; no balance could be read when Lonora checked. Lonora said in the conversation what it saw.",
    brokerChanged: "Saved and sent to MetaApi. Lonora said in the conversation what changed.",
    brokerFailed: "Could not connect. Lonora said why in the conversation.",
    deviceOnce: "A one-time step; after it, authorisations are signed with this device's passkey.",
    statusPending: "Waiting for your decision",
    statusConfirmed: "Done",
    statusCancelled: "Cancelled",
    statusExpired: "Expired",
    statusSuperseded: "Replaced",
    renew: "New request",
    latest: "Show the latest",
  },
  ar: {
    mandateTitle: "التفويض",
    mandateNow: "الآن",
    modeFull: "وكّله",
    modeAsk: "يستأذن",
    modeFullLine: "يتداول بنفسه ويخبرك بعد التنفيذ.",
    modeAskLine: "كل صفقة تزيد المخاطرة تنتظر موافقتك، أما الإغلاق وتشديد الوقف فلا ينتظران.",
    modeAskClause: "كل صفقة تزيد المخاطرة تنتظر موافقتك",
    modeFullClause: "يتداول بنفسه ويخبرك بعد التنفيذ",
    unresolvedOne: "عملية غير مؤكدة بانتظارك",
    unresolvedMany: "{n} عمليات غير مؤكدة بانتظارك",
    withdrawnOne: "سُحب طلب موافقة واحد",
    withdrawnTwo: "سُحب طلبا موافقة",
    withdrawnMany: "سُحب {n} طلبات موافقة",
    mandateToFull: "«وكّله» يتيح له التداول بنفسه، ويمكنك إعادته من هنا في أي وقت.",
    mandateToAsk: "«يستأذن» يجعل كل صفقة تزيد المخاطرة تنتظر موافقتك.",
    mandateGrantStays: "صلاحيته الموقّعة تبقى سارية ضمن شروطها حتى تلغيها.",
    mandatePreviousGrant: "انتهت صلاحيته الموقّعة السابقة ({grant})، وهذه البطاقة تحلّ محلّها.",
    mandatePreviousGrants: "انتهت صلاحياته الموقّعة السابقة ({grants})، وهذه البطاقة تحلّ محلّها.",
    mandatePreviousFull: "تفويض كامل",
    mandatePreviousAllPairs: "كل أزواج الحساب",
    mandateGone: "لم يعد هذا الوكيل موجودًا.",
    notNow: "ليس الآن",
    keep: "إبقاؤه",
    until: "حتى",
    fromYourMessage: "من رسالتك",
    anAgent: "وكيل",
    settleKind: "عملية غير مؤكَّدة",
    resolveTitle: "الوسيط لم يؤكد هذه الصفقة",
    resolveHint: "لن تُرسل مجددًا. المخاطرة الجديدة على هذا السوق معلّقة حتى تُحسم؛ يبقى الخروج متاحًا.",
    resolveRecord: "تُسجَّل إجابتك كتصريح منك، لا كتأكيد من الوسيط.",
    executed: "نُفذت",
    notExecuted: "لم تُنفذ",
    unknown: "غير معروفة",
    byYou: "أمرك",
    by: "من",
    at: "في",
    account: "الحساب",
    simulation: "محاكاة",
    brokerAccount: "حساب الوسيط",
    recordedExecuted: "سُجّل: نُفذت (تصريحك، لا تأكيد من الوسيط).",
    recordedNotExecuted: "سُجّل: لم تُنفذ (تصريحك، لا تأكيد من الوسيط).",
    recordedUnknown: "سُجّل: تبقى النتيجة غير معروفة ويُراجَع الوسيط، ولن تُرسل مجددًا.",
    cancelled: "تم التجاهل. لم يتغير شيء.",
    expired: "انتهت صلاحية هذه البطاقة. لم يتغير شيء.",
    alreadyEnded: "انتهى هذا الإيقاف مسبقًا. لم يتغير شيء.",
    alreadySettled: "حُسمت هذه العملية مسبقًا. لم يتغير شيء.",
    doneElsewhere: "نُفذ من بطاقة أخرى.",
    sameOnAnotherCard: "التفويض نفسه ينتظر في بطاقة أخرى. لم يتغير شيء.",
    noLongerApplies: "لم يعد هذا ساريًا. لم يتغير شيء.",
    passkeyUnsupported: "توقيع مفتاح المرور غير متاح هنا. افتح لونورا بمتصفح مدعوم أو التطبيق.",
    registerDevice: "سجّل هذا الجهاز أولًا",
    deviceName: "جهازي",
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
    conflict: "{agent} يتداول {markets} هنا بنفسه. لا بأس ببقائهما معًا.",
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
      "مخصص: الأسواق والعمليات والمدة الظاهرة هنا فقط؛ ولا تُشمل المراكز التي فتحتها بنفسك إلا إذا فعّلتها.",
    fullMeaning:
      "تفويض كامل: كل أزواج هذا الحساب وكل العمليات (الفتح، والإغلاق الكلي أو الجزئي، والأوامر المعلّقة، وتعديل وقف الخسارة وجني الربح، والإلغاء)، والمراكز التي فتحتها بنفسك أيضًا، حتى توقفه.",
    grantHint: "أكّد بمفتاح المرور. ما يخرج عن هذا التفويض يصلك كبطاقة موافقة.",
    oneRule:
      "كل وكيل يرى ويستخدم كل ما وصلته بلونورا، لكنه لا ينفّذ صفقة حقيقية إلا ضمن التفويض الذي وقّعته له بمفتاح المرور؛ وما يحتاجك يصلك كبطاقة في المحادثة بلمسة واحدة، وتستطيع إيقاف أي شيء بلمسة، ولا يستطيع أي وكيل أو مهارة أو إضافة توسيع صلاحياتك المالية.",
    authorize: "التفويض بمفتاح المرور",
    signed: "وُقّع. يتداول بنفسه ضمن هذا التفويض.",
    alreadySigned: "هذا موقّع بالفعل. لم يتغير شيء.",
    agent: "وكيل",
    agentRemoved: "أُزيل هذا الوكيل مسبقًا.",
    connectionChanged: "تغيّر حساب الوسيط. لم يتغير شيء.",
    pauseTitle: "عمل موقوف مؤقتًا",
    pausedBy: "أوقفه",
    pausedWhat: "ما أُوقف",
    targetAgent: "الوكيل كله",
    targetRoutine: "مهمة مجدولة",
    targetWatch: "مراقبة",
    targetTask: "مهمة",
    pauseHint: "لا يستطيع الوكيل استئنافه بنفسه. الاستئناف يرفع الإيقاف الآن.",
    pauseOwnerHolds: "هذا الإيقاف لك: لا يستأنفه غيرك.",
    pauseOwnerAsked:
      "طلبت هذا الإيقاف: يبقى حتى تستأنفه أنت، أو يستأنفه وكيل بناءً على رسالتك في المحادثة.",
    pauseEnded: "انتهى هذا الإيقاف مسبقًا.",
    resumeWork: "استئناف",
    keepPaused: "إبقاؤه موقوفًا",
    resumedWork: "تم الاستئناف.",
    keptPaused: "بقي موقوفًا.",
    watchExpired: "انتهت مدة هذه المراقبة: مدّد مدتها من قائمة المراقبات لاستئنافها.",
    connectMcp: "ربط خادم MCP",
    connectX: "ربط X",
    connectFeed: "إضافة موجز أخبار",
    connectBrave: "ربط بحث Brave",
    connectCalendar: "ربط تقويم اقتصادي",
    connectBroker: "ربط حساب وسيط",
    connectModel: "ربط مزوّد نماذج",
    modelHint:
      "يُحفظ المفتاح مشفّراً على خادم Lonora ولا يدخل المحادثة. تستخدمه نماذجك، والأوامر التي تطلبه في مساحة العمل.",
    modelEndpointHint: "ويُرسَل إلى العنوان الذي تكتبه مع كل طلب.",
    connectHint: "ما تكتبه يُحفظ مشفّرًا على الخادم. لا يدخل المحادثة، ولا يراه أي وكيل.",
    connectXHint:
      "تقرأ لونورا X عبر البحث على الويب أو موجزات الأخبار أو خادم MCP لـ X تثق به، ولا تستخدم حسابك على X أبدًا.",
    fieldName: "الاسم",
    fieldServerUrl: "عنوان الخادم",
    fieldFeedUrl: "عنوان الموجز",
    fieldToken: "رمز الوصول (اختياري)",
    fieldApiKey: "مفتاح API",
    connect: "ربط",
    connected: "تم الربط. لا يرى أي وكيل ما كتبته.",
    alreadyConnected: "هذا مربوط مسبقًا. لم يتغير شيء.",
    secretNameInUse: "يستخدم اتصالٌ أحد هذه الأسماء، فلم يُحفظ شيء.",
    secretTitle: "بيانات سرّية",
    secretAskedBy: "يطلبها {agent}",
    secretWorkspace: "تُحفظ مشفّرة لمساحة العمل. ما تكتبه لا يدخل المحادثة، ولا يراه أي وكيل.",
    secretBroker:
      "تُحفظ مشفّرة لاتصال الوسيط فقط. لا تدخل المحادثة ولا مساحة العمل، ولا يراها أي وكيل.",
    secretSave: "حفظ",
    secretSaved: "حُفظت مشفّرة. لا يرى أي وكيل القيم.",
    secretSavesAs: "تُحفظ: {fields}",
    secretReplaces: "تحلّ محل ما حُفظ سابقًا: {fields}",
    brokerConnectTitle: "ربط حساب التداول",
    brokerRotateTitle: "كلمة مرور تداول جديدة",
    brokerTokenNew: "رمز MetaApi API الجديد",
    brokerTokenTitle: "رمز MetaApi API جديد",
    brokerAccountLine: "الحساب {login} على الخادم {server} ({platform})",
    brokerMoveLine: "ينقل هذا الربط من الخادم {from} إلى الخادم {server}",
    brokerPassword: "كلمة مرور التداول (الرئيسية)",
    brokerToken: "رمز MetaApi API (يُطلب مرة واحدة)",
    brokerSaved: "حُفظت مشفّرة. بانتظار تسجيل الدخول لدى الوسيط؛ ستبلغك لونورا بالنتيجة.",
    brokerSending: "حُفظت مشفّرة. ترسلها لونورا إلى MetaApi وستوضح ما تغيّر.",
    brokerConnected: "تم الربط. أبلغتك لونورا برصيده في المحادثة.",
    brokerLinked: "حُفظت؛ تعذّرت قراءة الرصيد عند التحقق. أوضحت لونورا في المحادثة ما رأته.",
    brokerChanged: "حُفظت وأُرسلت إلى MetaApi. أوضحت لونورا في المحادثة ما تغيّر.",
    brokerFailed: "تعذّر الربط. أوضحت لونورا السبب في المحادثة.",
    deviceOnce: "خطوة لمرة واحدة؛ بعدها تُوقَّع التفويضات بمفتاح المرور على هذا الجهاز.",
    statusPending: "بانتظار قرارك",
    statusConfirmed: "تم",
    statusCancelled: "أُلغي",
    statusExpired: "انتهت المهلة",
    statusSuperseded: "استُبدل",
    renew: "طلب جديد",
    latest: "عرض الأحدث",
  },
} as const satisfies Record<Language, Record<string, string>>;
export type OwnerActionText = (typeof ownerActionLabels)[Language];

export function ownerActionText(locale: string): OwnerActionText {
  return ownerActionLabels[language(locale)];
}

/** What a button sends: confirm (with an outcome for a resolve card) or cancel. */
export type OwnerActionButton = {
  key: "confirm" | "cancel" | AttestedOutcome | TradingMode;
  label: string;
  decision: "confirm" | "cancel";
  outcome?: AttestedOutcome;
  /** The Mandate card: the mode this button shows; the tap applies exactly this mode. */
  trading_mode?: TradingMode;
  primary: boolean;
};
/** An owner switch on a card (a grant card's own positions, a conflict); the client
 * keeps its state and ``ownerActionChoices`` sends it. An option
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
  /** A Secret card's form while it waits (submitted by the client itself). */
  secret: SecretForm | null;
  passkey: boolean;
  /** The settled line ("Signed. It trades on its own inside this grant.", "This card expired. Nothing changed."). */
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
  const labels = tradeActionLabels[lang] as Record<string, string>;
  return action ? (labels[action] ?? isolate(action)) : "";
}

/** A broker card's purpose (raised only by the broker tools); null for every other card,
 * a credential card converted by 0071 included. */
export function brokerPurpose(
  card: OwnerAction,
): NonNullable<NonNullable<OwnerAction["facts"]["secret"]>["purpose"]> | null {
  const secret = card.facts.secret;
  return secret?.destination === "broker" && !secret.connect ? (secret.purpose ?? "connect") : null;
}

/**
 * A saved broker card whose provisioning failed: its end state in the frame says so in the
 * neutral tint, never the success one.
 */
export function brokerCardFailed(card: OwnerAction): boolean {
  return (
    card.status === "confirmed" &&
    brokerPurpose(card) !== null &&
    card.result.provisioning === "failed"
  );
}

/**
 * The status beside a folded card's kind (DecisionLine). Only kinds outside the fixed cards
 * fold, so a Secret card, broker or not, never shows it: its frame says how it ended.
 */
export function ownerActionStatus(card: OwnerAction, locale: string): string {
  const text = ownerActionText(locale);
  return {
    pending: text.statusPending,
    confirmed: text.statusConfirmed,
    cancelled: text.statusCancelled,
    expired: text.statusExpired,
    superseded: text.statusSuperseded,
  }[card.status];
}

function settledLine(card: OwnerAction, text: OwnerActionText, _lang: Language): string | null {
  if (card.status === "pending") return null;
  if (card.status === "cancelled")
    return card.kind === "supervision_paused" ? text.keptPaused : text.cancelled;
  if (card.status === "confirmed") {
    switch (card.kind) {
      case "trading_mode":
        // Still the agent's switch: its lines show the mode now.
        return null;
      case "supervision_paused":
        return text.resumedWork;
      case "secret": {
        const purpose = brokerPurpose(card);
        if (purpose)
          // A broker card: the card's own record of how provisioning ended, read on the
          // server ("connected" only once the terminal answered a read; "linked" when it was
          // saved but no read answered). A new password or token waits for MetaApi, never
          // for a broker login. A credential card converted by 0071 says what it connected.
          return card.result.provisioning === "failed"
            ? text.brokerFailed
            : card.result.provisioning === "connected"
              ? purpose === "connect"
                ? text.brokerConnected
                : text.brokerChanged
              : card.result.provisioning === "linked"
                ? text.brokerLinked
                : purpose === "connect"
                  ? text.brokerSaved
                  : text.brokerSending;
        return card.facts.secret?.connect ? text.connected : text.secretSaved;
      }
      case "settle_operation":
        return card.result.outcome === "executed"
          ? text.recordedExecuted
          : card.result.outcome === "not_executed"
            ? text.recordedNotExecuted
            : text.recordedUnknown;
    }
  }
  switch (card.status_reason) {
    case "operation_already_settled":
      return text.alreadySettled;
    case "done_by_another_card":
      return text.doneElsewhere;
    case "same_choice_on_another_card":
      return text.sameOnAnotherCard;
    case "grant_already_active":
      return text.alreadySigned;
    case "agent_already_removed":
      return text.agentRemoved;
    case "broker_connection_changed":
      return text.connectionChanged;
    case "supervision_pause_ended":
      return text.alreadyEnded;
    case "watch_expired":
      return text.watchExpired;
    case "credential_already_configured":
      return text.alreadyConnected;
    case "secret_name_in_use":
      return text.secretNameInUse;
    case "expired":
      return text.expired;
    default:
      return card.status === "expired" ? text.expired : text.noLongerApplies;
  }
}

function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => values[key] ?? "");
}

/** «التفويض: يستأذن» / "Trading mode: Ask". Null when the agent has no mode. */
export function mandateLine(mode: string | null | undefined, locale: string): string | null {
  const text = ownerActionText(locale);
  if (mode === "full") return `${text.mandateTitle}: ${text.modeFull}`;
  if (mode === "ask") return `${text.mandateTitle}: ${text.modeAsk}`;
  return null;
}

/** The line under the mode: an unconfirmed operation, otherwise the mode's first clause. */
export function tradingSubLine(
  unresolved: number | null | undefined,
  mode: string | null | undefined,
  locale: string,
): string | null {
  const text = ownerActionText(locale);
  const count = unresolved ?? 0;
  if (count === 1) return text.unresolvedOne;
  if (count > 1)
    return fill(text.unresolvedMany, {
      n: language(locale) === "ar" ? isolate(String(count)) : String(count),
    });
  if (mode === "ask") return text.modeAskClause;
  if (mode === "full") return text.modeFullClause;
  return null;
}

/** The one line after a Mandate tap. The withdrawn count is the server's, and only for Full. */
export function modeChangeLine(
  name: string,
  mode: "ask" | "full",
  withdrawn: number,
  locale: string,
): string {
  const text = ownerActionText(locale);
  const head = `${name}: ${mode === "full" ? text.modeFull : text.modeAsk}`;
  if (mode !== "full" || !Number.isInteger(withdrawn) || withdrawn < 1) return head;
  const tail =
    withdrawn === 1
      ? text.withdrawnOne
      : withdrawn === 2
        ? text.withdrawnTwo
        : fill(text.withdrawnMany, {
            n: language(locale) === "ar" ? isolate(String(withdrawn)) : String(withdrawn),
          });
  return `${head} · ${tail}`;
}

/** What selecting a choice option sends at once (the card's stored draft changes on the
 * server and nothing is signed); null for any other option. */
export function ownerActionChoose(_option: OwnerActionOption): OwnerActionDecision | null {
  // No card chooses a grant. A choice option settles nothing.
  return null;
}

/** No remaining card sends a passkey challenge or a grant decision. */
export function ownerActionChoices(
  _card: OwnerAction,
  _chosen: Readonly<Record<string, boolean>>,
): { challenge: OwnerActionChallenge; decision: Partial<OwnerActionDecision> } {
  return { challenge: {}, decision: {} };
}

/** Agent names, each isolated, joined with the language's list comma. */
function nameList(names: string[], lang: Language): string {
  return names.map(isolate).join(listSeparator(lang));
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
    server_url: text.fieldServerUrl,
    feed_url: text.fieldFeedUrl,
  };
  return {
    fields: secret.fields.map((field) => ({
      key: field.key,
      label: field.label ?? (field.role ? roles[field.role] : field.key),
      type: field.secret
        ? "password"
        : field.role === "feed_url" || field.role === "server_url"
          ? "url"
          : "text",
      required: field.required ?? true,
    })),
    submit: secret.connect ? text.connect : text.secretSave,
  };
}

/**
 * The labels of the fields a Secret card saves under these workspace names: the agent's card
 * saves each field under its own key, a model provider's card its key under the provider's
 * name, and a connecting card its fields in order. Never the names themselves (17).
 */
function savedLabels(
  secret: NonNullable<OwnerAction["facts"]["secret"]>,
  fields: SecretForm["fields"],
  names: string[],
): string[] {
  return names.flatMap((name, index) => {
    const field =
      secret.connect === "model_provider"
        ? fields[secret.fields.findIndex((item) => item.role === "api_key")]
        : secret.connect
          ? fields[index]
          : fields.find((item) => item.key === name);
    return field ? [field.label] : [];
  });
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
  let title = "";
  let hint: string | null = null;
  let buttons: OwnerActionButton[] = [];
  const options: OwnerActionOption[] = [];
  let form: SecretForm | null = null;
  const pair = (confirm: string, cancel: string): OwnerActionButton[] => [
    { key: "confirm", label: confirm, decision: "confirm", primary: true },
    { key: "cancel", label: cancel, decision: "cancel", primary: false },
  ];
  switch (card.kind) {
    case "trading_mode": {
      title = text.mandateTitle;
      const mode = facts.trading_mode;
      if (!facts.agent?.exists || !mode) {
        lines.push(text.mandateGone);
        break;
      }
      const name = facts.agent.name ? `${isolate(facts.agent.name)} · ` : "";
      lines.push(`${name}${text.mandateNow}: ${mode === "full" ? text.modeFull : text.modeAsk}`);
      lines.push(mode === "full" ? text.modeFullLine : text.modeAskLine);
      if (facts.active_grant) lines.push(text.mandateGrantStays);
      // The grants it held before the trading mode, named once by the migration.
      if (facts.previous_grants?.length) {
        const grants = facts.previous_grants.map((grant) =>
          [
            grant.full_delegation
              ? text.mandatePreviousFull
              : grant.symbol_scope === "account"
                ? text.mandatePreviousAllPairs
                : grant.symbols.map(isolate).join(listSeparator(lang)),
            facts.several_accounts ? accountLabel(grant.account, text) : null,
          ]
            .filter(Boolean)
            .join(" · "),
        );
        // Several grants: the plural line, and a semicolon between grants, since a comma
        // already separates the markets inside one.
        lines.push(
          grants.length > 1
            ? fill(text.mandatePreviousGrants, { grants: grants.join(lang === "ar" ? "؛ " : "; ") })
            : fill(text.mandatePreviousGrant, { grant: grants[0] ?? "" }),
        );
      }
      // One button for the other mode; the tap applies the mode this button shows.
      const other: TradingMode = mode === "full" ? "ask" : "full";
      hint = other === "full" ? text.mandateToFull : text.mandateToAsk;
      buttons = [
        {
          key: other,
          label: other === "full" ? text.modeFull : text.modeAsk,
          decision: "confirm",
          trading_mode: other,
          primary: true,
        },
      ];
      break;
    }
    case "settle_operation": {
      title = text.settleKind;
      lines.push(text.resolveTitle);
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
      if (card.result.outcome === "unknown") {
        // Answered Unknown: still uncertain and held; Executed or Not executed remain.
        lines.push(text.recordedUnknown);
        buttons = buttons.filter((button) => button.outcome !== "unknown");
      }
      break;
    }
    case "supervision_paused": {
      title = text.pauseTitle;
      lines.push(...pauseLines(card, text));
      if (!card.facts.supervision?.active) {
        // Resumed elsewhere (Lonora, the owner): the card can only be dismissed.
        hint = text.pauseEnded;
        buttons = [{ key: "cancel", label: text.keep, decision: "cancel", primary: false }];
        break;
      }
      // The owner's pause from a control is lifted only by the owner's control or this
      // card; one the owner asked for in chat also by an agent acting on the owner's
      // message in chat (refuse_held, control_work).
      hint = !card.facts.supervision.owner_holds
        ? text.pauseHint
        : card.facts.supervision.from_owner_message
          ? text.pauseOwnerAsked
          : text.pauseOwnerHolds;
      buttons = pair(text.resumeWork, text.keepPaused);
      break;
    }
    case "secret": {
      const secret = facts.secret;
      title = secret?.connect
        ? connectTitle(secret.connect, secret.service, text)
        : text.secretTitle;
      if (secret?.destination === "broker" && secret.account) {
        // Raised only by the broker tools: every word is ours, the account is server fact.
        const account = secret.account;
        title =
          secret.purpose === "rotate_password"
            ? text.brokerRotateTitle
            : secret.purpose === "replace_token"
              ? text.brokerTokenTitle
              : text.brokerConnectTitle;
        lines.push(
          fill(text.brokerAccountLine, {
            login: isolate(account.login),
            server: isolate(account.server),
            platform: account.platform.toUpperCase(),
          }),
        );
        if (secret.server_from)
          lines.push(
            fill(text.brokerMoveLine, {
              from: isolate(secret.server_from),
              server: isolate(account.server),
            }),
          );
        if (secret.agent_name)
          lines.push(fill(text.secretAskedBy, { agent: isolate(secret.agent_name) }));
        hint = text.secretBroker;
        form = {
          fields: secret.fields.map((field) => ({
            key: field.key,
            label:
              field.key !== "METAAPI_TOKEN"
                ? text.brokerPassword
                : secret.purpose === "replace_token"
                  ? text.brokerTokenNew
                  : text.brokerToken,
            type: "password",
            required: true,
          })),
          submit: text.secretSave,
        };
      } else if (secret) {
        // The label, field labels and details are the agent's words; every other word is ours.
        if (secret.label) lines.push(isolate(secret.label));
        const details = secret.details ?? {};
        if (details.name && secret.connect !== "brave_search")
          lines.push(`${text.fieldName}: ${isolate(details.name)}`);
        if (secret.agent_name)
          lines.push(fill(text.secretAskedBy, { agent: isolate(secret.agent_name) }));
        form = secretForm(secret, text);
        // What each value is saved as, and the saved values it would replace: never silently,
        // and by the field's label, never by the workspace name it is stored under (17).
        const saves = savedLabels(secret, form.fields, secret.saves_as ?? []);
        if (saves.length) lines.push(fill(text.secretSavesAs, { fields: nameList(saves, lang) }));
        const replaces = savedLabels(secret, form.fields, secret.replaces ?? []);
        if (replaces.length)
          lines.push(fill(text.secretReplaces, { fields: nameList(replaces, lang) }));
        hint =
          secret.connect === "model_provider"
            ? secret.fields.some((field) => field.role === "server_url")
              ? `${text.modelHint} ${text.modelEndpointHint}`
              : text.modelHint
            : secret.destination === "broker"
              ? text.secretBroker
              : !secret.connect
                ? text.secretWorkspace
                : secret.service === "x"
                  ? `${text.connectHint} ${text.connectXHint}`
                  : text.connectHint;
      }
      // Save is the form's own submit: the values go to the card's route, never here.
      buttons = [{ key: "cancel", label: text.notNow, decision: "cancel", primary: false }];
      break;
    }
  }
  const pending = ownerActionLive(card);
  return {
    title,
    lines,
    hint: pending ? hint : null,
    options: pending ? options : [],
    buttons: pending ? buttons : [],
    secret: pending ? form : null,
    passkey: pending && card.requires_passkey,
    outcome: settledLine(card, text, lang),
  };
}

/** Whether the card still offers its buttons: a pending card, or a Mandate card the owner
 * already tapped, which stays the agent's switch while the agent exists. */
export function ownerActionLive(card: OwnerAction): boolean {
  return (
    card.status === "pending" ||
    (card.kind === "trading_mode" && card.status === "confirmed" && !!card.facts.trading_mode)
  );
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
  trusted_source_write_blocked: {
    en: "This server offers tools that look like they trade or move money, so only its reading tools can run.",
    ar: "يقدّم هذا الخادم أدوات يبدو أنها تتداول أو تحرّك المال، فلا تعمل إلا أدواته التي تقرأ.",
  },
  owner_action_secret_values_invalid: {
    en: "Fill in every required field.",
    ar: "املأ كل حقل مطلوب.",
  },
  secret_value_too_short: {
    en: "Each value needs at least 3 characters. Nothing was saved.",
    ar: "تحتاج كل قيمة إلى 3 أحرف على الأقل. لم يُحفظ شيء.",
  },
  owner_action_secret_value_unsendable: {
    en: "A key or token has a character it cannot be sent with, such as a space or a hidden character from a paste. Type it again.",
    ar: "في مفتاح أو رمز حرفٌ لا يمكن إرساله، مثل مسافة أو حرف مخفي من النسخ. اكتبه من جديد.",
  },
  mcp_url_invalid: {
    en: "Enter the server's https:// address, without a user name or password in it.",
    ar: "أدخل عنوان الخادم الذي يبدأ بـ https://، دون اسم مستخدم أو كلمة مرور فيه.",
  },
  integration_source_invalid: {
    en: "Enter the calendar's https:// address, without a user name or password in it.",
    ar: "أدخل عنوان التقويم الذي يبدأ بـ https://، دون اسم مستخدم أو كلمة مرور فيه.",
  },
  owner_action_not_renewable: {
    en: "This card can no longer be asked again. Nothing changed.",
    ar: "لم يعد ممكنًا طلب هذه البطاقة من جديد. لم يتغير شيء.",
  },
  trade_approval_expired: {
    en: "This request expired. Ask for a new one.",
    ar: "انتهت مدة هذا الطلب. اطلب طلبًا جديدًا.",
  },
  trade_approval_quote_unavailable: {
    en: "The current price could not be read, so this request was not approved. Try again.",
    ar: "تعذّرت قراءة السعر الحالي، فلم تتم الموافقة على هذا الطلب. حاول مرة أخرى.",
  },
  trade_approval_drifted: {
    en: "The price moved outside this request's range, so it can no longer be approved.",
    ar: "خرج السعر عن نطاق هذا الطلب، فلم يعد قابلًا للموافقة.",
  },
  trade_approval_agent_paused: {
    en: "This agent is paused, so this request cannot be approved now. Resume the agent first.",
    ar: "هذا الوكيل متوقف مؤقتًا، فلا يمكن الموافقة على هذا الطلب الآن. استأنف الوكيل أولًا.",
  },
  trade_approval_not_renewable: {
    en: "This request is still waiting or was already answered.",
    ar: "هذا الطلب ما زال بانتظارك أو سبقت الإجابة عليه.",
  },
  trade_approval_already_decided: {
    en: "This request was already answered.",
    ar: "سبقت الإجابة على هذا الطلب.",
  },
  trade_approval_run_unavailable: {
    en: "This request is no longer waiting for you. Nothing was sent.",
    ar: "لم يعد هذا الطلب بانتظارك. لم يُرسل شيء.",
  },
  trade_approval_not_found: {
    en: "This request no longer exists.",
    ar: "لم يعد هذا الطلب موجودًا.",
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
