// POST /api/register: a normal account that waits for staff approval (docs/cloud/DECISIONS.md D46).
// Every outcome a visitor can cause with an email that already exists returns the same answer as a
// new one, so the form cannot tell whether an address is registered.
import {
  audit, clientIp, hashPassword, json, nowIso, randomToken, rateLimited, readJson, sameOrigin, turnstileOk, validateRegistration,
} from "../_lib/core.js";

const ACCEPTED = { ok: true, next: "signin" };

export async function onRequestPost({ request, env }) {
  if (!sameOrigin(request, env)) return json({ ok: false, error: "origin" }, 403);
  const ip = clientIp(request);
  if (await rateLimited(env, "register", ip, 5, 3600)) return json({ ok: false, error: "rate_limited" }, 429);
  const body = await readJson(request);
  if (!body) return json({ ok: false, error: "bad_request" }, 400);
  // Honeypot: a field people never see. A bot that fills it gets the normal answer and nothing is stored.
  if (typeof body.website === "string" && body.website !== "") return json(ACCEPTED, 202);
  if (!(await turnstileOk(env, body.turnstile, ip))) return json({ ok: false, error: "challenge" }, 400);
  const checked = validateRegistration(body);
  if (checked.error) return json({ ok: false, error: "invalid", field: checked.error }, 400);
  const v = checked.value;
  const id = randomToken(16);
  const result = await env.DB.prepare(
    `INSERT INTO accounts (id, email, name, country, lang, broker, uses, password_hash, status,
       terms_version, risk_version, privacy_version, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?) ON CONFLICT(email) DO NOTHING`,
  )
    .bind(
      id, v.email, v.name, v.country, v.lang, v.broker, JSON.stringify(v.uses), await hashPassword(v.password),
      env.TERMS_VERSION || "draft", env.RISK_VERSION || "draft", env.PRIVACY_VERSION || "draft", nowIso(),
    )
    .run();
  if (result.meta?.changes === 1) await audit(env, "visitor", "registered", id, { country: v.country, lang: v.lang });
  return json(ACCEPTED, 202);
}
