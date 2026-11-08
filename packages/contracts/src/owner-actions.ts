import type { AuthorityAction } from "./account-authority";
import type { AuthorityDuration } from "./agent-permissions";
import type { DeviceProof } from "./super-bot";
import type { GlobalTrading, MoneyLimitName, MoneyLimits, RestrictionActionClass } from "./trading";

export type OwnerActionKind =
  | "resume_trading"
  | "lift_restriction"
  | "resolve_operation"
  | "set_account_limits"
  | "grant_authority";
export type OwnerActionStatus = "pending" | "confirmed" | "cancelled" | "expired" | "superseded";
export type AttestedOutcome = "executed" | "not_executed" | "unknown";
/** A limits card shows one line per changed field: a limit, its currency or the day's zone. */
export type OwnerActionLimitField = MoneyLimitName | "currency" | "trading_day_timezone";
/** The broker identity the owner recognizes; label is null when it is not verified. */
export type OwnerActionAccount = { id: string; label: string | null; provider: string | null };
/** What a signed grant allows: markets, actions, caps, protections, expiry and own positions. */
export type OwnerActionGrantTerms = {
  management_mode: "bounded" | "full";
  symbol_scope: "selected" | "account";
  symbols: string[];
  actions: AuthorityAction[];
  all_actions: boolean;
  maximum_order_volume: string | null;
  maximum_symbol_volume: string | null;
  maximum_positions: number | null;
  maximum_pending_orders: number | null;
  maximum_actions: number | null;
  minimum_equity: string | null;
  valid_until: string | null;
  allow_manual_positions: boolean;
};
/**
 * One owner-only action offered as a card in the conversation (lonora_db.owner_actions).
 * Every fact is read on the server from the records the card names; nothing an agent
 * wrote appears on it. Only the owner's session can confirm it.
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
    /** A grant card: exactly what the owner signs, resolved on the server from its draft. */
    grant?: {
      agent_name: string | null;
      agent_is_personal: boolean;
      symbol_scope: "selected" | "account";
      symbols: string[];
      actions: AuthorityAction[];
      all_actions: boolean;
      duration: AuthorityDuration;
      allow_manual_positions: boolean;
    };
    /** The account's money limits and the daily loss line a grant card sets (D1). */
    money?: {
      limits: MoneyLimits;
      daily_loss: {
        current: string | null;
        /** Set by the card on confirm unless the owner chooses no money limit. */
        proposed: string | null;
        currency: string | null;
        basis: "suggested" | "requested" | null;
        percent: string | null;
        /** The owner asked for more than the current limit: the card keeps the current one. */
        requested_above?: string | null;
      };
    };
    /** Other agents already trading this market on the account on their own. */
    conflicts?: Array<{
      authority_id: string;
      agent_name: string | null;
      symbol_scope: "selected" | "account";
      symbols: string[];
    }>;
    /** Everything the agent's own grant on this account allows, which the new one replaces. */
    replaces?: OwnerActionGrantTerms | null;
    /** The owner's first grant: the card shows the one rule. */
    first_grant?: boolean;
  };
  /** Confirming needs the owner's passkey: it raises or removes a money limit. */
  requires_passkey: boolean;
  result: {
    outcome?: AttestedOutcome;
    global_trading?: string;
    limits?: MoneyLimits;
    resumed?: boolean;
    daily_loss?: string | null;
    /** The account's own daily loss limit, unchanged by the card. */
    daily_loss_kept?: string | null;
    money_limit?: "apply" | "none";
    stopped_agents?: string[];
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
  /** Grant card: "none" leaves the account's daily loss limit as it is. */
  money_limit?: "apply" | "none";
  /** Grant card: resume new trading too (it widens no authority). */
  resume_trading?: boolean;
  /** Grant card: stop these other agents' grants on this market (narrowing). */
  stop_authorities?: string[];
};
/** Grant card: the owner's choice that changes what the passkey signs. */
export type OwnerActionChallenge = { allow_manual_positions?: boolean };
