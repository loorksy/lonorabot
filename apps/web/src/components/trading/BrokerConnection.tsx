import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { api } from "../../lib/api";
import { connectBroker } from "../../lib/trading";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
export function BrokerConnection() {
  const { refresh } = useClient();
  const [account, setAccount] = useState("");
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
            const parsed = JSON.parse(snapshot);
            const row = await connectBroker({
              provider: "simulation",
              account_id: account,
              region: null,
              enabled: true,
              secret_id: null,
              api_key: null,
            });
            await api.post(`/trading/connections/${row.id}/simulation`, { snapshot: parsed });
            setAccount("");
            refresh();
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <p className="muted">
          <Trans>
            Simulation with an imported snapshot. A real trading account is connected from chat:
            ask Lonora to connect it.
          </Trans>
        </p>
        <label>
          <Trans>Account ID</Trans>
          <input dir="ltr" required value={account} onChange={(e) => setAccount(e.target.value)} />
        </label>
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
        <button type="submit" className="primary" disabled={busy}>
          <Trans>Connect account</Trans>
        </button>
        {error != null && <p role="alert">{userError(error)}</p>}
      </form>
    </details>
  );
}
