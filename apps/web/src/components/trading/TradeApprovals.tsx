import { i18n } from "@lingui/core";
import { Trans } from "@lingui/react/macro";
import type { TradeApproval as Approval } from "@lonora/contracts";
import {
  approvalEndTone,
  approvalStatusText,
  brokerPriceLabel,
  brokerTicketLabel,
  brokerWordsLabel,
  failedResultFallback,
  financialResultReason,
  orderLineAction,
} from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { operationStatusLabel } from "../../lib/operation-status";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

const rank: Record<string, number> = {
  pending: 0,
  approved: 1,
  rejected: 1,
  expired: 1,
  withdrawn: 1,
  drifted: 1,
  completed: 2,
  cancelled: 2,
};

/**
 * The reason under a broker result, from the table Mobile reads too. Only a result
 * known not to have executed may fall back to the error catalog, and a code it does not
 * know reads the shared fallback, as on Mobile; an uncertain result always says it will
 * not be sent again.
 */
function resultReason(result: Approval["results"][number]): string | null {
  const shared = financialResultReason(result.status, result.code, i18n.locale);
  if (shared || result.status !== "failed" || !result.code) return shared;
  return userError({ code: result.code }, failedResultFallback(i18n.locale));
}

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

export function useTradeApprovals(threadId: string, watching = false) {
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
    const load = () => {
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
    };
    load();
    if (!watching)
      return () => {
        live = false;
      };
    const timer = window.setInterval(load, 2000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [threadId, revision, watching]);
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
      // Decided elsewhere (its row, its slot, another device): a second tap shows the
      // record as the server holds it now (mandate 10.2.3).
      await api
        .get<Approval[]>(`/trading/approvals?thread_id=${encodeURIComponent(threadId)}`)
        .then((data) => {
          if (currentThread.current === threadId) setRows((old) => merge(old, data));
        })
        .catch(() => undefined);
    } finally {
      pending.current = false;
      setBusy(undefined);
    }
  }
  return {
    rows: rows.filter((row) => row.thread_id === threadId),
    error,
    busy,
    decide,
    callRequests: callRequests.current,
  };
}

/** The request in words and its volume («شراء 0.10»), never a raw action id. */
function RequestTitle({ request }: { request: Approval["requests"][number] }) {
  const action = orderLineAction(request, i18n.locale);
  return (
    <strong dir="auto">
      {action.label}
      {action.volume && (
        <>
          {" "}
          <span className="ltr">{action.volume}</span>
        </>
      )}
    </strong>
  );
}

/**
 * A trade approval in the conversation (reference apMarkup, Desktop-38): «طلب موافقة · SYMBOL»,
 * the request, «موافقة» / «رفض». A fixed card is never folded (10.2.2): decided, it keeps its
 * whole frame and shows its end state inside. A card has no time limit; a stored card that
 * expired offers «طلب جديد», which asks the agent again (it never creates an approvable
 * request by itself).
 */
