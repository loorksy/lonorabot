/**
 * The Capabilities view, one shared text table for Web and Mobile (GET /capabilities).
 * Lines are built only from server facts; names, domains and repositories are isolated
 * so they keep their order inside Arabic text. Nothing here decides anything.
 */
import type {
  BuiltInCapability,
  CapabilityIntegration,
  CapabilityServer,
  CapabilitySkill,
  TrustedSource,
} from "@lonora/contracts";
import { isolate } from "./trading-readiness";

type Language = "ar" | "en";

function language(locale: string): Language {
  return locale.startsWith("ar") ? "ar" : "en";
}

export const capabilityLabels = {
  en: {
    title: "Capabilities",
    intro:
      "Everything your agents can use now. Inside your trusted sources they install and use things without asking; money moves only inside the grants you signed.",
    trustedSources: "Trusted sources",
    skills: "Skills",
    servers: "MCP servers",
    integrations: "Integrations and feeds",
    builtIn: "Built in",
    none: "None yet.",
    github: "All public GitHub repositories",
    github_owner: "GitHub publisher",
    github_repo: "GitHub repository",
    mcp_server: "MCP server",
    feed_domain: "News feed site",
    default: "trusted by default",
    operator: "declared by the server operator",
    owner_ui: "added by you",
    owner_card: "added from your card",
    read: "read only",
    write_nonfinancial: "non-financial writes",
    ready: "Ready",
    not_connected: "Not connected",
    not_set_up: "Not set up on this server",
    web_search: "Web search",
    web_fetch: "Reading web pages",
    web_browse: "Browsing pages",
    news_feeds: "News and RSS feeds",
    economic_calendar: "Economic calendar",
    workspace_files: "Workspace files",
    workspace_execution: "Running code in the sandbox",
    chart_images: "Chart images",
    mcp_tools: "MCP tools",
    brave_search: "Brave web search",
    news_feed: "News feed",
    telegram: "Telegram",
    webhook: "Signed webhook",
    external: "from",
    agent_authored: "written by its agent",
    owner: "yours",
    bundled: "built in",
    unverified: "unverified",
    tools: "tools",
    blocked: "blocked",
    lastUsed: "last used",
    removedState: "removed",
    on: "on",
    off: "off",
    notTrusted: "tools not trusted yet",
    deliversTo: "delivers to",
    remove: "Remove",
    restore: "Restore",
    undo: "Undo",
    review: "Review and trust",
    trust: "Trust",
    trustRead: "Trust: read only",
    trustWrite: "Trust: non-financial writes",
    neverMoney: "Tools that can trade or move money never run.",
    writes: "may change something (only with non-financial writes)",
    needWrites: "need non-financial writes",
    needsReview: "declaration removed, review it to keep using it",
    undone: "undone",
    setUp: "Set up integrations on the web",
    unnamed: "Unnamed",
  },
  ar: {
    title: "القدرات",
    intro:
      "كل ما يستطيع وكلاؤك استخدامه الآن. ضمن مصادرك الموثوقة يثبّتون ويستخدمون دون أن يسألوك؛ والمال لا يتحرك إلا ضمن التفويضات التي وقّعتها.",
    trustedSources: "المصادر الموثوقة",
    skills: "المهارات",
    servers: "خوادم MCP",
    integrations: "التكاملات والموجزات",
    builtIn: "مدمجة",
    none: "لا شيء بعد.",
    github: "كل المستودعات العامة على GitHub",
    github_owner: "ناشر على GitHub",
    github_repo: "مستودع على GitHub",
    mcp_server: "خادم MCP",
    feed_domain: "موقع موجز أخبار",
    default: "موثوق افتراضيًا",
    operator: "أعلنه مشغّل الخادم",
    owner_ui: "أضفته أنت",
    owner_card: "أُضيف من بطاقتك",
    read: "قراءة فقط",
    write_nonfinancial: "كتابة غير مالية",
    ready: "جاهز",
    not_connected: "غير مربوط",
    not_set_up: "غير مُعدّ على هذا الخادم",
    web_search: "البحث على الويب",
    web_fetch: "قراءة صفحات الويب",
    web_browse: "تصفح الصفحات",
    news_feeds: "موجزات الأخبار وRSS",
    economic_calendar: "التقويم الاقتصادي",
    workspace_files: "ملفات مساحة العمل",
    workspace_execution: "تشغيل الشيفرة في البيئة المعزولة",
    chart_images: "صور الرسوم البيانية",
    mcp_tools: "أدوات MCP",
    brave_search: "بحث Brave",
    news_feed: "موجز أخبار",
    telegram: "تيليجرام",
    webhook: "خطاف ويب موقّع",
    external: "من",
    agent_authored: "كتبها وكيلها",
    owner: "لك",
    bundled: "مدمجة",
    unverified: "غير موثّقة",
    tools: "أدوات",
    blocked: "محظورة",
    lastUsed: "آخر استخدام",
    removedState: "أُزيل",
    on: "تعمل",
    off: "متوقفة",
    notTrusted: "أدواته غير موثوقة بعد",
    deliversTo: "يوصل إلى",
    remove: "إزالة",
    restore: "استعادة",
    undo: "تراجع",
    review: "مراجعة ووثوق",
    trust: "ثقة",
    trustRead: "ثقة: قراءة فقط",
    trustWrite: "ثقة: كتابة غير مالية",
    neverMoney: "الأدوات التي تتداول أو تحرّك المال لا تعمل أبدًا.",
    writes: "قد تغيّر شيئًا (مع الكتابة غير المالية فقط)",
    needWrites: "تحتاج الكتابة غير المالية",
    needsReview: "أُزيل الإعلان، راجعه لتواصل استخدامه",
    undone: "تم التراجع",
    setUp: "إعداد التكاملات على الويب",
    unnamed: "بلا اسم",
  },
} as const satisfies Record<Language, Record<string, string>>;
export type CapabilityText = (typeof capabilityLabels)[Language];

