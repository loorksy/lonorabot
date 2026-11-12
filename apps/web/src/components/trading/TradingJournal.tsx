import { i18n } from "@lingui/core";
import { Trans } from "@lingui/react/macro";
import { brokerTicketLabel } from "@lonora/core";
import type { Journal } from "../../lib/api";
import { operationStatusLabel } from "../../lib/operation-status";

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
          {typeof e.result.broker_id === "string" && e.result.broker_id && (
            <p>
              {brokerTicketLabel(i18n.locale)}: <bdi dir="ltr">{e.result.broker_id}</bdi>
            </p>
          )}
          {/* An uncertain operation is settled on its Settle card in the conversation (6.8). */}
          {/* Identifiers and raw records are for support, never the normal view. */}
          <details className="technical-details">
            <summary>
              <Trans>Technical details</Trans>
            </summary>
            <code dir="ltr">{e.operation_id}</code>
            <pre className="wrap" dir="ltr">
              {JSON.stringify(e.result, null, 2)}
            </pre>
          </details>
        </details>
      ))}
    </section>
  );
}
