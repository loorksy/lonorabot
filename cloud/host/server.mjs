// The Lonora Cloud website on the shared host (docs/cloud/DECISIONS.md D48): serves cloud/site/public
// and runs the handlers in cloud/site/functions the way Cloudflare Pages did (file routes,
// _middleware.js, onRequestGet/onRequestPost), with a D1-compatible database on node:sqlite.
// Node 22 built-ins only. Settings come from the environment (lonora-site.service, site.env):
//   SITE_LISTEN  a port on 127.0.0.1 (default 8788) or a unix socket path (on the host: the proxy's)
//   SITE_DB      the SQLite file (default site.db); schema.sql is applied at every start
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath, pathToFileURL } from "node:url";

const SITE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "site");
const PUBLIC = path.join(SITE, "public");
const FUNCTIONS = path.join(SITE, "functions");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json" };
const MAX_BODY = 64 * 1024;

// The part of D1's API the handlers use: prepare(sql).bind(...).first() / .all() / .run().
class Statement {
  constructor(db, sql, args = []) {
    Object.assign(this, { db, sql, args });
  }
  bind(...args) {
    return new Statement(this.db, this.sql, args);
  }
  async first(column) {
    const row = this.db.prepare(this.sql).get(...this.args);
    return row ? (column ? row[column] : { ...row }) : null;
  }
  async all() {
    return { results: this.db.prepare(this.sql).all(...this.args).map((r) => ({ ...r })), success: true };
  }
  async run() {
    return { success: true, meta: { changes: Number(this.db.prepare(this.sql).run(...this.args).changes) } };
  }
}

export function openDb(file = ":memory:") {
  const db = new DatabaseSync(file);
  db.exec("PRAGMA foreign_keys = ON");
  db.exec(fs.readFileSync(path.join(SITE, "schema.sql"), "utf8"));
  return { raw: db, prepare: (sql) => new Statement(db, sql) };
}

const load = async (file) => (fs.existsSync(file) ? import(pathToFileURL(file).href) : null);
const notFound = () => new Response(JSON.stringify({ ok: false, error: "not_found" }), { status: 404, headers: { "content-type": "application/json" } });

function asset(pathname) {
  let file = path.join(PUBLIC, pathname);
  if (file.startsWith(PUBLIC) && fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
  if (!file.startsWith(PUBLIC) || !fs.existsSync(file)) return new Response("Not found", { status: 404, headers: { "content-type": "text/plain" } });
  return new Response(fs.readFileSync(file), { headers: { "content-type": TYPES[path.extname(file)] || "application/octet-stream" } });
}

// One request through the middleware chain to its handler (/api/a/b -> functions/api/a/b.js) or to a
// file in public/. Only lowercase route names are looked up, so _lib and _middleware are never routes.
export async function handle(request, env) {
  const { pathname } = new URL(request.url);
  const steps = [(await load(path.join(FUNCTIONS, "_middleware.js")))?.onRequest];
  let last = () => asset(pathname);
  if (/^\/api(\/[a-z]+)+$/.test(pathname)) {
    const parts = pathname.slice(1).split("/");
    for (let i = 1; i < parts.length; i++) steps.push((await load(path.join(FUNCTIONS, ...parts.slice(0, i), "_middleware.js")))?.onRequest);
    const mod = await load(path.join(FUNCTIONS, `${pathname}.js`));
    const method = request.method.charAt(0) + request.method.slice(1).toLowerCase();
    const fn = mod && (mod[`onRequest${method}`] || mod.onRequest);
    last = fn ? (ctx) => fn(ctx) : () => (mod ? new Response(null, { status: 405 }) : notFound());
  }
  const chain = [...steps.filter(Boolean), last];
  const context = { request, env, data: {}, params: {}, waitUntil() {} };
  let i = 0;
  context.next = () => chain[i++](context);
  return context.next();
}

export function listen(env, where) {
  const server = http.createServer(async (req, res) => {
    try {
      const chunks = [];
      let size = 0;
      for await (const chunk of req) {
        size += chunk.length;
        if (size > MAX_BODY) return void res.writeHead(413).end();
        chunks.push(chunk);
      }
      const hasBody = !["GET", "HEAD"].includes(req.method);
      const request = new Request(`${env.SITE_ORIGIN}${req.url}`, { method: req.method, headers: req.headers, body: hasBody ? Buffer.concat(chunks) : undefined });
      const response = await handle(request, env);
      res.writeHead(response.status, Object.fromEntries(response.headers));
      res.end(Buffer.from(await response.arrayBuffer()));
    } catch {
      if (!res.headersSent) res.writeHead(500);
      res.end();
    }
  });
  if (/^\d+$/.test(String(where))) return server.listen(Number(where), "127.0.0.1");
  fs.rmSync(where, { force: true });
  return server.listen(where);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const env = { ...process.env, SITE_ORIGIN: process.env.SITE_ORIGIN || "http://localhost:8788" };
  env.DB = openDb(process.env.SITE_DB || "site.db");
  const where = process.env.SITE_LISTEN || "8788";
  listen(env, where).on("listening", () => console.log(`site: listening on ${where}`));
}
