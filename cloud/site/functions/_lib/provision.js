// One-click activation (docs/cloud PHASES.md PW-T6): staff press «تفعيل», and this creates the
// customer's dedicated server, points <handle>.<BASE_DOMAIN> at it, and installs Lonora on it with
// the stock installer. When the server reports that Lonora is ready, the account turns active by
// itself and the customer sees "Open in the app" with the one-time setup link.
//
// Settings (wrangler secrets unless noted):
//   HETZNER_TOKEN            Hetzner Cloud API token (read & write) for the fleet project (D3)
//   CLOUDFLARE_DNS_TOKEN     Cloudflare API token with DNS edit on the customer zone (D4, D5)
//   CLOUDFLARE_ZONE_ID       var: that zone's id
//   BASE_DOMAIN              var: e.g. lonora.app, so a customer is sara.lonora.app
//   SERVER_TYPE / SERVER_LOCATION / SERVER_IMAGE   vars: defaults cpx31 / fsn1 / ubuntu-24.04
//   LONORA_VERSION           var: the branch, tag or commit of the public Lonora repository every
//                            new install builds, e.g. main, v0.3.0 or a full commit id
//   HETZNER_SSH_KEY          optional var: the name of a Hetzner SSH key staff may use
// Without HETZNER_TOKEN, CLOUDFLARE_DNS_TOKEN, CLOUDFLARE_ZONE_ID and BASE_DOMAIN, provisioning is
// off and staff activate by hand with an address and a setup link.

import { audit, nowIso, randomToken, sha256 } from "./core.js";

const HETZNER = "https://api.hetzner.cloud/v1";
const CLOUDFLARE = "https://api.cloudflare.com/client/v4";
const RESERVED = new Set([
  "www", "admin", "api", "app", "my", "status", "mail", "smtp", "docs", "help", "support", "billing", "portal",
  "staff", "root", "lonora", "dashboard", "login", "signin", "signup", "register", "static", "cdn", "assets", "dev",
  "test", "staging", "prod", "ns1", "ns2", "mx", "ftp", "blog", "news",
]);

