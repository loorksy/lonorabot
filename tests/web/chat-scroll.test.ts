import assert from "node:assert/strict";
import test from "node:test";
import { showLatestButton, stickToLatest } from "../../apps/web/src/lib/chat-scroll";

test("latest-message affordance does not flash when streaming near the threshold", () => {
  assert.equal(showLatestButton(false, 95), false);
  assert.equal(showLatestButton(false, 97), true);
  assert.equal(showLatestButton(true, 95), true);
  assert.equal(showLatestButton(true, 25), true);
  assert.equal(showLatestButton(true, 24), false);
  assert.equal(showLatestButton(false, -1), false);
});

test("opening a transcript lands on the latest message", () => {
  const position = { scrollHeight: 4000, scrollTop: 0 };
  const following = { current: true };
  const anchored = { current: 0 };
  stickToLatest(position, following, anchored, false);
  assert.equal(following.current, true);
  assert.equal(position.scrollTop, 4000);
  assert.equal(anchored.current, 4000);
});

test("a jump to the top during a stream is left there", () => {
  const position = { scrollHeight: 4000, scrollTop: 0 };
  const following = { current: true };
  const anchored = { current: 0 };
  stickToLatest(position, following, anchored, false);
  position.scrollTop = 0;
  stickToLatest(position, following, anchored, false);
  assert.equal(following.current, false);
  assert.equal(position.scrollTop, 0);
  assert.equal(anchored.current, 4000);
});

test("growth while already at the bottom keeps following", () => {
  const position = { scrollHeight: 4000, scrollTop: 3200 };
  const following = { current: true };
  const anchored = { current: 3200 };
  position.scrollHeight = 4200;
  stickToLatest(position, following, anchored, false);
  assert.equal(following.current, true);
  assert.equal(position.scrollTop, 4200);
  assert.equal(anchored.current, 4200);
});
