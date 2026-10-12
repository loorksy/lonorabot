import { Trans } from "@lingui/react/macro";
import type { Run } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { WorkingIndicator } from "../components/ai/primitives";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";

export function RoutineRunHistory({ routineId }: { routineId: string }) {
  const { revision } = useClient();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Run[] | null>(null);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void revision;
    if (!open) return;
    let live = true;
    void api
      .get<Run[]>(`/routines/${routineId}/history`)
      .then((value) => {
        if (live) {
          setRows(value);
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (live) setError(cause);
      });
    return () => {
      live = false;
    };
  }, [open, routineId, revision]);
  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)} className="mt-4">
      <summary>
        <Trans>Execution history</Trans>
      </summary>
      {error != null ? (
        <p role="alert">{userError(error)}</p>
      ) : rows === null ? (
        <p role="status">
          <Trans>Loading…</Trans>
        </p>
      ) : !rows.length ? (
        <p className="muted">
          <Trans>No executions yet</Trans>
        </p>
      ) : (
        rows.map((run) => (
          <div className="row" key={run.id}>
            <time>{new Date(run.created_at).toLocaleString()}</time>
            <WorkingIndicator run={run} />
            <Link to={`/app/${run.agent_id}?thread=${encodeURIComponent(run.thread_id)}`}>
              <Trans>Open conversation</Trans>
            </Link>
          </div>
        ))
      )}
    </details>
  );
}
