// Order lines in the conversation, as on Web (Q30): one line per trading-journal operation of
// this chat, at its anchor (the server's timeline_seq: before the first message after it),
// else by time; an operation of another chat never shows here.
import type { Journal } from "@lonora/contracts";
import type { ConversationItem } from "@lonora/core";

export type TimelineItem =
  | ConversationItem
  | { kind: "order"; id: string; seq: number; journal: Journal };

export function withOrderLines(
  items: readonly ConversationItem[],
  journal: readonly Journal[],
  threadId: string,
): TimelineItem[] {
  const out: TimelineItem[] = [...items];
  for (const row of journal) {
    if (row.thread_id !== threadId) continue;
    const anchor = row.timeline_seq;
    const at = Date.parse(row.submitted_at ?? row.updated_at);
    const index =
      anchor != null
        ? out.findIndex((item) => item.kind === "message" && item.message.seq > anchor)
        : out.findIndex(
            (item) => item.kind === "message" && Date.parse(item.message.created_at) > at,
          );
    const line: TimelineItem = {
      kind: "order",
      id: `order:${row.operation_id}`,
      seq: anchor ?? Number.MAX_SAFE_INTEGER,
      journal: row,
    };
    if (index < 0) out.push(line);
    else out.splice(index, 0, line);
  }
  return out;
}
