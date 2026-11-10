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

type Details = { price?: unknown; volume?: unknown; partial_execution?: unknown };
const details = (entry: Journal) => (entry.result.details ?? {}) as Details;
const decimal = (value: unknown) =>
  value == null || value === "" || !Number.isFinite(Number(value)) ? null : String(value);
/** Pending-order entries: a confirmed one was placed at the broker, not filled. */
const PENDING = new Set(["buy_limit", "sell_limit", "buy_stop", "sell_stop"]);

/** What the executor recorded on a partial fill (the adapter's `partial_execution`, with the
 * broker's executed volume when it reported one). */
export const partialFill = (entry: Journal) =>
  entry.status === "confirmed" && details(entry).partial_execution === true;

/** The broker's evidence on a fill: its price and the volume it reports (Q30). Only a filled
 * or partly filled order has any; a placed, rejected, cancelled or pending one has none. */
export function orderFill(entry: Journal): { price: string | null; volume: string | null } {
  const state = orderState(entry);
  if (state !== "filled" && state !== "partial") return { price: null, volume: null };
  const fill = details(entry);
  return { price: decimal(fill.price), volume: decimal(fill.volume) };
}

/** «منفَّذ» only with the broker's evidence or the owner's own confirmation; a partial fill is
 * «منفَّذ جزئيًا» whatever its verification (verify_effect never verifies one); a placed
 * limit or stop order is «مقبول لدى الوسيط», never «منفَّذ». */
export function orderState(entry: Journal): OrderState {
  switch (entry.status) {
    case "reserved":
      return "requested";
    case "submitted":
      return "sent";
    case "confirmed": {
      if (partialFill(entry)) return "partial";
      if (PENDING.has(String(entry.request.action))) return "accepted";
      return verified(entry) ? "filled" : "accepted";
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
