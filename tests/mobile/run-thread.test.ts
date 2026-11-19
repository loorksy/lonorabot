import assert from "node:assert/strict";
import { test } from "node:test";
import { reportThread } from "../../apps/mobile/lib/run-thread";

test("a run opens the conversation its output reaches, never a hidden work thread", () => {
  // A wake or Task working in a hidden thread reports to its origin conversation.
  assert.equal(
    reportThread({
      thread_id: "work",
      status: "completed",
      model_metadata: { origin_thread_id: "conversation" },
    }),
    "conversation",
  );
  // An owner's turn, or a run from before origins existed, opens its own thread.
  assert.equal(
    reportThread({ thread_id: "chat", status: "completed", model_metadata: {} }),
    "chat",
  );
  assert.equal(
    reportThread({
      thread_id: "old",
      status: "completed",
      model_metadata: { origin_thread_id: "" },
    }),
    "old",
  );
});

test("a run waiting for the owner's answer opens the thread that holds its question", () => {
  const waiting = (input_request: unknown) =>
    ({
      thread_id: "work",
      status: "waiting_input",
      model_metadata: { origin_thread_id: "conversation" },
      input_request,
    }) as Parameters<typeof reportThread>[0];
  // A background question is copied into the conversation it reports to.
  assert.equal(
    reportThread(waiting({ status: "pending", thread_id: "conversation" })),
    "conversation",
  );
  // A question asked before copies existed stays in the run's own thread.
  assert.equal(reportThread(waiting({ status: "pending" })), "work");
  // Waiting with no question (an approval): its card is in the conversation it reports to.
  assert.equal(reportThread(waiting(null)), "conversation");
});
