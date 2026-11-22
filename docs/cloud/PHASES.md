# Lonora Cloud — executable phases

**Status: Proposed. Not binding until VISION.md Amendment 3 is issued.** Read [README.md](README.md) (rules for Claude
Code), [DECISIONS.md](DECISIONS.md) and [PLAN.md](PLAN.md) first. Repositories: `lonorabot` = this repository;
`lonora-cloud` = the new control-plane repository (D2).

## Definition of done (every task)

1. Branch from the latest `main` of the repository the task lives in, named `cloud/p<phase>-t<n>-<slug>`; one pull
   request titled `cloud(P<phase>-T<n>): <summary>`.
2. The acceptance criteria below are met and shown in the pull request description with the commands that prove them.
3. Tests are added or changed with the behaviour. In `lonorabot`: `bash scripts/build.sh` plus the suites the change
   touches (for example `tests/ops/lifecycle_test.sh`, `tests/test_push_sender.py`, `pnpm test:web`, `pnpm test:mobile`).
   In `lonora-cloud`: `make check`.
4. Self-hosted behaviour is unchanged unless the new setting is present (every Phase 1 task).
5. No secret, credential, customer data or generated build output is committed.
6. Docs describe the behaviour as built (VISION §0.4): `docs/operations.md` for operators, the help centre for customers.
7. If a `Proposed` decision blocks the task, stop and ask the owner; record the answer in DECISIONS.md.

---

## Phase 0 — Owner foundations (no code)

| ID | Task | Done when |
|---|---|---|
| P0-T1 | Edit and issue Amendment 3 ([draft](AMENDMENT-3-DRAFT.md)) with its date. | The owner says "issued". |
| P0-T2 | Confirm or change D1–D18. | Every one is `Confirmed` or `Changed`. |
| P0-T3 | Company (D19); engage counsel for D20–D23; accountant. | Counsel engaged with this plan as the brief. |
| P0-T4 | Register the cloud domain (D5); Cloudflare account; brand name check. | Domain in Cloudflare. |
| P0-T5 | Apply to the billing provider and get written acceptance of the category (D16). | Written answer received. |
| P0-T6 | Cloud accounts: one for the control plane, one for the fleet, one staging project (D3); spending alerts. | API tokens exist in the owner's vault. |
| P0-T7 | Create the empty repository `loorksy/lonora-cloud` and add it to the Claude Code environment. | A Claude Code session can clone it. |
| P0-T8 | Staff identity provider (D25) and hardware keys for the first staff. | Owner signs in with a key. |
| P0-T9 | MetaApi (D27, D32): open the company's MetaApi account; ask MetaApi in writing for permission to serve customers from it, volume pricing for high reliability, a DPA; with a test token, record the server's maximum `validity_in_hours`, the `get_access_rules` manifest entry for trading + streaming on listed accounts, and whether rotating the company token invalidates narrowed tokens (PLAN §3.8). | Written answer from MetaApi; the three facts recorded in D31's row. |

**Exit:** Amendment 3 issued, D1–D18 and D27–D31 settled, MetaApi's written answer received, repository and accounts
exist.

---

## Phase 1 — Instance readiness (`lonorabot`)

All additive, off by default, no change to VISION §6 or agent behaviour (Amendment 3 §6).

