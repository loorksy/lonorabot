import assert from "node:assert/strict";
import { test } from "node:test";
import type { ExecutionReceipt, Message, TradeApproval } from "@lonora/contracts";
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
test("an Execution Receipt sits where the broker confirmed it, once, on web and mobile alike", () => {
  const receipt: ExecutionReceipt = {
    operation_id: "op",
    thread_id: "thread",
    timeline_seq: 2,
    agent_id: "agent",
    created_at: "2026-10-15T10:00:01Z",
    kind: "fill",
    action: "buy",
    symbol: "XAUUSD",
    ticket: "1001",
    volume: "0.1",
    price: "2400.5",
    reason: null,
    verification: "pending",
  };
  assert.deepEqual(
    conversationTimeline(messages, [approval], [], [receipt, { ...receipt }]).map((row) => row.id),
    ["message:before", "approval:request", "receipt:op", "message:after"],
  );
  // A receipt without an anchor follows the clock, before the next message.
  const unanchored = { ...receipt, timeline_seq: null };
  assert.deepEqual(
    conversationTimeline(messages, [], [], [unanchored]).map((row) => row.id),
    ["message:before", "receipt:op", "message:after"],
  );
});
