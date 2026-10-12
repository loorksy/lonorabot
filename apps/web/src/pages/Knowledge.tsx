import { Trans } from "@lingui/react/macro";
import { useEffect, useRef, useState } from "react";
import { AgentPicker } from "../components/agents/AgentPicker";
import { type Agent, api, type Model, type Resource } from "../lib/api";
import { resources } from "../lib/rpc";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";

type Memory = { content: string; version: number };
export function Knowledge({ agents, initialAgent }: { agents: Agent[]; initialAgent: string }) {
  const { revision, refresh } = useClient();
  const [agent, setAgent] = useState(initialAgent || agents[0]?.id || "");
  const [tab, setTab] = useState<"memory" | "skills" | "scratchpad">("memory");
  const [memory, setMemory] = useState<Memory>({ content: "", version: 1 });
  const [content, setContent] = useState("");
  const [rows, setRows] = useState<Resource[]>([]);
  const [title, setTitle] = useState("");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<unknown>();
  const dirty = useRef(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    if (!agent) return;
    setSaved(false);
    if (tab === "memory")
      void api
        .get<Memory>(`/agents/${agent}/memory`)
        .then((v) => {
          if (!dirty.current) {
            setMemory(v);
            setContent(v.content);
          }
        })
        .catch(setError);
    else
      void resources(tab === "skills" ? "/agent-skills" : "/scratchpad")
        .list(agent)
        .then(setRows)
        .catch(setError);
  }, [agent, tab, revision]);
  return (
    <section>
      <div className="page-header">
        <h1>
          <Trans>Knowledge</Trans>
        </h1>
        <AgentPicker
          agents={agents}
          value={agent}
          onChange={(id) => {
            dirty.current = false;
            setAgent(id);
          }}
        />
      </div>
      <div className="tabs">
        <button
          type="button"
          className={tab === "memory" ? "selected" : ""}
          onClick={() => setTab("memory")}
        >
          <Trans>Long-term memory</Trans>
        </button>
        <button
          type="button"
          className={tab === "skills" ? "selected" : ""}
          onClick={() => setTab("skills")}
        >
          <Trans>Skills</Trans>
        </button>
        <button
          type="button"
          className={tab === "scratchpad" ? "selected" : ""}
          onClick={() => setTab("scratchpad")}
        >
          <Trans>Scratchpad</Trans>
        </button>
      </div>
      {error != null && <p role="alert">{userError(error)}</p>}
      {tab === "memory" ? (
        <form
          className="card"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              const m = await api.put<Memory>(`/agents/${agent}/memory`, {
                content,
                version: memory.version,
              });
              setMemory(m);
              dirty.current = false;
              setSaved(true);
            } catch (err) {
              setError(err);
            }
          }}
        >
          <p className="muted">
            <Trans>Stable facts and preferences kept separately from conversation history.</Trans>
          </p>
          <textarea
            rows={18}
            value={content}
            onChange={(e) => {
              dirty.current = true;
              setContent(e.target.value);
              setSaved(false);
            }}
          />
          <div className="actions">
            {saved && (
              <span role="status">
                <Trans>Saved</Trans>
              </span>
            )}
            <button type="submit" className="primary" disabled={!agent}>
              <Trans>Save memory</Trans>
            </button>
          </div>
        </form>
      ) : (
        <>
          <form
            className="card"
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await resources(tab === "skills" ? "/agent-skills" : "/scratchpad").create(
                  tab === "skills"
                    ? { name: title, content: draft, enabled: true }
                    : { title, content: draft },
                  agent,
                );
                setTitle("");
                setDraft("");
                refresh();
              } catch (err) {
                setError(err);
              }
            }}
          >
            <label>
              <Trans>Title</Trans>
              <input required value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label>
              <Trans>Content</Trans>
              <textarea
                rows={5}
                required
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
            </label>
            <button type="submit" disabled={!agent}>
              <Trans>Add</Trans>
            </button>
          </form>
          {rows.map((row) => (
            <details className="card" key={row.id}>
              <summary>{String(row.payload.name ?? row.payload.title ?? "")}</summary>
              <pre className="wrap" dir="auto">
                {String(row.payload.content ?? "")}
              </pre>
              <button
                type="button"
                className="danger"
                onClick={async () => {
                  try {
                    await resources(tab === "skills" ? "/agent-skills" : "/scratchpad").delete(
                      row.id,
                    );
                    refresh();
                  } catch (err) {
                    setError(err);
                  }
                }}
              >
                <Trans>Delete</Trans>
              </button>
            </details>
          ))}
        </>
      )}
      {tab === "memory" && agent && <SemanticKnowledge agentId={agent} />}
    </section>
  );
}

function SemanticKnowledge({ agentId }: { agentId: string }) {
  const [configuration, setConfiguration] = useState<{ enabled: boolean; model: string | null }>({
    enabled: false,
    model: null,
  });
  const [models, setModels] = useState<Model[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void Promise.all([
      api.get<typeof configuration>("/memory/semantic/config"),
      api.get<Model[]>("/providers/openai/models"),
    ])
      .then(([config, catalog]) => {
        setConfiguration(config);
        setModels(catalog);
      })
      .catch(setError);
  }, []);
  return (
    <details className="card">
      <summary>
        <Trans>Semantic memory · optional</Trans>
      </summary>
      <p className="muted">
        <Trans>
          Search separate knowledge notes using real embeddings from a globally selected OpenAI
          model.
        </Trans>
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api.put("/memory/semantic/config", configuration);
          } catch (err) {
            setError(err);
          }
        }}
      >
        <label className="check">
          <input
            type="checkbox"
            checked={configuration.enabled}
            onChange={(e) => setConfiguration({ ...configuration, enabled: e.target.checked })}
          />
          <Trans>Enable semantic retrieval</Trans>
        </label>
        <label>
          <Trans>Global embedding model</Trans>
          <select
            value={configuration.model ?? ""}
            onChange={(e) => setConfiguration({ ...configuration, model: e.target.value || null })}
          >
            <option value="">
              <Trans>Choose a discovered model</Trans>
            </option>
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={configuration.enabled && !configuration.model}>
          <Trans>Save</Trans>
        </button>
      </form>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api.post(`/agents/${agentId}/memory/semantic`, { text: note });
            setNote("");
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          <Trans>Knowledge note</Trans>
          <textarea rows={4} required value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button type="submit" disabled={!configuration.enabled || !configuration.model || busy}>
          <Trans>Index note</Trans>
        </button>
      </form>
      {error != null && <p role="alert">{userError(error)}</p>}
    </details>
  );
}
