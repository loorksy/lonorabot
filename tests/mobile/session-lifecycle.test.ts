import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import { ApiError } from "../../apps/mobile/lib/api-error";

type Client = typeof import("../../apps/mobile/lib/api");
function fixture() {
  const waiting: {
    init: RequestInit;
    resolve: (response: Response) => void;
    reject: (error: Error) => void;
  }[] = [];
  const timers: (() => void)[] = [];
  let expired = 0;
  const exports = {} as Client;
  const source = readFileSync(new URL("../../apps/mobile/lib/api.ts", import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  runInNewContext(outputText, {
    exports,
    require(name: string) {
      if (name === "react-native") return { Platform: { OS: "android" } };
      if (name === "./api-error") return { ApiError };
      if (name === "@lonora/core") return { attachmentTooLarge: () => false };
      throw new Error(`Unexpected module ${name}`);
    },
    Headers,
    FormData,
    URL,
    AbortController,
    setTimeout: (callback: () => void) => timers.push(callback),
    clearTimeout: () => {},
    fetch: (_url: string, init: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        waiting.push({ init, resolve, reject });
        init.signal?.addEventListener("abort", () => reject(new Error("aborted")));
      }),
  });
  exports.configureApi("https://example.test", "owner-a", () => {
    expired += 1;
    exports.setCredentials(null);
  });
  return { client: exports, waiting, timers, expired: () => expired };
}

test("logout cancels pending reads and financial requests without returning stale results", async () => {
  const { client, waiting } = fixture();
  const read = client.api.get("/agents");
  const trade = client.api.post("/trading/approvals/a/approve", {});
  const checks = [read, trade].map((request) =>
    assert.rejects(request, client.SessionRequestCancelled),
  );
  client.cancelSessionRequests();
  assert.ok(waiting.every((request) => request.init.signal?.aborted));
  await Promise.all(checks);
});

test("new account never consumes old account response or expires the new session", async () => {
  const { client, waiting, expired } = fixture();
  const request = client.api.get("/agents");
  const check = assert.rejects(request, client.SessionRequestCancelled);
  client.configureApi("https://other.test", "owner-b", () => assert.fail("new owner expired"));
  waiting[0].resolve(new Response(JSON.stringify({ code: "unauthorized" }), { status: 401 }));
  await check;
  assert.equal(expired(), 0);
  const fresh = client.api.get<{ id: string }>("/auth/session");
  waiting[1].resolve(new Response(JSON.stringify({ id: "owner-b" })));
  assert.equal((await fresh).id, "owner-b");
  assert.equal(new Headers(waiting[1].init.headers).get("Authorization"), "Bearer owner-b");
});

test("background cancels reads, preserves in-flight mutations, foreground reads work", async () => {
  const { client, waiting } = fixture();
  const read = client.api.get("/threads/inbox");
  const check = assert.rejects(read, client.SessionRequestCancelled);
  const trade = client.api.post("/trading/approvals/a/approve", {});
  client.cancelBackgroundReads();
  await check;
  assert.equal(waiting[1].init.signal?.aborted, false);
  waiting[1].resolve(new Response(JSON.stringify({ status: "confirmed" })));
  await trade;
  const foreground = client.api.get("/threads/inbox");
  waiting[2].resolve(new Response("[]"));
  await foreground;
});

test("explicit abort is silent lifecycle cancellation but timeout and genuine errors are not", async () => {
  const { client, waiting, timers } = fixture();
  const controller = new AbortController();
  const pending = client.request("/agents", { signal: controller.signal });
  const cancelled = assert.rejects(pending, client.SessionRequestCancelled);
  controller.abort();
  await cancelled;
  const timeout = client.api.get("/agents");
  const timedOut = assert.rejects(
    timeout,
    (error: unknown) =>
      error instanceof Error && !(error instanceof client.SessionRequestCancelled),
  );
  timers[1]();
  await timedOut;
  const unavailable = client.api.get("/agents");
  const failed = assert.rejects(
    unavailable,
    (error: unknown) => error instanceof ApiError && error.code === "broker_connection_unavailable",
  );
  waiting[2].resolve(
    new Response(JSON.stringify({ code: "broker_connection_unavailable" }), { status: 503 }),
  );
  await failed;
});

test("session replacement while response body parses cannot return another owner's data", async () => {
  const { client, waiting } = fixture();
  let release: (value: unknown) => void = () => {};
  const body = new Promise((resolve) => {
    release = resolve;
  });
  const request = client.api.get("/agents");
  const check = assert.rejects(request, client.SessionRequestCancelled);
  waiting[0].resolve({ ok: true, json: () => body } as Response);
  await Promise.resolve();
  client.setCredentials("owner-b");
  release([{ id: "owner-a-private-agent" }]);
  await check;
});

test("all registered resources close even if one teardown throws synchronously", async () => {
  const { registerSessionTeardown, closeSessionResources } = await import(
    "../../apps/mobile/lib/session-lifecycle"
  );
  let closed = false;
  const removeBroken = registerSessionTeardown(() => {
    throw new Error("broken resource");
  });
  const removeGood = registerSessionTeardown(async () => {
    closed = true;
  });
  try {
    await assert.rejects(closeSessionResources(), /broken resource/);
    assert.equal(closed, true);
  } finally {
    removeBroken();
    removeGood();
  }
});

test("backgrounding during initial authentication does not fabricate a signed-out state", async () => {
  const { client, waiting } = fixture();
  const auth = client.api.get<{ id: string }>("/auth/session");
  client.cancelBackgroundReads();
  assert.equal(waiting[0].init.signal?.aborted, false);
  waiting[0].resolve(new Response('{"id":"owner-a"}'));
  assert.equal((await auth).id, "owner-a");
});