export function TradeApprovalCard({
  row,
  busy,
  decide,
  onRenew,
}: {
  row: Approval;
  busy: boolean;
  decide: (id: string, decision: "approve" | "reject") => Promise<void>;
  onRenew?: (row: Approval) => void;
}) {
  const symbol = row.requests.find((request) => request.symbol)?.symbol;
  const status = row.status;
  // ok only once every result is confirmed; never a success look on a failure (0.4).
  const tone = approvalEndTone(row);
  return (
    <div
      className={`mcard${status === "pending" ? "" : " is-done"}`}
      data-trade-approval={row.id}
      data-trade-status={status}
    >
      <div className="mcard-kicker">
        <Icon name="shield" />
        <Trans>Approval request</Trans>
        {symbol && (
          <>
            {" · "}
            <bdi>{String(symbol)}</bdi>
          </>
        )}
      </div>
      {row.requests.map((request, index) => {
        const market = request.action === "buy" || request.action === "sell";
        return (
          <div key={String(request.operation_id ?? index)} className="mcard-request">
            <RequestTitle request={request} />
            <dl className="oa-dl">
              {(market || request.price != null) && (
                <div>
                  <dt>
                    <Trans>Entry</Trans>
                  </dt>
                  {market ? (
                    <dd>
                      <Trans>At market price</Trans>
                    </dd>
                  ) : (
                    <dd className="ltr">{String(request.price)}</dd>
                  )}
                </div>
              )}
              {request.stop_loss != null && (
                <div>
                  <dt>
                    <Trans>Stop loss</Trans>
                  </dt>
                  <dd className="ltr">{String(request.stop_loss)}</dd>
                </div>
              )}
              {request.take_profit != null && (
                <div>
                  <dt>
                    <Trans>Take profit</Trans>
                  </dt>
                  <dd className="ltr">{String(request.take_profit)}</dd>
                </div>
              )}
              {request.clear_stop_loss === true && (
                <div>
                  <dt>
                    <Trans>Stop loss</Trans>
                  </dt>
                  <dd>
                    <Trans>Remove stop loss</Trans>
                  </dd>
                </div>
              )}
              {request.clear_take_profit === true && (
                <div>
                  <dt>
                    <Trans>Take profit</Trans>
                  </dt>
                  <dd>
                    <Trans>Remove take profit</Trans>
                  </dd>
                </div>
              )}
              {(request.position_id ?? request.order_id) != null && (
                <div>
                  <dt>
                    <Trans>Broker ticket</Trans>
                  </dt>
                  <dd className="ltr">{String(request.position_id ?? request.order_id)}</dd>
                </div>
              )}
            </dl>
          </div>
        );
      })}
      {row.tolerance && (
        <dl className="oa-dl">
          <div>
            <dt>
              <Trans>Valid while the price stays within</Trans>
            </dt>
            <dd className="ltr">
              {row.reference_price
                ? `${row.reference_price} ± ${row.tolerance}`
                : `± ${row.tolerance}`}
            </dd>
          </div>
        </dl>
      )}
      {row.reason && (
        <div className="od-ev" data-trade-reason>
          <Icon name="chat" />
          <span>
            <b>
              <Trans>In the agent's words</Trans>:
            </b>{" "}
            <bdi>{row.reason}</bdi>
          </span>
        </div>
      )}
      {status === "pending" ? (
        <div className="mcard-actions">
          <button
            type="button"
            className="btn primary sm"
            disabled={busy}
            onClick={() => void decide(row.id, "approve")}
          >
            <Trans>Approve</Trans>
          </button>
          <button
            type="button"
            className="btn sm"
            disabled={busy}
            onClick={() => void decide(row.id, "reject")}
          >
            <Trans>Reject</Trans>
          </button>
        </div>
      ) : (
        <div
          className={`od-ev${tone === "plain" ? "" : ` ${tone}`}`}
          role="status"
          data-trade-status-tone={tone}
        >
          <Icon
            name={
              tone === "ok"
                ? "check"
                : tone === "wait"
                  ? "hourglass"
                  : tone === "warn"
                    ? "alert"
                    : "close"
            }
          />
          <span data-trade-status-text>{approvalStatusText(status, i18n.locale)}</span>
        </div>
      )}
      {/* A confirmed result is shown once: as its Execution Receipt (10.3). */}
      {row.results
        .filter((result) => result.status !== "confirmed")
        .map((result) => (
          <div
            key={result.operation_id}
            className={`od-ev ${result.status === "failed" ? "bad" : "warn"}`}
            data-trade-result={result.status}
          >
            <Icon name="alert" />
            <span>
              <span>{operationStatusLabel(result.status, result.details)}</span>
              {result.broker_id && (
                <>
                  {" · "}
                  {brokerTicketLabel(i18n.locale)} <b className="ltr">{result.broker_id}</b>
                </>
              )}
              {resultReason(result) && (
                <>
                  {" · "}
                  <span>{resultReason(result)}</span>
                </>
              )}
              {/* The broker's own prices, as it returned them and labelled; never its raw
                  codes or ids. */}
              {RECEIPT_FIELDS.filter(
                (key) => result.details?.[key] != null && result.details[key] !== "",
              ).map((key) => (
                <span key={key}>
                  {" · "}
                  {brokerPriceLabel(key, i18n.locale)}{" "}
                  <b className="ltr">{String(result.details[key])}</b>
                </span>
              ))}
              {/* The broker's own sentence, labelled as its words, after our reason. */}
              {result.details?.description != null && result.details.description !== "" && (
                <span data-trade-broker-words>
                  {" · "}
                  <b>{brokerWordsLabel(i18n.locale)}:</b>{" "}
                  <bdi>{String(result.details.description)}</bdi>
                </span>
              )}
            </span>
          </div>
        ))}
      {status === "expired" && onRenew && (
        <div className="mcard-actions">
          <button type="button" className="btn sm" onClick={() => onRenew(row)}>
            <Trans>New request</Trans>
          </button>
        </div>
      )}
    </div>
  );
}

const RECEIPT_FIELDS = ["price", "execution_price"] as const;

export function TradeApprovals({
  threadId,
  since,
  onPending,
}: {
  threadId: string;
  since?: number;
  onPending?: (pending: boolean) => void;
}) {
  const { rows, error, busy, decide, callRequests } = useTradeApprovals(
    threadId,
    since !== undefined,
  );
  useEffect(() => {
    onPending?.(rows.some((row) => row.status === "pending"));
  }, [onPending, rows]);
  return (
    <>
      {error != null && <p role="alert">{userError(error)}</p>}
      {rows
        .filter(
          (row) =>
            since === undefined ||
            row.status === "pending" ||
            Date.parse(row.created_at) >= since ||
            callRequests.has(row.id),
        )
        .map((row) => (
          <TradeApprovalCard key={row.id} row={row} busy={busy != null} decide={decide} />
        ))}
    </>
  );
}
