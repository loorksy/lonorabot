// The host server over real HTTP: pages, security headers, the API, and the proxy's staff header.
import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { listen, openDb } from "../../host/server.mjs";

let server;
let base;
before(async () => {
  server = listen({ DB: openDb(), SITE_ORIGIN: "https://lonora.test", ADMIN_EMAILS: "staff@lonora.test" }, 0);
  await new Promise((resolve) => server.on("listening", resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => server.close());

test("serves the website and the admin page with the security headers", async () => {
  for (const [path, text] of [["/", "<html"], ["/admin/", "لوحة الإدارة"], ["/admin", "لوحة الإدارة"]]) {
    const res = await fetch(`${base}${path}`);
    assert.equal(res.status, 200, path);
    assert.match(res.headers.get("content-type"), /^text\/html/);
    assert.match(res.headers.get("content-security-policy"), /frame-ancestors 'none'/);
    assert.ok((await res.text()).includes(text));
  }
  assert.equal((await fetch(`${base}/nothing-here`)).status, 404);
  assert.equal((await fetch(`${base}/..%2F..%2Fschema.sql`)).status, 404);
});

test("routes the API to the handlers, and only lowercase route names", async () => {
  assert.equal((await fetch(`${base}/api/me`)).status, 401);
  assert.deepEqual(await (await fetch(`${base}/api/config`)).json(), { turnstile_site_key: null });
  assert.equal((await fetch(`${base}/api/_lib/core`)).status, 404);
  assert.equal((await fetch(`${base}/api/nope`)).status, 404);
  assert.equal((await fetch(`${base}/api/me`, { method: "DELETE" })).status, 405);
  assert.equal((await fetch(`${base}/api/register`, { method: "POST", body: "x".repeat(70_000) })).status, 413);
  assert.equal((await fetch(`${base}/api/admin/accounts`)).status, 403);
  const out = await (await fetch(`${base}/api/admin/accounts`, { headers: { "x-staff-email": "staff@lonora.test" } })).json();
  assert.deepEqual([out.ok, out.accounts, out.provisioning], [true, [], false]);
});
