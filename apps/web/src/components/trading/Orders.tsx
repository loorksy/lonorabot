import { i18n } from "@lingui/core";
import { Trans } from "@lingui/react/macro";
import { financialBoundaryError } from "@lonora/core";
import type { Journal, Order } from "../../lib/api";
import { operationStatusLabel, operationUnsettled } from "../../lib/operation-status";
import { userError } from "../../lib/user_error";
import { useTicketAction } from "./useTicketAction";

export function Orders({
  accountId,
  orders,
  journal,
  onChange,
}: {
  accountId: string;
  orders: Order[];
  journal?: Journal[];
  onChange: () => void;
}) {
  const cancel = useTicketAction("cancel_order", accountId, journal, onChange);
  return (
    <section className="card">
      <h2>
        <Trans>Pending orders</Trans>
      </h2>
      {cancel.error != null && <p role="alert">{userError(cancel.error)}</p>}
      {orders.map((o) => {
        const outcome = cancel.outcome(o.id);
        return (
          <div className="row" key={o.id} data-order-id={o.id}>
            <bdi>
              {o.symbol} · {o.volume} · {o.price}
            </bdi>
            <button
              type="button"
              disabled={cancel.busy(o.id)}
              onClick={() =>
                void cancel.run(o.id, { action: "cancel_order", symbol: o.symbol, order_id: o.id })
              }
            >
              {cancel.held(o.id) ? <Trans>Check cancel result</Trans> : <Trans>Cancel order</Trans>}
            </button>
            {outcome && (
              <span role="status" data-operation-status={outcome.status}>
                {operationStatusLabel(outcome.status, outcome.details)}
                {operationUnsettled(outcome.status) && (
                  <>
                    {" "}
                    <Trans>This operation will not be sent again.</Trans>
                  </>
                )}
                {financialBoundaryError(outcome.code, i18n.locale) && (
                  <> {financialBoundaryError(outcome.code, i18n.locale)}</>
                )}
              </span>
            )}
          </div>
        );
      })}
      {!orders.length && (
        <p className="muted">
          <Trans>No pending orders</Trans>
        </p>
      )}
    </section>
  );
}
