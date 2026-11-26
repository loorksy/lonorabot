// POST /api/provision/callback: the new customer server reports once, with its job id and the
// per-job secret it was given at creation (only its SHA-256 is stored here). On "ready" the account
// turns active with its address and the one-time setup link; on "failed" the attempt is undone.
import { audit, clientIp, json, nowIso, rateLimited, readJson, sha256, timingSafeEqual } from "../../_lib/core.js";
import { deprovision } from "../../_lib/provision.js";

export async function onRequestPost({ request, env }) {
  if (await rateLimited(env, "provision-callback", clientIp(request), 30, 600)) return json({ ok: false, error: "rate_limited" }, 429);
  const body = await readJson(request, 4096);
  if (!body || typeof body.job !== "string" || typeof body.secret !== "string") return json({ ok: false, error: "bad_request" }, 400);
  const job = await env.DB.prepare("SELECT * FROM provision_jobs WHERE id = ?").bind(body.job).first();
  if (!job || !timingSafeEqual(await sha256(body.secret), job.secret_hash)) return json({ ok: false, error: "forbidden" }, 403);
  if (job.status !== "installing") return json({ ok: true, status: job.status }); // repeated or late report
  const domain = `${job.handle}.${env.BASE_DOMAIN}`;
  if (body.status === "ready") {
    if (typeof body.setup_token !== "string" || !/^[A-Za-z0-9_-]{20,128}$/.test(body.setup_token)) return json({ ok: false, error: "setup_token" }, 400);
    // Lonora must answer on its own domain before the customer is told it is ready.
    let answers = false;
    try {
      answers = (await fetch(`https://${domain}/ready`, { method: "GET" })).ok;
    } catch {
      answers = false;
    }
    if (!answers) return json({ ok: false, error: "not_ready" }, 409);
    await env.DB.prepare("UPDATE provision_jobs SET status = 'ready', updated_at = ? WHERE id = ?").bind(nowIso(), job.id).run();
    await env.DB.prepare("UPDATE accounts SET status = 'active', instance_url = ?, setup_link = ?, reason = NULL WHERE id = ? AND status = 'provisioning'")
      .bind(`https://${domain}/`, `https://${domain}/#token=${body.setup_token}`, job.account_id)
      .run();
    await audit(env, "system", "activated", job.account_id, { handle: job.handle, server_id: job.server_id });
    return json({ ok: true, status: "ready" });
  }
  const error = typeof body.error === "string" && /^[a-z_]{1,40}$/.test(body.error) ? body.error : "install_failed";
  try {
    await deprovision(env, job);
  } catch {
    // the ids stay on the job row for staff
  }
  await env.DB.prepare("UPDATE provision_jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ?").bind(error, nowIso(), job.id).run();
  await env.DB.prepare("UPDATE accounts SET status = 'approved' WHERE id = ? AND status = 'provisioning'").bind(job.account_id).run();
  await audit(env, "system", "provision_failed", job.account_id, { error });
  return json({ ok: true, status: "failed" });
}
