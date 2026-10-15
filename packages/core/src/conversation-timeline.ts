import type { Message, TradeApproval } from "@lonora/contracts";

export type ConversationItem =
  | { kind: "message"; id: string; seq: number; message: Message }
  | { kind: "approval"; id: string; seq: number; approval: TradeApproval };

/** Server sequence anchors win over fetch timing and mutable approval status. */
export function conversationTimeline(
  messages: Message[],
  approvals: TradeApproval[],
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
  for (const approval of new Map(approvals.map((row) => [row.id, row])).values()) {
    // Legacy rows retain their persisted request timestamp, never client arrival time.
    const seq =
      approval.timeline_seq ??
      ordered.find((message) => Date.parse(message.created_at) >= Date.parse(approval.created_at))
        ?.seq ??
      (ordered.at(-1)?.seq ?? 0) + 1;
    rows.push({ kind: "approval", id: `approval:${approval.id}`, seq, approval });
  }
  return rows.sort(
    (a, b) =>
      a.seq - b.seq ||
      (a.kind !== b.kind
        ? a.kind === "approval"
          ? -1
          : 1
        : a.kind === "approval" && b.kind === "approval"
          ? a.approval.created_at.localeCompare(b.approval.created_at) || a.id.localeCompare(b.id)
          : a.id.localeCompare(b.id)),
  );
}

export function nearConversationBottom(
  contentHeight: number,
  viewportHeight: number,
  offset: number,
) {
  return contentHeight - viewportHeight - offset <= 80;
}
