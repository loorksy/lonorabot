import type { AccountAuthorityProposal } from "./account-authority";
import type { MoneyLimits, TradingReadiness } from "./trading";

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
};
