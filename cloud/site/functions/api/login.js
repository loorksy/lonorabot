// POST /api/login: the portal account only. It never signs anyone in to their Lonora (D7).
import {
  DUMMY_HASH, SESSION_DAYS, clientIp, json, nowIso, randomToken, rateLimited, readJson, sameOrigin, sessionCookie, sha256,
  turnstileOk, verifyPassword,
} from "../_lib/core.js";

export async function onRequestPost({ request, env }) {
  if (!sameOrigin(request, env)) return json({ ok: false, error: "origin" }, 403);
  const ip = clientIp(request);
  const body = await readJson(request);
  if (!body || typeof body.email !== "string" || typeof body.password !== "string") return json({ ok: false, error: "bad_request" }, 400);
  const email = body.email.trim().toLowerCase().slice(0, 254);
  if ((await rateLimited(env, "login-ip", ip, 20, 900)) || (await rateLimited(env, "login-email", email, 8, 900))) {
    return json({ ok: false, error: "rate_limited" }, 429);
  }
  if (!(await turnstileOk(env, body.turnstile, ip))) return json({ ok: false, error: "challenge" }, 400);
  const account = await env.DB.prepare("SELECT id, password_hash FROM accounts WHERE email = ?").bind(email).first();
  const good = await verifyPassword(body.password.slice(0, 128), account ? account.password_hash : DUMMY_HASH);
  if (!account || !good) return json({ ok: false, error: "credentials" }, 401);
  const token = randomToken(32);
  const expires = new Date(Date.now() + SESSION_DAYS * 86400_000).toISOString();
  await env.DB.prepare("INSERT INTO sessions (token_hash, account_id, created_at, expires_at) VALUES (?, ?, ?, ?)")
    .bind(await sha256(token), account.id, nowIso(), expires)
    .run();
  return json({ ok: true }, 200, { "set-cookie": sessionCookie(token, SESSION_DAYS * 86400) });
}
