import type { TradingMode } from "@lonora/contracts";

/** The mode a Mandate decision response applied. Full only when the response says Full. */
export function appliedTradingMode(
  result: { trading_mode?: string | null } | null | undefined,
): TradingMode {
  return result?.trading_mode === "full" ? "full" : "ask";
}

/**
 * The agent the screen shows after that response. Only `trading_mode` changes, so the
 * parent's other fields stay, and the control reads this same field.
 */
export function agentShowingMandate<T extends { trading_mode?: TradingMode | null }>(
  agent: T,
  result: { trading_mode?: string | null } | null | undefined,
): Omit<T, "trading_mode"> & { trading_mode: TradingMode } {
  return { ...agent, trading_mode: appliedTradingMode(result) };
}

/** The other mode a reopen offers. Null when the agent has no mode. */
export function otherTradingMode(mode: TradingMode | null): TradingMode | null {
  if (mode === "full") return "ask";
  if (mode === "ask") return "full";
  return null;
}
