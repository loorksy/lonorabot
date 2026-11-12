import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  guestCandidates,
  mentionAddress,
  rebaseMentions,
} from "../../packages/core/src/composer-mentions";

test("committed all keeps its original session despite newer collaboration discovery", () => {
  const range = { agent_id: null, session_id: "original-session", token: "@all", start: 0, end: 4 };
  const next = rebaseMentions("@all", "@all inspect evidence", [range]);
  assert.deepEqual(mentionAddress("@all inspect evidence", next), {
    agent_ids: [],
    all: true,
    collaboration_session_id: "original-session",
  });
});

test("editing a committed token removes its broadcast identity", () => {
  const ranges = rebaseMentions("@all", "@alex", [
    { agent_id: null, session_id: "original", token: "@all", start: 0, end: 4 },
  ]);
  assert.equal(mentionAddress("@alex", ranges).all, false);
  assert.equal(mentionAddress("@alex", ranges).collaboration_session_id, undefined);
});

test("item 25: a direct chat offers every other agent as a guest, never its own agent", () => {
  const agent = (id: string) => ({ id, name: id }) as Parameters<typeof guestCandidates>[0][number];
  const pool = [agent("own"), agent("a"), agent("b"), agent("c")];
  const named = (ids: string[]) => ids.map((agent_id) => ({ agent_id }));
  // The chat's own agent is never a guest.
  assert.deepEqual(
    guestCandidates(pool, named(["own", "a"]), true, "own").map((row) => row.id),
    ["a", "b", "c"],
  );
  // No cap (mandate P1): naming two guests still offers the third.
  assert.deepEqual(
    guestCandidates(pool, named(["a", "b"]), true, "own").map((row) => row.id),
    ["a", "b", "c"],
  );
  // A group offers everyone.
  assert.equal(guestCandidates(pool, named(["a", "b", "c"]), false).length, 4);
  const screen = readFileSync("apps/mobile/app/thread.tsx", "utf8");
  assert.match(screen, /direct=\{!thread\?\.group_id\}/);
  assert.match(screen, /self=\{thread\?\.group_id \? null : agent\?\.id\}/);
});

test("every named agent is addressed: no cap on how many (mandate P1)", () => {
  const ids = Array.from({ length: 20 }, (_, index) => `agent-${index}`);
  let text = "";
  const ranges = ids.map((agent_id) => {
    const token = `@${agent_id}`;
    const start = text.length;
    text += `${token} `;
    return { agent_id, token, start, end: start + token.length };
  });
  assert.deepEqual(mentionAddress(text, ranges).agent_ids, ids);
});
