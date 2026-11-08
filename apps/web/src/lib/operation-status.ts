import { t } from "@lingui/core/macro";
import { operationStatusKey } from "@lonora/core";
import type { OperationStatus } from "./api";

/**
 * Owner-facing label for a durable financial operation. Only the stage the server's
 * evidence establishes is shown (shared with Mobile through @lonora/core): an
 * unverified or uncertain result is never "Confirmed", and a changed target is never
 * called gone.
 */
export function operationStatusLabel(status: OperationStatus | string, details?: unknown): string {
  switch (operationStatusKey(String(status), details)) {
    case "preparing":
      return t`Preparing — not sent`;
    case "awaiting_broker":
      return t`Awaiting broker confirmation`;
    case "acknowledged_unverified":
      return t`Broker acknowledged — resulting state unverified`;
    case "confirmed":
      return t`Confirmed`;
    case "not_sent":
      return t`Not sent`;
    case "failed":
      return t`Failed`;
    case "uncertain":
      return t`Outcome uncertain — it will not be sent again`;
    case "resolved_by_owner":
      return t`Resolved by owner`;
    case "resolved_position_closed":
      return t`Resolved — position no longer open`;
    case "resolved_order_gone":
      return t`Resolved — order no longer pending`;
    case "resolved_target_changed":
      return t`Resolved — changed by another action; current state observed`;
    case "resolved_unconfirmed":
      return t`Resolved without broker confirmation`;
    default:
      return t`Awaiting reconciliation`;
  }
}

/** Whether a client must keep the same operation identity: the outcome is not settled. */
export function operationUnsettled(status: OperationStatus | string): boolean {
  return status === "reserved" || status === "submitted" || status === "ambiguous";
}
