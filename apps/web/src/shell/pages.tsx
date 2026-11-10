import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation, useParams, useSearchParams } from "react-router-dom";
import { usePersistentThread } from "../hooks/usePersistentThread";
import type { Agent, Resource, Run } from "../lib/api";
import { userError } from "../lib/user_error";
import { ActivityList } from "../pages/ActivityList";
import { Artifacts } from "../pages/Artifacts";
import { BoardPage } from "../pages/Board";
import { GroupCreatePanel } from "../pages/GroupPanel";
import { Knowledge } from "../pages/Knowledge";
import { Routines } from "../pages/Routines";
import type { SettingsTab } from "../pages/settings-sidebar";
import { AgentCreatePanel } from "../pages/shell/bot-panel";
import { ThreadViewport } from "../pages/shell/chat-context";
import { useClient } from "../providers/ClientProvider";
import { AgentsPage } from "./AgentsPage";
import { useShellData } from "./data";
import { Lab } from "./Lab";
import { ArchivedPage, ChatList } from "./lists/ChatList";
import { type SearchTab, UnifiedSearch } from "./lists/UnifiedSearch";
import { useNavigation } from "./navigation";
import { DEV_ROUTES, type Page, type Root } from "./routes";
import { useShortcutsSheet } from "./ShortcutsSheet";
import { SkChat, SkChats } from "./Skeleton";
import { NotFoundPage } from "./StatePage";
import {
  BrokerAccountPage,
  BrokerFormPage,
  McpFormPage,
  ProviderFormPage,
  ProvidersPage,
} from "./settings/ConnectionPages";
import { AccessibilityPage, PrivacyPage, StoragePage } from "./settings/DevicePages";
import { IntegrationsPage } from "./settings/IntegrationsPage";
import { CommunicationPage, NotifyPage } from "./settings/NotifyPages";
import { OwnerPage } from "./settings/OwnerPage";
import { SettingsRoot } from "./settings/SettingsRoot";
import { UsageDetailPage, UsagePage } from "./settings/UsagePage";

const Market = lazy(() => import("../pages/Market").then((m) => ({ default: m.Market })));
const Trading = lazy(() => import("../pages/Trading").then((m) => ({ default: m.Trading })));
const Settings = lazy(() =>
  import("../pages/SettingsOverlay").then((m) => ({ default: m.SettingsOverlay })),
);
/** Old settings tabs: the ones with a reference page go there; models and voice keep the
 * existing screen until their phase (model routing and the trading controls have no reference
 * home yet, OQ47; voice is phase 6). */
const settingsTabs = new Set<string>(["models", "voice", "trading"]);
const settingsMoved: Readonly<Record<string, string>> = {
  capabilities: "/app/integrations",
  integrations: "/app/integrations",
  mcp: "/app/integrations",
  usage: "/app/usage",
  overview: "/app/settings",
};

const Loading = () => (
  <p className="note" role="status">
    <Trans>Loading…</Trans>
  </p>
);
/** Existing screens keep their palette until their phase ports them. */
const Legacy = ({ children }: { children: React.ReactNode }) => (
  <div className="legacy-surface">{children}</div>
);

export function pageTitle(page: Page): string {
  switch (page) {
    case "agents":
      return t`Agents`;
    case "artifacts":
      return t`Files`;
    case "archived":
      return t`Archived`;
    case "market":
      return t`Market`;
    case "trading":
      return t`Trades`;
    case "routines":
      return t`Routines`;
    case "knowledge":
      return t`Knowledge`;
    case "new-agent":
      return t`Create agent`;
    case "new-group":
      return t({ message: "Create group", context: "page title" });
    case "owner":
      return t({ message: "Profile", context: "owner" });
    case "accessibility":
      return t`Accessibility`;
    case "notify-settings":
      return t`Notifications and contact`;
    case "communication":
      return t`Proactive contact`;
    case "integrations":
      return t`Integrations`;
    case "providers":
      return t`Model providers`;
    case "provider":
      return t`Add an AI provider`;
    case "mcp":
      return t`Add MCP`;
    case "broker":
      return t`Link the broker`;
    case "broker-account":
      return t`Trading account`;
    case "usage":
      return t`Overall usage`;
    case "usage-detail":
      return t`Usage details`;
    case "storage":
      return t`Storage and data`;
    case "privacy":
      return t`Privacy and security`;
    default:
      return t`Lab`;
  }
}

