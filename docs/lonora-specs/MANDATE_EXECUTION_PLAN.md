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
| One failing scheduler step halts all maintenance, including broker reconciliation | `gateway/service.py` maintenance loop | 1.5 (W15-0) |
| Financial and authority records are hard-deleted by FK cascades from ordinary deletes | `db/schema.py` | 1.5 (W15-0) |
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
- **T2 Execution integrity.** A row that was never sent resolves as not sent. Modify and cancel operations are reconciled against the account's actual state. Blocking is scoped to the affected symbol or ticket, and risk-reducing actions are always admissible. The owner can resolve an operation by recording evidence. Dependent approval batches stop after an unconfirmed result, while the closes of an approved close-all are independent exits. Verification is re-checked until it settles.
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
  - An approved close-all proposed through `tool_call` is handled exactly like a direct call (`check_execution_recovery` scenario 7). After review, an uncertain close no longer holds back the other closes.
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
  - Dependent approval and authority batches stop after the first result that is not confirmed. After review, a close-all made only of full closes of distinct positions sends every close (`1dfb611`).
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

### Review of the integrated branch (2026-11-08)

Four reviewers (financial, engine, security, mandate) reviewed the integrated branch at `7da46c0`. Every finding was checked against the code, and the critical and high ones were reproduced before they were fixed. Each fix has a regression test.

- **Financial.**
  - Fixed (high): an approved close-all stopped at the first close that was not confirmed, which left the other approved exits open. A batch made only of full closes of distinct positions is now independent on both the approval path and the standing-authority path (`1dfb611`). Dependent sequences still stop.
  - Fixed in part (medium): cancelling a *protective* order now counts as new risk at admission (`c9c77b0`). A protective order is an opposite-side order whose fill would offset open positions. Closing a hedge leg stays an exit, as VISION requires; the docs and owner texts now say so.
  - Fixed (low): a restriction's start and its in-force check now both use the database clock (`cfda73c`).
- **Engine.**
  - Fixed (high): a Run that stops at a work limit is projected as `limited`, never as completed work (`6b01b19`). A ticket moves to `waiting`, a peer gets `status='limited'`, a collaboration participant is recorded as failed, and a limited synthesis never completes.
  - Fixed (high): every owner-attention escalation gets a unique question id, so a resumed Task whose model outage escalates again no longer fails (`7420a1d`).
  - Fixed (medium, pre-existing): steering or a limit after a restart now reports an interrupted mutation as `tool_execution_uncertain` with an ambiguous route, never as superseded (`8ab4024`).
  - Fixed (low): reconciling an ambiguous trade is no longer counted as a repeated effect (`52b18d0`). Exhausted read routes now expire with a new review epoch (`215ece3`). The final-report notice is added only once across a restart (`d87e476`).
- **Security.**
  - Fixed (high): a reason written by an agent never enters another Agent's system-role permission frame, and the frame shows truthfully who recorded each restriction (`df704bf`).
  - Fixed in part (medium): a restriction recorded by an agent never blocks a risk-reducing exit, including an exit the owner approved. Restrictions an agent records for other agents need a `valid_until` at most 31 days ahead (`df704bf`). An owner attention item and a Lift control are listed under Wave 2 and Wave 3.
  - Fixed (low): compaction labels speakers truthfully and escapes tool names (`87bec51`); calendar, consulted-model and delegated-agent results are labelled untrusted evidence (`337e00e`); the `consult_model` budget counts usage records (`56d962c`); calendar responses are streamed under a 2 MiB cap (`6652c1e`); a prompt written by a model or a person no longer enters the system role through `wake_context` (`cf72884`).
- **Mandate.**
  - Fixed (medium): broker-state resolutions show basis-specific labels on Web and Mobile, and boundary codes have owner text in Arabic and English. Both come from `@lonora/core` and are covered by `tests/web/financial-boundary.test.ts` (`2dcc111`).
  - Fixed (low): a failed account observation now raises `broker_observation_unavailable` instead of blaming a previous operation (`e49d6da`).
  - Fixed (low): `docs/context-engine.md` now matches the code (`cf72884`).
  - The gap findings are planned for future waves and are listed under Waves 2–4 below.

### Verification after the review fixes

These checks were re-run at `eb76b7d`, and every step used PostgreSQL 16 with its own fresh database. The container now has a tiktoken cache in `/tmp/data-gym-cache`. Both encodings match the upstream SHA-256 values, so the tokenizer-dependent tests ran with the real tokenizer for the first time.

