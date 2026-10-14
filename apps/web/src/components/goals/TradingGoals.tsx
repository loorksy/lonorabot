import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useCallback, useEffect, useState } from "react";
import { api, type Resource } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

function statusLabel(value: unknown): string {
  switch (String(value).toLowerCase()) {
    case "active":
      return t`Active`;
    case "waiting":
      return t`Waiting for a condition`;
    case "blocked":
      return t`Needs attention`;
    case "planning":
      return t`Planning`;
    case "waiting_for_condition":
      return t`Waiting for a condition`;
    case "condition_triggered":
      return t`Condition triggered`;
    case "revalidating":
      return t`Rechecking market conditions`;
    case "ready_to_execute":
      return t`Ready to execute`;
    case "executing":
      return t`Executing`;
    case "verifying":
      return t`Verifying execution`;
    case "ambiguous":
      return t`Execution requires reconciliation`;
    case "reconciling":
      return t`Reconciling with broker`;
    case "position_open":
      return t`Position open`;
    case "monitoring":
      return t`Monitoring`;
    case "completed":
      return t`Completed`;
    case "failed":
      return t`Failed`;
    case "paused":
      return t`Paused`;
    case "cancelled":
      return t`Cancelled`;
    default:
      return t`Pending`;
  }
}

export function TradingGoals({ agentId }: { agentId: string }) {
  const { revision, refresh } = useClient();
  const [goals, setGoals] = useState<Resource[]>([]);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState("");
  const reload = useCallback(async () => {
    const rows = await api.get<Resource[]>(
      `/trading/goals?agent_id=${encodeURIComponent(agentId)}`,
    );
    setGoals(rows.filter((row) => row.agent_id === agentId));
  }, [agentId]);
  useEffect(() => {
    void revision;
    let active = true;
    void api
      .get<Resource[]>(`/trading/goals?agent_id=${encodeURIComponent(agentId)}`)
      .then((rows) => {
        if (active) setGoals(rows.filter((row) => row.agent_id === agentId));
      })
      .catch((failure) => {
        if (active) setError(failure);
      });
    return () => {
      active = false;
    };
  }, [agentId, revision]);
  async function control(goal: Resource, action: string, autonomous?: boolean) {
    setBusy(goal.id);
    setError(undefined);
    try {
      await api.post(`/trading/goals/${goal.id}/control`, {
        version: goal.version,
        action,
        ...(autonomous === undefined ? {} : { autonomous }),
      });
      await reload();
      refresh();
    } catch (failure) {
      setError(failure);
      await reload().catch(() => undefined);
    } finally {
      setBusy("");
    }
  }
  async function wake(goal: Resource) {
    setBusy(goal.id);
    setError(undefined);
    try {
      await api.post(`/trading/goals/${goal.id}/wake`, {});
      refresh();
      await reload();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy("");
    }
  }
  return (
    <section aria-label={t`Trading goals`} className="stack">
      <p className="muted">
        <Trans>
          Ask this agent to create a trading goal. Its plan, watches and execution history remain on
          the server.
        </Trans>
      </p>
      {error != null && <p role="alert">{userError(error)}</p>}
      {goals.length === 0 && (
        <p>
          <Trans>No trading goals yet.</Trans>
        </p>
      )}
      {goals.map((goal) => {
        const phase = String(goal.state.status ?? "planning").toLowerCase();
        const terminal = ["cancelled", "completed"].includes(phase);
        const autonomous = goal.state.autonomous === true;
        const steps = Array.isArray(goal.payload.steps)
          ? (goal.payload.steps as Record<string, unknown>[])
          : [];
        return (
          <article className="card stack" key={goal.id} data-goal-id={goal.id}>
            <h3>{String(goal.payload.title ?? "")}</h3>
            <p>{String(goal.payload.objective ?? "")}</p>
            <p>
              <bdi>{String(goal.payload.symbol ?? "")}</bdi> · {statusLabel(phase)}
            </p>
            <ol>
              {steps.map((step) => {
                const states = goal.state.steps as
                  | Record<string, Record<string, unknown>>
                  | undefined;
                const trade = step.trade as Record<string, unknown> | undefined;
                return (
                  <li key={String(step.id)}>
                    <p>
                      {String(step.title ?? step.id)} ·{" "}
                      {statusLabel(states?.[String(step.id)]?.status)}
                    </p>
                    {trade && (
                      <p>
                        <bdi>
                          {[trade.action, trade.symbol, trade.volume, trade.price]
                            .filter(Boolean)
                            .join(" · ")}
                        </bdi>
                        <br />
                        <Trans>Stop loss</Trans>: <bdi>{String(trade.stop_loss ?? "—")}</bdi> ·{" "}
                        <Trans>Take profit</Trans>: <bdi>{String(trade.take_profit ?? "—")}</bdi>
                      </p>
                    )}
                  </li>
                );
              })}
            </ol>
            <label className="row">
              <input
                type="checkbox"
                checked={autonomous}
                disabled={terminal || busy === goal.id}
                onChange={(event) =>
                  void control(goal, phase === "paused" ? "pause" : "resume", event.target.checked)
                }
              />
              <Trans>Allow autonomous trading for this goal</Trans>
            </label>
            <p className="muted">
              <Trans>
                Global Trading and Emergency Stop still govern every financial operation. Pausing a
                goal does not close existing broker positions.
              </Trans>
            </p>
            <div className="row">
              <button
                type="button"
                disabled={terminal || busy === goal.id}
                onClick={() => void control(goal, phase === "paused" ? "resume" : "pause")}
              >
                {phase === "paused" ? <Trans>Resume</Trans> : <Trans>Pause</Trans>}
              </button>
              <button
                type="button"
                disabled={terminal || phase === "paused" || busy === goal.id}
                onClick={() => void wake(goal)}
              >
                <Trans>Review now</Trans>
              </button>
              <button
                type="button"
                className="danger"
                disabled={terminal || busy === goal.id}
                onClick={() => void control(goal, "cancel")}
              >
                <Trans>Cancel goal</Trans>
              </button>
            </div>
          </article>
        );
      })}
    </section>
  );
}
