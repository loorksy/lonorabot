export type AgentLiveState = {
  agent_id: string;
  observed_at: string;
  state: "idle" | "working" | "waiting" | "action_required" | "degraded" | "paused";
  phase: string;
  reason_code: string | null;
  pending_approval_count: number;
  watch_count: number;
  pending_authorization_count?: number;
  super_bot?: Array<{
    request_id: string;
    goal_id: string;
    title: string;
    mode: "advisory" | "supervised" | "autonomous";
    authorization_status: "pending" | "activated" | "paused";
    goal_status: string;
    current_step: string | null;
    reason_code: string | null;
    autonomous: boolean;
    review_status?: string | null;
    review_error_code?: string | null;
  }>;
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
  health: Array<{ account_id: string; symbol?: string; reason_code?: string }>;
};
