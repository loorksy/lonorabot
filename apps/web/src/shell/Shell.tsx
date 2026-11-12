import { plural, t } from "@lingui/core/macro";
import {
  appOpenReporter,
  filterRows,
  liveAvatarState,
  projectRunEvents,
  turnActivity,
  unreadBadgeTotal,
} from "@lonora/core";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { flushSync } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { useAgents } from "../hooks/useAgents";
import { useTheme } from "../hooks/useTheme";
import { useVoice } from "../hooks/useVoice";
import { useAgentLiveState } from "../lib/agent-live-state";
import {
  type Agent,
  ApiError,
  api,
  type ChatList,
  type InboxEntry,
  isRequestCancelled,
  type Message,
  type Resource,
  type Run,
  type ThreadSettings,
} from "../lib/api";
import { auth } from "../lib/auth";
import { flushQueued, serverAnswered } from "../lib/outgoing-messages";
import { useAttention } from "../providers/AttentionProvider";
import { useClient } from "../providers/ClientProvider";
import { VoiceProvider } from "../providers/VoiceProvider";
import { ChatHeader } from "./ChatHeader";
import { useChatMenu } from "./ChatMenu";
import {
  CallHeader,
  CallStrip,
  callReturn,
  useCallStarter,
  useIncomingCalls,
} from "./call/CallPages";
import { type EdgeOptions, useScrollChrome } from "./chrome";
import { DesktopList } from "./DesktopList";
import { DesktopRail } from "./DesktopRail";
import { mergePrefs, type ShellData, ShellDataProvider, useShellData } from "./data";
import { FloatingTabBar, tabLabel } from "./FloatingTabBar";
import { EASE, flip } from "./flip";
import { LargeTitle } from "./LargeTitle";
import { listsApi } from "./lists/api";
import { chatPath } from "./lists/ChatList";
import { HeadsUp } from "./lists/HeadsUp";
import { PopoverProvider } from "./lists/Popover";
import { SelBar } from "./lists/Selection";
import { ListsProvider, useLists } from "./lists/state";
import type { SearchTab } from "./lists/UnifiedSearch";
import { isDesktop, reducedMotion, useDesktop } from "./motion";
import { NetworkStrip, useNetworkPhase } from "./NetworkStrip";
import { useNewChatSheet } from "./NewChatSheet";
import { NavigationProvider, useNavigation, useScrollMemory } from "./navigation";
import { usePermissionSheet } from "./PermissionSheet";
import { usePager } from "./pager";
import { ChatPane, DetailPages, pageTitle, RootPage, useSettingsRedirect } from "./pages";
import { isRoot, type Root, rootPath, type ShellRoute, sectionOf } from "./routes";
import { useShortcutsSheet } from "./ShortcutsSheet";
import { MaintenanceOverlay, PageErrorBoundary } from "./StatePage";
import { AppLockProvider } from "./settings/AppLock";
import { SheetProvider, useSheets } from "./sheets/SheetHost";
import { ToastProvider, useToast } from "./Toast";
import { bareDetail, bareSection, TopBar } from "./TopBar";
import { UpdateBar } from "./UpdateBar";
import { useViewportVars } from "./viewport";
import { Welcome } from "./Welcome";
import "./shell.css";
import "./lists/lists.css";

// The owner opened the app: the morning brief's time is learned from it (VISION 11.1).
const reportAppOpen = appOpenReporter((body) => api.post("/app-opens", body));

