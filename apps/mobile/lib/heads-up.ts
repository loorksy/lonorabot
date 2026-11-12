// The heads-up banner's rules, as Web's HeadsUp (owner decisions Q4 and Q47, the reach-me
// policy): what an event or an attention item puts at the top of the screen, if anything.
import type { Agent, AttentionNotification, Event } from "@lonora/contracts";
import {
  attentionAlwaysShows,
  type ChatRow,
  headsUpAllowed,
  inQuietHours,
  type QuietHours,
  rowKey,
} from "@lonora/core";

export type Banner = { row: ChatRow; text: string };
const MAX = 120;
const cut = (text: string) => (text.length > MAX ? `${text.slice(0, MAX)}…` : text);

/**
 * An agent's answer in another chat: none for the open chat, a muted or archived chat, the
 * owner's quiet hours, an agent whose in-app rule is off, or anything from before the app
 * opened (with 5 s of slack).
 */
export function messageBanner(
  event: Event,
  context: {
    rows: readonly ChatRow[];
    agents: readonly Pick<Agent, "id" | "name">[];
    current: string | undefined;
    quiet: QuietHours | null;
    off: ReadonlySet<string>;
    openedAt: number;
    now: Date;
    newMessage: string;
  },
): Banner | null {
  const payload = event.payload as Record<string, unknown>;
  if (event.kind !== "message.created" || payload.role !== "assistant") return null;
  if (!event.thread_id || event.thread_id === context.current) return null;
  if (Date.parse(String(payload.created_at ?? "")) < context.openedAt - 5000) return null;
  if (inQuietHours(context.quiet, context.now)) return null;
  const row = context.rows.find((candidate) => candidate.threadId === event.thread_id);
  if (!row || !headsUpAllowed(row.entry)) return null;
  if (typeof payload.agent_id === "string" && context.off.has(payload.agent_id)) return null;
  const content = typeof payload.content === "string" ? payload.content.trim() : "";
  const speaker =
    row.kind === "group"
      ? context.agents.find((agent) => agent.id === payload.agent_id)?.name
      : undefined;
  return {
    row,
    text: content ? cut(speaker ? `${speaker}: ${content}` : content) : context.newMessage,
  };
}

/**
 * An urgent attention item (critical or action required) always shows, quiet hours included,
 * on its agent's or group's row.
 */
export function attentionBanner(
  item: AttentionNotification,
  context: { rows: readonly ChatRow[]; openedAt: number; labels: Record<string, string> },
): Banner | null {
  if (!attentionAlwaysShows(item.importance)) return null;
  if (Date.parse(item.created_at) < context.openedAt - 5000) return null;
  const parameters = (item.parameters ?? {}) as Record<string, string | undefined>;
  const key = parameters.group_id
    ? rowKey("group", parameters.group_id)
    : rowKey("agent", item.agent_id ?? "");
  const row = context.rows.find((candidate) => candidate.key === key);
  const text = parameters.summary || context.labels[item.code];
  return row && text ? { row, text: cut(text) } : null;
}
