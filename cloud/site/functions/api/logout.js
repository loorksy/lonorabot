// POST /api/logout: ends this browser's portal session.
import { SESSION_COOKIE, cookieValue, json, sameOrigin, sessionCookie, sha256 } from "../_lib/core.js";

export async function onRequestPost({ request, env }) {
  if (!sameOrigin(request, env)) return json({ ok: false, error: "origin" }, 403);
  const token = cookieValue(request, SESSION_COOKIE);
  if (token) await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?").bind(await sha256(token)).run();
  return json({ ok: true }, 200, { "set-cookie": sessionCookie("", 0) });
}
