// Paying in USDT on TRON (TRC-20) (owner, 2026-11-27). Staff set the wallet address and the price in the
// admin panel; a customer waiting for activation sends the transfer's id; staff check it and activate.
export const WALLET = /^T[1-9A-HJ-NP-Za-km-z]{33}$/;
export const TX = /^[0-9a-f]{64}$/;
export const WAITING = ["pending", "approved"];

export async function paymentSettings(env) {
  const { results } = await env.DB.prepare("SELECT key, value FROM settings WHERE key IN ('wallet', 'price')").all();
  const s = Object.fromEntries(results.map((r) => [r.key, r.value]));
  return { wallet: s.wallet || null, price: s.price || null };
}

// What the customer's account page shows: only while the account waits, and only once a wallet is set.
export async function customerPayment(env, account) {
  if (!WAITING.includes(account.status)) return null;
  const { wallet, price } = await paymentSettings(env);
  if (!wallet) return null;
  const paid = await env.DB.prepare("SELECT tx, submitted_at FROM payments WHERE account_id = ?").bind(account.id).first();
  return { wallet, price, network: "TRON (TRC-20)", tx: paid?.tx || null, submitted_at: paid?.submitted_at || null };
}
