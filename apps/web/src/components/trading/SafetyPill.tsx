import { i18n } from "@lingui/core";
import type { TradingReadiness } from "@lonora/contracts";
import {
  isolate,
  moneyLimitsLine,
  pauseClassLabel,
  readinessTime,
  tradingBrake,
  tradingReadinessLine,
  tradingReadinessTone,
  tradingSafetyText,
} from "@lonora/core";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@lonora/ui-web";
import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useAgentLiveState } from "../../lib/agent-live-state";
import type { Agent, Resource } from "../../lib/api";
import { brokerIdentityLabel } from "../../lib/broker-identity";
import { operationStatusLabel } from "../../lib/operation-status";
import { liftRestriction, readConnections, resumeTrading, stopNewTrading } from "../../lib/trading";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import "./safety-pill.css";

/**
 * The thread header's one safety pill: can this agent trade now, and what stops it.
 * It renders the server's presentation-only readiness; the executor alone decides.
 */
export function SafetyPill({ agentId, agents }: { agentId: string; agents: Agent[] }) {
  const { refresh } = useClient();
  const readiness: TradingReadiness | null =
    useAgentLiveState(agentId).state?.trading_readiness ?? null;
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [accounts, setAccounts] = useState<Resource[]>([]);
  const locale = i18n.locale;
  const text = tradingSafetyText(locale);
  // With more than one account the line and the sheet name the account of each item.
  const accountIds = new Set(
    readiness
      ? [
          ...readiness.money_limits.map((item) => item.account_id),
          ...readiness.grants.map((item) => item.account_id),
          ...readiness.restrictions.map((item) => item.account_id),
          ...readiness.unresolved_operations.map((item) => item.account_id),
        ]
      : [],
  );
  const several = accountIds.size > 1;
  useEffect(() => {
    if (!open && !several) return;
    let live = true;
    void readConnections()
      .then((rows) => {
        if (live) setAccounts(rows);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [open, several]);
  if (!readiness) return null;
  const brake = tradingBrake(readiness.global_trading, locale);
  const accountName = (id: string) => {
    if (!several) return null;
    const index = accounts.findIndex((row) => row.id === id);
    return index < 0 ? null : brokerIdentityLabel(accounts[index], index);
  };
  const agentName = (id: string | null) => {
    const name = agents.find((agent) => agent.id === id)?.name;
    return name ? `${text.setByAgent} · ${isolate(name)}` : text.setByAgent;
  };
  async function change(next: () => Promise<unknown>) {
    setBusy(true);
    try {
      await next();
      setError(undefined);
      refresh();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }
  const line = tradingReadinessLine(readiness, locale, new Date(), accountName);
  return (
    <>
      <button
        type="button"
        className="lonora-safety-pill"
        data-testid="safety-pill"
        data-readiness={readiness.state}
        data-tone={tradingReadinessTone(readiness)}
        aria-label={`${text.open}: ${line}`}
        title={line}
        onClick={() => setOpen(true)}
      >
        <ShieldCheck size={14} aria-hidden="true" />
        <span dir="auto">{line}</span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="lonora-safety-sheet" data-testid="safety-sheet">
          <DialogHeader>
            <DialogTitle>{text.title}</DialogTitle>
            <DialogDescription dir="auto">{line}</DialogDescription>
          </DialogHeader>
          <section aria-label={text.title}>
            <p role="status" data-trading-state={readiness.global_trading.state}>
              {brake.status}
              {readiness.global_trading.since && (
                <>
                  {" "}
                  · {text.since} {readinessTime(readiness.global_trading.since, locale)}
                </>
              )}
            </p>
            <p className="muted">{brake.hint}</p>
            <button
              type="button"
              className={brake.stopped ? "primary" : "danger"}
              disabled={busy}
              onClick={() => void change(brake.stopped ? resumeTrading : stopNewTrading)}
            >
              {brake.action}
            </button>
            {error != null && <p role="alert">{userError(error)}</p>}
          </section>
          <section>
            <h3>{text.level}</h3>
            <p>{text[readiness.level]}</p>
            {readiness.grants.map((grant) => (
              <p key={`${grant.account_id}:${grant.symbols.join(",")}`} dir="auto">
                {text.grants}
                {accountName(grant.account_id) && <> · {accountName(grant.account_id)}</>} ·{" "}
                {grant.symbol_scope === "account"
                  ? text.allPairs
                  : grant.symbols.map(isolate).join(", ")}{" "}
                ·{" "}
                {grant.valid_until
                  ? `${text.until} ${readinessTime(grant.valid_until, locale)}`
                  : text.untilStopped}{" "}
                · {grant.allow_manual_positions ? text.manualIncluded : text.manualExcluded}
              </p>
            ))}
          </section>
          <section>
            <h3>{text.pauses}</h3>
            {readiness.restrictions.length ? (
              <>
                {readiness.restrictions.map((item) => (
                  <p key={item.id} data-restriction-state={item.state} dir="auto">
                    {accountName(item.account_id) && <>{accountName(item.account_id)} · </>}
                    {pauseClassLabel(item.action_class, locale)} ·{" "}
                    {item.symbol ? isolate(item.symbol) : text.allPairs} ·{" "}
                    {item.applies_to === "all_agents" ? text.allAgents : text.thisAgent}
                    {item.includes_owner_manual && <> · {text.includesManual}</>} ·{" "}
                    {item.source === "owner_ui"
                      ? text.setByYou
                      : item.source === "owner_message"
                        ? text.fromYourMessage
                        : agentName(item.created_by_agent_id)}{" "}
                    ·{" "}
                    {item.state === "scheduled"
                      ? `${text.starts} ${readinessTime(item.valid_from, locale)}`
                      : item.valid_until
                        ? `${text.until} ${readinessTime(item.valid_until, locale)}`
                        : text.noEnd}{" "}
                    <button
                      type="button"
                      data-lift-restriction={item.id}
                      disabled={busy}
                      onClick={() => void change(() => liftRestriction(item.id))}
                    >
                      {text.lift}
                    </button>
                  </p>
                ))}
                <p className="muted">{text.onlyYouLift}</p>
              </>
            ) : (
              <p className="muted">{text.noPauses}</p>
            )}
            {!readiness.exits_allowed && <p role="alert">{text.exitsFrozen}</p>}
          </section>
          <section>
            <h3>{text.moneyLimits}</h3>
            {readiness.money_limits.map((limits) => (
              <p key={limits.account_id} dir="auto" data-money-limit={limits.configured}>
                {accountName(limits.account_id) && <>{accountName(limits.account_id)} · </>}
                {moneyLimitsLine(limits, locale)}
              </p>
            ))}
          </section>
          <section>
            <h3>{text.unresolved}</h3>
            {readiness.unresolved_operations.length ? (
              <>
                {readiness.unresolved_operations.map((operation) => (
                  <p key={operation.operation_id} dir="auto">
                    {accountName(operation.account_id) && (
                      <>{accountName(operation.account_id)} · </>
                    )}
                    <bdi>{operation.symbol}</bdi> · {operationStatusLabel(operation.status)}
                  </p>
                ))}
                <p className="muted">{text.uncertainHint}</p>
              </>
            ) : (
              <p className="muted">{text.noUnresolved}</p>
            )}
          </section>
        </DialogContent>
      </Dialog>
    </>
  );
}
