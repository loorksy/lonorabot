import { Trans } from "@lingui/react/macro";
import type { Journal } from "../../lib/api";
export function TradingJournal({ entries }: { entries: Journal[] }) {
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
        <details key={e.operation_id} className="run-item">
          <summary>
            <bdi>{String(e.request.symbol ?? "")}</bdi>
            <span>
              {e.status === "confirmed" ? (
                <Trans>Confirmed</Trans>
              ) : e.status === "failed" ? (
                <Trans>Failed</Trans>
              ) : (
                <Trans>Awaiting reconciliation</Trans>
              )}
            </span>
            <time>{new Date(e.updated_at).toLocaleString()}</time>
          </summary>
          <code>{e.operation_id}</code>
          <pre className="wrap" dir="ltr">
            {JSON.stringify(e.result, null, 2)}
          </pre>
        </details>
      ))}
    </section>
  );
}
