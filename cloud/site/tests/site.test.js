import assert from "node:assert/strict";
import { beforeEach, describe, test } from "node:test";
import { csvCell } from "../functions/api/admin/export.js";
import { call, goodSignup, installFetch, makeEnv, staff as staffCall } from "./harness.js";

let env;
const logs = [];
beforeEach(async () => {
  env = makeEnv();
  await installFetch();
  logs.length = 0;
  for (const level of ["log", "info", "warn", "error"]) console[level] = (...a) => logs.push(a.join(" "));
});

async function signIn(email = "sara@example.com", password = "correct horse battery") {
  const res = await call(env, "POST", "/api/login", { json: { email, password, turnstile: "good" } });
  const cookie = (res.headers.get("set-cookie") || "").split(";")[0];
  return { res, cookie };
}

const staff = (method, path, opts = {}) => staffCall(env, method, path, opts);

const row = (email = "sara@example.com") => env.DB.raw.prepare("SELECT * FROM accounts WHERE email = ?").get(email);

describe("registration", () => {
  test("a valid signup creates a pending account with the document versions", async () => {
    const res = await call(env, "POST", "/api/register", { json: goodSignup() });
    assert.equal(res.status, 202);
    assert.deepEqual(await res.json(), { ok: true, next: "signin" });
    const a = row();
    assert.equal(a.status, "pending");
    assert.equal(a.country, "AE");
    assert.equal(a.terms_version, "t1");
    assert.equal(a.risk_version, "r1");
    assert.match(a.password_hash, /^pbkdf2-sha256\$100000\$/);
    assert.ok(!a.password_hash.includes("correct horse"));
  });

  test("a second signup with the same email gets the same answer and changes nothing", async () => {
    await call(env, "POST", "/api/register", { json: goodSignup() });
    const before = row();
    const res = await call(env, "POST", "/api/register", { json: goodSignup({ name: "intruder", password: "another password!" }), ip: "198.51.100.2" });
    assert.equal(res.status, 202);
    assert.deepEqual(await res.json(), { ok: true, next: "signin" });
    assert.deepEqual(row(), before);
  });

  for (const [field, value] of [
    ["email", "not-an-email"], ["email", `${"a".repeat(250)}@x.io`], ["name", ""], ["name", "x".repeat(81)],
    ["password", "short"], ["password", "x".repeat(129)], ["country", "ARE"], ["lang", "fr"], ["broker", "x".repeat(81)],
    ["uses", ["trade", "crypto"]], ["accept_terms", false], ["accept_risk", undefined],
  ]) {
    test(`invalid ${field} is refused and nothing is stored`, async () => {
      const res = await call(env, "POST", "/api/register", { json: goodSignup({ [field]: value }) });
      assert.equal(res.status, 400);
      assert.equal((await res.json()).field, field);
      assert.equal(env.DB.raw.prepare("SELECT count(*) n FROM accounts").get().n, 0);
    });
  }

  test("a filled honeypot gets the normal answer and stores nothing", async () => {
    const res = await call(env, "POST", "/api/register", { json: goodSignup({ website: "http://spam" }) });
    assert.equal(res.status, 202);
    assert.equal(env.DB.raw.prepare("SELECT count(*) n FROM accounts").get().n, 0);
  });

  test("a failed or missing Turnstile is refused", async () => {
    assert.equal((await call(env, "POST", "/api/register", { json: goodSignup({ turnstile: "bad" }) })).status, 400);
    assert.equal((await call(env, "POST", "/api/register", { json: goodSignup({ turnstile: undefined }) })).status, 400);
  });

  test("without a Turnstile secret the check is off and signup still works", async () => {
    env = makeEnv({ TURNSTILE_SECRET: "" });
    assert.equal((await call(env, "POST", "/api/register", { json: goodSignup({ turnstile: undefined }) })).status, 202);
  });

  test("another origin, or no origin, is refused", async () => {
    assert.equal((await call(env, "POST", "/api/register", { json: goodSignup(), origin: "https://evil.test" })).status, 403);
    assert.equal((await call(env, "POST", "/api/register", { json: goodSignup(), origin: null })).status, 403);
  });

  test("more than 5 signups an hour from one address are refused", async () => {
    for (let i = 0; i < 5; i++) {
      assert.equal((await call(env, "POST", "/api/register", { json: goodSignup({ email: `u${i}@example.com` }) })).status, 202);
    }
    assert.equal((await call(env, "POST", "/api/register", { json: goodSignup({ email: "u9@example.com" }) })).status, 429);
    assert.equal((await call(env, "POST", "/api/register", { json: goodSignup({ email: "u9@example.com" }), ip: "198.51.100.9" })).status, 202);
  });

  test("an oversized or non-object body is refused", async () => {
    assert.equal((await call(env, "POST", "/api/register", { json: "x".repeat(9000) })).status, 400);
    assert.equal((await call(env, "POST", "/api/register", { json: "[1,2]" })).status, 400);
  });

  test("nothing personal reaches the logs", async () => {
    await call(env, "POST", "/api/register", { json: goodSignup() });
    await signIn();
    await signIn("sara@example.com", "wrong password!!");
    const all = logs.join("\n");
    for (const secret of ["sara@example.com", "Sara@Example.com", "correct horse", "wrong password", "سارة"]) assert.ok(!all.includes(secret));
  });
});

