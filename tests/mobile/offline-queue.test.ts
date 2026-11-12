// Owner decision Q6 on mobile, as on Web: a plain message the API never answered waits
// («بانتظار الشبكة…») and goes out by itself, under its own client_nonce, when the network
// returns; an answer, an edit, a card submit or a voice note never waits and stays «failed».
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import { ApiError } from "../../apps/mobile/lib/api-error";
import { isPlainOutgoing } from "../../packages/core/src/chat-rows";
import { pendingVoiceRich } from "../../packages/core/src/message-parts";

type Box = typeof import("../../apps/mobile/lib/outgoing-messages");

function storageFixture() {
  const storage: Record<string, unknown> = {};
  return Object.assign(storage, {
    getItem: (key: string) => (storage[key] as string | undefined) ?? null,
    setItem: (key: string, value: string) => {
      storage[key] = value;
    },
    removeItem: (key: string) => {
      delete storage[key];
    },
  });
}

function outbox(storage = storageFixture()) {
  const source = readFileSync(
    new URL("../../apps/mobile/lib/outgoing-messages.ts", import.meta.url),
    "utf8",
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  const box = {} as Box;
  let counter = 0;
  const dependencies: Record<string, unknown> = {
    "react-native": { Platform: { OS: "web" } },
    "@lonora/core": { pendingVoiceRich, isPlainOutgoing },
    "./api-error": { ApiError },
    "./session-lifecycle": { registerSessionTeardown: () => undefined },
  };
  runInNewContext(outputText, {
    exports: box,
    require(path: string) {
      if (!(path in dependencies)) throw new Error(`Unexpected module ${path}`);
      return dependencies[path];
    },
    localStorage: storage,
    crypto: { randomUUID: () => `nonce-${++counter}` },
  });
  return { box, storage };
}

const offline = new TypeError("Network request failed");

test("an unanswered plain send waits; an answered one fails", () => {
  const { box } = outbox();
  assert.equal(box.serverAnswered(offline), false);
  assert.equal(box.serverAnswered(new ApiError("request_failed", 502)), false);
  assert.equal(box.serverAnswered(new ApiError("request_failed", 504)), false);
  assert.equal(box.serverAnswered(new ApiError("thread_not_found", 404)), true);
  assert.equal(box.serverAnswered(new ApiError("database_unavailable", 503)), true);
  assert.equal(box.serverAnswered(new ApiError("upstream", 502)), true);
  assert.equal(box.waitsForNetwork(offline, { content: "hi" }), true);
  assert.equal(box.waitsForNetwork(new ApiError("bad", 422), { content: "hi" }), false);
  for (const body of [
    { content: "A", input_answer: { run_id: "r", question_id: "q", choice_id: "c" } },
    { content: "edit", edited_from: "m1" },
    { content: "form", ui_submit: { action: "x" } },
    { content: "", voice: { artifact_id: "v", duration: 3 } },
  ])
    assert.equal(box.waitsForNetwork(offline, body), false, JSON.stringify(body));
  const cancelled = Object.assign(new Error("session_request_cancelled"), {
    name: "SessionRequestCancelled",
  });
  assert.equal(box.waitsForNetwork(cancelled, { content: "hi" }), false);
});

test("a queued message survives a restart as queued; one in flight comes back failed", async () => {
  const first = outbox();
  const key = first.box.outgoingKey("https://one.test", "owner", "thread");
  const waiting = await first.box.enqueueOutgoing(key, "thread", "a", { content: "Waiting" }, 0);
  const flying = await first.box.enqueueOutgoing(key, "thread", "b", { content: "Flying" }, 0);
  first.box.failOutgoing(key, waiting.nonce, "queued");
  await new Promise((resolve) => setTimeout(resolve, 0));
  const second = outbox(first.storage);
  await second.box.hydrateOutgoing(key);
  const rows = second.box.outgoingMessages(key);
  assert.equal(rows.find((row) => row.nonce === waiting.nonce)?.message.delivery, "queued");
  assert.equal(rows.find((row) => row.nonce === flying.nonce)?.message.delivery, "failed");
});

test("the flush posts queued messages with their own nonce, in order, and stops offline", async () => {
  const { box } = outbox();
  const one = box.outgoingKey("https://one.test", "owner", "t1");
  const two = box.outgoingKey("https://one.test", "owner", "t2");
  const a = await box.enqueueOutgoing(one, "t1", "a", { content: "A" }, 0);
  const b = await box.enqueueOutgoing(one, "t1", "b", { content: "B" }, 0);
  const failed = await box.enqueueOutgoing(one, "t1", "f", { content: "F" }, 0);
  const c = await box.enqueueOutgoing(two, "t2", "c", { content: "C" }, 0);
  for (const [key, row] of [
    [one, a],
    [one, b],
    [two, c],
  ] as const)
    box.failOutgoing(key, row.nonce, "queued");
  box.failOutgoing(one, failed.nonce);

  const posted: [string, unknown][] = [];
  let network = false,
    attempts = 0;
  const post = async (thread: string, body: Record<string, unknown>) => {
    attempts += 1;
    if (!network) throw offline;
    posted.push([thread, body.client_nonce]);
    return { ...a.message, id: `m-${body.client_nonce}`, client_nonce: String(body.client_nonce) };
  };
  // Still offline: nothing is lost and the first one waits again.
  assert.equal(await box.flushQueued([one, two], post), 0);
  assert.equal(attempts, 1, "the flush stops at the first send the API does not answer");
  assert.equal(
    box.outgoingMessages(one).find((r) => r.nonce === a.nonce)?.message.delivery,
    "queued",
  );

  network = true;
  assert.equal(await box.flushQueued([one, two], post), 3);
  assert.deepEqual(posted, [
    ["t1", a.nonce],
    ["t1", b.nonce],
    ["t2", c.nonce],
  ]);
  // A failed message never leaves by itself: it waits for the owner's retry.
  assert.equal(
    JSON.stringify(box.outgoingMessages(one).map((row) => [row.nonce, row.message.delivery])),
    JSON.stringify([[failed.nonce, "failed"]]),
  );
  assert.equal(box.outgoingMessages(two).length, 0);
});

test("a message the server refuses during the flush fails and the flush goes on", async () => {
  const { box } = outbox();
  const key = box.outgoingKey("https://one.test", "owner", "t1");
  const a = await box.enqueueOutgoing(key, "t1", "a", { content: "A" }, 0);
  const b = await box.enqueueOutgoing(key, "t1", "b", { content: "B" }, 0);
  box.failOutgoing(key, a.nonce, "queued");
  box.failOutgoing(key, b.nonce, "queued");
  const sent = await box.flushQueued([key], async (_thread, body) => {
    if (body.client_nonce === a.nonce) throw new ApiError("thread_not_found", 404);
    return { ...b.message, id: "m-b", client_nonce: b.nonce };
  });
  assert.equal(sent, 1);
  assert.equal(
    JSON.stringify(box.outgoingMessages(key).map((row) => [row.nonce, row.message.delivery])),
    JSON.stringify([[a.nonce, "failed"]]),
  );
});

test("the flush covers every conversation of this server and owner, and no other", async () => {
  const { box } = outbox();
  const listed = box.outgoingKey("https://one.test", "owner", "inbox-thread");
  const routine = box.outgoingKey("https://one.test", "owner", "routine-thread");
  const otherOwner = box.outgoingKey("https://one.test", "someone", "thread");
  const otherServer = box.outgoingKey("https://two.test", "owner", "thread");
  for (const key of [listed, routine, otherOwner, otherServer])
    await box.enqueueOutgoing(key, JSON.parse(key)[2], key, { content: "x" }, 0);
  assert.equal(
    JSON.stringify(box.ownerOutgoingKeys("https://one.test", "owner").sort()),
    JSON.stringify([listed, routine].sort()),
  );
});

type Held = {
  done: Promise<{ id: string }>;
  cancel: () => void;
  name: string;
  size: number;
  media_type: string;
};
function heldUpload(name: string) {
  let resolve!: (row: { id: string }) => void, reject!: (cause: unknown) => void;
  let cancelled = false;
  const done = new Promise<{ id: string }>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  done.catch(() => undefined);
  const upload = {
    done,
    name,
    size: 1,
    media_type: "text/plain",
    cancel: () => (cancelled = true),
  };
  return { upload: upload as unknown as Held, resolve, reject, cancelled: () => cancelled };
}

test("a message sent while its files upload gets their ids once they are up", async () => {
  const { box } = outbox();
  const key = box.outgoingKey("https://one.test", "owner", "t1");
  const file = heldUpload("a.txt");
  const sent = await box.enqueueOutgoing(
    key,
    "t1",
    "f",
    { content: "Read", attachment_ids: [] },
    0,
    [file.upload] as never,
  );
  assert.equal(sent.message.uploading?.length, 1);
  assert.equal(box.outgoingUploads(sent.nonce).length, 1);
  file.resolve({ id: "file-1" });
  const ready = await box.settleOutgoingUploads(key, sent.nonce);
  assert.equal(JSON.stringify(ready?.body.attachment_ids), '["file-1"]');
  assert.equal(ready?.message.uploading, undefined);
  assert.equal(box.outgoingUploads(sent.nonce).length, 0);
});

test("a failed upload gives the message back: it leaves the outbox with its text and arrived files", async () => {
  const { box } = outbox();
  const key = box.outgoingKey("https://one.test", "owner", "t1");
  const broken = heldUpload("broken.txt"),
    arrived = heldUpload("arrived.txt");
  const sent = await box.enqueueOutgoing(key, "t1", "f", { content: "Read", reply_to: "m1" }, 0, [
    broken.upload,
    arrived.upload,
  ] as never);
  Object.assign(arrived.upload, { result: { id: "file-arrived" } });
  arrived.resolve({ id: "file-arrived" });
  broken.reject(new Error("upload_failed"));
  const failure = await box.settleOutgoingUploads(key, sent.nonce).then(
    () => null,
    (error) => error,
  );
  assert.equal(failure?.name, "OutgoingUploadFailed");
  assert.equal(failure.intent.body.content, "Read");
  assert.equal(failure.intent.body.reply_to, "m1");
  assert.equal(
    JSON.stringify(failure.finished.map((row: { id: string }) => row.id)),
    '["file-arrived"]',
  );
  assert.equal(box.outgoingMessages(key).length, 0);
});

test("a message whose files were uploading when the app died restarts failed: Delete only, never flushed", async () => {
  const first = outbox();
  const key = first.box.outgoingKey("https://one.test", "owner", "t1");
  await first.box.enqueueOutgoing(key, "t1", "f", { content: "Read" }, 0, [
    heldUpload("a.txt").upload,
  ] as never);
  await new Promise((resolve) => setTimeout(resolve, 0));
  const restarted = outbox(first.storage);
  await restarted.box.hydrateOutgoing(key);
  const restored = restarted.box.outgoingMessages(key)[0];
  assert.equal(restored.message.delivery, "failed");
  assert.equal(restored.message.uploading?.length, 1);
  let posts = 0;
  const post = async () => {
    posts += 1;
    return restored.message;
  };
  assert.equal(await restarted.box.flushQueued([key], post), 0);
  assert.equal(posts, 0);
});

test("✕ on a sent message's ring cancels its uploads and removes it unposted", async () => {
  const { box } = outbox();
  const key = box.outgoingKey("https://one.test", "owner", "t1");
  const file = heldUpload("a.txt");
  const sent = await box.enqueueOutgoing(key, "t1", "f", { content: "Read" }, 0, [
    file.upload,
  ] as never);
  box.cancelOutgoingUploads(key, sent.nonce);
  assert.equal(file.cancelled(), true);
  assert.equal(box.outgoingMessages(key).length, 0);
  file.resolve({ id: "late" });
  assert.equal(await box.settleOutgoingUploads(key, sent.nonce), null);
});
