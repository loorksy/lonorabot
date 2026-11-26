// GET /api/admin/audit?account=<id>: the decision log, newest first.
import { json } from "../../_lib/core.js";

export async function onRequestGet({ request, env }) {
  const account = new URL(request.url).searchParams.get("account");
  const stmt = account
    ? env.DB.prepare("SELECT at, actor, action, account_id, details FROM audit WHERE account_id = ? ORDER BY at DESC LIMIT 200").bind(account)
    : env.DB.prepare("SELECT at, actor, action, account_id, details FROM audit ORDER BY at DESC LIMIT 200");
  const { results } = await stmt.all();
  return json({ ok: true, entries: results.map((e) => ({ ...e, details: JSON.parse(e.details || "{}") })) });
}
