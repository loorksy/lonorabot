import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type {
  AgentLiveState,
  MoneyLimitName,
  MoneyLimits,
  TradingReadiness,
} from "@lonora/contracts";
import {
  agentStatusLine,
  isolate,
  moneyLimitLabel,
  orderLineAction,
  pauseClassLabel,
  readinessTime,
  tradingReadinessLine,
  tradingSafetyText,
  uncertainLine,
} from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { useCallback, useEffect, useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { useAgentLiveState } from "../../lib/agent-live-state";
import type { Agent, Resource } from "../../lib/api";
import { api } from "../../lib/api";
import { brokerIdentityLabel } from "../../lib/broker-identity";
import { liftRestriction, readConnections, resumeTrading, stopNewTrading } from "../../lib/trading";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { useShellData } from "../../shell/data";
import { useNavigation } from "../../shell/navigation";
import { useSheets } from "../../shell/sheets/SheetHost";
import { useToast } from "../../shell/Toast";
import { useChatPrefs } from "../prefs";
import { useLimitsSheet } from "./LimitsSheet";
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

function restrictionText(r: TradingReadiness["restrictions"][number]) {
  const until = r.valid_until ? readinessTime(r.valid_until, i18n.locale) : null;
  // Only a «no new entries» pause is «الصفقات الجديدة معلّقة»; the others name their class.
  if (r.action_class !== "no_new_entries") {
    const what = pauseClassLabel(r.action_class, i18n.locale);
    return until ? t`Restricted: ${what} until ${until}` : t`Restricted: ${what}`;
  }
  return until ? t`New trades are paused until ${until}` : t`New trades are paused`;
}

/** The alert capsule under the header of a trading agent's chat: abnormal states only. */
export function SafetyCapsule({ agent, onOpen }: { agent: Agent; onOpen: () => void }) {
  const { state } = useAgentLiveState(agent.id);
  const readiness = state?.trading_readiness;
  if (!readiness) return null;
  const count = readiness.unresolved_count;
  const full = count ? uncertainLine(count, i18n.locale) : "";
  const flag = count > 1 ? t`${count} unconfirmed` : full;
  const restriction = readiness.restrictions.find((r) => r.state === "active");
  let tone: "off" | "warn";
  let icon: IconName;
  let text: string;
  let showFlag = true;
  if (!readiness.exits_allowed) {
    // A freeze blocks exits too: the capsule says so in the server's own words.
    tone = "off";
    icon = "lock";
    text = tradingReadinessLine(readiness, i18n.locale);
  } else if (readiness.global_trading.state === "stopped") {
    tone = "off";
    icon = "power";
    text = t`Trading is stopped`;
  } else if (restriction) {
    tone = "warn";
    icon = "pause";
    text = restrictionText(restriction);
  } else if (count) {
    tone = "warn";
    icon = "alert";
    text = full;
    showFlag = false;
  } else return null;
  return (
    <div className="safety-row">
      <button
        type="button"
        className={`safety-cap tone-${tone}`}
        aria-haspopup="dialog"
        aria-label={`${text}${showFlag && full ? `، ${full}` : ""}`}
        data-testid="safety-capsule"
        data-readiness={readiness.state}
        onClick={onOpen}
      >
        <Icon name={icon} />
        <span className="sc-text">{text}</span>
        {showFlag && flag && (
          <span className="sc-flag">
            <Icon name="alert" />
            <span>{flag}</span>
          </span>
        )}
        <Icon name="down" />
      </button>
    </div>
  );
}

/** With more than one account every item names its account (as the old safety pill did). */
function useAccountName(readiness: TradingReadiness | null) {
  const [accounts, setAccounts] = useState<Resource[]>([]);
  const ids = new Set(
    readiness
      ? [
          ...readiness.money_limits.map((item) => item.account_id),
          ...readiness.grants.map((item) => item.account_id),
          ...readiness.restrictions.map((item) => item.account_id),
          ...readiness.unresolved_operations.map((item) => item.account_id),
        ]
      : [],
  );
  const several = ids.size > 1;
  useEffect(() => {
    if (!several) return;
    let live = true;
    void readConnections()
      .then((rows) => {
        if (live) setAccounts(rows);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [several]);
  return (id: string) => {
    if (!several) return null;
    const index = accounts.findIndex((row) => row.id === id);
    return index < 0 ? null : brokerIdentityLabel(accounts[index], index);
  };
}

/* The owner's money limits, every cap that is set (a percentage of equity and an absolute
   amount can both apply): «دون حد» only when neither is set. */
const LIMIT_GROUPS: Array<[() => string, MoneyLimitName[]]> = [
  [() => t`Daily loss limit`, ["max_daily_loss"]],
  [() => t`Trade risk limit`, ["max_trade_risk_equity_percent", "max_trade_risk"]],
  [() => t`Open risk limit`, ["max_open_risk_equity_percent", "max_open_risk"]],
  [() => t`Minimum free margin`, ["min_free_margin"]],
];

export function LimitRows({ limits }: { limits: MoneyLimits }) {
  const amount = (key: MoneyLimitName) =>
    `${limits.limits[key]}${key.endsWith("percent") ? "%" : limits.currency ? ` ${limits.currency}` : ""}`;
  if (!limits.configured)
    // The server enforces none: the same words as the readiness line.
    return (
      <div className="row" data-money-limit="none">
        <span className="body">{tradingSafetyText(i18n.locale).noMoneyLimit}</span>
      </div>
    );
  return (
    <>
      {LIMIT_GROUPS.map(([label, keys]) => {
        const set = keys.filter((key) => limits.limits[key] != null);
        return set.length ? (
          set.map((key) => (
            <div key={key} className="row" data-money-limit={key}>
              <span className="body">
                {set.length > 1 ? moneyLimitLabel(key, i18n.locale) : label()}
              </span>
              <span className="value ltr">{amount(key)}</span>
            </div>
          ))
        ) : (
          <div key={keys[0]} className="row" data-money-limit={keys[0]} data-unset="">
            <span className="body">{label()}</span>
            <span className="value">{t`No limit`}</span>
          </div>
        );
      })}
    </>
  );
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
  const limits_ = useLimitsSheet();
  const watches = useWatchesSheet();
  const [busy, setBusy] = useState(false);
  const readiness = state?.trading_readiness ?? null;
  const { agents } = useShellData();
  const accountName = useAccountName(readiness);
  const agentName = (id: string | null) => {
    const name = agents.find((row) => row.id === id)?.name;
    return name ? `${t`Set by the agent`} · ${isolate(name)}` : t`Set by the agent`;
  };
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
  const ownPause = readiness?.restrictions.find(
    (r) => r.applies_to === "this_agent" && r.source === "owner_ui",
  );
  const systemPauses = readiness?.restrictions.filter((r) => r !== ownPause) ?? [];
  const account = readiness?.money_limits[0];
  const work = state?.current_work;
  const pendingId = state?.pending_card_id;
  const stopped = readiness?.global_trading.state === "stopped";
  const exits = readiness?.exits_allowed !== false;
  const closing = exits ? ` · ${t`closing allowed`}` : "";
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
          <h3>
            <Trans>Trading</Trans>
          </h3>
          <div className="group">
            <div className="row sf-switch">
              <Icon name="power" />
              <span className="body">
                <strong>
                  <Trans>Trading</Trans>
                </strong>
                <small>
                  {stopped
                    ? t`Stopped · no new orders are sent`
                    : exits
                      ? t`On · closing is always allowed`
                      : t`On`}
                </small>
              </span>
              <button
                type="button"
                className="switch"
                role="switch"
                aria-checked={!stopped}
                aria-label={t`Trading`}
                disabled={busy}
                onClick={() =>
                  void run(
                    stopped ? resumeTrading : stopNewTrading,
                    stopped
                      ? t`Trading resumed`
                      : exits
                        ? t`Trading stopped · closing is still allowed`
                        : t`Trading stopped`,
                  )
                }
              />
            </div>
            <div className="row">
              <Icon name="pause" />
              <span className="body">
                <strong>
                  <Trans>New trades</Trans>
                </strong>
                <small>{ownPause ? `${restrictionText(ownPause)}${closing}` : t`Allowed`}</small>
              </span>
              {ownPause ? (
                <button
                  type="button"
                  className="btn sm"
                  disabled={busy}
                  onClick={() =>
                    void run(() => liftRestriction(ownPause.id), t`New trades resumed`)
                  }
                >
                  <Trans>Resume</Trans>
                </button>
              ) : (
                account && (
                  <button
                    type="button"
                    className="btn sm outline"
                    disabled={busy}
                    onClick={() => {
                      const end = new Date();
                      end.setHours(23, 59, 0, 0);
                      void run(
                        () =>
                          api.post("/trading/restrictions", {
                            account_id: account.account_id,
                            agent_id: agent.id,
                            action_class: "no_new_entries",
                            valid_until: end.toISOString(),
                            reason: "owner_pause",
                          }),
                        t`New trades paused until 23:59`,
                      );
                    }}
                  >
                    {t({ message: "Pause", context: "new trades pause" })}
                  </button>
                )
              )}
            </div>
            {systemPauses.map((r) => (
              <div
                key={r.id}
                className="row"
                data-restriction={r.id}
                data-closing={r.action_class === "all_mutations" ? "frozen" : "allowed"}
              >
                <Icon name="lock" />
                <span className="body">
                  <strong>{restrictionText(r)}</strong>
                  <small dir="auto">
                    {accountName(r.account_id) && <>{accountName(r.account_id)} · </>}
                    {r.symbol && (
                      <>
                        <bdi className="ltr">{r.symbol}</bdi> ·{" "}
                      </>
                    )}
                    {r.source === "owner_ui" || r.source === "owner_message"
                      ? t`Set by you`
                      : agentName(r.created_by_agent_id)}{" "}
                    · {/* Each row's own class: a freeze elsewhere never colours this pause. */}
                    {r.action_class === "all_mutations"
                      ? t`closing is frozen too`
                      : t`this one does not block closing`}
                  </small>
                </span>
                <button
                  type="button"
                  className="btn sm"
                  data-lift-restriction={r.id}
                  disabled={busy}
                  onClick={() =>
                    void run(() => liftRestriction(r.id), t`The restriction was lifted`)
                  }
                >
                  <Trans>Lift</Trans>
                </button>
              </div>
            ))}
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
          {(readiness.money_limits ?? []).map((limits) => (
            <section key={limits.account_id} data-account-limits={limits.account_id}>
              <h3>
                <Trans>Account limits</Trans>
                {accountName(limits.account_id) && <> · {accountName(limits.account_id)}</>}
              </h3>
              <div className="group">
                <LimitRows limits={limits} />
              </div>
              <button
                type="button"
                className="btn full outline"
                onClick={() => {
                  close();
                  limits_(limits.account_id);
                }}
              >
                <Trans>Edit the limits</Trans>
              </button>
            </section>
          ))}
          {exits ? (
            <p className="note">
              <Trans>
                Closing and tightening the stop loss are always allowed, even when trading is
                stopped.
              </Trans>
            </p>
          ) : (
            <p className="oa-warn" role="alert">
              <Icon name="lock" />
              <span>{tradingSafetyText(i18n.locale).exitsFrozen}</span>
            </p>
          )}
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
