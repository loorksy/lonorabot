import assert from "node:assert/strict";
import { test } from "node:test";
import { reportThread } from "../../apps/mobile/lib/run-thread";

test("a run opens the conversation its output reaches, never a hidden work thread", () => {
  // A wake or Task working in a hidden thread reports to its origin conversation.
  assert.equal(
    reportThread({ thread_id: "work", model_metadata: { origin_thread_id: "conversation" } }),
    "conversation",
  );
  // An owner's turn, or a run from before origins existed, opens its own thread.
  assert.equal(reportThread({ thread_id: "chat", model_metadata: {} }), "chat");
  assert.equal(reportThread({ thread_id: "old", model_metadata: { origin_thread_id: "" } }), "old");
});
