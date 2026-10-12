import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import { AgentPicker } from "../components/agents/AgentPicker";
import { type Agent, api, type Resource } from "../lib/api";
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
          setMemory(v);
          setContent(v.content);
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
        <AgentPicker agents={agents} value={agent} onChange={setAgent} />
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
    </section>
  );
}
