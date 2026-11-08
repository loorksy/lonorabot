import { i18n } from "@lingui/core";
import { tradingSafetyText } from "@lonora/core";
import { useEffect, useState } from "react";
import type { TradingControls } from "../../lib/api";
import { readControls, resumeTrading, stopNewTrading, tradingStopped } from "../../lib/trading";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

/**
 * One brake: "Stop new trading" stops new risk for every agent and the owner's manual
 * orders; exits stay allowed. Resume is one tap and widens no authority.
 */
export function TradingStatus() {
  const { revision, refresh } = useClient();
  const [control, setControl] = useState<TradingControls>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const text = tradingSafetyText(i18n.locale);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    void readControls().then(setControl).catch(setError);
  }, [revision]);
  async function change(next: () => Promise<TradingControls>) {
    setBusy(true);
    try {
      setControl(await next());
      setError(undefined);
      refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const stopped = control ? tradingStopped(control) : null;
  return (
    <section className="card trading-control" data-testid="trading-control">
      <div>
        <h2>{text.title}</h2>
        <p
          role="status"
          data-trading-state={stopped == null ? "" : stopped ? "stopped" : "running"}
        >
          {stopped == null ? text.loading : stopped ? text.stopped : text.running}
        </p>
        <p className="muted">{stopped ? text.resumeHint : text.stopHint}</p>
      </div>
      <div className="actions">
        {stopped === false && (
          <button
            type="button"
            className="danger"
            disabled={busy}
            onClick={() => void change(stopNewTrading)}
          >
            {text.stop}
          </button>
        )}
        {stopped && (
          <button
            type="button"
            className="primary"
            disabled={busy}
            onClick={() => void change(resumeTrading)}
          >
            {text.resume}
          </button>
        )}
      </div>
      {error != null && <p role="alert">{userError(error)}</p>}
    </section>
  );
}
