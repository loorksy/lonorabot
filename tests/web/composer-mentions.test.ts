import assert from "node:assert/strict";
import test from "node:test";
import { type MentionRange, mentionSegments } from "../../packages/core/src/composer-mentions";

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
