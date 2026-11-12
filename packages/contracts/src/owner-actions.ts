import type { AuthorityAction } from "./account-authority";
import type { AuthorityDuration } from "./agent-permissions";
import type { EffectTier } from "./capabilities";
import type { DeviceProof } from "./devices";
import type { MoneyLimitName, MoneyLimits, RestrictionActionClass, TradingMode } from "./trading";

export type OwnerActionKind =
  | "lift_restriction"
  | "resolve_operation"
  | "set_account_limits"
  | "grant_authority"
  | "create_agent"
  | "agent_created"
  | "supervise"
  | "supervision_created"
  | "supervision_stopped"
  | "supervision_paused"
  | "trust_source"
  | "connect_credential"
  /** The Secret card: fields the agent chose; values go straight to the encrypted store. */
  | "secret"
  /** Notices of a change an agent made without asking (Q31): Undo of an extended watch. */
  | "watch_changed"
  /** A stop loss an agent tightened under its grant: recorded settled, no Undo. */
  | "stop_tightened"
  /** The Mandate card: the agent's mode read live and one button for the other mode. */
  | "trading_mode";
/**
 * A grant card's one choice: Custom (the markets, actions, duration, daily loss limit and
 * own positions the card shows) or Full delegation (every pair on the account, every
 * action and the owner's own positions, until stopped, no daily loss limit from the card).
 */
export type GrantDelegation = "custom" | "full";
/** trust_source: what the owner adds to the trusted list. */
export type TrustSourceKind = "mcp_server" | "github_owner" | "github_repo" | "feed_domain";
/** connect_credential: which secure form the card offers. */
export type CredentialTarget =
  | "mcp_server"
  | "news_feed"
  | "brave_search"
  | "economic_calendar"
  | "broker";
/** One field of a Secret card, chosen by the agent: its key names the saved value; a
 * field with secret false may be shown while typed. Every value is stored encrypted. */
