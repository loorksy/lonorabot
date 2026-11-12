// Mobile uploads, as on Web: each picked file uploads on its own with progress and a cancel;
// a finished file joins the draft's attachments; a message sent while files still upload
// waits for them and then goes out with their ids; cancelling drops the file or the message.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import type { Artifact } from "../../packages/contracts/src";

type Uploads = typeof import("../../apps/mobile/lib/composer-uploads");
type Drafts = typeof import("../../apps/mobile/lib/composer-drafts");

function load<T>(name: string, dependencies: Record<string, unknown>): T {
  const source = readFileSync(new URL(`../../apps/mobile/lib/${name}.ts`, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  const exports = {} as T;
  let counter = 0;
  runInNewContext(outputText, {
    exports,
    require(path: string) {
      if (!(path in dependencies)) throw new Error(`Unexpected module ${path}`);
      return dependencies[path];
    },
    crypto: { randomUUID: () => `upload-${++counter}` },
    setTimeout,
    AbortController,
  });
  return exports;
}

function fixture() {
  const lifecycle = { registerSessionTeardown: () => undefined };
  const drafts = load<Drafts>("composer-drafts", { "./session-lifecycle": lifecycle });
  const transfers: {
    name: string;
    progress: (p: number) => void;
    resolve: (row: Artifact) => void;
    reject: (cause: unknown) => void;
    signal: AbortSignal;
  }[] = [];
  const uploads = load<Uploads>("composer-uploads", {
    "./composer-drafts": drafts,
    "./session-lifecycle": lifecycle,
  });
  const transfer = (name: string) => (progress: (p: number) => void, signal: AbortSignal) =>
    new Promise<Artifact>((resolve, reject) => {
      transfers.push({ name, progress, resolve, reject, signal });
      signal.addEventListener("abort", () => reject(new Error("aborted")));
    });
  return { drafts, uploads, transfers, transfer };
}
const artifact = (id: string) => ({ id, payload: { name: id } }) as unknown as Artifact;
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("a finished upload joins the draft; progress moves; a cancelled one leaves no trace", async () => {
  const { drafts, uploads, transfers, transfer } = fixture();
  const one = uploads.startUpload(
    "k",
    { name: "a.pdf", size: 10, media_type: "application/pdf" },
    transfer("a"),
  );
  const two = uploads.startUpload(
    "k",
    { name: "b.png", size: 20, media_type: "image/png" },
    transfer("b"),
  );
  assert.equal(uploads.composerUploads("k").length, 2);
  transfers[0].progress(0.5);
  assert.equal(uploads.composerUploads("k")[0].p, 0.5);
  transfers[0].resolve(artifact("file-a"));
  await one.done;
  assert.equal(
    JSON.stringify(drafts.composerDraft("k").attachments.map((row) => row.id)),
    '["file-a"]',
  );
  uploads.cancelUpload("k", two.id);
  assert.equal(transfers[1].signal.aborted, true);
  await assert.rejects(two.done);
  await tick();
  assert.equal(uploads.composerUploads("k").length, 0);
  assert.equal(
    JSON.stringify(drafts.composerDraft("k").attachments.map((row) => row.id)),
    '["file-a"]',
  );
});

test("files handed to a sent message settle there, not in the draft", async () => {
  const { drafts, uploads, transfers, transfer } = fixture();
  uploads.startUpload(
    "k",
    { name: "a.pdf", size: 10, media_type: "application/pdf" },
    transfer("a"),
  );
  const handed = uploads.handOver("k");
  assert.equal(handed.length, 1);
  assert.equal(uploads.composerUploads("k").length, 0);
  transfers[0].resolve(artifact("file-a"));
  const rows = await Promise.all(handed.map((row) => row.done));
  assert.deepEqual(
    rows.map((row) => row.id),
    ["file-a"],
  );
  assert.equal(drafts.composerDraft("k").attachments.length, 0);
});

test("a send that was not admitted gives its files back: finished ones as attachments", async () => {
  const { drafts, uploads, transfers, transfer } = fixture();
  uploads.startUpload(
    "k",
    { name: "a.pdf", size: 10, media_type: "application/pdf" },
    transfer("a"),
  );
  uploads.startUpload(
    "k",
    { name: "b.pdf", size: 10, media_type: "application/pdf" },
    transfer("b"),
  );
  const handed = uploads.handOver("k");
  transfers[0].resolve(artifact("file-a"));
  await handed[0].done;
  uploads.handBack("k", handed);
  assert.equal(
    JSON.stringify(drafts.composerDraft("k").attachments.map((row) => row.id)),
    '["file-a"]',
  );
  assert.equal(uploads.composerUploads("k").length, 1);
  assert.equal(uploads.composerUploads("k")[0].name, "b.pdf");
  transfers[1].resolve(artifact("file-b"));
  await handed[1].done;
  assert.equal(
    JSON.stringify(drafts.composerDraft("k").attachments.map((row) => row.id)),
    '["file-a","file-b"]',
  );
  assert.equal(uploads.composerUploads("k").length, 0);
});
