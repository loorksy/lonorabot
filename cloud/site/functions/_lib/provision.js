// One-click activation on the shared host (docs/cloud/DECISIONS.md D48, PHASES.md PW-T7): staff press
// «تفعيل», and the host script cloud/host/customer.sh creates the customer's own installation on this
// server: its database and role in the shared PostgreSQL, its env file with its own keys, its Lonora
// (server and worker) from the current release image, and its route in the shared proxy. The account
// that asked for it becomes its owner with the password it signed up with, so the customer signs up
// once; the account turns active with the address once Lonora is ready.
//
// Settings: HOST_SCRIPT (the path of customer.sh; run with sudo -n), and HOST_DRY_RUN=1 for tests and
// smoke runs (the script then prints its Docker and system commands instead of running them).
// Without HOST_SCRIPT, provisioning is off and staff activate by hand with an address and a setup link.

import { execFile } from "node:child_process";
import { audit, nowIso, randomToken } from "./core.js";

const RESERVED = new Set([
  "www", "admin", "api", "app", "my", "status", "mail", "smtp", "docs", "help", "support", "billing", "portal",
  "staff", "root", "lonora", "dashboard", "login", "signin", "signup", "register", "static", "cdn", "assets", "dev",
  "test", "staging", "prod", "ns1", "ns2", "mx", "ftp", "blog", "news",
]);

export function provisioningEnabled(env) {
  return Boolean(env.HOST_SCRIPT);
}

export function validHandle(handle) {
  return typeof handle === "string" && /^[a-z](?:[a-z0-9-]{1,28}[a-z0-9])$/.test(handle) && !handle.includes("--") && !RESERVED.has(handle);
}

function baseHandle(account) {
  const fromEmail = account.email.split("@")[0].toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  let h = fromEmail.replace(/^[^a-z]+/, "").slice(0, 24).replace(/-+$/g, "");
  if (h.length < 3) h = `lonora-${account.id.slice(0, 6)}`;
  return h;
}

// A free handle: the one staff typed, or one derived from the email, with -2, -3… when taken.
export async function chooseHandle(env, account, requested) {
  if (requested !== undefined && requested !== null && requested !== "") {
    const h = String(requested).trim().toLowerCase();
    if (!validHandle(h)) return { error: "handle" };
    const taken = await env.DB.prepare("SELECT id FROM accounts WHERE handle = ? AND id <> ?").bind(h, account.id).first();
    return taken ? { error: "handle_taken" } : { handle: h };
  }
  if (account.handle) return { handle: account.handle };
  const base = baseHandle(account);
  for (let i = 1; i < 50; i++) {
    const h = i === 1 ? base : `${base.slice(0, 26)}-${i}`;
    if (!validHandle(h)) continue;
    const taken = await env.DB.prepare("SELECT id FROM accounts WHERE handle = ?").bind(h).first();
    if (!taken) return { handle: h };
  }
  return { error: "handle_taken" };
}

// Runs customer.sh, with ``input`` on its stdin. Its stdout carries only the result line; its stderr is
// progress, never a secret.
function host(env, args, input = "") {
  const [cmd, ...rest] = env.HOST_DRY_RUN === "1" ? [env.HOST_SCRIPT, "--dry-run", ...args] : ["sudo", "-n", env.HOST_SCRIPT, ...args];
  return new Promise((resolve) => {
    const child = execFile(cmd, rest, { timeout: 5 * 60_000 }, (err, stdout, stderr) => {
      const lines = `${stderr || ""}\n${err && !stderr ? err.message : ""}`.trim().split("\n");
      resolve({ ok: !err, code: err?.code, stdout: String(stdout), error: lines[lines.length - 1].slice(0, 300) });
    });
    child.stdin.on("error", () => {}); // a script that exits without reading it
    child.stdin.end(input);
  });
}