| Check | Result |
| --- | --- |
| `ruff check .`, `ruff format --check .`, strict `pyright` | Pass. 0 errors. |
| `validate_resources`, `export_agent_tool_reference.py --check`, `export_native_visual_reference.py --check`, `check_policy_distribution.py` | Pass. |
| `pnpm lint`, `pnpm check` (7 TS packages), `pnpm build`; `pnpm --filter @lonora/web i18n` | Pass. Arabic: 782 of 782 entries translated, 0 missing. `AGENTS.md` unchanged. |
| Alembic: upgrade head, downgrade to `0033_flexible_agent_scope`, upgrade head | Pass. One head, `0035_agent_tool_usage`. |
| `pytest tests` (fresh `lonora_main_test`) | 1802 passed, 5 skipped, 0 failed. Both tokenizer tests in `test_model_context.py` pass with the real cache. |
| All 104 `tests/check_*.py`, each on its own fresh migrated database | 95 pass, with 379 PASS lines. The same 9 harness and environment cases fail as before. Five are Playwright stdin helpers: `check_chart_browser`, `check_group_ux`, `check_question_browser`, `check_rakazo_ui` and `check_task_browser`. Four need an administrator-reviewed analysis image ID and a Docker daemon, and the Docker socket is absent here: `check_analytical_workspace`, `check_analytics_profile`, `check_public_skill_package` and `check_workspace_container_runtime`. `check_goals` passes. |
| `pytest tests/test_task_runtime.py` (`LONORA_TASK_TEST_DATABASE_URL`) | 11 passed. |
| `tsx --test`: web, including the new `financial-boundary.test.ts`, and mobile | 18 and 25 passed. |
| CI "authenticated durable runtime" step | Pass. |
| CI "persistent context, steering and concurrency" step, re-extracted from `ci.yml` | 22 of 22 pass with the real tokenizer, after the stale assertion fix in `eb76b7d`. |
| Playwright `pnpm test:web` / `pnpm test:mobile` (system Chrome, each suite on its own fresh `*_ci` database) | Web: 82 passed, 9 failed. Mobile: 41 passed, 5 failed. No failure is new; see below. |

The "persistent context, steering and concurrency" step needs a note:

- Before `eb76b7d`, this step failed at check 20 on `7da46c0` and on this branch alike, with the real tokenizer and with an approximate chars/4 tokenizer. The check expected the reads to start in call order, but E1 runs reads concurrently. It also compared the request with the fixed 120,000-character bound, but E3 budgets by the resolved window.
- In the failing case the request was about 41k of 64k input tokens and within the 384,000-character transport bound.
- An earlier local extraction of this step predated `e7480c5`, so the step was re-extracted from `ci.yml` before it was run.

Playwright, compared with the integration run on the same suites:

- **Web.** The 9 failures are among the 10 recorded at integration: `agent-permissions:380`, `goals:14`, `group-status:14`, `inbox:120`, `skills-management:121`, and `visual-response:64` in all four locale and theme variants. `avatar:110`, which failed then, now passes. `streaming:127`, which renders peer requests and their returned results, passes.
- **Mobile.** The 5 failures are the same as before: `attention:4`, `chat-reliability:85`, `skills-management:67` (en and ar) and `workspace:7`.

### Known limitations and follow-ups

- **T2.**
  - Execution-quality gates (spread, freshness) still apply to risk-reducing exits under Emergency Stop. Exempting exits, or making that an owner choice, is open.
  - A worker crash between storing halted batch receipts and completing the approval could resume the remaining requests after reconciliation. This applies only to dependent sequences, and no caller submits one today: an approved close-all is a batch of independent exits.
  - A Goal step whose operation becomes `resolved` stays blocked until the owner decides.
  - MetaApi modify and cancel rely on the generic target-state comparison. A cancel needs deal history; without it, the cancel stays ambiguous until the owner resolves it.
