import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentLiveState, TradingReadiness } from "@lonora/contracts";
import {
  agentStatusLine,
  orderLineAction,
  tradingReadinessLine,
  uncertainLine,
} from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { useCallback, useEffect, useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { useAgentLiveState } from "../../lib/agent-live-state";
import type { Agent, Resource } from "../../lib/api";
import { api } from "../../lib/api";
import { brokerIdentityLabel } from "../../lib/broker-identity";
import { readConnections } from "../../lib/trading";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { useNavigation } from "../../shell/navigation";
import { useSheets } from "../../shell/sheets/SheetHost";
import { useToast } from "../../shell/Toast";
import { useChatPrefs } from "../prefs";
import { useWatchesSheet } from "./WatchesSheet";

/* The agent's status (Q35: a per-device preference, off by default) and the trading safety of
   a trading agent (reference agentStatus/safetyCap/agentSheet, Desktop-37 8060-8176). The
   capsule appears only when something is wrong; nothing is pinned in a normal state. */

type StatusKind =
  | "analyzing"
  | "searching"
  | "watching"
  | "broker"
  | "you"
  | "paused"
  | "uncertain"
  | "idle";
const STATUS_ICON: Record<StatusKind, IconName> = {
  analyzing: "sparkle",
  searching: "search",
  watching: "radar",
  broker: "hourglass",
  you: "user",
  paused: "pause",
  uncertain: "alert",
  idle: "check",
};
/** The current work's detail: the owner's own words, or the operation worded here. */
function workDetail(work: AgentLiveState["current_work"]) {
  if (!work) return "";
  if (work.operation) {
    const action = orderLineAction(work.operation, i18n.locale);
    const what = `${action.label}${work.operation.volume ? ` ${work.operation.volume}` : ""} ${work.operation.symbol}`;
    return work.card === "trade_approval" ? t`Approval request · ${what}` : what;
  }
  if (work.card === "owner_action") return t`A decision is needed`;
  return work.text;
}
export function statusKind(state: AgentLiveState | null | undefined): StatusKind {
  if (!state) return "idle";
  const work = state.current_work ?? null;
  if (state.state === "paused") return "paused";
  if (state.phase === "uncertain") return "uncertain";
  if (state.pending_card_id || work?.kind === "waiting_owner" || state.pending_approval_count > 0)
    return "you";
  if (state.phase === "awaiting_broker" || work?.kind === "broker") return "broker";
  if (work?.kind === "analysing") return "analyzing";
  if (work?.kind === "searching") return "searching";
  if (state.phase === "monitoring" && (state.watches ?? []).length) return "watching";
  return "idle";
}

/** The header's status line: a button under the name, opening the AgentSheet. */
export function StatusLine({ agent, onOpen }: { agent: Agent; onOpen: () => void }) {
  const { state } = useAgentLiveState(agent.id);
  const kind = statusKind(state);
  const text = state ? agentStatusLine(state, i18n.locale) : t`Active`;
  return (
    <button
      type="button"
      className={`presence st-line st-${kind}`}
      data-testid="agent-status-line"
      aria-haspopup="dialog"
      aria-label={t`Status: ${text}`}
      onClick={onOpen}
    >
      {kind !== "idle" && (
        <span className="sl-ic">
          <Icon name={STATUS_ICON[kind]} />
        </span>
      )}
      <span className="st-text">{text}</span>
    </button>
  );
}

/** With the preference on, the avatar wraps in .st-av.st-<state> (rings and badges). */
export function StatusAvatar({ agent, children }: { agent: Agent; children: React.ReactNode }) {
  const prefs = useChatPrefs();
  const { state } = useAgentLiveState(agent.id);
  if (!prefs.agentStatus) return <>{children}</>;
  const kind = statusKind(state);
  return (
    <span className={`st-av st-${kind}`}>
      {children}
      {(kind === "uncertain" || kind === "you") && (
        <i className="st-badge" aria-hidden="true">
          {kind === "you" ? "" : "!"}
        </i>
      )}
    </span>
  );
}

/** The alert capsule under the header of a trading agent's chat: abnormal states only. */
export function SafetyCapsule({ agent, onOpen }: { agent: Agent; onOpen: () => void }) {
  const { state } = useAgentLiveState(agent.id);
  const readiness = state?.trading_readiness;
  if (!readiness) return null;
  const count = readiness.unresolved_count;
  if (!count) return null;
  const text = uncertainLine(count, i18n.locale);
  return (
    <div className="safety-row">
      <button
        type="button"
        className="safety-cap tone-warn"
        aria-haspopup="dialog"
        aria-label={text}
        data-testid="safety-capsule"
        data-readiness={readiness.state}
        onClick={onOpen}
      >
        <Icon name="alert" />
        <span className="sc-text">{text}</span>
        <Icon name="down" />
      </button>
    </div>
  );
}

/** With more than one account every item names its account (as the old safety pill did). */
function useAccountName(readiness: TradingReadiness | null) {
  const [accounts, setAccounts] = useState<Resource[]>([]);
  const trading = readiness !== null;
  useEffect(() => {
    if (!trading) return;
    let live = true;
    void readConnections()
      .then((rows) => {
        if (live) setAccounts(rows);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [trading]);
  const several = accounts.length > 1;
  return (id: string) => {
    if (!several) return null;
    const index = accounts.findIndex((row) => row.id === id);
    return index < 0 ? null : brokerIdentityLabel(accounts[index], index);
  };
}

function AgentSheetBody({
  agent,
  onJump,
  go,
  close,
}: {
  agent: Agent;
  onJump: (id: string) => void;
  go: (path: string) => void;
  close: () => void;
}) {
  const { state } = useAgentLiveState(agent.id);
  const prefs = useChatPrefs();
  const { refresh } = useClient();
  const toast = useToast();
  const watches = useWatchesSheet();
  const [busy, setBusy] = useState(false);
  const readiness = state?.trading_readiness ?? null;
  const accountName = useAccountName(readiness);
  const kind = statusKind(state);
  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try {
      await action();
      refresh();
      toast(done, { type: "success" });
    } catch (error) {
      toast(userError(error), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  const work = state?.current_work;
  const pendingId = state?.pending_card_id;
  return (
    <>
      <div className="sf-head" data-testid="agent-live-state" data-state={state?.state}>
        <AgentAvatar agent={agent} />
        <div>
          <strong>{agent.name}</strong>
          <small data-testid="agent-mode-line">
            {readiness
              ? tradingReadinessLine(readiness, i18n.locale, new Date(), accountName)
              : state
                ? agentStatusLine(state, i18n.locale)
                : ""}
          </small>
        </div>
      </div>
      {prefs.agentStatus && state && (
        <>
          <h3>
            <Trans>Current work</Trans>
          </h3>
          <div className="group">
            <div className="row">
              <span className="row-icon">
                <Icon name={STATUS_ICON[kind]} />
              </span>
              <span className="body">
                <strong>{agentStatusLine(state, i18n.locale)}</strong>
                {workDetail(work) && <small dir="auto">{workDetail(work)}</small>}
              </span>
            </div>
            {(state.watches ?? []).length > 0 && (
              <button
                type="button"
                className="row ev-row"
                onClick={() => {
                  close();
                  watches(agent);
                }}
              >
                <span className="row-icon">
                  <Icon name="radar" />
                </span>
                <span className="body">
                  <strong>
                    <Trans>Watches</Trans>
                  </strong>
                  <small>{t`${state.watch_count} active`}</small>
                </span>
                <span className="chevron">
                  <Icon name="chev" />
                </span>
              </button>
            )}
          </div>
          {pendingId && (
            <button
              type="button"
              className="btn full primary"
              onClick={() => {
                close();
                onJump(pendingId);
              }}
            >
              <Trans>Show the request</Trans>
            </button>
          )}
        </>
      )}
      {(state?.tasks ?? []).length > 0 && (
        <>
          <h3>
            <Trans>Tasks</Trans>
          </h3>
          <div className="group">
            {(state?.tasks ?? []).map((task) => (
              <div key={task.id} className="row" data-task-id={task.id}>
                <Icon name="task" />
                <span className="body">
                  <strong dir="auto">{task.title}</strong>
                  <small>
                    {task.retry_at
                      ? `${t`Retry scheduled`} · ${new Date(task.retry_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`
                      : task.recovery === "reconcile"
                        ? t`Waiting for reconciliation`
                        : task.status === "failed"
                          ? t`Task needs review`
                          : agentStatusLine(state as AgentLiveState, i18n.locale)}
                  </small>
                </span>
                {(["resume", "pause", "cancel"] as const).map(
                  (action) =>
                    task[`can_${action}`] && (
                      <button
                        key={action}
                        type="button"
                        className={`btn sm${action === "resume" ? " primary" : ""}`}
                        disabled={busy}
                        onClick={() =>
                          void run(
                            () =>
                              api.post("/tasks/control", {
                                task_id: task.id,
                                action,
                                expected_version: task.version,
                              }),
                            action === "resume"
                              ? t`Task resumed`
                              : action === "pause"
                                ? t`Task paused`
                                : t`Task cancelled`,
                          )
                        }
                      >
                        {action === "pause"
                          ? t`Pause`
                          : action === "resume"
                            ? t`Resume`
                            : t`Cancel`}
                      </button>
                    ),
                )}
              </div>
            ))}
          </div>
        </>
      )}
      {readiness && (
        <>
          {readiness.unresolved_operations.length > 0 && (
            <>
              <h3>
                <Trans>Trading</Trans>
              </h3>
              <div className="group">
                {readiness.unresolved_operations.map((op) => (
                  <div key={op.operation_id} className="row">
                    <Icon name="alert" />
                    <span className="body">
                      <strong dir="auto">
                        <bdi>
                          {op.action} {op.symbol}
                        </bdi>
                      </strong>
                      <small dir="auto">
                        {accountName(op.account_id) && <>{accountName(op.account_id)} · </>}
                        <Trans>Unconfirmed operation · not confirmed by the broker</Trans>
                      </small>
                    </span>
                    {op.resolve_card && (
                      <button
                        type="button"
                        className="btn sm"
                        data-resolve-card={op.resolve_card.id}
                        onClick={() => {
                          close();
                          if (op.resolve_card) openCard(op.resolve_card, go);
                        }}
                      >
                        <Trans>Resolve</Trans>
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
          <p className="note">
            <Trans>Closing and tightening the stop loss are always allowed.</Trans>
          </p>
        </>
      )}
    </>
  );
}

/** «حسم»: the open chat jumps to the card when it holds it; otherwise the card's own
    conversation (another agent's chat, a group, Lonora's) opens on it. */
function openCard(card: ResolveCard, go: (path: string) => void) {
  const held = !window.dispatchEvent(
    new CustomEvent("lonora:jump", {
      detail: { id: card.id, thread_id: card.thread_id },
      cancelable: true,
    }),
  );
  if (held) return;
  const path = card.group_id
    ? `/app/g/${encodeURIComponent(card.group_id)}`
    : card.agent_id
      ? `/app/${encodeURIComponent(card.agent_id)}`
      : null;
  if (!path) return;
  const query = new URLSearchParams({ card: card.id });
  if (card.thread_id && !card.group_id) query.set("thread", card.thread_id);
  if (card.timeline_seq) query.set("around", String(card.timeline_seq));
  go(`${path}?${query}`);
}
type ResolveCard = NonNullable<TradingReadiness["unresolved_operations"][number]["resolve_card"]>;

export function useAgentSheet(onJump: (id: string) => void) {
  const sheets = useSheets();
  const nav = useNavigation();
  return useCallback(
    (agent: Agent, trading: boolean, statusOn: boolean) => {
      const title = trading
        ? statusOn
          ? t`Status and safety`
          : t`Trading and safety`
        : t`Agent status`;
      sheets.open({
        id: "safety",
        title,
        label: title,
        body: (
          <AgentSheetBody agent={agent} onJump={onJump} go={nav.go} close={() => sheets.close()} />
        ),
      });
    },
    [sheets, onJump, nav.go],
  );
}
