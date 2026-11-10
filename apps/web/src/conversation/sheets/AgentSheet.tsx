import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentLiveState, MoneyLimitName, TradingReadiness } from "@lonora/contracts";
import {
  agentStatusLine,
  readinessTime,
  tradingReadinessLine,
  tradingSafetyText,
  uncertainLine,
} from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { useCallback, useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { useAgentLiveState } from "../../lib/agent-live-state";
import type { Agent } from "../../lib/api";
import { api } from "../../lib/api";
import { liftRestriction, resumeTrading, stopNewTrading } from "../../lib/trading";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
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

const LIMIT_ROWS: Array<[MoneyLimitName, () => string]> = [
  ["max_daily_loss", () => t`Daily loss limit`],
  ["max_trade_risk_equity_percent", () => t`Trade risk limit`],
  ["max_open_risk_equity_percent", () => t`Open risk limit`],
  ["min_free_margin", () => t`Minimum free margin`],
];

function AgentSheetBody({
  agent,
  onJump,
  close,
}: {
  agent: Agent;
  onJump: (id: string) => void;
  close: () => void;
}) {
  const { state } = useAgentLiveState(agent.id);
  const prefs = useChatPrefs();
  const { refresh } = useClient();
  const toast = useToast();
  const limits = useLimitsSheet();
  const watches = useWatchesSheet();
  const [busy, setBusy] = useState(false);
  const readiness = state?.trading_readiness ?? null;
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
      <div className="sf-head">
        <AgentAvatar agent={agent} />
        <div>
          <strong>{agent.name}</strong>
          <small data-testid="agent-mode-line">
            {readiness
              ? tradingReadinessLine(readiness, i18n.locale)
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
                {work?.text && <small dir="auto">{work.text}</small>}
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
                    stopped ? t`Trading resumed` : t`Trading stopped · closing is still allowed`,
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
                    <Trans>Pause</Trans>
                  </button>
                )
              )}
            </div>
            {systemPauses.map((r) => (
              <div key={r.id} className="row">
                <Icon name="lock" />
                <span className="body">
                  <strong>{restrictionText(r)}</strong>
                  <small>
                    {r.source === "agent" ? t`Set by the agent` : t`Set by you`} ·{" "}
                    {t`closing allowed`}
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
                  <small>
                    <Trans>Unconfirmed operation · not confirmed by the broker</Trans>
                  </small>
                </span>
                {pendingId && (
                  <button
                    type="button"
                    className="btn sm"
                    onClick={() => {
                      close();
                      onJump(pendingId);
                    }}
                  >
                    <Trans>Resolve</Trans>
                  </button>
                )}
              </div>
            ))}
          </div>
          {account && (
            <>
              <h3>
                <Trans>Account limits</Trans>
              </h3>
              <div className="group">
                {LIMIT_ROWS.map(([key, label]) => (
                  <div key={key} className="row">
                    <span className="body">{label()}</span>
                    <span className="value ltr">
                      {account.limits[key] != null
                        ? `${account.limits[key]}${key.endsWith("percent") ? "%" : account.currency ? ` ${account.currency}` : ""}`
                        : t`No limit`}
                    </span>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="btn full outline"
                onClick={() => {
                  close();
                  limits(account.account_id);
                }}
              >
                <Trans>Edit the limits</Trans>
              </button>
            </>
          )}
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

export function useAgentSheet(onJump: (id: string) => void) {
  const sheets = useSheets();
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
        body: <AgentSheetBody agent={agent} onJump={onJump} close={() => sheets.close()} />,
      });
    },
    [sheets, onJump],
  );
}
