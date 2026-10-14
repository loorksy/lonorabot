import { Trans } from "@lingui/react/macro";
import type { TradeApproval as Approval } from "@lonora/contracts";
import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

const rank = { pending: 0, approved: 1, rejected: 1, completed: 2, cancelled: 2 };
function merge(previous: Approval[], rows: Approval[]) {
  return rows.map((row) => {
    const old = previous.find((entry) => entry.id === row.id);
    return old &&
      (rank[old.status] > rank[row.status] ||
        (old.status === row.status && old.results.length > row.results.length))
      ? old
      : row;
  });
}

export function TradeApprovals({ threadId, since }: { threadId: string; since?: number }) {
  const { revision } = useClient();
  const [rows, setRows] = useState<Approval[]>([]);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState<string>();
  const pending = useRef(false);
  const callRequests = useRef(new Set<string>());
  const currentThread = useRef(threadId);
  currentThread.current = threadId;
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<Approval[]>(`/trading/approvals?thread_id=${encodeURIComponent(threadId)}`)
      .then((data) => {
        if (live) {
          for (const row of data) if (row.status === "pending") callRequests.current.add(row.id);
          setRows((old) => merge(old, data));
          setError(undefined);
        }
      })
      .catch((caught: unknown) => {
        if (live) setError(caught);
      });
    return () => {
      live = false;
    };
  }, [threadId, revision]);
  async function decide(id: string, decision: "approve" | "reject") {
    if (pending.current) return;
    pending.current = true;
    setBusy(id);
    setError(undefined);
    try {
      const row = await api.post<Approval>(`/trading/approvals/${id}/decision`, { decision });
      if (currentThread.current === threadId)
        setRows((old) =>
          merge(
            old,
            old.map((item) => (item.id === id ? row : item)),
          ),
        );
    } catch (caught) {
      if (currentThread.current === threadId) setError(caught);
    } finally {
      pending.current = false;
      setBusy(undefined);
    }
  }
  return (
    <>
      {error != null && <p role="alert">{userError(error)}</p>}
      {rows
        .filter(
          (row) =>
            row.thread_id === threadId &&
            (since === undefined ||
              row.status === "pending" ||
              Date.parse(row.created_at) >= since ||
              callRequests.current.has(row.id)),
        )
        .map((row) => (
          <article className="card" key={row.id} data-trade-approval={row.id}>
            <strong>
              <Trans>Trading request</Trans>
            </strong>
            {row.requests.map((request, index) => (
              <dl key={String(request.operation_id ?? index)}>
                <dt>
                  <Trans>Action</Trans>
                </dt>
                <dd>
                  <bdi>{String(request.action)}</bdi>
                </dd>
                <dt>
                  <Trans>Symbol</Trans>
                </dt>
                <dd>
                  <bdi>{String(request.symbol)}</bdi>
                </dd>
                {request.volume != null && (
                  <>
                    <dt>
                      <Trans>Volume</Trans>
                    </dt>
                    <dd>
                      <bdi>{String(request.volume)}</bdi>
                    </dd>
                  </>
                )}
                {request.price != null && (
                  <>
                    <dt>
                      <Trans>Price</Trans>
                    </dt>
                    <dd>
                      <bdi>{String(request.price)}</bdi>
                    </dd>
                  </>
                )}
                {request.stop_loss != null && (
                  <>
                    <dt>
                      <Trans>Stop loss</Trans>
                    </dt>
                    <dd>
                      <bdi>{String(request.stop_loss)}</bdi>
                    </dd>
                  </>
                )}
                {request.clear_stop_loss === true && (
                  <p>
                    <Trans>Remove stop loss</Trans>
                  </p>
                )}
                {request.clear_take_profit === true && (
                  <p>
                    <Trans>Remove take profit</Trans>
                  </p>
                )}
                {request.take_profit != null && (
                  <>
                    <dt>
                      <Trans>Take profit</Trans>
                    </dt>
                    <dd>
                      <bdi>{String(request.take_profit)}</bdi>
                    </dd>
                  </>
                )}
                {(request.position_id ?? request.order_id) != null && (
                  <>
                    <dt>
                      <Trans>Broker ticket</Trans>
                    </dt>
                    <dd>
                      <bdi>{String(request.position_id ?? request.order_id)}</bdi>
                    </dd>
                  </>
                )}
              </dl>
            ))}
            {row.status === "pending" ? (
              <div className="actions">
                <button
                  type="button"
                  disabled={busy != null}
                  onClick={() => void decide(row.id, "approve")}
                >
                  <Trans>Approve</Trans>
                </button>
                <button
                  type="button"
                  disabled={busy != null}
                  onClick={() => void decide(row.id, "reject")}
                >
                  <Trans>Reject</Trans>
                </button>
              </div>
            ) : (
              <p>
                {row.status === "cancelled" ? (
                  <Trans>Cancelled</Trans>
                ) : row.status === "rejected" ? (
                  <Trans>Rejected</Trans>
                ) : row.status === "approved" ? (
                  <Trans>Approved — awaiting broker result</Trans>
                ) : (
                  <Trans>Broker result</Trans>
                )}
              </p>
            )}
            {row.results.map((result) => (
              <div key={result.operation_id} data-trade-result={result.status}>
                <p>
                  {result.status === "confirmed" ? (
                    <Trans>Confirmed</Trans>
                  ) : result.status === "ambiguous" ? (
                    <Trans>Awaiting reconciliation</Trans>
                  ) : result.status === "failed" ? (
                    <Trans>Failed</Trans>
                  ) : (
                    <Trans>Submitted</Trans>
                  )}
                </p>
                {result.broker_id && (
                  <p>
                    <Trans>Broker ticket</Trans>: <bdi>{result.broker_id}</bdi>
                  </p>
                )}
                {result.code && (
                  <p>
                    <bdi>{result.code}</bdi>
                  </p>
                )}
                {Object.entries(result.details ?? {})
                  .filter(([key]) =>
                    [
                      "price",
                      "execution_price",
                      "order_id",
                      "deal_id",
                      "position_id",
                      "numeric_code",
                      "string_code",
                      "message",
                      "description",
                    ].includes(key),
                  )
                  .map(([key, value]) => (
                    <p key={key}>
                      <bdi>{String(value)}</bdi>
                    </p>
                  ))}
              </div>
            ))}
          </article>
        ))}
    </>
  );
}
