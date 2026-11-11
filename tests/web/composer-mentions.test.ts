import assert from "node:assert/strict";
import test from "node:test";
import {
  type MentionRange,
  matchesEveryone,
  mentionAddress,
  mentionSegments,
} from "../../packages/core/src/composer-mentions";

const range = (token: string, start: number): MentionRange => ({
  agent_id: token,
  token,
  start,
  end: start + token.length,
});

test("the mirror marks each committed token and keeps the rest as text", () => {
  const text = "مرحبا @رفيق و @Lonora كيف";
  assert.deepEqual(mentionSegments(text, [range("@Lonora", 14), range("@رفيق", 6)]), [
    { text: "مرحبا ", mark: false },
    { text: "@رفيق", mark: true },
    { text: " و ", mark: false },
    { text: "@Lonora", mark: true },
    { text: " كيف", mark: false },
  ]);
});

test("an edited token is no longer marked", () => {
  assert.deepEqual(mentionSegments("@Lonoa hi", [range("@Lonora", 0)]), [
    { text: "@Lonoa hi", mark: false },
  ]);
  assert.deepEqual(mentionSegments("", []), []);
});

test("@all in a group names every member; in a direct chat it stays the session's", () => {
  const all: MentionRange = { agent_id: null, token: "@الكل", start: 0, end: 5 };
  assert.deepEqual(mentionAddress("@الكل hi", [all], ["a", "b"]), {
    agent_ids: ["a", "b"],
    all: false,
    collaboration_session_id: undefined,
  });
  // A member named beside it is addressed once.
  const named = { ...range("@a", 6), agent_id: "a" };
  assert.deepEqual(mentionAddress("@الكل @a", [all, named], ["a", "b"]).agent_ids, ["a", "b"]);
  // No group: the open collaboration session is addressed, as before.
  const session = { ...all, session_id: "s1" };
  assert.deepEqual(mentionAddress("@الكل hi", [session]), {
    agent_ids: [],
    all: true,
    collaboration_session_id: "s1",
  });
  // A token the owner edited addresses no one.
  assert.deepEqual(mentionAddress("@الك hi", [all], ["a", "b"]).agent_ids, []);
});

test("@all is found by the start of any of its names", () => {
  for (const query of ["", "ال", "الك", "al", "ALL", "Every", "الجم"])
    assert.equal(matchesEveryone(query), true, query);
  for (const query of ["x", "ل", "allx", "كل"]) assert.equal(matchesEveryone(query), false, query);
});
