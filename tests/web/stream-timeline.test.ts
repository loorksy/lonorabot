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

test("a new generation uses its own server anchor despite a stale Run snapshot", () => {
  const reply = { ...stream, input_seq: 11 };
  assert.deepEqual(
    streamTimeline(
      [message("input", 10), message("followup", 11)],
      [{ run: { ...run, input_seq: 1 }, stream: reply }],
    ).map((m) => m.id),
    ["input", "followup", "preview:r"],
  );
});

test("actual queued activity stays after its own input instead of a detached footer", async () => {
  const { activityTimeline } = await import("../../apps/web/src/lib/stream-timeline");
  const input = { ...message("input", 10), thread_id: "thread" };
  const later = { ...message("later", 11), thread_id: "thread" };
  const queued = {
    ...run,
    thread_id: "thread",
    status: "queued",
    trigger: "user",
    parent_run_id: null,
  } as Run;
  assert.deepEqual(
    activityTimeline([input, later], [queued], []).map((row) => row.id),
    ["input", "activity:r", "later"],
  );
  assert.deepEqual(
    activityTimeline([input, later], [queued], [{ run: queued, stream }]).map((row) => row.id),
    ["input", "preview:r", "later"],
  );
  assert.deepEqual(
    activityTimeline([input], [{ ...queued, trigger: "routine" }], []).map((row) => row.id),
    ["input"],
  );
});
