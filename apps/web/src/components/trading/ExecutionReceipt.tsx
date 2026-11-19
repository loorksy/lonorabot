import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { ExecutionReceipt } from "@lonora/contracts";
import { orderLineAction } from "@lonora/core";
import { Icon } from "@lonora/ui-web";

/**
 * The Execution Receipt (mandate 10.3, 11.2): a fixed card the server posts when the
 * broker confirms an operation. Every fact comes from the receipt record (the broker's
 * own numbers); the agent's reason is labelled as the agent's words. It never reads as
 * verified before the account state was read back.
 */
export function ExecutionReceiptCard({ row }: { row: ExecutionReceipt }) {
  const action = orderLineAction({ action: row.action }, i18n.locale);
  const facts: [string, string | null | undefined][] = [[t`Broker ticket`, row.ticket]];
  if (row.kind === "fill") {
    facts.push([t`Volume`, row.volume], [t`Fill price`, row.price]);
  } else if (row.kind === "order") {
    facts.push(
      [t`Volume`, row.volume],
      [t`Order price`, row.price],
      [t`Stop loss`, row.stop_loss],
      [t`Take profit`, row.take_profit],
    );
  } else if (row.kind === "modify") {
    facts.push(
      [t`New price`, row.price],
      [t`New stop loss`, row.stop_loss],
      [t`New take profit`, row.take_profit],
    );
  }
  return (
    <div
      className="mcard is-done"
      data-execution-receipt={row.operation_id}
      data-receipt-kind={row.kind}
      data-receipt-verification={row.verification ?? "none"}
    >
      <div className="mcard-kicker">
        <Icon name="check" />
        <Trans>Execution receipt</Trans>
        {" · "}
        <bdi>{row.symbol}</bdi>
      </div>
      <div className="mcard-request">
        <strong dir="auto">
          {action.label}
          {row.partial && (
            <>
              {" · "}
              <Trans>Partially filled</Trans>
            </>
          )}
        </strong>
        <dl className="mcard-facts">
          {facts
            .filter(([, value]) => value != null && value !== "")
            .map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd className="ltr">{value}</dd>
              </div>
            ))}
          {row.stop_loss_removed && (
            <div>
              <dt>
                <Trans>Stop loss</Trans>
              </dt>
              <dd>
                <Trans>Removed</Trans>
              </dd>
            </div>
          )}
          {row.take_profit_removed && (
            <div>
              <dt>
                <Trans>Take profit</Trans>
              </dt>
              <dd>
                <Trans>Removed</Trans>
              </dd>
            </div>
          )}
        </dl>
      </div>
      <div
        className={`od-ev ${
          row.verification === "unverified"
            ? "warn"
            : row.verification === "pending"
              ? "wait"
              : "ok"
        }`}
        data-receipt-status
      >
        <Icon
          name={
            row.verification === "unverified"
              ? "alert"
              : row.verification === "pending"
                ? "hourglass"
                : "check"
          }
        />
        <span>
          <Trans>Confirmed by the broker</Trans>
          {row.verification === "verified" ? (
            <>
              {" · "}
              <Trans>Account state verified</Trans>
            </>
          ) : row.verification === "unverified" ? (
            <>
              {" · "}
              <Trans>The account state could not be verified</Trans>
            </>
          ) : row.verification === "pending" ? (
            <>
              {" · "}
              <Trans>Checking the account state…</Trans>
            </>
          ) : null}
        </span>
      </div>
      {row.reason && (
        <div className="mcard-reason" data-receipt-reason>
          <span className="oa-line-kind">
            <Trans>In the agent's words</Trans>
          </span>
          <p dir="auto">{row.reason}</p>
        </div>
      )}
    </div>
  );
}
