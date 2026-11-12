import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation, useParams, useSearchParams } from "react-router-dom";
import { ChatPrefsPage } from "../conversation/ChatPrefsPage";
import { Conversation } from "../conversation/Conversation";
import { usePersistentThread } from "../hooks/usePersistentThread";
import type { Agent, Resource, Run } from "../lib/api";
import { userError } from "../lib/user_error";
import { Artifacts } from "../pages/Artifacts";
import { Knowledge } from "../pages/Knowledge";
import type { SettingsTab } from "../pages/settings-sidebar";
import { AgentCreatePanel } from "../pages/shell/bot-panel";
import { useClient } from "../providers/ClientProvider";
import { AgentsPage } from "./AgentsPage";
import { AgentPage } from "./agent/AgentPage";
import { GroupPage, NewGroupPage } from "./agent/GroupPage";
import { IdentityPage } from "./agent/IdentityPage";
import { RecoveryPage } from "./agent/RecoveryPage";
import { scoped } from "./agent/scope";
import { TradesPage } from "./agent/TradesPage";
import { CallPage, IncomingPage } from "./call/CallPages";
import { useShellData } from "./data";
import "./domain/domain.css";
import { FileEditPage, FilesPage } from "./domain/FilesPages";
import {
  GoalEditPage,
  GoalsPage,
  KnowledgeEditPage,
  KnowledgePage,
} from "./domain/GoalsKnowledgePages";
import { NewSchedulePage, SchedulesPage } from "./domain/SchedulesPages";
import { SkillPage, SkillsPage } from "./domain/SkillsPages";
import { NewTaskPage, TaskPage, TasksPage } from "./domain/TasksPages";
import { ActivityPage, UpdatesPage } from "./domain/UpdatesPages";
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
import { RunningPage } from "./settings/RunningPage";
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
    case "agent":
      return t`Agent info`;
    case "identity":
      return t`Agent identity`;
    case "trades":
      return t({ message: "Trades", context: "agent page" });
    case "group":
      return t({ message: "Groups", context: "page title" });
    case "recovery":
      return t`Outage and recovery`;
    case "artifacts":
      return t`Files`;
    case "archived":
      return t`Archived`;
    case "market":
      return t`Market`;
    case "trading":
      return t`Trades`;
    case "routines":
      return t`Scheduled tasks`;
    case "knowledge":
      return t`Knowledge`;
    case "knowledge-edit":
      return t`Edit knowledge`;
    case "memory":
      return t`Memory`;
    case "goals":
      return t`Goals`;
    case "new-goal":
      return t`Edit goal`;
    case "new-schedule":
      return t`Schedule a task`;
    case "task":
      return t`Task details`;
    case "new-task":
      return t({ message: "Create task", context: "page title" });
    case "skills":
      return t`Skills`;
    case "skill":
      return t`Edit skill`;
    case "new-skill":
      return t({ message: "Create a skill", context: "page title" });
    case "file-edit":
      return t`Edit file`;
    case "activity":
      return t`Activity log`;
    case "new-agent":
      return t`Create agent`;
    case "new-group":
      return t({ message: "Create group", context: "page title" });
    case "owner":
      return t({ message: "Profile", context: "owner" });
    case "running":
      return t`What is running`;
    case "accessibility":
      return t`Accessibility`;
    case "chat-prefs":
      return t`Chat experience`;
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
    case "call":
      return t({ message: "Call", context: "page title" });
    case "incoming":
      return t`Incoming call`;
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
  if (root === "updates") return <UpdatesPage />;
  if (root === "tasks") return <TasksPage />;
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
        {/* «الملفات»: an agent's (?agent=) or the workspace's text files (Q36). */}
        <Route path="/app/artifacts" element={<FilesPage />} />
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
        <Route path="/app/agent/:id" element={<AgentItemPage page="agent" />} />
        <Route path="/app/identity/:id" element={<AgentItemPage page="identity" />} />
        <Route path="/app/trades/:id" element={<AgentItemPage page="trades" />} />
        <Route path="/app/group/:id" element={<AgentItemPage page="group" />} />
        <Route path="/app/recovery" element={scoped(<RecoveryPage />)} />
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
        {/* «المهام المجدولة»: one agent's (?agent=) schedules. */}
        <Route path="/app/routines" element={<SchedulesPage />} />
        <Route path="/app/knowledge" element={<KnowledgePage />} />
        <Route path="/app/knowledge-edit" element={<KnowledgeEditPage key={location.key} />} />
        {/* The memory editor and the skills catalog keep their screen until their pages arrive. */}
        <Route
          path="/app/memory"
          element={
            <Legacy>
              <Knowledge agents={data.agents} initialAgent={knowledgeAgent || first} />
            </Legacy>
          }
        />
        <Route path="/app/goals" element={<GoalsPage />} />
        <Route path="/app/new-goal" element={<GoalEditPage key={location.key} />} />
        <Route path="/app/new-schedule" element={<NewSchedulePage key={location.key} />} />
        <Route path="/app/tasks/:taskId" element={<TaskPage />} />
        <Route path="/app/new-task" element={<NewTaskPage key={location.key} />} />
        <Route path="/app/skills" element={<SkillsPage />} />
        <Route path="/app/skills/:skillId" element={<SkillPage />} />
        <Route path="/app/new-skill" element={<SkillPage create key={location.key} />} />
        <Route path="/app/file-edit" element={<FileEditPage key={location.key} />} />
        <Route path="/app/activity" element={<ActivityPage />} />
        <Route path="/app/call" element={<CallPage />} />
        <Route path="/app/incoming/:callId" element={<IncomingPage />} />
        <Route
          path="/app/new-agent"
          element={scoped(
            <AgentCreatePanel
              onCreated={(row) => {
                data.refresh();
                nav.go(`/app/agent/${row.id}`, { replace: true });
              }}
            />,
          )}
        />
        <Route
          path="/app/new-group"
          element={scoped(
            <NewGroupPage
              key={location.key}
              initialMembers={draft.members}
              initialName={draft.name}
            />,
          )}
        />
        <Route path="/app/owner" element={<OwnerPage />} />
        <Route path="/app/running" element={<RunningPage />} />
        <Route path="/app/accessibility" element={<AccessibilityPage />} />
        <Route path="/app/chat-prefs" element={<ChatPrefsPage />} />
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

