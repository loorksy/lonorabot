// Composer drafts survive an app restart on mobile, as on Web (localStorage `lonora:composer:v1:`):
// the text, the finished attachments and the reply, per server, owner and conversation; a
// restored draft never overwrites one typed since; sign-out removes them all.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import * as drafts from "../../apps/mobile/lib/composer-drafts";
import { closeSessionResources } from "../../apps/mobile/lib/session-lifecycle";

type Store = typeof import("../../apps/mobile/lib/draft-store");

function storage() {
  const values: Record<string, string> = {};
  return {
    values,
    getItem: (key: string) => values[key] ?? null,
    setItem: (key: string, value: string) => {
      values[key] = value;
    },
    removeItem: (key: string) => {
      delete values[key];
    },
    key: (index: number) => Object.keys(values)[index] ?? null,
    get length() {
      return Object.keys(values).length;
    },
  };
}

function load(local: ReturnType<typeof storage>) {
  const source = readFileSync(
    new URL("../../apps/mobile/lib/draft-store.ts", import.meta.url),
    "utf8",
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  const teardown: (() => Promise<void>)[] = [];
  const store = {} as Store;
  runInNewContext(outputText, {
    exports: store,
    require(path: string) {
      const map: Record<string, unknown> = {
        "react-native": { Platform: { OS: "web" } },
        "./composer-drafts": drafts,
        "./session-lifecycle": {
          registerSessionTeardown: (fn: () => Promise<void>) => teardown.push(fn),
        },
      };
      if (!(path in map)) throw new Error(`Unexpected module ${path}`);
      return map[path];
    },
    localStorage: local,
    setTimeout,
    clearTimeout,
  });
  return { store, teardown };
}
const key = (thread: string) => JSON.stringify(["https://one.test", "owner", thread]);

test("a draft written before a restart comes back in its own conversation only", async () => {
  const local = storage();
  const first = load(local);
  drafts.editComposerDraft(key("a"), {
    text: "Close half at 2,425",
    attachments: [{ id: "file-1", payload: { name: "r.pdf" } } as never],
    reply: { id: "m1", content: "Where?" } as never,
  });
  await first.store.saveDraft(key("a"));
  assert.ok(Object.keys(local.values).some((name) => name.startsWith("lonora.draft.v1:")));

  // Restart (not sign-out): the drafts in memory are gone, the saved ones are not. Clearing
  // memory runs only the drafts' own teardown; the device store's is not registered here.
  await closeSessionResources();
  const second = load(local);
  await second.store.restoreDraft(key("a"));
  const restored = drafts.composerDraft(key("a"));
  assert.equal(restored.text, "Close half at 2,425");
  assert.equal(restored.attachments[0]?.id, "file-1");
  assert.equal(restored.reply?.id, "m1");
  await second.store.restoreDraft(key("b"));
  assert.equal(drafts.composerDraft(key("b")).text, "");
});

test("a restored draft never overwrites one typed since; an empty draft is removed", async () => {
  const local = storage();
  const { store } = load(local);
  drafts.editComposerDraft(key("c"), { text: "old" });
  await store.saveDraft(key("c"));
  drafts.editComposerDraft(key("c"), { text: "typed after opening" });
  await store.restoreDraft(key("c"));
  assert.equal(drafts.composerDraft(key("c")).text, "typed after opening");
  drafts.consumeComposerDraft(key("c"), drafts.composerDraft(key("c")).revision);
  await store.saveDraft(key("c"));
  assert.equal(
    Object.keys(local.values).filter((name) => name.startsWith("lonora.draft.v1:")).length,
    0,
  );
});

test("sign-out removes every saved draft", async () => {
  const local = storage();
  const { store, teardown } = load(local);
  drafts.editComposerDraft(key("d"), { text: "private" });
  await store.saveDraft(key("d"));
  await Promise.all(teardown.map((close) => close()));
  assert.equal(
    Object.keys(local.values).filter((name) => name.startsWith("lonora.draft.v1:")).length,
    0,
  );
});

test("an edit in progress is never saved as text: a restart cannot turn it into a new message", async () => {
  const local = storage();
  const { store } = load(local);
  drafts.editComposerDraft(key("e"), { text: "the original, being edited" });
  store.markEditing(key("e"), true);
  await store.saveDraft(key("e"));
  assert.equal(
    Object.keys(local.values).filter((name) => name.startsWith("lonora.draft.v1:")).length,
    0,
  );
  store.markEditing(key("e"), false);
  await store.saveDraft(key("e"));
  assert.equal(
    Object.keys(local.values).filter((name) => name.startsWith("lonora.draft.v1:")).length,
    1,
  );
});

test("a draft sent or cleared in this run never comes back from the device, even before its save", async () => {
  const local = storage();
  const { store } = load(local);
  drafts.editComposerDraft(key("f"), { text: "foo" });
  await store.saveDraft(key("f"));
  // Sent: memory is empty; leaving and coming back before any save must not restore "foo".
  drafts.consumeComposerDraft(key("f"), drafts.composerDraft(key("f")).revision);
  assert.equal(await store.restoreDraft(key("f")), false);
  assert.equal(drafts.composerDraft(key("f")).text, "");
});

test("a draft too large to keep removes the older saved one", async () => {
  const local = storage();
  const { store } = load(local);
  drafts.editComposerDraft(key("g"), { text: "short" });
  await store.saveDraft(key("g"));
  drafts.editComposerDraft(key("g"), { text: "x".repeat(300 * 1024) });
  await store.saveDraft(key("g"));
  assert.equal(
    Object.keys(local.values).filter((name) => name.startsWith("lonora.draft.v1:")).length,
    0,
  );
});