export function Shell({ onLogout }: { onLogout: () => void }) {
  const { owner } = useClient();
  useEffect(() => {
    // Only an app the owner sees counts: a tab restored in the background is not an open.
    const visible = () => {
      if (document.visibilityState === "visible") reportAppOpen();
    };
    visible();
    document.addEventListener("visibilitychange", visible);
    return () => document.removeEventListener("visibilitychange", visible);
  }, []);
  return (
    <VoiceProvider ownerId={owner.id}>
      <ShellDataLoader onLogout={onLogout}>
        {/* One scope for the chrome and what the providers float above it (sheets, toast,
            menus): the reference's defaults reach all of them, the legacy styles none. */}
        <div className="app-shell">
          {/* Sheet and menu bodies use the toast; menus open sheets; navigation closes both. */}
          <ToastProvider>
            <SheetProvider>
              <PopoverProvider>
                <AppLockProvider>
                  <NavigationProvider>
                    <ShellLists />
                  </NavigationProvider>
                </AppLockProvider>
              </PopoverProvider>
            </SheetProvider>
          </ToastProvider>
        </div>
      </ShellDataLoader>
    </VoiceProvider>
  );
}

/* What every pane reads: agents, groups, the inbox projection and the live runs. */
function ShellDataLoader({ onLogout, children }: { onLogout: () => void; children: ReactNode }) {
  const { owner, revision, refresh, events } = useClient();
  const voice = useVoice();
  const navigate = useNavigate();
  const { agents, loading, error: agentError } = useAgents();
  const [groups, setGroups] = useState<Resource[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [inbox, setInbox] = useState<InboxEntry[]>([]);
  const [inboxLoading, setInboxLoading] = useState(true);
  const [inboxError, setInboxError] = useState<unknown>();
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [chatLists, setChatListsState] = useState<ChatList[]>([]);
  const [threadSettings, setThreadSettings] = useState<ThreadSettings | null>(null);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void revision;
    let live = true;
    void Promise.allSettled([api.get<Resource[]>("/groups"), api.get<Run[]>("/runs")]).then(
      ([groupResult, runResult]) => {
        if (!live) return;
        if (groupResult.status === "fulfilled") setGroups(groupResult.value);
        if (runResult.status === "fulfilled") setRuns(runResult.value);
        setGroupsLoading(false);
        const failure = [groupResult, runResult].find(
          (result) => result.status === "rejected" && !isRequestCancelled(result.reason),
        );
        setError(failure?.status === "rejected" ? failure.reason : undefined);
      },
    );
    return () => {
      live = false;
    };
  }, [revision]);
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<InboxEntry[]>("/threads/inbox")
      .then((rows) => {
        if (live) {
          setInbox(rows);
          setInboxError(undefined);
          setInboxLoading(false);
        }
      })
      .catch((failure) => {
        if (live && !isRequestCancelled(failure)) {
          setInboxError(failure);
          setInboxLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [revision]);
  useEffect(() => {
    void revision;
    let live = true;
    void Promise.allSettled([
      api.get<ChatList[]>("/chat-lists"),
      api.get<ThreadSettings>("/threads/settings"),
    ]).then(([lists, settings]) => {
      if (!live) return;
      if (lists.status === "fulfilled") setChatListsState(lists.value);
      if (settings.status === "fulfilled") setThreadSettings(settings.value);
    });
    return () => {
      live = false;
    };
  }, [revision]);
  const patchInbox = useCallback<ShellData["patchInbox"]>(
    (prefs) => setInbox((rows) => mergePrefs(rows, prefs)),
    [],
  );
  const setChatLists = useCallback<ShellData["setChatLists"]>(
    (update) => setChatListsState((rows) => update(rows)),
    [],
  );
  const observedRuns = useMemo(() => projectRunEvents(runs, events), [runs, events]);
  const busyIds = useMemo(
    () =>
      new Set(
        observedRuns
          .filter((row) => ["queued", "leased", "running"].includes(row.status))
          .map((row) => row.agent_id),
      ),
    [observedRuns],
  );
  const signOut = useCallback(async () => {
    try {
      await voice.stop().catch(() => undefined);
      await auth.logout();
      navigate("/app", { replace: true });
      onLogout();
    } catch (failure) {
      if (!isRequestCancelled(failure)) setError(failure);
    }
  }, [voice, navigate, onLogout]);
  const value = useMemo<ShellData>(
    () => ({
      owner,
      agents,
      agentsLoading: loading,
      groups,
      groupsLoading,
      inbox,
      inboxLoading,
      inboxError,
      chatLists,
      threadSettings,
      patchInbox,
      setChatLists,
      setThreadSettings,
      error: error ?? agentError,
      runs: observedRuns,
      busyIds,
      refresh,
      addGroup: (group) => setGroups((rows) => [...rows, group]),
      signOut,
    }),
    [
      owner,
      agents,
      loading,
      groups,
      groupsLoading,
      inbox,
      inboxLoading,
      inboxError,
      chatLists,
      threadSettings,
      patchInbox,
      setChatLists,
      error,
      agentError,
      observedRuns,
      busyIds,
      refresh,
      signOut,
    ],
  );
  return <ShellDataProvider value={value}>{children}</ShellDataProvider>;
}

function routeTitle(route: ShellRoute, agent?: Agent, group?: Resource) {
  switch (route.kind) {
    case "root":
      return tabLabel(route.root);
    case "page":
      return pageTitle(route.page);
    case "chat":
      return agent?.name ?? "Lonora";
    case "group":
      return group ? String(group.payload.name) : "Lonora";
    default:
      return "Lonora";
  }
}
type SearchState = { expanded: boolean; query: string; tab: SearchTab };
const noSearch: SearchState = { expanded: false, query: "", tab: "all" };

/* The list's state: phones select on the chat list and the archived page, desktop anywhere. */
function ShellLists() {
  const { route } = useNavigation();
  const desktop = useDesktop();
  const selectable =
    desktop ||
    (route.kind === "root" && route.root === "chats") ||
    (route.kind === "page" && route.page === "archived");
  return (
    <ListsProvider selectable={selectable}>
      <ShellBody />
    </ListsProvider>
  );
}

function ShellBody() {
  const nav = useNavigation();
  const { route } = nav;
  const location = useLocation();
  const navigate = useNavigate();
  const desktop = useDesktop();
  const data = useShellData();
  const { owner, connected, revision, events } = useClient();
  const attention = useAttention();
  const voice = useVoice();
  const sheets = useSheets();
  const toast = useToast();
  const openNewChat = useNewChatSheet();
  const openShortcuts = useShortcutsSheet();
  const permission = usePermissionSheet();
  const lists = useLists();
  const { theme } = useTheme();
  useViewportVars();
  useSettingsRedirect();

  // route aliases and dev-only routes
  useEffect(() => {
    if (route.kind === "alias") navigate(route.to, { replace: true });
  }, [route, navigate]);
  useEffect(() => {
    if (route.kind === "page" && route.page === "lab" && !import.meta.env.DEV)
      toast(t`This page is available in the development build only`, { type: "info" });
  }, [route, toast]);
  useEffect(() => {
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", theme === "light" ? "#f7f5ef" : "#0b0c10");
  }, [theme]);

  const agent =
    route.kind === "chat" ? data.agents.find((row) => row.id === route.agentId) : undefined;
  const group =
    route.kind === "group" ? data.groups.find((row) => row.id === route.groupId) : undefined;
  const memberIds = (group?.payload.member_ids ?? []) as string[];
  const memberAgents = memberIds
    .map((id) => data.agents.find((row) => row.id === id))
    .filter((row): row is Agent => Boolean(row));
  const { state: liveState } = useAgentLiveState(agent?.id);
  const currentRun =
    agent &&
    [...data.runs]
      .reverse()
      .find(
        (run) =>
          run.agent_id === agent.id &&
          ["queued", "leased", "running", "waiting_input", "waiting_takeover"].includes(run.status),
      );
  const avatarState = agent
    ? currentRun
      ? turnActivity(currentRun, events).avatar
      : liveAvatarState(liveState)
    : undefined;
  const section = sectionOf(route);
  const conversation = route.kind === "chat" || route.kind === "group";
  /* Phase 6: the call screen is the expanded call. On /app/call it is open; leaving the route
     folds it; expanding it anywhere else (the strip, the header's call) opens the route and
     remembers where it was opened from. A call that ends on its screen returns there. */
  const onCallRoute = route.kind === "page" && route.page === "call";
  const starter = useCallStarter();
  useIncomingCalls(!voice.target);
  const wasOnCall = useRef(onCallRoute);
  const hadCall = useRef(false);
  const here = location.pathname + location.search;
  // biome-ignore lint/correctness/useExhaustiveDependencies: the voice actions are stable intents; the route and the call state drive this.
  useEffect(() => {
    const left = wasOnCall.current && !onCallRoute;
    wasOnCall.current = onCallRoute;
    const ended = hadCall.current && !voice.target;
    hadCall.current = Boolean(voice.target);
    if (!voice.target) {
      if (ended && onCallRoute) {
        toast(t`The call ended.`, { type: "info" });
        nav.go(
          callReturn.path && !callReturn.path.startsWith("/app/call") ? callReturn.path : "/app",
          {
            replace: true,
          },
        );
      }
      return;
    }
    if (onCallRoute) {
      if (voice.minimized) voice.expand();
    } else if (left) {
      if (!voice.minimized) voice.minimize();
    } else if (!voice.minimized) {
      callReturn.path = here;
      nav.go("/app/call", { replace: true });
    }
  }, [onCallRoute, voice.target, voice.minimized]);
  const home = desktop && route.kind === "root" && route.root === "chats";
  const net = useNetworkPhase(connected);
  const menu = useChatMenu({ agent, group, memberAgents });
  const [maintenance, setMaintenance] = useState(false);
  const [forcedUpdate, setForcedUpdate] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [desktopQuery, setDesktopQuery] = useState("");
  const [desktopTab, setDesktopTab] = useState<SearchTab>("all");
  const chatsBadge = unreadBadgeTotal(data.inbox);

  /* The open conversation is read: its unread count and «marked unread» clear on the server
     (shared with mobile), and stay clear while new answers arrive in view. */
  const openThread = agent
    ? (new URLSearchParams(location.search).get("thread") ??
      lists.rows.find((row) => row.key === `agent:${agent.id}`)?.threadId)
    : group
      ? String(group.state?.thread_id ?? "")
      : undefined;
  const reading = useRef("");
  const { patchInbox } = data;
  useEffect(() => {
    const entry = data.inbox.find((row) => row.thread_id === openThread);
    if (!entry || !(entry.unread_count > 0 || entry.marked_unread)) return;
    if (document.visibilityState !== "visible") return;
    const seq = Math.max(entry.last_message?.seq ?? 0, entry.last_read_seq);
    const key = `${entry.thread_id}:${seq}:${entry.unread_count}`;
    if (reading.current === key) return;
    reading.current = key;
    void listsApi
      .read(entry.thread_id, seq)
      .then((prefs) => patchInbox([prefs]))
      .catch(() => {
        reading.current = "";
      });
  }, [data.inbox, openThread, patchInbox]);

  /* Owner decision Q6: plain messages written offline go out by themselves once the network
     is back (same client_nonce); a refused one stays «failed» with a manual retry. */
  const { refresh } = data;
  const flush = useCallback(async () => {
    const sent = await flushQueued(
      owner.id,
      (threadId, body) =>
        api
          .post<{ message: Message }>(`/threads/${threadId}/messages`, body)
          .then((accepted) => accepted.message),
      serverAnswered,
    );
    if (!sent) return;
    refresh();
    toast(
      plural(sent, {
        one: "One waiting message was sent",
        two: "Two waiting messages were sent",
        few: "# waiting messages were sent",
        many: "# waiting messages were sent",
        other: "# waiting messages were sent",
      }),
      { type: "success" },
    );
  }, [owner.id, refresh, toast]);
  useEffect(() => {
    if (connected && navigator.onLine) void flush();
  }, [connected, flush]);
  useEffect(() => {
    const online = () => void flush();
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, [flush]);

  /* The chats header's search field: expanded and query live in the history entry so Back
     restores a previous search; a fresh navigation to the chats starts unsearched. */
  const [search, setSearch] = useState<SearchState>(noSearch);
  const searchInput = useRef<HTMLInputElement>(null);
  const searchRef = useRef(search);
  searchRef.current = search;
  const entryKey = location.key;
  useEffect(() => {
    void entryKey;
    const saved = (window.history.state as { lonoraSearch?: SearchState } | null)?.lonoraSearch;
    setSearch(
      route.kind === "root" && route.root === "chats" && saved
        ? { ...noSearch, ...saved }
        : noSearch,
    );
  }, [entryKey, route]);
  const updateSearch = useCallback((next: SearchState) => {
    // The header gives the field its room (or takes it back) at once; the title, the field and
    // the + travel with transforms.
    const header = topRef.current?.querySelector<HTMLElement>("header.chats-header");
    if (header && next.expanded !== searchRef.current.expanded)
      flip(
        [
          ...header.querySelectorAll<HTMLElement>(
            ":scope > h1, :scope > .header-search, :scope > .icon",
          ),
        ].map((el) => ({ el, scale: el.classList.contains("header-search") })),
        () => flushSync(() => setSearch(next)),
        { duration: 200 },
      );
    else setSearch(next);
    try {
      window.history.replaceState(
        {
          ...(window.history.state ?? {}),
          lonoraSearch: next.expanded || next.query ? next : undefined,
        },
        "",
        window.location.href,
      );
    } catch {
      /* history may refuse while unloading */
    }
  }, []);
  const clearSearch = useCallback(() => {
    updateSearch(noSearch);
    searchInput.current?.blur();
  }, [updateSearch]);
  useEffect(() => {
    if (!search.expanded) return;
    const outside = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (sheets.isOpen() || target?.closest(".header-search,#view-scroll")) return;
      clearSearch();
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [search.expanded, sheets, clearSearch]);

  /* Whole-app states */
  useEffect(() => {
    let hits: number[] = [];
    const unavailable = () => {
      const now = Date.now();
      hits = [...hits.filter((at) => now - at < 30_000), now];
      if (hits.length >= 3) setMaintenance(true);
    };
    window.addEventListener("lonora:api-unavailable", unavailable);
    return () => window.removeEventListener("lonora:api-unavailable", unavailable);
  }, []);
  useEffect(() => {
    if (connected) setMaintenance(false);
  }, [connected]);
  const retryMaintenance = useCallback(async () => {
    try {
      const response = await fetch("/ready", { credentials: "include" });
      if (response.ok) {
        setMaintenance(false);
        data.refresh();
        return;
      }
    } catch {
      /* still down */
    }
    navigator.vibrate?.([10, 50, 10]);
    toast(t`Maintenance is still in progress. Try again shortly`, { type: "warn" });
  }, [data, toast]);
  useEffect(() => {
    if (voice.error instanceof ApiError && voice.error.code === "voice_permission_denied")
      permission("mic");
  }, [voice.error, permission]);
  useEffect(() => {
    const settings = () => nav.go("/app/settings");
    window.addEventListener("lonora:open-settings", settings);
    return () => window.removeEventListener("lonora:open-settings", settings);
  }, [nav]);

  /* Keyboard: ⌘/Ctrl K search · ⌘/Ctrl Shift O new chat · ⌘/Ctrl / shortcuts · Alt ↑↓ chats */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      if (mod && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (!isDesktop() && !(route.kind === "root" && route.root === "chats")) nav.go("/app");
        setTimeout(
          () =>
            (
              document.getElementById("desktop-search") ?? document.getElementById("search")
            )?.focus(),
          60,
        );
        return;
      }
      if (mod && event.shiftKey && event.key.toLowerCase() === "o") {
        event.preventDefault();
        openNewChat();
        return;
      }
      if (mod && event.key === "/") {
        event.preventDefault();
        openShortcuts();
        return;
      }
      if (event.altKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
        // The previous or next chat in the list's current order (wraps).
        const rows = filterRows(lists.rows, lists.filter, data.chatLists);
        if (!rows.length) return;
        event.preventDefault();
        const current = rows.findIndex(
          (row) => row.key === (agent ? `agent:${agent.id}` : group ? `group:${group.id}` : ""),
        );
        const next =
          rows[(current + (event.key === "ArrowDown" ? 1 : -1) + rows.length) % rows.length];
        nav.go(chatPath(next));
        return;
      }
      if (event.key === "Escape" && searchRef.current.expanded && !sheets.isOpen()) clearSearch();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    nav,
    route,
    agent,
    group,
    lists.rows,
    lists.filter,
    data.chatLists,
    openNewChat,
    openShortcuts,
    sheets,
    clearSearch,
  ]);

  /* Chrome refs and the pager */
  const appRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const topRef = useRef<HTMLElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const ghostTopRef = useRef<HTMLElement>(null);
  const ghostMainRef = useRef<HTMLElement>(null);
  const busy = useRef(false);
  const swiped = useRef(false);
  const [ghost, setGhost] = useState<Root | null>(null);
  const edgeFor = useCallback(
    (r: ShellRoute): EdgeOptions => ({
      edge: isRoot(r) || bareDetail(r, isDesktop()),
      chats: isRoot(r) && r.root === "chats",
      searchExpanded: searchRef.current.expanded,
    }),
    [],
  );
  const edgeOptions = useMemo(
    () => ({
      edge: isRoot(route) || bareDetail(route, desktop),
      chats: isRoot(route) && route.root === "chats",
      searchExpanded: search.expanded,
    }),
    [route, desktop, search.expanded],
  );
  const viewKey = location.pathname + location.search;
  const pagerTo = usePager({
    refs: {
      app: appRef,
      main: mainRef,
      top: topRef,
      nav: navRef,
      ghostTop: ghostTopRef,
      ghostMain: ghostMainRef,
    },
    root: isRoot(route) ? route.root : null,
    edgeOptions: (r) => edgeFor({ kind: "root", root: r }),
    setGhost,
    commit: (r) => {
      swiped.current = true;
      nav.go(rootPath(r));
    },
    blocked: () => sheets.isOpen() || searchRef.current.expanded,
    busy,
  });
  const switchTab = useCallback(
    (root: Root) => {
      if (isRoot(route) && route.root === root) {
        mainRef.current?.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" });
        return;
      }
      if (!isDesktop() && isRoot(route)) pagerTo(root);
      else nav.go(rootPath(root));
    },
    [route, nav, pagerTo],
  );
  useScrollChrome({
    host: hostRef,
    main: mainRef,
    top: topRef,
    nav: navRef,
    options: edgeOptions,
    viewKey,
    paused: busy,
  });
  useScrollMemory(mainRef, viewKey);
  const [enter, setEnter] = useState(false);
  const lastKey = useRef<string>(undefined);
  useLayoutEffect(() => {
    setEnter(
      lastKey.current !== undefined &&
        lastKey.current !== entryKey &&
        !swiped.current &&
        !reducedMotion(),
    );
    lastKey.current = entryKey;
    swiped.current = false;
  }, [entryKey]);

  const title = routeTitle(route, agent, group);
  const onNewTask = useCallback(() => nav.go("/app/tasks?new=1"), [nav]);
  const onOpenChart = useCallback((id: string) => menu.openChart(id), [menu]);
  // The conversation's own controls ask the shell for the call, the chart and the members.
  useEffect(() => {
    const call = () => {
      if (voice.target) voice.expand();
      else if (agent) void voice.start(agent, new URLSearchParams(location.search).get("thread"));
    };
    const chart = () => menu.openChart();
    const members = () => menu.openInfo();
    window.addEventListener("lonora:start-call", call);
    window.addEventListener("lonora:open-chart", chart);
    window.addEventListener("lonora:members-permissions", members);
    return () => {
      window.removeEventListener("lonora:start-call", call);
      window.removeEventListener("lonora:open-chart", chart);
      window.removeEventListener("lonora:members-permissions", members);
    };
  }, [voice, agent, location.search, menu]);
  const header = conversation ? (
    <ChatHeader
      agent={agent}
      group={group}
      memberAgents={memberAgents}
      agents={data.agents}
      working={agent ? data.busyIds.has(agent.id) : false}
      avatarState={avatarState}
      net={net}
      voiceActive={Boolean(voice.target)}
      onBack={nav.back}
      onInfo={menu.openInfo}
      onCall={() => {
        if (agent) void starter.start(agent, new URLSearchParams(location.search).get("thread"));
      }}
      onMenu={menu.openMenu}
      menuReady={menu.ready}
    />
  ) : undefined;
  const mainClass = [
    isRoot(route) ? "root" : "detail",
    bareSection(route, desktop) || bareDetail(route, desktop) ? "bare" : "",
    conversation ? "chat-main" : "",
    enter ? "page-enter" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const largeTitle =
    isRoot(route) && bareSection(route, desktop) ? (
      <LargeTitle title={title} />
    ) : route.kind === "page" && route.page !== "call" && bareDetail(route, desktop) ? (
      // The call screen has no page title (the reference's largeTitle skips `call`).
      <LargeTitle title={title} detail />
    ) : null;
  const content = (
    <PageErrorBoundary resetKey={location.key}>
      {route.kind === "root" ? (
        home ? (
          <Welcome
            name={owner.email.split("@")[0]}
            onNewChat={openNewChat}
            onNewTask={onNewTask}
            onNewGroup={() => nav.go("/app/new-group")}
            onUpdates={() => nav.go("/app/updates")}
          />
        ) : (
          <RootPage
            root={route.root}
            search={search}
            onTab={(tab) => updateSearch({ ...searchRef.current, tab })}
            desktop={desktop}
          />
        )
      ) : conversation ? (
        <ChatPane
          agent={agent}
          group={group}
          memberAgents={memberAgents}
          onOpenChart={onOpenChart}
        />
      ) : (
        <DetailPages
          onMaintenance={() => setMaintenance(true)}
          onUpdateBar={() => setForcedUpdate(true)}
        />
      )}
    </PageErrorBoundary>
  );
  const topBar = (
    <TopBar
      topRef={topRef}
      route={route}
      title={title}
      desktop={desktop}
      search={
        !desktop && isRoot(route) && route.root === "chats"
          ? {
              expanded: search.expanded,
              query: search.query,
              inputRef: searchInput,
              onChange: (query) => updateSearch({ ...searchRef.current, expanded: true, query }),
              onExpand: () => updateSearch({ ...searchRef.current, expanded: true }),
              onClear: clearSearch,
            }
          : undefined
      }
      onBack={nav.back}
      onNewChat={openNewChat}
      onNewTask={onNewTask}
      onNewAgent={() => nav.go("/app/new-agent")}
      header={header ?? (onCallRoute ? <CallHeader desktop={desktop} /> : undefined)}
      selection={
        lists.selected &&
        !desktop &&
        ((route.kind === "root" && route.root === "chats") ||
          (route.kind === "page" && route.page === "archived")) ? (
          <SelBar />
        ) : undefined
      }
    >
      <CallStrip
        hidden={onCallRoute || (route.kind === "chat" && route.agentId === voice.target?.agentId)}
      />
      <NetworkStrip phase={net} ownerId={owner.id} />
    </TopBar>
  );
  const main = (
    <main id="view-scroll" key={location.key} ref={mainRef} className={mainClass}>
      {largeTitle}
      {content}
    </main>
  );
  const selectedKey = agent ? `agent:${agent.id}` : group ? `group:${group.id}` : undefined;
  return (
    <>
      {desktop ? (
        <div id="app" ref={appRef} className={collapsed ? "list-collapsed" : ""}>
          <DesktopRail
            section={section}
            chatsBadge={chatsBadge}
            updatesDot={attention.items.length > 0}
            collapsed={collapsed}
            onToggleCollapsed={() => {
              // The list pane leaves and returns with opacity and a slide; the grid changes at once.
              const list = appRef.current?.querySelector<HTMLElement>(".desktop-list");
              if (!list || reducedMotion()) return setCollapsed((value) => !value);
              // Toward the rail: its side is the inline start.
              const slide = getComputedStyle(list).direction === "rtl" ? 24 : -24;
              if (collapsed) {
                flushSync(() => setCollapsed(false));
                list.animate(
                  [
                    { opacity: 0, transform: `translateX(${slide}px)` },
                    { opacity: 1, transform: "none" },
                  ],
                  { duration: 220, easing: EASE },
                );
              } else
                list.animate(
                  [
                    { opacity: 1, transform: "none" },
                    { opacity: 0, transform: `translateX(${slide}px)` },
                  ],
                  { duration: 220, easing: EASE },
                ).onfinish = () => setCollapsed(true);
            }}
            onSection={switchTab}
            ownerInitial={owner.email.slice(0, 1).toUpperCase()}
            onOwner={() => nav.go("/app/owner")}
          />
          <DesktopList
            query={desktopQuery}
            onQuery={(query) => {
              setDesktopQuery(query);
              if (!query.trim()) setDesktopTab("all");
            }}
            tab={desktopTab}
            onTab={setDesktopTab}
            selected={selectedKey}
            onNewChat={openNewChat}
          />
          <section
            ref={hostRef as React.RefObject<HTMLElement>}
            className={`desktop-content${home ? " is-home" : ""}`}
            aria-label={t`Workspace`}
          >
            {topBar}
            {main}
          </section>
        </div>
      ) : (
        <div
          id="app"
          ref={(node) => {
            appRef.current = node;
            hostRef.current = node;
          }}
          className={
            search.expanded && isRoot(route) && route.root === "chats" ? "search-mode" : ""
          }
        >
          {topBar}
          {main}
          {ghost && (
            <>
              <TopBar
                topRef={ghostTopRef}
                route={{ kind: "root", root: ghost }}
                title={tabLabel(ghost)}
                desktop={false}
                onBack={nav.back}
                onNewChat={openNewChat}
                onNewTask={onNewTask}
              />
              <main
                ref={ghostMainRef}
                className={`root${ghost === "chats" ? "" : " bare"} pager-ghost`}
                aria-hidden="true"
                inert
              >
                {ghost !== "chats" && <LargeTitle title={tabLabel(ghost)} />}
                <PageErrorBoundary resetKey={ghost}>
                  <RootPage
                    root={ghost}
                    search={noSearch}
                    onTab={() => undefined}
                    desktop={false}
                  />
                </PageErrorBoundary>
              </main>
            </>
          )}
          {isRoot(route) && (
            <FloatingTabBar
              navRef={navRef}
              section={section}
              chatsBadge={chatsBadge}
              updatesDot={attention.items.length > 0}
              onTab={switchTab}
              onLensRelease={(root, lensFrom) => pagerTo(root, lensFrom)}
              dragging={busy}
            />
          )}
        </div>
      )}
      <UpdateBar revision={revision} forced={import.meta.env.DEV && forcedUpdate} />
      <HeadsUp currentThreadId={conversation ? openThread : undefined} />
      {maintenance && <MaintenanceOverlay retry={() => void retryMaintenance()} />}
    </>
  );
}
