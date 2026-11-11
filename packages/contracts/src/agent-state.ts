import type { AccountAuthorityProposal } from "./account-authority";
import type { MoneyLimits, TradingReadiness } from "./trading";

export type AgentWatchSummary = {
  id: string;
  kind: "price" | "indicator" | "position" | "account" | "calendar" | "dynamic";
  account_id: string | null;
  symbol: string | null;
  condition:
    | "above"
    | "below"
    | "cross_above"
    | "cross_below"
    | "changed"
    | "closed"
    | "opened"
    | "due"
    | null;
  level: string | null;
  indicator: string | null;
  timeframe: string | null;
  metric: string | null;
  expires_at: string | null;
  lifecycle: string;
};

/** What the agent does now, most urgent first, from durable records only. */
export type AgentCurrentWork = {
  kind: "analysing" | "searching" | "watching" | "broker" | "waiting_owner" | "other";
  /** Owner content only: the Task title, the owner's message being answered or the watched
      market (≤120); "" when the work is an operation or a card (no server prose). */
  text: string;
  /** ISO: the watch's expiry or the card's; null otherwise. */
  until: string | null;
  run_id: string | null;
  /** broker / waiting_owner: the operation as codes and numbers; the client words it. */
  operation?: { action: string; volume?: string; symbol: string } | null;
  /** waiting_owner: what waits for the owner. */
  card?: "trade_approval" | "owner_action" | null;
};

export type AgentLiveState = {
  agent_id: string;
  observed_at: string;
  state: "idle" | "working" | "waiting" | "action_required" | "degraded" | "paused";
  phase: string;
  reason_code: string | null;
  runtime_waits?: Array<{
    run_id: string;
    kind: "read_retry" | "model_retry" | "watch" | "broker_recovery" | "timer";
    retry_at: string | null;
  }>;
  pending_approval_count: number;
  watch_count: number;
  /** Active watches, newest first: what is watched and until when, never the prompt. */
  watches?: AgentWatchSummary[];
  pending_authorization_count?: number;
  account_authorities?: Array<
    Omit<AccountAuthorityProposal, "thread_id"> & {
      id: string;
      status: "pending" | "active";
      money_limits?: MoneyLimits;
      /** The readiness review after a bounded grant is signed (full grants start a Task). */
      review_status?: string | null;
    }
  >;
  tasks: Array<{
    id: string;
    title: string;
    status: string;
    phase: string;
    waiting_reason: string | null;
    version: number;
    can_pause: boolean;
    can_resume: boolean;
    can_cancel: boolean;
    attempt?: number;
    failure_code?: string | null;
    recovery?: string | null;
    retry_at?: string | null;
  }>;
  health: Array<{
    account_id: string;
    kind?: "broker" | "market";
    symbol?: string;
    reason_code?: string;
  }>;
  /** Present on the owner's state endpoint; presentation only. */
  trading_readiness?: TradingReadiness | null;
  current_work?: AgentCurrentWork | null;
  /** The newest pending owner-action card or trade approval waiting for the owner. */
  pending_card_id?: string | null;
};