/** The pages of one agent or group, keyed by it so a new item starts fresh. */
function AgentItemPage({ page }: { page: "agent" | "identity" | "trades" | "group" }) {
  const { id = "" } = useParams();
  if (page === "agent") return scoped(<AgentPage key={id} agentId={id} />);
  if (page === "identity") return scoped(<IdentityPage key={id} agentId={id} />);
  if (page === "trades") return scoped(<TradesPage key={id} agentId={id} />);
  return scoped(<GroupPage key={id} groupId={id} />);
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
      <Conversation
        key={thread.id}
        threadId={thread.id}
        aroundSeq={aroundOf(params)}
        jumpTo={params.get("card") ?? undefined}
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
    return group.state?.thread_id ? (
      <Conversation
        key={String(group.state.thread_id)}
        threadId={String(group.state.thread_id)}
        aroundSeq={aroundOf(params)}
        jumpTo={params.get("card") ?? undefined}
        agentId=""
        knownRuns={data.runs}
        conversationName={String(group.payload.name)}
        onOpenChart={onOpenChart}
        agents={memberAgents}
        groupLead={(group.payload.lead_agent_id as string | undefined) ?? memberAgents[0]?.id}
      />
    ) : (
      <NotFoundPage />
    );
  if (!agent) return data.agentsLoading ? <SkChat /> : <NotFoundPage />;
  return (
    <AgentConversation
      key={agent.id}
      agent={agent}
      agents={data.agents}
      knownRuns={data.runs}
      onOpenChart={onOpenChart}
    />
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
