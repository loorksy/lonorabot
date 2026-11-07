import { t } from "@lingui/core/macro";
import type { OperationStatus, Payload } from "./api";

function field(value: unknown, key: string): unknown {
  return value && typeof value === "object" ? (value as Payload)[key] : undefined;
}

/**
 * Owner-facing label for a durable financial operation. Only the stage the server's
 * evidence establishes is shown: an unverified or uncertain result is never "Confirmed".
 */
export function operationStatusLabel(status: OperationStatus | string, details?: unknown): string {
  const verification = field(field(details, "verification"), "status");
  const resolution = field(field(details, "resolution"), "source");
  switch (status) {
    case "reserved":
      return t`Preparing — not sent`;
    case "submitted":
      return t`Awaiting broker confirmation`;
    case "confirmed":
      if (verification === "pending") return t`Awaiting broker confirmation`;
      if (verification === "unverified") return t`Broker acknowledged — resulting state unverified`;
      return t`Confirmed`;
    case "failed":
      return field(details, "send_state") === "not_sent" ? t`Not sent` : t`Failed`;
    case "ambiguous":
      return t`Outcome uncertain — it will not be sent again`;
    case "resolved":
      return resolution === "owner" ? t`Resolved by owner` : t`Resolved — target no longer exists`;
    default:
      return t`Awaiting reconciliation`;
  }
}

/** Whether a client must keep the same operation identity: the outcome is not settled. */
export function operationUnsettled(status: OperationStatus | string): boolean {
  return status === "reserved" || status === "submitted" || status === "ambiguous";
}
