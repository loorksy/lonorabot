import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { financialBoundaryError } from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { useState } from "react";
import {
  modifyTicket,
  type TicketOutcome,
  useTicketAction,
} from "../../components/trading/useTicketAction";
import type { AccountSummary, Agent, Journal, Position, Resource } from "../../lib/api";
import { operationStatusLabel } from "../../lib/operation-status";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { SkPage, SkRows } from "../Skeleton";
import { NotFoundPage } from "../StatePage";
import { useSheets } from "../sheets/SheetHost";
import { ORDER_TONE, type OrderState, orderFill, orderState } from "./order-state";
import { scoped } from "./scope";
import { accountLabel, clockTime, usePageAgent, useRead } from "./shared";
import "./agent.css";

const STATE_ICON: Record<OrderState, "check" | "close" | "minus" | "alert" | "hourglass"> = {
  requested: "hourglass",
  sent: "hourglass",
  accepted: "hourglass",
  partial: "check",
  filled: "check",
  rejected: "close",
  cancelled: "minus",
  uncertain: "alert",
};

function stateName(state: OrderState) {
  switch (state) {
    case "requested":
      return t({ message: "Requested", context: "order state" });
    case "sent":
      return t({ message: "Sent", context: "order state" });
    case "accepted":
      return t({ message: "Accepted by the broker", context: "order state" });
    case "partial":
      return t({ message: "Partly filled", context: "order state" });
    case "filled":
      return t({ message: "Filled", context: "order state" });
    case "rejected":
      return t({ message: "Rejected", context: "order state" });
    case "cancelled":
      return t({ message: "Cancelled", context: "order state" });
    default:
      return t({ message: "Unconfirmed", context: "order state" });
  }
}

const sideName = (side: unknown) =>
  String(side).startsWith("sell")
    ? t({ message: "Sell", context: "side" })
    : t({ message: "Buy", context: "side" });

/** Each executor action under the reference's words: what was asked, and how. */
function orderWording(action: string): { title: string; kind: string } {
  const side = sideName(action);
  switch (action) {
    case "buy":
    case "sell":
      return { title: side, kind: t`At market price` };
    case "buy_limit":
    case "sell_limit":
      return { title: side, kind: t`Limit order` };
    case "buy_stop":
    case "sell_stop":
      return { title: side, kind: t`Stop order` };
    case "close_position":
      return { title: t`Close the trade`, kind: t`At market price` };
    case "modify_position":
      return { title: t`Edit stop and target`, kind: t`Protection change` };
    case "cancel_order":
      return { title: t`Cancel order`, kind: t`Pending order` };
    case "modify_order":
      return { title: t`Edit order`, kind: t`Pending order` };
    default:
      return { title: action, kind: "" };
  }
}

/* «الصفقات» (route trades): the agent's open positions with the owner's own «تعديل الوقف
   والهدف» and «إغلاق الصفقة» — the owner's direct order through POST /api/trading/execute,
   the single executor (Q30) — then «سجل الأوامر» from the journal. */
export function TradesPage({ agentId }: { agentId: string }) {
  const data = useShellData();
  const { agent, missing } = usePageAgent(agentId, data.agents, data.agentsLoading);
  if (!agent)
    return !missing ? (
      <SkPage>
        <SkRows count={4} />
      </SkPage>
    ) : (
      <NotFoundPage />
    );
  return <Trades key={agent.id} agent={agent} />;
}

