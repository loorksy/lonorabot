// Modified for Lonora; template source and license attribution in THIRD_PARTY_NOTICES.md.
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@lonora/ui-web";
import {
  Activity as ActivityIcon,
  ArrowLeftRight,
  Bell,
  BookOpen,
  ChartCandlestick,
  ChevronDown,
  Clock,
  Folder,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  PanelsTopLeft,
  Plus,
  Search as SearchIcon,
  Settings as SettingsIcon,
  X,
} from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { AgentAvatar } from "../components/agents/AgentAvatar";
import { AgentCreatePanel } from "../components/agents/AgentCreatePanel";
import { AgentSettings } from "../components/agents/AgentSettings";
import { ThreadViewport } from "../components/chat/ThreadViewport";
import { GroupAvatar } from "../components/groups/GroupAvatar";
import { GroupCreatePanel } from "../components/groups/GroupCreatePanel";
import { GroupSettings } from "../components/groups/GroupSettings";
import type { SettingsTab } from "../components/settings/SettingsSidebar";
import { NewConversationPicker } from "../components/template/NewConversationPicker";
import { SidebarRow } from "../components/template/SidebarRow";
import { SwitchAgentDialog } from "../components/template/SwitchAgentDialog";
import { useAgents } from "../hooks/useAgents";
import { dismissOverlays, useOverlayHistory } from "../hooks/useOverlayHistory";
import { usePersistentThread } from "../hooks/usePersistentThread";
import { useTheme } from "../hooks/useTheme";
import { type Agent, api, type Resource, type Run } from "../lib/api";
import { auth } from "../lib/auth";
import {
  type Panel,
  readRightPanelState,
  rightPanelStorageKey,
  writeRightPanelState,
} from "../lib/right-panel-state";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import { Activity } from "./Activity";
import { Artifacts } from "./Artifacts";
import { Knowledge } from "./Knowledge";
import { ResizableSidePanel } from "./ResizableSidePanel";
import { Routines } from "./Routines";
import { Search } from "./Search";

const Market = lazy(() => import("./Market").then((module) => ({ default: module.Market })));
const Trading = lazy(() => import("./Trading").then((module) => ({ default: module.Trading })));
const Settings = lazy(() => import("./Settings").then((module) => ({ default: module.Settings })));
const surfaces = [
  "activity",
  "board",
  "artifacts",
  "search",
  "market",
  "trading",
  "routines",
  "knowledge",
];

