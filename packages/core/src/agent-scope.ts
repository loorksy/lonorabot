import type { Agent } from "@lonora/contracts";

/** A default market is a preference; only legacy bindings restrict visibility. */
export function hasFixedMarket(agent: Pick<Agent, "scope_mode" | "trading_account_id">): boolean {
  return Boolean(agent.trading_account_id) && agent.scope_mode !== "flexible";
}

export type AgentMarketMode = "fixed" | "general" | "market";
export function agentMarketMode(agent: Agent): AgentMarketMode {
  return agent.scope_mode !== "flexible" && agent.role !== "personal"
    ? "fixed"
    : agent.trading_account_id
      ? "market"
      : "general";
}

export function marketScopeChange(
  mode: AgentMarketMode,
  pair: { trading_account_id: string; trading_symbol: string },
  revision = 0,
  current?: Agent,
) {
  if (mode === "fixed") return {};
  const change = {
    scope_mode: "flexible" as const,
    trading_account_id: mode === "market" ? pair.trading_account_id : null,
    trading_symbol: mode === "market" ? pair.trading_symbol : null,
    expected_scope_revision: revision,
  };
  if (
    current?.scope_mode === "flexible" &&
    (current.trading_account_id ?? null) === change.trading_account_id &&
    (current.trading_symbol ?? null) === change.trading_symbol
  )
    return {};
  return change;
}
