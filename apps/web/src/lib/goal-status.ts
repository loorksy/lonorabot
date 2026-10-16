import { t } from "@lingui/core/macro";

export function goalStatusLabel(value: unknown): string {
  switch (String(value).toLowerCase()) {
    case "active":
      return t`Active`;
    case "waiting":
      return t`Waiting for a condition`;
    case "blocked":
      return t`Needs attention`;
    case "planning":
      return t`Planning`;
    case "waiting_for_condition":
      return t`Waiting for a condition`;
    case "condition_triggered":
      return t`Condition triggered`;
    case "revalidating":
      return t`Rechecking market conditions`;
    case "ready_to_execute":
      return t`Ready to execute`;
    case "executing":
      return t`Executing`;
    case "verifying":
      return t`Verifying execution`;
    case "ambiguous":
      return t`Execution requires reconciliation`;
    case "reconciling":
      return t`Reconciling with broker`;
    case "position_open":
      return t`Position open`;
    case "monitoring":
      return t`Monitoring`;
    case "completed":
    case "confirmed":
    case "executed":
      return t`Completed`;
    case "failed":
      return t`Failed`;
    case "paused":
      return t`Paused`;
    case "cancelled":
      return t`Cancelled`;
    default:
      return t`Pending`;
  }
}