function useMedia(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const changed = () => setMatches(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, [query]);
  return matches;
}
function NotFound() {
  return (
    <div className="tpl-empty">
      <h1>
        <Trans>This page is unavailable</Trans>
      </h1>
      <p>
        <Trans>Choose an agent or return to your workspace.</Trans>
      </p>
      <a href="/app">
        <Trans>Back to workspace</Trans>
      </a>
    </div>
  );
}
function AgentConversation({ agent, agents }: { agent: Agent; agents: Agent[] }) {
  const [params, setParams] = useSearchParams();
  const { refresh } = useClient();
  const { thread, threads, error } = usePersistentThread(agent.id, params.get("thread"));
  if (error != null && !thread)
    return (
      <div className="tpl-empty">
        <p role="alert">{userError(error)}</p>
        <button type="button" onClick={() => window.location.reload()}>
          <Trans>Retry</Trans>
        </button>
      </div>
    );
  if (!thread)
    return (
      <div className="tpl-empty" role="status">
        <Trans>Opening conversation…</Trans>
      </div>
    );
  return (
    <>
      {error != null && (
        <div className="tpl-error-banner" role="alert">
          {userError(error)}
          <button type="button" onClick={refresh}>
            <Trans>Retry</Trans>
          </button>
        </div>
      )}
      {threads.length > 1 && (
        <div className="tpl-history-picker">
          <label>
            <Trans>Conversation history</Trans>
            <select
              aria-label={t`Conversation history`}
              value={thread.id}
              onChange={(event) => setParams({ thread: event.target.value })}
            >
              {threads.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.title || new Date(row.created_at).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <ThreadViewport key={thread.id} threadId={thread.id} agentId={agent.id} agents={agents} />
    </>
  );
}
export function Shell({ onLogout }: { onLogout: () => void }) {
  useTheme();
  const { owner, connected, revision, refresh } = useClient();
  const { agents, create, loading, error: agentError } = useAgents();
  const location = useLocation();
  const navigate = useNavigate();
  const mobile = useMedia("(max-width: 767px)");
  const panelOverlay = useMedia("(max-width: 1149px)");
  const [groups, setGroups] = useState<Resource[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(`lonora:sidebar-collapsed:${owner.id}`) === "1";
    } catch {
      return false;
    }
  });
  const [query, setQuery] = useState("");
  const [panel, setPanel] = useState<Panel>(null);
  const [pendingProfile, setPendingProfile] = useState<string | null>(null);
  const [picker, setPicker] = useState(false);
  const [accountMenu, setAccountMenu] = useState(false);
  const [switcher, setSwitcher] = useState(false);
  const [globalSettings, setGlobalSettings] = useState<SettingsTab | null>(null);
  const [error, setError] = useState<unknown>();
  const segments = location.pathname.split("/").filter(Boolean);
  const isGroup = segments[1] === "g";
  const agentId = segments.length === 2 && !surfaces.includes(segments[1]) ? segments[1] : "";
  const agent = agents.find((row) => row.id === agentId);
  const group = isGroup ? groups.find((row) => row.id === segments[2]) : undefined;
  const memberIds = (group?.payload.member_ids ?? []) as string[];
  const memberAgents = memberIds
    .map((id) => agents.find((row) => row.id === id))
    .filter((row): row is Agent => Boolean(row));
  const entityKey = agent
    ? rightPanelStorageKey(owner.id, "agent", agent.id)
    : group
      ? rightPanelStorageKey(owner.id, "group", group.id)
      : "";
  const title =
    agent?.name ??
    (group
      ? String(group.payload.name)
      : ({
          activity: t`Activity`,
          board: t`Task boards`,
          artifacts: t`Artifacts`,
          search: t`Search`,
          market: t`Market`,
          trading: t`Trading`,
          routines: t`Routines`,
          knowledge: t`Knowledge`,
        }[segments[1]] ?? "Lonora"));
  const panelTitle = {
    settings: t`Agent settings`,
    knowledge: t`Knowledge`,
    routines: t`Routines`,
    workspace: t`Agent workspace`,
    create: t`Create agent`,
    "create-group": t`Create group`,
    "group-settings": t`Group settings`,
  }[panel ?? "settings"];
  useOverlayHistory(drawer, () => setDrawer(false));
  useOverlayHistory(picker, () => setPicker(false));
  useOverlayHistory(accountMenu, () => setAccountMenu(false));
  useOverlayHistory(Boolean(panel), closePanel);
  useOverlayHistory(globalSettings !== null, () => setGlobalSettings(null));
  useOverlayHistory(switcher, () => setSwitcher(false));
  useEffect(() => {
    void revision;
    let live = true;
    void Promise.all([api.get<Resource[]>("/groups"), api.get<Run[]>("/runs")])
      .then(([nextGroups, nextRuns]) => {
        if (live) {
          setGroups(nextGroups);
          setRuns(nextRuns);
          setGroupsLoading(false);
          setError(undefined);
        }
      })
      .catch((failure) => {
        if (live) {
          setError(failure);
          setGroupsLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [revision]);
  useEffect(() => {
    if (entityKey && !panelOverlay) setPanel(readRightPanelState(entityKey));
    else setPanel(null);
  }, [entityKey, panelOverlay]);
  useEffect(() => {
    if (!agent && !group) return;
    try {
      localStorage.setItem(`lonora:last-context:${owner.id}`, location.pathname);
    } catch {
      /* Preference only. */
    }
  }, [agent, group, location.pathname, owner.id]);
  useEffect(() => {
    if (loading || groupsLoading || !["/", "/app", "/app/", "/sign-in"].includes(location.pathname))
      return;
    let previous = "";
    try {
      previous = localStorage.getItem(`lonora:last-context:${owner.id}`) ?? "";
    } catch {
      /* Preference only. */
    }
    const valid =
      agents.some((row) => previous === `/app/${row.id}`) ||
      groups.some((row) => previous === `/app/g/${row.id}`);
    if (valid || agents.length)
      navigate(valid ? previous : `/app/${agents[0].id}`, { replace: true });
  }, [agents, groups, loading, groupsLoading, location.pathname, navigate, owner.id]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSwitcher((value) => !value);
      }
    };
    const settings = () => setGlobalSettings("overview");
    window.addEventListener("keydown", key);
    window.addEventListener("lonora:open-settings", settings);
    return () => {
      window.removeEventListener("keydown", key);
      window.removeEventListener("lonora:open-settings", settings);
    };
  }, []);
  function open(path: string) {
    const remembered = panel;
    dismissOverlays();
    if (entityKey) writeRightPanelState(entityKey, remembered);
    setPanel(null);
    setDrawer(false);
    setPicker(false);
    setAccountMenu(false);
    setQuery("");
    navigate(path);
  }
  function closePanel() {
    setPanel(null);
    if (entityKey) writeRightPanelState(entityKey, null);
  }
  function openPanel(next: Panel) {
    if (panel) {
      setDrawer(false);
      setPicker(false);
      setAccountMenu(false);
      setPanel(next);
      if (entityKey) writeRightPanelState(entityKey, next);
      return;
    }
    dismissOverlays();
    setDrawer(false);
    setPicker(false);
    setAccountMenu(false);
    setPanel(next);
    if (entityKey) writeRightPanelState(entityKey, next);
  }
  useEffect(() => {
    if (pendingProfile && agent?.id === pendingProfile) {
      setPanel("settings");
      writeRightPanelState(entityKey, "settings");
      setPendingProfile(null);
    }
  }, [pendingProfile, agent?.id, entityKey]);
  function openSettings(tab: SettingsTab) {
    dismissOverlays();
    setGlobalSettings(tab);
  }
  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem(`lonora:sidebar-collapsed:${owner.id}`, next ? "1" : "0");
    } catch {
      /* Preference only. */
    }
  }
  const busyIds = new Set(
    runs
      .filter((row) => ["queued", "leased", "running"].includes(row.status))
      .map((row) => row.agent_id),
  );
  const needle = query.trim().toLocaleLowerCase();
  const filtered = agents.filter((row) => !needle || row.name.toLocaleLowerCase().includes(needle));
  const backgroundInert = (mobile && drawer) || (panelOverlay && Boolean(panel));
  return (
    <div className="tpl-shell" data-sidebar-collapsed={collapsed ? "true" : "false"}>
      {mobile && drawer && (
        <button
          type="button"
          className="tpl-drawer-backdrop"
          tabIndex={-1}
          aria-label={t`Close navigation`}
          onClick={() => setDrawer(false)}
        />
      )}
      <aside
        className="tpl-sidebar"
        data-mobile-open={drawer ? "true" : "false"}
        inert={mobile ? !drawer : collapsed}
        aria-label={t`Agents and groups`}
      >
        <div className="tpl-sidebar-top">
          <button type="button" className="tpl-wordmark" onClick={() => open("/app")}>
            <span className="tpl-logo">L</span>Lonora
            <span
              className={`tpl-connection ${connected ? "online" : ""}`}
              title={connected ? t`Connected` : t`Reconnecting`}
            />
          </button>
          <div className="tpl-toolbar">
            <button
              type="button"
              className="tpl-icon-button"
              aria-label={t`Activity`}
              aria-pressed={segments[1] === "activity"}
              onClick={() => open("/app/activity")}
            >
              <Bell />
            </button>
            <button
              type="button"
              className="tpl-icon-button tpl-desktop-only"
              aria-label={t`Minimize agents`}
              onClick={toggleCollapsed}
            >
              <PanelLeftClose />
            </button>
            <button
              type="button"
              className="tpl-icon-button"
              aria-label={t`Create`}
              onClick={() => setPicker((value) => !value)}
            >
              <Plus />
            </button>
            <button
              type="button"
              className="tpl-icon-button tpl-mobile-only"
              aria-label={t`Close navigation`}
              onClick={() => setDrawer(false)}
            >
              <X />
            </button>
          </div>
        </div>
        <form
          className="tpl-sidebar-search"
          onSubmit={(event) => {
            event.preventDefault();
            open(`/app/search?q=${encodeURIComponent(query)}`);
          }}
        >
          <SearchIcon />
          <input
            aria-label={t`Search`}
            placeholder={t`Search`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button
            type="submit"
            title={t`Search your workspace`}
            aria-label={t`Search your workspace`}
          >
            <kbd>↵</kbd>
          </button>
        </form>
        <div className="tpl-roster-scroll lonora-scroll">
          <div className="tpl-section-label">
            <Trans>Agents</Trans>
            <button
              type="button"
              className="tpl-icon-button"
              aria-label={t`Switch agent`}
              onClick={() => setSwitcher(true)}
            >
              <kbd dir="ltr">⌘/Ctrl K</kbd>
            </button>
          </div>
          {loading && (
            <p role="status" className="tpl-roster-notice">
              <Trans>Loading agents…</Trans>
            </p>
          )}
          {filtered.map((row) => (
            <div className="tpl-roster-item" key={row.id}>
              <SidebarRow
                agent={row}
                selected={agent?.id === row.id}
                working={busyIds.has(row.id)}
                depth={row.parent_id ? 1 : 0}
                onClick={() => open(`/app/${row.id}`)}
              />
              <button
                type="button"
                className="tpl-roster-settings"
                aria-label={`${t`Agent settings`}: ${row.name}`}
                onClick={() => {
                  if (agent?.id === row.id) openPanel("settings");
                  else {
                    open(`/app/${row.id}`);
                    setPendingProfile(row.id);
                  }
                }}
              >
                <SettingsIcon />
              </button>
            </div>
          ))}
          {!loading && !filtered.length && (
            <p className="tpl-roster-notice">
              <Trans>No agents match</Trans>
            </p>
          )}
          <div className="tpl-section-label">
            <Trans>Groups</Trans>
            <button
              type="button"
              className="tpl-icon-button"
              aria-label={t`Create group`}
              onClick={() => openPanel("create-group")}
            >
              <Plus />
            </button>
          </div>
          {groups
            .filter(
              (row) => !needle || String(row.payload.name).toLocaleLowerCase().includes(needle),
            )
            .map((row) => (
              <SidebarRow
                group={row}
                key={row.id}
                selected={group?.id === row.id}
                subtitle={`${(row.payload.member_ids as string[]).length} ${t`Members`}`}
                onClick={() => open(`/app/g/${row.id}`)}
              />
            ))}
          {!groupsLoading && !groups.length && (
            <p className="tpl-roster-notice">
              <Trans>Bring agents together in a group.</Trans>
            </p>
          )}
        </div>
        <div className="tpl-account">
          <button
            type="button"
            className="tpl-account-trigger"
            onClick={() => setAccountMenu((value) => !value)}
            aria-expanded={accountMenu}
          >
            <span className="tpl-owner-avatar">{owner.email[0].toUpperCase()}</span>
            <span className="tpl-truncate">
              <bdi>{owner.email}</bdi>
            </span>
            <ChevronDown />
          </button>
        </div>
        {accountMenu && (
          <div className="tpl-account-menu" role="menu" aria-label={t`Workspace menu`}>
            <button type="button" role="menuitem" onClick={() => open("/app/board")}>
              <LayoutDashboard />
              <Trans>Task boards</Trans>
            </button>
            <button type="button" role="menuitem" onClick={() => open("/app/artifacts")}>
              <Folder />
              <Trans>Artifacts</Trans>
            </button>
            <button type="button" role="menuitem" onClick={() => open("/app/market")}>
              <ChartCandlestick />
              <Trans>Market</Trans>
            </button>
            <button type="button" role="menuitem" onClick={() => open("/app/trading")}>
              <ArrowLeftRight />
              <Trans>Trading</Trans>
            </button>
            <button type="button" role="menuitem" onClick={() => openSettings("overview")}>
              <SettingsIcon />
              <Trans>Settings</Trans>
            </button>
            <button type="button" role="menuitem" onClick={() => openSettings("usage")}>
              <ActivityIcon />
              <Trans>Token usage</Trans>
            </button>
            <button
              type="button"
              role="menuitem"
              className="danger"
              onClick={() => {
                void auth.logout().then(onLogout).catch(setError);
              }}
            >
              <LogOut />
              <Trans>Sign out</Trans>
            </button>
          </div>
        )}
      </aside>
      {picker && (
        <div className="tpl-picker-layer">
          <button
            className="tpl-picker-dismiss"
            type="button"
            tabIndex={-1}
            aria-label={t`Close`}
            onClick={() => setPicker(false)}
          />
          <div className="tpl-picker-popover">
            <NewConversationPicker
              agents={agents}
              onCreateAgent={() => openPanel("create")}
              onOpenAgent={(id) => open(`/app/${id}`)}
              onCreateGroup={() => openPanel("create-group")}
            />
          </div>
        </div>
      )}
      <main className="tpl-main" inert={backgroundInert} aria-hidden={backgroundInert || undefined}>
        <header className="tpl-chat-header">
          <div className="tpl-header-leading">
            <button
              type="button"
              className="tpl-icon-button tpl-mobile-only"
              aria-label={t`Open navigation`}
              onClick={() => setDrawer(true)}
            >
              <Menu />
            </button>
            {collapsed && (
              <button
                type="button"
                className="tpl-icon-button tpl-desktop-only"
                aria-label={t`Show agents`}
                onClick={toggleCollapsed}
              >
                <PanelLeftOpen />
              </button>
            )}
            <button
              type="button"
              className="tpl-chat-identity"
              onClick={() => {
                if (agent || group) openPanel(group ? "group-settings" : "settings");
              }}
              disabled={!agent && !group}
            >
              {agent ? (
                <AgentAvatar agent={agent} />
              ) : group ? (
                <GroupAvatar name={String(group.payload.name)} />
              ) : null}
              <span dir="auto">{title}</span>
              {agent?.paused && (
                <span className="badge">
                  <Trans>Paused</Trans>
                </span>
              )}
            </button>
          </div>
          <div className="tpl-toolbar">
            {(agent || group) && (
              <>
                <button
                  type="button"
                  className="tpl-icon-button"
                  aria-label={t`Knowledge`}
                  title={t`Knowledge`}
                  onClick={() => openPanel("knowledge")}
                >
                  <BookOpen />
                </button>
                <button
                  type="button"
                  className="tpl-icon-button"
                  aria-label={t`Routines`}
                  title={t`Routines`}
                  onClick={() => openPanel("routines")}
                >
                  <Clock />
                </button>
                <button
                  type="button"
                  className="tpl-icon-button"
                  aria-label={t`Agent workspace`}
                  title={t`Agent workspace`}
                  aria-pressed={panel === "workspace"}
                  onClick={() => openPanel(panel === "workspace" ? null : "workspace")}
                >
                  <PanelsTopLeft />
                </button>
              </>
            )}
            <button
              type="button"
              className="tpl-icon-button"
              aria-label={t`Settings`}
              onClick={() => openSettings("overview")}
            >
              <SettingsIcon />
            </button>
          </div>
        </header>
        {(error ?? agentError) != null && (
          <div className="tpl-error-banner" role="alert">
            {userError(error ?? agentError)}
            <button type="button" onClick={() => window.location.reload()}>
              <Trans>Retry</Trans>
            </button>
          </div>
        )}
        <Suspense
          fallback={
            <div className="tpl-empty" role="status">
              <Trans>Loading workspace…</Trans>
            </div>
          }
        >
          <Routes>
            <Route path="/" element={<Navigate to="/app" replace />} />
            <Route path="/sign-in" element={<Navigate to="/app" replace />} />
            <Route
              path="/app"
              element={
                <div className="tpl-empty">
                  <span className="tpl-logo large">L</span>
                  <h1>
                    <Trans>Your team starts here</Trans>
                  </h1>
                  <p>
                    <Trans>Create a persistent agent and start a conversation.</Trans>
                  </p>
                  <button type="button" className="primary" onClick={() => openPanel("create")}>
                    <Plus />
                    <Trans>Create agent</Trans>
                  </button>
                </div>
              }
            />
            <Route
              path="/app/activity"
              element={
                <div className="tpl-surface">
                  <Activity agents={agents} view="activity" />
                </div>
              }
            />
            <Route
              path="/app/board"
              element={
                <div className="tpl-surface">
                  <Activity agents={agents} view="board" />
                </div>
              }
            />
            <Route
              path="/app/artifacts"
              element={
                <div className="tpl-surface">
                  <Artifacts />
                </div>
              }
            />
            <Route
              path="/app/artifacts/:artifactId"
              element={
                <div className="tpl-surface">
                  <Artifacts />
                </div>
              }
            />
            <Route
              path="/app/search"
              element={
                <div className="tpl-surface">
                  <Search />
                </div>
              }
            />
            <Route
              path="/app/market"
              element={
                <div className="tpl-surface">
                  <Market agents={agents} />
                </div>
              }
            />
            <Route
              path="/app/trading"
              element={
                <div className="tpl-surface">
                  <Trading />
                </div>
              }
            />
            <Route
              path="/app/routines"
              element={
                <div className="tpl-surface">
                  <Routines agents={agents} />
                </div>
              }
            />
            <Route
              path="/app/knowledge"
              element={
                <div className="tpl-surface">
                  <Knowledge agents={agents} initialAgent={agents[0]?.id ?? ""} />
                </div>
              }
            />
            <Route
              path="/app/g/:groupId"
              element={
                groupsLoading ? (
                  <div className="tpl-empty" role="status">
                    <Trans>Loading group…</Trans>
                  </div>
                ) : group?.state?.thread_id ? (
                  <ThreadViewport
                    key={String(group.state.thread_id)}
                    threadId={String(group.state.thread_id)}
                    agentId=""
                    agents={memberAgents}
                  />
                ) : (
                  <NotFound />
                )
              }
            />
            <Route
              path="/app/:agentId"
              element={
                loading ? (
                  <div className="tpl-empty" role="status">
                    <Trans>Loading agents…</Trans>
                  </div>
                ) : agent ? (
                  <AgentConversation key={agent.id} agent={agent} agents={agents} />
                ) : (
                  <NotFound />
                )
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </main>
      <ResizableSidePanel
        open={Boolean(panel)}
        panel={panel ?? "closed"}
        botsSidebarCollapsed={collapsed}
        label={panelTitle}
        onClose={closePanel}
      >
        <header className="tpl-panel-header">
          <h2>{panelTitle}</h2>
          <button
            type="button"
            className="tpl-icon-button"
            aria-label={t`Close context panel`}
            onClick={() => {
              setPanel(null);
              if (entityKey) writeRightPanelState(entityKey, null);
            }}
          >
            <X />
          </button>
        </header>
        <div className="tpl-panel-tabs">
          {(agent || group) && !["create", "create-group"].includes(panel ?? "") && (
            <>
              <button
                type="button"
                onClick={() => openPanel(group ? "group-settings" : "settings")}
              >
                <SettingsIcon />
                <Trans>Profile</Trans>
              </button>
              <button type="button" onClick={() => openPanel("knowledge")}>
                <BookOpen />
                <Trans>Knowledge</Trans>
              </button>
              <button type="button" onClick={() => openPanel("routines")}>
                <Clock />
                <Trans>Routines</Trans>
              </button>
            </>
          )}
        </div>
        <div className="tpl-panel-body lonora-scroll">
          {panel === "create" && (
            <AgentCreatePanel
              create={create}
              onCreated={(row) => {
                refresh();
                open(`/app/${row.id}`);
              }}
            />
          )}
          {panel === "create-group" && (
            <GroupCreatePanel
              agents={agents}
              onCreated={(row) => {
                refresh();
                setGroups((rows) => [...rows, row]);
                open(`/app/g/${row.id}`);
              }}
            />
          )}
          {panel === "settings" && agent && (
            <AgentSettings key={agent.id} agent={agent} onClose={closePanel} />
          )}
          {panel === "group-settings" && group && (
            <GroupSettings
              key={group.id}
              group={group}
              agents={agents}
              onSave={() => {
                refresh();
                closePanel();
              }}
            />
          )}
          {panel === "knowledge" && (agent || memberAgents.length > 0) && (
            <Knowledge
              key={agent?.id ?? group?.id}
              agents={agent ? agents : memberAgents}
              initialAgent={agent?.id ?? memberAgents[0]?.id ?? ""}
            />
          )}
          {panel === "routines" && (
            <Routines key={agent?.id ?? group?.id} agents={agent ? [agent] : memberAgents} />
          )}
          {panel === "workspace" && (
            <div className="tpl-workspace-links">
              <p className="muted">
                <Trans>Keep working beside the conversation.</Trans>
              </p>
              <button type="button" onClick={() => openPanel("knowledge")}>
                <BookOpen />
                <span>
                  <Trans>Memory, skills and open work</Trans>
                </span>
              </button>
              <button type="button" onClick={() => openPanel("routines")}>
                <Clock />
                <span>
                  <Trans>Scheduled work</Trans>
                </span>
              </button>
              <button type="button" onClick={() => open("/app/market")}>
                <ChartCandlestick />
                <span>
                  <Trans>Market and charts</Trans>
                </span>
              </button>
              <button type="button" onClick={() => open("/app/trading")}>
                <ArrowLeftRight />
                <span>
                  <Trans>Trading and operation journal</Trans>
                </span>
              </button>
              <button type="button" onClick={() => open("/app/board")}>
                <LayoutDashboard />
                <span>
                  <Trans>Task boards</Trans>
                </span>
              </button>
              <button type="button" onClick={() => open("/app/artifacts")}>
                <Folder />
                <span>
                  <Trans>Artifacts</Trans>
                </span>
              </button>
              <button type="button" onClick={() => openSettings("models")}>
                <SettingsIcon />
                <span>
                  <Trans>Global models</Trans>
                </span>
              </button>
            </div>
          )}
        </div>
      </ResizableSidePanel>
      <Dialog
        open={globalSettings !== null}
        onOpenChange={(value) => {
          if (!value) setGlobalSettings(null);
        }}
      >
        <DialogContent className="tpl-settings-dialog">
          <DialogHeader>
            <DialogTitle>
              <Trans>Workspace settings</Trans>
            </DialogTitle>
            <DialogDescription>
              <Trans>Shared preferences and connections for all your agents.</Trans>
            </DialogDescription>
          </DialogHeader>
          <Suspense
            fallback={
              <p role="status">
                <Trans>Loading settings…</Trans>
              </p>
            }
          >
            <Settings key={globalSettings} initialTab={globalSettings ?? "overview"} />
          </Suspense>
        </DialogContent>
      </Dialog>
      <SwitchAgentDialog
        open={switcher}
        onOpenChange={setSwitcher}
        agents={agents}
        onSelectAgent={(id) => open(`/app/${id}`)}
      />
    </div>
  );
}
