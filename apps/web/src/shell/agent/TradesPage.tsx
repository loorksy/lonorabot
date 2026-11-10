import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { financialBoundaryError } from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { useState } from "react";
import { useTicketAction } from "../../components/trading/useTicketAction";
import type { AccountSummary, Agent, Journal, Position, Resource } from "../../lib/api";
import { operationStatusLabel } from "../../lib/operation-status";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { SkPage, SkRows } from "../Skeleton";
import { NotFoundPage } from "../StatePage";
import { useSheets } from "../sheets/SheetHost";
import { ORDER_TONE, type OrderState, orderState } from "./order-state";
import { accountLabel, clockTime, useRead } from "./shared";
import "./agent.css";

const STATE_ICON: Record<OrderState, "check" | "close" | "minus" | "alert" | "hourglass"> = {
  requested: "hourglass",
  sent: "hourglass",
  accepted: "hourglass",
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

/* «الصفقات» (route trades): the agent's open positions with the owner's own «تعديل الوقف
   والهدف» and «إغلاق الصفقة» — the owner's direct order through POST /api/trading/execute,
   the single executor under the global brake (Q30) — then «سجل الأوامر» from the journal. */
export function TradesPage({ agentId }: { agentId: string }) {
  const data = useShellData();
  const agent = data.agents.find((row) => row.id === agentId);
  if (!agent)
    return data.agentsLoading ? (
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
      {orders.length ? (
        <div className="group">
          {orders.map((entry) => {
            const state = orderState(entry);
            const request = entry.request;
            const limit = String(request.action ?? "").includes("_limit");
            const price = entry.result.price ?? request.price;
            return (
              // The chat's order sheet (chat.messages.order-line) arrives with the journal's
              // conversation anchors (WP-F); until then a row shows its state only.
              <div
                className="row od-row"
                key={entry.operation_id}
                data-operation-id={entry.operation_id}
              >
                <span className="row-icon">
                  <Icon name={String(request.action).startsWith("sell") ? "trendDown" : "trend"} />
                </span>
                <span className="body">
                  <strong>
                    {sideName(request.action)}{" "}
                    {request.volume != null && (
                      <span className="ltr">{String(request.volume)}</span>
                    )}{" "}
                    <bdi>{String(request.symbol ?? "")}</bdi>
                  </strong>
                  <small>
                    <span className="ltr">{clockTime(entry.submitted_at ?? entry.updated_at)}</span>
                    {" · "}
                    {limit ? t`Limit order` : t`At market price`}
                    {price != null && state !== "uncertain" && (
                      <>
                        {" · "}
                        <span className="ltr">{String(price)}</span>
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
  const outcome = close.outcome(position.id) ?? modify.outcome(position.id);
  const error = close.error ?? modify.error;
  const openModify = () =>
    sheets.open({
      id: "trade-edit",
      title: t`Edit stop and target`,
      body: (
        <ModifyForm
          position={position}
          onSubmit={(stop, target) => {
            sheets.close();
            void modify.run(position.id, {
              action: "modify_position",
              symbol: position.symbol,
              position_id: position.id,
              ...(stop ? { stop_loss: stop } : {}),
              ...(target ? { take_profit: target } : {}),
            });
          }}
        />
      ),
    });
  const openClose = () =>
    sheets.open({
      id: "trade-close",
      title: t`Close the trade`,
      body: (
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
        </>
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
      <div className="group">
        <Value label={t`Volume`} value={position.volume} />
        <Value label={t`Entry price`} value={position.open_price} />
        <Value label={t`Stop loss`} value={position.stop_loss} />
        <Value label={t`Take profit`} value={position.take_profit} />
      </div>
      <div className="actions">
        <button
          type="button"
          className="btn outline"
          disabled={modify.busy(position.id) || close.busy(position.id)}
          onClick={openModify}
        >
          <Trans>Edit stop and target</Trans>
        </button>
        <button
          type="button"
          className="btn danger"
          disabled={close.busy(position.id) || modify.busy(position.id)}
          onClick={openClose}
        >
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