// Removes the customer's installation (its Lonora, database, route and files). Missing parts are not an error.
export async function deprovision(env, job) {
  const out = await host(env, ["remove", job.handle]);
  if (!out.ok) throw new Error(`remove: ${out.error}`);
  await env.DB.prepare("UPDATE provision_jobs SET status = 'removed', updated_at = ? WHERE id = ?").bind(nowIso(), job.id).run();
}

// One attempt, in under a minute. On failure, what it created is removed, and the account goes back to
// approved with the script's last message so staff can retry.
export async function startProvisioning(env, account, handle, staff) {
  const job = { id: randomToken(16), handle };
  const now = nowIso();
  // Claim the account first: of two overlapping activations only one moves it to provisioning,
  // and only that one creates a job.
  const claimed = await env.DB.prepare(
    "UPDATE accounts SET status = 'provisioning', handle = ?, decided_at = ?, decided_by = ? WHERE id = ? AND status IN ('pending', 'approved')",
  )
    .bind(handle, now, staff, account.id)
    .run();
  if (claimed.meta?.changes !== 1) return { ok: false, error: "bad_state" };
  await env.DB.prepare(
    "INSERT INTO provision_jobs (id, account_id, handle, status, server_id, created_at, updated_at) VALUES (?, ?, ?, 'creating', ?, ?, ?)",
  )
    .bind(job.id, account.id, handle, `lonora-${handle}`, now, now)
    .run();
  const { password_hash: hash } = await env.DB.prepare("SELECT password_hash FROM accounts WHERE id = ?").bind(account.id).first();
  const out = await host(env, ["create", handle], `${account.email}\n${hash}\n`);
  const url = /^instance_url=(https:\/\/[a-z0-9.-]+\/)$/m.exec(out.stdout)?.[1];
  if (out.ok && url) {
    await env.DB.prepare("UPDATE provision_jobs SET status = 'ready', updated_at = ? WHERE id = ?").bind(nowIso(), job.id).run();
    await env.DB.prepare("UPDATE accounts SET status = 'active', instance_url = ?, setup_link = NULL, reason = NULL WHERE id = ? AND status = 'provisioning'")
      .bind(url, account.id)
      .run();
    await audit(env, staff, "activated", account.id, { handle });
    return { ok: true, handle };
  }
  const message = out.ok ? "create: no address" : `create: ${out.error}`;
  if (out.code === 73) {
    // customer.sh changed nothing (the handle is already installed, or the host was busy): nothing is
    // undone, and the job names no installation, so deleting this account never removes another's.
    await env.DB.prepare("UPDATE provision_jobs SET server_id = NULL WHERE id = ?").bind(job.id).run();
  } else {
    try {
      await deprovision(env, job);
    } catch {
      // Left for staff: customer.sh remove <handle>.
    }
  }
  await env.DB.prepare("UPDATE provision_jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ?").bind(message, nowIso(), job.id).run();
  await env.DB.prepare("UPDATE accounts SET status = 'approved' WHERE id = ? AND status = 'provisioning'").bind(account.id).run();
  await audit(env, staff, "provision_failed", account.id, { error: message });
  return { ok: false, error: "provision_failed", message };
}

// A job still creating after this long (the site stopped during an attempt) is failed and undone the
// next time staff look at the list.
export const INSTALL_TIMEOUT_MS = 10 * 60_000;

export async function expireStaleJobs(env) {
  const cutoff = new Date(Date.now() - INSTALL_TIMEOUT_MS).toISOString();
  const { results } = await env.DB.prepare("SELECT * FROM provision_jobs WHERE status = 'creating' AND created_at < ?").bind(cutoff).all();
  for (const job of results) {
    try {
      await deprovision(env, job);
    } catch {
      // keep going; the error is recorded below
    }
    await env.DB.prepare("UPDATE provision_jobs SET status = 'failed', error = 'timeout', updated_at = ? WHERE id = ?").bind(nowIso(), job.id).run();
    await env.DB.prepare("UPDATE accounts SET status = 'approved' WHERE id = ? AND status = 'provisioning'").bind(job.account_id).run();
    await audit(env, "system", "provision_failed", job.account_id, { error: "timeout" });
  }
}
