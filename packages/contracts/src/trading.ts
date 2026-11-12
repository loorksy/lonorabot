import type { Payload } from "./domain";
export type Quote = {
  symbol: string;
  bid: string;
  ask: string;
  observed_at: string;
  source: string;
  profit_tick_value?: string | null;
  loss_tick_value?: string | null;
  tick_value_basis?: "account_currency_per_lot" | null;
  account_currency_exchange_rate?: string | null;
};
export type Candle = {
  symbol: string;
  timeframe: string;
  time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
};
export type Instrument = {
  symbol: string;
  description: string;
  path?: string | null;
  digits: number;
  tick_size: string;
  volume_min: string;
  volume_max: string;
  volume_step: string;
  stops_level?: number;
  point_size?: string | null;
  contract_size?: string | null;
  base_currency?: string | null;
  profit_currency?: string | null;
};
export type Position = {
  id: string;
  symbol: string;
  side: string;
  volume: string;
  open_price: string;
  profit: string;
  stop_loss: string | null;
  take_profit: string | null;
};
export type Order = { id: string; symbol: string; side: string; volume: string; price: string };
export type AccountSummary = {
  account: {
    id: string;
    currency: string;
    balance: string;
    equity: string;
    margin: string;
    free_margin: string;
    observed_at: string;
    broker?: string | null;
    login?: string | null;
    server?: string | null;
    name?: string | null;
    platform?: string | null;
  };
  positions: Position[];
  orders: Order[];
};
export type Trade = {
  account_id: string;
  operation_id: string;
  action: string;
  symbol: string;
  volume?: string;
  price?: string;
  stop_loss?: string;
  take_profit?: string;
  /** modify_position: remove the stop or the target (the server decides if that is allowed). */
  clear_stop_loss?: boolean;
  clear_take_profit?: boolean;
  position_id?: string;
  order_id?: string;
};
/**
 * Durable financial operation lifecycle (lonora_contracts.trading.OperationStatus).
 * reserved: journaled, provably not sent. submitted: send authorized, may be at the broker.
 * confirmed: broker acknowledged or broker evidence established it. failed: known outcome,
 * including never sent (send_state "not_sent"). ambiguous: possibly sent, outcome unknown;
 * never resent automatically. resolved: uncertainty settled without broker confirmation
 * (owner attestation or the target no longer exists).
 */
export type OperationStatus =
  | "reserved"
  | "submitted"
  | "confirmed"
  | "failed"
  | "ambiguous"
  | "resolved";
export type OperationSendState = "not_sent" | "sent" | "unknown";
export type OperationResolutionRecord = {
  source: "owner" | "broker_state";
  basis?: string;
  outcome?: "executed" | "not_executed" | "unknown";
  statement?: string;
  resolved_at?: string;
  broker_confirmed?: false;
};
export type Journal = {
  operation_id: string;
  account_id: string;
  status: OperationStatus;
  request: Payload;
  result: Payload;
  submitted_at: string | null;
  updated_at: string;
  run_id?: string | null;
  agent_id?: string | null;
  send_state?: OperationSendState;
  verification_status?: string | null;
  awaiting_broker_confirmation?: boolean;
  resolution?: OperationResolutionRecord | null;
  /**
   * Conversation anchor (presentation only): the thread and its next message seq when an
   * agent Run of that conversation requested the operation; null for the owner's own
   * controls and background transitions. The chat places the order line there.
   */
  thread_id?: string | null;
  timeline_seq?: number | null;
};
/**
 * The Execution Receipt (mandate 10.3, 11.2) of one broker-confirmed operation
 * (lonora_db.execution_receipts.receipt_data). Every fact is the broker's: fills give the
 * ticket, action, volume and fill price; a placed order its ticket and order; a change
 * its ticket and new values; a cancel its ticket.
 */
