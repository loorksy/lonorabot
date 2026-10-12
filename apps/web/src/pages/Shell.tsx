import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import {
  Activity as ActivityIcon,
  ArrowLeftRight,
  BookOpen,
  ChartCandlestick,
  Clock,
  Folder,
  LogOut,
  MessageSquare,
  PanelLeftClose,
  Plus,
  Search as SearchIcon,
  Settings as SettingsIcon,
  Users,
} from "lucide-react";
import { lazy, type ReactNode, Suspense, useEffect, useState } from "react";
import { AgentAvatar } from "../components/agents/AgentAvatar";
import { AgentPanel } from "../components/agents/AgentPanel";
import { AgentSettings } from "../components/agents/AgentSettings";
import { ThreadViewport } from "../components/chat/ThreadViewport";
import { useAgents } from "../hooks/useAgents";
import { useTheme } from "../hooks/useTheme";
import { useThreads } from "../hooks/useThreads";
import type { Agent } from "../lib/api";
import { auth } from "../lib/auth";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import { Activity } from "./Activity";
import { Artifacts } from "./Artifacts";
import { Group } from "./Group";
import { Knowledge } from "./Knowledge";

const Market = lazy(() => import("./Market").then((module) => ({ default: module.Market })));

import { Routines } from "./Routines";
import { Search } from "./Search";

const Settings = lazy(() => import("./Settings").then((module) => ({ default: module.Settings })));
const Trading = lazy(() => import("./Trading").then((module) => ({ default: module.Trading })));

type Page =
  | "chat"
  | "groups"
  | "activity"
  | "knowledge"
  | "routines"
  | "search"
  | "market"
  | "trading"
  | "artifacts"
  | "settings";
