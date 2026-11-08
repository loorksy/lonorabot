import { i18n } from "@lingui/core";
import type { AgentLiveState, TradingReadiness } from "@lonora/contracts";
import {
  isolate,
  moneyLimitsLine,
  pauseClassLabel,
  readinessTime,
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
import { type Agent, api, type Resource } from "../../lib/api";
import { brokerIdentityLabel } from "../../lib/broker-identity";
import { operationStatusLabel } from "../../lib/operation-status";
import { readConnections, resumeTrading, stopNewTrading } from "../../lib/trading";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import "./safety-pill.css";

/**
 * The thread header's one safety pill: can this agent trade now, and what stops it.
 * It renders the server's presentation-only readiness; the executor alone decides.
 */
export function SafetyPill({ agentId, agents }: { agentId: string; agents: Agent[] }) {
  const { revision, refresh } = useClient();
  const [readiness, setReadiness] = useState<TradingReadiness | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [accounts, setAccounts] = useState<Resource[]>([]);
  const locale = i18n.locale;
  const text = tradingSafetyText(locale);
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<AgentLiveState>(`/agents/${encodeURIComponent(agentId)}/state`)
      .then((state) => {
        if (live) setReadiness(state.trading_readiness ?? null);
      })
      .catch(() => {
        // The pill is informational: a failed read keeps the last known line.
      });
    return () => {
      live = false;
    };
  }, [agentId, revision]);
  useEffect(() => {
    if (!open) return;
    let live = true;
    void readConnections()
      .then((rows) => {
        if (live) setAccounts(rows);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [open]);
  if (!readiness) return null;
  const stopped = readiness.global_trading.state === "stopped";
  const accountIds = new Set([
    ...readiness.money_limits.map((item) => item.account_id),
    ...readiness.grants.map((item) => item.account_id),
  ]);
  const accountName = (id: string) => {
    if (accountIds.size < 2) return null;
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
  const line = tradingReadinessLine(readiness, locale);
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
              {stopped ? text.stopped : text.running}
              {readiness.global_trading.since && (
                <>
                  {" "}
                  · {text.since} {readinessTime(readiness.global_trading.since, locale)}
                </>
              )}
            </p>
            <p className="muted">{stopped ? text.resumeHint : text.stopHint}</p>
            {stopped ? (
              <button
                type="button"
                className="primary"
                disabled={busy}
                onClick={() => void change(resumeTrading)}
              >
                {text.resume}
              </button>
            ) : (
              <button
                type="button"
                className="danger"
                disabled={busy}
                onClick={() => void change(stopNewTrading)}
              >
                {text.stop}
              </button>
            )}
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
                        : text.noEnd}
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
