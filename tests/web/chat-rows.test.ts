import assert from "node:assert/strict";
import test from "node:test";
import type {
  Agent,
  ChatList,
  InboxEntry,
  InboxLastMessage,
  Resource,
} from "../../packages/contracts/src/domain";
import type { RunStatus } from "../../packages/contracts/src/runs";
import {
  archivedRowSummary,
  attentionAlwaysShows,
  chatRows,
  filterRows,
  groupDraftName,
  headsUpAllowed,
  inQuietHours,
  isPlainOutgoing,
  mergeLiveMessage,
  pinsAfter,
  rowMarkedOnly,
  selectionSummary,
} from "../../packages/core/src/chat-rows";
import { retriedRunIds, stopTargets } from "../../packages/core/src/run-state";
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
    last_message: { created_at: at(hour), seq: hour } as InboxLastMessage,
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

test("a chat with no message sorts last; one written here moves up before the server answers", () => {
  const quiet = [
    entry("ta", { agent: "a" }, 10),
    entry("tb", { agent: "b" }, 3, { last_message: null }),
    entry("tc", { agent: "c" }, 9),
  ];
  // b's thread is newer than every message, but it has none to show: it stays below.
  assert.deepEqual(
    chatRows(agents.slice(0, 3), [], quiet).map((row) => row.key),
    ["agent:a", "agent:c", "agent:b"],
  );
  // The agents without a conversation keep the server's order after the chats with messages.
  assert.deepEqual(
    chatRows(agents, [], quiet.slice(0, 1)).map((row) => row.key),
    ["agent:a", "agent:b", "agent:c", "agent:d", "agent:e"],
  );
  // A message queued offline in c's chat (12:00) puts it on top.
  const outbox = (thread: string) => (thread === "tc" ? at(12) : undefined);
  assert.deepEqual(
    chatRows(agents.slice(0, 3), [], quiet, outbox).map((row) => row.key),
    ["agent:c", "agent:a", "agent:b"],
  );
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
  // GENUI_PLAN §8: a card submit never enters the auto-flushed outbox; nor does a voice note.
  assert.equal(isPlainOutgoing({ content: "x", ui_submit: { card_id: "c" } }), false);
  assert.equal(isPlainOutgoing({ content: "", voice: { artifact_id: "a" } }), false);
  assert.equal(isPlainOutgoing({ content: "x", edited_from: "m" }), false);
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

test("quiet hours: 22:00-08:00 in the owner's zone, crossing midnight; none set, none", () => {
  const night = { quiet_start_hour: 22, quiet_end_hour: 8, timezone: "Asia/Damascus" };
  // 20:30 UTC is 23:30 in Damascus (UTC+3); 06:00 UTC is 09:00 there.
  assert.equal(inQuietHours(night, new Date("2026-11-09T20:30:00Z")), true);
  assert.equal(inQuietHours(night, new Date("2026-11-09T04:59:00Z")), true);
  assert.equal(inQuietHours(night, new Date("2026-11-09T06:00:00Z")), false);
  const day = { quiet_start_hour: 13, quiet_end_hour: 15, timezone: "UTC" };
  assert.equal(inQuietHours(day, new Date("2026-11-09T14:00:00Z")), true);
  assert.equal(inQuietHours(day, new Date("2026-11-09T15:00:00Z")), false);
  assert.equal(
    inQuietHours({ quiet_start_hour: null, quiet_end_hour: null, timezone: "UTC" }, new Date()),
    false,
  );
  assert.equal(inQuietHours(null, new Date()), false);
});

test("Stop cancels every cancellable run of the thread, a queued card submit included", () => {
  const run = (id: string, status: RunStatus, thread_id = "t") => ({ id, status, thread_id });
  const targets = stopTargets(
    [
      run("a", "running"),
      run("b", "queued"),
      run("c", "waiting_input"),
      run("d", "completed"),
      run("e", "queued", "other"),
    ],
    "t",
  ).map((row) => row.id);
  assert.deepEqual(targets, ["a", "b", "c"]);
});

test("quiet hours to the minute (Q47): 22:30-07:15 wins over the whole hours", () => {
  const policy = {
    quiet_start_hour: 22,
    quiet_end_hour: 7,
    quiet_start_minute: 22 * 60 + 30,
    quiet_end_minute: 7 * 60 + 15,
    timezone: "UTC",
  };
  assert.equal(inQuietHours(policy, new Date("2026-11-09T22:29:00Z")), false);
  assert.equal(inQuietHours(policy, new Date("2026-11-09T22:30:00Z")), true);
  assert.equal(inQuietHours(policy, new Date("2026-11-10T07:14:00Z")), true);
  assert.equal(inQuietHours(policy, new Date("2026-11-10T07:15:00Z")), false);
});

test("M2(d): a retried reply's error card settles; it never offers a second Retry", () => {
  const ids = retriedRunIds([
    { model_metadata: { retry_of: "failed-1" } },
    { model_metadata: {} },
    { model_metadata: null },
  ]);
  assert.deepEqual([...ids], ["failed-1"]);
});

test("M7: a late message.created never overwrites what the refetch already knows", () => {
  const read = {
    id: "m",
    thread_id: "t",
    seq: 3,
    role: "user",
    content: "اشترِ",
    attachment_ids: [],
    created_at: "2026-11-10T08:00:00Z",
    superseded_by: "m2",
    consumed: true,
    reactions: [{ emoji: "👍", by: "owner" }],
  } as unknown as Parameters<typeof mergeLiveMessage>[0];
  const created = { ...read, superseded_by: null, reactions: [] } as Record<string, unknown>;
  delete created.consumed;
  const merged = mergeLiveMessage(read, "message.created", created);
  assert.equal(merged.superseded_by, "m2");
  assert.equal((merged as { consumed?: boolean }).consumed, true);
  assert.equal((merged as { reactions?: unknown[] }).reactions?.length, 1);
  // A message.updated is the newer projection.
  const updated = mergeLiveMessage(read, "message.updated", { ...created, superseded_by: "m3" });
  assert.equal(updated.superseded_by, "m3");
});

test("a direct chat offers every other agent as a guest, however many are named", async () => {
  const { guestCandidates } = await import("../../packages/core/src/composer-mentions");
  const named = (id: string) => ({ id, name: id, paused: false }) as unknown as Agent;
  const pool = [named("a"), named("b"), named("c")];
  assert.deepEqual(
    guestCandidates(pool, [{ agent_id: "a" }], true).map((row) => row.id),
    ["a", "b", "c"],
  );
  assert.deepEqual(
    guestCandidates(pool, [{ agent_id: "a" }, { agent_id: "b" }], true).map((row) => row.id),
    ["a", "b", "c"],
  );
  assert.equal(guestCandidates(pool, [{ agent_id: "a" }, { agent_id: "b" }], false).length, 3);
});
