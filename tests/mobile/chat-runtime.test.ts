import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import type { Event, Message, Run } from "@lonora/contracts";
import ts from "typescript";
import {
  composerDraft,
  consumeComposerDraft,
  editComposerDraft,
} from "../../apps/mobile/lib/composer-drafts";
import { projectConversation } from "../../apps/mobile/lib/conversation-projection";
import { closeSessionResources } from "../../apps/mobile/lib/session-lifecycle";

function moduleFixture<T>(name: string, dependencies: Record<string, unknown>, globals = {}) {
  const source = readFileSync(new URL(`../../apps/mobile/lib/${name}.ts`, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  const exports = {} as T;
  runInNewContext(outputText, {
    exports,
    require(path: string) {
      if (!(path in dependencies)) throw new Error(`Unexpected module ${path}`);
      return dependencies[path];
    },
    URL,
    ...globals,
  });
  return exports;
}
function browserStorage() {
  const storage: Record<string, unknown> = {};
  return Object.assign(storage, {
    getItem: (key: string) => storage[key] ?? null,
    setItem: (key: string, value: string) => {
      storage[key] = value;
    },
    removeItem: (key: string) => {
      delete storage[key];
    },
  });
}
function outboxFixture(storage = browserStorage()) {
  const teardown: (() => Promise<void>)[] = [];
  const box = moduleFixture<typeof import("../../apps/mobile/lib/outgoing-messages")>(
    "outgoing-messages",
    {
      "react-native": { Platform: { OS: "web" } },
      "./session-lifecycle": {
        registerSessionTeardown: (fn: () => Promise<void>) => teardown.push(fn),
      },
    },
    { localStorage: storage, crypto: { randomUUID: () => "stable-client-nonce" } },
  );
  return { box, storage, teardown };
}

test("native outbox persists before acceptance, retries stable identity and deduplicates ACK", async () => {
  const { box, storage } = outboxFixture();
  const key = box.outgoingKey("https://one.test", "owner", "thread");
  const first = await box.enqueueOutgoing(key, "thread", "same-content", { content: "Hello" }, 5);
  assert.equal(first.nonce, "stable-client-nonce");
  assert.equal(box.outgoingMessages(key).length, 1);
  assert.ok(Object.keys(storage).some((value) => value.startsWith("lonora.outbox.v1:")));
  box.failOutgoing(key, first.nonce);
  const retry = await box.enqueueOutgoing(key, "thread", "same-content", { content: "Hello" }, 5);
  assert.equal(retry.nonce, first.nonce);
  assert.equal(retry.body.client_nonce, first.nonce);
  assert.equal(box.outgoingMessages(key).length, 1);
  box.acknowledgeOutgoing(key, [{ ...first.message, id: "canonical", seq: 6 }]);
  box.acknowledgeOutgoing(key, [{ ...first.message, id: "canonical", seq: 6 }]);
  assert.equal(box.outgoingMessages(key).length, 0);
});

test("native restart restores recoverable failed intents in their owner/thread scope", async () => {
  const first = outboxFixture();
  const key = first.box.outgoingKey("https://one.test", "owner", "thread");
  const accepted = await first.box.enqueueOutgoing(
    key,
    "thread",
    "content",
    {
      content: "With attachment",
      attachment_ids: ["file-one"],
      reply_to: "reply-one",
    },
    0,
  );
  const restarted = outboxFixture(first.storage);
  await restarted.box.hydrateOutgoing(key);
  const recovered = restarted.box.outgoingMessages(key)[0];
  assert.equal(recovered.nonce, accepted.nonce);
  assert.equal(recovered.message.delivery, "failed");
  assert.deepEqual(Array.from(recovered.message.attachment_ids), ["file-one"]);
  assert.equal(recovered.body.reply_to, "reply-one");
  assert.equal(
    restarted.box.outgoingMessages(
      restarted.box.outgoingKey("https://one.test", "other-owner", "thread"),
    ).length,
    0,
  );
});

test("native local persistence failure preserves caller draft and rolls back only unaccepted bubble", async () => {
  const storage = browserStorage();
  storage.setItem = () => {
    throw new Error("storage full");
  };
  const { box } = outboxFixture(storage);
  await assert.rejects(
    box.enqueueOutgoing("scope", "thread", "signature", { content: "Unsent draft" }, 0),
    /storage full/,
  );
  assert.equal(box.outgoingMessages("scope").length, 0);
});

test("logout fences asynchronous local admission before any new-owner delivery", async () => {
  const { box, teardown } = outboxFixture();
  const admission = box.enqueueOutgoing("scope", "thread", "signature", { content: "private" }, 0);
  await Promise.all(teardown.map((close) => close()));
  await assert.rejects(admission, /session_request_cancelled/);
  assert.equal(box.outgoingMessages("scope").length, 0);
});

test("native composer keeps per-thread drafts and never consumes a newer revision", async () => {
  const key = "owner-one/thread-a",
    other = "owner-one/thread-b";
  editComposerDraft(key, {
    text: "submitted",
    attachments: [{ id: "file" } as never],
    reply: { id: "reply" } as never,
  });
  const submitted = composerDraft(key);
  editComposerDraft(other, { text: "other conversation" });
  editComposerDraft(key, { text: "new text while admission writes" });
  assert.equal(
    consumeComposerDraft(key, submitted.revision).text,
    "new text while admission writes",
  );
  assert.equal(composerDraft(other).text, "other conversation");
  const consumed = consumeComposerDraft(key, composerDraft(key).revision);
  assert.equal(consumed.text, "");
  assert.equal(consumed.attachments.length, 0);
  assert.equal(consumed.reply, null);
  await closeSessionResources();
  assert.equal(composerDraft(other).text, "");
});

const message = (id: string, seq: number): Message => ({
  id,
  seq,
  thread_id: "thread",
  agent_id: null,
  role: "user",
  content: id,
  created_at: "2026-10-25T10:00:00Z",
  attachment_ids: [],
  reply_to: null,
});
const run = (id: string, trigger = "user"): Run => ({
  id,
  thread_id: "thread",
  agent_id: "agent",
  parent_run_id: null,
  status: "queued",
  trigger,
  error_code: null,
  result: null,
  model_metadata: {},
  input_seq: 1,
  created_at: "2026-10-25T10:00:01Z",
  updated_at: "2026-10-25T10:00:01Z",
});

test("native response preview is anchored to its actual user input; background runs stay separate", () => {
  const projected = projectConversation(
    [message("input-one", 1), message("input-two", 2)],
    [run("reply-one"), run("background", "routine")],
    {},
  );
  assert.deepEqual(
    projected.map((row) => row.id),
    ["input-one", "preview:reply-one", "input-two"],
  );
  assert.equal(projectConversation([], [run("orphan")], {}).length, 0);
});

test("concurrent pending sends remain after canonical ACK and never jump before it", () => {
  const rows = projectConversation(
    [message("canonical-one", 1), message("pending:two", 0.5)],
    [],
    {},
  );
  assert.deepEqual(
    rows.map((row) => row.id),
    ["canonical-one", "pending:two"],
  );
});

test("native durable WS authenticates live, resumes cursor, refreshes after ready and pauses in background", async () => {
  type Timer = { callback: () => void; ms: number; cleared?: boolean };
  const timers: Timer[] = [],
    sockets: Socket[] = [],
    phases: string[] = [],
    events: Event[] = [];
  let refreshes = 0,
    appChange: ((state: string) => void) | undefined;
  class Socket {
    static OPEN = 1;
    static CONNECTING = 0;
    readyState = 1;
    sent: string[] = [];
    onopen?: () => void;
    onclose?: () => void;
    onerror?: () => void;
    onmessage?: (event: { data: string }) => void;
    constructor(readonly url: string) {
      sockets.push(this);
    }
    send(raw: string) {
      this.sent.push(raw);
    }
    close() {
      this.readyState = 3;
      this.onclose?.();
    }
    receive(value: unknown) {
      this.onmessage?.({ data: JSON.stringify(value) });
    }
  }
  const transport = moduleFixture<typeof import("../../apps/mobile/lib/events")>(
    "events",
    {
      "react-native": {
        Platform: { OS: "android" },
        AppState: {
          currentState: "active",
          addEventListener: (_: string, callback: (state: string) => void) => {
            appChange = callback;
            return { remove() {} };
          },
        },
      },
      "./session-lifecycle": { registerSessionTeardown() {} },
      "./storage": { loadNativeToken: async () => "private-session" },
    },
    {
      WebSocket: Socket,
      setTimeout: (callback: () => void, ms: number) => {
        const timer = { callback, ms };
        timers.push(timer);
        return timer;
      },
      clearTimeout: (timer: Timer) => {
        timer.cleared = true;
      },
    },
  );
  const stop = transport.subscribeOwnerEvents(
    "https://one.test",
    (event) => events.push(event),
    () => {
      refreshes++;
    },
    (phase) => phases.push(phase),
  );
  sockets[0].onopen?.();
  await new Promise<void>((resolve) => setImmediate(resolve));
  const auth = JSON.parse(sockets[0].sent[0]);
  assert.deepEqual(auth, { cursor: 0, live: true, token: "private-session" });
  assert.equal(sockets[0].url.includes("private-session"), false);
  sockets[0].receive({ type: "ready", cursor: 10 });
  const event = {
    cursor: 11,
    kind: "run.delta",
    payload: {},
    thread_id: "thread",
    agent_id: "agent",
    run_id: "run",
    created_at: "2026-10-25T10:00:01Z",
  };
  sockets[0].receive(event);
  sockets[0].receive(event);
  assert.equal(events.length, 1);
  sockets[0].close();
  timers.find((timer) => timer.ms === 1500 && !timer.cleared)?.callback();
  sockets[1].onopen?.();
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.deepEqual(JSON.parse(sockets[1].sent[0]), { cursor: 11, token: "private-session" });
  sockets[1].receive({ type: "ready", cursor: 11 });
  assert.equal(refreshes, 2);
  appChange?.("background");
  assert.equal(sockets[1].readyState, 3);
  assert.deepEqual(phases, [
    "connecting",
    "connected",
    "reconnecting",
    "reconnecting",
    "connected",
  ]);
  stop();
});
