import { Trans } from "@lingui/react/macro";
import { useEffect, useMemo, useState } from "react";
import type { Agent, Resource } from "../../lib/api";
import { resources } from "../../lib/rpc";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { AgentPicker } from "../agents/AgentPicker";
export function MarketWatch({
  accountId,
  symbol,
  agents,
}: {
  accountId: string;
  symbol: string;
  agents: Agent[];
}) {
  const { revision, refresh } = useClient();
  const [rows, setRows] = useState<Resource[]>([]);
  const [agent, setAgent] = useState(agents[0]?.id ?? "");
  const [condition, setCondition] = useState("cross_above");
  const [level, setLevel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState<unknown>();
  const service = useMemo(() => resources("/watches"), []);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    void service.list().then(setRows).catch(setError);
  }, [revision, service]);
  return (
    <details className="card">
      <summary>
        <Trans>Market watches</Trans>
      </summary>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await service.create(
              {
                account_id: accountId,
                symbol,
                condition,
                level,
                prompt,
                enabled: true,
                cooldown_seconds: 300,
                interval_seconds: 30,
              },
              agent,
            );
            refresh();
            setPrompt("");
          } catch (err) {
            setError(err);
          }
        }}
      >
        <AgentPicker agents={agents} value={agent} onChange={setAgent} />
        <label>
          <Trans>Condition</Trans>
          <select value={condition} onChange={(e) => setCondition(e.target.value)}>
            <option value="cross_above">
              <Trans>Crosses above</Trans>
            </option>
            <option value="cross_below">
              <Trans>Crosses below</Trans>
            </option>
            <option value="above">
              <Trans>Above</Trans>
            </option>
            <option value="below">
              <Trans>Below</Trans>
            </option>
          </select>
        </label>
        <label>
          <Trans>Price level</Trans>
          <input
            required
            dir="ltr"
            type="number"
            step="any"
            min="0.00000001"
            value={level}
            onChange={(e) => setLevel(e.target.value)}
          />
        </label>
        <label>
          <Trans>Task when triggered</Trans>
          <textarea required value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        </label>
        <button type="submit" disabled={!accountId || !symbol || !agent}>
          <Trans>Create watch</Trans>
        </button>
      </form>
      {error != null && <p role="alert">{userError(error)}</p>}
      {rows.map((w) => (
        <div className="row" key={w.id}>
          <bdi>
            {String(w.payload.symbol)} · {String(w.payload.level)}
          </bdi>
          <button
            type="button"
            onClick={() =>
              void service
                .update(w, { ...w.payload, enabled: !w.payload.enabled })
                .then(refresh)
                .catch(setError)
            }
          >
            {w.payload.enabled ? <Trans>Pause</Trans> : <Trans>Resume</Trans>}
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => void service.delete(w.id).then(refresh).catch(setError)}
          >
            <Trans>Delete</Trans>
          </button>
        </div>
      ))}
    </details>
  );
}
