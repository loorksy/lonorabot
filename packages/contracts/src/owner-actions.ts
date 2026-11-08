import type { DeviceProof } from "./super-bot";
import type { GlobalTrading, MoneyLimitName, MoneyLimits, RestrictionActionClass } from "./trading";

export type OwnerActionKind =
  | "resume_trading"
  | "lift_restriction"
  | "resolve_operation"
  | "set_account_limits"
  | "create_agent"
  | "agent_created";
/** Agent templates (lonora_contracts.agent_creation); none carries money authority. */
export type AgentTemplate = "trading" | "general" | "research" | "supervisor";
/** A creation card's agent, read on the server. */
export type OwnerActionAgent = {
  exists: boolean;
  name: string | null;
  template?: AgentTemplate | null;
  symbol?: string | null;
  level?: "analysis" | "supervised" | "autonomous";
  paused?: boolean;
  report_to?: string[];
  model?: string | null;
  /** Its task exactly as stored (its standing instructions); shown isolated and labelled. */
  responsibility?: string | null;
};
export type OwnerActionStatus = "pending" | "confirmed" | "cancelled" | "expired" | "superseded";
export type AttestedOutcome = "executed" | "not_executed" | "unknown";
/** A limits card shows one line per changed field: a limit, its currency or the day's zone. */
export type OwnerActionLimitField = MoneyLimitName | "currency" | "trading_day_timezone";
/** The broker identity the owner recognizes; label is null when it is not verified. */
export type OwnerActionAccount = { id: string; label: string | null; provider: string | null };
/**
 * One owner-only action offered as a card in the conversation (lonora_db.owner_actions).
 * Every fact is read on the server from the records the card names; nothing an agent
 * wrote appears on it, except a creation card's stored task, quoted and labelled
 * because it is the exact instruction the tap keeps. Only the owner's session can
 * confirm it.
 */
export type OwnerAction = {
  id: string;
  kind: OwnerActionKind;
  status: OwnerActionStatus;
  status_reason: string | null;
  source: "agent" | "system";
  agent_id: string;
  thread_id: string | null;
  run_id: string | null;
  timeline_seq: number | null;
  facts: {
    several_accounts: boolean;
    global_trading?: GlobalTrading;
    account?: OwnerActionAccount;
    restriction?: {
      action_class: RestrictionActionClass;
      symbol: string | null;
      all_agents: boolean;
      agent_name: string | null;
      includes_owner_manual: boolean;
      state: "scheduled" | "active" | "expired" | "revoked";
      valid_from: string;
      valid_until: string | null;
      source: "owner_ui" | "owner_message" | "agent";
      set_by_agent_name: string | null;
    };
    operation?: {
      action: string | null;
      symbol: string | null;
      volume: string | null;
      price: string | null;
      has_ticket: boolean;
      status: string;
      submitted_at: string | null;
      by_agent_name: string | null;
      by_owner: boolean;
    };
    blocks?: "new_risk_on_this_symbol_or_ticket";
    current?: MoneyLimits;
    proposed?: MoneyLimits;
    changes?: Array<{ name: OwnerActionLimitField; from: string | null; to: string | null }>;
    /** The account's limits changed since the card was raised and its change no longer fits. */
    no_longer_applies?: boolean;
    /** create_agent / agent_created: the agent the card creates or created. */
    agent?: OwnerActionAgent;
    /** agent_created: what Undo does now (remove an untouched agent, else pause it). */
    undo?: "delete" | "pause";
  };
  /** Confirming needs the owner's passkey: it raises or removes a money limit. */
  requires_passkey: boolean;
  result: {
    outcome?: AttestedOutcome;
    global_trading?: string;
    limits?: MoneyLimits;
    agent_id?: string;
    agent_name?: string;
    undo?: "deleted" | "paused";
  };
  expires_at: string;
  decided_at: string | null;
  decided_via: "tap" | "passkey" | null;
  created_at: string;
  updated_at: string;
};
export type OwnerActionDecision = {
  decision: "confirm" | "cancel";
  outcome?: AttestedOutcome;
  note?: string;
  broker_reference?: string;
  proof?: DeviceProof;
};
