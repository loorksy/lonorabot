import type { MessageReaction, Payload, ThreadOptions } from "./domain";
export type Event = {
  cursor: number;
  kind: string;
  thread_id: string | null;
  agent_id: string | null;
  run_id: string | null;
  payload: Payload;
  created_at: string;
};
/** `message.reaction_updated`: the message's whole reaction list after a change. */
export type MessageReactionUpdatedPayload = {
  thread_id: string;
  message_id: string;
  reactions: MessageReaction[];
};
/** `thread.updated`: the chat's options after PUT /api/threads/{id}/options. */
export type ThreadUpdatedPayload = { thread_id: string; options: ThreadOptions };
