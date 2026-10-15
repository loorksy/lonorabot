import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentLiveState } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

export function AgentLiveStatus({ agentId }: { agentId: string }) {
  const { revision } = useClient();
  const [state, setState] = useState<AgentLiveState | null>(null);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<AgentLiveState>(`/agents/${encodeURIComponent(agentId)}/state`)
      .then((next) => {
        if (live) {
          setState(next);
          setError(undefined);
        }
      })
      .catch((caught: unknown) => {
        if (live) setError(caught);
      });
    return () => {
      live = false;
    };
  }, [agentId, revision]);
  if (!state || state.agent_id !== agentId) return null;
  const labels = {
    idle: t`Idle`,
    working: t`Working`,
    waiting: t`Waiting`,
    action_required: t`Action required`,
    degraded: t`Market data unavailable`,
    paused: t`Paused`,
  };
  return (
    <details
      className="template-run-status"
      data-testid="agent-live-state"
      data-state={state.state}
    >
      <summary>{labels[state.state]}</summary>
      {error != null && <p role="alert">{userError(error)}</p>}
      {state.pending_approval_count > 0 && (
        <p>
          <Trans>Waiting for approval</Trans>
        </p>
      )}
      {state.watch_count > 0 && (
        <p>
          <Trans>Active watches</Trans>: {state.watch_count}
        </p>
      )}
      {state.tasks.map((task) => (
        <div key={task.id}>
          <p dir="auto">{task.title}</p>
          {task.retry_at ? (
            <p>
              <Trans>Retry scheduled</Trans> ·{" "}
              <time dateTime={task.retry_at}>{new Date(task.retry_at).toLocaleTimeString()}</time>
            </p>
          ) : task.recovery === "reconcile" ? (
            <p>
              <Trans>Waiting for reconciliation</Trans>
            </p>
          ) : task.status === "failed" ? (
            <p>
              <Trans>Task needs review</Trans>
            </p>
          ) : null}
          {(["pause", "resume", "cancel"] as const).map(
            (action) =>
              task[`can_${action}`] && (
                <button
                  key={action}
                  type="button"
                  onClick={() => {
                    void api
                      .post("/tasks/control", {
                        task_id: task.id,
                        action,
                        expected_version: task.version,
                      })
                      .then(() =>
                        api.get<AgentLiveState>(`/agents/${encodeURIComponent(agentId)}/state`),
                      )
                      .then(setState)
                      .catch(setError);
                  }}
                >
                  {action === "pause" ? t`Pause` : action === "resume" ? t`Resume` : t`Cancel`}
                </button>
              ),
          )}
        </div>
      ))}
      {state.health.map((health, index) => (
        <p key={`${health.account_id}:${health.symbol ?? index}`}>
          <Trans>Market data unavailable</Trans> <bdi>{health.symbol}</bdi>
        </p>
      ))}
      <time dateTime={state.observed_at}>{new Date(state.observed_at).toLocaleTimeString()}</time>
    </details>
  );
}