/* The four main tabs. A pager ghost renders the same page with the same data. */
export function RootPage({
  root,
  search,
  onTab,
  desktop,
}: {
  root: Root;
  search: { expanded: boolean; query: string; tab: SearchTab };
  onTab: (tab: SearchTab) => void;
  desktop: boolean;
}) {
  const data = useShellData();
  if (root === "chats") {
    if (search.expanded)
      return <UnifiedSearch query={search.query} tab={search.tab} onTab={onTab} />;
    const loading = data.agentsLoading || data.groupsLoading || data.inboxLoading;
    if (loading && !data.agents.length && !data.groups.length) return <SkChats />;
    return <ChatList />;
  }
  if (root === "updates")
    return (
      <Legacy>
        <ActivityList agents={data.agents} />
      </Legacy>
    );
  if (root === "tasks")
    return (
      <Legacy>
        <BoardPage agents={data.agents} />
      </Legacy>
    );
  return <SettingsPage desktop={desktop} />;
}

function SettingsPage({ desktop: _desktop }: { desktop: boolean }) {
  const [params] = useSearchParams();
  const tab = params.get("tab");
  if (tab && Object.hasOwn(settingsMoved, tab) && tab !== "overview")
    return <Navigate to={settingsMoved[tab]} replace />;
  if (tab && settingsTabs.has(tab))
    return (
      <Legacy>
        <Suspense fallback={<Loading />}>
          <Settings key={tab} initialTab={tab as SettingsTab} />
        </Suspense>
      </Legacy>
    );
  return <SettingsRoot />;
}

const ItemPage = ({ render }: { render: (item: string) => React.ReactNode }) => {
  const { item = "" } = useParams();
  return <>{render(item)}</>;
};

