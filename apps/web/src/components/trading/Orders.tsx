import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import type { Order } from "../../lib/api";
import { executeTrade } from "../../lib/trading";
import { userError } from "../../lib/user_error";
export function Orders({
  accountId,
  orders,
  onChange,
}: {
  accountId: string;
  orders: Order[];
  onChange: () => void;
}) {
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState("");
  return (
    <section className="card">
      <h2>
        <Trans>Pending orders</Trans>
      </h2>
      {error != null && <p role="alert">{userError(error)}</p>}
      {orders.map((o) => (
        <div className="row" key={o.id}>
          <bdi>
            {o.symbol} · {o.volume} · {o.price}
          </bdi>
          <button
            type="button"
            disabled={busy === o.id}
            onClick={async () => {
              setBusy(o.id);
              try {
                await executeTrade({
                  account_id: accountId,
                  operation_id: crypto.randomUUID(),
                  action: "cancel_order",
                  symbol: o.symbol,
                  order_id: o.id,
                });
                onChange();
              } catch (e) {
                setError(e);
              } finally {
                setBusy("");
              }
            }}
          >
            <Trans>Cancel order</Trans>
          </button>
        </div>
      ))}
      {!orders.length && (
        <p className="muted">
          <Trans>No pending orders</Trans>
        </p>
      )}
    </section>
  );
}
