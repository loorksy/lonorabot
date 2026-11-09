import { t } from "@lingui/core/macro";
import { liveAvatarState, projectRunEvents, turnActivity } from "@lonora/core";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { VoiceChatCard } from "../components/call/VoiceChatCard";
import { useAgents } from "../hooks/useAgents";
import { useTheme } from "../hooks/useTheme";
import { useVoice } from "../hooks/useVoice";
import { useAgentLiveState } from "../lib/agent-live-state";
import { type Agent, ApiError, api, isRequestCancelled, type Resource, type Run } from "../lib/api";
import { auth } from "../lib/auth";
import { type InboxEntry, inboxPath, inboxRows } from "../pages/shell/conversation-inbox";
import { useAttention } from "../providers/AttentionProvider";
import { useClient } from "../providers/ClientProvider";
import { VoiceProvider } from "../providers/VoiceProvider";
import { ChatHeader } from "./ChatHeader";
import { useChatMenu } from "./ChatMenu";
import { type EdgeOptions, useScrollChrome } from "./chrome";
import { DesktopList } from "./DesktopList";
import { DesktopRail } from "./DesktopRail";
import { type ShellData, ShellDataProvider, useShellData } from "./data";
import { FloatingTabBar, tabLabel } from "./FloatingTabBar";
import { LargeTitle } from "./LargeTitle";
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
import { SheetProvider, useSheets } from "./sheets/SheetHost";
import { ToastProvider, useToast } from "./Toast";
import { bareDetail, bareSection, TopBar } from "./TopBar";
import { UpdateBar } from "./UpdateBar";
import { useViewportVars } from "./viewport";
import { Welcome } from "./Welcome";
import "./shell.css";

export function Shell({ onLogout }: { onLogout: () => void }) {
  const { owner } = useClient();
  return (
    <VoiceProvider ownerId={owner.id}>
      <ShellDataLoader onLogout={onLogout}>
        <SheetProvider>
          <ToastProvider>
            <NavigationProvider>
              <ShellBody />
            </NavigationProvider>
          </ToastProvider>
        </SheetProvider>
      </ShellDataLoader>
    </VoiceProvider>
  );
}

/* What every pane reads: agents, groups, the inbox projection and the live runs. */
function ShellDataLoader({ onLogout, children }: { onLogout: () => void; children: ReactNode }) {
  const { owner, revision, refresh, events } = useClient();
  const voice = useVoice();
  const navigate = useNavigate();
  const { agents, create, remove, loading, error: agentError } = useAgents();
  const [groups, setGroups] = useState<Resource[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [inbox, setInbox] = useState<InboxEntry[]>([]);
  const [inboxLoading, setInboxLoading] = useState(true);
  const [inboxError, setInboxError] = useState<unknown>();
  const [groupsLoading, setGroupsLoading] = useState(true);
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
      error: error ?? agentError,
      runs: observedRuns,
      busyIds,
      refresh,
      createAgent: create,
      removeAgent: remove,
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
      error,
      agentError,
      observedRuns,
      busyIds,
      refresh,
      create,
      remove,
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
type SearchState = { expanded: boolean; query: string };
const noSearch: SearchState = { expanded: false, query: "" };

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
  const home = desktop && route.kind === "root" && route.root === "chats";
  const net = useNetworkPhase(connected);
  const [preferredChartId, setPreferredChartId] = useState<string>();
  const menu = useChatMenu({ agent, group, memberAgents, preferredChartId });
  const [maintenance, setMaintenance] = useState(false);
  const [forcedUpdate, setForcedUpdate] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [desktopQuery, setDesktopQuery] = useState("");

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
    setSearch(route.kind === "root" && route.root === "chats" && saved ? saved : noSearch);
  }, [entryKey, route]);
  const updateSearch = useCallback((next: SearchState) => {
    setSearch(next);
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
        const { rows, byEntity } = inboxRows(data.agents, data.groups, data.inbox);
        if (!rows.length) return;
        event.preventDefault();
        const current = rows.findIndex((row) =>
          agent
            ? row.kind === "agent" && row.value.id === agent.id
            : group
              ? row.kind === "group" && row.value.id === group.id
              : false,
        );
        const next =
          rows[(current + (event.key === "ArrowDown" ? 1 : -1) + rows.length) % rows.length];
        nav.go(inboxPath(next, byEntity.get(`${next.kind}:${next.value.id}`)));
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
    data.agents,
    data.groups,
    data.inbox,
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
  const onOpenChart = useCallback(
    (id: string) => {
      setPreferredChartId(id);
      menu.openChart();
    },
    [menu],
  );
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
        if (voice.target) voice.expand();
        else if (agent) void voice.start(agent, new URLSearchParams(location.search).get("thread"));
      }}
      onMenu={menu.openMenu}
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
    ) : route.kind === "page" && bareDetail(route, desktop) ? (
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
            onOpen={nav.go}
            onNewChat={openNewChat}
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
              onChange: (query) => updateSearch({ expanded: true, query }),
              onExpand: () => updateSearch({ ...searchRef.current, expanded: true }),
              onClear: clearSearch,
            }
          : undefined
      }
      onBack={nav.back}
      onNewChat={openNewChat}
      onNewTask={onNewTask}
      header={header}
    >
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
    <div className="app-shell">
      {desktop ? (
        <div id="app" ref={appRef} className={collapsed ? "list-collapsed" : ""}>
          <DesktopRail
            section={section}
            chatsBadge={0}
            updatesDot={attention.items.length > 0}
            collapsed={collapsed}
            onToggleCollapsed={() => setCollapsed((value) => !value)}
            onSection={switchTab}
            ownerInitial={owner.email.slice(0, 1).toUpperCase()}
            onOwner={() => nav.go("/app/owner")}
          />
          <DesktopList
            query={desktopQuery}
            onQuery={setDesktopQuery}
            selected={selectedKey}
            onOpen={nav.go}
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
                    onOpen={nav.go}
                    onNewChat={openNewChat}
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
              chatsBadge={0}
              updatesDot={attention.items.length > 0}
              onTab={switchTab}
              onLensRelease={(root, lensFrom) => pagerTo(root, lensFrom)}
              dragging={busy}
            />
          )}
        </div>
      )}
      <VoiceChatCard
        agents={data.agents}
        onSettings={() => nav.go("/app/settings?tab=voice")}
        onOpenConversation={() => {
          const target = voice.target;
          if (target)
            nav.go(
              `/app/${target.agentId}${target.threadId ? `?thread=${encodeURIComponent(target.threadId)}` : ""}`,
            );
        }}
      />
      <UpdateBar revision={revision} forced={import.meta.env.DEV && forcedUpdate} />
      {maintenance && <MaintenanceOverlay retry={() => void retryMaintenance()} />}
    </div>
  );
}
