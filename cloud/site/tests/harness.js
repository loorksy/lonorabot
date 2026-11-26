// Test harness: the host server's own D1-compatible database and request dispatch (cloud/host/server.mjs),
// with a stubbed Turnstile. Staff are signed in the way the proxy passes them: X-Staff-Email.
import { handle, openDb } from "../../host/server.mjs";

export const ORIGIN = "https://lonora.test";
export const STAFF = "staff@lonora.test";
export const makeDb = () => openDb();

// Replaces global fetch: Turnstile passes for the token "good"; any other outbound call fails the test.
export async function installFetch() {
  globalThis.fetch = async (url, init) => {
    const u = String(url);
    if (u === "https://challenges.cloudflare.com/turnstile/v0/siteverify") {
      const token = init.body.get("response");
      return new Response(JSON.stringify({ success: token === "good" }));
    }
    throw new Error(`unexpected fetch ${u}`);
  };
}

export function makeEnv(overrides = {}) {
  return {
    DB: makeDb(),
    SITE_ORIGIN: ORIGIN,
    TURNSTILE_SECRET: "test-secret",
    TURNSTILE_SITE_KEY: "site-key",
    ADMIN_EMAILS: STAFF,
    TERMS_VERSION: "t1",
    RISK_VERSION: "r1",
    PRIVACY_VERSION: "p1",
    ...overrides,
  };
}

// call(env, "POST", "/api/register", {json, headers, cookie, origin, ip}) -> Response
export async function call(env, method, pathname, { json, headers = {}, cookie, origin = ORIGIN, ip = "203.0.113.7", query = "" } = {}) {
  const h = new Headers(headers);
  if (origin) h.set("origin", origin);
  if (cookie) h.set("cookie", cookie);
  h.set("x-real-ip", ip);
  const request = new Request(`${ORIGIN}${pathname}${query}`, {
    method,
    headers: h,
    body: json === undefined ? undefined : typeof json === "string" ? json : JSON.stringify(json),
  });
  return handle(request, env);
}

export const staff = (env, method, path, opts = {}) => call(env, method, path, { ...opts, headers: { "x-staff-email": STAFF, ...(opts.headers || {}) } });

export const goodSignup = (over = {}) => ({
  email: "Sara@Example.com",
  name: "سارة",
  password: "correct horse battery",
  country: "ae",
  lang: "ar",
  broker: "Exness",
  uses: ["trade", "brief"],
  accept_terms: true,
  accept_risk: true,
  turnstile: "good",
  website: "",
  ...over,
});