export function capabilityText(locale: string): CapabilityText {
  return capabilityLabels[language(locale)];
}

function dot(parts: Array<string | null | undefined | false>): string {
  return parts.filter(Boolean).join(" · ");
}

function day(value: string | null, locale: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return isolate(
    date.toLocaleDateString(language(locale) === "ar" ? "ar" : "en", {
      day: "numeric",
      month: "short",
    }),
  );
}

/** How many trusted tools wait for the write tier while a server is trusted for reading. */
function waitingWrites(tier: string | null, writes: string[], text: CapabilityText) {
  return tier === "read" && writes.length
    ? `${isolate(String(writes.length))} ${text.needWrites}`
    : null;
}

/** One trusted source: what it is, who added it, its tier and when it was last used. */
export function sourceLine(source: TrustedSource, locale: string): string {
  const text = capabilityText(locale);
  const label =
    source.kind === "github" ? null : source.label ? isolate(source.label) : text.unnamed;
  const used = day(source.last_used_at, locale);
  const server = source.kind === "mcp_server";
  return dot([
    label ? `${text[source.kind]}: ${label}` : text[source.kind],
    text[source.added_via],
    server && source.needs_review ? text.needsReview : null,
    server && !source.needs_review ? text[source.effect_tier] : null,
    server && source.tools.length ? `${isolate(String(source.tools.length))} ${text.tools}` : null,
    server ? waitingWrites(source.effect_tier, source.write_tools, text) : null,
    used ? `${text.lastUsed} ${used}` : null,
    source.active ? null : text.removedState,
  ]);
}

export function skillLine(skill: CapabilitySkill, locale: string): string {
  const text = capabilityText(locale);
  const origin =
    skill.provenance === "external"
      ? `${text.external} ${skill.repository ? isolate(skill.repository) : "GitHub"}`
      : text[skill.provenance];
  return dot([
    isolate(skill.skill_id),
    skill.version ? isolate(skill.version) : null,
    skill.agent_name ? isolate(skill.agent_name) : null,
    origin,
    skill.undone ? text.undone : skill.enabled ? text.on : text.off,
  ]);
}

export function serverLine(server: CapabilityServer, locale: string): string {
  const text = capabilityText(locale);
  const used = day(server.last_used_at, locale);
  return dot([
    server.name ? isolate(server.name) : text.unnamed,
    server.trusted_tier
      ? `${text[server.trusted_tier]} · ${isolate(String(server.trusted_tools.length))} ${text.tools}`
      : server.operator_declared
        ? text.operator
        : text.notTrusted,
    waitingWrites(server.trusted_tier, server.write_tools, text),
    server.blocked_tools.length
      ? `${isolate(String(server.blocked_tools.length))} ${text.blocked}`
      : null,
    server.enabled ? text.on : text.off,
    used ? `${text.lastUsed} ${used}` : null,
  ]);
}

export function integrationLine(item: CapabilityIntegration, locale: string): string {
  const text = capabilityText(locale);
  return dot([
    text[item.type],
    item.name ? isolate(item.name) : null,
    item.domain ? isolate(item.domain) : null,
    item.deliver_to_agent_name ? `${text.deliversTo} ${isolate(item.deliver_to_agent_name)}` : null,
    item.enabled ? text.on : text.off,
  ]);
}

export function builtInLine(item: BuiltInCapability, locale: string): string {
  const text = capabilityText(locale);
  return `${text[item.capability]}: ${text[item.state]}`;
}
