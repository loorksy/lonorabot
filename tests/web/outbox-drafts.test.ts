import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import type { Message, Resource } from "../../apps/web/src/lib/api";
import {
  draftKey,
  draftUploads,
  pendingDraftUploads,
  readComposerDraft,
  saveComposerDraft,
  takeDraftUploads,
  trackDraftUpload,
} from "../../apps/web/src/lib/composer-drafts";
import {
  acknowledgeOutgoing,
  enqueueOutgoing,
  failOutgoing,
  outgoingKey,
  outgoingMessages,
} from "../../apps/web/src/lib/outgoing-messages";

beforeEach(() => {
  const values = new Map<string, string>();
  Object.assign(globalThis, {
    localStorage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    },
  });
});
test("uncertain send retains stable nonce, attachments and reply until canonical acknowledgement", () => {
  const key = outgoingKey(crypto.randomUUID(), "thread");
  const body = { content: "Review this", attachment_ids: ["file"], reply_to: "parent" };
  const first = enqueueOutgoing(key, "thread", "same intent", body, 5);
  failOutgoing(key, first.nonce);
  assert.equal(outgoingMessages(key)[0].message.delivery, "failed");
  const retry = enqueueOutgoing(key, "thread", "same intent", body, 6);
  assert.equal(retry.nonce, first.nonce);
  assert.equal(outgoingMessages(key).length, 1);
  assert.equal(outgoingMessages(key)[0].message.delivery, "sending");
  assert.equal(retry.body.client_nonce, first.nonce);
  assert.deepEqual(retry.message.attachment_ids, ["file"]);
  assert.equal(retry.message.reply_to, "parent");
  acknowledgeOutgoing(key, [{ id: "canonical", client_nonce: first.nonce } as Message]);
  assert.equal(outgoingMessages(key).length, 0);
  // SSE and HTTP may acknowledge the same committed message independently.
  acknowledgeOutgoing(key, [{ id: "canonical", client_nonce: first.nonce } as Message], true);
  assert.equal(outgoingMessages(key).length, 0);
});
test("restored unacknowledged receipts require Retry and never auto-submit", () => {
  const owner = crypto.randomUUID(),
    key = outgoingKey(owner, "thread");
  const nonce = crypto.randomUUID();
  localStorage.setItem(
    `lonora:outbox:v1:${key}`,
    JSON.stringify([
      {
        nonce,
        fingerprint: "recovered",
        body: { client_nonce: nonce, content: "Saved text" },
        message: {
          id: `pending:${nonce}`,
          thread_id: "thread",
          role: "user",
          content: "Saved text",
          attachment_ids: [],
          delivery: "sending",
        },
      },
    ]),
  );
  assert.equal(outgoingMessages(key)[0].message.delivery, "failed");
  assert.equal(outgoingMessages(outgoingKey(crypto.randomUUID(), "thread")).length, 0);
});
/** An upload the test finishes by hand: its progress callback, its signal, its outcome. */
function held() {
  const run = {
    progress: (_: number) => {},
    signal: undefined as AbortSignal | undefined,
    finish: (_: Resource) => {},
    fail: (_: unknown) => {},
  };
  const start = (progress: (p: number) => void, signal: AbortSignal) => {
    run.progress = progress;
    run.signal = signal;
    return new Promise<Resource>((resolve, reject) => {
      run.finish = resolve;
      run.fail = reject;
    });
  };
  return { run, start };
}
const file = (name: string) => ({ name, size: 3, type: "text/plain" }) as File;
const stored = (id: string) => ({ id, payload: { name: "chart.png" } }) as Resource;

test("thread and owner drafts remain isolated, including uploads completing offscreen", async () => {
  const owner = crypto.randomUUID(),
    a = draftKey(owner, "A"),
    b = draftKey(owner, "B");
  saveComposerDraft(a, { text: "Unsent A", files: [], mentions: [], reply: null });
  saveComposerDraft(b, { text: "Unsent B", files: [], mentions: [], reply: null });
  const { run, start } = held();
  const upload = trackDraftUpload(a, file("chart.png"), start);
  assert.equal(pendingDraftUploads(a), 1);
  assert.equal(pendingDraftUploads(b), 0);
  // Progress gives readers a new list, so one that compares lists redraws.
  const before = draftUploads(a);
  run.progress(0.5);
  assert.equal(upload.p, 0.5);
  assert.notEqual(draftUploads(a), before);
  run.finish(stored("upload-a"));
  await upload.done;
  assert.equal(pendingDraftUploads(a), 0);
  assert.equal(readComposerDraft(a).text, "Unsent A");
  assert.equal(readComposerDraft(a).files[0].id, "upload-a");
  assert.equal(readComposerDraft(b).text, "Unsent B");
  assert.equal(readComposerDraft(b).files.length, 0);
  assert.equal(readComposerDraft(draftKey(crypto.randomUUID(), "A")).text, "");
});
test("a cancelled or failed upload leaves nothing, and one a message took stays out of the draft", async () => {
  const key = draftKey(crypto.randomUUID(), "A");
  const cancelled = held();
  const first = trackDraftUpload(key, file("a.txt"), cancelled.start);
  first.cancel();
  assert.equal(cancelled.run.signal?.aborted, true);
  cancelled.run.fail(new Error("aborted"));
  await assert.rejects(first.done);
  assert.equal(pendingDraftUploads(key), 0);
  assert.equal(readComposerDraft(key).files.length, 0);

  const sent = held();
  let moved = 0;
  const second = trackDraftUpload(key, file("b.txt"), sent.start, () => {
    moved += 1;
  });
  assert.deepEqual(takeDraftUploads(key), [second]);
  assert.equal(pendingDraftUploads(key), 0);
  // The message that took it still hears its progress.
  sent.run.progress(0.25);
  assert.equal(moved, 1);
  sent.run.finish(stored("upload-b"));
  assert.equal((await second.done).id, "upload-b");
  assert.equal(readComposerDraft(key).files.length, 0);
});
test("closed storage does not prevent local acceptance or destroy a draft", () => {
  Object.assign(globalThis, {
    localStorage: {
      getItem() {
        throw Error("closed");
      },
      setItem() {
        throw Error("closed");
      },
      removeItem() {
        throw Error("closed");
      },
    },
  });
  const key = outgoingKey(crypto.randomUUID(), "thread");
  enqueueOutgoing(key, "thread", "local", { content: "Recoverable" });
  assert.equal(outgoingMessages(key)[0].message.content, "Recoverable");
  const draft = draftKey(crypto.randomUUID(), "thread");
  saveComposerDraft(draft, { text: "Still here", files: [], mentions: [], reply: null });
  assert.equal(readComposerDraft(draft).text, "Still here");
});