- **T3.**
  - Web and mobile have no control yet to list or lift restrictions or to edit limits; this is API only.
  - A restriction an agent records raises no owner attention item yet. It cannot trap an exit, and a restriction on other agents is time-boxed to 31 days.
  - Closing one leg of a hedged book stays an exit under Emergency Stop and `no_risk_increase`, even though it changes net direction. This is a deliberate rule, documented in the admission module and in the owner texts.
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
  - Goal detail records (an agent's objective and step text) remain a system-role block. They are JSON-escaped and labelled untrusted. The run prompt itself now reaches the system role only for server-authored wakes.
  - The family window and output-cap tables must be kept current.
- **E4.**
  - Cooldowns and learned limits are kept per process.
  - The per-agent model preference has no UI, and its settings row is not deleted with the agent.
  - No spend budget is enforced per agent or owner. Correction D4 keeps it that way (no cap); Wave 2 adds a usage view per agent instead.
  - There are no per-adapter reasoning or thinking controls.
  - A truncated text reply is not continued.
- **E5.**
  - There is no memory revision table, so edits cannot be reverted from the server.
  - Automatic recall covers the current thread only.
  - The owner memory API does not take operation batches.
  - Without an index, `session_search` discovery took about 0.85 s at 50k scoped messages and about 4.3 s at 300k, where it falls back to the 5,000 newest messages. With the documented GIN expression index, selective queries took 10–70 ms. These numbers come from one synthetic bench and depend on hardware. The index itself is a Wave 2 migration.
- **Verification.**
  - The tokenizer-dependent checks need the tiktoken cache that `scripts/cache_model_tokenizers.py` writes. A hash-verified cache was present for the post-review run; CI must provide it too.
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

## Wave 1.5 — simplicity and access

The owner asked, on 2026-11-08, for a simple experience without contradictions and an agent with access to everything. The design is in `VISION.md`, and the binding amendments are in `MANDATE_CORRECTIONS.md`. Wave 1.5 builds on Wave 1. It adds no new engine and no second authority path, and every widening still goes through the passkey and the single executor. Several gaps from the Wave 1 review that are listed under Wave 2 below move into this wave.

1. **W15-0 Reliability first** (correction 13, owner "failure-free").
   - Each gateway maintenance step runs in its own supervised task with per-item fault isolation and its own liveness record. One bad routine, watch or attention event can no longer halt broker reconciliation.
   - A minimal LLM-independent watchdog detects stalled loops, runs recovered too many times and aging unresolved operations, and raises owner attention.
   - Financial and authority records (journal, approvals, grants, restrictions, decisions) are no longer cascade-deleted by ordinary deletes.
   - Delivered on branch `w15-a1` (migrations `0036_durable_records` and `0037_gateway_reliability`); the design is in `docs/gateway-reliability.md`.
   - Review fixes: a delete settles the grants, Super Bot requests and goals of the deleted conversation or agent instead of leaving them active but unusable; every maintenance item has its own time limit and the attention cursor advances per event; watchdog items open the originating agent; failed worker polls no longer count as liveness; ended "running late" items are withdrawn after a restart; quarantine notices coalesce per kind and never cost a critical alert. Deferred: an owner-recoverable failure for a quarantined Task wait or outcome return (they stay in the ledger quarantine, with the owner notice).
2. **W15-1 Safety truth and one brake.**
   - A one-line trading readiness for every agent, shown in the permission frame and in a header safety pill on web and mobile.
   - One "Stop new trading / Resume" control.
   - Owner close and cancel buttons keep one operation id until the outcome settles.
   - Owner text in Arabic and English for every boundary code.
   - Delivered on branch `w15-a1` (no migration); the design is in `docs/trading-safety.md`. The readiness block is presentation only and never read by enforcement. Stop sends the former Emergency Stop flag and Resume clears both flags in one call; the API contract is unchanged. Grant summaries now report the account's money limits instead of `monetary_stop_risk: "unavailable"`. Restrictions are listed read-only in the safety sheet; lifting from a card is W15-2.
   - Review fixes: a held close or cancel identity is released as soon as its journal row settles (confirmed, failed or resolved), so a position the owner attested as not closed can be closed again; the stopped line says exits are frozen too while a freeze is in force; the line counts only pauses and uncertain operations on the accounts the agent acts on and names the account when there are several; both sheets name the agent that set a pause and offer Start trading before the first start; Mobile reads the agent's live state once per refresh for the pill and the activity strip.
3. **W15-2 Owner action cards in chat.**
   - Durable, server-validated, single-use cards for resuming trading, lifting a pause, resolving an uncertain operation and setting money limits. Later slices add grants, agent creation, supervision, trusted sources and credentials.
   - Widening needs the passkey. Narrowing is one tap.
   - Delivered on branch `w15-a1` (migration `0038_owner_actions`; the W15-0 head was `0037_gateway_reliability`); the design is in `docs/owner-actions.md`. Agents propose cards with `owner_action_propose`; the gateway raises Lift and resolve cards from restriction and uncertain-operation events, and an uncertain operation is the owner's `operation_uncertain` item. The owner's decision route re-validates, is idempotent and runs the existing owner functions; raising or removing a money limit needs a passkey assertion bound to the card. The resolve statement is now optional. The header safety sheet lifts a pause in one tap on Web and Mobile. The raw execution-policy route still accepts any change from an owner session (follow-up). Review fixes: a limits card shows every field it changes (currency and trading day too), the confirmation line says what still holds new risk (Stop, other pauses, another uncertain trade), "Unknown" says it releases the hold, agents propose Resume or Lift only when the owner asks, deletes supersede their cards, and an uncertain trade alerts the owner once.
4. **W15-3 One-sentence delegation and a monotonic ladder** (corrections 5–7, D1).
   - No trading / Ask me / On its own.
   - Grant cards are built from a stored draft and include the D1 defaults: a daily-loss limit suggested at 3% of equity, and the owner's manual positions excluded.
   - Under *On its own*, an out-of-grant trade becomes an approval card.
   - The Personal Assistant defaults to *Ask me*.
   - Delivered on branch `w15-a2` (migration `0040_explicit_agent_permission_rows`, after `0039_owner_profile_memory_revisions`; the slice text named it `0039`, which the profile migration already holds); the design is in `docs/owner-actions.md` and `docs/account-authority.md`. The `grant_authority` card is a server-resolved draft (the only or focus account, the focus pair or all pairs for Lonora, every action, until stopped, the owner's own positions excluded, the owner's daily loss or a suggested 3% of equity); its challenge builds the composer-identical full-management envelope with the existing `propose` and `begin_activation`, and its confirmation is `finish_activation` plus the card's narrowing choices (the daily loss limit, stopping another agent's overlapping grant) and Resume. A card is raised only when no active grant covers the draft. Under *On its own* an uncovered trade, the owner's own position under a grant that excludes it included, becomes an approval card, reused within the Run once approved; moving down still revokes and now says so. Lonora and root trading agents start at *Ask me*, every other new agent at *No trading*, and existing agents keep an explicit level. Widening money limits through `PUT /trading/accounts/{id}/execution-policy` now needs the passkey (`/challenge`, `/verify`), closing the W15-2 follow-up. A live Goal step outside the grant now asks too (W15-9). Review fixes: the card suggests 3% only where the account has no daily loss limit and lowers the owner's own limit only to an amount the owner asked for (one line, "500 → 300", with "Keep my current limit"), and says when a higher amount needs a limits card; the grant it replaces is described in full (caps, protections, markets, expiry); stopping another agent says it ends that agent's grant on the account; the Arabic opt-out reads as a deliberate choice; lists use the comma of the language; the owner's own positions are stated once; and a repeated trade request waits on its pending card or returns the owner's rejection until the owner writes again.
