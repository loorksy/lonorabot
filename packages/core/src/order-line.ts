/**
 * One order line per financial operation in the chat (Q30): the server's durable operation
 * states under the reference's names (Lonora-Desktop-37 OD_ST / odTimeline()):
 * requested «مطلوب» → sent «مُرسَل» → accepted «مقبول لدى الوسيط» → partial «منفَّذ جزئيًا» |
 * filled «منفَّذ», or rejected «مرفوض» · cancelled «ملغى» · uncertain «غير مؤكَّد».
 *
 * «منفَّذ» never shows without evidence: a broker ticket or a verified resulting state, or
 * the owner's own attestation. A confirmation without it reads «غير مؤكَّد». The partial
 * quantity is the broker-reported volume of the result, never an estimate.
 */
import type { Journal } from "@lonora/contracts";
import { accountAuthorityLabels } from "./account-authority-labels";

export type OrderLineState =
  | "requested"
  | "sent"
  | "accepted"
  | "partial"
  | "filled"
  | "rejected"
  | "cancelled"
  | "uncertain";

export type OrderLine = {
  state: OrderLineState;
  /** The timeline steps reached, in order; the last one is `state`. */
  steps: OrderLineState[];
  /** What was asked and what the broker reported filled (decimal strings), when known. */
  requested_volume: string | null;
  filled_volume: string | null;
  /** Who established a fill: the broker's result or the owner's attestation. */
  evidence: "broker" | "owner" | null;
  /** The fill price the broker reported; only with fill evidence, never the requested price. */
  fill_price: string | null;
  /** The broker's own reference for the operation (ticket, order or position id), if any. */
  ticket: string | null;
  /** Never sent to the broker (a brake, a limit or a released reservation stopped it). */
  not_sent: boolean;
};

export const orderLineLabels = {
  ar: {
    requested: "مطلوب",
    sent: "مُرسَل",
    accepted: "مقبول لدى الوسيط",
    partial: "منفَّذ جزئيًا",
    filled: "منفَّذ",
    rejected: "مرفوض",
    cancelled: "ملغى",
    uncertain: "غير مؤكَّد",
  },
  en: {
    requested: "Requested",
    sent: "Sent",
    accepted: "Accepted by the broker",
    partial: "Partially filled",
    filled: "Filled",
    rejected: "Rejected",
    cancelled: "Cancelled",
    uncertain: "Unconfirmed",
  },
} as const satisfies Record<"ar" | "en", Record<OrderLineState, string>>;

export function orderLineText(state: OrderLineState, locale: string): string {
  return orderLineLabels[locale.startsWith("ar") ? "ar" : "en"][state];
}

// Entries that rest at the broker until the market reaches their price.
const PENDING_ENTRIES = new Set(["buy_limit", "sell_limit", "buy_stop", "sell_stop"]);

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function decimal(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return value;
  return null;
}

/** The order line of one journal operation, from its durable status and result only
    (the executor's TradeResult: status, broker_id, code, details{order_id, position_id,
    price, volume, partial_execution, verification, resolution}). */
export function orderLineState(
  journal: Pick<Journal, "status" | "request" | "result"> & {
    send_state?: string;
    verification_status?: string | null;
  },
): OrderLine {
  const request = record(journal.request);
  const result = record(journal.result);
  const details = record(result.details);
  const verification = journal.verification_status ?? record(details.verification).status;
  const resolution = record(details.resolution);
  const requested = decimal(request.volume);
  const reported = decimal(details.volume);
  const sendState = journal.send_state ?? details.send_state;
  const text = (value: unknown) => (typeof value === "string" && value !== "" ? value : null);
  const ticket =
    text(result.broker_id) ??
    text(details.order_id) ??
    text(details.position_id) ??
    text(details.deal_id);
  const line = (
    state: OrderLineState,
    reached: OrderLineState[],
    evidence: OrderLine["evidence"] = null,
    filled: string | null = null,
  ): OrderLine => ({
    state,
    steps: [...reached, state],
    requested_volume: requested,
    filled_volume: filled,
    evidence,
    fill_price:
      evidence === "broker" && (state === "filled" || state === "partial")
        ? (decimal(details.price) ?? decimal(details.execution_price))
        : null,
    ticket,
    not_sent: journal.status === "failed" && sendState === "not_sent",
  });
  switch (journal.status) {
    case "reserved":
      return line("requested", []);
    case "submitted":
      return line("sent", ["requested"]);
    case "confirmed": {
      if (verification === "pending") return line("accepted", ["requested", "sent"]);
      // Acknowledged, but the resulting account state could not be verified.
      if (verification === "unverified") return line("uncertain", ["requested", "sent"]);
      if (PENDING_ENTRIES.has(String(request.action)))
        return line("accepted", ["requested", "sent"]);
      if (!ticket && verification !== "verified") return line("uncertain", ["requested", "sent"]);
      // The broker's own word on a partial fill; otherwise a reported volume short of the request.
      const partial =
        Boolean(details.partial_execution) ||
        (requested !== null && reported !== null && Number(reported) < Number(requested));
      return line(
        partial ? "partial" : "filled",
        ["requested", "sent", "accepted"],
        "broker",
        partial ? reported : (reported ?? requested),
      );
    }
    case "failed":
      // Stopped before the broker (a brake, a limit, a released reservation): never sent.
      if (sendState === "not_sent") return line("cancelled", ["requested"]);
      return line("rejected", ["requested", "sent"]);
    case "ambiguous":
      return line("uncertain", ["requested", "sent"]);
    case "resolved":
      if (resolution.source === "owner" && resolution.outcome === "executed")
        return line("filled", ["requested", "sent"], "owner", requested);
      if (resolution.source === "owner" && resolution.outcome === "not_executed")
        return line("cancelled", ["requested", "sent"]);
      // Settled without establishing the operation's own outcome: it stays unconfirmed.
      return line("uncertain", ["requested", "sent"]);
    default:
      return line("uncertain", ["requested"]);
  }
}

/** What the operation does, in the reference's words: «شراء» / «بيع» for market orders (odSide),
    the authority vocabulary for entries, closes, modifications and cancellations. */
export function orderLineAction(request: Record<string, unknown>, locale: string) {
  const action = String(request.action ?? "");
  const ar = locale.startsWith("ar");
  const labels = accountAuthorityLabels[ar ? "ar" : "en"] as Record<string, string>;
  const label =
    action === "buy"
      ? ar
        ? "شراء"
        : "Buy"
      : action === "sell"
        ? ar
          ? "بيع"
          : "Sell"
        : (labels[action] ?? action);
  // A volume belongs to entries and closes; a modification or a cancellation has none.
  const volume = [
    "buy",
    "sell",
    "buy_limit",
    "sell_limit",
    "buy_stop",
    "sell_stop",
    "close_position",
  ].includes(action)
    ? decimal(request.volume)
    : null;
  const direction: "up" | "down" | null = action.startsWith("buy")
    ? "up"
    : action.startsWith("sell")
      ? "down"
      : null;
  return { label, volume, direction };
}
