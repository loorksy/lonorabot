import assert from "node:assert/strict";
import { test } from "node:test";
import type { Message, OwnerAction, TradeApproval } from "@lonora/contracts";
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

/** A message whose card embeds a fixed card as a trusted slot (mandate 10.2). */
function slotting(seq: number, card: string, record: string, extra: object = {}): Message {
  return {
    ...message(`slot-${seq}`, seq, "2026-10-15T10:00:02Z"),
    rich_content: {
      version: 1,
      parts: [
        {
          type: "ui",
          document: {
            v: 2,
            kind: "receipt",
            title: "Waiting for you",
            icon: "check",
            facts: {},
            state: {},
            calc: {},
            blocks: [{ type: "Slot", card, record, ...extra }],
            fallback: "",
          },
        },
      ],
    } as Message["rich_content"],
  };
}

test("a fixed card's row is shown only while no message embeds its record as a slot", () => {
  const ids = (rows: ReturnType<typeof conversationTimeline>) => rows.map((row) => row.id);
  // No slot: the row is the card's place.
  assert.ok(ids(conversationTimeline(messages, [approval])).includes("approval:request"));
  // A message embeds the record: the slot is its place, the row is gone.
  const embedded = [...messages, slotting(3, "trade_approval", "request")];
  assert.ok(!ids(conversationTimeline(embedded, [approval])).includes("approval:request"));
  // The embedding message is gone (or never carried a valid slot): the row returns.
  assert.ok(ids(conversationTimeline(messages, [approval])).includes("approval:request"));
  const forged = [...messages, slotting(3, "trade_approval", "request", { when: "false" })];
  assert.ok(ids(conversationTimeline(forged, [approval])).includes("approval:request"));
  // An owner-action fixed card steps aside for a slot of its own card only.
  const mandate = {
    id: "mode-card",
    kind: "trading_mode",
    thread_id: "thread",
    created_at: "2026-10-15T10:00:01Z",
    timeline_seq: 2,
  } as unknown as OwnerAction;
  const withMandate = (rows: Message[]) => ids(conversationTimeline(rows, [], [mandate]));
  assert.ok(withMandate(messages).includes("owner_action:mode-card"));
  assert.ok(
    !withMandate([...messages, slotting(3, "mandate", "mode-card")]).includes(
      "owner_action:mode-card",
    ),
  );
  assert.ok(
    withMandate([...messages, slotting(3, "settle", "mode-card")]).includes(
      "owner_action:mode-card",
    ),
  );
  // A message the client draws as a question's or a peer's card never draws its slot, so
  // the row stays.
  const asked = slotting(3, "trade_approval", "request");
  assert.ok(
    ids(conversationTimeline([...messages, asked], [approval], [], new Set([asked.id]))).includes(
      "approval:request",
    ),
  );
  // A slot of another kind never hides the record.
  const other = [...messages, slotting(3, "settle", "request")];
  assert.ok(ids(conversationTimeline(other, [approval])).includes("approval:request"));
});
