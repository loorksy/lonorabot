// GET /api/admin/accounts?status=pending&q=text&limit=100: accounts for staff review.
import { json } from "../../_lib/core.js";
import { expireStaleJobs, provisioningEnabled } from "../../_lib/provision.js";

const STATUSES = ["pending", "approved", "provisioning", "active", "rejected", "suspended"];

export async function onRequestGet({ request, env }) {
  if (provisioningEnabled(env)) await expireStaleJobs(env);
  const url = new URL(request.url);
  const status = url.searchParams.get("status");
  const q = (url.searchParams.get("q") || "").trim().toLowerCase().slice(0, 100);
  const limit = Math.min(Math.max(Number(url.searchParams.get("limit")) || 100, 1), 500);
  const where = [];
  const args = [];
  if (status && STATUSES.includes(status)) { where.push("status = ?"); args.push(status); }
  if (q) { where.push("(email LIKE ? ESCAPE '\\' OR lower(name) LIKE ? ESCAPE '\\')"); const like = `%${q.replace(/[\\%_]/g, (c) => `\\${c}`)}%`; args.push(like, like); }
  const sql = `SELECT id, email, name, handle, country, lang, broker, uses, status, instance_url, setup_link, reason,
      terms_version, risk_version, privacy_version, created_at, decided_at, decided_by
    FROM accounts ${where.length ? `WHERE ${where.join(" AND ")}` : ""} ORDER BY created_at DESC LIMIT ?`;
  const { results } = await env.DB.prepare(sql).bind(...args, limit).all();
  const counts = {};
  for (const s of STATUSES) {
    counts[s] = Number((await env.DB.prepare("SELECT count(*) AS n FROM accounts WHERE status = ?").bind(s).first()).n);
  }
  const accounts = [];
  for (const a of results) {
    const job = await env.DB.prepare("SELECT id, handle, status, server_id, error, created_at, updated_at FROM provision_jobs WHERE account_id = ? ORDER BY created_at DESC LIMIT 1").bind(a.id).first();
    const payment = await env.DB.prepare("SELECT tx, submitted_at FROM payments WHERE account_id = ?").bind(a.id).first();
    accounts.push({ ...a, uses: JSON.parse(a.uses || "[]"), job: job || null, payment: payment || null });
  }
  return json({ ok: true, accounts, counts, provisioning: provisioningEnabled(env), base_domain: env.BASE_DOMAIN || null });
}
