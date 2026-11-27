// Paying in USDT on TRON (owner, 2026-11-27): staff set the wallet and price; a waiting customer sends the
// transfer's id; staff see it next to the account and activate as before.
import assert from "node:assert/strict";
import { beforeEach, describe, test } from "node:test";
import { call, goodSignup, installFetch, makeEnv, staff } from "./harness.js";

const WALLET = "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE";
const TX = "a".repeat(63) + "1";
let env;

beforeEach(async () => {
  env = makeEnv();
  await installFetch();
  await call(env, "POST", "/api/register", { json: goodSignup() });
});

async function signIn(email = "sara@example.com", ip) {
  const res = await call(env, "POST", "/api/login", { json: { email, password: "correct horse battery", turnstile: "good" }, ip });
  return (res.headers.get("set-cookie") || "").split(";")[0];
}
const me = async (cookie) => (await call(env, "GET", "/api/me", { cookie })).json();
const pay = (cookie, tx) => call(env, "POST", "/api/payment", { cookie, json: { tx } });
const setWallet = (wallet, price = "30 USDT شهرياً") => staff(env, "POST", "/api/admin/settings", { json: { wallet, price } });

describe("paying in USDT", () => {
  test("staff set the wallet and price; only staff can, and only a TRON address", async () => {
    assert.equal((await call(env, "POST", "/api/admin/settings", { json: { wallet: WALLET } })).status, 403);
    assert.equal((await setWallet("0x1234")).status, 400);
    assert.equal((await setWallet(WALLET)).status, 200);
    assert.deepEqual(await (await staff(env, "GET", "/api/admin/settings")).json(), { ok: true, wallet: WALLET, price: "30 USDT شهرياً" });
  });

  test("a waiting customer sees the wallet and sends the transfer id; staff see it on the account", async () => {
    const cookie = await signIn();
    assert.equal((await me(cookie)).payment, null); // no wallet set yet: nothing to pay to
    assert.equal((await pay(cookie, TX)).status, 409);
    await setWallet(WALLET);
    const before = await me(cookie);
    assert.deepEqual(before.payment, { wallet: WALLET, price: "30 USDT شهرياً", network: "TRON (TRC-20)", tx: null, submitted_at: null });
    assert.equal((await pay(cookie, "not-a-tx")).status, 400);
    const res = await pay(cookie, `0x${TX.toUpperCase()}`);
    assert.equal(res.status, 200);
    assert.equal((await res.json()).payment.tx, TX);
    const listed = (await (await staff(env, "GET", "/api/admin/accounts?status=pending")).json()).accounts[0];
    assert.equal(listed.payment.tx, TX);
    // A typo can be corrected while the account waits.
    const fixed = "b".repeat(64);
    assert.equal((await pay(cookie, fixed)).status, 200);
    assert.equal((await me(cookie)).payment.tx, fixed);
  });

  test("one transfer pays for one account, and an active account shows no payment", async () => {
    await setWallet(WALLET);
    await call(env, "POST", "/api/register", { json: goodSignup({ email: "omar@example.com" }), ip: "198.51.100.9" });
    const sara = await signIn();
    const omar = await signIn("omar@example.com", "198.51.100.9");
    assert.equal((await pay(sara, TX)).status, 200);
    assert.equal((await pay(omar, TX)).status, 409);
    const id = env.DB.raw.prepare("SELECT id FROM accounts WHERE email = ?").get("sara@example.com").id;
    await staff(env, "POST", "/api/admin/decide", {
      json: { id, action: "activate", instance_url: "https://sara.lonora.test", setup_link: "https://sara.lonora.test/#token=" + "c".repeat(32) },
    });
    assert.equal((await me(sara)).payment, null);
    assert.equal((await pay(sara, "d".repeat(64))).status, 409);
  });
});
