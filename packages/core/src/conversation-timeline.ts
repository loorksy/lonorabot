import type { Message, OwnerAction, TradeApproval } from "@lonora/contracts";
import { embeddedSlots } from "./genui/spec";

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
  const slots = embeddedSlots(ordered);
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
    if (action.kind === "resolve_operation" && slots.has(`settle:${action.id}`)) continue;
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