5. **W15-4 Create and steer agents from chat** (corrections 17, 23, 24).
   - An `agent_create` tool with templates.
   - Watch cancel, pause and update tools.
   - A real status line in place of "Waiting".
6. **W15-5 One owner profile, revertible memory** (corrections 18, 19).
   - A shared owner profile with attributed revisions and revert.
   - Self-edited operating notes.
   - Reach-me preferences settable from chat.
   - Delivered on branch `w15-b1` (migration `0038_owner_profile_memory_revisions` there, renumbered `0039_owner_profile_memory_revisions` at integration); the design is in `docs/agent-memory-and-recall.md` and `docs/incoming-attention.md`. One owner profile (`ln_owner_profile`) is the single USER.md every agent reads as an owner-attributed `owner_preferences` context section; `memory_write` on USER.md changes it only from a Run that answers the owner's message. `OPERATING.md` holds each agent's own working method. `ln_memory_revisions` records every commit of the profile, the preferences and each agent's memory with its author, and the owner can undo one change. Reach-me (activity, notify, message, call) and the reply language are set from chat with `owner_preferences_update`. Writes that add an authority statement to the profile or the operating notes are refused. Review fixes: locked re-reads are fresh so concurrent writers keep both changes, undo takes back exactly one change, an agent's write keeps its retired USER.md lines, each form keeps its unsaved edits, and reach-me validator codes have shared owner text.
7. **W15-6 Lonora sees everything** (corrections 1, 3, 15). Supervision grants, with the Personal Assistant supervising every agent by default (visible and revocable), and `agent_inspect` and `agent_control` tools. Peers stay private from each other.
8. **W15-7 Proactive wakes that can act; reading without walls** (correction 25).
   - Observe-only means no financial effects.
   - Broker events wake the agent that owns the position.
   - Every agent reads every owned account.
   - An `owner_notify` tool.
   - Delivered on branch `w15-b1` (no migration); the design is in `docs/proactive-wakes.md`. One tool scope per Run (`full`, `observe_only`, `helper`) drives exposure, discovery, skills and execution: observe-only wakes keep every non-financial tool, helpers keep reads plus workspace computation and reports, and a financial tool outside a full Run fails `observe_only_execution_forbidden` before any work. Reconciliation attributes an external broker change to the agent whose journaled operation opened or last managed the ticket and wakes that agent once, with its normal authority, reporting to its conversation; the owner's own activity, and activity of a paused or missing agent, wakes the Personal Agent observe-only. Opportunity wakes carry normal authority. Read-only tools are open across every owned account and symbol, and mutations keep the binding. `owner_notify` raises an owner attention item under dedupe, an hourly rate, quiet hours and reach-me. Review fixes: Tasks and tickets started from an observe-only wake inherit the narrowing, work-lane wakes read the Goals of their conversation, fixed-market reads of another account come back whole, and an identical Goal watch is deduplicated.