| ID | Task | Acceptance criteria |
|---|---|---|
| P1-T1 | Append the issued Amendment 3 verbatim under "## Owner amendments" in `VISION.md`; change the status line of `docs/cloud/*.md` to "Adopted by Amendment 3". | Text matches the owner's issued version exactly; no other mandate text changed. |
| P1-T2 | Machine-readable `lonora`: `--json` for `status`, `start`, `update`, `rollback`, `backup`, `restore-test` in `infra/compose/lonora`; one JSON object on stdout, human text unchanged without the flag; documented schema in `docs/operations.md`. | `tests/ops/lifecycle_test.sh` (or a sibling test) parses every command's JSON; exit codes unchanged; secrets never printed. |
| P1-T3 | Origin-certificate TLS mode (D4): `infra/compose/mode-origin.yml` and a Caddyfile branch that serves a provided certificate/key and requires the Authenticated Origin Pulls client CA; `install.sh --origin-cert F --origin-key F --origin-pull-ca F`; `lonora` selects the mode like it selects direct/proxy. | Direct and proxy modes byte-identical in behaviour; origin mode rejects a client without the pull certificate; `/api/events/stream` still unbuffered. |
| P1-T4 | Setup link (D7): the first-run screen that calls `initializeOwner` (`apps/web/src/lib/bootstrap.ts`) reads `#token=…` from the URL fragment, pre-fills it, removes it from history immediately; `lonora rotate-bootstrap` writes a new `LONORA_BOOTSTRAP_TOKEN` and recreates the api service. | Web test: link opens, token never appears in a request URL or server log, owner created; reuse returns 409; rotated token invalidates the old link. |
| P1-T5 | `lonora quiesce [--timeout SECONDS] --json`: maintenance on → wait until no `ln_trading_journal` row is in `UNRESOLVED_STATUSES` (`lonora_contracts.trading`) or timeout → stop the gateway; output lists remaining unresolved operation ids. Read-only query run inside the api container. | Test with a seeded unresolved row: quiesce reports it and still stops; `lonora start` resumes and reconciliation runs; no write to the journal by quiesce. |
| P1-T6 | Hosted notices (Amendment 3 §5): `LONORA_HOSTED_PORTAL_URL` shows one "Account and billing" link in settings and sign-in (web and mobile); `LONORA_HOSTED_NOTICE_FILE` (JSON: level, ar, en, until) shown only there. | Absent settings → nothing rendered (snapshot tests); present → link and notice in Arabic RTL and English; nowhere else. |
| P1-T7 | Push relay client in `packages/adapters/src/lonora_adapters/channels/expo_push.py`: with `LONORA_PUSH_RELAY_URL` and `LONORA_PUSH_RELAY_TOKEN`, send the same payloads and device registrations to the relay instead of Expo. | `tests/test_push_sender.py` covers both paths with a fake relay; default path unchanged. |
| P1-T8 | Mobile connect (D9): deep link `lonora://connect?server=https://…` and QR scan on `apps/mobile/app/server.tsx`, stored through `apps/mobile/lib/session.tsx`; confirmation shows the host; https required except local addresses. | Mobile tests for link parsing, rejection of non-https remote hosts, manual entry still works. |
| P1-T9 | Passkeys on customer subdomains: confirm each instance serves Digital Asset Links and Apple app-site-association for its own host from `LONORA_PASSKEY_*`; document `webcredentials:*.lonora.app` in the mobile release configuration. | Checklist run on two staging hosts with real devices; results in `docs/mobile/`. |
| P1-T10 | Workspace image location: `LONORA_WORKSPACE_IMAGE` (path) so `workspace.img` can live on an attached volume; default `workspace.img` next to `.env` as today. | Lifecycle test with a custom path; grow-in-place and never-shrink rules unchanged. |
| P1-T11 | `lonora diagnostics --json`: versions, service states, `/ready`, resource usage and the last N lines per service, scrubbed inside the api container with `lonora_security.secrets`, size-capped. | Test: a planted secret and its base64/hex/URL forms never appear in the bundle. |
| P1-T13 | Proxied `LONORA_DOMAIN` (D4): the workspace guard blocks the addresses `LONORA_DOMAIN` resolves to (`address_domains` in `packages/workspace/src/lonora_workspace/egress.py`). Behind Cloudflare's proxy those are shared edge addresses, so blocking them would cut the workspace off from every site on that edge. In hosted mode, refuse `LONORA_DOMAIN` by name only and block the VM's own addresses (`LONORA_WORKSPACE_HOST_ADDRESSES`), as `OTHER_VENUE_DOMAINS` already works. | Test: with the setting, `LONORA_DOMAIN` is refused by name and no CDN address is learned; without it, behaviour unchanged. |
| P1-T12 | Hosted broker provisioning (D27, D30, Amendment 3 §10): with `LONORA_BROKER_PROVISIONER_URL` and its instance credential set, the connect flow asks only number, server and the password Secret card (no MetaApi-token card); the create/deploy/update/remove steps of `packages/trading/src/lonora_trading/broker_provisioning.py` call the provisioner (keeping the stable `transaction-id`) instead of `metaapi_provisioning.py`; the returned narrowed token is written as `METAAPI_TOKEN` through the existing `replace_token` path (`broker_manage.py`), also for renewals; a "this connection costs X per month" confirmation from the provisioner is shown in the connect step before creation. Trading code and the execution door untouched. | Tests with a fake provisioner: connect, retry after a lost answer makes one account, password never logged or kept after acceptance, renewal swaps the token without dropping the connection, extra-connection confirmation; without the setting the self-hosted flow (owner's token card) is unchanged; core safety tests pass unchanged. |

**Exit:** all tasks merged; a fresh staging VM installs non-interactively in origin mode, reaches `/ready`, onboards
through a setup link, answers every `--json` command, and a self-hosted install without the new flags behaves as before.

**Starter prompt (Phase 1):**
> Read VISION.md including Amendment 3, AGENTS.md, CLAUDE.md, docs/cloud/README.md, docs/cloud/DECISIONS.md and the
> Phase 1 section of docs/cloud/PHASES.md. Implement only task P1-T2 on a branch `cloud/p1-t2-status-json` from the
> latest main. Keep self-hosted behaviour identical without the new flag, never print secrets, extend
> tests/ops/lifecycle_test.sh, run bash scripts/build.sh, and open a pull request titled "cloud(P1-T2): …" that lists
> the commands proving each acceptance criterion.

---

## Phase 2 — Control-plane foundation (`lonora-cloud`)

| ID | Task | Acceptance criteria |
|---|---|---|
| P2-T1 | Scaffold: `apps/cloud-api`, `apps/cloud-worker`, `apps/portal-web`, `apps/admin-web`, `apps/host-agent`, `packages/cloud-contracts`, `packages/cloud-db`, `packages/cloud-core`, `packages/ui` (tokens copied from `lonorabot/packages/ui-tokens`), `infra/` (OpenTofu), `docs/`, `tests/`; Python 3.12 + FastAPI, pnpm + turbo, Ruff/Pyright/Biome, `make check`, CI, `AGENTS.md`/`CLAUDE.md` mirroring lonorabot's rules plus the zero-access rule. | `make check` green in CI on an empty app; Docker images build. |
| P2-T2 | Database v1 (PLAN §11): accounts, factors, sessions, legal documents/acceptances, plans/versions, subscriptions, billing events, instances, instance events, entitlements, jobs, staff, roles, approvals, audit log; Alembic; expand/contract policy. | Migrations up/down on a fresh database; constraint tests (unique handle, unique provider event id). |
| P2-T3 | Job queue on Postgres with leases (`FOR UPDATE SKIP LOCKED`), retries with backoff, dead letter, idempotency keys, `awaiting_approval` state. | Concurrency test: two workers never run one job; a crashed worker's lease expires and the job resumes. |
| P2-T4 | Customer auth: signup, email verification, login, sessions, password reset, TOTP, passkeys, rate limits, CAPTCHA hook, breached-password check. | E2E tests for each flow; brute force throttled; sessions revocable. |
| P2-T5 | Staff auth (D25): OIDC, WebAuthn required, session timeout, re-authentication for sensitive actions; RBAC engine with PLAN §7.2 as data; deny by default. | A test per matrix cell (allowed and denied). |
| P2-T6 | Audit log: append-only table, hash chain, verification job, every staff read of customer data and every action recorded. | Tampering with any row fails verification. |
| P2-T7 | Email: provider abstraction, outbox table, templates (ar/en, RTL), bounce/complaint webhooks. | Templates render in both languages; outbox retries. |
| P2-T8 | KMS/Vault integration: job-signing key, provider tokens, escrow public key; config loading. | No secret in environment dumps or logs (test). |
| P2-T9 | Portal and admin shells: auth screens, layout, i18n (Arabic default, RTL), dark/light, accessibility baseline. | Playwright: sign in on both; axe checks pass. |

**Exit:** CI green; auth E2E; RBAC deny-by-default proven; audit chain verified.

**Starter prompt (Phase 2):**
> In loorksy/lonora-cloud, read docs/cloud/PLAN.md, PHASES.md and DECISIONS.md from loorksy/lonorabot. Implement P2-T1:
> scaffold the repository exactly as listed, mirror lonorabot's toolchain versions, add `make check` and CI, and write
> AGENTS.md/CLAUDE.md with the README rules (zero access, no secrets, Arabic first). Open a pull request.

---

## Phase 3 — Provisioning engine and host agent (`lonora-cloud`, uses Phase 1)

| ID | Task | Acceptance criteria |
|---|---|---|
| P3-T1 | Provider driver interface (create/delete server, volume, firewall, snapshot, resize, list, labels) + a fake driver for tests (D1). | Contract tests run against the fake driver. |
| P3-T2 | Hetzner Cloud driver (D3) and regions/capacity table (D12). | Staging: create and destroy a server with volume and firewall; labels set; no orphan after destroy. |
| P3-T3 | Cloudflare driver (D4, D5): proxied record per handle, Origin CA certificate per instance, Authenticated Origin Pulls, record and certificate revocation on destroy. | Staging host reachable only through Cloudflare; direct IP access refused. |
| P3-T4 | cloud-init template: hardening (`harden-host.sh`), pinned Docker, SMTP 25 blocked, host agent install, enrollment token. | Fresh VM enrolls within 2 minutes. |
| P3-T5 | Host agent (PLAN §10): enrollment, mTLS, signed-job verification (signature, instance id, expiry, nonce), allowlist runner over `lonora … --json`, heartbeat, progress, self-update. | Tests: tampered, replayed, expired or foreign-instance jobs refused; unknown job type refused; no listening port. |
| P3-T6 | Provisioning state machine (PLAN §4.1–4.2) with idempotent steps, retries, compensations, internal ticket on final failure. | Fault-injection tests at each step leave no orphan resources; a reconciler job finds none. |
| P3-T7 | Key escrow (D8): sealing on the VM to the KMS public key; dual-approval decrypt flow for DR. | The control plane database holds only sealed blobs; decrypt requires two approvals; audited. |
| P3-T8 | Setup-link handoff (portal-encrypted, never stored), onboarding polling via `GET /onboarding`, bootstrap rotation after onboarding and on expiry. | E2E: paid → link → owner onboarded → `active`; expired link replaced. |
| P3-T9 | Push relay service (D9): relay credentials per instance, device binding per instance, rate limits, operator notices. | An instance cannot push to a device registered by another instance (test). |
| P3-T10 | Quiesce, suspend, resume, destroy flows (PLAN §4.6) with DNS/certificate cleanup and retention timers (D24). | E2E on staging including an instance with a seeded unresolved operation. |
| P3-T11 | Staging end-to-end: real VM to `active`; SSE through Cloudflare; uploads at Lonora's limits; voice check; p95 provisioning time. | 20 consecutive provisions succeed; p95 under 5 minutes. |
| P3-T12 | Cost measurement for each plan size with the worksheet (PLAN §5.3), including MetaApi high-reliability connections. | Numbers recorded in DECISIONS D14 discussion; owner sets prices. |
| P3-T13 | `broker-provisioner` (PLAN §3.8): separate deployment; company MetaApi token in KMS/Vault by workload identity; egress allowlist of MetaApi provisioning and token-management hosts only; endpoints of PLAN §12 bound to the calling instance's accounts; create in the MetaApi region nearest the broker server, tag with the instance id, deploy at the D29 tier; password held in memory only; audit and the customer-facing connection log. | Tests: password absent from database, queues and logs (planted-value scan); an instance cannot read or change another instance's accounts; a request to a trading host from the provisioner fails at the network; repeated create with one `transaction_id` makes one account; staging connects a MetaApi demo account end to end through P1-T12. |
| P3-T15 | Open-agent hosting (Amendment 3 §11): `LONORA_WORKSPACE_BLOCKED_DOMAINS` set to the cloud domain; SMTP 25 blocked at the provider firewall and nothing else. | Staging: from a customer workspace, HTTPS/WSS to a public API, a remote MCP server, `pip install`, `git clone` and SSH all work; another customer's instance, the portal API, the provisioner, MetaApi and `169.254.169.254` are refused. |
| P3-T14 | Narrowed tokens and metering: mint tokens narrowed to the instance's account set (trading + streaming), validity per D31, re-mint on connect/remove and on schedule, deliver by host-agent `broker_token` job or instance pull; undeploy on suspension and deploy on resume; deployed-hours metering and monthly reconciliation with MetaApi's invoice. | A control-plane outage simulated for 48 h does not stop trading; a token under 7 days alerts; suspension stops MetaApi billing for that instance; usage report matches MetaApi's numbers within 1%. |

**Exit:** the API can create, update, suspend, resume and destroy a real customer instance with no manual step and no
orphan resources, and that instance connects an MT5 demo account with only number, server and password.

---

## Phase 4 — Customer portal and billing (`lonora-cloud`)

| ID | Task | Acceptance criteria |
|---|---|---|
| P4-T1 | Onboarding wizard: handle (live availability, reserved list, profanity filter), region, plan, legal acceptances recorded per version. | Playwright in Arabic and English. |
| P4-T2 | Geo and sanctions screening at signup and checkout (D21). | Blocked countries refused with a clear message; decisions logged. |
| P4-T3 | Provisioning progress (SSE), dashboard, "Open my Lonora", "Connect phone" QR, version and update notes. | E2E against staging. |
| P4-T4 | Billing provider integration (D16) behind `BillingProvider`; idempotent webhooks; entitlements recomputed from events. | Replaying any webhook twice changes nothing; out-of-order events handled. |
| P4-T5 | Plans and prices as data (D13, D14); proration preview; upgrade triggers resize; downgrade triggers migration when the disk must shrink. | Each path E2E in test mode. |
| P4-T6 | Trial (D15): card required, abuse heuristics, expiry handling. | Trial ends → export offer → destroy after 3 days. |
| P4-T7 | Dunning, suspension with quiesce, resume; notices by email, push relay and the hosted notice file. | Failed-payment simulation through day 7 suspends; payment resumes within 5 minutes. |
| P4-T8 | Cancel at term end, data export, account deletion with cool-off (D24). | Deletion purges per D24; invoices retained. |
| P4-T9 | Maintenance window, "Update now", backups list, backup download, restore request (typed confirmation). | Restore job requires confirmation and warns about replaced data. |
| P4-T10 | Transparency page (staff access log and the broker connection log of P3-T13), notification preferences, security page (sessions, factors), WCAG 2.1 AA. | axe checks; every break-glass session and every connection created/renewed/removed appears for the customer. |
| P4-T11 | Connection billing (D28): included connections per plan; extra connections as a subscription quantity changed on connect/remove; price returned to the instance for the confirmation of P1-T12. | Connecting beyond the included number adds the charge after the owner confirms; removing it drops the charge at the next period. |

**Exit:** test-mode purchase → active instance → plan change → cancel → deletion, fully automated.

---

## Phase 5 — Administration, supervisors and support (`lonora-cloud`)

| ID | Task | Acceptance criteria |
|---|---|---|
| P5-T1 | Admin shell with RBAC-gated navigation, deployed behind the Zero Trust gateway. | Unauthenticated and wrong-role access denied (tests). |
| P5-T2 | Customers module (PLAN §7.3.2). | Search by email/handle/invoice; every view audited. |
| P5-T3 | Fleet/instances module; actions as signed jobs; approvals for restore/migrate/resize/destroy. | Destroy impossible without the second approval. |
| P5-T4 | Provisioning queue module: attempts, dead letters, retry, compensate. | Operator can recover a failed provisioning in staging. |
| P5-T5 | Billing module: refunds and credits with per-role limits and approvals; coupons; dunning view. | Refund above limit waits for Finance approval. |
| P5-T6 | Ticketing core (D17): tickets, messages, internal notes, statuses, assignment, teams, macros, SLA policies and timers, merge, CSAT, email in/out. | SLA timers pause on "pending customer"; breach events fire. |
| P5-T7 | Agent workspace with the instance context panel and the diagnostics-consent flow (P1-T11). | No content from the instance is visible except a consented, scrubbed bundle. |
| P5-T8 | **Supervisors panel** (PLAN §7.4): queues, SLA board, team performance, QA reviews, escalations, approvals inbox, roster (D18), KB approval, broadcasts, customer health. | Each widget backed by tested queries; broadcasts reach only the chosen segment. |
| P5-T9 | Break-glass (PLAN §7.5): consent or dual approval, scope, time box, customer notifications, recording references. | A session without consent/approval cannot start; it ends automatically at the time box. |
| P5-T10 | Help centre: articles (ar/en), versions, search, portal and ticket-form suggestions. | Launch article set from PLAN §8 drafted. |
| P5-T11 | Live chat: embedded Chatwoot or in-house widget (D17), linked to tickets. | A chat can be converted to a ticket with history. |
| P5-T12 | Audit viewer, staff management, access reviews. | Quarterly review report generated. |

**Exit:** every RBAC cell tested; a ticket goes L1 → L2 → solved within SLA timers; break-glass impossible without
consent or approvals; the supervisors panel shows live data on staging.

---

## Phase 6 — Operations and reliability

| ID | Task | Acceptance criteria |
|---|---|---|
| P6-T1 | Off-host backups: agent uploads `lonora backup` output; object lock per plan retention; checksum verification. | Missing backup > 26 h alerts; checksum mismatch alerts. |
| P6-T2 | Workspace volume snapshots (D10) on the plan schedule; restore of a snapshot to a new volume. | Snapshot restore drill on staging. |
| P6-T3 | Weekly `lonora restore-test` scheduling inside windows; measure peak memory on Starter; pause the workspace if required. | Results visible in portal and admin; failures page SRE. |
| P6-T4 | Release ingestion: signature verification, `release.json`, `compatibility.json`; add SBOM, scan and signing to `lonorabot/.github/workflows/publish-server-image.yml` (lonorabot PR). | Unsigned or unscanned image cannot be rolled out. |
| P6-T5 | Rollout manager (PLAN §13.3, D11): rings, windows, automatic halt, per-instance hold. | Staging fleet of ≥ 20 instances: injected failure in ring 1 halts the rollout. |
| P6-T6 | Monitoring: heartbeat metrics to the time-series store, external probes from two regions, alert rules of PLAN §13.5, dashboards. | Each alert fires in a staging drill. |
| P6-T7 | Observability stack (D26) and logging policy: no instance content centrally; scrubbed error tracking. | Log review finds no customer content. |
| P6-T8 | Status page, incident module, communication templates (ar/en). | SEV1 drill: status page within 15 minutes. |
| P6-T9 | Fleet maintenance: OS patch windows, Docker upgrades as rollouts, agent self-updates. | Patch rollout on staging with reboots inside windows. |
| P6-T10 | Disaster recovery: runbook and drill restoring a region from backups with escrow (dual approval). | RTO ≤ 4 h for the staging fleet. |
| P6-T11 | Runbooks for every alert; on-call rota and paging. | Each alert links to its runbook. |
| P6-T12 | Cost dashboards per instance and plan. | Gross margin per plan visible. |

**Exit:** full staging rollout with automatic halt; DR drill within RTO; every alert has a runbook.

---

## Phase 7 — Security, compliance and legal

| ID | Task | Acceptance criteria |
|---|---|---|
| P7-T1 | Threat model (PLAN §14) with mitigations tracked as issues. | Reviewed by the owner and an external reviewer. |
| P7-T2 | Abuse system (PLAN §13.8): egress counters, cases, action ladder, abuse mailbox, provider notices. | Drill: simulated port scan stops the workspace only. |
| P7-T3 | Hardening: CSP, dependency and secret scanning in CI for both repositories, SBOMs. | No high findings open. |
| P7-T4 | GDPR features: export, deletion, retention purges, records of processing, sub-processors page. | Data-subject request completed end to end. |
| P7-T5 | Legal documents in the portal (texts by counsel): versioning, acceptance, re-acceptance on change. | New version forces re-acceptance at next sign-in. |
| P7-T6 | External penetration test of portal, admin, host agent, edge and a customer VM; fixes. | No critical/high open; `security.txt` and disclosure policy published. |
| P7-T7 | SOC 2 readiness: policies, evidence automation. | Readiness assessment scheduled. |

**Exit:** pen test clean; counsel signs off D20–D23; legal documents published.

---

## Phase 8 — Launch and growth

| ID | Task | Acceptance criteria |
|---|---|---|
| P8-T1 | Marketing site (ar/en): promise, how it works, security, pricing, FAQ, legal, status. | Lighthouse ≥ 90; Arabic RTL reviewed by a native speaker. |
| P8-T2 | Public help centre and video guides (connect model key, MetaApi, Telegram, phone). | Every launch article published in both languages. |
| P8-T3 | Private alpha with 10–20 traders. | Weekly feedback; activation and support numbers recorded. |
| P8-T4 | Closed beta with waitlist and discounted pricing. | 100 customers; SLA met for four weeks. |
| P8-T5 | Referral programme (account credit). | Fraud checks; credits applied by billing events. |
| P8-T6 | Custom domains for Max (Cloudflare for SaaS). | Verified domain serves the instance with its own certificate. |
| P8-T7 | Support assistant (human approves every send; company key only). | Answers cite help-centre articles; no customer data beyond the ticket. |
| P8-T8 | Lifecycle email and privacy-friendly analytics. | Funnel dashboard live. |
| P8-T9 | Go/no-go checklist (below). | All items green. |

### Launch go/no-go checklist

- [ ] Amendment 3 in VISION.md; D1–D32 confirmed.
- [ ] Counsel sign-off on D20–D23; legal documents published; risk disclosure accepted at signup.
- [ ] Billing provider live mode approved; tax configured.
- [ ] Pen test: no critical/high open.
- [ ] 30 consecutive days of staging and beta with availability ≥ target, backups 100%, restore tests passing.
- [ ] Rollout with automatic halt proven; DR drill within RTO.
- [ ] Support staffed per D18; help centre complete; status page live; on-call rota active.
- [ ] Cost per instance measured; prices give the target margin.
- [ ] TradingView licence and icon licences settled.
- [ ] MetaApi written agreement (D32) in place; the provisioner's network test proves it cannot reach trading hosts;
      broker passwords proven absent from every control-plane store and log; undeploy-all runbook rehearsed.

---

## Product track (`lonorabot`, independent of hosting; each item needs the owner's go-ahead and its own spec)

| ID | Item | Notes |
|---|---|---|
| PT-2 | Openness gaps with nanobot (D35): skills catalogue installable from chat; plugin bundles; stdio MCP tools as native tools. | Each weighed against VISION P3/P5 and `docs/mcp-boundary.md`. |
| PT-3 | Workspace CLI order commands (VISION §7.3: `trade`, `close`, `modify`, `cancel`) — not built yet; prerequisite of PT-4. | VISION phase 4 "done when". |
| PT-4 | Agent environment with Claude Code's philosophy: [docs/proposals/agent-environment.md](../proposals/agent-environment.md) (G1–G5). | Decisions A1–A5. |

---

## Phase 9 — Scale

| ID | Task | Notes |
|---|---|---|
| P9-T1 | Dense cells tier: containers on shared hosts, workspace under gVisor or Kata, per-customer networks. | Only after a dedicated security review approves it. |
| P9-T2 | More regions; customer region choice and region move (migration job). | |
| P9-T3 | Enterprise: dedicated hosts, portal SSO, contract SLA, custom DPA. | |
| P9-T4 | Continuous PostgreSQL WAL archiving for a 15-minute RPO on Max (additive `lonorabot` change). | Off by default for self-hosters. |
| P9-T5 | SOC 2 Type II; ISO 27001 on demand. | |
| P9-T6 | Local currencies and prices. | |
| P9-T7 | Partner programme (brokers, prop firms, creators) within counsel's limits. | |
