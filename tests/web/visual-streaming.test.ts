import assert from "node:assert/strict";
import test from "node:test";
import type { Event, Payload, ReplyStreamSnapshot, RichContent, Run } from "@lonora/contracts";
import { accumulateStream, seedStream } from "../../packages/core/src/reply-stream";

const rich: RichContent = {
  version: 1,
  parts: [
    { type: "text", text: "Illustration." },
    {
      type: "ui",
      document: {
        version: 1,
        mode: "example",
        root: { id: "value", type: "metric", label: "Illustrative value", value: 5 },
      },
    },
  ],
};
function event(
  kind: string,
  sequence: number,
  payload: Record<string, unknown> = {},
  cursor = sequence + 1,
): Event {
  return {
    cursor,
    kind,
    thread_id: "thread",
    agent_id: "agent",
    run_id: "run",
    created_at: "2026-10-25T10:00:00Z",
    payload: {
      turn_id: "turn",
      fence: 1,
      generation: 1,
      sequence,
      ...payload,
    } as Payload,
  };
}
function run(stream: ReplyStreamSnapshot): Run {
  return {
    id: "run",
    thread_id: "thread",
    agent_id: "agent",
    parent_run_id: null,
    status: "completed",
    trigger: "message",
    error_code: null,
    result: "Illustration.",
    model_metadata: {},
    created_at: "2026-10-25T10:00:00Z",
    updated_at: "2026-10-25T10:00:00Z",
    stream,
  };
}

test("only complete validated compositions stream, then the canonical commit replaces the preview", () => {
  let stream = accumulateStream(undefined, event("run.reply_started", 0, { rich_content: rich }));
  assert.equal(stream?.rich_content, undefined);
  stream = accumulateStream(
    stream,
    event("run.delta", 1, { text: "Illustration.", rich_content: rich }),
  );
  assert.deepEqual(stream?.rich_content, rich);
  assert.equal(stream?.text, "Illustration.");
  stream = accumulateStream(
    stream,
    event("run.reply_committed", 1, { message_id: "message", rich_content: rich }),
  );
  assert.equal(stream?.phase, "committed");
  assert.deepEqual(stream?.rich_content, rich);
  const next = accumulateStream(stream, event("run.reply_started", 0, { generation: 2 }, 4));
  assert.equal(next?.phase, "streaming");
  assert.equal(next?.rich_content, undefined);
  assert.equal(next?.text, "");
  const stale = accumulateStream(
    next,
    event("run.reply_committed", 2, { message_id: "old", rich_content: rich }),
  );
  assert.deepEqual(stale, next);
});

test("cancellation retains accepted content, discard clears it, and malformed compositions fail closed", () => {
  const started = accumulateStream(undefined, event("run.reply_started", 0));
  const committed = accumulateStream(
    started,
    event("run.reply_committed", 0, { message_id: "message", rich_content: rich }),
  );
  const failed = accumulateStream(committed, event("run.failed", 1));
  assert.equal(failed?.phase, "failed");
  assert.deepEqual(failed?.rich_content, rich);
  const cancelled = accumulateStream(committed, event("run.cancelled", 1));
  assert.equal(cancelled?.phase, "cancelled");
  assert.deepEqual(cancelled?.rich_content, rich);
  assert.equal(
    accumulateStream(
      started,
      event("run.reply_committed", 0, { phase: "discarded", rich_content: rich }),
    )?.rich_content,
    null,
  );
  assert.equal(
    accumulateStream(
      started,
      event("run.reply_committed", 0, {
        rich_content: { version: 1, parts: [{ type: "script" }] },
      }),
    )?.rich_content,
    null,
  );
});

test("reopening validates durable partial frames and refuses stale snapshots", () => {
  const snapshot: ReplyStreamSnapshot = {
    turn_id: "turn",
    fence: 1,
    generation: 1,
    sequence: 1,
    text: "Illustration.",
    truncated: false,
    phase: "committed",
    message_id: "message",
    rich_content: rich,
  };
  const reopened = seedStream(undefined, run(snapshot));
  assert.deepEqual(reopened?.rich_content, rich);
  assert.deepEqual(
    seedStream(undefined, run({ ...snapshot, phase: "streaming" }))?.rich_content,
    rich,
  );
  const stale = seedStream(reopened, run({ ...snapshot, phase: "streaming", rich_content: null }));
  assert.deepEqual(stale?.rich_content, rich);
  assert.equal(stale?.phase, "committed");
});