9. **W15-8 Capabilities you can see** (corrections 21, 22, D3).
   - One trusted-sources list. Trusted MCP servers are usable without environment declarations.
   - RSS/news feeds.
   - Secure credential cards.
   - A Capabilities view.
10. **W15-9 One vocabulary.**
    - Retire Super Bot and per-goal autonomy.
    - Rename Emergency Stop to "Stop new trading".
    - No raw ids or JSON in normal views.
    - The same labels on web and mobile.
    - Delivered on branch `w15-a2` (migration `0040_retire_super_bot_requests`, after `0040_explicit_agent_permission_rows`; the slice text named it `0041`, the orchestration `0040_retire_super_bot_requests`); the design is in `docs/owner-vocabulary.md`, `docs/trading-goals.md` and `docs/account-authority.md`. The three Super Bot tools, its routes and its cards on Web and Mobile are removed; pending and activated requests are marked `retired` and kept. A goal is a plan under the agent's level and grant: no autonomy switch or limit knobs, a live step outside the grant becomes an approval card (closing the W15-3 limitation), and a Shadow step needs no approval. The readiness review runs once for a newly signed bounded grant (full grants start their management Task), and a grant signed from the trading-level controls writes one confirmation line. The composer shows the trading level only for an agent that can trade, others show "No trading". Activity rows read from the tool's toolset and effect, which `tool.started` now carries; ids and JSON sit behind "Technical details"; the peer-outcome wrapper is stripped; operation and approval labels come from one `@lonora/core` table; the error copy says the outcome; Mobile says "agent". The model-facing policy (core 14,698 of 16,000 characters, goals chapter 2,927), constitution, prompts and bundled skills no longer name Super Bot or Emergency Stop.
11. **W15-10 Choose a model from chat** (D4): a per-agent model card, an agent-requested switch within the allowed list, and a usage view per agent. No spend cap.
12. **W15-ACC Acceptance.** Scripted Arabic owner journeys check the confirmation counts in `VISION.md`, using the simulation broker and a scripted provider, plus the full local verification list.

Moved to Wave 2: the optional signed emergency reduction rule (D2), together with the Responsibility record, the wake primitive and the full watchdog.

### Wave 1.5 phase 1 status

Recorded 2026-11-08. Phase 1 delivered W15-0, W15-1 and W15-2 on track A (`w15-a1`) and W15-5 and W15-7 on track B (`w15-b1`). Each slice was implemented, reviewed adversarially and fixed after review on its own branch. The tracks were then merged into `ccr-9c66a289-3283wb` with `--no-ff` merge commits, track A first (`ecb3b1e`, no conflicts), then track B (`6ea283f`). The branch is not merged into `main` yet. GitHub CI is still dark, so everything was verified locally only, and nothing ran against a real broker account, a real model provider or a real device.

Points where the tracks met:

- **Migrations.** Both tracks added a `0038`. `0038_owner_actions` keeps it. The profile migration becomes `0039_owner_profile_memory_revisions`, with `down_revision = 0038_owner_actions`, so there is one head; its check now downgrades to its own predecessor. No deployed database has run any of them. Track B's `migrations/env.py` widens the Alembic version column to 128 characters, which these long revision ids need.
- **Attention.** The codes are the union of track A's `maintenance_item_quarantined`, `run_quarantined`, `operation_unresolved`, `operation_uncertain` and `gateway_degraded` and track B's `agent_notification`, with Arabic and English labels on Web and Mobile. The gateway keeps track A's per-item `ItemGuard` loop and readies items through track B's shared `publish_ready`.
- **Tools and scopes.** The three new tools, `owner_action_propose`, `owner_notify` and `owner_preferences_update`, are long-tail, so the eager and promoted schema budgets are unchanged (25,700 and 4,100). None is financial: observe-only wakes keep them, and helpers do not.
- **Policy and texts.** `manifest.json` was regenerated from the merged `lonora.md`. The trading chapter is 4,649 and the memory chapter 4,655 characters of their 4,666 budget, and the core is 14,877 of 16,000. The web catalogs were merged by msgid and re-extracted: 795 messages, 0 missing Arabic. Web and Mobile error text looks up the owner-action table, then the owner-profile table; the two code sets do not overlap.

Per slice:

