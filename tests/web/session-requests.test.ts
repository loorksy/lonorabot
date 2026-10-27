import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import { ReadRequestGate } from "../../packages/core/src/read-request-gate";

type Client = typeof import("../../apps/web/src/lib/api");
function fixture() {
  const window = new EventTarget();
  const document = Object.assign(new EventTarget(), {
    cookie: "lonora_csrf=token",
    visibilityState: "visible",
  });
  const waiting: {
    init: RequestInit;
    resolve: (response: Response) => void;
    reject: (error: Error) => void;
  }[] = [];
  const exports = {} as Client;
  const source = readFileSync(new URL("../../apps/web/src/lib/api.ts", import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  runInNewContext(outputText, {
    exports,
    require(name: string) {
      if (name === "@lonora/core") return { ReadRequestGate };
      throw new Error(`Unexpected module ${name}`);
    },
    window,
    document,
    Headers,
    FormData,
    Event,
    AbortController,
    CustomEvent: class extends Event {},
    fetch: (_url: string, init: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        waiting.push({ init, resolve, reject });
        init.signal?.addEventListener("abort", () => reject(new Error("aborted")));
      }),
  });
  return { client: exports, window, document, waiting };
}

test("concurrent projections share one read but always revalidate after completion", async () => {
  const { client, waiting } = fixture();
  const a = client.api.get("/agents");
  const b = client.api.get("/agents");
  assert.equal(waiting.length, 1);
  waiting[0].resolve(new Response("[]"));
  await Promise.all([a, b]);
  const next = client.api.get("/agents");
  assert.equal(waiting.length, 2);
  waiting[1].resolve(new Response("[]"));
  await next;
});

test("old session cannot return data or expire its replacement", async () => {
  const { client, window, waiting } = fixture();
  let expired = 0;
  window.addEventListener("lonora:session-expired", () => expired++);
  const old = client.api.get("/agents");
  const check = assert.rejects(old, client.RequestCancelled);
  client.resetSessionRequests();
  waiting[0].resolve(new Response('{"code":"unauthorized"}', { status: 401 }));
  await check;
  assert.equal(expired, 0);
  const fresh = client.api.get("/agents");
  waiting[1].resolve(new Response('[{"id":"new-owner"}]'));
  assert.deepEqual(await fresh, [{ id: "new-owner" }]);
});

test("session replacement fences even a response body already being read", async () => {
  const { client, waiting } = fixture();
  let finish!: (value: unknown) => void;
  let started!: () => void;
  const bodyStarted = new Promise<void>((resolve) => {
    started = resolve;
  });
  const request = client.api.get("/agents");
  const check = assert.rejects(request, client.RequestCancelled);
  waiting[0].resolve({
    ok: true,
    json: () =>
      new Promise((resolve) => {
        finish = resolve;
        started();
      }),
  } as Response);
  await bodyStarted;
  client.resetSessionRequests();
  finish([{ id: "old-owner" }]);
  await check;
});

test("background reads cancel silently while writes keep the broker's actual result", async () => {
  const { client, waiting, document } = fixture();
  const read = client.api.get("/threads/inbox");
  const check = assert.rejects(read, client.RequestCancelled);
  const trade = client.api.post("/trading/approvals/a/decision", { decision: "approve" });
  document.visibilityState = "hidden";
  document.dispatchEvent(new Event("visibilitychange"));
  await check;
  assert.equal(waiting[1].init.signal?.aborted, false);
  waiting[1].resolve(new Response('{"status":"confirmed"}'));
  assert.deepEqual(await trade, { status: "confirmed" });
});

test("explicit abort is distinct from real network and server failures", async () => {
  const { client, waiting } = fixture();
  const signal = new AbortController();
  const cancel = client.request("/agents", { signal: signal.signal });
  const check = assert.rejects(cancel, client.RequestCancelled);
  signal.abort();
  await check;
  const network = client.api.get("/agents");
  const networkCheck = assert.rejects(network, /offline/);
  waiting[1].reject(new Error("offline"));
  await networkCheck;
  const rejected = client.api.get("/agents");
  const serverCheck = assert.rejects(
    rejected,
    (error: unknown) => error instanceof client.ApiError && error.code === "broker_market_closed",
  );
  waiting[2].resolve(new Response('{"code":"broker_market_closed"}', { status: 409 }));
  await serverCheck;
});

test("background startup retains bootstrap and session authentication", async () => {
  const { client, waiting, document } = fixture();
  const bootstrap = client.api.get("/onboarding");
  const auth = client.api.get("/auth/session");
  document.visibilityState = "hidden";
  document.dispatchEvent(new Event("visibilitychange"));
  assert.ok(waiting.every((entry) => !entry.init.signal?.aborted));
  waiting[0].resolve(new Response('{"owner_initialized":true}'));
  waiting[1].resolve(new Response('{"id":"owner-a"}'));
  await Promise.all([bootstrap, auth]);
});

test("Send starts while slow projection reads fill their bounded slots", async () => {
  const { client, waiting } = fixture();
  const reads = Array.from({ length: 7 }, (_, i) => client.api.get(`/projection/${i}`));
  assert.equal(waiting.length, 3);
  const sent = client.api.post("/threads/chat/messages", { content: "Hello" });
  assert.equal(waiting.length, 4);
  assert.equal(waiting[3].init.method, "POST");
  assert.equal(waiting[3].init.priority, "high");
  waiting[3].resolve(new Response('{"accepted":true}'));
  assert.deepEqual(await sent, { accepted: true });
  // No projection has finished; the message was still sent and acknowledged.
  assert.equal(waiting.length, 4);
  const resolved = new Set<number>([3]);
  for (let round = 0; round < 7; round++) {
    for (let i = 0; i < waiting.length; i++) {
      if (resolved.has(i)) continue;
      resolved.add(i);
      waiting[i].resolve(new Response("[]"));
    }
    await new Promise((resolve) => setImmediate(resolve));
  }
  await Promise.all(reads);
  assert.equal(waiting.length, 8);
});
