import type { Message, ReplyStreamSnapshot, Run } from "./api";

export type StreamRow = { run: Run; stream: ReplyStreamSnapshot };
export function streamVisible(
  run: Run,
  stream: ReplyStreamSnapshot | undefined,
  messages: Message[],
): boolean {
  if (!stream?.text || !["streaming", "committed"].includes(stream.phase)) return false;
  if (stream.message_id && messages.some((m) => m.id === stream.message_id)) return false;
  const canonical = messages.filter((m) => !m.id.startsWith("pending:"));
  if (stream.phase === "committed" && !canonical.length) return false;
  if (
    canonical.length &&
    run.input_seq != null &&
    run.input_seq < Math.min(...canonical.map((m) => m.seq))
  )
    return false;
  return true;
}
/** Place a provisional reply at its observed input, rather than in a detached footer. */
export function streamTimeline(messages: Message[], streams: StreamRow[]): Message[] {
  const rows = streams.filter(({ run, stream }) => streamVisible(run, stream, messages));
  return [
    ...messages,
    ...rows.map(({ run, stream }) => {
      const anchor =
        run.input_seq ??
        Math.max(
          0,
          ...messages
            .filter(
              (m) =>
                m.role === "user" &&
                !m.id.startsWith("pending:") &&
                Date.parse(m.created_at) <= Date.parse(run.created_at),
            )
            .map((m) => m.seq),
        );
      return {
        id: `preview:${run.id}`,
        thread_id: run.thread_id,
        agent_id: run.agent_id,
        seq: anchor + 0.125,
        role: "assistant" as const,
        content: stream.text,
        created_at: messages.find((m) => m.seq === anchor)?.created_at ?? run.created_at,
        reply_to: null,
        attachment_ids: [],
      };
    }),
  ].sort((a, b) => a.seq - b.seq || a.id.localeCompare(b.id));
}