function Trades({ agent }: { agent: Agent }) {
  const connections = useRead<Resource[]>("/trading/connections");
  const accountId = agent.trading_account_id ?? "";
  const account = useRead<AccountSummary>(
    accountId ? `/trading/accounts/${encodeURIComponent(accountId)}` : null,
  );
  const journal = useRead<Journal[]>(
    accountId ? `/trading/journal?account_id=${encodeURIComponent(accountId)}` : null,
  );
  if (!accountId)
    return (
      <div className="empty">
        <Icon name="folder" />
        <div>
          {connections.value?.length
            ? t`No trading account was chosen for this agent.`
            : t`Link a trading account from Settings first.`}
        </div>
      </div>
    );
  const reload = () => {
    account.reload();
    journal.reload();
  };
  const positions = (account.value?.positions ?? []).filter(
    (row) => !agent.trading_symbol || row.symbol === agent.trading_symbol,
  );
  const orders = (journal.value ?? [])
    .filter((row) => row.agent_id === agent.id)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return (
    <>
      {account.error != null ? (
        <p role="alert">{userError(account.error)}</p>
      ) : !account.value ? (
        <SkPage>
          <SkRows count={2} />
        </SkPage>
      ) : positions.length ? (
        positions.map((position) => (
          <PositionCard
            key={position.id}
            accountId={accountId}
            accountName={accountLabel(connections.value ?? [], accountId)}
            position={position}
            journal={journal.value}
            onChange={reload}
          />
        ))
      ) : (
        <div className="empty">
          <Icon name="folder" />
          <div>
            <Trans>No open trade.</Trans>
          </div>
        </div>
      )}
      <h3>
        <Trans>Order log</Trans>
      </h3>
      {journal.error != null ? (
        <p role="alert">{userError(journal.error)}</p>
      ) : !journal.value ? (
        <SkPage>
          <SkRows count={3} />
        </SkPage>
      ) : orders.length ? (
        <div className="group">
          {orders.map((entry) => {
            const state = orderState(entry);
            const request = entry.request;
            const action = String(request.action ?? "");
            const wording = orderWording(action);
            const fill = orderFill(entry);
            // A price only with the broker's evidence (a fill), never the asked one.
            const price = fill.price;
            const asked = request.volume != null ? String(request.volume) : null;
            return (
              // The chat's order sheet (chat.messages.order-line) arrives with the journal's
              // conversation anchors (WP-F); until then a row shows its state only.
              <div
                className="row od-row"
                key={entry.operation_id}
                data-operation-id={entry.operation_id}
                data-order-state={state}
              >
                <span className="row-icon">
                  <Icon name={action.startsWith("sell") ? "trendDown" : "trend"} />
                </span>
                <span className="body">
                  <strong>
                    {wording.title}{" "}
                    {state === "partial" ? (
                      // The executed size when the broker gave it; otherwise no number.
                      fill.volume && asked ? (
                        <span className="ltr">{`${fill.volume} / ${asked}`}</span>
                      ) : null
                    ) : (
                      asked && <span className="ltr">{asked}</span>
                    )}{" "}
                    <bdi>{String(request.symbol ?? "")}</bdi>
                  </strong>
                  <small>
                    <span className="ltr">{clockTime(entry.submitted_at ?? entry.updated_at)}</span>
                    {wording.kind && <> · {wording.kind}</>}
                    {price && state !== "uncertain" && (
                      <>
                        {" · "}
                        <span className="ltr">{price}</span>
                      </>
                    )}
                  </small>
                </span>
                <span className={`od-st t-${ORDER_TONE[state]}`}>
                  <Icon name={STATE_ICON[state]} />
                  <span>{stateName(state)}</span>
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty">
          <Icon name="folder" />
          <div>
            <Trans>No orders yet.</Trans>
          </div>
        </div>
      )}
      <p className="note">
        <Trans>«Filled» shows only with the broker's evidence or your confirmation.</Trans>
      </p>
    </>
  );
}

function Value({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="row">
      <span className="body">{label}</span>
      <span className="value ltr">{value ?? "—"}</span>
    </div>
  );
}

/** When the owner acted: set at reservation and again at the send, never by a recheck. */
const sentAt = (entry: Journal) => entry.submitted_at ?? entry.updated_at;

function PositionCard({
  accountId,
  accountName,
  position,
  journal,
  onChange,
}: {
  accountId: string;
  accountName: string;
  position: Position;
  journal: Journal[] | undefined;
  onChange: () => void;
}) {
  const sheets = useSheets();
  const close = useTicketAction("close_position", accountId, journal, onChange);
  const modify = useTicketAction("modify_position", accountId, journal, onChange);
  // The last thing the owner did is what the card reports: an old close never masks a
  // later modify, and each modify body has its own operation.
  const [last, setLast] = useState<{ action: "close" | "modify"; ticket: string } | null>(null);
  // After a reload nothing was done in this session: the journal's latest operation on this
  // position (the owner's own rows included) is what the card reports, unsettled or not.
  const latest = (journal ?? [])
    .filter(
      (entry) =>
        String(entry.request.position_id ?? "") === position.id &&
        ["modify_position", "close_position"].includes(String(entry.request.action)),
    )
    // When the owner acted (submitted_at), never updated_at: verification rechecks bump an
    // older pending row's updated_at every 30 s.
    .sort((a, b) => sentAt(b).localeCompare(sentAt(a)))[0];
  const restored: TicketOutcome | null = latest
    ? {
        status: latest.status,
        details: latest.result.details,
        code: typeof latest.result.code === "string" ? latest.result.code : null,
      }
    : null;
  const outcome = last
    ? last.action === "modify"
      ? modify.outcome(last.ticket)
      : close.outcome(position.id)
    : restored;
  const error = last?.action === "modify" ? modify.error : last ? close.error : undefined;
  const busy = close.busy(position.id) || (last ? modify.busy(last.ticket) : false);
  const openModify = () =>
    sheets.open({
      id: "trade-edit",
      title: t`Edit stop and target`,
      body: scoped(
        <ModifyForm
          position={position}
          onSubmit={(stop, target) => {
            sheets.close();
            // An emptied field is an explicit clear: the server decides (clearing a stop
            // widens risk and may be refused), and the card shows its real answer.
            const request = {
              action: "modify_position",
              symbol: position.symbol,
              position_id: position.id,
              ...(stop ? { stop_loss: stop } : position.stop_loss ? { clear_stop_loss: true } : {}),
              ...(target
                ? { take_profit: target }
                : position.take_profit
                  ? { clear_take_profit: true }
                  : {}),
            };
            const ticket = modifyTicket(request);
            setLast({ action: "modify", ticket });
            void modify.run(ticket, request);
          }}
        />,
      ),
    });
  const openClose = () =>
    sheets.open({
      id: "trade-close",
      title: t`Close the trade`,
      body: scoped(
        <>
          <p>
            <Trans>
              The trade on <bdi>{position.symbol}</bdi> is closed at the market price. This is your
              own order, sent through the executor.
            </Trans>
          </p>
          <div className="actions">
            <button type="button" className="btn outline" onClick={() => sheets.close()}>
              <Trans>Cancel</Trans>
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={() => {
                sheets.close();
                setLast({ action: "close", ticket: position.id });
                void close.run(position.id, {
                  action: "close_position",
                  symbol: position.symbol,
                  position_id: position.id,
                });
              }}
            >
              <Trans>Close the trade</Trans>
            </button>
          </div>
        </>,
      ),
    });
  return (
    <section data-position-id={position.id}>
      <p className="muted">
        <bdi>{accountName}</bdi>
      </p>
      <h2>
        <span className="ltr">{position.symbol}</span>{" "}
        <span className="badge">{sideName(position.side)}</span>
      </h2>
      <Value label={t`Volume`} value={position.volume} />
      <Value label={t`Entry price`} value={position.open_price} />
      <Value label={t`Stop loss`} value={position.stop_loss} />
      <Value label={t`Take profit`} value={position.take_profit} />
      <div className="actions">
        <button type="button" className="btn outline" disabled={busy} onClick={openModify}>
          <Trans>Edit stop and target</Trans>
        </button>
        <button type="button" className="btn danger" disabled={busy} onClick={openClose}>
          {close.held(position.id) ? (
            <Trans>Check close result</Trans>
          ) : (
            <Trans>Close the trade</Trans>
          )}
        </button>
      </div>
      {outcome && (
        <p role="status" className="note" data-operation-status={outcome.status}>
          {operationStatusLabel(outcome.status, outcome.details)}
          {financialBoundaryError(outcome.code, i18n.locale) && (
            <> {financialBoundaryError(outcome.code, i18n.locale)}</>
          )}
        </p>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
    </section>
  );
}

function ModifyForm({
  position,
  onSubmit,
}: {
  position: Position;
  onSubmit: (stop: string, target: string) => void;
}) {
  const [stop, setStop] = useState(position.stop_loss ?? "");
  const [target, setTarget] = useState(position.take_profit ?? "");
  const changed = stop !== (position.stop_loss ?? "") || target !== (position.take_profit ?? "");
  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (changed) onSubmit(stop.trim(), target.trim());
      }}
    >
      <label className="field">
        <span>
          <Trans>Stop loss</Trans>
        </span>
        <input
          inputMode="decimal"
          dir="ltr"
          value={stop}
          onChange={(event) => setStop(event.target.value)}
        />
      </label>
      <label className="field">
        <span>
          <Trans>Take profit</Trans>
        </span>
        <input
          inputMode="decimal"
          dir="ltr"
          value={target}
          onChange={(event) => setTarget(event.target.value)}
        />
      </label>
      <div className="actions">
        <button type="submit" className="btn primary" disabled={!changed}>
          <Trans>Save</Trans>
        </button>
      </div>
    </form>
  );
}
