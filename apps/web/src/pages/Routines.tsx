// Adapted from Tampletgrok RoutineEditor.tsx list boundaries (Apache-2.0).
import { Trans, useLingui } from "@lingui/react/macro";
import { Clock, Pause, Pencil, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import { type Agent, api, type Routine } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import { RoutineEditor } from "./RoutineEditor";
import { RoutineRunHistory } from "./RoutineRunHistory";
import { RoutineScheduleSummary } from "./RoutineSchedule";

export function RoutineListHeader({
  onCreate,
  disabled,
}: {
  onCreate: () => void;
  disabled: boolean;
}) {
  return (
    <header className="workspace-surface-header">
      <div className="workspace-surface-heading">
        <h1>
          <Trans>Routines</Trans>
        </h1>
        <p>
          <Trans>Schedule recurring work for your agents.</Trans>
        </p>
      </div>
      <button
        type="button"
        className="workspace-button workspace-button-primary"
        onClick={onCreate}
        disabled={disabled}
      >
        <Plus size={15} aria-hidden="true" />
        <Trans>Create routine</Trans>
      </button>
    </header>
  );
}

export function RoutineListRow({
  routine,
  agent,
  busy,
  onEdit,
  onToggle,
}: {
  routine: Routine;
  agent?: Agent;
  busy: boolean;
  onEdit: () => void;
  onToggle: () => void;
}) {
  const { t, i18n } = useLingui();
  return (
    <article
      className="rounded-xl border border-border bg-card p-4"
      data-testid={`routine-row-${routine.id}`}
    >
      <div className="flex flex-wrap items-start gap-3">
        {agent && <AgentAvatar agent={agent} />}
        <button
          type="button"
          className="min-w-0 flex-1 text-start"
          onClick={onEdit}
          aria-label={t`Edit routine`}
        >
          <span className="block text-sm font-medium text-foreground" dir="auto">
            {agent?.name}
          </span>
          <span className="mt-1 block break-words text-sm text-muted-foreground" dir="auto">
            {routine.prompt}
          </span>
        </button>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {routine.enabled ? (
            <Clock size={14} aria-hidden="true" />
          ) : (
            <Pause size={14} aria-hidden="true" />
          )}
          {routine.enabled ? <Trans>Enabled</Trans> : <Trans>Paused</Trans>}
        </span>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 text-xs text-muted-foreground">
          <RoutineScheduleSummary routine={routine} />
          {routine.enabled && (
            <p className="mt-1">
              <Trans>Next run</Trans>:{" "}
              <time dateTime={routine.next_run_at}>
                {new Date(routine.next_run_at).toLocaleString(i18n.locale)}
              </time>
            </p>
          )}
        </div>
        <div className="workspace-surface-actions">
          <button type="button" className="workspace-button" onClick={onToggle} disabled={busy}>
            {routine.enabled ? <Trans>Pause</Trans> : <Trans>Resume</Trans>}
          </button>
          <button type="button" className="workspace-button" onClick={onEdit} disabled={busy}>
            <Pencil size={13} aria-hidden="true" />
            <Trans>Edit</Trans>
          </button>
        </div>
      </div>
      <RoutineRunHistory routineId={routine.id} />
    </article>
  );
}

export function Routines({ agents }: { agents: Agent[] }) {
  const { revision, refresh } = useClient();
  const [rows, setRows] = useState<Routine[]>([]);
  const [selected, setSelected] = useState<Routine | "new" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void revision;
    let active = true;
    void api
      .get<Routine[]>("/routines")
      .then((next) => {
        if (!active) return;
        setRows(next);
        setError(undefined);
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

  async function toggle(routine: Routine) {
    if (busy) return;
    setBusy(routine.id);
    setError(undefined);
    try {
      const updated = await api.put<Routine>(`/routines/${routine.id}`, {
        prompt: routine.prompt,
        interval_seconds: routine.interval_seconds,
        cron: routine.cron,
        timezone: routine.timezone,
        enabled: !routine.enabled,
      });
      setRows((current) => current.map((row) => (row.id === updated.id ? updated : row)));
      refresh();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="workspace-surface" data-testid="workspace-routines">
      <RoutineListHeader onCreate={() => setSelected("new")} disabled={!agents.length} />
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
            <Trans>Loading…</Trans>
          </p>
        ) : !rows.length ? (
          <div className="workspace-empty">
            <Clock size={28} aria-hidden="true" />
            <p>
              {agents.length ? (
                <Trans>Create a routine to schedule recurring work.</Trans>
              ) : (
                <Trans>Create an agent before adding a routine.</Trans>
              )}
            </p>
          </div>
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-4">
            {rows.map((routine) => (
              <RoutineListRow
                key={routine.id}
                routine={routine}
                agent={agents.find((agent) => agent.id === routine.agent_id)}
                busy={busy !== null}
                onEdit={() => setSelected(routine)}
                onToggle={() => void toggle(routine)}
              />
            ))}
          </div>
        )}
      </div>
      {selected && (
        <RoutineEditor
          key={selected === "new" ? "new" : selected.id}
          routine={selected === "new" ? null : selected}
          agents={agents}
          onClose={() => setSelected(null)}
          onSaved={refresh}
        />
      )}
    </section>
  );
}