describe("portal sign-in and account page", () => {
  beforeEach(async () => {
    await call(env, "POST", "/api/register", { json: goodSignup() });
  });

  test("sign-in sets a secure session cookie and /api/me shows the pending status", async () => {
    const { res, cookie } = await signIn("SARA@example.com");
    assert.equal(res.status, 200);
    const set = res.headers.get("set-cookie");
    for (const part of ["__Host-lonora_session=", "HttpOnly", "Secure", "SameSite=Lax", "Path=/"]) assert.ok(set.includes(part), part);
    const me = await (await call(env, "GET", "/api/me", { cookie })).json();
    assert.equal(me.account.status, "pending");
    assert.equal(me.account.instance_url, null);
    assert.equal(me.account.setup_link, null);
    assert.equal(me.account.password_hash, undefined);
  });

  test("a wrong password and an unknown email give the same answer", async () => {
    const a = await signIn("sara@example.com", "wrong password!!");
    const b = await signIn("nobody@example.com", "wrong password!!");
    assert.equal(a.res.status, 401);
    assert.equal(b.res.status, 401);
    assert.deepEqual(await a.res.json(), await b.res.json());
  });

  test("sign-in attempts per email are limited", async () => {
    for (let i = 0; i < 8; i++) await signIn("sara@example.com", "wrong password!!");
    assert.equal((await signIn()).res.status, 429);
  });

  test("logout ends the session", async () => {
    const { cookie } = await signIn();
    assert.equal((await call(env, "POST", "/api/logout", { cookie })).status, 200);
    assert.equal((await call(env, "GET", "/api/me", { cookie })).status, 401);
  });

  test("a forged or expired session is signed out", async () => {
    assert.equal((await call(env, "GET", "/api/me", { cookie: `__Host-lonora_session=${"a".repeat(64)}` })).status, 401);
    const { cookie } = await signIn();
    env.DB.raw.exec("UPDATE sessions SET expires_at = '2000-01-01T00:00:00Z'");
    assert.equal((await call(env, "GET", "/api/me", { cookie })).status, 401);
  });
});

