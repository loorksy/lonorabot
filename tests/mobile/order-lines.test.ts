// Order lines sit at their anchor in the conversation, as on Web; another chat's never show.
import assert from "node:assert/strict";
import test from "node:test";
import { withOrderLines } from "../../apps/mobile/lib/order-lines";
import type { Journal } from "../../packages/contracts/src";

const message = (seq: number, at: string) =>
  ({
    kind: "message",
    id: `m${seq}`,
    seq,
    message: { id: `m${seq}`, seq, created_at: at },
  }) as never;
const journal = (id: string, fields: Partial<Journal>) =>
  ({
    operation_id: id,
    account_id: "acc",
    status: "filled",
    request: {},
    result: {},
    submitted_at: null,
    updated_at: "2026-11-12T08:00:00Z",
    thread_id: "t",
    ...fields,
  }) as Journal;

test("an order line goes before the first message after its anchor, else by time, else last", () => {
  const items = [
    message(1, "2026-11-12T08:00:00Z"),
    message(2, "2026-11-12T08:05:00Z"),
    message(3, "2026-11-12T08:10:00Z"),
  ];
  const out = withOrderLines(
    items,
    [
      journal("anchored", { timeline_seq: 1 }),
      journal("timed", { submitted_at: "2026-11-12T08:07:00Z" }),
      journal("late", { timeline_seq: 9 }),
      journal("elsewhere", { thread_id: "other", timeline_seq: 1 }),
    ],
    "t",
  );
  assert.deepEqual(
    out.map((item) => item.id),
    ["m1", "order:anchored", "m2", "order:timed", "m3", "order:late"],
  );
});
