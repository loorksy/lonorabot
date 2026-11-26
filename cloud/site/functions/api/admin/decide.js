// POST /api/admin/decide {id, action, reason?, instance_url?, setup_link?}: staff decisions (D46).
// Every decision is written to the audit log with the staff email.
import { audit, json, nowIso, readJson, sameOrigin, sha256 } from "../../_lib/core.js";

const MOVES = {
  approve: { from: ["pending"], to: "approved" },
  activate: { from: ["pending", "approved"], to: "active" },
  reject: { from: ["pending", "approved"], to: "rejected", needsReason: true },
  suspend: { from: ["active"], to: "suspended", needsReason: true },
  reinstate: { from: ["suspended"], to: "active" },
};

function httpsUrl(value) {
  if (typeof value !== "string" || value.length > 500) return null;
  try {
    const u = new URL(value);
    return u.protocol === "https:" ? u.toString() : null;
  } catch {
    return null;
  }
}

export async function onRequestPost({ request, env, data }) {
  if (!sameOrigin(request, env)) return json({ ok: false, error: "origin" }, 403);
  const body = await readJson(request);
  if (!body || typeof body.id !== "string" || typeof body.action !== "string") return json({ ok: false, error: "bad_request" }, 400);
  const account = await env.DB.prepare("SELECT id, email, status, instance_url, setup_link FROM accounts WHERE id = ?").bind(body.id).first();
  if (!account) return json({ ok: false, error: "not_found" }, 404);
  if (body.action === "delete") {
    // Deletion on the person's request: the account and its sessions go; the audit keeps only a hash.
    await env.DB.prepare("DELETE FROM sessions WHERE account_id = ?").bind(account.id).run();
    await env.DB.prepare("DELETE FROM accounts WHERE id = ?").bind(account.id).run();
    await audit(env, data.staff, "deleted", account.id, { email_sha256: await sha256(account.email) });
    return json({ ok: true, status: "deleted" });
  }
  const move = MOVES[body.action];
  if (!move) return json({ ok: false, error: "bad_action" }, 400);
  if (!move.from.includes(account.status)) return json({ ok: false, error: "bad_state", status: account.status }, 409);
  const reason = typeof body.reason === "string" ? body.reason.trim().slice(0, 500) : "";
  if (move.needsReason && !reason) return json({ ok: false, error: "reason_required" }, 400);
  let instanceUrl = account.instance_url;
  let setupLink = account.setup_link;
  if (body.action === "activate") {
    instanceUrl = httpsUrl(body.instance_url);
    if (!instanceUrl) return json({ ok: false, error: "instance_url" }, 400);
    setupLink = body.setup_link ? httpsUrl(body.setup_link) : null;
    if (body.setup_link && !setupLink) return json({ ok: false, error: "setup_link" }, 400);
  }
  const changed = await env.DB.prepare(
    "UPDATE accounts SET status = ?, reason = ?, instance_url = ?, setup_link = ?, decided_at = ?, decided_by = ? WHERE id = ? AND status = ?",
  )
    .bind(move.to, move.needsReason ? reason : null, instanceUrl, setupLink, nowIso(), data.staff, account.id, account.status)
    .run();
  if (changed.meta?.changes !== 1) return json({ ok: false, error: "bad_state" }, 409);
  await audit(env, data.staff, body.action, account.id, { from: account.status, to: move.to, reason: reason || undefined });
  return json({ ok: true, status: move.to });
}
