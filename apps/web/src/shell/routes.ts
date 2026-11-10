/** The shell's route model: four root tabs, the two conversation routes and the inner pages. */
export const ROOTS = ["chats", "updates", "tasks", "settings"] as const;
export type Root = (typeof ROOTS)[number];
export const PAGES = [
  "agents",
  "agent",
  "identity",
  "trades",
  "group",
  "recovery",
  "artifacts",
  "archived",
  "market",
  "trading",
  "routines",
  "knowledge",
  "new-agent",
  "new-group",
  "owner",
  "lab",
  // Phase 5: settings pages (the reference's route names).
  "accessibility",
  "notify-settings",
  "communication",
  "integrations",
  "providers",
  "provider",
  "mcp",
  "broker",
  "broker-account",
  "usage",
  "usage-detail",
  "storage",
  "privacy",
] as const;
export type Page = (typeof PAGES)[number];
export type ShellRoute =
  | { kind: "root"; root: Root }
  | { kind: "chat"; agentId: string }
  | { kind: "group"; groupId: string }
  | { kind: "page"; page: Page; item?: string }
  | { kind: "alias"; to: string }
  | { kind: "not-found" };

/** Out of production: the lab (plans and the gallery arrive with their pages). */
export const DEV_ROUTES: ReadonlySet<Page> = new Set<Page>(["lab"]);
/** Old names that still reach their merged page (the reference's ROUTE_ALIAS, plus ours). */
const ALIASES: Readonly<Record<string, string>> = {
  board: "/app/tasks",
  activity: "/app/updates",
  notifications: "/app/updates",
  account: "/app/settings",
  capabilities: "/app/integrations",
  // Search lives in the chats header (phones) and the list pane (desktop).
  search: "/app",
};
/** Pages that take one item (`/app/<page>/<id>`): settings items, the agent page, its
 * identity form and trades, the group page. */
const ITEM_PAGES = new Set<string>([
  "artifacts",
  "communication",
  "broker-account",
  "usage-detail",
  "provider",
  "agent",
  "identity",
  "trades",
  "group",
]);
/** The settings pages: the settings tab stays selected under them. */
const SETTINGS_PAGES = new Set<string>([
  "owner",
  "accessibility",
  "notify-settings",
  "communication",
  "integrations",
  "providers",
  "provider",
  "mcp",
  "broker",
  "broker-account",
  "usage",
  "usage-detail",
  "storage",
  "privacy",
]);
const rootNames = new Set<string>(ROOTS);
const pageNames = new Set<string>(PAGES);
const NEEDS_ITEM: ReadonlySet<string> = new Set(["agent", "identity", "trades", "group"]);

export const rootPath = (root: Root) => (root === "chats" ? "/app" : `/app/${root}`);

export function parseRoute(pathname: string): ShellRoute {
  const segments = pathname.split("/").filter(Boolean);
  if (segments[0] !== "app")
    return segments.length ? { kind: "not-found" } : { kind: "alias", to: "/app" };
  if (segments.length === 1) return { kind: "root", root: "chats" };
  const [, head, item, extra] = segments;
  if (head === "g" && item && !extra) return { kind: "group", groupId: item };
  if (Object.hasOwn(ALIASES, head) && !item) return { kind: "alias", to: ALIASES[head] };
  if (rootNames.has(head) && !item) return { kind: "root", root: head as Root };
  if (pageNames.has(head)) {
    if (extra || (item && !ITEM_PAGES.has(head)) || (!item && NEEDS_ITEM.has(head)))
      return { kind: "not-found" };
    return item ? { kind: "page", page: head as Page, item } : { kind: "page", page: head as Page };
  }
  if (!item) return { kind: "chat", agentId: head };
  return { kind: "not-found" };
}

export function sectionOf(route: ShellRoute): Root {
  if (route.kind === "root") return route.root;
  if (route.kind === "page" && SETTINGS_PAGES.has(route.page)) return "settings";
  return "chats";
}
/** A route the pager can slide between: only the four roots on phones. */
export const isRoot = (route: ShellRoute): route is { kind: "root"; root: Root } =>
  route.kind === "root";
export const isConversation = (route: ShellRoute) =>
  route.kind === "chat" || route.kind === "group";

/** The recovery page (recovery.page) for a broker outage, scoped to its account. */
export const recoveryPath = (account: unknown) =>
  typeof account === "string" && account
    ? `/app/recovery?account=${encodeURIComponent(account)}`
    : "/app/recovery";
