import assert from "node:assert/strict";
import test from "node:test";
import type { InboxEntry } from "../../packages/contracts/src/domain";
import {
  archivedSummary,
  inboxUnread,
  orderInbox,
  unreadBadgeTotal,
} from "../../packages/core/src/inbox";

function entry(thread_id: string, at: string, overrides: Partial<InboxEntry> = {}): InboxEntry {
  return {
    thread_id,
    agent_id: `agent-${thread_id}`,
    group_id: null,
    last_message: null,
    last_activity_at: at,
    unread_count: 0,
    last_read_seq: 0,
    marked_unread: false,
    muted: false,
    archived: false,
    favourite: false,
    pinned_order: null,
    hidden_before_seq: 0,
    ...overrides,
  };
}

const entries = [
  entry("a", "2026-11-09T10:00:00Z", { unread_count: 3 }),
  entry("b", "2026-11-09T12:00:00Z", { marked_unread: true }),
  entry("c", "2026-11-09T08:00:00Z", { pinned_order: 2, unread_count: 1 }),
  entry("d", "2026-11-09T09:00:00Z", { pinned_order: 1, muted: true, unread_count: 5 }),
  entry("e", "2026-11-09T11:00:00Z", { archived: true, unread_count: 2 }),
  entry("f", "2026-11-09T07:00:00Z", { archived: true }),
];

test("a marked-unread row counts as one; the badge skips archived and muted", () => {
  assert.equal(inboxUnread(entries[1]), 1);
  assert.equal(inboxUnread(entries[0]), 3);
  // a (3) + b (1) + c (1); d is muted, e is archived.
  assert.equal(unreadBadgeTotal(entries), 5);
});

test("the archived row shows the archived count and how many of them are unread", () => {
  assert.deepEqual(archivedSummary(entries), { count: 2, unread: 1 });
});

test("pinned rows lead in pin order, then the latest activity", () => {
  const main = orderInbox(entries.filter((item) => !item.archived));
  assert.deepEqual(
    main.map((item) => item.thread_id),
    ["d", "c", "b", "a"],
  );
  const archived = orderInbox(entries.filter((item) => item.archived));
  assert.deepEqual(
    archived.map((item) => item.thread_id),
    ["e", "f"],
  );
});