test("rich-only updates share the ordered sequence and a text gap is repaired by a durable snapshot", () => {
  let stream = accumulateStream(undefined, event("run.reply_started", 0));
  stream = accumulateStream(stream, event("run.delta", 1, { text: "First. " }));
  stream = accumulateStream(stream, event("run.rich_partial", 2, { rich_content: rich }));
  assert.equal(stream?.sequence, 2);
  assert.equal(stream?.text, "First. ");
  assert.deepEqual(stream?.rich_content, rich);
  const duplicate = accumulateStream(stream, event("run.rich_partial", 2, { rich_content: rich }));
  assert.equal(duplicate?.sequence, 2);
  assert.equal(duplicate?.chunks.length, 2);
  stream = accumulateStream(stream, event("run.delta", 4, { text: "Fourth." }));
  assert.equal(stream?.gap, true);
  assert.equal(stream?.text, "First. ");
  assert.ok(stream);
  const recovered = seedStream(
    stream,
    run({
      ...stream,
      sequence: 3,
      text: "First. Third. ",
      phase: "streaming",
    }),
  );
  assert.equal(recovered?.text, "First. Third. Fourth.");
  assert.equal(recovered?.sequence, 4);
  assert.equal(recovered?.gap, false);
  assert.deepEqual(recovered?.rich_content, rich);
});

test("interruption is terminal for its generation and stale commits cannot replace newer content", () => {
  let stream = accumulateStream(undefined, event("run.reply_started", 0));
  stream = accumulateStream(
    stream,
    event("run.delta", 1, { text: "Accepted. ", rich_content: rich }),
  );
  const interrupted = accumulateStream(stream, event("run.cancelled", 2));
  assert.equal(interrupted?.phase, "cancelled");
  assert.deepEqual(
    accumulateStream(interrupted, event("run.reply_committed", 3, { message_id: "late" })),
    interrupted,
  );
  const resumed = accumulateStream(
    interrupted,
    event(
      "run.reply_started",
      0,
      {
        fence: 2,
        generation: 1,
        input_seq: 8,
      },
      5,
    ),
  );
  assert.equal(resumed?.phase, "streaming");
  assert.equal(resumed?.text, "");
  assert.equal(resumed?.input_seq, 8);
  assert.equal(resumed?.rich_content, undefined);
  const first = accumulateStream(undefined, event("run.delta", 1, { text: "First. " }));
  const third = accumulateStream(first, event("run.delta", 2, { text: "Second." }));
  assert.deepEqual(
    accumulateStream(third, event("run.reply_committed", 1, { message_id: "stale" })),
    third,
  );
});

test("invalid partial trees do not replace a prior validated preview or expose raw protocol", () => {
  let stream = accumulateStream(
    undefined,
    event("run.delta", 1, { text: "Safe.", rich_content: rich }),
  );
  stream = accumulateStream(
    stream,
    event("run.rich_partial", 2, {
      rich_content: {
        version: 1,
        parts: [
          {
            type: "ui",
            document: {
              version: 1,
              mode: "example",
              root: { id: "script", type: "script", text: "execute()" },
            },
          },
        ],
      },
    }),
  );
  assert.deepEqual(stream?.rich_content, rich);
  assert.equal(stream?.text, "Safe.");
  assert.equal(stream?.sequence, 2);
});

test("cumulative rich previews keep one recovery tree instead of a full tree per token", () => {
  let stream = accumulateStream(undefined, event("run.reply_started", 0));
  for (let sequence = 1; sequence <= 200; sequence++)
    stream = accumulateStream(
      stream,
      event("run.delta", sequence, { text: "x", rich_content: rich }),
    );
  assert.equal(stream?.text.length, 200);
  assert.equal(stream?.chunks.length, 150);
  assert.equal(stream?.chunks.filter((chunk) => chunk.rich_content).length, 1);
  assert.deepEqual(stream?.rich_content, rich);
});
