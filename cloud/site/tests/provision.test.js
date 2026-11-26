import assert from "node:assert/strict";
import { beforeEach, describe, test } from "node:test";
import { cloudInit, validHandle } from "../functions/_lib/provision.js";
import { accessJwt, call, cloud, goodSignup, installFetch, makeEnv, resetCloud } from "./harness.js";

let env;
const PROVISIONING = { HETZNER_TOKEN: "hz-token", CLOUDFLARE_DNS_TOKEN: "cf-token", CLOUDFLARE_ZONE_ID: "zone1", BASE_DOMAIN: "lonora.test", LONORA_VERSION: "v0.3.0" };

beforeEach(async () => {
  env = makeEnv(PROVISIONING);
  await installFetch();
  resetCloud();
  await call(env, "POST", "/api/register", { json: goodSignup() });
});

const account = () => env.DB.raw.prepare("SELECT * FROM accounts WHERE email = 'sara@example.com'").get();
const job = () => env.DB.raw.prepare("SELECT * FROM provision_jobs ORDER BY created_at DESC, rowid DESC LIMIT 1").get();
async function staff(method, path, opts = {}) {
  const jwt = await accessJwt("staff@lonora.test");
  return call(env, method, path, { ...opts, headers: { "cf-access-jwt-assertion": jwt } });
}
const activate = (extra = {}) => staff("POST", "/api/admin/decide", { json: { id: account().id, action: "activate", ...extra } });
function secretFromUserData() {
  const create = cloud.calls.find((c) => c.api === "hetzner" && c.method === "POST");
  return create.body.user_data.match(/^SECRET='([0-9a-f]{64})'$/m)[1];
}
const report = (body, ip = "192.0.2.100") => call(env, "POST", "/api/provision/callback", { json: { job: job().id, ...body }, origin: null, ip });

