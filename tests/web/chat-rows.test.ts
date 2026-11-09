import assert from "node:assert/strict";
import test from "node:test";
import type { Agent, ChatList, InboxEntry, Resource } from "../../packages/contracts/src/domain";
import {
  archivedRowSummary,
  attentionAlwaysShows,
  chatRows,
  filterRows,
  groupDraftName,
  headsUpAllowed,
  isPlainOutgoing,
  pinsAfter,
  rowMarkedOnly,
  selectionSummary,
} from "../../packages/core/src/chat-rows";
import { foldSearch, highlightRange } from "../../packages/core/src/search-fold";

const at = (hour: number) => `2026-11-09T${String(hour).padStart(2, "0")}:00:00Z`;
const agent = (id: string, hour: number): Agent =>
  ({ id, name: `Agent ${id}`, title: `role ${id}`, paused: false, created_at: at(hour) }) as Agent;
const group = (id: string, hour: number, thread?: string): Resource => ({
  id,
  agent_id: null,
  thread_id: null,
  payload: { name: `Group ${id}`, purpose: `purpose ${id}`, member_ids: [] },
  state: thread ? { thread_id: thread } : {},
  version: 1,
  created_at: at(hour),
  updated_at: at(hour),
});
function entry(
  thread: string,
  owner: { agent?: string; group?: string },
  hour: number,
  extra: Partial<InboxEntry> = {},
): InboxEntry {
  return {
    thread_id: thread,
    agent_id: owner.agent ?? null,
    group_id: owner.group ?? null,
    last_message: null,
    last_activity_at: at(hour),
    unread_count: 0,
    last_read_seq: 0,
    marked_unread: false,
    muted: false,
    archived: false,
    favourite: false,
    pinned_order: null,
    hidden_before_seq: 0,
    ...extra,
  };
}

const agents = [agent("a", 1), agent("b", 1), agent("c", 1), agent("d", 1), agent("e", 1)];
const groups = [group("g", 1, "tg"), group("h", 1)];
const entries = [
  entry("ta", { agent: "a" }, 10, { unread_count: 2 }),
  entry("tb", { agent: "b" }, 12, { marked_unread: true, favourite: true }),
  entry("tc", { agent: "c" }, 8, { pinned_order: 2 }),
  entry("td", { agent: "d" }, 9, { pinned_order: 1, muted: true, unread_count: 4 }),
  entry("te", { agent: "e" }, 11, { archived: true, unread_count: 1 }),
  entry("tg", { group: "g" }, 7),
];
const rows = chatRows(agents, groups, entries);

test("every agent and group is a row: pins first in pin order, then the latest activity", () => {
  assert.deepEqual(
    rows.map((row) => row.key),
    ["agent:d", "agent:c", "agent:b", "agent:e", "agent:a", "group:g", "group:h"],
  );
  // A group with no conversation in the inbox still reaches its thread through its state.
  assert.equal(rows.find((row) => row.key === "group:g")?.threadId, "tg");
  assert.equal(rows.find((row) => row.key === "group:h")?.threadId, undefined);
  assert.equal(rows.find((row) => row.key === "group:g")?.subtitle, "purpose g");
});

test("filters: archived rows never show; unread counts the marked dot; lists by thread", () => {
  assert.ok(!filterRows(rows, "all").some((row) => row.key === "agent:e"));
  assert.deepEqual(
    filterRows(rows, "unread").map((row) => row.key),
    ["agent:d", "agent:b", "agent:a"],
  );
  assert.deepEqual(
    filterRows(rows, "fav").map((row) => row.key),
    ["agent:b"],
  );
  assert.deepEqual(
    filterRows(rows, "groups").map((row) => row.key),
    ["group:g", "group:h"],
  );
  const list = { id: "l1", name: "عمل", thread_ids: ["tg", "ta", "te"] } as ChatList;
  assert.deepEqual(
    filterRows(rows, "list:l1", [list]).map((row) => row.key),
    ["agent:a", "group:g"],
  );
  assert.equal(rowMarkedOnly(rows.find((row) => row.key === "agent:b")!), true);
});

test("the archived row counts archived conversations and their unread", () => {
  assert.deepEqual(archivedRowSummary(rows), { count: 1, unread: 1 });
});

test("selection: toolbar state, select-all, the pin limit and the group draft name", () => {
  const picked = rows.filter((row) => ["agent:c", "agent:d"].includes(row.key));
  const summary = selectionSummary(picked, ["agent:c", "agent:d"]);
  assert.equal(summary.allPinned, true);
  assert.equal(summary.allMuted, false);
  assert.equal(summary.anyUnread, true);
  assert.equal(summary.allVisiblePicked, true);
  assert.equal(
    pinsAfter(
      rows,
      rows.filter((row) => row.key === "agent:a"),
    ),
    3,
  );
  assert.equal(
    pinsAfter(
      rows,
      rows.filter((row) => ["agent:a", "agent:b"].includes(row.key)),
    ),
    4,
  );
  assert.equal(groupDraftName(["علي", "سارة", "منى", "خالد"]), "علي، سارة، منى");
});

test("Q6 and Q4: only plain messages flush; mute hides heads-ups, never urgent attention", () => {
  assert.equal(isPlainOutgoing({ content: "hi", client_nonce: "n" }), true);
  assert.equal(
    isPlainOutgoing({
      content: "",
      input_answer: { run_id: "r", question_id: "q", choice_id: "c" },
    }),
    false,
  );
  assert.equal(headsUpAllowed(entries[3]), false);
  assert.equal(headsUpAllowed(entries[4]), false);
  assert.equal(headsUpAllowed(entries[0]), true);
  assert.equal(attentionAlwaysShows("critical"), true);
  assert.equal(attentionAlwaysShows("action_required"), true);
  assert.equal(attentionAlwaysShows("informational"), false);
});

test("search folding matches the server's and highlights the original characters", () => {
  assert.equal(foldSearch("  الفِيدرالي   أسعار ـــ"), "الفيدرالي اسعار");
  assert.equal(foldSearch("مدرسة"), "مدرسه");
  const text = "🙂 قرار الفِيدرالي اليوم";
  const range = highlightRange(text, "الفيدرالي");
  assert.ok(range);
  assert.equal(text.slice(range[0], range[1]), "الفِيدرالي");
  assert.equal(highlightRange("Gold", "silver"), null);
});
