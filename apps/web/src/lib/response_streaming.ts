import type { Event, ReplyStreamSnapshot, Run } from "./api";

export const MAX_STREAM_CHARS = 60000;
const MAX_TAIL_CHUNKS = 150;
type Chunk = { sequence: number; text: string; truncated: boolean };
export type LiveReplyStream = ReplyStreamSnapshot & {
  run_id: string;
  thread_id: string;
  agent_id: string;
  cursor: number;
  gap: boolean;
  chunks: Chunk[];
};

function version(stream: Pick<ReplyStreamSnapshot, "fence" | "generation">) {
  return [stream.fence, stream.generation] as const;
}
function compareVersion(
  a: Pick<ReplyStreamSnapshot, "fence" | "generation">,
  b: Pick<ReplyStreamSnapshot, "fence" | "generation">,
) {
  const [af, ag] = version(a);
  const [bf, bg] = version(b);
  return af - bf || ag - bg;
}
function bounded(text: string) {
  // Count Unicode code points like Python's durable snapshot, keeping surrogate pairs intact.
  return Array.from(text).slice(0, MAX_STREAM_CHARS).join("");
}
function append(current: LiveReplyStream, chunk: Chunk): LiveReplyStream {
  if (chunk.sequence <= current.sequence) return current;
  const gap = current.gap || chunk.sequence !== current.sequence + 1;
  const text = gap ? current.text : bounded(current.text + chunk.text);
  return {
    ...current,
    sequence: chunk.sequence,
    text,
    gap,
    truncated: current.truncated || chunk.truncated,
    chunks: [...current.chunks, chunk].slice(-MAX_TAIL_CHUNKS),
  };
}

/** Every delivered delta updates this bounded accumulator before event-history eviction. */
export function accumulateStream(
  current: LiveReplyStream | undefined,
  event: Event,
): LiveReplyStream | undefined {
  if (!event.run_id) return current;
  if (event.kind === "run.cancelled" || event.kind === "run.failed") {
    return current
      ? {
          ...current,
          phase: event.kind === "run.failed" ? "failed" : "cancelled",
          cursor: event.cursor,
        }
      : undefined;
  }
  if (!["run.reply_started", "run.delta", "run.reply_committed"].includes(event.kind))
    return current;
  const payload = event.payload;
  const { turn_id, fence, generation, sequence } = payload;
  if (
    typeof turn_id !== "string" ||
    typeof fence !== "number" ||
    typeof generation !== "number" ||
    typeof sequence !== "number"
  )
    return current;
  const identity = {
    turn_id,
    fence,
    generation,
    sequence,
    ...(typeof payload.input_seq === "number" ? { input_seq: payload.input_seq } : {}),
  };
  if (current && compareVersion(current, identity) > 0) return current;
  const same =
    current?.turn_id === turn_id && current.fence === fence && current.generation === generation;
  let stream: LiveReplyStream = same
    ? current
    : {
        ...identity,
        sequence: 0,
        text: "",
        truncated: false,
        phase: "streaming",
        message_id: null,
        run_id: event.run_id,
        thread_id: event.thread_id ?? "",
        agent_id: event.agent_id ?? "",
        cursor: event.cursor,
        gap: false,
        chunks: [],
      };
  if (event.kind === "run.reply_started")
    return same ? stream : { ...stream, cursor: event.cursor };
  if (typeof payload.input_seq === "number") stream = { ...stream, input_seq: payload.input_seq };
  if (event.kind === "run.delta") {
    stream = append(stream, {
      sequence,
      text: typeof payload.text === "string" ? payload.text : "",
      truncated: payload.truncated === true,
    });
    return { ...stream, cursor: Math.max(stream.cursor, event.cursor) };
  }
  return {
    ...stream,
    sequence: Math.max(stream.sequence, sequence),
    phase: payload.phase === "discarded" ? "discarded" : "committed",
    message_id: typeof payload.message_id === "string" ? payload.message_id : null,
    cursor: event.cursor,
  };
}

/** Rebase on the committed DB preview, then apply only later contiguous chunks of that turn. */
export function seedStream(
  current: LiveReplyStream | undefined,
  run: Run,
): LiveReplyStream | undefined {
  const snapshot = run.stream;
  if (!snapshot) return current;
  if (current && compareVersion(current, snapshot) > 0) return current;
  const same = current?.turn_id === snapshot.turn_id && compareVersion(current, snapshot) === 0;
  if (same && current && !current.gap && current.sequence > snapshot.sequence) return current;
  let rebased: LiveReplyStream = {
    ...snapshot,
    run_id: run.id,
    thread_id: run.thread_id,
    agent_id: run.agent_id,
    cursor: current?.cursor ?? 0,
    gap: false,
    chunks: [],
  };
  if (same && current) {
    for (const chunk of current.chunks) rebased = append(rebased, chunk);
    if (current.sequence > rebased.sequence) rebased.gap = true;
    if (current.phase !== "streaming" && snapshot.phase === "streaming") {
      rebased.phase = current.phase;
      rebased.message_id = current.message_id;
    }
  }
  return rebased;
}

export function streamForRun(run: Run, live?: LiveReplyStream): ReplyStreamSnapshot | undefined {
  return seedStream(live, run);
}

/** Compatibility reader for older callers; new rendering uses the fenced durable preview. */
export function streamText(events: Event[], runId: string) {
  const local = events.filter((event) => event.run_id === runId);
  const start = [...local].reverse().find((event) => event.kind === "run.reply_started");
  return local
    .filter((event) => event.kind === "run.delta" && (!start || event.cursor > start.cursor))
    .map((event) => (typeof event.payload.text === "string" ? event.payload.text : ""))
    .join("");
}
