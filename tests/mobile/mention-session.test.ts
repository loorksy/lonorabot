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

test("item 25: mobile caps guests only in a direct chat and never counts the chat's own agent", () => {
  const agent = (id: string) => ({ id, name: id }) as Parameters<typeof guestCandidates>[0][number];
  const pool = [agent("own"), agent("a"), agent("b"), agent("c")];
  const named = (ids: string[]) => ids.map((agent_id) => ({ agent_id }));
  // The chat's own agent is never a guest and does not use up the two places.
  assert.deepEqual(
    guestCandidates(pool, named(["own", "a"]), true, "own").map((row) => row.id),
    ["a", "b", "c"],
  );
  assert.deepEqual(
    guestCandidates(pool, named(["a", "b"]), true, "own").map((row) => row.id),
    ["a", "b"],
  );
  // A group has no guest cap.
  assert.equal(guestCandidates(pool, named(["a", "b", "c"]), false).length, 4);
  const screen = readFileSync("apps/mobile/app/thread.tsx", "utf8");
  assert.match(screen, /direct=\{!thread\?\.group_id\}/);
  assert.match(screen, /self=\{thread\?\.group_id \? null : agent\?\.id\}/);
});
