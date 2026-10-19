import assert from "node:assert/strict";
import test from "node:test";
import { ConversationCache, conversationCache } from "../../apps/mobile/lib/conversation-cache";
import { closeSessionResources } from "../../apps/mobile/lib/session-lifecycle";

test("navigation retains confirmed conversation state within the same owner and server", () => {
  const cache = new ConversationCache();
  const scope = cache.activate("https://lonora.test", "owner");
  const state = {
    messages: [{ id: "message-1", content: "confirmed" }],
    runs: [{ status: "running" }],
  };
  cache.set(scope, "thread:one", state);
  assert.equal(cache.activate("https://lonora.test", "owner"), scope);
  assert.equal(cache.get(scope, "thread:one"), state);
  cache.set(scope, "thread:two", { messages: [] });
  assert.equal(cache.get(scope, "thread:one"), state);
});

test("logout teardown clears cached text and fences late responses even for the same owner", async () => {
  const scope = conversationCache.activate("https://lonora.test", "owner");
  conversationCache.set(scope, "thread:secret", { messages: ["private"] });
  await closeSessionResources();
  const next = conversationCache.activate("https://lonora.test", "owner");
  conversationCache.set(scope, "thread:secret", { messages: ["late private response"] });
  assert.equal(conversationCache.current(scope), false);
  assert.equal(conversationCache.get(next, "thread:secret"), undefined);
});

test("owner and server switches isolate conversations", () => {
  const cache = new ConversationCache();
  const first = cache.activate("https://one.test", "owner-a");
  cache.set(first, "thread:one", ["private"]);
  const second = cache.activate("https://one.test", "owner-b");
  assert.equal(cache.get(second, "thread:one"), undefined);
  cache.set(second, "thread:one", ["other private"]);
  const third = cache.activate("https://two.test", "owner-b");
  assert.equal(cache.get(third, "thread:one"), undefined);
});

test("cache expires idle entries and bounds the retained navigation history", () => {
  let now = 0;
  const cache = new ConversationCache(() => now, 2);
  const scope = cache.activate("https://one.test", "owner");
  cache.set(scope, "thread:one", 1);
  cache.set(scope, "thread:two", 2);
  assert.equal(cache.get(scope, "thread:one"), 1);
  cache.set(scope, "thread:three", 3);
  assert.equal(cache.get(scope, "thread:two"), undefined);
  now += 15 * 60_000 + 1;
  assert.equal(cache.get(scope, "thread:one"), undefined);
  assert.equal(cache.get(scope, "thread:three"), undefined);
});
