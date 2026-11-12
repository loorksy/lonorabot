import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Payload, type Resource } from "../../lib/api";
import { goalStatusLabel as statusLabel } from "../../lib/goal-status";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

type GoalResource = Resource & { state: Payload };

function GoalHistory({
  id,
  revision,
  stepTitles,
}: {
  id: string;
  revision: number;
  stepTitles: Record<string, string>;
}) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Payload[]>([]);
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    void revision;
    if (!open) return;
    let live = true;
    setLoading(true);
    setError(undefined);
    void api
      .get<Payload[]>(`/trading/goals/${encodeURIComponent(id)}/decisions`)
      .then((values) => {
        if (live) setRows(values);
      })
      .catch((failure) => {
        if (live) setError(failure);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [id, revision, open]);
  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        <Trans>Execution history</Trans>
      </summary>
      {loading && (
        <p role="status">
          <Trans>Loading…</Trans>
        </p>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
      {!loading && error == null && rows.length === 0 && (
        <p>
          <Trans>No financial executions yet.</Trans>
        </p>
      )}
      {rows.map((row) => (
        <article className="card stack" key={String(row.id)} data-goal-decision={String(row.id)}>
          <p>
            <bdi>{stepTitles[String(row.step_id)] ?? t`Plan step`}</bdi> · {statusLabel(row.status)}
          </p>
          {/* Identifiers and raw records are for support, never the normal view. */}
          <details className="technical-details">
            <summary>
              <Trans>Technical details</Trans>
            </summary>
            <p>
              <Trans>Operation</Trans>: <bdi dir="ltr">{String(row.operation_id)}</bdi>
            </p>
            <p>
              <Trans>Decision evidence</Trans>
            </p>
            <pre dir="ltr">{JSON.stringify(row.evidence, null, 2)}</pre>
            <p>
              <Trans>Broker result</Trans>
            </p>
            <pre dir="ltr">{JSON.stringify(row.result, null, 2)}</pre>
          </details>
        </article>
      ))}
    </details>
  );
}

export function TradingGoals({ agentId }: { agentId: string }) {
  const { revision, refresh } = useClient();
  const [goals, setGoals] = useState<GoalResource[]>([]);
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const [loadedAgent, setLoadedAgent] = useState("");
  const currentAgent = useRef(agentId);
  currentAgent.current = agentId;
  const [busy, setBusy] = useState("");
  const applyRows = useCallback(
    (rows: GoalResource[]) => {
      if (currentAgent.current !== agentId) return;
      setGoals((previous) =>
        rows
          .filter((row) => row.agent_id === agentId)
          .map((row) => {
            const current = previous.find((item) => item.id === row.id);
            return current && current.version > row.version ? current : row;
          }),
      );
      setLoadedAgent(agentId);
    },
    [agentId],
  );
  const reload = useCallback(async () => {
    const rows = await api.get<GoalResource[]>(
      `/trading/goals?agent_id=${encodeURIComponent(agentId)}`,
    );
    applyRows(rows);
  }, [agentId, applyRows]);
  useEffect(() => {
    void revision;
    let active = true;
    setLoading(true);
    setError(undefined);
    void api
      .get<GoalResource[]>(`/trading/goals?agent_id=${encodeURIComponent(agentId)}`)
      .then((rows) => {
        if (active) applyRows(rows);
      })
      .catch((failure) => {
        if (active) setError(failure);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [agentId, revision, applyRows]);
  async function control(goal: GoalResource, action: string) {
    setBusy(goal.id);
    setError(undefined);
    try {
      // A goal is a plan under the agent's trading level and grant: its owner controls
      // pause, resume and cancel it, and never change authority.
      await api.post(`/trading/goals/${goal.id}/control`, { version: goal.version, action });
      await reload();
      refresh();
    } catch (failure) {
      setError(failure);
      await reload().catch(() => undefined);
    } finally {
      setBusy("");
    }
  }
  async function wake(goal: GoalResource) {
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
      {(loading || loadedAgent !== agentId) && error == null && (
        <p role="status">
          <Trans>Loading…</Trans>
        </p>
      )}
      {!loading && loadedAgent === agentId && error == null && goals.length === 0 && (
        <p>
          <Trans>No trading goals yet.</Trans>
        </p>
      )}
      {goals
        .filter((goal) => goal.agent_id === agentId)
        .map((goal) => {
          const phase = String(goal.state.status ?? "planning").toLowerCase();
          const terminal = ["cancelled", "completed"].includes(phase);
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
              {typeof goal.state.code === "string" && (
                <p role="status">{userError({ code: goal.state.code })}</p>
              )}
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
              <GoalHistory
                id={goal.id}
                revision={goal.version}
                stepTitles={Object.fromEntries(
                  steps.map((step) => [String(step.id), String(step.title ?? "")]),
                )}
              />
              <p className="muted">
                <Trans>
                  This goal is a plan under the agent's trading level and signed grant. Your pauses
                  and the account's money limits still apply to every order. Pausing a goal does not
                  close existing broker positions.
                </Trans>
              </p>
              <div className="row">
                <button
                  type="button"
                  disabled={terminal || busy === goal.id}
                  onClick={() =>
                    void control(goal, ["paused", "blocked"].includes(phase) ? "resume" : "pause")
                  }
                >
                  {["paused", "blocked"].includes(phase) ? (
                    <Trans>Resume</Trans>
                  ) : (
                    <Trans>Pause</Trans>
                  )}
                </button>
                <button
                  type="button"
                  disabled={terminal || ["paused", "blocked"].includes(phase) || busy === goal.id}
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
