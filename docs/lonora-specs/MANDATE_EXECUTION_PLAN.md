# Lonora mandate execution plan

Status: in progress. Started 2026-11-07. Wave 1 is implemented and integrated on the working branch (see [Wave 1 status](#wave-1-status)); waves 2–4 are not started.

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

## Wave 1 status

Recorded 2026-11-08. Every Wave 1 slice was implemented, reviewed adversarially, fixed after review and then integrated on branch `ccr-9c66a289-3283wb`. That branch has not been merged into `main` yet. GitHub CI is still dark, so everything below was verified locally only. Nothing has run against a real broker account, a real model provider or a real device.

### Integration

The slices were built on two tracks and merged in this order, each with a `--no-ff` merge commit:

1. T1 (`cbf9785`).
2. E1 (`c9aeb4a`).
3. `wave1-trading`: T2, T3 and T4 (`1fb154c`).
4. `wave1-engine`: the E1 review fix and E2–E5 (`fceaea2`).

Points where the two tracks met:

- **Migrations.** Both tracks added a `0034`. `0034_trading_restrictions` keeps that number. The engine migration became `0035_agent_tool_usage`, with `down_revision = 0034_trading_restrictions`, so there is one head. No deployed database had run either migration.
- **Tool metadata.** The new T3/T4 tools got E2 exposure metadata (`6f6233d`):
  - `market_snapshot` and the DST-correct `market_sessions` joined the eager `market` working set. `market_structure` left it: the snapshot reports swing structure with the same rule, and `market_structure` is still one `tool_call` away.
  - `EAGER_SCHEMA_BUDGET` rose from 24,800 to 25,700 and `PROMOTED_SCHEMA_BUDGET` fell from 5,000 to 4,100. The worst-case native tool set stays at 29,800 characters.
  - `economic_calendar_read` is eager for research agents. Its availability check reports `economic_calendar_not_configured` when the owner has no enabled calendar integration.
  - `market_candles_to_workspace` reports `workspace_unconfigured` when there is no workspace access.
  - The restriction tools stay long-tail. The permission frame already shows restrictions and limits on every turn.
  - No new tool is financial.
- **Protected operational state** (`4215dc0`, `218e14f`). This state is re-read from the database every turn. It now follows the T2 lifecycle:
  - `reserved`, `submitted` and `ambiguous` operations, each with a next action and its scoped block. They are read in their own statement, so recently settled rows can never push them out of the limit.
  - For 24 hours after they settle: confirmed operations whose state verification is still pending, and `resolved` operations, marked `broker_confirmed: false`.
  - T3 restrictions and limits are not repeated there, because the permission frame in the same routing frame already shows them.
- **Bridge, planner, approvals and retries** (`ec0cd9f`). New regression tests cover four cases:
  - Bridged trading calls get exactly the direct-call plan. Financial calls and the restriction writer stay serial barriers.
  - A bridged financial call runs alone between overlapping reads.
  - An approved batch proposed through `tool_call` still stops after an uncertain result (`check_execution_recovery` scenario 7).
  - An E4 model outage after an uncertain trade retries the checkpoint and never the trade. A `reserved` journal row keeps a Task outage with the owner.
- **Other fixes.**
  - The T1 legacy-catalog test now excludes `tool_call` (`3341154`).
  - CI step 11's schema-room assertion now uses E3's window-derived limits instead of the fixed 120,000-character bound (`e7480c5`). It had already failed the same way on `wave1-engine` alone.
  - `manifest.json` was regenerated with `scripts/export_agent_tool_reference.py`.
  - The web catalogs were merged by msgid and re-extracted. Arabic has 0 missing translations.

### Delivered per slice

- **T1. Backtesting removed.** Removed the strategy research engine, its two tools, their policy lines and their tests. Legacy calls to the removed tools are refused before any database, broker or file access.
- **T2. Execution integrity.**
  - New `reserved` and `resolved` statuses. A reservation that was never sent resolves as `failed`/`not_sent`, with no broker call.
  - Modify, cancel and full close are concluded from the broker target state after a settle window.
  - An unresolved operation blocks only new risk on its own account and symbol, or its own ticket. Risk-reducing exits stay admissible under Emergency Stop, Trading OFF and degraded recovery.
  - The owner can resolve an operation with an audited attestation (`POST /trading/journal/{id}/resolve`).
  - Approval and authority batches stop after the first result that is not confirmed.
  - Pending verification is re-checked until it settles.
  - The scoped guard also applies to the owner's own execute path.
- **T3. Restrictions and money limits.**
  - Scoped, expiring restrictions (`no_new_entries`, `no_risk_increase`, `all_mutations`). They are enforced under the account send lock at the send boundary, including work already queued or approved.
  - Agent tools `trade_restriction_create` and `trade_restriction_list`, an owner API, and a lift action only the owner can use.
  - Monetary limits: per-trade risk at the stop (an amount or a percentage of equity), daily loss, aggregate open risk, and a free-margin floor.
- **T4. Analysis tools.**
  - `market_snapshot`: one call over several timeframes, using closed bars only.
  - `market_sessions`: a DST-correct Sydney, Tokyo, London and New York clock, plus the broker's trading hours when the adapter reports them.
  - `economic_calendar_read`: failures are reported per source.
  - `market_candles_to_workspace`: writes broker candles into the analysis workspace.
  - Agents bound to one market can read related symbols on their bound account. Execution stays bound to their market.
- **E1. Tool execution core.**
  - Contiguous read-only calls run concurrently in planned segments. Mutating, financial and waiting calls stay serial barriers.
  - Each tool has a dispatch timeout. Financial tools are never wrapped.
  - A checkpointed warn/block/halt guardrail controller limits identical repeated effects, `trade_execute` included.
  - Reaching a limit ends with a final reply instead of a failed run.
  - Runtime nudges are trailing user notices, not system messages.
- **E2. Capability exposure.**
  - Tool metadata: `toolset`, `eager` and `availability`.
  - Eager working sets per profile (`core`, `market`, `research`, `task`), chosen once and frozen in the checkpoint.
  - The stable `tool_call` bridge is resolved before every other boundary.
  - Remembered long-tail tools (migration 0035) and the policy routing map are derived from tool metadata.
- **E3. Context engine.**
  - Budgets come from the model's context window.
  - Admission degrades by shedding optional blocks and inserting an explicit omission notice.
  - In-run compaction prunes old results first, then summarizes with a deterministic fallback. Canonical messages are never rewritten.
  - Protected operational state is rebuilt from the database every turn.
  - Recent tool evidence carries across runs, with untrusted content labelled.
  - Model-authored and untrusted text leaves the system role.
- **E4. Provider resilience.**
  - An error taxonomy that honors Retry-After.
  - Bounded retries, a fallback chain and short provider cooldowns.
  - Truncated output is detected, and incomplete tool calls are never used.
  - Run-level backoff on the same checkpoint, with profiles for conversations, background work and continuous Tasks.
  - A per-agent model preference (API only) and a read-only `consult_model` tool.
- **E5. Memory privacy and recall.**
  - `search_internal` is scoped to the agent's own memory, its threads, its groups and its own decisions. The leak is closed.
  - `session_search` supports discover, scroll, read and browse.
  - `memory_write` takes add, patch and remove batches, with protected headings and an overflow protocol.
  - Skill provenance labels are truthful.
  - `subagent_inspect` is scoped to the agent's own runs.

### Verification on the merged tree

The Python checks, the check scripts, the Task runtime tests and CI steps 10 and 11 were re-run at the final code commit, `218e14f`. The pnpm checks and the Alembic round trip ran at `ec0cd9f`; nothing they cover has changed since. `test:web` ran on the `e7480c5` code and `test:mobile` on `218e14f`. Every step used PostgreSQL 16 with its own fresh database.

| Check | Result |
| --- | --- |
| `ruff check .`, `ruff format --check .`, strict `pyright` | Pass. 0 errors. |
| `validate_resources`, `export_agent_tool_reference.py --check`, `export_native_visual_reference.py --check`, `check_policy_distribution.py` | Pass. |
| `pnpm lint`, `pnpm check` (7 TS packages), `pnpm build` (web and mobile); `pnpm --filter @lonora/web i18n` | Pass. Arabic: 778 of 778 entries translated, 0 missing. `AGENTS.md` unchanged. |
| Alembic: upgrade head, downgrade to `0033_flexible_agent_scope`, upgrade head | Pass. One head, `0035_agent_tool_usage`. |
| `pytest tests` (fresh `lonora_main_test`) | 1777 passed, 5 skipped, 1 failed. The failure is `test_model_context.py::test_real_tool_catalog_fits_default_admission_with_tokenizer`, which is environment-only: its first assertion requires the tiktoken cache, which cannot be downloaded here. It passes under an approximate chars/4 tokenizer (approximate evidence only). |
| All 104 `tests/check_*.py`, each on its own fresh migrated database | 95 pass, with 376 PASS lines and no traceback. The 9 failures are harness or environment cases, not standalone checks: 5 Playwright stdin helpers (`check_chart_browser`, `check_group_ux`, `check_question_browser`, `check_rakazo_ui`, `check_task_browser`), and 4 scripts that need an administrator-reviewed analysis image ID and a Docker daemon, which this container does not run (`check_analytical_workspace`, `check_analytics_profile`, `check_public_skill_package`, `check_workspace_container_runtime`). `check_goals` and `check_chart_visual_observation` pass. |
| `pytest tests/test_task_runtime.py` (`LONORA_TASK_TEST_DATABASE_URL`) | 11 passed. |
| CI step 10 (authenticated durable runtime) | Pass. |
| CI step 11 (persistent context, steering, concurrency) | 22 of 22 checks pass under an approximate tokenizer. Without the tiktoken cache it stops at compaction (`utf8_bytes_fallback_v1`), as it did on the base. |
| CI step 14 (`tsx --test` permission and authority) | 15 passed. |
| Playwright `pnpm test:web` / `pnpm test:mobile` | See below. |

Playwright was driven with the system Chrome (`LONORA_UI_TEST_BROWSER_PATH=/usr/bin/google-chrome`), each suite on its own fresh migrated `*_ci` database:

- **`test:web`: 81 passed, 10 failed.** Every failure also failed in the full web run recorded on 2026-11-07, before Wave 1 (11 failures there), with the same kind of error:
  - `agent-permissions:380`, `avatar:110`, `goals:14`, `group-status:14`, `inbox:120` and `skills-management:121`.
  - `visual-response:64`, in all four locale and theme variants.
  - `attention:4`, which failed on the base, now passes.
- **`test:mobile`: 41 passed, 5 failed.** These are exactly the failures of the run recorded before Wave 1: `attention:4`, `chat-reliability:85`, `skills-management:67` (en and ar) and `workspace:7`.

No Playwright failure is new.

### Known limitations and follow-ups

- **T2.**
  - Execution-quality gates (spread, freshness) still apply to risk-reducing exits under Emergency Stop. Exempting exits, or making that an owner choice, is open.
  - A worker crash between storing halted batch receipts and completing the approval could resume the remaining requests after reconciliation.
  - A Goal step whose operation becomes `resolved` stays blocked until the owner decides.
  - MetaApi modify and cancel rely on the generic target-state comparison. A cancel needs deal history; without it, the cancel stays ambiguous until the owner resolves it.
- **T3.**
  - Web and mobile have no control yet to list or lift restrictions or to edit limits; this is API only.
  - `trading_restriction_active` and the `risk_*` codes have no client text. Clients show the generic "could not be completed" message.
  - Daily loss depends on synchronized broker deal history, and there is no opening-equity baseline.
  - Open risk uses current tick values and ignores gaps, slippage, swap and margin.
  - Restrictions are not yet fed into attention or "what happened" summaries.
  - Live risk usage is checked at the execution boundary, not shown to the agent on every turn.
- **T4.**
  - Session hours ignore holidays and early closes.
  - The broker clock offset is measured at call time.
  - There is no built-in calendar or news provider.
  - The workspace bridge exports one symbol and timeframe, up to 1000 bars, per call.
- **E1.** The web "Open conversation" link of an attention item still opens the agent conversation. The TS attention type does not carry `task_id`/`work_thread_id`.
- **E2.**
  - Not verified with live providers: whether they accept history naming a tool that is not in the request's tool list (this happens after a bridged call).
  - Required tools of active skills are not pre-promoted.
  - The UI tool-phase regex is still a hand-kept list.
  - The financial name lists are constants checked against the registry by tests.
  - Tool usage is recorded per agent, not per thread.
  - Moving `market_structure` to long-tail, and giving the promoted budget 900 characters, are integration choices to revisit with real usage.
- **E3.**
  - Provider context-overflow errors are mapped to compact-and-retry (E4), but there is no usage-anchored trigger.
  - The checkpoint still grows with the full transcript.
  - `wake_context` still puts `run.prompt` in the system role.
  - The family window and output-cap tables must be kept current.
- **E4.**
  - Cooldowns and learned limits are kept per process.
  - The per-agent model preference has no UI, and its settings row is not deleted with the agent.
  - No spend budget is enforced per agent or owner.
  - There are no per-adapter reasoning or thinking controls.
  - A truncated text reply is not continued.
- **E5.**
  - There is no memory revision table, so edits cannot be reverted from the server.
  - Automatic recall covers the current thread only.
  - The owner memory API does not take operation batches.
  - Without an index, `session_search` discovery took about 0.85 s at 50k scoped messages and about 4.3 s at 300k, where it falls back to the 5,000 newest messages. With the documented GIN expression index, selective queries took 10–70 ms. These numbers come from one synthetic bench and depend on hardware. The index itself is a Wave 2 migration.
- **Verification.**
  - The tokenizer-dependent checks need `scripts/cache_model_tokenizers.py`, which cannot run here.
  - The 9 harness and image checks need Playwright and Docker with the analysis image.
  - The full `run_foundation_checks.py --isolated-databases` and CI as a whole must run again once runner capacity is back.

### Needs a real broker, provider or device

- **MetaApi.** These were only exercised against the simulation broker or SDK-shaped fixtures:
  - Cancel and modify reconciliation through live deal history.
  - The `historyOrders` fallback.
  - The trade-session time format and `brokerTime` offset behind `market_sessions`.
  - The deal `type` values used to exclude cash flows from daily loss.
  - The `state` field handling fixed in T2.
- **Model providers.** Live verification is still needed for:
  - Retry-After and 429/529 handling.
  - Classification of permission errors versus model-specific 403 responses.
  - Stream truncation.
  - Bridged-call history acceptance.
  - `consult_model` against a second configured provider.
  - Real context windows against the family tables.
- **Devices and clients.** Verification is still needed for:
  - Web and Expo rendering of the new journal states and restriction codes.
  - Push or off-app delivery, which arrives in Wave 3.

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
