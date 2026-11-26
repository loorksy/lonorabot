// One-click activation on the shared host (PW-T7), with cloud/host/customer.sh in dry-run mode: the
// real script runs, writes into a scratch host folder, and prints its Docker commands instead.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { beforeEach, describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { validHandle } from "../functions/_lib/provision.js";
import { call, goodSignup, installFetch, makeEnv, staff } from "./harness.js";

const SCRIPT = path.join(path.dirname(fileURLToPath(import.meta.url)), "../../host/customer.sh");
let env;
let home;

beforeEach(async () => {
  home = fs.mkdtempSync(path.join(os.tmpdir(), "lonora-host-"));
  fs.writeFileSync(path.join(home, "host.env"), "BASE_DOMAIN=lonora.test\n");
  fs.writeFileSync(path.join(home, "release.env"), "LONORA_IMAGE=127.0.0.1:5055/lonora@sha256:r1\n");
  process.env.LONORA_HOST_HOME = home;
  env = makeEnv({ HOST_SCRIPT: SCRIPT, HOST_DRY_RUN: "1", BASE_DOMAIN: "lonora.test" });
  await installFetch();
  await call(env, "POST", "/api/register", { json: goodSignup() });
});

const account = (email = "sara@example.com") => env.DB.raw.prepare("SELECT * FROM accounts WHERE email = ?").get(email);
const job = () => env.DB.raw.prepare("SELECT * FROM provision_jobs ORDER BY created_at DESC, rowid DESC LIMIT 1").get();
const activate = (extra = {}, id = account().id) => staff(env, "POST", "/api/admin/decide", { json: { id, action: "activate", ...extra } });
const envFile = (handle) => fs.readFileSync(path.join(home, "customers", handle, ".env"), "utf8");
const setting = (handle, name) => envFile(handle).match(new RegExp(`^${name}=(.*)$`, "m"))[1];
const script = (...args) => spawnSync("bash", [SCRIPT, "--dry-run", ...args], { encoding: "utf8", env: { ...process.env, LONORA_HOST_HOME: home } });