export function Shell({ onLogout }: { onLogout: () => void }) {
  useTheme();
  const { connected } = useClient();
  const { agents, create, error: agentError } = useAgents();
  const [selected, setSelected] = useState("");
  const [threadId, setThreadId] = useState("");
  const threads = useThreads(selected);
  const [page, setPage] = useState<Page>("chat");
  const [settings, setSettings] = useState<Agent | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [color, setColor] = useState("#7c83fd");
  const [shape, setShape] = useState("orb");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [sidebar, setSidebar] = useState(() => window.innerWidth > 650);
  const agent = agents.find((a) => a.id === selected);
  useEffect(() => {
    const query = window.matchMedia("(max-width:650px)");
    const resized = () => {
      if (query.matches) setSidebar(false);
    };
    query.addEventListener("change", resized);
    return () => query.removeEventListener("change", resized);
  }, []);
  useEffect(() => {
    if (!selected && agents.length) setSelected(agents[0].id);
  }, [agents, selected]);
  const nav: [Page, ReactNode, ReactNode][] = [
    ["chat", <MessageSquare key="2445" />, <Trans key="2464">Conversations</Trans>],
    ["groups", <Users key="2510" />, <Trans key="2521">Groups</Trans>],
    ["activity", <ActivityIcon key="2562" />, <Trans key="2580">Activity</Trans>],
    ["knowledge", <BookOpen key="2624" />, <Trans key="2638">Knowledge</Trans>],
    ["routines", <Clock key="2682" />, <Trans key="2693">Routines</Trans>],
    ["search", <SearchIcon key="2734" />, <Trans key="2750">Search</Trans>],
    ["market", <ChartCandlestick key="2789" />, <Trans key="2811">Market</Trans>],
    ["trading", <ArrowLeftRight key="2851" />, <Trans key="2871">Trading</Trans>],
    ["artifacts", <Folder key="2914" />, <Trans key="2926">Artifacts</Trans>],
    ["settings", <SettingsIcon key="2970" />, <Trans key="2988">Settings</Trans>],
  ];
  async function newThread() {
    if (!agent) return;
    try {
      const row = await threads.create(agent.id);
      setThreadId(row.id);
      setPage("chat");
    } catch (e) {
      setError(e);
    }
  }
  return (
    <div className={`shell ${sidebar ? "" : "sidebar-collapsed"}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">L</div>
          <strong>Lonora</strong>
          <span
            className={`connection-dot ${connected ? "online" : ""}`}
            title={connected ? t`Connected` : t`Reconnecting`}
          />
        </div>
        <nav className="primary-nav">
          {nav.map(([key, icon, label]) => (
            <button
              type="button"
              className={page === key ? "selected" : ""}
              key={key}
              onClick={() => setPage(key)}
            >
              {icon}
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-heading">
          <span>
            <Trans>Agents</Trans>
          </span>
          <button type="button" aria-label={t`Create agent`} onClick={() => setCreating(true)}>
            <Plus />
          </button>
        </div>
        <div className="agent-list">
          {agents.map((a) => (
            <button
              type="button"
              key={a.id}
              className={selected === a.id ? "selected" : ""}
              onClick={() => {
                setSelected(a.id);
                setThreadId("");
                setPage("chat");
              }}
            >
              <AgentAvatar agent={a} />
              <span>{a.name}</span>
              {a.parent_id && (
                <small>
                  <Trans>Child</Trans>
                </small>
              )}
            </button>
          ))}
        </div>
        {agent && (
          <>
            <div className="sidebar-heading">
              <span>
                <Trans>Conversations</Trans>
              </span>
              <button
                type="button"
                aria-label={t`New conversation`}
                onClick={() => void newThread()}
              >
                <Plus />
              </button>
            </div>
            <div className="thread-list">
              {threads.threads
                .filter((th) => !th.group_id)
                .map((th) => (
                  <button
                    type="button"
                    className={threadId === th.id ? "selected" : ""}
                    key={th.id}
                    onClick={() => {
                      setThreadId(th.id);
                      setPage("chat");
                    }}
                  >
                    <MessageSquare />
                    <span>{th.title || t`New conversation`}</span>
                  </button>
                ))}
            </div>
          </>
        )}
        <button
          type="button"
          className="logout"
          onClick={() => void auth.logout().then(onLogout).catch(setError)}
        >
          <LogOut />
          <Trans>Sign out</Trans>
        </button>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <button
            type="button"
            aria-label={t`Toggle sidebar`}
            onClick={() => setSidebar((v) => !v)}
          >
            <PanelLeftClose />
          </button>
          <span>{nav.find(([key]) => key === page)?.[2]}</span>
          <span className="topbar-end muted">
            <Trans>Persistent workspace</Trans>
          </span>
        </header>
        {(error ?? agentError) != null && (
          <p className="notice" role="alert">
            {userError(error ?? agentError)}
          </p>
        )}
        {page === "chat" ? (
          <div className="conversation">
            {agent && <AgentPanel agent={agent} onSettings={() => setSettings(agent)} />}
            <div className="conversation-content">
              {threadId && agent ? (
                <ThreadViewport
                  key={threadId}
                  threadId={threadId}
                  agentId={agent.id}
                  agents={agents}
                />
              ) : (
                <div className="empty welcome">
                  <div className="brand-mark large">L</div>
                  <h1>
                    <Trans>Welcome to Lonora</Trans>
                  </h1>
                  <p>
                    <Trans>
                      Persistent agents, shared knowledge and continuous work in one place.
                    </Trans>
                  </p>
                  <button
                    type="button"
                    className="primary"
                    onClick={() => (agent ? void newThread() : setCreating(true))}
                  >
                    {agent ? (
                      <Trans>Start a conversation</Trans>
                    ) : (
                      <Trans>Create your first agent</Trans>
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="page-content">
            <Suspense
              fallback={
                <p role="status">
                  <Trans>Loading</Trans>
                </p>
              }
            >
              {page === "groups" ? (
                <Group agents={agents} />
              ) : page === "activity" ? (
                <Activity agents={agents} />
              ) : page === "knowledge" ? (
                <Knowledge agents={agents} initialAgent={selected} />
              ) : page === "routines" ? (
                <Routines agents={agents} />
              ) : page === "search" ? (
                <Search />
              ) : page === "market" ? (
                <Market agents={agents} />
              ) : page === "trading" ? (
                <Trading />
              ) : page === "artifacts" ? (
                <Artifacts />
              ) : (
                <Settings />
              )}
            </Suspense>
          </div>
        )}
      </main>
      {settings && (
        <AgentSettings key={settings.id} agent={settings} onClose={() => setSettings(null)} />
      )}{" "}
      {creating && (
        <div className="modal-backdrop">
          <form
            className="modal"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                const a = await create(name, shape, color);
                setSelected(a.id);
                setThreadId("");
                setName("");
                setCreating(false);
                setPage("chat");
              } catch (err) {
                setError(err);
              } finally {
                setBusy(false);
              }
            }}
          >
            <h2>
              <Trans>Create agent</Trans>
            </h2>
            <label>
              <Trans>Name</Trans>
              <input
                required
                maxLength={80}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <div className="form-grid">
              <label>
                <Trans>Avatar shape</Trans>
                <select value={shape} onChange={(e) => setShape(e.target.value)}>
                  <option value="orb">
                    <Trans>Orb</Trans>
                  </option>
                  <option value="square">
                    <Trans>Square</Trans>
                  </option>
                  <option value="diamond">
                    <Trans>Diamond</Trans>
                  </option>
                </select>
              </label>
              <label>
                <Trans>Color</Trans>
                <input type="color" value={color} onChange={(e) => setColor(e.target.value)} />
              </label>
            </div>
            <div className="actions">
              <button type="button" onClick={() => setCreating(false)}>
                <Trans>Close</Trans>
              </button>
              <button type="submit" className="primary" disabled={busy}>
                <Trans>Create agent</Trans>
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
