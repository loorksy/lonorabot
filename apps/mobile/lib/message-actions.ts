// The message menu's rules, as on Web's conversation menu: which messages can be edited and
// resent (Q21), which can become a task, and the owner's single quick reaction (Q26, Q28).
import type { Message, MessageReaction, ReactionEmoji } from "@lonora/contracts";

const pending = (message: Message) => message.id.startsWith("pending:");
/** A part the owner did not type: a card, a chart, a voice note, a call log. */
const drawn = (message: Message) =>
  (message.rich_content?.parts ?? []).some((part) => part.type !== "text");

/** «تعديل وإعادة الإرسال»: the owner's own plain text (no voice note, no files), not yet
 * replaced, never a card's send. */
export function canEditAndResend(message: Message): boolean {
  return (
    message.role === "user" &&
    !pending(message) &&
    !message.attachment_ids.length &&
    !drawn(message) &&
    !message.superseded_by &&
    message.origin !== "ui_submit"
  );
}

/** «تحويل إلى مهمة»: a text message, never a drawn answer, a voice note or files. */
export function canTurnIntoTask(message: Message): boolean {
  return (
    !pending(message) &&
    Boolean(message.content.trim()) &&
    !message.attachment_ids.length &&
    !drawn(message)
  );
}

/** The task a message becomes: POST /tasks?agent_id=&thread_id= with this body. */
export const taskFromMessage = (message: Message) => ({
  title: message.content.slice(0, 160),
  description: message.content,
});

export const ownerReaction = (rows: readonly MessageReaction[] | undefined) =>
  rows?.find((row) => row.reactor === "owner")?.emoji ?? null;

/** The owner holds at most one reaction per message: a new one replaces it, null removes it. */
export function withOwnerReaction(
  rows: readonly MessageReaction[] | undefined,
  emoji: ReactionEmoji | null,
  now: string,
): MessageReaction[] {
  const others = (rows ?? []).filter((row) => row.reactor !== "owner");
  return emoji ? [...others, { reactor: "owner", emoji, created_at: now }] : others;
}