describe("one-click activation on the host", () => {
  test("one click creates the customer's installation and activates the account with its setup link", async () => {
    const res = await activate();
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { ok: true, status: "active", handle: "sara" });
    const a = account();
    assert.equal(a.status, "active");
    assert.equal(a.instance_url, "https://sara.lonora.test/");
    assert.equal(a.setup_link, `https://sara.lonora.test/#token=${setting("sara", "LONORA_BOOTSTRAP_TOKEN")}`);
    assert.deepEqual([job().status, job().server_id], ["ready", "lonora-sara"]);
    // Its own key and database, in a file only root can read; and its route in the proxy.
    assert.equal(fs.statSync(path.join(home, "customers/sara/.env")).mode & 0o777, 0o600);
    assert.match(setting("sara", "LONORA_ENCRYPTION_KEY"), /^[A-Za-z0-9_-]{43}=$/);
    assert.match(setting("sara", "LONORA_DATABASE_URL"), /^postgresql\+asyncpg:\/\/lonora_sara:[A-Za-z0-9_-]{32}@lonora-postgres:5432\/lonora_sara$/);
    assert.match(fs.readFileSync(path.join(home, "caddy/customers/sara.caddy"), "utf8"), /^sara\.lonora\.test \{\n\timport customer lonora-sara-api\n\}/);
  });

  test("the script prints its Docker commands and never a key or a password", () => {
    const out = script("create", "bob");
    assert.equal(out.status, 0, out.stderr);
    assert.match(out.stdout, /^setup_link=https:\/\/bob\.lonora\.test\/#token=[A-Za-z0-9_-]{43}\n$/);
    assert.match(out.stderr, /would run: docker exec -i lonora-postgres psql/);
    assert.match(out.stderr, /would run: docker compose .*--profile on-demand up -d --wait api gateway/);
    assert.match(out.stderr, /would run: docker exec lonora-caddy caddy reload/);
    const password = setting("bob", "LONORA_DATABASE_URL").match(/:([^:@]+)@/)[1];
    for (const secret of [setting("bob", "LONORA_ENCRYPTION_KEY"), setting("bob", "LONORA_WEBHOOK_SECRET"), password]) {
      assert.ok(!out.stdout.includes(secret) && !out.stderr.includes(secret));
    }
    assert.notEqual(script("create", "bob").status, 0); // never twice
    assert.notEqual(script("create", "../etc").status, 0);
    assert.ok(!fs.existsSync(path.join(home, "etc")));
  });

  test("a release is built once and switches every customer", () => {
    for (const h of ["ann", "bob"]) assert.equal(script("create", h).status, 0);
    const out = script("release", "v0.4.0");
    assert.equal(out.status, 0, out.stderr);
    assert.equal(out.stderr.match(/Building the release image once/g).length, 1);
    assert.equal(out.stderr.match(/up -d --wait api gateway/g).length, 2);
    assert.match(fs.readFileSync(path.join(home, "release.env"), "utf8"), /^LONORA_IMAGE=127\.0\.0\.1:5055\/lonora@sha256:/);
  });

  test("a failed attempt removes what it made, shows why, and staff can retry", async () => {
    fs.rmSync(path.join(home, "release.env"));
    const res = await activate();
    assert.equal(res.status, 502);
    assert.match((await res.json()).message, /No release yet/);
    assert.equal(account().status, "approved");
    assert.equal(job().status, "failed");
    fs.writeFileSync(path.join(home, "release.env"), "LONORA_IMAGE=127.0.0.1:5055/lonora@sha256:r1\n");
    assert.equal((await staff(env, "POST", "/api/admin/decide", { json: { id: account().id, action: "retry" } })).status, 200);
    assert.equal(account().status, "active");
  });

  test("an activation never removes an installation it did not make", async () => {
    assert.equal(script("create", "sara").status, 0); // made by hand, so no account holds the handle
    const res = await activate();
    assert.equal(res.status, 502);
    assert.match((await res.json()).message, /sara already exists; choose another handle/);
    assert.deepEqual([job().status, job().server_id], ["failed", null]);
    assert.equal((await staff(env, "POST", "/api/admin/decide", { json: { id: account().id, action: "delete" } })).status, 200);
    assert.ok(fs.existsSync(path.join(home, "customers/sara/.env")));
  });

  test("two overlapping activations make one installation and one job", async () => {
    const [a, b] = await Promise.all([activate(), activate()]);
    assert.deepEqual([a.status, b.status].sort(), [200, 409]);
    assert.equal(env.DB.raw.prepare("SELECT count(*) n FROM provision_jobs").get().n, 1);
    assert.equal(account().status, "active");
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
    const second = account("sara@other.org").id;
    assert.equal((await activate({ handle: "sara" }, second)).status, 400); // handle_taken
    assert.equal((await (await activate({}, second)).json()).handle, "sara-2");
  });

  test("deleting an account with an installation needs remove_server and removes it", async () => {
    await activate();
    const id = account().id;
    assert.equal((await staff(env, "POST", "/api/admin/decide", { json: { id, action: "delete" } })).status, 409);
    assert.equal((await staff(env, "POST", "/api/admin/decide", { json: { id, action: "delete", remove_server: true } })).status, 200);
    assert.equal(account(), undefined);
    assert.ok(!fs.existsSync(path.join(home, "customers/sara")));
    assert.ok(!fs.existsSync(path.join(home, "caddy/customers/sara.caddy")));
  });

  test("without HOST_SCRIPT, activation stays manual", async () => {
    env = makeEnv();
    await call(env, "POST", "/api/register", { json: goodSignup() });
    assert.equal((await activate()).status, 400); // instance_url required
    assert.ok(!fs.existsSync(path.join(home, "customers/sara")));
  });
});
