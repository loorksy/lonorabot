import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import type { TradingControls } from "../../lib/api";
import { readControls, setControls } from "../../lib/trading";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
export function TradingStatus() {
  const { revision, refresh } = useClient();
  const [control, setControl] = useState<TradingControls>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    void readControls().then(setControl).catch(setError);
  }, [revision]);
  async function change(next: TradingControls) {
    setBusy(true);
    try {
      setControl(await setControls(next));
      refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card trading-control">
      <div>
        <h2>
          <Trans>Trading control</Trans>
        </h2>
        <p role="status">
          {control?.emergency_stop ? (
            <Trans>Emergency stop active</Trans>
          ) : control?.enabled ? (
            <Trans>Trading ON</Trans>
          ) : (
            <Trans>Trading OFF</Trans>
          )}
        </p>
      </div>
      <div className="actions">
        <button
          type="button"
          disabled={busy || !control || control.emergency_stop}
          className={control?.enabled ? "" : "primary"}
          onClick={() => void change({ enabled: !control?.enabled, emergency_stop: false })}
        >
          {control?.enabled ? <Trans>Turn trading OFF</Trans> : <Trans>Turn trading ON</Trans>}
        </button>
        <button
          type="button"
          className="danger"
          disabled={busy}
          onClick={() => void change({ enabled: false, emergency_stop: true })}
        >
          <Trans>Emergency Stop</Trans>
        </button>
        {control?.emergency_stop && (
          <button
            type="button"
            disabled={busy}
            onClick={() => void change({ enabled: false, emergency_stop: false })}
          >
            <Trans>Reset emergency stop</Trans>
          </button>
        )}
      </div>
      {error != null && <p role="alert">{userError(error)}</p>}
    </section>
  );
}
