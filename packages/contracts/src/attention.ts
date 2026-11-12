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
  | "collaboration_completed"
  | "task_review"
  | "task_degraded"
  | "task_completed"
  | "internal_update"
  | "super_bot_authorization"
  | "super_bot_changed"
  | "maintenance_item_quarantined"
  | "run_quarantined"
  | "operation_unresolved"
  | "operation_uncertain"
  | "gateway_degraded"
  | "agent_notification";
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
    /** An Agent's own alert (agent_notification): its plain summary for the owner. */
    summary?: string;
    /** Where an Agent's alert is delivered; "in_app" until off-app delivery exists. */
    delivery?: "in_app";
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