- **W15-0 Reliability first.**
  - Delivered: supervised gateway steps with per-item isolation and liveness, a model-free watchdog, run recovery quarantine, `/ready` from real liveness, and durable financial and authority records with guarded deletes.
  - Verified: `tests/test_gateway_reliability.py` (23 tests) and `check_durable_records` (migration round trip, the three delete routes, `/ready`), together with the merged-tree runs below.
  - Limitations:
    - A quarantined Task wait or outcome return has no owner-recoverable failure yet.
    - After five whole-process crashes in a row, runs that were running alongside the crashing one are quarantined too.
    - A run held over an uncertain operation keeps its stale status until the operation settles.
    - The watchdog runs inside the gateway, with no external healthcheck.
- **W15-1 Safety truth and one brake.**
  - Delivered: a presentation-only readiness block, `global_trading` in the permission frame, one Stop new trading / Resume control, the header safety pill on Web and Mobile, held operation ids for the owner's close and cancel, and owner text for every boundary code.
  - Verified: `tests/test_trading_readiness.py`, `tests/web/trading-readiness.test.ts`, `tests/web/held-operation.test.ts`, Playwright `safety-truth` (web) and `safety-pill` (mobile, Arabic and English).
  - Limitations: the model-facing policy still says "Emergency Stop" in a few places, which W15-9 renames.
- **W15-2 Owner action cards in chat.**
  - Delivered: durable, single-use cards for resume, lift, resolve and money limits; the `owner_action_propose` tool; cards raised by the gateway; and a passkey bound to the card for any widening.
  - Verified: `tests/test_owner_actions.py`, `check_owner_actions`, `tests/web/owner-actions.test.ts`, Playwright `owner-actions` (web and mobile).
  - Limitations:
    - The raw `PUT /trading/accounts/{id}/execution-policy` route still accepts a widening from an owner session without a passkey. No client calls it.
    - Grant, agent-creation, supervision, trusted-source and credential cards come in later slices.
