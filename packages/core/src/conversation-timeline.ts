import type { Message, OwnerAction, TradeApproval, UiSlotCard } from "@lonora/contracts";
import { isUiPart } from "./genui/spec";
import { validateRichContent } from "./visual-response";

/** The owner-action kind each owner-action fixed card a slot names is stored as. */
export const SLOT_OWNER_ACTION_KINDS: Readonly<
  Record<Exclude<UiSlotCard, "trade_approval">, string>
> = { settle: "resolve_operation", mandate: "trading_mode" };

/** The `card:record` key of an owner-action card when a slot can name it, else null. */
function ownerActionSlot(action: OwnerAction): string | null {
  const card = Object.entries(SLOT_OWNER_ACTION_KINDS).find(
    ([, kind]) => kind === action.kind,
  )?.[0];
  return card ? `${card}:${action.id}` : null;
}

/** The records the drawn cards of these messages embed as trusted slots, keyed
 * `card:record`. A message counts only as the renderers draw it: an assistant message whose
 * whole rich content validates, each card up to its cut. A fixed card's standalone row is
 * shown only while none of them embeds its record (mandate 10.2.3). */
export function embeddedSlots(
  messages: readonly Message[],
  undrawn: ReadonlySet<string> = new Set(),
): ReadonlySet<string> {
  const found = new Set<string>();
  for (const message of messages) {
    if (message.role !== "assistant" || undrawn.has(message.id)) continue;
    for (const part of validateRichContent(message.rich_content)?.parts ?? []) {
      if (!isUiPart(part)) continue;
      part.document.blocks.forEach((block, position) => {
        if (block.type !== "Slot" || (part.cut !== undefined && position >= part.cut)) return;
        found.add(`${String(block.card)}:${String(block.record)}`);
      });
    }
  }
  return found;
}

export type ConversationItem =
  | { kind: "message"; id: string; seq: number; message: Message }
  | { kind: "approval"; id: string; seq: number; approval: TradeApproval }
  | { kind: "owner_action"; id: string; seq: number; action: OwnerAction };

/** Server sequence anchors win over fetch timing and mutable approval status. A fixed card
 * that a message embeds as a trusted slot has no standalone row: the slot is its place
 * (mandate 10.2.3); the row returns as soon as no message embeds it. */
export function conversationTimeline(
  messages: Message[],
  approvals: TradeApproval[],
  ownerActions: OwnerAction[] = [],
  /** Messages the client draws as another card (a question, a peer's message) instead of
   * their rich content: a slot in them is not drawn, so it never hides a row. */
  undrawn: ReadonlySet<string> = new Set(),
): ConversationItem[] {
  const ordered = [...new Map(messages.map((message) => [message.id, message])).values()].sort(
    (a, b) => a.seq - b.seq,
  );
  const rows: ConversationItem[] = ordered.map((message) => ({
    kind: "message",
    id: `message:${message.id}`,
    seq: message.seq,
    message,
  }));
  const slots = embeddedSlots(ordered, undrawn);
  for (const approval of new Map(approvals.map((row) => [row.id, row])).values()) {
    if (slots.has(`trade_approval:${approval.id}`)) continue;
    // Legacy rows retain their persisted request timestamp, never client arrival time.
    const seq =
      approval.timeline_seq ??
      ordered.find((message) => Date.parse(message.created_at) >= Date.parse(approval.created_at))
        ?.seq ??
      (ordered.at(-1)?.seq ?? 0) + 1;
    rows.push({ kind: "approval", id: `approval:${approval.id}`, seq, approval });
  }
  for (const action of new Map(ownerActions.map((row) => [row.id, row])).values()) {
    const key = ownerActionSlot(action);
    if (key && slots.has(key)) continue;
    // Anchored like an approval: after everything that existed when it was raised.
    const seq =
      action.timeline_seq ??
      ordered.find((message) => Date.parse(message.created_at) >= Date.parse(action.created_at))
        ?.seq ??
      (ordered.at(-1)?.seq ?? 0) + 1;
    rows.push({ kind: "owner_action", id: `owner_action:${action.id}`, seq, action });
  }
  const order = { approval: 0, owner_action: 1, message: 2 };
  const time = (item: ConversationItem) =>
    item.kind === "approval"
      ? item.approval.created_at
      : item.kind === "owner_action"
        ? item.action.created_at
        : item.message.created_at;
  return rows.sort(
    (a, b) =>
      a.seq - b.seq ||
      order[a.kind] - order[b.kind] ||
      time(a).localeCompare(time(b)) ||
      a.id.localeCompare(b.id),
  );
}

export function nearConversationBottom(
  contentHeight: number,
  viewportHeight: number,
  offset: number,
) {
  return contentHeight - viewportHeight - offset <= 80;
}
