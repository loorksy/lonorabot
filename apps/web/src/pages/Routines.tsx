import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import { AgentPicker } from "../components/agents/AgentPicker";
import { WorkingIndicator } from "../components/chat/WorkingIndicator";
import { type Agent, api, type Routine, type Run } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
export function Routines({ agents }: { agents: Agent[] }) {
  const { revision, refresh } = useClient();
  const [rows, setRows] = useState<Routine[]>([]);
  const [agent, setAgent] = useState(agents[0]?.id ?? "");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState("interval");
  const [minutes, setMinutes] = useState(60);
  const [cron, setCron] = useState("0 9 * * 1-5");
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [history, setHistory] = useState<Run[]>([]);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    void api.get<Routine[]>("/routines").then(setRows).catch(setError);
  }, [revision]);
  return (
    <section>
      <h1>
        <Trans>Routines</Trans>
      </h1>
      <p className="muted">
        <Trans>
          Scheduled work runs through the same agents, memory, tools and global model settings.
        </Trans>
      </p>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api.post(`/routines/${agent}`, {
              prompt,
              interval_seconds: mode === "interval" ? minutes * 60 : null,
              cron: mode === "cron" ? cron : null,
              timezone,
              enabled: true,
            });
            setPrompt("");
            refresh();
          } catch (err) {
            setError(err);
          }
        }}
      >
        <AgentPicker agents={agents} value={agent} onChange={setAgent} />
        <label>
          <Trans>Task</Trans>
          <textarea rows={3} required value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        </label>
        <div className="form-grid">
          <label>
            <Trans>Schedule</Trans>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="interval">
                <Trans>Interval</Trans>
              </option>
              <option value="cron">
                <Trans>Cron expression</Trans>
              </option>
            </select>
          </label>
          {mode === "interval" ? (
            <label>
              <Trans>Every · minutes</Trans>
              <input
                type="number"
                min={1}
                max={525600}
                value={minutes}
                onChange={(e) => setMinutes(Number(e.target.value))}
              />
            </label>
          ) : (
            <label>
              <Trans>Cron expression</Trans>
              <input dir="ltr" value={cron} onChange={(e) => setCron(e.target.value)} />
            </label>
          )}
          <label>
            <Trans>Timezone</Trans>
            <input dir="ltr" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
          </label>
        </div>
        <button type="submit" className="primary" disabled={!agent}>
          <Trans>Create routine</Trans>
        </button>
      </form>
      {error != null && <p role="alert">{userError(error)}</p>}
      {rows.map((r) => (
        <article className="card" key={r.id}>
          <div className="row">
            <h3>{agents.find((a) => a.id === r.agent_id)?.name}</h3>
            <span className="badge">
              {r.enabled ? <Trans>Enabled</Trans> : <Trans>Paused</Trans>}
            </span>
          </div>
          <p dir="auto">{r.prompt}</p>
          <p className="muted">
            <Trans>Next run</Trans>: {new Date(r.next_run_at).toLocaleString()} ·{" "}
            <bdi>
              {r.cron ?? `${r.interval_seconds}s`} · {r.timezone}
            </bdi>
          </p>
          <div className="actions">
            <button
              type="button"
              onClick={async () => {
                try {
                  await api.put(`/routines/${r.id}`, {
                    prompt: r.prompt,
                    interval_seconds: r.interval_seconds,
                    cron: r.cron,
                    timezone: r.timezone,
                    enabled: !r.enabled,
                  });
                  refresh();
                } catch (err) {
                  setError(err);
                }
              }}
            >
              {r.enabled ? <Trans>Pause</Trans> : <Trans>Resume</Trans>}
            </button>
            <button
              type="button"
              onClick={() =>
                void api.get<Run[]>(`/routines/${r.id}/history`).then(setHistory).catch(setError)
              }
            >
              <Trans>History</Trans>
            </button>
            <button
              type="button"
              className="danger"
              onClick={() => void api.delete(`/routines/${r.id}`).then(refresh).catch(setError)}
            >
              <Trans>Delete</Trans>
            </button>
          </div>
        </article>
      ))}
      {history.length > 0 && (
        <section className="card">
          <h2>
            <Trans>Execution history</Trans>
          </h2>
          {history.map((r) => (
            <div className="row" key={r.id}>
              <time>{new Date(r.created_at).toLocaleString()}</time>
              <WorkingIndicator run={r} />
            </div>
          ))}
        </section>
      )}
    </section>
  );
}
