import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { lazy, Suspense, useEffect } from "react";
import { Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { usePersistentThread } from "../hooks/usePersistentThread";
import type { Agent, Resource, Run } from "../lib/api";
import { userError } from "../lib/user_error";
import { Artifacts } from "../pages/Artifacts";
import { GroupCreatePanel } from "../pages/GroupPanel";
import { Knowledge } from "../pages/Knowledge";
import { OwnerProfileSection } from "../pages/OwnerProfileSection";
import { Routines } from "../pages/Routines";
import type { SettingsTab } from "../pages/settings-sidebar";
import { AgentCreatePanel } from "../pages/shell/bot-panel";
import { ThreadViewport } from "../pages/shell/chat-context";
import { useClient } from "../providers/ClientProvider";
import { AgentsPage } from "./AgentsPage";
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

const Market = lazy(() => import("../pages/Market").then((m) => ({ default: m.Market })));
const Trading = lazy(() => import("../pages/Trading").then((m) => ({ default: m.Trading })));
const Settings = lazy(() =>
  import("../pages/SettingsOverlay").then((m) => ({ default: m.SettingsOverlay })),
);
const settingsTabs = new Set<string>([
  "overview",
  "capabilities",
  "models",
  "voice",
  "trading",
  "integrations",
  "mcp",
  "usage",
]);

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
    case "knowledge-edit":
      return t`Edit knowledge`;
    case "memory":
      return t`Memory`;
    case "goals":
      return t`Goals`;
    case "new-goal":
      return t`Edit goal`;
    case "schedules":
      return t`Scheduled tasks`;
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
    case "files":
      return t`Files`;
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

function SettingsPage({ desktop }: { desktop: boolean }) {
  const data = useShellData();
  const [params] = useSearchParams();
  const tab = params.get("tab") ?? "overview";
  const initialTab = (settingsTabs.has(tab) ? tab : "overview") as SettingsTab;
  const shortcuts = useShortcutsSheet();
  return (
    <>
      <Legacy>
        <Suspense fallback={<Loading />}>
          <Settings key={initialTab} initialTab={initialTab} />
        </Suspense>
      </Legacy>
      {desktop && (
        <div className="group">
          <button type="button" className="row" onClick={shortcuts}>
            <Icon name="keyboard" />
            <span className="body">
              <strong>
                <Trans>Keyboard shortcuts</Trans>
              </strong>
            </span>
            <span className="chevron">
              <Icon name="chev" />
            </span>
          </button>
        </div>
      )}
      <div className="group">
        <button type="button" className="row" onClick={() => void data.signOut()}>
          <Icon name="power" />
          <span className="body">
            <strong>
              <Trans>Sign out</Trans>
            </strong>
            <small className="ltr">{data.owner.email}</small>
          </span>
        </button>
      </div>
    </>
  );
}

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
        <Route path="/app/schedules" element={<SchedulesPage />} />
        <Route path="/app/new-schedule" element={<NewSchedulePage key={location.key} />} />
        <Route path="/app/tasks/:taskId" element={<TaskPage />} />
        <Route path="/app/new-task" element={<NewTaskPage key={location.key} />} />
        <Route path="/app/skills" element={<SkillsPage />} />
        <Route path="/app/skills/:skillId" element={<SkillPage />} />
        <Route path="/app/new-skill" element={<SkillPage create key={location.key} />} />
        <Route path="/app/files" element={<FilesPage />} />
        <Route path="/app/file-edit" element={<FileEditPage key={location.key} />} />
        <Route path="/app/activity" element={<ActivityPage />} />
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
        <Route
          path="/app/owner"
          element={
            <Legacy>
              <OwnerProfileSection />
            </Legacy>
          }
        />
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
