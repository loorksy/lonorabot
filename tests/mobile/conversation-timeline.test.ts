import assert from "node:assert/strict";
import { test } from "node:test";
import type { Message, SuperBotRequest, TradeApproval } from "@lonora/contracts";
import { conversationTimeline } from "../../packages/core/src/conversation-timeline";

function message(id: string, seq: number, created_at: string): Message {
  return {
    id,
    seq,
    created_at,
    thread_id: "thread",
    agent_id: "agent",
    role: "assistant",
    content: id,
    attachment_ids: [],
    reply_to: null,
  };
}
const approval: TradeApproval = {
  id: "request",
  run_id: "run",
  thread_id: "thread",
  agent_id: "agent",
  timeline_seq: 2,
  created_at: "2026-10-15T10:00:01Z",
  status: "pending",
  requests: [],
  results: [],
};
const messages = [
  message("before", 1, "2026-10-15T10:00:00Z"),
  message("after", 2, "2026-10-15T10:00:01Z"),
];

test("approval retains server sequence position through decision, receipt and reconnect", () => {
  for (const status of ["pending", "approved", "completed", "rejected", "cancelled"] as const) {
    const rows = conversationTimeline(messages.toReversed(), [{ ...approval, status }]);
    assert.deepEqual(
      rows.map((row) => row.id),
      ["message:before", "approval:request", "message:after"],
    );
  }
});
test("durable anchor wins over clock ordering; repeated snapshots do not duplicate cards", () => {
  const row = { ...approval, created_at: "2026-10-16T12:00:00Z" };
  assert.deepEqual(
    conversationTimeline([...messages, messages[1]], [row, row]).map((row) => row.id),
    ["message:before", "approval:request", "message:after"],
  );
});
test("legacy approvals use persisted time; equal anchor requests sort deterministically", () => {
  const legacy = { ...approval, timeline_seq: null };
  const second = { ...legacy, id: "z-request" };
  assert.deepEqual(
    conversationTimeline(messages, [second, legacy]).map((row) => row.id),
    ["message:before", "approval:request", "approval:z-request", "message:after"],
  );
});
test("approval anchors survive older history pagination", () => {
  const older = message("oldest", 0, "2026-10-15T09:00:00Z");
  assert.deepEqual(
    conversationTimeline([older, ...messages], [approval]).map((row) => row.id),
    ["message:oldest", "message:before", "approval:request", "message:after"],
  );
});

const superBot = {
  id: "activation",
  agent_id: "agent",
  thread_id: "thread",
  goal_id: "goal",
  mode: "supervised",
  status: "pending",
  timeline_seq: 2,
  created_at: "2026-10-15T10:00:00.500Z",
  expires_at: "2026-10-15T10:10:00.500Z",
} as SuperBotRequest;
test("Super Bot remains between causal messages across status updates and history pagination", () => {
  for (const status of [
    "pending",
    "activated",
    "paused",
    "disabled",
    "rejected",
    "expired",
  ] as const) {
    const rows = conversationTimeline(messages.toReversed(), [], [{ ...superBot, status }]);
    assert.deepEqual(
      rows.map((row) => row.id),
      ["message:before", "super_bot:activation", "message:after"],
    );
  }
  const rows = conversationTimeline(
    [message("oldest", 0, "2026-10-14T09:00:00Z"), ...messages],
    [],
    [superBot, superBot],
  );
  assert.equal(rows.filter((row) => row.kind === "super_bot").length, 1);
  assert.equal(rows[2].id, "super_bot:activation");
});
test("mixed financial approvals and Super Bot cards retain independent exact anchors", () => {
  const rows = conversationTimeline(messages, [approval], [superBot]);
  assert.deepEqual(
    rows.map((row) => row.id),
    ["message:before", "approval:request", "super_bot:activation", "message:after"],
  );
});