export function provisioningEnabled(env) {
  return Boolean(env.HETZNER_TOKEN && env.CLOUDFLARE_DNS_TOKEN && env.CLOUDFLARE_ZONE_ID && env.BASE_DOMAIN);
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

const shellQuote = (s) => `'${String(s).replace(/'/g, "'\\''")}'`;

// The public repository every customer server builds Lonora from. No published image is needed:
// GitHub Actions is not available, so each new server builds its own image from this source with
// the stock build-from-source.sh, then installs it by digest with the stock installer.
export const SOURCE_REPO = "https://github.com/loorksy/lonorabot.git";

// The server's first-boot script. It installs Docker and git, fetches LONORA_VERSION of the public
// repository, builds the image on the server, runs the stock Lonora installer for the customer's own
// domain, waits until Lonora answers /ready, and reports back once with the one-time bootstrap token
// that the setup link carries. Nothing else of the server is sent.
export function cloudInit({ jobId, secret, callback, domain, version }) {
  return `#!/bin/bash
set -euo pipefail
JOB=${shellQuote(jobId)}
SECRET=${shellQuote(secret)}
CALLBACK=${shellQuote(callback)}
DOMAIN=${shellQuote(domain)}
VERSION=${shellQuote(version)}
report() {
  curl -fsS -m 30 --retry 5 --retry-delay 10 -X POST "$CALLBACK" -H 'content-type: application/json' --data-binary @- <<JSON || true
{"job":"$JOB","secret":"$SECRET","status":"$1","error":"$2","setup_token":"$3"}
JSON
}
trap 'report failed install_failed ""' ERR
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q ca-certificates curl gpg git
curl -fsSL https://get.docker.com | sh
SRC=/opt/lonora-src
rm -rf "$SRC" && git init -q "$SRC"
git -C "$SRC" fetch -q --depth 1 ${shellQuote(SOURCE_REPO)} "$VERSION"
git -C "$SRC" checkout -q FETCH_HEAD
DIGEST=$(bash "$SRC/infra/compose/build-from-source.sh" --source "$SRC" --project lonora --cpus 3 --memory 6g | sed -n 's/^build: Digest: //p')
test -n "$DIGEST"
bash "$SRC/infra/compose/install.sh" --domain "$DOMAIN" --version "$DIGEST" --home /opt/lonora
for i in $(seq 1 90); do
  if curl -fsS -m 10 "https://$DOMAIN/ready" >/dev/null; then
    TOKEN=$(grep '^LONORA_BOOTSTRAP_TOKEN=' /opt/lonora/.env | cut -d= -f2-)
    trap - ERR
    report ready "" "$TOKEN"
    exit 0
  fi
  sleep 10
done
trap - ERR
report failed not_ready ""
`;
}

async function api(url, token, init = {}) {
  const res = await fetch(url, {
    ...init,
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json", ...(init.headers || {}) },
  });
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  return { ok: res.ok, status: res.status, body };
}

function cloudError(prefix, out) {
  const msg = out.body?.error?.message || out.body?.errors?.[0]?.message || `HTTP ${out.status}`;
  return `${prefix}: ${String(msg).slice(0, 200)}`;
}

// Removes what an earlier attempt created. Missing resources are not an error.
export async function deprovision(env, job) {
  if (job.dns_record_id) {
    const out = await api(`${CLOUDFLARE}/zones/${env.CLOUDFLARE_ZONE_ID}/dns_records/${job.dns_record_id}`, env.CLOUDFLARE_DNS_TOKEN, { method: "DELETE" });
    if (!out.ok && out.status !== 404) throw new Error(cloudError("dns_delete", out));
  }
  if (job.server_id) {
    const out = await api(`${HETZNER}/servers/${job.server_id}`, env.HETZNER_TOKEN, { method: "DELETE" });
    if (!out.ok && out.status !== 404) throw new Error(cloudError("server_delete", out));
  }
  await env.DB.prepare("UPDATE provision_jobs SET status = 'removed', updated_at = ? WHERE id = ?").bind(nowIso(), job.id).run();
}

// Starts one attempt. On any cloud error the attempt is failed with the provider's message, what it
// created so far is removed, and the account goes back to approved so staff can retry.
export async function startProvisioning(env, account, handle, staff, origin) {
  const jobId = randomToken(16);
  const secret = randomToken(32);
  const domain = `${handle}.${env.BASE_DOMAIN}`;
  const now = nowIso();
  await env.DB.prepare(
    "INSERT INTO provision_jobs (id, account_id, handle, status, secret_hash, created_at, updated_at) VALUES (?, ?, ?, 'creating', ?, ?, ?)",
  )
    .bind(jobId, account.id, handle, await sha256(secret), now, now)
    .run();
  await env.DB.prepare("UPDATE accounts SET status = 'provisioning', handle = ?, decided_at = ?, decided_by = ? WHERE id = ?")
    .bind(handle, now, staff, account.id)
    .run();
  const job = { id: jobId, server_id: null, dns_record_id: null };
  try {
    const server = await api(`${HETZNER}/servers`, env.HETZNER_TOKEN, {
      method: "POST",
      body: JSON.stringify({
        name: `lonora-${handle}`,
        server_type: env.SERVER_TYPE || "cpx31",
        location: env.SERVER_LOCATION || "fsn1",
        image: env.SERVER_IMAGE || "ubuntu-24.04",
        user_data: cloudInit({
          jobId, secret, callback: `${origin}/api/provision/callback`, domain,
          version: env.LONORA_VERSION || "main",
        }),
        labels: { lonora: "customer", account: account.id },
        ...(env.HETZNER_SSH_KEY ? { ssh_keys: [env.HETZNER_SSH_KEY] } : {}),
        start_after_create: true,
      }),
    });
    if (!server.ok || !server.body?.server) throw new Error(cloudError("server_create", server));
    job.server_id = String(server.body.server.id);
    const ipv4 = server.body.server.public_net?.ipv4?.ip;
    if (!ipv4) throw new Error("server_create: no IPv4 address");
    await env.DB.prepare("UPDATE provision_jobs SET server_id = ?, ipv4 = ?, updated_at = ? WHERE id = ?").bind(job.server_id, ipv4, nowIso(), jobId).run();
    const dns = await api(`${CLOUDFLARE}/zones/${env.CLOUDFLARE_ZONE_ID}/dns_records`, env.CLOUDFLARE_DNS_TOKEN, {
      method: "POST",
      body: JSON.stringify({ type: "A", name: domain, content: ipv4, ttl: 60, proxied: false, comment: `lonora customer ${account.id}` }),
    });
    if (!dns.ok || !dns.body?.result?.id) throw new Error(cloudError("dns_create", dns));
    job.dns_record_id = String(dns.body.result.id);
    await env.DB.prepare("UPDATE provision_jobs SET dns_record_id = ?, status = 'installing', updated_at = ? WHERE id = ?")
      .bind(job.dns_record_id, nowIso(), jobId)
      .run();
    await audit(env, staff, "provision_started", account.id, { handle, server_id: job.server_id });
    return { ok: true, job: jobId, handle };
  } catch (err) {
    const message = String(err.message || err).slice(0, 300);
    try {
      await deprovision(env, job);
    } catch {
      // Left for staff: the job row keeps the ids.
    }
    await env.DB.prepare("UPDATE provision_jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ?").bind(message, nowIso(), jobId).run();
    await env.DB.prepare("UPDATE accounts SET status = 'approved' WHERE id = ? AND status = 'provisioning'").bind(account.id).run();
    await audit(env, staff, "provision_failed", account.id, { error: message });
    return { ok: false, error: "provision_failed", message };
  }
}

// A job still installing after this long is failed, and its server removed, the next time staff
// look at the list (Pages Functions have no timer; the admin list runs this). The server builds the
// image itself first, so this leaves room for the build.
export const INSTALL_TIMEOUT_MS = 75 * 60_000;

export async function expireStaleJobs(env) {
  const cutoff = new Date(Date.now() - INSTALL_TIMEOUT_MS).toISOString();
  const { results } = await env.DB.prepare("SELECT * FROM provision_jobs WHERE status IN ('creating', 'installing') AND created_at < ?").bind(cutoff).all();
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