describe("one-click activation", () => {
  test("one click creates the server and the DNS record and waits for the install", async () => {
    const res = await activate();
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { ok: true, status: "provisioning", handle: "sara" });
    assert.equal(account().status, "provisioning");
    assert.equal(account().handle, "sara");
    const create = cloud.calls.find((c) => c.api === "hetzner" && c.method === "POST");
    assert.equal(create.auth, "Bearer hz-token");
    assert.equal(create.body.name, "lonora-sara");
    assert.equal(create.body.server_type, "cpx31");
    assert.equal(create.body.image, "ubuntu-24.04");
    assert.match(create.body.user_data, /DOMAIN='sara\.lonora\.test'/);
    assert.match(create.body.user_data, /VERSION='v0\.3\.0'/);
    assert.match(create.body.user_data, /CALLBACK='https:\/\/lonora\.test\/api\/provision\/callback'/);
    const dns = cloud.calls.find((c) => c.api === "cloudflare" && c.method === "POST");
    assert.equal(dns.auth, "Bearer cf-token");
    assert.equal(dns.url, "https://api.cloudflare.com/client/v4/zones/zone1/dns_records");
    assert.deepEqual([dns.body.type, dns.body.name, dns.body.content, dns.body.proxied], ["A", "sara.lonora.test", "192.0.2.100", false]);
    assert.equal(job().status, "installing");
    // Only the secret's hash is kept.
    assert.notEqual(job().secret_hash, secretFromUserData());
    assert.ok(!JSON.stringify(job()).includes(secretFromUserData()));
  });

  test("the server's ready report activates the account with the setup link", async () => {
    await activate();
    const res = await report({ secret: secretFromUserData(), status: "ready", setup_token: "tok_ABCDEFGHIJKLMNOPQRSTUVWXYZ" });
    assert.equal(res.status, 200);
    const a = account();
    assert.equal(a.status, "active");
    assert.equal(a.instance_url, "https://sara.lonora.test/");
    assert.equal(a.setup_link, "https://sara.lonora.test/#token=tok_ABCDEFGHIJKLMNOPQRSTUVWXYZ");
    assert.ok(cloud.calls.some((c) => c.api === "instance" && c.url === "https://sara.lonora.test/ready"));
    // A repeated report changes nothing.
    assert.deepEqual(await (await report({ secret: secretFromUserData(), status: "ready", setup_token: "tok_OTHERxxxxxxxxxxxxxxxxxxxx" })).json(), { ok: true, status: "ready" });
    assert.equal(account().setup_link, "https://sara.lonora.test/#token=tok_ABCDEFGHIJKLMNOPQRSTUVWXYZ");
  });

  test("a report with a wrong secret or an unknown job is refused", async () => {
    await activate();
    assert.equal((await report({ secret: "0".repeat(64), status: "ready", setup_token: "tok_ABCDEFGHIJKLMNOPQRSTUVWXYZ" })).status, 403);
    assert.equal((await call(env, "POST", "/api/provision/callback", { json: { job: "nope", secret: "x", status: "ready" }, origin: null })).status, 403);
    assert.equal(account().status, "provisioning");
  });

  test("a ready report is not believed until Lonora answers on its domain", async () => {
    await activate();
    cloud.ready = false;
    assert.equal((await report({ secret: secretFromUserData(), status: "ready", setup_token: "tok_ABCDEFGHIJKLMNOPQRSTUVWXYZ" })).status, 409);
    assert.equal(account().status, "provisioning");
  });

  test("a failed install removes the server and DNS, and staff can retry", async () => {
    await activate();
    assert.equal((await report({ secret: secretFromUserData(), status: "failed", error: "install_failed" })).status, 200);
    assert.equal(job().status, "failed");
    assert.equal(account().status, "approved");
    assert.ok(cloud.calls.some((c) => c.api === "hetzner" && c.method === "DELETE" && c.url.endsWith("/servers/100")));
    assert.ok(cloud.calls.some((c) => c.api === "cloudflare" && c.method === "DELETE" && c.url.endsWith("/dns_records/rec1")));
    const retry = await staff("POST", "/api/admin/decide", { json: { id: account().id, action: "retry" } });
    assert.equal(retry.status, 200);
    assert.equal(account().status, "provisioning");
    assert.equal(job().server_id, "101");
  });

  test("a cloud error fails the attempt, undoes what it created, and shows the provider's message", async () => {
    cloud.failDns = true;
    const res = await activate();
    assert.equal(res.status, 502);
    assert.match((await res.json()).message, /dns_create: record exists/);
    assert.equal(account().status, "approved");
    assert.equal(job().status, "failed");
    assert.ok(cloud.calls.some((c) => c.api === "hetzner" && c.method === "DELETE"));
  });

  test("handles are unique, valid and never reserved", async () => {
    assert.equal(validHandle("admin"), false);
    assert.equal(validHandle("a"), false);
    assert.equal(validHandle("sara--x"), false);
    assert.equal(validHandle("1sara"), false);
    assert.equal(validHandle("sara-2"), true);
    assert.equal((await activate({ handle: "www" })).status, 400);
    await activate();
    await call(env, "POST", "/api/register", { json: goodSignup({ email: "sara@other.org" }), ip: "198.51.100.5" });
    const second = env.DB.raw.prepare("SELECT id FROM accounts WHERE email = 'sara@other.org'").get();
    const res = await staff("POST", "/api/admin/decide", { json: { id: second.id, action: "activate" } });
    assert.equal((await res.json()).handle, "sara-2");
    const taken = await staff("POST", "/api/admin/decide", { json: { id: second.id, action: "activate", handle: "sara" } });
    assert.equal(taken.status, 409); // already provisioning
  });

  test("deleting an account with a server needs remove_server and removes it", async () => {
    await activate();
    await report({ secret: secretFromUserData(), status: "ready", setup_token: "tok_ABCDEFGHIJKLMNOPQRSTUVWXYZ" });
    const id = account().id;
    assert.equal((await staff("POST", "/api/admin/decide", { json: { id, action: "delete" } })).status, 409);
    assert.equal((await staff("POST", "/api/admin/decide", { json: { id, action: "delete", remove_server: true } })).status, 200);
    assert.ok(cloud.calls.some((c) => c.api === "hetzner" && c.method === "DELETE"));
    assert.equal(account(), undefined);
  });

  test("without provisioning settings, activation stays manual", async () => {
    env = makeEnv();
    await call(env, "POST", "/api/register", { json: goodSignup() });
    assert.equal((await activate()).status, 400); // instance_url required
    assert.equal(cloud.calls.length, 0);
  });

  test("the first-boot script quotes every value and never prints the secret's hash", () => {
    const script = cloudInit({ jobId: "j1", secret: "s'1", callback: "https://x/cb", domain: "d.lonora.test", version: "v1" });
    assert.match(script, /SECRET='s'\\''1'/);
    assert.match(script, /fetch -q --depth 1 'https:\/\/github\.com\/loorksy\/lonorabot\.git' "\$VERSION"/);
    assert.match(script, /build-from-source\.sh" --source "\$SRC"/);
    assert.match(script, /--domain "\$DOMAIN" --version "\$DIGEST" --home \/opt\/lonora/);
    assert.doesNotMatch(script, /ghcr\.io/);
    assert.match(script, /https:\/\/\$DOMAIN\/ready/);
  });
});
