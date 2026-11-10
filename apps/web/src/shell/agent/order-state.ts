import type { Journal } from "@lonora/contracts";

/** The reference's order states (OD_ST), Q30: the server's operation states under its names. */
export type OrderState =
  | "requested"
  | "sent"
  | "accepted"
  | "partial"
  | "filled"
  | "rejected"
  | "cancelled"
  | "uncertain";
export type OrderTone = "wait" | "ok" | "bad" | "off" | "warn";

export const ORDER_TONE: Record<OrderState, OrderTone> = {
  requested: "wait",
  sent: "wait",
  accepted: "wait",
  partial: "ok",
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

type Details = { price?: unknown; volume?: unknown };
const details = (entry: Journal) => (entry.result.details ?? {}) as Details;
const decimal = (value: unknown) =>
  value == null || value === "" || !Number.isFinite(Number(value)) ? null : String(value);

/** The broker's evidence on a fill: its price and the volume it reports (Q30). */
export function orderFill(entry: Journal): { price: string | null; volume: string | null } {
  const fill = details(entry);
  return { price: decimal(fill.price), volume: decimal(fill.volume) };
}

/** «منفَّذ» only with the broker's evidence or the owner's own confirmation; a fill for less
 * than was asked is «منفَّذ جزئيًا», never a full «منفَّذ». */
export function orderState(entry: Journal): OrderState {
  switch (entry.status) {
    case "reserved":
      return "requested";
    case "submitted":
      return "sent";
    case "confirmed": {
      if (!verified(entry)) return "accepted";
      const asked = Number(entry.request.volume);
      const got = Number(orderFill(entry).volume);
      return Number.isFinite(asked) && Number.isFinite(got) && got > 0 && got < asked
        ? "partial"
        : "filled";
    }
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
