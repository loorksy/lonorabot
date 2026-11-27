// GET /api/me: the signed-in customer's own account and its approval status.
import { currentAccount, json, publicAccount } from "../_lib/core.js";
import { customerPayment } from "../_lib/payment.js";

export async function onRequestGet({ request, env }) {
  const account = await currentAccount(request, env);
  if (!account) return json({ ok: false, error: "signed_out" }, 401);
  return json({ ok: true, account: publicAccount(account), payment: await customerPayment(env, account) });
}
