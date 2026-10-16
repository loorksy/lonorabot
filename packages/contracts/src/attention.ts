export type AttentionImportance =
  | "critical"
  | "action_required"
  | "important_change"
  | "opportunity"
  | "informational"
  | "silent";
export type AttentionCode =
  | "watch_condition_met"
  | "emergency_stop"
  | "approval_required"
  | "approval_resolved"
  | "broker_degraded"
  | "broker_recovered"
  | "external_broker_activity"
  | "setup_confirmed"
  | "thesis_invalidated"
  | "goal_changed"
  | "collaboration_completed"
  | "task_review"
  | "task_completed"
  | "internal_update";
export interface AttentionNotification {
  id: string;
  agent_id: string;
  thread_id: string;
  importance: AttentionImportance;
  code: AttentionCode;
  status: "pending" | "ready" | "seen" | "suppressed";
  parameters: {
    symbol?: string;
    account_id?: string;
    group_id?: string;
    valid_until?: string;
    execution_authorized?: false;
  };
  source_count: number;
  version: number;
  created_at: string;
}
export interface AttentionPolicy {
  opportunities: boolean;
  informational: boolean;
  locale: "ar" | "en";
}
