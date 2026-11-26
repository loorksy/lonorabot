// Shared helpers for the Lonora Cloud website functions (Pages-style handlers that cloud/host/server.mjs
// runs, with its D1-compatible SQLite database).
// Nothing here logs a request body, an email, a password or a token.

const enc = new TextEncoder();

export const SESSION_COOKIE = "__Host-lonora_session";
export const SESSION_DAYS = 30;
// Cloudflare Workers caps PBKDF2 at 100,000 iterations.
const PBKDF2_ITERATIONS = 100_000;

export function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
  });
}

export function nowIso() {
  return new Date().toISOString();
}

export function hex(bytes) {
  return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function randomToken(bytes = 32) {
  const b = new Uint8Array(bytes);
  crypto.getRandomValues(b);
  return hex(b);
}

export async function sha256(text) {
  return hex(await crypto.subtle.digest("SHA-256", enc.encode(text)));
}

export function timingSafeEqual(a, b) {
  const x = enc.encode(String(a));
  const y = enc.encode(String(b));
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

async function pbkdf2(password, salt, iterations) {
  const key = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: enc.encode(salt), iterations }, key, 256);
  return hex(bits);
}

export async function hashPassword(password) {
  const salt = randomToken(16);
  return `pbkdf2-sha256$${PBKDF2_ITERATIONS}$${salt}$${await pbkdf2(password, salt, PBKDF2_ITERATIONS)}`;
}

// A fixed hash checked when the email is unknown, so a wrong email costs the same time as a wrong password.
const DUMMY_HASH = `pbkdf2-sha256$${PBKDF2_ITERATIONS}$00000000000000000000000000000000$0000000000000000000000000000000000000000000000000000000000000000`;

export async function verifyPassword(password, stored) {
  const [scheme, iterations, salt, digest] = String(stored || DUMMY_HASH).split("$");
  if (scheme !== "pbkdf2-sha256") return false;
  return timingSafeEqual(await pbkdf2(password, salt, Number(iterations)), digest);
}

export { DUMMY_HASH };

// POST, PUT and DELETE must come from the site's own origin (CSRF); a missing Origin is refused.
export function sameOrigin(request, env) {
  const origin = request.headers.get("origin");
  const allowed = env.SITE_ORIGIN || new URL(request.url).origin;
  return origin !== null && origin === allowed;
}

// The reverse proxy (cloud/host/Caddyfile) sets X-Real-IP to the connecting address.
export function clientIp(request) {
  return request.headers.get("x-real-ip") || "0.0.0.0";
}

// Fixed-window counter in D1, keyed by a hash of the route and the client address.
export async function rateLimited(env, route, keyPart, limit, windowSeconds) {
  const now = Math.floor(Date.now() / 1000);
  const windowStart = now - (now % windowSeconds);
  const bucket = await sha256(`${route}|${keyPart}|${windowStart}`);
  await env.DB.prepare("DELETE FROM rate WHERE expires_at < ?").bind(now).run();
  const row = await env.DB.prepare(
    "INSERT INTO rate (bucket, count, expires_at) VALUES (?, 1, ?) ON CONFLICT(bucket) DO UPDATE SET count = count + 1 RETURNING count",
  )
    .bind(bucket, windowStart + windowSeconds)
    .first();
  return Number(row?.count ?? 1) > limit;
}

// Cloudflare Turnstile. Without a configured secret every request is refused, so a misconfigured
// deployment never accepts bots silently.
export async function turnstileOk(env, token, ip) {
  if (!env.TURNSTILE_SECRET || typeof token !== "string" || token.length === 0 || token.length > 2048) return false;
  const body = new FormData();
  body.append("secret", env.TURNSTILE_SECRET);
  body.append("response", token);
  body.append("remoteip", ip);
  try {
    const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body });
    const out = await res.json();
    return out.success === true;
  } catch {
    return false;
  }
}

export function cookieValue(request, name) {
  const header = request.headers.get("cookie") || "";
  for (const part of header.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return null;
}

export function sessionCookie(token, maxAgeSeconds) {
  return `${SESSION_COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAgeSeconds}`;
}

export async function currentAccount(request, env) {
  const token = cookieValue(request, SESSION_COOKIE);
  if (!token || !/^[0-9a-f]{64}$/.test(token)) return null;
  const row = await env.DB.prepare(
    "SELECT a.* FROM sessions s JOIN accounts a ON a.id = s.account_id WHERE s.token_hash = ? AND s.expires_at > ?",
  )
    .bind(await sha256(token), nowIso())
    .first();
  return row || null;
}

export async function audit(env, actor, action, accountId, details = {}) {
  await env.DB.prepare("INSERT INTO audit (id, at, actor, action, account_id, details) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(randomToken(16), nowIso(), actor, action, accountId, JSON.stringify(details))
    .run();
}

export async function readJson(request, maxBytes = 8192) {
  const text = await request.text();
  if (text.length > maxBytes) return null;
  try {
    const value = JSON.parse(text);
    return value && typeof value === "object" && !Array.isArray(value) ? value : null;
  } catch {
    return null;
  }
}

export const USES = ["watch", "trade", "analysis", "news", "brief", "other"];
const EMAIL = /^[^\s@<>()[\]\\,;:"]{1,64}@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/;

function text(value, min, max) {
  if (typeof value !== "string") return null;
  const v = value.replace(/[\u0000-\u001f\u007f]/g, "").trim();
  return v.length >= min && v.length <= max ? v : null;
}

// Returns { value } or { error: "<field>" }.
export function validateRegistration(body) {
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  if (email.length > 254 || !EMAIL.test(email)) return { error: "email" };
  const name = text(body.name, 1, 80);
  if (!name) return { error: "name" };
  if (typeof body.password !== "string" || body.password.length < 10 || body.password.length > 128) return { error: "password" };
  const country = typeof body.country === "string" ? body.country.trim().toUpperCase() : "";
  if (!/^[A-Z]{2}$/.test(country)) return { error: "country" };
  if (body.lang !== "ar" && body.lang !== "en") return { error: "lang" };
  const broker = body.broker === undefined || body.broker === "" ? null : text(body.broker, 1, 80);
  if (body.broker && !broker) return { error: "broker" };
  const uses = Array.isArray(body.uses) ? [...new Set(body.uses)] : [];
  if (uses.length > USES.length || uses.some((u) => !USES.includes(u))) return { error: "uses" };
  if (body.accept_terms !== true) return { error: "accept_terms" };
  if (body.accept_risk !== true) return { error: "accept_risk" };
  return { value: { email, name, password: body.password, country, lang: body.lang, broker, uses } };
}

// Staff sign in at the reverse proxy (basic_auth on /admin and /api/admin in cloud/host/Caddyfile), which
// passes the signed-in name in X-Staff-Email and drops that header from every other request. The site
// listens only to the proxy. The name must also be one of ADMIN_EMAILS.
export function staffEmail(request, env) {
  const email = String(request.headers.get("x-staff-email") || "").toLowerCase();
  const allowed = String(env.ADMIN_EMAILS || "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  return email && allowed.includes(email) ? email : null;
}

// The account fields a customer sees about themselves. The setup link shows only while active.
export function publicAccount(a) {
  return {
    email: a.email,
    name: a.name,
    status: a.status,
    lang: a.lang,
    created_at: a.created_at,
    reason: a.status === "rejected" || a.status === "suspended" ? a.reason || null : null,
    instance_url: a.status === "active" ? a.instance_url : null,
    setup_link: a.status === "active" ? a.setup_link : null,
  };
}
