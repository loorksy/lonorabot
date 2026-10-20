import type { Message, SuperBotRequest, TradeApproval } from "@lonora/contracts";

export type ConversationItem =
  | { kind: "message"; id: string; seq: number; message: Message }
  | { kind: "approval"; id: string; seq: number; approval: TradeApproval }
  | { kind: "super_bot"; id: string; seq: number; request: SuperBotRequest };

/** Server sequence anchors win over fetch timing and mutable approval status. */
export function conversationTimeline(
  messages: Message[],
  approvals: TradeApproval[],
  superBotRequests: SuperBotRequest[] = [],
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
  for (const request of new Map(superBotRequests.map((row) => [row.id, row])).values()) {
    const timestamp =
      request.created_at ?? new Date(Date.parse(request.expires_at) - 600_000).toISOString();
    const seq =
      request.timeline_seq ??
      ordered.find((message) => Date.parse(message.created_at) >= Date.parse(timestamp))?.seq ??
      (ordered.at(-1)?.seq ?? 0) + 1;
    rows.push({ kind: "super_bot", id: `super_bot:${request.id}`, seq, request });
  }
  const order = { approval: 0, super_bot: 1, message: 2 };
  const time = (item: ConversationItem) =>
    item.kind === "approval"
      ? item.approval.created_at
      : item.kind === "super_bot"
        ? (item.request.created_at ?? item.request.expires_at)
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
