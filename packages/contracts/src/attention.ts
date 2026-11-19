export type AttentionImportance =
  | "critical"
  | "action_required"
  | "important_change"
  | "opportunity"
  | "informational"
  | "silent";
export type AttentionCode =
  | "watch_condition_met"
  | "approval_required"
  | "approval_resolved"
  | "broker_token_rejected"
  | "broker_account_undeployed"
  | "broker_connection_lost"
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
  | "agent_notification"
  | "secret_requested"
  | "mandate_proposed";
/**
 * The events of mandate 11.4 that need the owner, by code: each is one item, ready at
 * once and withdrawn when its card ends or its problem clears. Mirrors ATTENTION_EVENTS
 * in lonora_contracts.attention.
 */
export type AttentionEvent =
  | "trade_approval"
  | "settle_operation"
  | "secret_request"
  | "mandate_card"
  | "broker_health";
export const ATTENTION_EVENTS: Partial<Record<AttentionCode, AttentionEvent>> = {
  approval_required: "trade_approval",
  operation_uncertain: "settle_operation",
  secret_requested: "secret_request",
  mandate_proposed: "mandate_card",
  broker_token_rejected: "broker_health",
  broker_account_undeployed: "broker_health",
  broker_connection_lost: "broker_health",
};
/** A broker health problem (mandate 9.4): one item per account and problem. */
export function isBrokerHealth(code: AttentionCode): boolean {
  return ATTENTION_EVENTS[code] === "broker_health";
}
/** The payload of the attention.updated and attention.ready events. */
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
    /** Broker health: when the problem started and the adapter's reason code. */
    since?: string;
    reason_code?: string;
    /** The Secret or Mandate card the item is about. */
    owner_action_id?: string;
    /** An Agent's own alert (agent_notification): its plain summary for the owner. */
    summary?: string;
    /** Where an Agent's alert is delivered; "in_app" until off-app delivery exists. */
    delivery?: "in_app";
  };
  source_count: number;
  version: number;
  created_at: string;
  updated_at: string;
}
export interface AttentionPolicy {
  opportunities: boolean;
  informational: boolean;
  locale: "ar" | "en";
}
