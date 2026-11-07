# Lonora mandate execution plan

Status: in progress. Started 2026-11-07.

This plan turns the owner's *Master Production Engineering Mandate* into ordered, verifiable waves. It is based on a verified gap analysis of commit `36bea7c` (nine subsystem readers plus a source study of Nous Research's Hermes Agent at `a9ff979`). Each wave is implemented as focused slices. Every slice is reviewed adversarially and checked locally before it is merged.

GitHub CI has not run since about 2026-10-12, because the account is billing-locked. Until runner capacity is restored, every slice is verified locally: ruff, strict pyright, the resource checks, the full pytest suite against PostgreSQL 16, and the relevant `tests/check_*.py` scripts on fresh databases.

## What already holds and must be preserved

These were verified by reading the code and are kept as the foundation:

- **One agent loop.** Every trigger goes through `create_run → claim_next → execute_tool_loop`. The only model call site is `model_runtime.model_turn`.
- **Durable runs.** Runs carry fenced leases (`FOR UPDATE SKIP LOCKED`, `lease_fence`, `require_lease` on every write).
- **Checkpoint before effect.** An inflight marker is written before each effect. An interrupted mutating call comes back to the model as `tool_execution_uncertain` and is never replayed.
- **Financial execution.** All live sends pass through one executor (`ExecutionService.execute`) with a persisted `send_authorized` flag. Sends are serialized by a per-account advisory lock, journal rows are reserved idempotently, and reconciliation only observes and never resends.
- **Owner grants.** Account authority grants are device-signed and hash-pinned, and can expire or be revoked.
- **Message admission.** Messages are admitted transactionally with `(thread_id, client_nonce)` deduplication. Clients keep a nonce-addressed outbox, and the reply stream is fenced.
- **Agent sandbox.** Agent code runs in a networkless, kernel-verified sandbox.

## Critical defects found (fixed first)

| Defect | Where | Wave |
|---|---|---|
| `search_internal` returns other agents' private memory and conversations | `packages/tools/src/lonora_tools/search.py` | 1 (E5) |
| An unresolvable uncertain operation freezes the whole account, including closes and stop-loss moves | `trading/execution.py`, `broker_recovery.py`, `brokers/metaapi.py` | 1 (T2) |
| A model-independent 120k-char ceiling silently drops evidence mid-run; there is no in-run compaction | `adapter-kit/context.py` | 1 (E3) |
| Backtesting engine shipped as an agent tool, which the mandate excludes | `market/research.py`, `tools/strategy_research.py` | 1 (T1) |
| One failing scheduler step halts all maintenance, including broker reconciliation | `gateway/service.py` maintenance loop | 2 |
| Financial and authority records are hard-deleted by FK cascades from ordinary deletes | `db/schema.py` | 2 |
| No off-app delivery to the owner (no push, no telephony) | gateway, voice | 3 |
| Mobile has no trading controls, positions or emergency stop | `apps/mobile` | 3 |
| The default update deploys a stale image that cannot start on the current schema | `infra/compose/deploy-main.sh` | 4 |

## Wave 1 — engine parity with Hermes Agent, and trading integrity

**Engine track:**

- **E1 Tool execution core.** Read-only calls run concurrently in planned segments; mutating, financial and waiting calls stay serial barriers. Each tool gets a dispatch-level timeout. A guardrail controller replaces the hard `repeated_tool_call` failure. Limits end with a final reply instead of failing the run. Runtime nudges are no longer inserted as system messages.
- **E2 Capability exposure.** Each role gets an eager core toolset. The tools array stays stable within a run (long-tail tools go through a bridge). Tools used in one run carry over to the next. Each tool reports whether its backend is available. Name maps are derived from tool metadata.
- **E3 Context engine.** Budgets follow the model's context window. In-run compaction prunes first and summarizes second. Open operations are re-rendered from the database, the model is told when content was omitted, and recent tool evidence carries across runs. Untrusted content leaves the system role.
- **E4 Provider resilience.** An error taxonomy decides between retrying with backoff (honoring Retry-After), falling back to another provider, and benching a failing provider. Truncated output is detected. A transient provider failure makes the run back off and retry later instead of failing.
- **E5 Memory privacy and recall.** Search is scoped to the agent. A `session_search` tool supports discovery, scroll and read. Memory can be edited by entry (add, patch, remove). Skill provenance is labelled truthfully.

