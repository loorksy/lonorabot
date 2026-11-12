import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { agentStatusLine, agentStatusText, watchCondition, watchUntil } from "@lonora/core";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { useAgentLiveState } from "../../lib/agent-live-state";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import "./agent-status.css";

export function AgentLiveStatus({ agentId }: { agentId: string }) {
  const { state, error: readError, reload } = useAgentLiveState(agentId);
  const [actionError, setActionError] = useState<unknown>();
  const error = actionError ?? readError;
  if (!state) return null;
  const locale = i18n.locale;
  const status = agentStatusText(locale);
  return (
    <details
      className="template-run-status lonora-background-status"
      data-testid="agent-live-state"
      data-state={state.state}
    >
      <summary>
        <i className="lonora-status-dot" aria-hidden="true" />
        <span dir="auto" data-testid="agent-status-line">
          {agentStatusLine(state, locale)}
        </span>
        <ChevronDown size={14} className="lonora-status-expand" aria-hidden="true" />
      </summary>
      {error != null && <p role="alert">{userError(error)}</p>}
      {(state.runtime_waits ?? []).map((wait) => (
        <p key={wait.run_id}>
          {wait.kind === "read_retry"
            ? t`Retry scheduled`
            : wait.kind === "model_retry"
              ? t`Model provider unavailable — retry scheduled`
              : t`Waiting`}
          {wait.retry_at && (
            <>
              {" "}
              · <time dateTime={wait.retry_at}>{new Date(wait.retry_at).toLocaleTimeString()}</time>
            </>
          )}
        </p>
      ))}
      {state.pending_approval_count > 0 && (
        <p>
          <Trans>Waiting for approval</Trans>
        </p>
      )}
      {(state.watches ?? []).length > 0 && (
        <ul className="lonora-watch-list" aria-label={status.watches}>
          {(state.watches ?? []).map((watch) => (
            <li key={watch.id} data-watch={watch.id}>
              <span>
                {watchCondition(watch, locale)} · {watchUntil(watch, locale)}
              </span>
              <button
                type="button"
                onClick={() => {
                  void api
                    .post(`/watches/${encodeURIComponent(watch.id)}/control`, { action: "cancel" })
                    .then(() => {
                      setActionError(undefined);
                      return reload();
                    })
                    .catch(setActionError);
                }}
              >
                {status.cancel}
              </button>
            </li>
          ))}
        </ul>
      )}
      {(state.pending_authorization_count ?? 0) > 0 && (
        <p>
          <Trans>Waiting for device authorization</Trans>
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
                      .then(() => {
                        setActionError(undefined);
                        return reload();
                      })
                      .catch(setActionError);
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
          {health.reason_code === "broker_reconciliation_pending" ? (
            <Trans>
              Broker verification pending. Market data remains available; new orders on the affected
              market are blocked until verification finishes, and closing remains available.
            </Trans>
          ) : health.kind === "broker" || !health.symbol ? (
            <Trans>Broker connection requires attention</Trans>
          ) : (
            <>
              <Trans>Market data unavailable</Trans> <bdi>{health.symbol}</bdi>
            </>
          )}
        </p>
      ))}
      <time dateTime={state.observed_at}>{new Date(state.observed_at).toLocaleTimeString()}</time>
    </details>
  );
}
