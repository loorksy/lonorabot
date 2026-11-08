import { i18n } from "@lingui/core";
import { Trans } from "@lingui/react/macro";
import { financialBoundaryError } from "@lonora/core";
import type { Journal, Position } from "../../lib/api";
import { operationStatusLabel, operationUnsettled } from "../../lib/operation-status";
import { userError } from "../../lib/user_error";
import { useTicketAction } from "./useTicketAction";

export function Positions({
  accountId,
  positions,
  journal,
  onChange,
}: {
  accountId: string;
  positions: Position[];
  journal?: Journal[];
  onChange: () => void;
}) {
  const close = useTicketAction("close_position", accountId, journal, onChange);
  return (
    <section className="card">
      <h2>
        <Trans>Positions</Trans>
      </h2>
      {close.error != null && <p role="alert">{userError(close.error)}</p>}
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
            {positions.map((p) => {
              const outcome = close.outcome(p.id);
              const unsettled = outcome != null && operationUnsettled(outcome.status);
              return (
                <tr key={p.id} data-position-id={p.id}>
                  <td>
                    <bdi>{p.symbol}</bdi>
                  </td>
                  <td>{p.side === "buy" ? <Trans>Buy</Trans> : <Trans>Sell</Trans>}</td>
                  <td>{p.volume}</td>
                  <td>{p.open_price}</td>
                  <td>{p.profit}</td>
                  <td>
                    <button
                      type="button"
                      disabled={close.busy(p.id)}
                      onClick={() =>
                        void close.run(p.id, {
                          action: "close_position",
                          symbol: p.symbol,
                          position_id: p.id,
                        })
                      }
                    >
                      {close.held(p.id) ? (
                        <Trans>Check close result</Trans>
                      ) : (
                        <Trans>Close position</Trans>
                      )}
                    </button>
                    {outcome && (
                      <p role="status" data-operation-status={outcome.status}>
                        {operationStatusLabel(outcome.status, outcome.details)}
                        {unsettled && (
                          <>
                            {" "}
                            <Trans>This operation will not be sent again.</Trans>
                          </>
                        )}
                        {financialBoundaryError(outcome.code, i18n.locale) && (
                          <> {financialBoundaryError(outcome.code, i18n.locale)}</>
                        )}
                      </p>
                    )}
                  </td>
                </tr>
              );
            })}
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
