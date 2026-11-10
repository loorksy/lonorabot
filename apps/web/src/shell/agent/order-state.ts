import type { Journal } from "@lonora/contracts";

/** The reference's order states (OD_ST), Q30: the server's operation states under its names. */
export type OrderState =
  | "requested"
  | "sent"
  | "accepted"
  | "filled"
  | "rejected"
  | "cancelled"
  | "uncertain";
export type OrderTone = "wait" | "ok" | "bad" | "off" | "warn";

export const ORDER_TONE: Record<OrderState, OrderTone> = {
  requested: "wait",
  sent: "wait",
  accepted: "wait",
  filled: "ok",
  rejected: "bad",
  cancelled: "off",
  uncertain: "warn",
};

const verified = (entry: Journal) => {
  if (entry.verification_status) return entry.verification_status === "verified";
  const details = entry.result.details as { verification?: { status?: unknown } } | undefined;
  return details?.verification?.status === "verified";
};

/** «منفَّذ» only with the broker's evidence or the owner's own confirmation. */
export function orderState(entry: Journal): OrderState {
  switch (entry.status) {
    case "reserved":
      return "requested";
    case "submitted":
      return "sent";
    case "confirmed":
      return verified(entry) ? "filled" : "accepted";
    case "failed":
      return "rejected";
    case "ambiguous":
      return "uncertain";
    case "resolved": {
      const outcome = entry.resolution?.outcome;
      return outcome === "executed"
        ? "filled"
        : outcome === "not_executed"
          ? "cancelled"
          : "uncertain";
    }
    default:
      return "uncertain";
  }
}
