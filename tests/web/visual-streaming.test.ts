import assert from "node:assert/strict";
import test from "node:test";
import type { Event, Payload, ReplyStreamSnapshot, RichContent, Run } from "@lonora/contracts";
import { accumulateStream, seedStream } from "../../apps/web/src/lib/response_streaming";

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
function event(kind: string, sequence: number, payload: Record<string, unknown> = {}): Event {
  return {
    cursor: sequence + 1,
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

test("native composition is atomic: deltas cannot publish it, only a valid final commit", () => {
  let stream = accumulateStream(undefined, event("run.reply_started", 0, { rich_content: rich }));
  assert.equal(stream?.rich_content, undefined);
  stream = accumulateStream(
    stream,
    event("run.delta", 1, { text: "Illustration.", rich_content: rich }),
  );
  assert.equal(stream?.rich_content, undefined);
  assert.equal(stream?.text, "Illustration.");
  stream = accumulateStream(
    stream,
    event("run.reply_committed", 1, { message_id: "message", rich_content: rich }),
  );
  assert.equal(stream?.phase, "committed");
  assert.deepEqual(stream?.rich_content, rich);
  const next = accumulateStream(stream, event("run.reply_started", 0, { generation: 2 }));
  assert.equal(next?.phase, "streaming");
  assert.equal(next?.rich_content, undefined);
  assert.equal(next?.text, "");
  const stale = accumulateStream(
    next,
    event("run.reply_committed", 2, { message_id: "old", rich_content: rich }),
  );
  assert.deepEqual(stale, next);
});

test("discarded, failed and malformed compositions never reach the rich renderer", () => {
  const started = accumulateStream(undefined, event("run.reply_started", 0));
  const committed = accumulateStream(
    started,
    event("run.reply_committed", 0, { message_id: "message", rich_content: rich }),
  );
  assert.equal(accumulateStream(committed, event("run.failed", 1))?.rich_content, null);
  assert.equal(accumulateStream(committed, event("run.cancelled", 1))?.rich_content, null);
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

test("reopening validates committed composition and refuses premature or stale snapshots", () => {
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
  assert.equal(seedStream(undefined, run({ ...snapshot, phase: "streaming" }))?.rich_content, null);
  const stale = seedStream(reopened, run({ ...snapshot, phase: "streaming", rich_content: null }));
  assert.deepEqual(stale?.rich_content, rich);
  assert.equal(stale?.phase, "committed");
});
