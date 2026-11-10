import { t } from "@lingui/core/macro";
import type { AgentPermissionLevel } from "@lonora/contracts";
import type { IconName } from "@lonora/ui-web";
import { useCallback, useEffect, useState } from "react";
import { type Agent, api, isRequestCancelled, type Resource } from "../../lib/api";
import { brokerIdentityLabel } from "../../lib/broker-identity";
import { useClient } from "../../providers/ClientProvider";

/** One read, refetched by every runtime revision; null path reads nothing. */
export function useRead<T>(path: string | null) {
  const { revision } = useClient();
  const [value, setValue] = useState<T>();
  const [error, setError] = useState<unknown>();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    void revision;
    void tick;
    if (!path) return;
    let live = true;
    api
      .get<T>(path)
      .then((next) => {
        if (!live) return;
        setValue(next);
        setError(undefined);
      })
      .catch((caught: unknown) => {
        if (live && !isRequestCancelled(caught)) setError(caught);
      });
    return () => {
      live = false;
    };
  }, [path, revision, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { value, error, loading: value === undefined && error === undefined, reload };
}

/** A trading agent: the trading template, or a focus pair on an account (reference isTrader). */
export const isTrader = (agent: Agent) =>
  agent.template === "trading" ||
  (agent.role !== "personal" && agent.role !== "delegated" && Boolean(agent.trading_account_id));

/** The research template never trades: no level badge and no permission line (reference hasDelegation). */
export const hasDelegation = (agent: Agent) =>
  agent.template !== "research" && agent.role !== "delegated";

export const levelIcon: Record<AgentPermissionLevel, IconName> = {
  analysis: "eye",
  supervised: "userCheck",
  autonomous: "bot",
};

/** The reference's ladder words: دون تنفيذ · تنفيذ بموافقة · تنفيذ مفوَّض. */
export function levelLabel(level: AgentPermissionLevel) {
  if (level === "autonomous") return t({ message: "On its own", context: "level" });
  if (level === "supervised") return t({ message: "Ask me", context: "level" });
  return t({ message: "No trading", context: "level" });
}

/** «{broker} · {number}», or the simulation's label when the broker gave none. */
export function accountLabel(connections: Resource[], id: string | null | undefined) {
  const index = connections.findIndex((row) => row.id === id);
  return index < 0 ? t`Unknown account` : brokerIdentityLabel(connections[index], index);
}

export function watchCondition(payload: Record<string, unknown>) {
  const symbol = String(payload.symbol ?? "");
  const level = payload.level != null ? String(payload.level) : "";
  switch (payload.condition) {
    case "below":
    case "cross_below":
      return t`${symbol} below ${level}`;
    case "above":
    case "cross_above":
      return t`${symbol} above ${level}`;
    default:
      return symbol || t`Watch`;
  }
}

export const clockTime = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });

/** The agent of an agent page: from the shell's list, or read directly while the list has
 * not caught up (a freshly created agent, a deep link). `missing` once the server says so. */
export function usePageAgent(agentId: string, agents: Agent[], listLoading: boolean) {
  const listed = agents.find((row) => row.id === agentId);
  const direct = useRead<Agent>(listed ? null : `/agents/${encodeURIComponent(agentId)}`);
  const agent = listed ?? direct.value;
  return { agent, missing: !agent && !listLoading && direct.error != null };
}
