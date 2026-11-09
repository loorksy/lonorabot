import { i18n } from "@lingui/core";
import { operationStatusText } from "@lonora/core";
import type { OperationStatus } from "./api";

/**
 * Owner-facing label for a durable financial operation, from the one table Web and Mobile
 * share (@lonora/core). Only the stage the server's evidence establishes is shown: an
 * unverified or uncertain result is never "Confirmed", and a changed target is never
 * called gone.
 */
export function operationStatusLabel(status: OperationStatus | string, details?: unknown): string {
  return operationStatusText(String(status), details, i18n.locale);
}

/** Whether a client must keep the same operation identity: the outcome is not settled. */
export function operationUnsettled(status: OperationStatus | string): boolean {
  return status === "reserved" || status === "submitted" || status === "ambiguous";
}
