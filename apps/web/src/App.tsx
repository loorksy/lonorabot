import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  type Agent,
  type GlobalModelSettings,
  type Health,
  type Message,
  type ModelProviderId,
  type Routine,
  type Thread,
  getToken,
  saveToken,
} from "./api";
import { errorMessage, translate, type Language, type TranslationKey } from "./i18n";

type View = "chat" | "memory" | "routines" | "settings";

const modelProviders: { id: ModelProviderId; label: TranslationKey }[] = [
  { id: "xai", label: "providerXai" },
  { id: "openai", label: "providerOpenai" },
  { id: "anthropic", label: "providerAnthropic" },
  { id: "deepseek", label: "providerDeepseek" },
  { id: "zai", label: "providerZai" },
  { id: "openrouter", label: "providerOpenrouter" },
];

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function formatDate(value: string, language: Language): string {
  return new Intl.DateTimeFormat(language === "ar" ? "ar" : "en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function App() {
  const [language, setLanguage] = useState<Language>(() => {
    return localStorage.getItem("lonora.language") === "en" ? "en" : "ar";
  });
  const t = useMemo(() => (key: TranslationKey) => translate(language, key), [language]);
  const [token, setTokenState] = useState<string | null>(getToken());
  const [accountEmail, setAccountEmail] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const selectedThreadIdRef = useRef<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [modelSettings, setModelSettings] = useState<GlobalModelSettings | null>(null);
  const [modelProvider, setModelProvider] = useState<ModelProviderId>("xai");
  const [modelName, setModelName] = useState("grok-4.20-0309-non-reasoning");
  const [modelOptions, setModelOptions] = useState<{ id: string; name: string }[]>([]);
  const [view, setView] = useState<View>("chat");
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [agentName, setAgentName] = useState("");
  const [agentInstructions, setAgentInstructions] = useState("");
  const [draft, setDraft] = useState("");
  const [memory, setMemory] = useState("");
  const [routines, setRoutines] = useState<Routine[]>([]);
  const [routinePrompt, setRoutinePrompt] = useState("");
  const [routineMinutes, setRoutineMinutes] = useState(60);
  const [busy, setBusy] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [savingModel, setSavingModel] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [requestError, setRequestError] = useState("");

  const selectedAgent = agents.find((agent) => agent.id === selectedAgentId) ?? null;

  useEffect(() => {
    selectedThreadIdRef.current = selectedThreadId;
  }, [selectedThreadId]);

  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
    localStorage.setItem("lonora.language", language);
  }, [language]);

  useEffect(() => {
    void api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    const expire = () => {
      setTokenState(null);
      setAgents([]);
      setSelectedAgentId(null);
      setThreads([]);
      setSelectedThreadId(null);
      setMessages([]);
    };
    window.addEventListener("lonora:unauthorized", expire);
    return () => window.removeEventListener("lonora:unauthorized", expire);
  }, []);

  const openThread = useCallback(async (threadId: string) => {
    const response = await api.thread(threadId);
    setSelectedThreadId(threadId);
    setMessages(response.messages);
  }, []);

  const openAgent = useCallback(
    async (agentId: string) => {
      setSelectedAgentId(agentId);
      setSelectedThreadId(null);
      setMessages([]);
      setMemory("");
      setRoutines([]);
      setView("chat");
      setLoading(true);
      try {
        const result = await api.threads(agentId);
        setThreads(result);
        if (result.length > 0) await openThread(result[0].id);
      } catch {
        setRequestError("request_failed");
      } finally {
        setLoading(false);
      }
    },
    [openThread],
  );

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    try {
      const [account, agentRows, service, modelConfig] = await Promise.all([
        api.me(),
        api.agents(),
        api.health(),
        api.modelSettings(),
      ]);
      setAccountEmail(account.email);
      setAgents(agentRows);
      setHealth(service);
      setModelSettings(modelConfig);
      setModelProvider(modelConfig.provider);
      setModelName(modelConfig.model_name);
      const preferredAgent = agentRows[0];
      if (preferredAgent) await openAgent(preferredAgent.id);
      else {
        setSelectedAgentId(null);
        setThreads([]);
        setSelectedThreadId(null);
      }
    } catch {
      setRequestError("request_failed");
    } finally {
      setLoading(false);
    }
  }, [openAgent]);

  useEffect(() => {
    if (token) void loadWorkspace();
  }, [token, loadWorkspace]);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setRequestError("");
    try {
      const response = await api.login(email, password);
      saveToken(response.access_token);
      setTokenState(response.access_token);
      setPassword("");
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "unauthorized");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    saveToken(null);
    setTokenState(null);
    setAccountEmail("");
    setAgents([]);
    setSelectedAgentId(null);
    setSelectedThreadId(null);
    setThreads([]);
    setMessages([]);
  }

  async function createAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agentName.trim()) return;
    setBusy(true);
    setRequestError("");
    try {
      const agent = await api.createAgent(
        agentName.trim(),
        agentInstructions.trim() || t("defaultInstructions"),
      );
      setAgents((current) => [...current, agent]);
      setAgentName("");
      setAgentInstructions("");
      setShowAgentForm(false);
      setSelectedAgentId(agent.id);
      setSelectedThreadId(null);
      setThreads([]);
      setMessages([]);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "request_failed");
    } finally {
      setBusy(false);
    }
  }

  async function createThread() {
    if (!selectedAgentId) return;
    setBusy(true);
    setRequestError("");
    try {
      const thread = await api.createThread(selectedAgentId, t("newChat"));
      setThreads((current) => [thread, ...current]);
      setSelectedThreadId(thread.id);
      setMessages([]);
      setView("chat");
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "request_failed");
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || !selectedAgentId || busy) return;
    setBusy(true);
    setRequestError("");
    setNotice("");
    let threadId = selectedThreadId;
    try {
      if (!threadId) {
        const title = content.length > 64 ? `${content.slice(0, 61)}…` : content;
        const thread = await api.createThread(selectedAgentId, title);
        threadId = thread.id;
        setThreads((current) => [thread, ...current]);
        setSelectedThreadId(thread.id);
      }
      const queued = await api.send(threadId, content);
      setDraft("");
      const initial = await api.thread(threadId);
      setMessages(initial.messages);
      for (let attempt = 0; attempt < 180; attempt += 1) {
        await wait(1000);
        const run = await api.run(queued.run_id);
        if (run.status === "completed") {
          const latest = await api.thread(threadId);
          if (selectedThreadIdRef.current === threadId) {
            setMessages(latest.messages);
          }
          break;
        }
        if (run.status === "failed" || run.status === "cancelled") {
          const latest = await api.thread(threadId);
          if (selectedThreadIdRef.current === threadId) {
            setMessages(latest.messages);
          }
          setNotice(run.error_code || "run_failed");
          break;
        }
      }
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "request_failed");
    } finally {
      setBusy(false);
    }
  }

  async function showMemory() {
    if (!selectedAgentId) return;
    setView("memory");
    setLoading(true);
    setRequestError("");
    try {
      const result = await api.memory(selectedAgentId);
      setMemory(result.content);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "request_failed");
    } finally {
      setLoading(false);
    }
  }

  async function saveMemory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedAgentId) return;
    setBusy(true);
    setRequestError("");
    try {
      await api.saveMemory(selectedAgentId, memory);
      setNotice("saved");
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "request_failed");
    } finally {
      setBusy(false);
    }
  }

  async function showRoutines() {
    if (!selectedAgentId) return;
    setView("routines");
    setLoading(true);
    setRequestError("");
    try {
      setRoutines(await api.routines(selectedAgentId));
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "request_failed");
    } finally {
      setLoading(false);
    }
  }

  async function createRoutine(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedAgentId || !routinePrompt.trim()) return;
    setBusy(true);
    setRequestError("");
    try {
      const routine = await api.createRoutine(
        selectedAgentId,
        routinePrompt.trim(),
        Math.max(60, Math.round(routineMinutes * 60)),
      );
      setRoutines((current) => [routine, ...current]);
      setRoutinePrompt("");
      setNotice("saved");
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "request_failed");
    } finally {
      setBusy(false);
    }
  }

  async function showSettings() {
    setView("settings");
    setLoading(true);
    setRequestError("");
    try {
      const result = await api.modelSettings();
      setModelSettings(result);
      setModelProvider(result.provider);
      setModelName(result.model_name);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "request_failed");
    } finally {
      setLoading(false);
    }
  }

  async function discoverModels() {
    setDiscovering(true);
    setRequestError("");
    setModelOptions([]);
    try {
      const result = await api.discoverModels(modelProvider);
      setModelOptions(result.models);
      if (result.models.length === 0) setRequestError("model_provider_models_unavailable");
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "request_failed");
    } finally {
      setDiscovering(false);
    }
  }

  async function saveModelSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSavingModel(true);
    setRequestError("");
    setNotice("");
    try {
      const result = await api.saveModelSettings(modelProvider, modelName.trim());
      setModelSettings(result);
      setNotice("model_saved");
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "request_failed");
    } finally {
      setSavingModel(false);
    }
  }

  function switchLanguage() {
    setLanguage((current) => (current === "ar" ? "en" : "ar"));
  }

  if (!token) {
    return (
      <main className="auth-screen">
        <div className="auth-card">
          <div className="brand-mark large">L</div>
          <p className="eyebrow">{t("tagline")}</p>
          <h1>{t("brand")}</h1>
          <p className="muted">{t("signInHint")}</p>
          <form className="stack-form" onSubmit={signIn}>
            <label>
              <span>{t("email")}</span>
              <input
                dir="ltr"
                autoComplete="username"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              <span>{t("password")}</span>
              <input
                dir="ltr"
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            {requestError && <p className="form-error">{t("loginFailed")}</p>}
            <button className="button primary full" type="submit" disabled={busy}>
              {busy ? t("signingIn") : t("signIn")}
            </button>
          </form>
          <button className="text-button language-link" onClick={switchLanguage} type="button">
            {t("language")}
          </button>
        </div>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand-mark">L</div>
          <div>
            <div className="brand-name">{t("brand")}</div>
            <div className="brand-tagline">{t("tagline")}</div>
          </div>
        </div>

        <section className="sidebar-section">
          <div className="section-heading">
            <span>{t("agents")}</span>
            <button
              className="icon-button add-agent"
              aria-label={t("createAgent")}
              title={t("createAgent")}
              onClick={() => setShowAgentForm(true)}
              type="button"
            >
              +
            </button>
          </div>
          <div className="agent-list">
            {agents.map((agent) => (
              <button
                className={`agent-item ${agent.id === selectedAgentId ? "active" : ""}`}
                key={agent.id}
                onClick={() => void openAgent(agent.id)}
                type="button"
              >
                <span className="avatar">{agent.name.slice(0, 1).toUpperCase()}</span>
                <span className="agent-item-name">{agent.name}</span>
                <span className="agent-presence" />
              </button>
            ))}
            {agents.length === 0 && (
              <div className="sidebar-empty">
                <span className="empty-orbit">✳</span>
                <span>{t("noAgents")}</span>
              </div>
            )}
          </div>
        </section>

        <section className="sidebar-section conversations-section">
          <div className="section-heading">
            <span>{t("chats")}</span>
            {selectedAgent && (
              <button
                className="icon-button"
                aria-label={t("newChat")}
                title={t("newChat")}
                onClick={() => void createThread()}
                type="button"
              >
                +
              </button>
            )}
          </div>
          <div className="thread-list">
            {threads.map((thread) => (
              <button
                key={thread.id}
                className={`thread-item ${thread.id === selectedThreadId ? "active" : ""}`}
                onClick={() => {
                  setView("chat");
                  void openThread(thread.id).catch(() => setRequestError("request_failed"));
                }}
                type="button"
              >
                <span className="thread-dot" />
                <span>{thread.title}</span>
              </button>
            ))}
            {selectedAgent && threads.length === 0 && (
              <p className="thread-empty">{t("noThreads")}</p>
            )}
          </div>
        </section>

        <div className="sidebar-bottom">
          <div className={`service-chip ${health?.model_configured ? "ready" : "waiting"}`}>
            <span className="status-dot" />
            <span>{health?.model_configured ? t("modelReady") : t("modelMissing")}</span>
          </div>
          <div className="account-row">
            <span className="account-avatar">{accountEmail.slice(0, 1).toUpperCase()}</span>
            <span className="account-email" dir="ltr">{accountEmail}</span>
            <button
              className="icon-button logout-button"
              aria-label={t("signOut")}
              title={t("signOut")}
              onClick={() => void signOut()}
              type="button"
            >
              ↗
            </button>
          </div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            <span className="crumb">{selectedAgent?.name ?? t("brand")}</span>
            <span className="crumb-separator">/</span>
            <span className="current-view">{t(view)}</span>
          </div>
          <div className="topbar-actions">
            <div className={`top-status ${health?.status === "ok" ? "good" : "bad"}`}>
              <span className="status-dot" />
              <span>{health?.status === "ok" ? t("serviceReady") : t("serviceUnavailable")}</span>
            </div>
            <button className="language-button" onClick={switchLanguage} type="button">
              ◉ <span>{t("language")}</span>
            </button>
          </div>
        </header>

        {token && (
          <nav className="workspace-nav" aria-label={t("agents")}>
            <button
              className={view === "chat" ? "selected" : ""}
              onClick={() => setView("chat")}
              disabled={!selectedAgent}
              type="button"
            >
              <span>◌</span>{t("chat")}
            </button>
            <button
              className={view === "memory" ? "selected" : ""}
              onClick={() => void showMemory()}
              disabled={!selectedAgent}
              type="button"
            >
              <span>◈</span>{t("memory")}
            </button>
            <button
              className={view === "routines" ? "selected" : ""}
              onClick={() => void showRoutines()}
              disabled={!selectedAgent}
              type="button"
            >
              <span>◷</span>{t("routines")}
            </button>
            <button
              className={view === "settings" ? "selected" : ""}
              onClick={() => void showSettings()}
              type="button"
            >
              <span>⚙</span>{t("settings")}
            </button>
          </nav>
        )}

        <main className={`content-area ${view === "chat" ? "chat-content" : ""}`}>
          {!selectedAgent && view !== "settings" && (
            <div className="empty-workspace">
              <div className="hero-orbit"><span>✳</span></div>
              <p className="eyebrow">{t("tagline")}</p>
              <h1>{agents.length === 0 ? t("createFirstAgent") : t("selectAgent")}</h1>
              {agents.length === 0 && (
                <p className="muted">{t("welcomeHint")}</p>
              )}
              <button className="button primary" onClick={() => setShowAgentForm(true)} type="button">
                + {t("createAgent")}
              </button>
            </div>
          )}

          {selectedAgent && view === "chat" && (
            <div className="chat-layout">
              <div className="message-stream">
                {messages.length === 0 && (
                  <div className="conversation-welcome">
                    <div className="hero-orbit small-orbit"><span>✳</span></div>
                    <h1>{t("welcome")}</h1>
                    <p>{t("welcomeHint")}</p>
                    {!selectedThreadId && (
                      <button className="button secondary" onClick={() => void createThread()} type="button">
                        + {t("newChat")}
                      </button>
                    )}
                  </div>
                )}
                {messages.map((message) => (
                  <article className={`message-row ${message.role}`} key={message.id}>
                    <div className="message-avatar">
                      {message.role === "user" ? t("you").slice(0, 1) : "L"}
                    </div>
                    <div className="message-body">
                      <div className="message-meta">
                        <span>{message.role === "user" ? t("you") : t("assistant")}</span>
                        <time dir="auto">{formatDate(message.created_at, language)}</time>
                      </div>
                      <div className="message-bubble" dir="auto">{message.content}</div>
                    </div>
                  </article>
                ))}
                {busy && messages.length > 0 && (
                  <div className="thinking-row">
                    <span className="thinking-indicator"><i /><i /><i /></span>
                    <span>{t("sending")}</span>
                  </div>
                )}
                <div className="stream-spacer" />
              </div>
              <form className="composer-wrap" onSubmit={(event) => void sendMessage(event)}>
                {notice && (
                  <div className="notice">{notice === "saved" ? t("saved") : errorMessage(notice, language)}</div>
                )}
                {requestError && <div className="notice error">{errorMessage(requestError, language)}</div>}
                <div className="composer">
                  <textarea
                    dir="auto"
                    aria-label={t("messagePlaceholder")}
                    placeholder={t("messagePlaceholder")}
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                    rows={1}
                    disabled={busy}
                  />
                  <button className="send-button" type="submit" aria-label={t("send")} disabled={!draft.trim() || busy}>
                    ↑
                  </button>
                </div>
                <div className="composer-footer"><span>{t("welcomeHint")}</span></div>
              </form>
            </div>
          )}

          {selectedAgent && view === "memory" && (
            <section className="panel-view">
              <div className="panel-heading">
                <div className="panel-icon memory-icon">◈</div>
                <div><h1>{t("memoryTitle")}</h1><p>{t("memoryHint")}</p></div>
              </div>
              <form className="panel-card" onSubmit={(event) => void saveMemory(event)}>
                <label htmlFor="agent-memory">{t("memory")}</label>
                <textarea
                  id="agent-memory"
                  dir="auto"
                  value={memory}
                  onChange={(event) => setMemory(event.target.value)}
                  rows={12}
                  maxLength={30000}
                  disabled={loading}
                />
                {requestError && <div className="notice error">{errorMessage(requestError, language)}</div>}
                {notice && <div className="notice">{t("saved")}</div>}
                <button className="button primary" type="submit" disabled={busy || loading}>
                  {busy ? t("saving") : t("saveMemory")}
                </button>
              </form>
            </section>
          )}

          {selectedAgent && view === "routines" && (
            <section className="panel-view">
              <div className="panel-heading">
                <div className="panel-icon routine-icon">◷</div>
                <div><h1>{t("routines")}</h1><p>{t("routineHint")}</p></div>
              </div>
              <form className="panel-card routine-form" onSubmit={(event) => void createRoutine(event)}>
                <label htmlFor="routine-prompt">{t("routinePrompt")}</label>
                <textarea
                  id="routine-prompt"
                  dir="auto"
                  value={routinePrompt}
                  onChange={(event) => setRoutinePrompt(event.target.value)}
                  rows={3}
                  maxLength={8000}
                />
                <label htmlFor="routine-interval">{t("interval")}</label>
                <input
                  id="routine-interval"
                  className="interval-input"
                  type="number"
                  min={1}
                  max={525600}
                  value={routineMinutes}
                  onChange={(event) => setRoutineMinutes(Number(event.target.value))}
                  dir="ltr"
                />
                {requestError && <div className="notice error">{errorMessage(requestError, language)}</div>}
                <button className="button primary" type="submit" disabled={busy || !routinePrompt.trim()}>
                  {busy ? t("creating") : t("createRoutine")}
                </button>
              </form>
              <div className="routine-list">
                {routines.map((routine) => (
                  <article className="routine-card" key={routine.id}>
                    <div className="routine-card-icon">◷</div>
                    <div className="routine-card-main">
                      <strong dir="auto">{routine.prompt}</strong>
                      <span>{t("nextRun")}: {formatDate(routine.next_run_at, language)}</span>
                    </div>
                    <span className="routine-state">{routine.enabled ? t("enabled") : "—"}</span>
                  </article>
                ))}
                {!loading && routines.length === 0 && <p className="muted empty-routines">{t("noRoutines")}</p>}
              </div>
            </section>
          )}

          {view === "settings" && (
            <section className="panel-view settings-view">
              <div className="panel-heading">
                <div className="panel-icon settings-icon">⚙</div>
                <div><h1>{t("globalModels")}</h1><p>{t("globalModelsHint")}</p></div>
              </div>
              <form className="panel-card settings-card" onSubmit={(event) => void saveModelSettings(event)}>
                <div className={`key-status ${modelSettings?.key_configured ? "configured" : "missing"}`}>
                  <span className="status-dot" />
                  <span>{modelSettings?.key_configured ? t("apiKeyReady") : t("apiKeyMissing")}</span>
                </div>
                <p className="key-hint">{t("apiKeyHint")}</p>
                <label htmlFor="model-provider">{t("provider")}</label>
                <select
                  id="model-provider"
                  value={modelProvider}
                  onChange={(event) => {
                    setModelProvider(event.target.value as ModelProviderId);
                    setModelOptions([]);
                  }}
                >
                  {modelProviders.map((option) => (
                    <option key={option.id} value={option.id}>{t(option.label)}</option>
                  ))}
                </select>
                <div className="label-row">
                  <label htmlFor="model-name">{t("modelName")}</label>
                  <button className="text-button" type="button" onClick={() => void discoverModels()} disabled={discovering || savingModel}>
                    {discovering ? t("discoveringModels") : t("discoverModels")}
                  </button>
                </div>
                <input
                  id="model-name"
                  className="model-name-input"
                  value={modelName}
                  onChange={(event) => setModelName(event.target.value)}
                  maxLength={200}
                  dir="ltr"
                  required
                />
                {modelOptions.length > 0 && (
                  <div className="model-options" aria-label={t("discoverModels")}>
                    {modelOptions.map((option) => (
                      <button
                        key={option.id}
                        className={`model-option ${modelName === option.id ? "selected" : ""}`}
                        type="button"
                        onClick={() => setModelName(option.id)}
                      >
                        <strong dir="ltr">{option.id}</strong>
                        {option.name !== option.id && <span dir="auto">{option.name}</span>}
                      </button>
                    ))}
                  </div>
                )}
                {requestError && <div className="notice error">{errorMessage(requestError, language)}</div>}
                {notice && <div className="notice">{t("modelSaved")}</div>}
                <button className="button primary" type="submit" disabled={savingModel || discovering || !modelName.trim()}>
                  {savingModel ? t("saving") : t("saveSettings")}
                </button>
              </form>
            </section>
          )}
        </main>
      </section>

      {showAgentForm && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setShowAgentForm(false);
        }}>
          <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="new-agent-title">
            <div className="modal-heading">
              <div className="panel-icon"><span>✳</span></div>
              <div><h2 id="new-agent-title">{t("createAgent")}</h2><p>{t("createFirstAgent")}</p></div>
              <button className="icon-button close-modal" aria-label={t("cancel")} onClick={() => setShowAgentForm(false)} type="button">×</button>
            </div>
            <form className="stack-form" onSubmit={(event) => void createAgent(event)}>
              <label>
                <span>{t("agentName")}</span>
                <input value={agentName} onChange={(event) => setAgentName(event.target.value)} maxLength={80} required autoFocus />
              </label>
              <label>
                <span>{t("instructions")}</span>
                <textarea
                  dir="auto"
                  placeholder={t("agentInstructionsHint")}
                  value={agentInstructions}
                  onChange={(event) => setAgentInstructions(event.target.value)}
                  rows={4}
                  maxLength={8000}
                />
              </label>
              {requestError && <div className="notice error">{errorMessage(requestError, language)}</div>}
              <div className="form-actions">
                <button className="button secondary" onClick={() => setShowAgentForm(false)} type="button">{t("cancel")}</button>
                <button className="button primary" type="submit" disabled={busy || !agentName.trim()}>
                  {busy ? t("creating") : t("create")}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
