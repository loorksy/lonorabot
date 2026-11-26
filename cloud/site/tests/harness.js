// Test harness: a D1-compatible database on node:sqlite, stubbed Turnstile and Cloudflare Access,
// and a small router that runs a Pages Function (with its middleware) the way Pages does.
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import { _resetCertCache } from "../functions/_lib/core.js";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export const ORIGIN = "https://lonora.test";
export const TEAM = "team.cloudflareaccess.com";
export const AUD = "aud-123";

class Statement {
  constructor(db, sql, args = []) {
    this.db = db;
    this.sql = sql;
    this.args = args;
  }
  bind(...args) {
    return new Statement(this.db, this.sql, args);
  }
  async first(column) {
    const row = this.db.prepare(this.sql).get(...this.args);
    if (!row) return null;
    return column ? row[column] : { ...row };
  }
  async all() {
    return { results: this.db.prepare(this.sql).all(...this.args).map((r) => ({ ...r })), success: true };
  }
  async run() {
    const info = this.db.prepare(this.sql).run(...this.args);
    return { success: true, meta: { changes: Number(info.changes) } };
  }
}

export function makeDb() {
  const db = new DatabaseSync(":memory:");
  db.exec("PRAGMA foreign_keys = ON");
  db.exec(fs.readFileSync(path.join(root, "schema.sql"), "utf8"));
  return { raw: db, prepare: (sql) => new Statement(db, sql) };
}

let rsa;
async function keys() {
  if (!rsa) {
    rsa = await crypto.subtle.generateKey(
      { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
      true,
      ["sign", "verify"],
    );
  }
  return rsa;
}

const b64url = (bytes) => Buffer.from(bytes).toString("base64url");

export async function accessJwt(email, { aud = AUD, iss = `https://${TEAM}`, exp = Math.floor(Date.now() / 1000) + 600, kid = "k1" } = {}) {
  const { privateKey } = await keys();
  const head = b64url(new TextEncoder().encode(JSON.stringify({ alg: "RS256", kid })));
  const body = b64url(new TextEncoder().encode(JSON.stringify({ email, aud: [aud], iss, exp })));
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", privateKey, new TextEncoder().encode(`${head}.${body}`));
  return `${head}.${body}.${b64url(new Uint8Array(sig))}`;
}

// Fake Hetzner, Cloudflare DNS and customer servers, recording every call (cloud.calls).
export const cloud = { calls: [], failServer: false, failDns: false, ready: true, nextServer: 100, nextDns: 1 };
export function resetCloud() {
  Object.assign(cloud, { calls: [], failServer: false, failDns: false, ready: true, nextServer: 100, nextDns: 1 });
}
function cloudFetch(u, init = {}) {
  const method = init.method || "GET";
  const body = init.body ? JSON.parse(init.body) : null;
  if (u.startsWith("https://api.hetzner.cloud/v1/servers")) {
    cloud.calls.push({ api: "hetzner", method, url: u, body, auth: init.headers?.authorization });
    if (method === "POST") {
      if (cloud.failServer) return new Response(JSON.stringify({ error: { message: "server limit reached" } }), { status: 403 });
      const id = cloud.nextServer++;
      return new Response(JSON.stringify({ server: { id, public_net: { ipv4: { ip: `192.0.2.${id % 250}` } } } }), { status: 201 });
    }
    if (method === "DELETE") return new Response(JSON.stringify({ action: {} }), { status: 200 });
  }
  if (u.startsWith("https://api.cloudflare.com/client/v4/zones/")) {
    cloud.calls.push({ api: "cloudflare", method, url: u, body, auth: init.headers?.authorization });
    if (method === "POST") {
      if (cloud.failDns) return new Response(JSON.stringify({ success: false, errors: [{ message: "record exists" }] }), { status: 400 });
      return new Response(JSON.stringify({ success: true, result: { id: `rec${cloud.nextDns++}` } }), { status: 200 });
    }
    if (method === "DELETE") return new Response(JSON.stringify({ success: true }), { status: 200 });
  }
  if (/^https:\/\/[a-z0-9-]+\.lonora\.test\/ready$/.test(u)) {
    cloud.calls.push({ api: "instance", method, url: u });
    return new Response("{}", { status: cloud.ready ? 200 : 503 });
  }
  return null;
}

// Replaces global fetch: Turnstile passes for the token "good", Access serves the test key.
export async function installFetch() {
  const { publicKey } = await keys();
  const jwk = { ...(await crypto.subtle.exportKey("jwk", publicKey)), kid: "k1", alg: "RS256" };
  _resetCertCache();
  globalThis.fetch = async (url, init) => {
    const u = String(url);
    if (u === "https://challenges.cloudflare.com/turnstile/v0/siteverify") {
      const token = init.body.get("response");
      return new Response(JSON.stringify({ success: token === "good" }));
    }
    if (u === `https://${TEAM}/cdn-cgi/access/certs`) return new Response(JSON.stringify({ keys: [jwk] }));
    const c = cloudFetch(u, init);
    if (c) return c;
    throw new Error(`unexpected fetch ${u}`);
  };
}

export function makeEnv(overrides = {}) {
  return {
    DB: makeDb(),
    SITE_ORIGIN: ORIGIN,
    TURNSTILE_SECRET: "test-secret",
    TURNSTILE_SITE_KEY: "site-key",
    ACCESS_TEAM_DOMAIN: TEAM,
    ACCESS_AUD: AUD,
    ADMIN_EMAILS: "staff@lonora.test",
    TERMS_VERSION: "t1",
    RISK_VERSION: "r1",
    PRIVACY_VERSION: "p1",
    ...overrides,
  };
}

const ROUTES = {
  "POST /api/register": ["../functions/api/register.js", "onRequestPost"],
  "POST /api/login": ["../functions/api/login.js", "onRequestPost"],
  "POST /api/logout": ["../functions/api/logout.js", "onRequestPost"],
  "GET /api/me": ["../functions/api/me.js", "onRequestGet"],
  "GET /api/config": ["../functions/api/config.js", "onRequestGet"],
  "GET /api/admin/accounts": ["../functions/api/admin/accounts.js", "onRequestGet", true],
  "POST /api/admin/decide": ["../functions/api/admin/decide.js", "onRequestPost", true],
  "GET /api/admin/export": ["../functions/api/admin/export.js", "onRequestGet", true],
  "GET /api/admin/audit": ["../functions/api/admin/audit.js", "onRequestGet", true],
  "POST /api/provision/callback": ["../functions/api/provision/callback.js", "onRequestPost"],
};

// call(env, "POST", "/api/register", {json, headers, cookie, origin, ip}) -> Response
export async function call(env, method, pathname, { json, headers = {}, cookie, origin = ORIGIN, ip = "203.0.113.7", query = "" } = {}) {
  const route = ROUTES[`${method} ${pathname}`];
  if (!route) throw new Error(`no route ${method} ${pathname}`);
  const [file, handlerName, admin] = route;
  const h = new Headers(headers);
  if (origin) h.set("origin", origin);
  if (cookie) h.set("cookie", cookie);
  h.set("cf-connecting-ip", ip);
  const request = new Request(`${ORIGIN}${pathname}${query}`, {
    method,
    headers: h,
    body: json === undefined ? undefined : typeof json === "string" ? json : JSON.stringify(json),
  });
  const mod = await import(file);
  const handler = (ctx) => mod[handlerName](ctx);
  const data = {};
  const ctx = { request, env, data, params: {}, next: () => handler(ctx) };
  if (admin) {
    const mw = await import("../functions/api/admin/_middleware.js");
    return mw.onRequest(ctx);
  }
  return handler(ctx);
}

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
