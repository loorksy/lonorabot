import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { api } from "../../lib/api";
import { connectBroker } from "../../lib/trading";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
export function BrokerConnection() {
  const { refresh } = useClient();
  const [provider, setProvider] = useState("metaapi");
  const [account, setAccount] = useState("");
  const [key, setKey] = useState("");
  const [snapshot, setSnapshot] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  return (
    <details className="card">
      <summary>
        <Trans>Add broker connection</Trans>
      </summary>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const parsed = provider === "simulation" ? JSON.parse(snapshot) : null;
            const row = await connectBroker({
              provider,
              account_id: account,
              region: "london",
              enabled: true,
              secret_id: null,
              api_key: key || null,
            });
            if (parsed)
              await api.post(`/trading/connections/${row.id}/simulation`, { snapshot: parsed });
            setKey("");
            setAccount("");
            refresh();
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          <Trans>Connection type</Trans>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="metaapi">MetaApi</option>
            <option value="simulation">
              <Trans>Simulation with an imported snapshot</Trans>
            </option>
          </select>
        </label>
        <label>
          <Trans>Account ID</Trans>
          <input dir="ltr" required value={account} onChange={(e) => setAccount(e.target.value)} />
        </label>
        {provider === "metaapi" ? (
          <label>
            <Trans>MetaApi token</Trans>
            <input
              type="password"
              autoComplete="off"
              required
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
          </label>
        ) : (
          <label>
            <Trans>Simulation snapshot JSON</Trans>
            <textarea
              rows={6}
              dir="ltr"
              required
              value={snapshot}
              onChange={(e) => setSnapshot(e.target.value)}
            />
            <small className="muted">
              <Trans>
                Supply account, instruments, quotes and candles explicitly. Simulation data is
                labelled in the workspace.
              </Trans>
            </small>
          </label>
        )}
        <button type="submit" className="primary" disabled={busy}>
          <Trans>Connect account</Trans>
        </button>
        {error != null && <p role="alert">{userError(error)}</p>}
      </form>
    </details>
  );
}
