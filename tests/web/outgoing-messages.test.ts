import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import type { Message } from "../../apps/web/src/lib/api";

type Outbox = typeof import("../../apps/web/src/lib/outgoing-messages");
function fixture() {
  const window = new EventTarget();
  const exports = {} as Outbox;
  const source = readFileSync(
    new URL("../../apps/web/src/lib/outgoing-messages.ts", import.meta.url),
    "utf8",
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  runInNewContext(outputText, { exports, window, crypto: webcrypto });
  const key = exports.outgoingKey("owner", "thread");
  return { outbox: exports, window, key };
}
function accepted(intent: ReturnType<Outbox["enqueueOutgoing"]>): Message {
  return { ...intent.message, id: "server-record", seq: 4 };
}

test("a send is visible synchronously before any network acknowledgement", () => {
  const { outbox, key } = fixture();
  const notifications: number[] = [];
  const unsubscribe = outbox.subscribeOutgoing(() =>
    notifications.push(outbox.outgoingMessages(key).length),
  );
  const intent = outbox.enqueueOutgoing(key, "thread", "fingerprint", { content: "صباح الخير" });
  assert.equal(outbox.outgoingMessages(key)[0].message.content, "صباح الخير");
  assert.equal(intent.message.delivery, "sending");
  assert.equal(intent.message.client_nonce, intent.body.client_nonce);
  assert.deepEqual(notifications, [1]);
  unsubscribe();
});

test("failed and in-flight retries retain the exact nonce and original intent", () => {
  const { outbox, key } = fixture();
  const first = outbox.enqueueOutgoing(key, "thread", "fingerprint", {
    content: "Review the market",
    reply_to: "original-parent",
    attachment_ids: ["owned-file"],
  });
  assert.equal(outbox.enqueueOutgoing(key, "thread", "fingerprint", first.body).nonce, first.nonce);
  outbox.failOutgoing(key, first.nonce);
  assert.equal(outbox.outgoingMessages(key)[0].message.delivery, "failed");
  const retry = outbox.enqueueOutgoing(key, "thread", "fingerprint", first.body);
  assert.equal(retry.nonce, first.nonce);
  assert.equal(retry.body.reply_to, "original-parent");
  assert.equal(outbox.outgoingMessages(key).length, 1);
  assert.equal(outbox.outgoingMessages(key)[0].message.delivery, "sending");
});

test("a committed SSE/history record replaces its optimistic copy by nonce", () => {
  const { outbox, key } = fixture();
  const intent = outbox.enqueueOutgoing(key, "thread", "same text", { content: "hello" });
  outbox.acknowledgeOutgoing(key, [accepted(intent)]);
  assert.equal(outbox.outgoingMessages(key).length, 0);
  outbox.failOutgoing(key, intent.nonce);
  assert.equal(outbox.outgoingMessages(key).length, 0);
});

test("lost HTTP receipt remains safe to retry even after an event confirms the message", () => {
  const { outbox, key } = fixture();
  const intent = outbox.enqueueOutgoing(key, "thread", "same text", { content: "hello" });
  outbox.failOutgoing(key, intent.nonce);
  outbox.acknowledgeOutgoing(key, [accepted(intent)]);
  const retry = outbox.enqueueOutgoing(key, "thread", "same text", intent.body);
  assert.equal(retry.nonce, intent.nonce);
  outbox.acknowledgeOutgoing(key, [accepted(retry)], true);
  const next = outbox.enqueueOutgoing(key, "thread", "same text", intent.body);
  assert.notEqual(next.nonce, intent.nonce);
});

test("navigation and other owners cannot consume another conversation's outbox", () => {
  const { outbox, key } = fixture();
  const intent = outbox.enqueueOutgoing(key, "thread", "a", { content: "retained" });
  const otherThread = outbox.outgoingKey("owner", "other-thread");
  const otherOwner = outbox.outgoingKey("other-owner", "thread");
  assert.equal(outbox.outgoingMessages(otherThread).length, 0);
  assert.equal(outbox.outgoingMessages(otherOwner).length, 0);
  outbox.acknowledgeOutgoing(otherThread, [accepted(intent)], true);
  assert.equal(outbox.outgoingMessages(key)[0].nonce, intent.nonce);
});

test("session reset clears pending and uncertain intent before another login", () => {
  const { outbox, key, window } = fixture();
  const first = outbox.enqueueOutgoing(key, "thread", "intent", { content: "hello" });
  outbox.failOutgoing(key, first.nonce);
  window.dispatchEvent(new Event("lonora:session-reset"));
  assert.equal(outbox.outgoingMessages(key).length, 0);
  const next = outbox.enqueueOutgoing(key, "thread", "intent", first.body);
  assert.notEqual(next.nonce, first.nonce);
});
