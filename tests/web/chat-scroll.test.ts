import assert from "node:assert/strict";
import test from "node:test";
import { showLatestButton } from "../../apps/web/src/lib/chat-scroll";

test("latest-message affordance does not flash when streaming near the threshold", () => {
  assert.equal(showLatestButton(false, 95), false);
  assert.equal(showLatestButton(false, 97), true);
  assert.equal(showLatestButton(true, 95), true);
  assert.equal(showLatestButton(true, 25), true);
  assert.equal(showLatestButton(true, 24), false);
  assert.equal(showLatestButton(false, -1), false);
});
