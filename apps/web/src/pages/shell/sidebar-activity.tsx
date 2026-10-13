import { Trans, useLingui } from "@lingui/react/macro";
import { useState } from "react";
import { WorkingIndicator } from "../../components/ai/primitives";
import type { Agent, Run } from "../../lib/api";

export function SidebarActivity({
  runs,
  agents,
  onOpen,
  onShowAll,
}: {
  runs: Run[];
  agents: Agent[];
  onOpen: (run: Run) => void;
  onShowAll: () => void;
}) {
  const { t, i18n } = useLingui();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const names = new Map(agents.map((agent) => [agent.id, agent.name]));
  const rows = runs
    .filter((run) => {
      const date = new Date(run.created_at);
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
      return (
        (status === "all" || run.status === status) &&
        (!from || key >= from) &&
        (!to || key <= to) &&
        (!query.trim() ||
          `${names.get(run.agent_id) ?? ""} ${run.result ?? ""}`
            .toLocaleLowerCase()
            .includes(query.trim().toLocaleLowerCase()))
      );
    })
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  return (
    <section className="tpl-sidebar-activity" aria-label={t`Activity`}>
      <input
        type="search"
        aria-label={t`Search runs`}
        placeholder={t`Search runs`}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <label>
        <Trans>Status</Trans>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="all">{t`All statuses`}</option>
          {[
            "queued",
            "running",
            "waiting_input",
            "waiting_takeover",
            "completed",
            "failed",
            "cancelled",
          ].map((value) => (
            <option key={value} value={value}>
              {value === "queued"
                ? t`Queued`
                : value === "running"
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
      <label>
        <Trans>From</Trans>
        <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
      </label>
      <label>
        <Trans>To</Trans>
        <input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
      </label>
      <h3>
        <Trans>Recent</Trans>
      </h3>
      {rows.slice(0, 12).map((run) => (
        <button
          type="button"
          className="tpl-activity-run"
          key={run.id}
          data-sidebar-run-id={run.id}
          data-status={run.status}
          onClick={() => onOpen(run)}
        >
          <span className="tpl-activity-dot" aria-hidden="true" />
          <span className="tpl-activity-copy">
            <span className="tpl-activity-name" dir="auto">
              {names.get(run.agent_id) ?? t`Agent`}
            </span>
            {run.result && (
              <span className="tpl-activity-snippet" dir="auto">
                {run.result}
              </span>
            )}
          </span>
          <span className="tpl-activity-outcome">
            <time dateTime={run.created_at}>
              {new Date(run.created_at).toLocaleTimeString(i18n.locale, {
                hour: "numeric",
                minute: "2-digit",
              })}
            </time>
            <WorkingIndicator run={run} />
          </span>
        </button>
      ))}
      {!rows.length && (
        <p className="tpl-roster-notice">
          <Trans>No runs match these filters.</Trans>
        </p>
      )}
      <button type="button" className="tpl-activity-more" onClick={onShowAll}>
        <Trans>All activity</Trans>
      </button>
    </section>
  );
}
