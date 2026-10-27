import type { Message, ReplyStreamSnapshot, Run } from "./api";

export type StreamRow = { run: Run; stream: ReplyStreamSnapshot };
export function streamVisible(
  run: Run,
  stream: ReplyStreamSnapshot | undefined,
  messages: Message[],
): boolean {
  if (
    (!stream?.text && !stream?.rich_content) ||
    !["streaming", "committed", "cancelled", "failed"].includes(stream.phase)
  )
    return false;
  if (stream.message_id && messages.some((m) => m.id === stream.message_id)) return false;
  const canonical = messages.filter((m) => !m.id.startsWith("pending:"));
  if (stream.phase === "committed" && !canonical.length) return false;
  const inputSeq = stream.input_seq ?? run.input_seq;
  if (canonical.length && inputSeq != null && inputSeq < Math.min(...canonical.map((m) => m.seq)))
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
        stream.input_seq ??
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

/** Actual conversational activity occupies its own input's reply slot. Background work stays separate. */
export function activityTimeline(
  messages: Message[],
  runs: Run[],
  streams: StreamRow[],
): Message[] {
  const visible = new Set(
    streams
      .filter(({ run, stream }) => streamVisible(run, stream, messages))
      .map(({ run }) => run.id),
  );
  const canonical = messages.filter((row) => !row.id.startsWith("pending:"));
  return [
    ...streamTimeline(messages, streams),
    ...runs
      .filter(
        (run) =>
          ["queued", "leased", "running", "waiting_input", "waiting_takeover"].includes(
            run.status,
          ) &&
          ["user", "group"].includes(run.trigger) &&
          !run.parent_run_id &&
          !visible.has(run.id),
      )
      .flatMap((run) => {
        const input = canonical
          .filter(
            (row) =>
              row.thread_id === run.thread_id &&
              row.role === "user" &&
              (run.input_seq != null
                ? row.seq === run.input_seq
                : Date.parse(row.created_at) <= Date.parse(run.created_at)),
          )
          .sort((a, b) => b.seq - a.seq)[0];
        // Never attach an old/background run to a different owner's recent input.
        return input
          ? [
              {
                id: `activity:${run.id}`,
                thread_id: run.thread_id,
                agent_id: run.agent_id,
                seq: input.seq + 0.125,
                role: "assistant" as const,
                content: "",
                created_at: input.created_at,
                reply_to: null,
                attachment_ids: [],
              },
            ]
          : [];
      }),
  ].sort((a, b) => a.seq - b.seq || a.id.localeCompare(b.id));
}
