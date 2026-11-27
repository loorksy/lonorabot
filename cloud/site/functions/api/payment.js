// POST /api/payment {tx}: the signed-in customer sends the id of their USDT (TRC-20) transfer while the
// account waits for activation. They can correct it until then; one transfer pays for one account.
import { audit, currentAccount, json, nowIso, rateLimited, readJson, sameOrigin } from "../_lib/core.js";
import { TX, WAITING, customerPayment } from "../_lib/payment.js";

export async function onRequestPost({ request, env }) {
  if (!sameOrigin(request, env)) return json({ ok: false, error: "origin" }, 403);
  const account = await currentAccount(request, env);
  if (!account) return json({ ok: false, error: "signed_out" }, 401);
  if (await rateLimited(env, "payment", account.id, 10, 3600)) return json({ ok: false, error: "rate_limited" }, 429);
  if (!WAITING.includes(account.status) || !(await customerPayment(env, account))) return json({ ok: false, error: "bad_state" }, 409);
  const body = await readJson(request);
  const tx = typeof body?.tx === "string" ? body.tx.trim().toLowerCase().replace(/^0x/, "") : "";
  if (!TX.test(tx)) return json({ ok: false, error: "tx" }, 400);
  const other = await env.DB.prepare("SELECT account_id FROM payments WHERE tx = ? AND account_id <> ?").bind(tx, account.id).first();
  if (other) return json({ ok: false, error: "tx_used" }, 409);
  await env.DB.prepare(
    "INSERT INTO payments (account_id, tx, submitted_at) VALUES (?, ?, ?) ON CONFLICT(account_id) DO UPDATE SET tx = excluded.tx, submitted_at = excluded.submitted_at",
  ).bind(account.id, tx, nowIso()).run();
  await audit(env, "customer", "payment_submitted", account.id, { tx });
  return json({ ok: true, payment: await customerPayment(env, account) });
}