**Trading track:**

- **T1** Remove backtesting completely.
- **T2 Execution integrity.** A row that was never sent resolves as not sent. Modify and cancel operations are reconciled against the account's actual state. Blocking is scoped to the affected symbol or ticket, and risk-reducing actions are always admissible. The owner can resolve an operation by recording evidence. Approval batches stop after an unconfirmed result. Verification is re-checked until it settles.
- **T3 Owner restrictions and money limits.** Restrictions have a scope and an expiry, for example "no new positions today", and are enforced at the execution boundary. Monetary limits cover per-trade risk at the stop, daily loss, aggregate open risk and a margin floor.
- **T4 Professional analysis tools.** A multi-timeframe market snapshot, a DST-correct session clock, an economic calendar read tool, and a bridge that writes candles into the analysis workspace. Agents can read related instruments, while execution scope stays separate.

## Wave 2 — durable responsibilities and the always-on gateway

- A `Responsibility` record that owns tasks, wakes, watches, grants, restrictions, communication preference and expiry. It answers "what is active" and "what happened while I was away".
- One wake primitive (at, interval, cron, condition, event) with occurrence identity, overlap policy, grace and catch-up, failure streaks, expiry and a repeat count. It replaces the many scattered time-wake fields. Agents get tools to update, pause, resume and cancel wakes, plus one-shot reminders.
- One continuation primitive: every wait, from any run, resumes its own checkpoint. Routines, watches and goal waits stop spawning fresh-context runs. Legacy tickets and boards are retired.
- An event admission stage with `UNIQUE(source, external_id)`, causation and correlation ids. Producers only admit events, and one dispatcher routes them to responsibilities.
- A real outbox relay with retries, fallback channels and accurate delivery states. Each loop records its own liveness, an LLM-independent watchdog checks it, and failures are isolated per item.
- A first-class task table where each run is an attempt, plus an append-only step log instead of rewriting a full-transcript blob. Financial and authority records are append-only and no longer cascade-deleted. Ephemeral telemetry is separated from domain events, with retention.
- Memory revisions with revert, and a scoped knowledge store (agent-private, shared with named agents, owner-wide) with provenance. A GIN full-text index backs `session_search`.
- A self-improvement loop: a review run, grounded in verified outcomes, proposes versioned memory and skill changes. A curator archives stale skills and never deletes. A single `skill_manage` tool covers create, edit and patch.
- A trade outcome ledger: decision → operation → fills → realized P&L, R-multiple, MAE/MFE.
- Per-agent primary model and fallback chain (needs a schema change). Richer delegation: context handoff, output schema, batches, steer and stop.

## Wave 3 — communication and experience

- Off-app delivery: Expo push and Web Push, with a delivery ledger (intent → provider accepted → device delivered → presented → acknowledged). A `contact_owner` tool for agent-originated communication, under quiet hours and per-responsibility channel preferences.
- Voice that keeps one brain: voice turns are stored as canonical thread messages tagged as voice, with progress streamed into the live session.
- Server-authored activity states: researching, monitoring, awaiting broker confirmation, waiting for the owner, blocked or uncertain. Both clients render them through one shared projection, and the avatar follows them.
- An execution lifecycle card tied to the operation ledger. Mobile gets trading parity: positions, orders, trading on/off and emergency stop. One shared client chat runtime in `@lonora/core`.
- Peer outcomes and other wrapper markup are stored as structured metadata, so internal wrappers never reach the owner.

## Wave 4 — installation, releases and updates

- A CI-gated, versioned release pipeline: an image digest, a release manifest with the migration head and minimum client version, a signed APK and OTA updates.
- A production installer that needs no development toolchain. `lonora update [version]` uses a pinned digest, takes a backup first, runs migrations as a separate step, gates on health and rolls back on failure.
- Complete, encrypted, restore-tested backups. A versioned export and import of all operational state.
- One canonical deployment definition that matches production.

## Acceptance

The end-to-end scenario in the owner addendum §6 is the acceptance test for waves 2–3 combined. It is exercised with the simulation broker and controlled providers, with no live trades and no backtesting. Each wave records what was exercised, what evidence confirms it, and which integrations still need a real device or a configured provider.
