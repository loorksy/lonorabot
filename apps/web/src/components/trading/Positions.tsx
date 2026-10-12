import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import type { Position } from "../../lib/api";
import { executeTrade } from "../../lib/trading";
import { userError } from "../../lib/user_error";
export function Positions({
  accountId,
  positions,
  onChange,
}: {
  accountId: string;
  positions: Position[];
  onChange: () => void;
}) {
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState("");
  async function close(p: Position) {
    setBusy(p.id);
    try {
      await executeTrade({
        account_id: accountId,
        operation_id: crypto.randomUUID(),
        action: "close_position",
        symbol: p.symbol,
        position_id: p.id,
      });
      onChange();
    } catch (e) {
      setError(e);
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="card">
      <h2>
        <Trans>Positions</Trans>
      </h2>
      {error != null && <p role="alert">{userError(error)}</p>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>
                <Trans>Symbol</Trans>
              </th>
              <th>
                <Trans>Side</Trans>
              </th>
              <th>
                <Trans>Volume</Trans>
              </th>
              <th>
                <Trans>Open price</Trans>
              </th>
              <th>
                <Trans>Profit</Trans>
              </th>
              <th>
                <Trans>Action</Trans>
              </th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.id}>
                <td>
                  <bdi>{p.symbol}</bdi>
                </td>
                <td>{p.side === "buy" ? <Trans>Buy</Trans> : <Trans>Sell</Trans>}</td>
                <td>{p.volume}</td>
                <td>{p.open_price}</td>
                <td>{p.profit}</td>
                <td>
                  <button type="button" disabled={busy === p.id} onClick={() => void close(p)}>
                    <Trans>Close position</Trans>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!positions.length && (
        <p className="muted">
          <Trans>No open positions</Trans>
        </p>
      )}
    </section>
  );
}
