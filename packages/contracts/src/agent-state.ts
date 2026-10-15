export type AgentLiveState = {
  agent_id: string;
  observed_at: string;
  state: "idle" | "working" | "waiting" | "action_required" | "degraded" | "paused";
  phase: string;
  reason_code: string | null;
  pending_approval_count: number;
  watch_count: number;
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
