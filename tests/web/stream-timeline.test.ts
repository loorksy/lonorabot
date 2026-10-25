import assert from "node:assert/strict";
import test from "node:test";
import type { Message, ReplyStreamSnapshot, Run } from "../../apps/web/src/lib/api";
import { streamTimeline, streamVisible } from "../../apps/web/src/lib/stream-timeline";

const message = (id: string, seq: number) =>
  ({ id, seq, role: "user", created_at: "2026-10-25T10:00:00Z" }) as Message;
const run = { id: "r", input_seq: 10, created_at: "2026-10-25T10:00:01Z" } as Run;
const stream = { text: "Live answer", phase: "streaming", message_id: null } as ReplyStreamSnapshot;
test("preview stays after its own input and before later messages", () => {
  assert.deepEqual(
    streamTimeline([message("input", 10), message("later", 11)], [{ run, stream }]).map(
      (m) => m.id,
    ),
    ["input", "preview:r", "later"],
  );
});
test("old committed previews outside the history window cannot reappear", () => {
  assert.equal(
    streamVisible(run, { ...stream, phase: "committed", message_id: "old-answer" }, [
      message("recent", 100),
    ]),
    false,
  );
  assert.equal(streamVisible(run, { ...stream, phase: "committed" }, []), false);
});
test("canonical acknowledgement replaces preview exactly once", () => {
  const committed = { ...stream, phase: "committed" as const, message_id: "answer" };
  assert.deepEqual(
    streamTimeline(
      [message("input", 10), { ...message("answer", 11), role: "assistant" }],
      [{ run, stream: committed }],
    ).map((m) => m.id),
    ["input", "answer"],
  );
});
