import assert from "node:assert/strict";
import test from "node:test";
import { mentionAddress, rebaseMentions } from "../../packages/core/src/composer-mentions";

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
