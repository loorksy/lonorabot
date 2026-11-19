import assert from "node:assert/strict";
import { test } from "node:test";
import type { InputRequest, Run } from "@lonora/contracts";
import { threadQuestions } from "../../packages/core/src/thread-questions";

const request = (id: string, message: string, thread?: string): InputRequest =>
  ({
    id,
    run_id: "run",
    message_id: message,
    ...(thread ? { thread_id: thread } : {}),
    question: "Hold the position?",
    choices: [],
    status: "pending",
    selected_choice_id: null,
    answer_message_id: null,
  }) as InputRequest;

const run = (thread: string, requests: InputRequest[]): Run =>
  ({ id: "run", thread_id: thread, input_requests: requests }) as unknown as Run;

test("a thread shows the questions held there, including a background run's copy", () => {
  // A background run in a hidden work thread asked in the conversation.
  const background = run("work", [request("q1", "copy", "conversation")]);
  const own = run("conversation", [request("q2", "own")]);
  const elsewhere = run("work", [request("q3", "hidden", "work")]);
  const shown = threadQuestions([background, own, elsewhere], "conversation");
  assert.deepEqual([...shown.keys()].sort(), ["copy", "own"]);
  // A stored request without a thread is in its run's own thread.
  assert.deepEqual([...threadQuestions([own], "conversation").keys()], ["own"]);
  assert.deepEqual([...threadQuestions([elsewhere], "work").keys()], ["hidden"]);
});

test("a later row replaces an earlier one for the same message", () => {
  const before = run("work", [request("q1", "copy", "conversation")]);
  const after = run("work", [{ ...request("q1", "copy", "conversation"), status: "answered" }]);
  assert.equal(threadQuestions([before, after], "conversation").get("copy")?.status, "answered");
});