export type ExecutionReceipt = {
  operation_id: string;
  thread_id: string | null;
  timeline_seq: number | null;
  /** The requesting agent; null for the owner's own order. */
  agent_id: string | null;
  created_at: string;
  kind: "fill" | "order" | "modify" | "cancel";
  action: string;
  symbol: string;
  ticket: string | null;
  volume?: string | null;
  price?: string | null;
  partial?: boolean;
  stop_loss?: string | null;
  take_profit?: string | null;
  stop_loss_removed?: boolean;
  take_profit_removed?: boolean;
  /** The agent's own words, stored beside the request; null for the owner's own order. */
  reason: string | null;
  /** Broker-confirmed; "pending" until the resulting account state is read back. */
  verification: "pending" | "verified" | "unverified" | null;
};
/** The agent's one trading switch: Full executes on its own, Ask asks for new risk. */
export type TradingMode = "full" | "ask";
export type TradeApproval = {
  timeline_seq?: number | null;
  id: string;
  run_id: string;
  thread_id: string;
  agent_id: string;
  /** expired: a card stored with a lifetime ended unapproved («طلب جديد» asks again);
   * drifted: the quote left reference ± tolerance; withdrawn: ended without a decision. */
  status:
    | "pending"
    | "approved"
    | "rejected"
    | "completed"
    | "cancelled"
    | "expired"
    | "withdrawn"
    | "drifted";
  requests: Payload[];
  results: {
    operation_id: string;
    status: OperationStatus;
    broker_id?: string | null;
    code?: string | null;
    details: Payload;
  }[];
  /** Stored cards only: past it the card can no longer be approved. New cards have none. */
  expires_at?: string | null;
  /** The agent's own words: shown labelled as the agent's, never as the owner's. */
  reason?: string;
  /** Price distance; the card drifts outside reference_price ± tolerance. */
  tolerance?: string | null;
  reference_price?: string | null;
  created_at: string;
};
/** Owner money limits of one account (lonora_db.trading_readiness.risk_limit_frame). */
export type MoneyLimitName =
  | "max_trade_risk"
  | "max_trade_risk_equity_percent"
  | "max_daily_loss"
  | "max_open_risk"
  | "max_open_risk_equity_percent"
  | "min_free_margin";
export type MoneyLimits = {
  account_id: string;
  /** False: no money limit is set on this account, so none is enforced. */
  configured: boolean;
  currency: string | null;
  limits: Partial<Record<MoneyLimitName, string>>;
  not_configured: MoneyLimitName[];
  trading_day_timezone?: string;
};
export type RestrictionActionClass = "no_new_entries" | "no_risk_increase" | "all_mutations";
export type TradingReadinessState =
  | "no_trading"
  | "agent_paused"
  | "paused"
  | "uncertain"
  | "ask_me"
  | "on_its_own";
/**
 * Presentation only: can this agent trade now, and what stops it. Built on the server
 * from the records the executor reads; never consulted for enforcement.
 */
export type TradingReadiness = {
  presentation_only: true;
  observed_at: string;
  state: TradingReadinessState;
  params: {
    action_class?: RestrictionActionClass;
    valid_until?: string | null;
    symbol?: string | null;
    /**
     * paused: the account of the strongest pause; on_its_own: the first grant's account.
     * The line names it when the owner has several accounts.
     */
    account_id?: string | null;
    count?: number;
    symbol_scope?: "selected" | "account";
    /** on_its_own: the first grant is Full delegation (every pair, action and own position). */
    full_delegation?: boolean;
    symbols?: string[];
    grant_count?: number;
    /** on_its_own: how many accounts its grants cover. */
    account_count?: number;
    money_limit_set?: boolean;
    /** The daily loss limit of the grant's account, when the owner set one. */
    daily_loss?: { amount: string; currency: string | null } | null;
  };
  level: "analysis" | "supervised" | "autonomous";
  grants: Array<{
    account_id: string;
    symbol_scope: "selected" | "account";
    symbols: string[];
    actions: string[];
    allow_manual_positions: boolean;
    valid_until: string | null;
    /** Every pair on the account, every action and the owner's own positions, until revoked. */
    full_delegation?: boolean;
  }>;
  restrictions: Array<{
    id: string;
    account_id: string;
    symbol: string | null;
    action_class: RestrictionActionClass;
    state: "active" | "scheduled";
    applies_to: "all_agents" | "this_agent";
    includes_owner_manual: boolean;
    valid_from: string;
    valid_until: string | null;
    source: "owner_ui" | "owner_message" | "agent";
    created_by_agent_id: string | null;
  }>;
  money_limits: MoneyLimits[];
  unresolved_operations: Array<{
    operation_id: string;
    account_id: string;
    symbol: string;
    action: string;
    status: "submitted" | "ambiguous";
    submitted_at: string | null;
    this_agent: boolean;
    blocks: "new_risk_on_this_symbol_or_ticket";
    /** The operation's own pending resolve card («حسم») and the conversation that holds it
        (an agent's chat or a group), or null. */
    resolve_card: {
      id: string;
      thread_id: string | null;
      agent_id: string | null;
      group_id: string | null;
      timeline_seq: number | null;
    } | null;
  }>;
  unresolved_count: number;
  exits_allowed: boolean;
};
