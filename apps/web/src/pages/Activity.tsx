import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import { CollaborationMarker } from "../components/agents/CollaborationMarker";
import { WorkingIndicator } from "../components/chat/WorkingIndicator";
import { type Agent, api, type Resource, type Run } from "../lib/api";
import { resources } from "../lib/rpc";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
export function Activity({ agents }: { agents: Agent[] }) {
  const { revision, refresh } = useClient();
  const [runs, setRuns] = useState<Run[]>([]);
  const [boards, setBoards] = useState<Resource[]>([]);
  const [tickets, setTickets] = useState<Resource[]>([]);
  const [board, setBoard] = useState("");
  const [title, setTitle] = useState("");
  const [task, setTask] = useState("");
  const [agent, setAgent] = useState("");
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    void Promise.all([
      api.get<Run[]>("/runs"),
      resources("/boards").list(),
      resources("/tickets").list(),
    ])
      .then(([r, b, t]) => {
        setRuns(r);
        setBoards(b);
        setTickets(t);
      })
      .catch(setError);
  }, [revision]);
  return (
    <section>
      <h1>
        <Trans>Activity and task boards</Trans>
      </h1>
      {error != null && <p role="alert">{userError(error)}</p>}
      <div className="columns">
        <section className="card">
          <h2>
            <Trans>Task boards</Trans>
          </h2>
          <form
            className="inline-form"
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await resources("/boards").create({ title });
                setTitle("");
                refresh();
              } catch (err) {
                setError(err);
              }
            }}
          >
            <label>
              <Trans>Board title</Trans>
              <input required value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <button type="submit">
              <Trans>Add board</Trans>
            </button>
          </form>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await resources("/tickets").create(
                  { board_id: board, title: task, description: task, status: "todo", run_id: null },
                  agent,
                );
                setTask("");
                refresh();
              } catch (err) {
                setError(err);
              }
            }}
          >
            <label>
              <Trans>Board</Trans>
              <select required value={board} onChange={(e) => setBoard(e.target.value)}>
                <option value="">
                  <Trans>Choose a board</Trans>
                </option>
                {boards.map((b) => (
                  <option key={b.id} value={b.id}>
                    {String(b.payload.title)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <Trans>Agent</Trans>
              <select required value={agent} onChange={(e) => setAgent(e.target.value)}>
                <option value="">
                  <Trans>Choose an agent</Trans>
                </option>
                {agents.map((a) => (
                  <option value={a.id} key={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <Trans>Task</Trans>
              <input required value={task} onChange={(e) => setTask(e.target.value)} />
            </label>
            <button type="submit" disabled={!board || !agent}>
              <Trans>Add ticket</Trans>
            </button>
          </form>
          {tickets
            .filter((t) => !board || t.payload.board_id === board)
            .map((ticket) => (
              <div className="ticket" key={ticket.id}>
                <strong>{String(ticket.payload.title)}</strong>
                <span className="badge">
                  {ticket.payload.status === "done" ? (
                    <Trans>Completed</Trans>
                  ) : ticket.payload.status === "working" ? (
                    <Trans>Working</Trans>
                  ) : ticket.payload.status === "failed" ? (
                    <Trans>Failed</Trans>
                  ) : (
                    <Trans>To do</Trans>
                  )}
                </span>
                <button
                  type="button"
                  disabled={ticket.payload.status === "working"}
                  onClick={() =>
                    void api.post(`/tickets/${ticket.id}/start`, {}).then(refresh).catch(setError)
                  }
                >
                  <Trans>Run task</Trans>
                </button>
              </div>
            ))}
        </section>
        <section className="card">
          <h2>
            <Trans>Recent runs</Trans>
          </h2>
          {runs.map((r) => (
            <details className="run-item" key={r.id}>
              <summary>
                <span>{agents.find((a) => a.id === r.agent_id)?.name}</span>
                <WorkingIndicator run={r} />
                <CollaborationMarker run={r} />
                <time>{new Date(r.created_at).toLocaleString()}</time>
              </summary>
              {r.error_code && <p role="alert">{userError({ code: r.error_code })}</p>}
              {r.result && (
                <p className="wrap" dir="auto">
                  {r.result}
                </p>
              )}
              <bdi className="muted">
                {String(r.model_metadata.provider ?? "")} {String(r.model_metadata.model ?? "")}
              </bdi>
              {["queued", "leased", "running", "waiting_input"].includes(r.status) && (
                <button
                  type="button"
                  onClick={() =>
                    void api.post(`/runs/${r.id}/cancel`, {}).then(refresh).catch(setError)
                  }
                >
                  <Trans>Stop</Trans>
                </button>
              )}
              {["waiting_takeover", "failed"].includes(r.status) && (
                <button
                  type="button"
                  onClick={() =>
                    void api.post(`/runs/${r.id}/resume`, {}).then(refresh).catch(setError)
                  }
                >
                  <Trans>Resume</Trans>
                </button>
              )}
            </details>
          ))}
        </section>
      </div>
    </section>
  );
}
