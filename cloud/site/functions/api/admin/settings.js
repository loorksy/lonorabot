// GET|POST /api/admin/settings {wallet, price}: the USDT (TRC-20) wallet customers pay to and the price
// text they see (owner, 2026-11-27). An empty wallet hides the payment box.
import { audit, json, nowIso, readJson, sameOrigin } from "../../_lib/core.js";
import { WALLET, paymentSettings } from "../../_lib/payment.js";

export async function onRequestGet({ env }) {
  return json({ ok: true, ...(await paymentSettings(env)) });
}

export async function onRequestPost({ request, env, data }) {
  if (!sameOrigin(request, env)) return json({ ok: false, error: "origin" }, 403);
  const body = await readJson(request);
  if (!body) return json({ ok: false, error: "bad_request" }, 400);
  const wallet = typeof body.wallet === "string" ? body.wallet.trim() : "";
  const price = typeof body.price === "string" ? body.price.trim() : "";
  if (wallet && !WALLET.test(wallet)) return json({ ok: false, error: "wallet" }, 400);
  if (price.length > 200) return json({ ok: false, error: "price" }, 400);
  const now = nowIso();
  for (const [key, value] of [["wallet", wallet], ["price", price]]) {
    await env.DB.prepare(
      "INSERT INTO settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at, updated_by = excluded.updated_by",
    ).bind(key, value, now, data.staff).run();
  }
  await audit(env, data.staff, "payment_settings", null, { wallet, price });
  return json({ ok: true, wallet: wallet || null, price: price || null });
}