export type SecretField = { key: string; label: string; secret: boolean };
/** Where a Secret card's values go; the server sets it, never the agent's fields. */
export type SecretDestination = "workspace" | "broker";
/** Agent templates (lonora_contracts.agent_creation); none carries money authority. */
export type AgentTemplate = "trading" | "general" | "research" | "supervisor";
/** A creation card's agent, read on the server. */
export type OwnerActionAgent = {
  exists: boolean;
  id?: string;
  name: string | null;
  template?: AgentTemplate | null;
  symbol?: string | null;
  level?: "analysis" | "supervised" | "autonomous";
  paused?: boolean;
  report_to?: string[];
  /** Names of the agents it supervises (reads, messages, pauses; never trades). */
  supervises?: string[];
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
  /** Every pair, every action and the owner's own positions, with no expiry or cap. */
  full_delegation?: boolean;
};
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
  /** The newer card that replaced this one («عرض الأحدث»), or null. */
  superseded_by: string | null;
  /** owner: a grant card the owner drafted from the mandate sheet. */
  source: "agent" | "system" | "owner";
  agent_id: string;
  thread_id: string | null;
  run_id: string | null;
  timeline_seq: number | null;
  facts: {
    several_accounts: boolean;
    /** The Mandate card: the agent's mode now, read live. */
    trading_mode?: TradingMode;
    /** The Mandate card: a signed grant of this agent is still in force. */
    active_grant?: boolean;
    /** The Mandate card shown by migration 0063 (14.3.18.2): the grants that ended. */
    previous_grants?: Array<{
      full_delegation: boolean;
      symbol_scope: "selected" | "account";
      symbols: string[];
      account: OwnerActionAccount;
    }>;
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
      operation_id: string;
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
      /** The card's choice now (Custom by default); the owner switches it on the card. */
      delegation?: GrantDelegation;
      /** False for an agent whose grant never covers every pair (a fixed-market agent). */
      full_available?: boolean;
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
    /** create_agent / agent_created: the agent the card creates or created. */
    agent?: OwnerActionAgent;
    /** agent_created: what Undo does now (remove an untouched agent, else pause it). */
    undo?: "delete" | "pause";
    /**
     * supervise / supervision_created / supervision_stopped: who supervises whom;
     * supervision_paused: which supervisor paused which work of which agent. Names are
     * read on the server.
     */
    supervision?: {
      supervisor_name: string | null;
      supervised_names: string[];
      /**
       * supervision_created: a grant of this change is still in force; supervision_stopped:
       * one can still be restored; supervision_paused: the pause still holds.
       */
      active: boolean;
      /** supervision_paused: what is paused, and that item's own short label. */
      target?: "agent" | "task" | "routine" | "watch";
      target_label?: string | null;
      from_owner_message?: boolean;
      /** The owner paused it too: the pause is the owner's now. */
      owner_holds?: boolean;
    };
    /**
     * trust_source: the source to trust. An MCP server's label is its saved name and its
     * tools are the reviewed names (tools that can move money are listed as blocked;
     * writes are the ones that may change something and run only at the write tier);
     * review is true when the server is trusted already and its tools changed.
     */
    source?: {
      kind: TrustSourceKind;
      label: string | null;
      subscribe: boolean;
      tools?: string[];
      writes?: string[];
      blocked?: string[];
      review?: boolean;
      tier?: EffectTier | null;
    };
    /** connect_credential: the form to offer ("x" names an X MCP server). */
    credential?: { target: CredentialTarget; service: "x" | null };
    /** The Secret card: the agent's label and fields, where they go and who asked. */
    secret?: {
      label: string;
      fields: SecretField[];
      destination: SecretDestination;
      agent_name: string | null;
      /** A broker card (raised only by the connect tool): the account the password is for. */
      account?: { login: string; server: string; platform: "mt4" | "mt5" };
      /** A broker card: connect the account, store its new password, or a new token. */
      purpose?: "connect" | "rotate_password" | "replace_token";
    };
    /** watch_changed: the agent's extension; active while Undo still restores it. */
    watch?: {
      symbol: string | null;
      kind: string | null;
      previous_expires_at: string | null;
      /** null: the agent removed the end (the watch runs until cancelled). */
      expires_at: string | null;
      active: boolean;
    };
    /** stop_tightened: the position's stop loss before and after (no Undo). */
    stop?: {
      symbol: string;
      position_id: string;
      previous_stop_loss: string | null;
      stop_loss: string;
    };
  };
  /** Confirming needs the owner's passkey: it raises or removes a money limit. */
  requires_passkey: boolean;
  result: {
    outcome?: AttestedOutcome;
    limits?: MoneyLimits;
    daily_loss?: string | null;
    /** The account's own daily loss limit, unchanged by the card. */
    daily_loss_kept?: string | null;
    money_limit?: "apply" | "none";
    /** A grant card: the choice that was signed. */
    delegation?: GrantDelegation;
    stopped_agents?: string[];
    allowed_added?: boolean;
    undone?: boolean;
    agent_id?: string;
    agent_name?: string;
    undo?: "deleted" | "paused";
    grant_ids?: string[];
    supervisor_id?: string;
    revoked?: number;
    restored?: number;
    /** supervision_paused: what was resumed. */
    resumed?: boolean | "agent" | "task" | "routine" | "watch";
    tier?: EffectTier;
    tools?: number;
    /** trust_source on an MCP server: how many trusted tools may change something. */
    writes?: number;
    subscribed?: boolean;
    target?: CredentialTarget;
    configured?: boolean;
    connection_id?: string;
    integration_id?: string;
    /** A saved Secret card: the keys saved and where; never a value. */
    saved?: string[];
    /** A broker card: how provisioning stands (9.2). */
    provisioning?: "pending" | "deploying" | "reading" | "connected" | "failed";
    destination?: SecretDestination;
    /** connect_credential for an MCP server: whether its trust card followed. */
    review?: "raised" | "unread" | "nothing_to_trust" | "disabled" | "already";
    /** resolve_operation answered unknown with pause_new_today: the owner pause it set. */
    restriction_id?: string;
    /** watch_changed Undo: the watch's expiry now. */
    expires_at?: string | null;
  };
  expires_at: string;
  decided_at: string | null;
  decided_via: "tap" | "passkey" | null;
  created_at: string;
  updated_at: string;
};
export type OwnerActionDecision = {
  /** "choose" switches a pending grant card's choice in its stored draft; it signs nothing. */
  decision: "confirm" | "cancel" | "choose";
  /** The Mandate card: the mode its button showed at the moment of the tap. */
  trading_mode?: TradingMode;
  /** Grant card, with "choose": Custom or Full delegation. */
  delegation?: GrantDelegation;
  outcome?: AttestedOutcome;
  note?: string;
  broker_reference?: string;
  proof?: DeviceProof;
  /** Grant card: "none" leaves the account's daily loss limit as it is. */
  money_limit?: "apply" | "none";
  /** Grant card: stop these other agents' grants on this market (narrowing). */
  stop_authorities?: string[];
  /** trust_source on an MCP server: what the owner trusts its tools for. */
  tier?: EffectTier;
  /** connect_credential: what the secure form created; never the value it holds. */
  connected?: { resource: "integration" | "mcp" | "broker"; id: string };
  /**
   * Resolve card answered "unknown" only: also pause new trades by every agent on its
   * account until the trading day ends there (an owner restriction; it only narrows).
   */
  pause_new_today?: boolean;
};
/**
 * The mandate sheet («تنفيذ مفوَّض»): POST /agents/{id}/account-authorities/draft. It
 * becomes a pending grant card; nothing is active until the owner signs that card with
 * the passkey (POST /owner-actions/{id}/challenge, then /decision with the proof and the
 * card's choices: money_limit, stop_authorities). "full" takes no terms:
 * every pair for Lonora and flexible agents; a fixed-pair agent's own pair only, every
 * action, until stopped, its owner's positions included.
 */
export type AccountAuthorityDraft = {
  mode?: GrantDelegation;
  thread_id?: string;
  account_id?: string;
  symbols?: string[];
  all_pairs?: boolean;
  actions?: AuthorityAction[];
  duration?: AuthorityDuration;
  allow_manual_positions?: boolean;
  /** An amount in the account currency (Q16), or daily_loss_percent of equity now. */
  daily_loss_amount?: string;
  daily_loss_percent?: string;
};
/** The draft's grant card, with the exact stored payload and its hash. */
export type AccountAuthorityDraftResult = {
  owner_action: OwnerAction;
  payload: Record<string, unknown>;
  payload_hash: string;
};
/**
 * Grant card: the owner's choice that changes what the passkey signs (his own positions,
 * under Custom only), and the choice the card showed when he tapped. The server refuses a
 * challenge whose choice differs from the card's stored draft (owner_action_card_changed).
 */
export type OwnerActionChallenge = {
  delegation?: GrantDelegation;
  allow_manual_positions?: boolean;
};
