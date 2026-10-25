import assert from "node:assert/strict";
import test from "node:test";
import type { Message, Run } from "../../apps/web/src/lib/api";
import { failedReplies } from "../../apps/web/src/lib/failed-replies";

const input = (seq: number, thread = "thread") =>
  ({
    id: `input:${seq}`,
    thread_id: thread,
    seq,
    role: "user",
    created_at: "2026-10-25T10:00:00Z",
  }) as Message;
const run = {
  id: "failed",
  thread_id: "thread",
  input_seq: 10,
  trigger: "user",
  status: "failed",
  parent_run_id: null,
  created_at: "2026-10-25T10:00:01Z",
  error_code: "public_reply_unavailable",
} as Run;

test("a failed reply is attached to its own owner input, not a later message", () => {
  const rows = failedReplies([run], [input(10), input(11)]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].message.id, "input:10");
});
test("background, child and cancelled work does not become an owner reply failure", () => {
  for (const changed of [
    { trigger: "routine" },
    { trigger: "watch" },
    { trigger: "peer" },
    { parent_run_id: "parent" },
    { status: "cancelled" },
    { status: "completed" },
  ])
    assert.equal(failedReplies([{ ...run, ...changed } as Run], [input(10)]).length, 0);
});
test("failures outside the loaded history and other threads cannot reappear at the footer", () => {
  assert.equal(failedReplies([run], [input(11)]).length, 0);
  assert.equal(failedReplies([run], [input(10, "elsewhere")]).length, 0);
  assert.equal(failedReplies([run], [{ ...input(10), id: "pending:input" }]).length, 0);
});