- **W15-5 One owner profile, revertible memory.**
  - Delivered: the shared owner profile, attributed revisions with per-change undo, operating notes, and reach-me and reply language set from chat.
  - Verified: `tests/test_owner_profile.py`, including the PostgreSQL race tests; `check_owner_profile` (lossless, idempotent upgrade, an agent's write, downgrade and re-upgrade); `tests/web/owner-profile.test.ts`; Playwright `owner-profile` (web) and `reach-me` (mobile).
  - Limitations:
    - Delivery is in the app only until Wave 3.
    - Mobile edits only reach-me and the reply language; the profile text and its history are on the Web.
    - The "Notify me" hint still describes the time before `owner_notify` (agents write in the conversation, Lonora's alerts reach the inbox). It should now also say that agents can raise inbox alerts themselves; to be corrected in phase 2.
- **W15-7 Proactive wakes that can act; reading without walls.**
  - Delivered: run scopes (full, observe-only, helper), broker events that wake the attributed agent with its normal authority, opportunity wakes with normal authority, open reads across owned accounts, and `owner_notify`.
  - Verified: `tests/test_proactive_wakes.py`, the updated binding, decision, opportunity and recovery checks, `tests/mobile/text-direction.test.ts`, Playwright `agent-alert` (web and mobile).
  - Limitations:
    - Attribution reads the newest 1,000 journal rows of the account.
    - A paused agent's activity wakes the Personal Agent, and the paused agent is not woken when it resumes.
    - Agent alerts reach the owner in the app only until Wave 3.
    - The Personal Agent cannot yet read other agents' work; that is W15-6.

Verification on the merged tree (`6ea283f`), each database step on its own fresh PostgreSQL 16 database:

| Check | Result |
| --- | --- |
| `ruff check .`, `ruff format --check .`, strict `pyright` | Pass. 0 errors. |
| `validate_resources`, `export_agent_tool_reference.py --check`, `export_native_visual_reference.py --check`, `check_policy_distribution.py` | Pass. |
| `pnpm lint`, `pnpm check` (7 TS packages), `pnpm build`; `pnpm --filter @lonora/web i18n` | Pass. Arabic: 795 of 795 translated. `AGENTS.md` unchanged. |
| `tsx --test` web and mobile | 153 and 55 passed. |
| Alembic: upgrade head, downgrade to `0035_agent_tool_usage`, upgrade head | Pass. One head, `0039_owner_profile_memory_revisions`. |
| `pytest tests` (fresh `lonora_main_test`) | 1927 passed, 5 skipped (APK), 0 failed. The baseline was 1802. |
| All 108 `tests/check_*.py` | 99 pass, with 397 PASS lines. The 9 failures are the known harness and environment cases. Five are Playwright stdin helpers when run alone: `check_chart_browser`, `check_group_ux`, `check_question_browser`, `check_rakazo_ui` and `check_task_browser`. Four need an administrator-reviewed analysis image and a Docker daemon: `check_analytical_workspace`, `check_analytics_profile`, `check_public_skill_package` and `check_workspace_container_runtime`. New and passing: `check_durable_records`, `check_owner_actions`, `check_owner_profile` and `check_agent_alert_browser`. |
| `pytest tests/test_task_runtime.py` (`LONORA_TASK_TEST_DATABASE_URL`) | 11 passed. |
| CI "authenticated durable runtime" and "persistent context, steering and concurrency" steps, re-extracted from `ci.yml` and run in order on one database, as in CI | Pass. 22 of 22 with the real tokenizer. |
| Playwright `test:web` / `test:mobile` (system Chrome, each suite on its own fresh `*_ci` database) | Web: 96 passed, 10 failed. Nine are the baseline failures: `agent-permissions:380`, `goals:14`, `group-status:14`, `inbox:120`, `skills-management:121` and `visual-response:64` in all four locale and theme variants. The tenth, `avatar:110`, is the known reduced-motion timing flake; the integration changed no avatar code, and it passed when rerun alone on a fresh database. Mobile: 48 passed, 5 failed, exactly the baseline: `attention:4`, `chat-reliability:85`, `skills-management:67` (en and ar) and `workspace:7`. The new specs pass, among them `attention`, `safety-truth`, `owner-actions`, `owner-profile` and `agent-alert` on Web and `safety-pill`, `owner-actions`, `reach-me` and `agent-alert` on Mobile. No failure is new. |

## Wave 2 — durable responsibilities and the always-on gateway

- A `Responsibility` record that owns tasks, wakes, watches, grants, restrictions, communication preference and expiry. It answers "what is active" and "what happened while I was away".
- One wake primitive (at, interval, cron, condition, event) with occurrence identity, overlap policy, grace and catch-up, failure streaks, expiry and a repeat count. It replaces the many scattered time-wake fields. Agents get tools to update, pause, resume and cancel wakes, plus one-shot reminders.
- One continuation primitive: every wait, from any run, resumes its own checkpoint. Routines, watches and goal waits stop spawning fresh-context runs. Legacy tickets and boards are retired.
- An event admission stage with `UNIQUE(source, external_id)`, causation and correlation ids. Producers only admit events, and one dispatcher routes them to responsibilities.
- A real outbox relay with retries, fallback channels and accurate delivery states. Each loop records its own liveness, an LLM-independent watchdog checks it, and failures are isolated per item.
- A first-class task table where each run is an attempt, plus an append-only step log instead of rewriting a full-transcript blob. Financial and authority records are append-only and no longer cascade-deleted. Ephemeral telemetry is separated from domain events, with retention.
- Memory revisions with revert, and a scoped knowledge store (agent-private, shared with named agents, owner-wide) with provenance. A GIN full-text index backs `session_search`.
- A self-improvement loop: a review run, grounded in verified outcomes, makes versioned and revertible memory and skill changes, which the agent activates itself (correction 11). A curator archives stale skills and never deletes them. A single `skill_manage` tool covers create, edit and patch.
- A trade outcome ledger: decision → operation → fills → realized P&L, R-multiple, MAE/MFE.
- Per-agent primary model and fallback chain (needs a schema change). Richer delegation: context handoff, output schema, batches, steer and stop.

Gaps from the review of the integrated Wave 1 branch. They are planned here and were not implemented in Wave 1:

- **First slice: fault isolation and durable financial records** (section 26, correction 8).
  - Isolate every maintenance step and give it a liveness record, so one failing step no longer halts all maintenance, broker reconciliation included.
  - Add a watchdog that does not depend on an LLM. It watches for missed wakes, stalled runs, a lost broker connection, ambiguous operations that keep aging, and risk-limit breaches.
  - Protect `ln_trading_journal`, restrictions, approvals and authority rows from ordinary deletes with `ON DELETE RESTRICT` or soft delete, and add a migration test. T2 and T3 depend on their evidence and attestations.
- **Re-baseline on the owner's 2026-11-08 corrections.**
  - Done: `docs/lonora-specs/MANDATE_CORRECTIONS.md` (D1–D4, corrections 1–31) and the rewritten root `VISION.md` are committed.
  - Re-check every Wave 2–4 item against each correction. Drop the spend-cap follow-up (D4) in favour of a usage view per agent.
- **One ladder per agent: No trading / Ask me / On its own** (corrections 5–7).
  - When the signed grant does not cover a trade from an autonomous agent, create the existing approval card with the same operation id, instead of refusing with `account_authority_scope_mismatch`.
  - Move Super Bot and per-goal autonomy onto AccountAuthority plus the ladder, then retire them.
  - Rename Emergency Stop to "Stop new trading" / "Resume" in the UI, `lonora.md` and the attention messages. Exits stay admissible, as T2 already does.
- **Money limits are money authority** (correction 21, D1).
  - Compare the previous and new risk policy in `PUT /trading/accounts/{id}/execution-policy`.
  - Accept narrowing silently, with Undo. Require the existing passkey device challenge for any widening: a limit raised or removed, or a changed currency or time zone.
  - Show a daily-loss limit on the default grant card, suggested at 3% of equity.
- **Restrictions recorded by agents.**
  - Raise an owner attention item when an agent records a restriction for other agents, with a one-tap Lift.
  - Consider owner confirmation for restrictions that affect other agents. Today they are time-boxed and can never block an exit.
- **Readable scope and supervision** (corrections 1, 3, 4).
  - Every agent can read all owner-connected accounts and pairs; it can execute only within its signed grant. `account_history` and `account_activity` stop filtering by the bound symbol.
  - Add a supervision grant table (supervisor, supervised, created_by, revoked_at). The Personal Assistant's default grant is visible and revocable in the UI.
  - `session_search`, `subagent_inspect` and memory reads honour the supervision grant. Since E5, the PA cannot inspect other agents' work at all.
- **One owner profile** (correction 18).
  - Add an `owner_profile` record: versioned, attributed (author and run) and revertible. Every agent reads it as first-party owner instructions.
  - Migrate the `USER.md` sections of each agent's memory into it, with provenance. This goes with the memory revision table above.
- **Wake runs act without financial effects** (correction 25).
  - Split the loop's `read_only` flag into `no_financial_effects` (observe-only wakes) and `read_only` (subagents).
  - Expose non-financial mutating tools to wake runs: memory writes, watch and routine changes, peer messages, owner notifications and artifacts.
- **Context and admission follow-ups found in review.**
  - Move goal detail records from the system role into the user-role context data.
  - Report a non-connected account observation in decision readiness as `broker_observation_unavailable`, as the executor now does.
  - If a live provider rejects history that names a tool missing from the request (after a bridged call), send bridged calls on the wire as `tool_call` wrappers and keep the real name internally. See Wave 4 for the contract test.

## Wave 3 — communication and experience

- Off-app delivery: Expo push and Web Push, with a delivery ledger (intent → provider accepted → device delivered → presented → acknowledged). A `contact_owner` tool for agent-originated communication, under quiet hours and per-responsibility channel preferences.
- Voice that keeps one brain: voice turns are stored as canonical thread messages tagged as voice, with progress streamed into the live session.
- Server-authored activity states: researching, monitoring, awaiting broker confirmation, waiting for the owner, blocked or uncertain. Both clients render them through one shared projection, and the avatar follows them.
- An execution lifecycle card tied to the operation ledger. Mobile gets trading parity: positions, orders, trading on/off and emergency stop. One shared client chat runtime in `@lonora/core`.
- Peer outcomes and other wrapper markup are stored as structured metadata, so internal wrappers never reach the owner.
- **Owner controls for T2 and T3 in chat and on Mobile** (section 26, corrections 2, 12, 21(4), 26).
  - Today restrictions, money limits and risk status are API only. Operation resolve is a form on the Web Trading page only, and Mobile cannot clear an ambiguous block.
  - Add shared `@lonora/core` projections and chat cards, rendered the same way on Web and Mobile:
    - "It executed / it did not / still unknown".
    - "Lift pause".
    - A limits editor that asks for the passkey only when a limit is widened.
    - A status line built from risk status.
  - Feed `trading.restriction_*` and `operation_resolved` into attention and into the "what happened" builder.
  - The owner-notify tool is the `contact_owner` tool above.

## Wave 4 — installation, releases and updates

- A CI-gated, versioned release pipeline: an image digest, a release manifest with the migration head and minimum client version, a signed APK and OTA updates.
- A production installer that needs no development toolchain. `lonora update [version]` uses a pinned digest, takes a backup first, runs migrations as a separate step, gates on health and rolls back on failure.
- Complete, encrypted, restore-tested backups. A versioned export and import of all operational state.
- One canonical deployment definition that matches production.
- **Release gating that covers what is still unverified.**
  - Add a provider contract test with real Anthropic and OpenAI-compatible keys: one turn with a bridged call in its history and a reduced tools array. If a provider rejects it, the Wave 2 wire fallback applies.
  - Run `scripts/cache_model_tokenizers.py` and the tokenizer tests in CI.
  - Exercise the MetaApi target-state, cancel and history paths against a demo account.
  - Gate releases on Playwright Web and Mobile parity once runners are back.

## Acceptance

The end-to-end scenario in the owner addendum §6 is the acceptance test for waves 2–3 combined. It is exercised with the simulation broker and controlled providers, with no live trades and no backtesting. Each wave records what was exercised, what evidence confirms it, and which integrations still need a real device or a configured provider.
