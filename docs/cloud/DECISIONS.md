# Lonora Cloud — owner decisions

Each decision has a recommendation. Status is `Proposed` until the owner confirms it, then `Confirmed (date)` or
`Changed (date): <what>`. A Claude Code session that needs a `Proposed` decision asks the owner and records the answer
here in the same pull request. "Blocks" names the first task that cannot start without it.

## Product and architecture

| ID | Decision | Recommendation | Why | Blocks | Status |
|---|---|---|---|---|---|
| D1 | Isolation unit per customer | **One VM per customer** running the existing production stack. Dense container cells are a later, cheaper tier (Phase 9) after a security review. | The workspace runs arbitrary agent code with egress and setuid-class capabilities; a shared kernel beside other customers' broker credentials is not acceptable for a trading product. The installer and `lonora` CLI were built for one owner per server. | P3-T1 | Proposed |
| D2 | Where the control plane lives | **New repository `loorksy/lonora-cloud`.** | Different security boundary (it knows every customer) and release cadence; the Lonora `Dockerfile` copies `packages/` whole, so in-repo code would ship inside every customer image. | P2-T1 | Proposed |
| D3 | Cloud provider for the customer fleet | **Hetzner Cloud** to start (API, firewalls, volumes, snapshots, EU + US + Singapore). Behind a provider driver interface so DigitalOcean/AWS can be added. Verify current prices and the provider's acceptable-use terms for agent workloads. | Lowest cost per GB of RAM among API-driven providers; VM-per-customer makes RAM the main cost. | P3-T2 | Proposed |
| D4 | Edge and TLS | **Cloudflare proxied DNS + one Cloudflare Origin CA certificate per VM + Authenticated Origin Pulls**; firewall accepts 443 only from Cloudflare ranges. | Avoids Let's Encrypt per-registered-domain issuance limits at signup volume, adds DDoS/WAF, hides origin IPs. Trade-off: Cloudflare terminates TLS. Alternative: DNS-only + Caddy ACME with several issuers. | P1-T3 | Proposed |
| D5 | Domains | Owner picks and registers the cloud domain. Placeholders used in this plan: `<handle>.lonora.app` (customer), `my.lonora.app` (portal), `admin.lonora.app` (staff, behind Zero Trust), `status.lonora.app`, `lonora.app` (marketing). | — | P3-T3 | Proposed |
| D6 | Model access | **BYOK only**: the customer enters their own provider keys in their Lonora, as VISION §12 requires. Platform-managed model credits are not offered. | The earlier owner decisions "D4" and "Q22" recorded in docs/usage-dashboard.md (not this table's D4) forbid spend caps and budgets; managed credits would need them. Also keeps zero access. | — | Proposed |
| D7 | Signing in to a customer's Lonora | **Independent of the portal.** The customer sets their own password/passkey on their instance through a one-time setup link. No SSO from the portal into the instance. | A portal or control-plane compromise must not open any customer's trading. This is the "we cannot access your account" promise. | P1-T4 | Proposed |
| D8 | Recovery keys (backup key, `LONORA_ENCRYPTION_KEY`) | **Escrowed**, encrypted on the VM to a KMS public key; decryption needs two staff approvals and is audited. Customer-managed keys (no escrow) offered later on Max/Enterprise. | Without escrow a lost VM is a lost customer. Honest trade-off: escrow means the company could, with dual control, recover a customer's data. | P3-T7 | Proposed |
| D9 | One app for self-hosted and cloud | **One mobile app**; cloud customers connect by scanning a QR code from the portal. | One store listing, one review, one codebase. | P1-T8 | Proposed |
| D10 | Workspace backups | **Workspace on its own attached volume**, provider snapshots (daily Pro/Max, weekly Starter). `lonora backup` stays as is for database, artifacts and config. | `lonora backup` deliberately excludes the workspace (up to tens of GB). | P6-T2 | Proposed |
| D11 | Update window default | **Weekend window while forex is closed** (Saturday, customer's time zone); customer may choose another window. Security fixes may go sooner with notice. Customers trading 24/7 instruments (crypto CFDs) pick their own window. | A gateway restart mid-week interrupts live trading work; reconciliation makes it safe, but quiet is better. | P6-T5 | Proposed |
| D12 | Regions | Start with **one EU region** close to the customers and to the MetaApi region the brokers use; add US/Asia when demand exists. | Latency to MetaApi matters more than latency to the browser. | P3-T2 | Proposed |

## Broker connections (owner decision of 2026-11-22)

| ID | Decision | Recommendation | Why | Blocks | Status |
|---|---|---|---|---|---|
| D27 | Who provides MetaApi | **The company's MetaApi account.** The customer enters only account number, server and password; the company pays MetaApi and bills the customer. Design in PLAN §3.8, mandate text in Amendment 2 §10. | Owner: «لا يحتاج المستخدم غير رقم الحساب والخادم وكلمة المرور، وليس توكن … يتم محاسبتنا نحن». | P1-T12 | Confirmed (2026-11-22) |
| D28 | Pricing of connections | Each plan **includes** connections (Starter 1, Pro 2, Max 5); more are billed monthly at cost plus margin. Only the number of connections is counted: never trades, volume or activity. | MetaApi bills per deployed account; included connections keep pricing simple; P1 forbids anything else. | P4-T11 | Proposed |
| D29 | MetaApi reliability tier | **High reliability** for every paying plan (MetaApi recommends it for production; it costs more); regular only for trials. | A trading agent that loses its connection overnight is the failure customers remember. | P3-T13 | Proposed |
| D30 | Where the password is typed | **In Lonora's Secret card, as today**; it passes once through the provisioning service to MetaApi in memory. Alternative: MetaApi's own configuration link (the customer types the password on a MetaApi page; it never touches our servers) but the customer leaves Lonora. | Keeps the journey inside chat (VISION §9.2); honest disclosure of the single pass. | P1-T12 | Proposed |
| D31 | Narrowed-token lifetime | **14 days, renewed every 3 days**; alert if any token is under 7 days. | MetaApi narrowed tokens cannot be revoked before expiry in the SDK; short enough to contain, long enough that a control-plane outage does not stop trading. Verify the server's maximum in P0-T9. | P3-T14 | Proposed |

## Open agent (owner requirement of 2026-11-22)

| ID | Decision | Recommendation | Why | Blocks | Status |
|---|---|---|---|---|---|
| D33 | Crypto as a first-class venue | — | Owner: «لا داعي للكريبتو نهائياً … على MT5 فقط». Lonora Cloud trades MT5 through MetaApi only, on any symbol the customer's broker offers (Amendment 2 §12). The crypto adapter spec was removed. | — | Rejected (2026-11-22) |
| D34 | Fixed outbound IP per customer | — | Its only reason was crypto-exchange key allowlists (D33). MetaApi connects to the broker from MetaApi's side, so an MT5-only service does not need it. | — | Withdrawn (2026-11-22) |
| D35 | Closing the gaps with nanobot | Consider for `lonorabot`, not for hosting: a skills catalogue with install from chat, plugin bundles (skills + MCP servers), stdio MCP tools as native tools. Each is a product change under VISION P3/P5 and `docs/mcp-boundary.md`; see [docs/proposals/agent-environment.md](../proposals/agent-environment.md). | Owner wants nanobot-level openness; today Lonora covers it through the workspace and owner-trusted remote MCP. | PT-2 | Proposed |

## Commercial

| ID | Decision | Recommendation | Blocks | Status |
|---|---|---|---|---|
| D13 | Plans | Resource tiers only (VISION P1: no trading, activity or model limits). Starter (8 GB VM, workspace 2 GB / 1 CPU / 10 GB), Pro (16 GB, workspace 4 GB / 2 CPU / 20 GB), Max (32 GB dedicated vCPU, workspace 8 GB / 4 CPU / 50 GB, custom domain, daily snapshots, priority support), Enterprise (dedicated, SSO, contract SLA). Sizes follow the installer preflight (RAM ≥ 3584 MB + workspace memory). | P4-T5 | Proposed |
| D14 | Prices | Set **after** measuring real cost per instance in Phase 3 with the cost worksheet in PLAN.md §5.3. Starting hypotheses to test: Starter $39–49, Pro $79–99, Max $149–199 per month, two months free on annual. | P4-T5 | Proposed |
| D15 | Trial | **7 days on Starter, card required**, instance destroyed 3 days after an unconverted trial ends (export offered). | P4-T6 | Proposed |
| D16 | Billing provider | Depends on D19. **Stripe Billing + Stripe Tax** if the company is in a Stripe country; otherwise **Paddle** (merchant of record: it collects and remits global sales tax/VAT). Before integrating, get written confirmation that the provider accepts automated-trading software. | P4-T4 | Proposed |
| D17 | Support desk | **Built in-house** in the control plane (tickets, SLAs, macros, CSAT, supervisors, approvals) because it needs instance context, RBAC and break-glass. Live chat can start with an embedded Chatwoot (open source, self-hosted) and move in-house later. | P5-T6 | Proposed |
| D18 | Support coverage | Arabic + English. Starter/Pro: business hours (owner's time zone). Max: 24/7 for P1 incidents. | P5-T8 | Proposed |

## Company and legal (owner + counsel; never settled by Claude Code)

| ID | Decision | Notes | Blocks | Status |
|---|---|---|---|---|
| D19 | Company jurisdiction | Drives payment provider, tax, licensing and contracts. | P0 | Proposed |
| D20 | Regulatory position | Counsel confirms the positioning "software the customer runs on their own accounts; we host it; our systems never place orders" in each target market, and whether any licence (investment advice, portfolio management, signal provider) applies. Since D27 the company also holds the MetaApi key behind every customer connection: counsel assesses that specifically. | Launch (P8) | Proposed |
| D21 | Target markets and geo-blocking | Counsel lists countries to serve and to block (including sanctions). | P4-T2 | Proposed |
| D22 | TradingView Advanced Charts | The library ships "under the owner's TradingView license" (THIRD_PARTY_NOTICES.md). Confirm in writing that it covers a hosted service on many customer subdomains; otherwise obtain the right licence or replace it before launch. | Launch (P8) | Proposed |
| D23 | Unlicensed assets | `nvstly/icons` states no licence (THIRD_PARTY_NOTICES.md). Get permission or replace before commercial launch. SearXNG (AGPL-3.0) stays unmodified from upstream. | Launch (P8) | Proposed |
| D24 | Retention | Suspended (unpaid) instances kept 30 days, then destroyed after a final backup kept 30 more days; deleted accounts purged after 30 days; invoices kept as tax law requires. | P4-T8 | Proposed |
| D25 | Staff identity | Google Workspace (or Microsoft Entra) as the staff identity provider, hardware security keys mandatory. | P2-T5 | Proposed |
| D26 | Observability | Self-hosted Grafana stack (Prometheus/VictoriaMetrics, Loki, Grafana, Alertmanager/OnCall) or a hosted equivalent. | P6-T7 | Proposed |
| D32 | MetaApi commercial agreement | No public partner or resale terms were found. Get a **written agreement** from MetaApi that allows serving the company's customers from the company's account, with volume pricing, a DPA and sub-processor terms. Counsel also assesses what holding one key that reaches every customer's trading connection means for licensing (D20). | Launch (P8); start in P0-T9 | Proposed |
