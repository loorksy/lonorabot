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

/** The order line of one journal operation, from its durable status and result only. */
export function orderLineState(
  journal: Pick<Journal, "status" | "request" | "result"> & { send_state?: string },
): OrderLine {
  const request = record(journal.request);
  const result = record(journal.result);
  const details = record(result.details);
  const verification = record(details.verification).status;
  const resolution = record(details.resolution);
  const requested = decimal(request.volume);
  const reported = decimal(details.volume);
  const sendState = journal.send_state ?? details.send_state;
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
      const ticket = typeof result.broker_id === "string" && result.broker_id !== "";
      if (!ticket && verification !== "verified") return line("uncertain", ["requested", "sent"]);
      const partial =
        requested !== null && reported !== null && Number(reported) < Number(requested);
      return line(
        partial ? "partial" : "filled",
        ["requested", "sent", "accepted"],
        "broker",
        reported ?? requested,
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
