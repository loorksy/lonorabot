// Adapted for Lonora from Tampletgrok ActivityList.tsx (Apache-2.0).

import { Trans, useLingui } from "@lingui/react/macro";
import { canCancel, canResume } from "@lonora/core";
import { ClipboardList } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import { CollaborationMarker } from "../components/ai/CollaborationMarker";
import { WorkingIndicator } from "../components/ai/primitives";
import { type Agent, api, type Run } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";

const activeStatuses = ["queued", "leased", "running", "waiting_input", "waiting_takeover"];
const statuses: Run["status"][] = [
  "queued",
  "leased",
  "running",
  "waiting_input",
  "waiting_takeover",
  "completed",
  "failed",
  "cancelled",
];
export function ActivityList({ agents }: { agents: Agent[] }) {
  const { t } = useLingui();
  const { revision, refresh } = useClient();
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<Run["status"] | "all">("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  useEffect(() => {
    void revision;
    let active = true;
    void api
      .get<Run[]>("/runs")
      .then((rows) => {
        if (active) {
          setRuns(rows);
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (active) setError(cause);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [revision]);
  const filtered = useMemo(
    () =>
      runs.filter((run) => {
        const date = new Date(run.created_at);
        const dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
        const name = agents.find((entry) => entry.id === run.agent_id)?.name ?? "";
        return (
          (status === "all" || run.status === status) &&
          (!from || dateKey >= from) &&
          (!to || dateKey <= to) &&
          (!query.trim() ||
            `${name} ${run.result ?? ""}`
              .toLocaleLowerCase()
              .includes(query.trim().toLocaleLowerCase()))
        );
      }),
    [runs, agents, status, from, to, query],
  );
  return (
    <section className="workspace-surface" data-testid="workspace-activity">
      <header className="workspace-surface-header">
        <div className="workspace-surface-heading">
          <h1>
            <Trans>Activity</Trans>
          </h1>
          <p>
            <Trans>Follow your agents’ runs and pick up unfinished work.</Trans>
          </p>
        </div>
      </header>
      <div className="workspace-artifact-filters">
        <label className="workspace-search-field">
          <input
            aria-label={t`Search activity`}
            placeholder={t`Search runs`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="workspace-inline-label">
          <Trans>Status</Trans>
          <select
            aria-label={t`Status`}
            value={status}
            onChange={(event) => setStatus(event.target.value as typeof status)}
          >
            <option value="all">
              <Trans>All statuses</Trans>
            </option>
            {statuses.map((value) => (
              <option key={value} value={value}>
                {value === "queued"
                  ? t`Queued`
                  : value === "leased" || value === "running"
                    ? t`Working`
                    : value === "waiting_input"
                      ? t`Waiting for your reply`
                      : value === "waiting_takeover"
                        ? t`Waiting for handover`
                        : value === "completed"
                          ? t`Completed`
                          : value === "failed"
                            ? t`Failed`
                            : t`Cancelled`}
              </option>
            ))}
          </select>
        </label>
        <label className="workspace-inline-label">
          <Trans>From</Trans>
          <input
            type="date"
            aria-label={t`From`}
            value={from}
            onChange={(event) => setFrom(event.target.value)}
          />
        </label>
        <label className="workspace-inline-label">
          <Trans>To</Trans>
          <input
            type="date"
            aria-label={t`To`}
            value={to}
            min={from || undefined}
            onChange={(event) => setTo(event.target.value)}
          />
        </label>
        {(query || status !== "all" || from || to) && (
          <button
            type="button"
            className="workspace-button"
            onClick={() => {
              setQuery("");
              setStatus("all");
              setFrom("");
              setTo("");
            }}
          >
            <Trans>Reset all</Trans>
          </button>
        )}
      </div>
      {error != null && (
        <div className="workspace-error" role="alert">
          <p>{userError(error)}</p>
          <button type="button" className="workspace-button" onClick={refresh}>
            <Trans>Retry</Trans>
          </button>
        </div>
      )}
      <div className="workspace-surface-body" aria-busy={loading}>
        {loading ? (
          <p className="workspace-empty" role="status">
            <Trans>Loading activity…</Trans>
          </p>
        ) : !runs.length ? (
          <div className="workspace-empty">
            <ClipboardList size={28} aria-hidden="true" />
            <p>
              <Trans>Your agents’ activity will appear here.</Trans>
            </p>
          </div>
        ) : !filtered.length ? (
          <p className="workspace-empty">
            <Trans>No runs match these filters.</Trans>
          </p>
        ) : (
          <div className="workspace-run-list" data-testid="activity-list">
            {[true, false].map((active) => {
              const rows = filtered.filter((run) => activeStatuses.includes(run.status) === active);
              return rows.length ? (
                <section key={String(active)}>
                  <h2 className="mb-3 text-[13px] font-medium text-muted-foreground">
                    {active ? <Trans>Now</Trans> : <Trans>Recent</Trans>}
                  </h2>
                  <div className="flex flex-col gap-2">
                    {rows.map((run) => (
                      <ActivityRow
                        key={run.id}
                        run={run}
                        agent={agents.find((entry) => entry.id === run.agent_id)}
                        onRefresh={refresh}
                        onError={setError}
                      />
                    ))}
                  </div>
                </section>
              ) : null;
            })}
          </div>
        )}
      </div>
    </section>
  );
}
function ActivityRow({
  run,
  agent,
  onRefresh,
  onError,
}: {
  run: Run;
  agent?: Agent;
  onRefresh: () => void;
  onError: (error: unknown) => void;
}) {
  const [busy, setBusy] = useState(false);
  async function action(name: "cancel" | "resume") {
    if (busy) return;
    setBusy(true);
    try {
      await api.post(`/runs/${run.id}/${name}`, {});
      onRefresh();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="workspace-run-card">
      <summary>
        {agent && <AgentAvatar agent={agent} />}
        <span className="workspace-run-agent">{agent?.name}</span>
        <WorkingIndicator run={run} />
        <time dateTime={run.created_at}>{new Date(run.created_at).toLocaleString()}</time>
      </summary>
      <div className="workspace-run-details">
        <CollaborationMarker run={run} />
        {run.error_code && <p role="alert">{userError({ code: run.error_code })}</p>}
        {run.result && (
          <p className="workspace-run-result" dir="auto">
            {run.result}
          </p>
        )}
        <bdi className="workspace-muted">
          {String(run.model_metadata.provider ?? "")} {String(run.model_metadata.model ?? "")}
        </bdi>
        <div className="workspace-surface-actions">
          <Link
            className="workspace-button"
            to={`/app/${run.agent_id}?thread=${encodeURIComponent(run.thread_id)}`}
          >
            <Trans>Open conversation</Trans>
          </Link>
          {canCancel(run.status) && (
            <button
              type="button"
              className="workspace-button"
              disabled={busy}
              onClick={() => void action("cancel")}
            >
              <Trans>Stop</Trans>
            </button>
          )}
          {canResume(run.status) && (
            <button
              type="button"
              className="workspace-button"
              disabled={busy}
              onClick={() => void action("resume")}
            >
              <Trans>Resume</Trans>
            </button>
          )}
        </div>
      </div>
    </details>
  );
}
