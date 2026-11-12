// The owner text of each attention code, as the web's AttentionInbox labels; the heads-up
// banner names an urgent item with it.
import type { AttentionCode } from "@lonora/contracts";
import type { Label } from "./i18n";

export const attentionLabels: Record<AttentionCode, Label> = {
  approval_required: "attentionApproval",
  approval_resolved: "attentionRequestUpdated",
  broker_token_rejected: "attentionBrokerTokenRejected",
  broker_account_undeployed: "attentionBrokerUndeployed",
  broker_connection_lost: "attentionBrokerConnectionLost",
  external_broker_activity: "attentionAccountChanged",
  setup_confirmed: "attentionSetupConfirmed",
  thesis_invalidated: "attentionThesisChanged",
  watch_condition_met: "attentionWatchChanged",
  collaboration_completed: "attentionCollaborationCompleted",
  task_review: "taskNeedsReview",
  task_degraded: "attentionTaskDegraded",
  // Retired Super Bot items still stored in the inbox; nothing raises them any more.
  super_bot_authorization: "attentionRequestUpdated",
  super_bot_changed: "attentionRequestUpdated",
  task_completed: "attentionTaskCompleted",
  internal_update: "attentionUpdated",
  maintenance_item_quarantined: "attentionItemQuarantined",
  run_quarantined: "attentionRunQuarantined",
  operation_unresolved: "attentionOperationUnresolved",
  operation_uncertain: "attentionOperationUncertain",
  gateway_degraded: "attentionGatewayDegraded",
  agent_notification: "attentionAgentAlert",
  secret_requested: "attentionSecretRequested",
  mandate_proposed: "attentionMandateProposed",
};
