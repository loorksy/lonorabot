import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import type { Journal, OperationResolution } from "../../lib/api";
import { operationStatusLabel } from "../../lib/operation-status";
import { resolveOperation } from "../../lib/trading";
import { userError } from "../../lib/user_error";

function ResolveOperation({ entry, onResolved }: { entry: Journal; onResolved: () => void }) {
  const [outcome, setOutcome] = useState<OperationResolution["outcome"]>("unknown");
  const [statement, setStatement] = useState("");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  return (
    <form
      className="form-grid"
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        try {
          await resolveOperation(entry.operation_id, {
            outcome,
            statement,
            broker_reference: reference.trim() || null,
          });
          setError(undefined);
          onResolved();
        } catch (caught) {
          setError(caught);
        } finally {
          setBusy(false);
        }
      }}
    >
      <p className="muted">
        <Trans>
          The broker could not establish this operation's outcome. Record what you verified at the
          broker. This settles the block on this market; it is not broker confirmation and nothing
          is sent again.
        </Trans>
      </p>
      <label>
        <Trans>What happened at the broker</Trans>
        <select
          value={outcome}
          onChange={(event) => setOutcome(event.target.value as OperationResolution["outcome"])}
        >
          <option value="executed">{t`It was executed`}</option>
          <option value="not_executed">{t`It was not executed`}</option>
          <option value="unknown">{t`Still unknown`}</option>
        </select>
      </label>
      <label>
        <Trans>Your statement</Trans>
        <textarea
          required
          maxLength={2000}
          value={statement}
          onChange={(event) => setStatement(event.target.value)}
        />
      </label>
      <label>
        <Trans>Broker reference (optional)</Trans>
        <input
          maxLength={200}
          value={reference}
          dir="ltr"
          onChange={(event) => setReference(event.target.value)}
        />
      </label>
      <button type="submit" disabled={busy || !statement.trim()}>
        <Trans>Record resolution</Trans>
      </button>
      {error != null && <p role="alert">{userError(error)}</p>}
    </form>
  );
}

export function TradingJournal({
  entries,
  onChange,
}: {
  entries: Journal[];
  onChange?: () => void;
}) {
  return (
    <section className="card">
      <h2>
        <Trans>Durable trading journal</Trans>
      </h2>
      {!entries.length && (
        <p className="muted">
          <Trans>No operations yet</Trans>
        </p>
      )}
      {entries.map((e) => (
        <details key={e.operation_id} className="run-item" data-operation-status={e.status}>
          <summary>
            <bdi>{String(e.request.symbol ?? "")}</bdi>
            <span>
              {operationStatusLabel(e.status, {
                ...(typeof e.result.details === "object" ? e.result.details : {}),
                ...(e.send_state ? { send_state: e.send_state } : {}),
                ...(e.resolution ? { resolution: e.resolution } : {}),
              })}
            </span>
            <time>{new Date(e.updated_at).toLocaleString()}</time>
          </summary>
          <code>{e.operation_id}</code>
          {e.status === "ambiguous" && onChange && (
            <ResolveOperation entry={e} onResolved={onChange} />
          )}
          <pre className="wrap" dir="ltr">
            {JSON.stringify(e.result, null, 2)}
          </pre>
        </details>
      ))}
    </section>
  );
}