describe("admin panel", () => {
  beforeEach(async () => {
    await call(env, "POST", "/api/register", { json: goodSignup() });
  });

  test("admin endpoints refuse requests without a signed-in staff email", async () => {
    assert.equal((await call(env, "GET", "/api/admin/accounts")).status, 403);
    assert.equal((await call(env, "GET", "/api/admin/accounts", { headers: { "x-staff-email": "stranger@lonora.test" } })).status, 403);
    assert.equal((await call(env, "POST", "/api/admin/decide", { json: { id: row().id, action: "approve" } })).status, 403);
    assert.equal(row().status, "pending");
    assert.equal((await call(env, "GET", "/api/admin/accounts", { headers: { "x-staff-email": "STAFF@lonora.test" } })).status, 200);
  });

  test("staff list pending accounts with counts and search", async () => {
    const out = await (await staff("GET", "/api/admin/accounts", { query: "?status=pending&q=sara" })).json();
    assert.equal(out.accounts.length, 1);
    assert.deepEqual(out.accounts[0].uses, ["trade", "brief"]);
    assert.equal(out.accounts[0].password_hash, undefined);
    assert.equal(out.counts.pending, 1);
    const none = await (await staff("GET", "/api/admin/accounts", { query: "?q=%25" })).json();
    assert.equal(none.accounts.length, 0);
  });

  test("approve then activate shows the customer the instance and the setup link", async () => {
    const id = row().id;
    assert.equal((await staff("POST", "/api/admin/decide", { json: { id, action: "approve" } })).status, 200);
    assert.equal(row().status, "approved");
    const bad = await staff("POST", "/api/admin/decide", { json: { id, action: "activate", instance_url: "http://sara.lonora.app" } });
    assert.equal(bad.status, 400);
    const ok = await staff("POST", "/api/admin/decide", {
      json: { id, action: "activate", instance_url: "https://sara.lonora.app", setup_link: "https://sara.lonora.app/#token=abc" },
    });
    assert.equal(ok.status, 200);
    const { cookie } = await signIn();
    const me = (await (await call(env, "GET", "/api/me", { cookie })).json()).account;
    assert.equal(me.status, "active");
    assert.equal(me.instance_url, "https://sara.lonora.app/");
    assert.equal(me.setup_link, "https://sara.lonora.app/#token=abc");
    assert.equal(row().decided_by, "staff@lonora.test");
  });

  test("reject and suspend need a reason the customer sees; illegal moves are refused", async () => {
    const id = row().id;
    assert.equal((await staff("POST", "/api/admin/decide", { json: { id, action: "suspend", reason: "x" } })).status, 409);
    assert.equal((await staff("POST", "/api/admin/decide", { json: { id, action: "reject" } })).status, 400);
    assert.equal((await staff("POST", "/api/admin/decide", { json: { id, action: "reject", reason: "خارج الدول المخدومة" } })).status, 200);
    const { cookie } = await signIn();
    const me = (await (await call(env, "GET", "/api/me", { cookie })).json()).account;
    assert.equal(me.status, "rejected");
    assert.equal(me.reason, "خارج الدول المخدومة");
    assert.equal((await staff("POST", "/api/admin/decide", { json: { id, action: "approve" } })).status, 409);
    assert.equal((await staff("POST", "/api/admin/decide", { json: { id, action: "fly" } })).status, 400);
  });

  test("a decision from another origin is refused", async () => {
    const id = row().id;
    assert.equal((await staff("POST", "/api/admin/decide", { json: { id, action: "approve" }, origin: "https://evil.test" })).status, 403);
    assert.equal(row().status, "pending");
  });

  test("every decision is in the audit log with the staff email", async () => {
    const id = row().id;
    await staff("POST", "/api/admin/decide", { json: { id, action: "approve" } });
    await staff("POST", "/api/admin/decide", { json: { id, action: "activate", instance_url: "https://sara.lonora.app" } });
    await staff("POST", "/api/admin/decide", { json: { id, action: "suspend", reason: "non-payment" } });
    await staff("POST", "/api/admin/decide", { json: { id, action: "reinstate" } });
    const log = await (await staff("GET", "/api/admin/audit", { query: `?account=${id}` })).json();
    assert.deepEqual(log.entries.map((e) => e.action).sort(), ["activate", "approve", "registered", "reinstate", "suspend"].sort());
    assert.ok(log.entries.filter((e) => e.action !== "registered").every((e) => e.actor === "staff@lonora.test"));
  });

  test("deletion on request removes the account and its sessions and keeps only a hash", async () => {
    const { cookie } = await signIn();
    const id = row().id;
    assert.equal((await staff("POST", "/api/admin/decide", { json: { id, action: "delete" } })).status, 200);
    assert.equal(row(), undefined);
    assert.equal(env.DB.raw.prepare("SELECT count(*) n FROM sessions").get().n, 0);
    assert.equal((await call(env, "GET", "/api/me", { cookie })).status, 401);
    const entry = env.DB.raw.prepare("SELECT details FROM audit WHERE action = 'deleted'").get();
    assert.ok(!entry.details.includes("sara@example.com"));
  });

  test("the CSV export neutralises formulas and is audited", async () => {
    await call(env, "POST", "/api/register", { json: goodSignup({ email: "x@example.com", name: "=HYPERLINK(\"http://evil\")" }), ip: "198.51.100.3" });
    const res = await staff("GET", "/api/admin/export");
    assert.equal(res.status, 200);
    const text = await res.text();
    assert.ok(!/,=HYPERLINK/.test(text));
    assert.ok(text.includes(`"'=HYPERLINK(""http://evil"")"`));
    assert.equal(csvCell("+1"), `"'+1"`);
    assert.equal(csvCell("-1"), `"'-1"`);
    assert.equal(csvCell("@x"), `"'@x"`);
    assert.equal(csvCell("plain"), "plain");
    assert.ok(env.DB.raw.prepare("SELECT count(*) n FROM audit WHERE action = 'exported'").get().n === 1);
  });
});
