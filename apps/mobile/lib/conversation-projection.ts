import type { Message, Run } from "@lonora/contracts";
import { type LiveReplyStream, streamForRun } from "@lonora/core";

/** Current response belongs at its actual input, not a detached list footer. */
export function projectConversation(
  messages: Message[],
  runs: Run[],
  streams: Record<string, LiveReplyStream>,
): Message[] {
  const canonical = messages.filter((row) => !row.id.startsWith("pending:"));
  const last = Math.max(0, ...canonical.map((row) => row.seq));
  const rows = [
    ...canonical,
    ...messages
      .filter((row) => row.id.startsWith("pending:"))
      .map((row, index) => ({
        ...row,
        seq: last + (index + 1) / (messages.length + 1),
      })),
  ];
  const minimum = canonical.length ? Math.min(...canonical.map((row) => row.seq)) : 0;
  for (const run of runs) {
    const stream = streamForRun(run, streams[run.id]);
    if (stream?.message_id && canonical.some((message) => message.id === stream.message_id))
      continue;
    const active = ["queued", "leased", "running", "waiting_input", "waiting_takeover"].includes(
      run.status,
    );
    const visible =
      stream &&
      ["streaming", "committed", "cancelled", "failed"].includes(stream.phase) &&
      Boolean(stream.text || stream.rich_content?.parts.length);
    if (!active && !visible) continue;
    const inputSeq = stream?.input_seq ?? run.input_seq;
    const input = canonical
      .filter(
        (row) =>
          row.thread_id === run.thread_id &&
          row.role === "user" &&
          (inputSeq != null
            ? row.seq === inputSeq
            : Date.parse(row.created_at) <= Date.parse(run.created_at)),
      )
      .sort((a, b) => b.seq - a.seq)[0];
    if (!visible && (!input || !["user", "group"].includes(run.trigger) || run.parent_run_id))
      continue;
    const anchor =
      inputSeq ??
      input?.seq ??
      Math.max(
        0,
        ...canonical
          .filter(
            (row) =>
              row.role === "user" && Date.parse(row.created_at) <= Date.parse(run.created_at),
          )
          .map((row) => row.seq),
      );
    if (anchor < minimum) continue;
    rows.push({
      id: `preview:${run.id}`,
      thread_id: run.thread_id,
      agent_id: run.agent_id,
      seq: anchor + 0.125,
      role: "assistant",
      content: visible ? stream.text : "",
      rich_content: visible ? stream.rich_content : null,
      created_at: canonical.find((row) => row.seq === anchor)?.created_at ?? run.created_at,
      reply_to: null,
      attachment_ids: [],
    });
  }
  return rows.sort((a, b) => a.seq - b.seq || a.id.localeCompare(b.id));
}
