import assert from "node:assert/strict";
import { test } from "node:test";
import { reportThread } from "../../apps/mobile/lib/run-thread";

test("a wake opens the conversation it reports to, never its hidden work thread", () => {
  const wake = (trigger: string) => ({
    thread_id: "work",
    trigger,
    model_metadata: { origin_thread_id: "conversation" },
  });
  for (const trigger of ["routine", "watch", "broker_event", "follow_up"]) {
    assert.equal(reportThread(wake(trigger)), "conversation");
  }
  // A Task's run opens its own transcript; an owner's turn opens its own conversation.
  assert.equal(reportThread(wake("tickets")), "work");
  assert.equal(reportThread({ thread_id: "chat", trigger: "user", model_metadata: {} }), "chat");
  // A wake from before origins existed keeps its own thread.
  assert.equal(reportThread({ thread_id: "old", trigger: "routine", model_metadata: {} }), "old");
});
