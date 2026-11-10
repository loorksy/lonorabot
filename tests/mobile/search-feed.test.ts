import assert from "node:assert/strict";
import test from "node:test";
import type { InboxEntry, SearchCategory, SearchResponse } from "../../packages/contracts/src";
import { mergePrefs } from "../../packages/core/src/inbox";
import {
  firstSearchPage,
  moreSearchItems,
  SEARCH_PAGE,
  searchPath,
} from "../../packages/core/src/search-feed";

const hit = (category: SearchCategory, id: string) => ({
  category,
  id,
  title: id,
  snippet: id,
  created_at: null,
});
const fake =
  (calls: string[]) =>
  async (
    q: string,
    category: SearchCategory | null,
    limit: number,
    offset: number,
  ): Promise<SearchResponse> => {
    calls.push(searchPath(q, category, limit, offset));
    const results: SearchResponse["results"] = {};
    const counts: SearchResponse["counts"] = {};
    for (const name of (category
      ? [category]
      : ["chats", "messages", "knowledge"]) as SearchCategory[]) {
      results[name] = [hit(name, `${name}-${offset}`)];
      counts[name] = 40;
    }
    return { q, category, limit, offset, counts, results };
  };

test("the all tab asks once, a few of each; browsing asks for four", async () => {
  const calls: string[] = [];
  const sections = await firstSearchPage("", "all", fake(calls));
  assert.deepEqual(calls, ["/search?q=&limit=4&offset=0"]);
  assert.deepEqual(
    sections.map((section) => section.tab),
    ["chats", "messages", "tasks", "files", "other"],
  );
  assert.equal(sections[0].count, 40);
  const searched: string[] = [];
  await firstSearchPage("gold", "all", fake(searched));
  assert.deepEqual(searched, ["/search?q=gold&limit=3&offset=0"]);
});

test("the knowledge and skills tab merges two categories and pages by 32", async () => {
  const calls: string[] = [];
  const [section] = await firstSearchPage("x", "other", fake(calls));
  assert.deepEqual(calls, [
    `/search?q=x&limit=${SEARCH_PAGE}&offset=0&category=knowledge`,
    `/search?q=x&limit=${SEARCH_PAGE}&offset=0&category=skills`,
  ]);
  assert.equal(section.count, 80);
  const more: string[] = [];
  const next = await moreSearchItems("x", section, fake(more));
  assert.ok(more.every((call) => call.includes("offset=1")));
  assert.equal(next.items.length, section.items.length + 2);
});

test("a preference answer is merged into the inbox entry", () => {
  const base: InboxEntry = {
    thread_id: "t1",
    agent_id: "a1",
    group_id: null,
    last_message: {
      id: "m",
      role: "assistant",
      agent_id: "a1",
      content: "hi",
      created_at: "2026-01-01T00:00:00Z",
      seq: 5,
      kind: "text",
      preview: "hi",
      attachments: { count: 0, kinds: [] },
      consumed: null,
    },
    last_activity_at: "2026-01-01T00:00:00Z",
    unread_count: 3,
    last_read_seq: 0,
    marked_unread: false,
    muted: false,
    archived: false,
    favourite: false,
    pinned_order: null,
    hidden_before_seq: 0,
  };
  const prefs = (patch: Record<string, unknown>) => ({
    thread_id: "t1",
    last_read_seq: 0,
    marked_unread: false,
    muted: false,
    archived: false,
    favourite: false,
    pinned_order: null,
    hidden_before_seq: 0,
    updated_at: null,
    ...patch,
  });
  assert.equal(mergePrefs([base], [prefs({ muted: true })])[0].muted, true);
  assert.equal(mergePrefs([base], [prefs({ last_read_seq: 5 })])[0].unread_count, 0);
  const cleared = mergePrefs([base], [prefs({ hidden_before_seq: 5 })])[0];
  assert.equal(cleared.last_message, null);
  assert.equal(cleared.unread_count, 0);
  assert.equal(mergePrefs([base], [prefs({ thread_id: "other" })])[0], base);
});