/* The inner pages: the existing screens, each under its reference title. */
export function DetailPages({
  onMaintenance,
  onUpdateBar,
}: {
  onMaintenance: () => void;
  onUpdateBar: () => void;
}) {
  const data = useShellData();
  const nav = useNavigation();
  const first = data.agents[0]?.id ?? "";
  const [params] = useSearchParams();
  const location = useLocation();
  // A search hit opens the knowledge of its agent.
  const knowledgeAgent = data.agents.find((agent) => agent.id === params.get("agent"))?.id;
  // «مجموعة من المحددين» prefills the members and the name.
  const draft = (location.state ?? {}) as { members?: string[]; name?: string };
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route
          path="/app/artifacts"
          element={
            <Legacy>
              <Artifacts />
            </Legacy>
          }
        />
        <Route
          path="/app/artifacts/:artifactId"
          element={
            <Legacy>
              <Artifacts />
            </Legacy>
          }
        />
        <Route path="/app/archived" element={<ArchivedPage />} />
        <Route path="/app/agents" element={<AgentsPage />} />
        <Route
          path="/app/market"
          element={
            <Legacy>
              <Market agents={data.agents} />
            </Legacy>
          }
        />
        <Route
          path="/app/trading"
          element={
            <Legacy>
              <Trading />
            </Legacy>
          }
        />
        <Route
          path="/app/routines"
          element={
            <Legacy>
              <Routines agents={data.agents} />
            </Legacy>
          }
        />
        <Route
          path="/app/knowledge"
          element={
            <Legacy>
              <Knowledge agents={data.agents} initialAgent={knowledgeAgent || first} />
            </Legacy>
          }
        />
        <Route
          path="/app/new-agent"
          element={
            <AgentCreatePanel
              onCreated={(row) => {
                data.refresh();
                nav.go(`/app/${row.id}`, { replace: true });
              }}
            />
          }
        />
        <Route
          path="/app/new-group"
          element={
            <Legacy>
              <GroupCreatePanel
                key={location.key}
                agents={data.agents}
                initialMembers={draft.members}
                initialName={draft.name}
                onCreated={(row) => {
                  data.addGroup(row);
                  data.refresh();
                  nav.go(`/app/g/${row.id}`, { replace: true });
                }}
              />
            </Legacy>
          }
        />
        <Route path="/app/owner" element={<OwnerPage />} />
        <Route path="/app/accessibility" element={<AccessibilityPage />} />
        <Route path="/app/notify-settings" element={<NotifyPage />} />
        <Route
          path="/app/communication/:item"
          element={<ItemPage render={(item) => <CommunicationPage key={item} agentId={item} />} />}
        />
        <Route path="/app/integrations" element={<IntegrationsPage />} />
        <Route path="/app/providers" element={<ProvidersPage />} />
        <Route path="/app/provider" element={<ProviderFormPage />} />
        <Route
          path="/app/provider/:item"
          element={<ItemPage render={(item) => <ProviderFormPage key={item} initial={item} />} />}
        />
        <Route path="/app/mcp" element={<McpFormPage />} />
        <Route path="/app/broker" element={<BrokerFormPage />} />
        <Route
          path="/app/broker-account/:item"
          element={
            <ItemPage render={(item) => <BrokerAccountPage key={item} connectionId={item} />} />
          }
        />
        <Route path="/app/usage" element={<UsagePage />} />
        <Route
          path="/app/usage-detail/:item"
          element={<ItemPage render={(item) => <UsageDetailPage key={item} agentId={item} />} />}
        />
        <Route path="/app/storage" element={<StoragePage />} />
        <Route path="/app/privacy" element={<PrivacyPage />} />
        <Route
          path="/app/lab"
          element={
            import.meta.env.DEV && DEV_ROUTES.has("lab") ? (
              <Lab onMaintenance={onMaintenance} onUpdateBar={onUpdateBar} />
            ) : (
              <NotFoundPage />
            )
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}

/* The conversation body: the existing message list and composer, mounted as they are. */
function AgentConversation({
  agent,
  agents,
  knownRuns,
  onOpenChart,
}: {
  agent: Agent;
  agents: Agent[];
  knownRuns: Run[];
  onOpenChart: (id: string) => void;
}) {
  const [params, setParams] = useSearchParams();
  const { refresh } = useClient();
  const { thread, threads, error } = usePersistentThread(agent.id, params.get("thread"));
  if (error != null && !thread)
    return (
      <div className="tpl-empty">
        <p role="alert">{userError(error)}</p>
        <button type="button" onClick={refresh}>
          <Trans>Retry</Trans>
        </button>
      </div>
    );
  if (!thread) return <SkChat />;
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
      <ThreadViewport
        key={thread.id}
        threadId={thread.id}
        aroundSeq={aroundOf(params)}
        agentId={agent.id}
        agents={agents}
        knownRuns={knownRuns}
        onOpenChart={onOpenChart}
      />
    </>
  );
}

const aroundOf = (params: URLSearchParams) => {
  const seq = Number(params.get("around"));
  return Number.isInteger(seq) && seq > 0 ? seq : undefined;
};

export function ChatPane({
  agent,
  group,
  memberAgents,
  onOpenChart,
}: {
  agent?: Agent;
  group?: Resource;
  memberAgents: Agent[];
  onOpenChart: (id: string) => void;
}) {
  const data = useShellData();
  const [params] = useSearchParams();
  if (group)
    return (
      <Legacy>
        {group.state?.thread_id ? (
          <ThreadViewport
            key={String(group.state.thread_id)}
            threadId={String(group.state.thread_id)}
            aroundSeq={aroundOf(params)}
            agentId=""
            knownRuns={data.runs}
            conversationName={String(group.payload.name)}
            onOpenChart={onOpenChart}
            agents={memberAgents}
          />
        ) : (
          <NotFoundPage />
        )}
      </Legacy>
    );
  if (!agent) return data.agentsLoading ? <SkChat /> : <NotFoundPage />;
  return (
    <Legacy>
      <AgentConversation
        key={agent.id}
        agent={agent}
        agents={data.agents}
        knownRuns={data.runs}
        onOpenChart={onOpenChart}
      />
    </Legacy>
  );
}

/** `?settings=tab` on any route (the composer's /settings, links) opens the settings page. */
export function useSettingsRedirect() {
  const [params] = useSearchParams();
  const nav = useNavigation();
  const tab = params.get("settings");
  useEffect(() => {
    if (tab) nav.go(`/app/settings?tab=${encodeURIComponent(tab)}`, { replace: true });
  }, [tab, nav]);
}
