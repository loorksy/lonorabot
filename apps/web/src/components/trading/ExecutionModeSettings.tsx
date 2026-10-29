import { Trans } from "@lingui/react/macro";
import type { Agent, PerformanceSummary, ShadowTradeSummary } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

export function ExecutionModeSettings({ agent }: { agent: Agent }) {
  const { refresh } = useClient();
  const [mode, setMode] = useState(agent.execution_mode ?? "live");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [summary, setSummary] = useState<PerformanceSummary>();
  const [trades, setTrades] = useState<ShadowTradeSummary[]>([]);
  useEffect(() => {
    let active = true;
    setSummary(undefined);
    setTrades([]);
    void api
      .get<PerformanceSummary>(`/agents/${agent.id}/performance?execution_mode=${mode}`)
      .then((value) => {
        if (active) setSummary(value);
      })
      .catch((failure) => {
        if (active) setError(failure);
      });
    void api
      .get<{ trades: ShadowTradeSummary[] }>(`/agents/${agent.id}/shadow-trades`)
      .then((value) => {
        if (active) setTrades(value.trades);
      })
      .catch((failure) => {
        if (active) setError(failure);
      });
    return () => {
      active = false;
    };
  }, [agent.id, mode]);
  return (
    <fieldset disabled={busy}>
      <legend>
        <Trans>Execution mode</Trans>
      </legend>
      <label className="check">
        <input
          type="checkbox"
          role="switch"
          data-lonora-switch="true"
          aria-checked={mode === "shadow"}
          checked={mode === "shadow"}
          onChange={async (event) => {
            const next = event.target.checked ? "shadow" : "live";
            setBusy(true);
            setError(undefined);
            try {
              const saved = await api.put<Agent>(`/agents/${agent.id}/execution-mode`, {
                execution_mode: next,
              });
              setMode(saved.execution_mode ?? "live");
              refresh();
            } catch (failure) {
              setError(failure);
            } finally {
              setBusy(false);
            }
          }}
        />
        <Trans>Shadow trading — virtual orders only</Trans>
      </label>
      <p className="muted">
        <Trans>
          Changing mode pauses active trading goals. Live trading still requires existing approvals
          and safety controls.
        </Trans>
      </p>
      {summary && (
        <p>
          {mode === "shadow" ? (
            <Trans>Shadow observations</Trans>
          ) : (
            <Trans>Live observations</Trans>
          )}
          : {summary.sample_count}
          {summary.sample_state === "insufficient_data" && (
            <>
              {" "}
              · <Trans>Insufficient data for performance conclusions</Trans>
            </>
          )}
        </p>
      )}
      {trades.length > 0 && (
        <details>
          <summary>
            <Trans>Shadow history</Trans>
          </summary>
          <p className="muted">
            <Trans>Sampled quote fills are hypothetical. Monetary profit is unavailable.</Trans>
          </p>
          <ul>
            {trades.slice(0, 20).map((trade) => (
              <li key={trade.id}>
                <bdi>{trade.symbol}</bdi> · <Trans>Virtual</Trans> ·{" "}
                <bdi>
                  {trade.state.entry_price ?? "—"} → {trade.state.exit_price ?? "—"}
                </bdi>
              </li>
            ))}
          </ul>
        </details>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
    </fieldset>
  );
}
