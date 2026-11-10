# Lonora mandate execution plan

Status: in progress. Started 2026-11-07. Wave 1 is implemented and integrated on the working branch (see [Wave 1 status](#wave-1-status)); Wave 1.5 is implemented and its acceptance journeys pass locally (see [Wave 1.5 acceptance](#wave-15-acceptance-w15-acc)); waves 2–4 are not started.

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
   - Delivered on branch `w15-b2` (no migration); the design is in `docs/agents-from-chat.md`. `agent_create` (trading, general, research, supervisor) creates an independent flexible root agent through the same creation function as the owner's form when the run answers the owner's message, and otherwise raises a `create_agent` card the owner taps. The trading template's focus pair comes from an exact broker catalog lookup (one account is used without asking; two matches return the candidates for one question). New agents never get a grant: trading starts at *Ask me*, the others at *No trading*, written explicitly. Per owner at most 20 active agents, per run at most three creations; replays and retries of one owner request never add a second agent. Provenance and the `report_to` peer link live in the agent's origin record and the `agent.created` event, and both agents' operating notes say who reports to whom. Every creation raises an `agent_created` card with Undo (remove an untouched agent, otherwise pause it). `watch_cancel`, `watch_pause`, `watch_resume` and `watch_update` steer only the agent's own watches, the owner cancels any watch from the status line, and `routine_toggle` reaches only the agent's own routines. The live state lists active watches; Web and Mobile show "Monitoring XAUUSD until 17:00" with a watch list and Cancel, and the header avatar follows the phase between runs. The identity line and the default rule in `lonora.md` follow correction 30. Supervision (`supervises`) arrived with W15-6.
   - Review fixes on `w15-b2`: a yes in chat to a pending creation card creates the agent once and closes the card (and any other card for the same agent); the owner's tap on a creation card queues one run for the proposing agent to hand the new agent its first task; both creation cards quote the stored task and say what the agent may do with money by its live level; Undo and the owner's delete remove the creation's notes and links from other agents (notes name agents, never ids) and never deadlock with each other; a Task waiting on its own watch reads as monitoring.
6. **W15-5 One owner profile, revertible memory** (corrections 18, 19).
   - A shared owner profile with attributed revisions and revert.
   - Self-edited operating notes.
   - Reach-me preferences settable from chat.
   - Delivered on branch `w15-b1` (migration `0038_owner_profile_memory_revisions` there, renumbered `0039_owner_profile_memory_revisions` at integration); the design is in `docs/agent-memory-and-recall.md` and `docs/incoming-attention.md`. One owner profile (`ln_owner_profile`) is the single USER.md every agent reads as an owner-attributed `owner_preferences` context section; `memory_write` on USER.md changes it only from a Run that answers the owner's message. `OPERATING.md` holds each agent's own working method. `ln_memory_revisions` records every commit of the profile, the preferences and each agent's memory with its author, and the owner can undo one change. Reach-me (activity, notify, message, call) and the reply language are set from chat with `owner_preferences_update`. Writes that add an authority statement to the profile or the operating notes are refused. Review fixes: locked re-reads are fresh so concurrent writers keep both changes, undo takes back exactly one change, an agent's write keeps its retired USER.md lines, each form keeps its unsaved edits, and reach-me validator codes have shared owner text.
7. **W15-6 Lonora sees everything** (corrections 1, 3, 15). Supervision grants, with the Personal Assistant supervising every agent by default (visible and revocable), and `agent_inspect` and `agent_control` tools. Peers stay private from each other.
   - Delivered on branch `w15-b2` (migration `0041_supervision_grants`; written after `0039_owner_profile_memory_revisions` on its branch and re-chained at integration to `down_revision = 0040_retire_super_bot_requests`); the design is in `docs/supervision.md`. `ln_supervision_grants` is seeded with a `default` grant from each Personal Agent over every other agent, and every agent created later gets one. Grants are set from the owner's message (`supervision_change`, `agent_create(supervises=…)`, the message recorded as the source) or the owner's tap on a `supervise` card, each with a `supervision_created` Undo card; the owner sees, stops and restores grants on every agent's profile on Web and Mobile. A grant opens the supervised agent's threads, decisions, Runs and memory to `session_search`, `search_internal`, `subagent_inspect` and `agent_inspect` (paged, on demand, every result named and labelled untrusted); revoking it ends them at once. `agent_control` pauses or resumes the agent, a Task, a routine or a watch and messages it; it never trades, grants, raises a limit, lifts a restriction or edits memory. `ln_supervision_holds` records who paused what: on its own initiative only that supervisor lifts its hold, a run that answers the owner's message lifts any supervisor's hold, the owner pausing the same work makes the hold the owner's (only the owner lifts it), the paused agent never resumes it on its own, and the cycle rule refuses a counter-pause or counter-narrowing unless the owner asks; every intervention is an event for both agents, and every pause raises a `supervision_paused` card in the paused agent's conversation naming the supervisor, with one-tap Resume. Without the owner's message a supervisor never pauses a whole agent with money standing (its exits would stop; it narrows it and pauses its routines, watches or Tasks instead), and no agent ever pauses Lonora. A revoke from chat raises a `supervision_stopped` card with Restore, and a supervised agent never revokes its own oversight. Narrowing another agent with `trade_restriction_create` now needs a grant or the owner's message (403 otherwise). A `coordination` exposure profile (`agent_inspect`, `peer_send`, `web_search`) is native for the Personal Agent and any agent holding a grant, except in a trading identity's Task Run. Limitation and open item for the acceptance slice: the rest of the research profile and the `collaboration_*` tools do not fit the Personal Agent's eager budget and stay one `tool_call` away, promoted after first use. The set was 25,695 of 25,700 on the branch and is 25,684 after integration (see the phase 2 status), so a longer eager description there still needs trimming elsewhere or an explicit, owner-approved budget.
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
   - Delivered on branch `w15-b2` (migration `0042_trusted_sources`, `down_revision = 0041_supervision_grants`); the design is in `docs/trusted-sources.md`. `ln_trusted_sources` lists github.com (seeded for every owner: the trust Skill imports always had, now visible and removable), GitHub owners and repositories, MCP servers (endpoint and each tool's input schema pinned; the read tier runs only the tools the server marked read-only at review, the non-financial write tier runs them all) and feed domains; operator declarations are seeded as read-tier entries that stand only for their declaration (removing it stops the tool until the owner reviews the server) and keep working as an allow override, and `LONORA_MCP_OWNER_TRUST=false` is the deny override. `mcp_execute` runs a trusted server's pinned tools without a declaration; a changed schema is blocked and raises one re-review card; a tool that can trade or move money (by name, description or a transfer-shaped input schema; the check fails closed) is never pinned and is refused; write-tier calls keep an effect receipt. Skill imports outside the list raise one `trust_source` card and fetch nothing; instructions-only packages install without the analysis host. `news_feed` integrations are read through the SSRF-safe public client (`news_feed_read`, `news_feed_subscribe`; D3: X through web search, feeds or a trusted X MCP server, never the owner's account), and channels deliver to an agent picked by name. `connect_credential` cards hold a secure form that posts straight to the owner API; agents see only "configured", and the agent that asked is woken once to continue after a trust or credential card (also when a connected MCP server's tools cannot be reviewed, which the confirmation line says). `GET /capabilities`, `capabilities_list`, and a Capabilities view on Web and Mobile show every source, Skill, server, integration and built-in capability (ready, not connected, not set up on this server) with Undo.
10. **W15-9 One vocabulary.**
    - Retire Super Bot and per-goal autonomy.
    - Rename Emergency Stop to "Stop new trading".
    - No raw ids or JSON in normal views.
    - The same labels on web and mobile.
    - Delivered on branch `w15-a2` (migration `0040_retire_super_bot_requests`, after `0040_explicit_agent_permission_rows`; the slice text named it `0041`, the orchestration `0040_retire_super_bot_requests`); the design is in `docs/owner-vocabulary.md`, `docs/trading-goals.md` and `docs/account-authority.md`. The three Super Bot tools, its routes and its cards on Web and Mobile are removed; pending and activated requests are marked `retired` and kept. A goal is a plan under the agent's level and grant: no autonomy switch or limit knobs, a live step outside the grant becomes an approval card (closing the W15-3 limitation), and a Shadow step needs no approval. The readiness review runs once for a newly signed bounded grant (full grants start their management Task), and a grant signed from the trading-level controls writes one confirmation line. The composer shows the trading level only for an agent that can trade, others show "No trading". Activity rows read from the tool's toolset and effect, which `tool.started` now carries; ids and JSON sit behind "Technical details"; the peer-outcome wrapper is stripped; operation and approval labels come from one `@lonora/core` table; the error copy says the outcome; Mobile says "agent". The model-facing policy (core 14,698 of 16,000 characters, goals chapter 2,998), constitution, prompts and bundled skills no longer name Super Bot or Emergency Stop. Review fixes: an uncertain broker result reads one shared reason on Web and Mobile (`financialResultReason`: never "Try again", it will not be sent again); a failed readiness review is observe-only and never puts the agent at "action required", and its line ends once later work completes; the migration also removes the retired autonomy keys from existing goals (restored on downgrade); a few activity labels that stated the wrong action have per-tool overrides; a goal's volume and action count are shown to the model as plan data (`planned_volume`, `planned_trade_actions`), and an owner's hard cap goes to a restriction or account limit.
11. **W15-10 Choose a model from chat** (D4): a per-agent model card, an agent-requested switch within the allowed list, and a usage view per agent. No spend cap.
    - Delivered on branch `w15-a2` (no migration; the E4 settings row gained a mode); the design is in `docs/provider-resilience.md` and `docs/owner-actions.md`. Each agent is *Automatic* (Lonora chooses: the owner's default model, and the agent may switch itself among the allowed models) or *Fixed* (one model only the owner changes), set from a model card in the agent's settings on Web and Mobile. The allowed list is the owner's global text routes and backups plus the owner's additions (`model_allowed`, editable in Model settings); Automatic agents fall back on the additions. `model_list` shows the agent its mode, the model answering now, the allowed models with exact ids and catalog matches for a name ("Opus"). `model_request` applies a switch at once when an Automatic agent picks an allowed model for itself, or when the owner's message in that run names an allowed model (that is how a Fixed agent changes, keeping Fixed, and how Lonora sets another agent); anything else (a model outside the list, always; a change the owner's words do not name) is a one-tap `agent_model` card whose confirmation adds the model to the list. Every applied switch is logged (`agent.model.updated`) and raises an Undo card that ends older requests about that agent; Undo restores who had chosen; at most three per Run. A switch changes only the model record: memory, tasks, grants, uncertain operations and the Run checkpoint stay, and nothing is repeated. `subagent_spawn` takes an allowed model, which leads the helper Run's chain; `consult_model` accepts any allowed model. Usage per agent comes from the recorded requests (`GET /usage/agents`, the usage settings and each model card). No cap (D4).
12. **W15-ACC Acceptance.** Scripted Arabic owner journeys check the confirmation counts in `VISION.md`, using the simulation broker and a scripted provider, plus the full local verification list.
    - Delivered on `ccr-9c66a289-3283wb` (no migration): `tests/check_simple_lonora.py`, `tests/web/simple-lonora.spec.mjs` and `tests/mobile/simple-lonora.spec.mjs`, with five product fixes the journeys found. The journeys, their evidence and what still needs a real broker, provider or device are in [Wave 1.5 acceptance](#wave-15-acceptance-w15-acc).

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

### Wave 1.5 phase 2 status

Recorded 2026-11-08. Phase 2 delivered W15-3, W15-9 and W15-10 on track A (`w15-a2`) and W15-4, W15-6 and W15-8 on track B (`w15-b2`). Each slice was implemented, reviewed adversarially and fixed after review on its own branch. The tracks were merged into `ccr-9c66a289-3283wb` with `--no-ff` merge commits: track A first (`1a9c221`, no conflicts, the branch was based on the phase 1 head), then track B (`e078f10`, 22 conflicted files), followed by two integration fixes (`98a7691` and `cd708e0`). The branch is not merged into `main` yet. GitHub CI is still dark, so everything was verified locally only, and nothing ran against a real broker account, a real model provider or a real device.

Points where the tracks met:

- **Migrations.** One chain and one head: `0039_owner_profile_memory_revisions` → `0040_explicit_agent_permission_rows` → `0040_retire_super_bot_requests` → `0041_supervision_grants` → `0042_trusted_sources`. `0041` named `0039` as its predecessor on its branch and was re-chained to `0040_retire_super_bot_requests`; `check_supervision` now downgrades to that predecessor. Two files share the `0040` prefix; their revision ids differ and sort in chain order. No deployed database has run any of them.
- **Retired Super Bot.** W15-9 moved the per-agent authority lock to `lonora_db.authority_lock` (same lock key). Track B's creation, Undo and delete paths now import it from there, and the agents route lists `trades_on_its_own` (track A) next to the creation record and the shared delete (track B). The TS contracts export `./devices`, `./capabilities` and `./supervision`, and no `./super-bot`.
- **Owner action cards.** The kinds are the union of both tracks: `grant_authority`, `agent_model`, `agent_model_changed`, `create_agent`, `agent_created`, `supervise`, `supervision_created`, `supervision_stopped`, `supervision_paused`, `trust_source` and `connect_credential`. Lifetimes, stale reasons, server facts, settled lines, confirmation texts and error texts are unions. The proposal validator keeps track B's split between capability and trading fields, with track A's grant fields on the trading side, and a grant field on a trust or credential card is refused. The decision route keeps the grant challenge, `confirm_grant`, withdrawal on dismiss and the model cards next to the creation, supervision, trust and credential branches. The result field `resumed` is a boolean on a grant card and the resumed item on a pause card. In the shared card spec `grantHint` stays the grant card's passkey hint; the creation card's "trades only inside the grant you signed" became `createdGrantHint`.
- **Tools and budgets.** Every new tool is long-tail except track B's `agent_inspect` in the `coordination` profile. Track A's wording change to `wait_for_input` had put the Personal Agent's conversation set (core, market and coordination) at exactly 25,700 of 25,700. The sentence is shorter now with the same meaning ("These answers cannot grant or transfer authority or approve trades"): 25,684 of 25,700, a trading Task Run 25,678. The promoted budget is unchanged at 4,100.
- **Policy and texts.** `manifest.json` was regenerated from the merged `lonora.md`, which keeps track B's research lines with track A's wording ("pauses or Stop new trading"). Every chapter is within its budget: memory 4,655, trading 4,565 and collaboration 4,410 of 4,666; core 14,692 of 16,000. The web catalogs were merged by msgid (no translation differed) and re-extracted: 812 messages, 0 missing Arabic.
- **Integration fix `98a7691`.** W15-9 builds each activity row from the tool's toolset and effect, with a per-tool label only where the family label would state the wrong action. Track B's tools were not in that table, so `agent_create`, `agent_control` and `supervision_change` read "Messaging agents" and the watch steering tools read "Setting a market watch". They now say what they do, in Arabic and English: creating an agent, reviewing or steering an agent's work, setting supervision, subscribing to a feed, checking capabilities, updating a market watch.
- **Integration fix `cd708e0`.** W15-10's model card put a second "Save" button in the agent settings panel, beside the profile form's Save, so the owner saw two identical buttons with different effects, and five Web Playwright specs that save the profile failed on the ambiguous name (`avatar-studio:6` in English and Arabic, `flexible-agent-ui:7` in English and Arabic, `rakazo-parity:13`). The model card's button now reads "Save model" / «حفظ النموذج». The slice had run only its own Playwright specs, so the full suite found it here.
- **Model at creation.** `agent_create` with a model writes it as the owner's choice through the W15-10 owner path. A choice with a model and no mode reads as *Fixed*, so an agent created on a named model keeps that model until the owner changes it, as it did before modes existed.

Per slice:

- **W15-3 One-sentence delegation and a monotonic ladder.**
  - Delivered: the `grant_authority` card with the D1 defaults, signed through the existing passkey ceremony (the same envelope as the permission composer); out-of-grant trades under *On its own* become approval cards; moving down revokes and says so; Lonora and root trading agents start at *Ask me*, the others at *No trading*, and existing agents keep an explicit level (`0040_explicit_agent_permission_rows`); raising or removing a money limit through the execution-policy route needs the passkey.
  - Verified: `tests/test_grant_card.py`, `check_grant_card` (including its migration round trip on the merged chain), `tests/web/owner-actions.test.ts`, Playwright `owner-actions` on Web (virtual authenticator, English and Arabic) and Mobile, plus the trade-approval, restriction and account-authority checks in the full sweep.
  - Limitations: approval reuse is per Run, so the same out-of-grant trade in a later wake raises a new card; one account per card; the card sets or lowers a daily loss limit and never raises or removes one; with no amount from the owner and no readable equity, no card is raised (`owner_action_equity_unavailable`).
- **W15-4 Create and steer agents from chat.**
  - Delivered: `agent_create` with four templates (at once from the owner's message, otherwise a card), the creation and Undo cards, the proposing agent's first-task run, ladder levels written at creation and never a grant, 20 active agents per owner and three creations per Run, watch steering on the agent's own watches, `routine_toggle` on its own routines, and one status line with the watch list on Web and Mobile.
  - Verified: `check_agent_create` (16 scenarios), `check_task_environment_wait`, `tests/test_agent_create.py`, `tests/web/agent-create.test.ts`, Playwright `agents-from-chat` on Web and Mobile in English and Arabic.
  - Limitations: provenance and peer links live in an `ln_settings` origin record (no typed column); a new trading agent starts at *Ask me*, and an *On its own* grant for it is a separate grant card the agent proposes, so the one-sentence "create and let it trade" journey takes two cards (for W15-ACC).
- **W15-6 Lonora sees everything.**
  - Delivered: supervision grants with the Personal Agent's visible, revocable default grant over every agent (`0041_supervision_grants`), supervised reads, `agent_inspect`, `agent_control` with holds and the cycle rule, `supervision_change`, the supervise, Undo, Restore and pause cards, and the Supervision section on every profile.
  - Verified: `check_supervision` (seed and round trip on the re-chained migration, a later agent, a Lonora journey through a real Run, revoke), `tests/test_supervision.py`, `tests/web/supervision.test.ts`, Playwright `supervision` on Web and Mobile.
  - Limitations: peers share nothing private except through supervision (a scoped knowledge store is Wave 2); the rest of the research profile and the `collaboration_*` tools stay outside the Personal Agent's eager set; without the owner's message a supervisor narrows an agent with money standing and pauses its work items, never the whole agent.
- **W15-8 Capabilities you can see.**
  - Delivered: one trusted-sources list (`0042_trusted_sources`), trusted MCP servers with pinned schemas and the read and non-financial write tiers, a money classifier that fails closed, trusted Skill sources, news feeds, the `trust_source` and `connect_credential` cards, and the Capabilities view on Web and Mobile.
  - Verified: `tests/test_trusted_sources.py`, `check_trusted_sources`, `tests/web/capabilities.test.ts`, Playwright `capabilities` on Web and Mobile, plus the MCP, Skill and market checks in the full sweep.
  - Limitations: the classifier is a word and shape list that errs toward blocking; the read tier relies on the server's own read-only hint; feeds are read on demand, and feed watches that wake an agent come with the Wave 2 wake primitive; a credential record whose confirmation failed stays in Capabilities for the owner to remove.
- **W15-9 One vocabulary.**
  - Delivered: Super Bot and per-goal autonomy retired (`0040_retire_super_bot_requests`, data only and reversible), goals as plans under the grant with an approval card for a step outside it, "Stop new trading" everywhere, activity rows from toolset and effect, ids and JSON behind "Technical details", and one label table for Web and Mobile.
  - Verified: `tests/test_one_vocabulary.py`, `tests/web/one-vocabulary.test.ts` (now covering track B's tools too), `check_device_authority` (migration round trip), `check_activation_review`, `check_goals`, `check_shadow_goals`, Playwright `one-vocabulary` and `goals` on Web.
  - Limitations: old Super Bot inbox items keep their codes and read "Request updated"; paused Super Bot rows are left as they are (they grant nothing); the lock key keeps its old prefix so a rolling restart takes the same lock.
- **W15-10 Choose a model from chat.**
  - Delivered: *Automatic* or *Fixed* per agent, `model_request` and `model_list`, the `agent_model` and `agent_model_changed` cards with Undo, the allowed list, and usage per agent with no spend cap (D4).
  - Verified: `check_agent_model_choice`, the router and contract unit tests, `tests/web/agent-model.test.ts`, Playwright `agent-model` on Web and Mobile in English and Arabic.
  - Limitations: a model named in Arabic transliteration falls back to the card; the model record outlives a deleted agent (unreachable); the Fixed picker can list non-chat models for catalogs that do not report capabilities; there are no per-adapter reasoning controls.

Verification on the merged tree, each database step on its own fresh PostgreSQL 16 database. The static, TypeScript and Web Playwright rows ran at `cd708e0`. The Python and database rows ran at the merge commit `e078f10` and Mobile Playwright at `98a7691`; the two later commits change only TypeScript labels and their tests:

| Check | Result |
| --- | --- |
| `ruff check .`, `ruff format --check .`, strict `pyright` | Pass. 0 errors. |
| `validate_resources`, `export_agent_tool_reference.py --check`, `export_native_visual_reference.py --check`, `check_policy_distribution.py` | Pass. |
| `pnpm lint`, `pnpm check` (7 TS packages), `pnpm build`; `pnpm --filter @lonora/web i18n` | Pass. Arabic: 812 of 812 translated. `AGENTS.md` unchanged. |
| `tsx --test` web and mobile | 189 and 51 passed. |
| Alembic: upgrade head, downgrade to `0035_agent_tool_usage`, upgrade head | Pass. One head, `0042_trusted_sources`. |
| `pytest tests` (fresh `lonora_main_test`) | 2012 passed, 5 skipped (APK), 0 failed. Phase 1 had 1927. |
| All 113 `tests/check_*.py` | 104 pass. The 9 failures are the known harness and environment cases: the Playwright stdin helpers `check_chart_browser`, `check_group_ux`, `check_question_browser`, `check_rakazo_ui` and `check_task_browser` when run alone, and `check_analytical_workspace`, `check_analytics_profile`, `check_public_skill_package` and `check_workspace_container_runtime`, which need an administrator-reviewed analysis image and a Docker daemon. New and passing: `check_grant_card`, `check_agent_model_choice`, `check_agent_create`, `check_supervision` and `check_trusted_sources`. |
| `pytest tests/test_task_runtime.py` (`LONORA_TASK_TEST_DATABASE_URL`) | 11 passed. |
| CI "authenticated durable runtime" and "persistent context, steering and concurrency" steps, re-extracted from `ci.yml` and run in order on one database, as in CI | Pass. 22 of 22. |
| Playwright `test:web` / `test:mobile` (system Chrome, each suite on its own fresh `*_ci` database) | Web at `cd708e0`: 109 passed, 8 failed. Seven are baseline failures: `agent-permissions:391` (`:380` in the baseline), `group-status:14`, `skills-management:121` and `visual-response:64` in all four locale and theme variants. The eighth, `avatar:110`, is the known reduced-motion timing flake: it passed in the first full run and again alone on a fresh database. `goals:14` (fixed by W15-9) and `inbox:120` pass. The first full Web run, at `98a7691`, had 13 failures: the same baseline set, `inbox:120`, and the five "Save" failures fixed by `cd708e0`, which pass on rerun (8 of 8 with `agent-model`). Mobile at `98a7691`: 54 passed, 5 failed, exactly the baseline: `attention:4`, `chat-reliability:85`, `skills-management:67` (en and ar) and `workspace:7`. The new specs pass, among them `owner-actions` (grant card with a virtual authenticator), `one-vocabulary`, `agent-model`, `agents-from-chat`, `supervision` and `capabilities` on Web, and `owner-actions`, `agent-model`, `agents-from-chat`, `supervision` and `capabilities` on Mobile. No failure is new. |

### Wave 1.5 acceptance (W15-ACC)

Recorded 2026-11-08 on `ccr-9c66a289-3283wb`. The acceptance slice ran the owner's journeys from `VISION.md` through the normal entry points and fixed what they found. As before, GitHub CI is dark, so everything ran locally, and nothing ran against a real broker account, a real model provider or a real device.

How the journeys run:

- `tests/check_simple_lonora.py` (registered with the isolated foundation checks) sends Arabic owner messages to `POST /threads/{id}/messages`. Each Run is claimed the way the gateway claims it (same lease, fence and recovery bookkeeping as `claim_next`) and executed by the gateway's `AgentRuntime`. The model is a scripted provider adapter behind the real model router (`OwnerServices.router`); capabilities outside a Run's native tools are called through `tool_call`, as a real model does. Market and order state come from the simulation broker. Every owner decision is the request a card sends (`/owner-actions/{id}/decision`, `/trading/approvals/{id}/decision`, `/trading/controls`), with a scripted passkey (`tests/device_fixture.py`) where the card needs one. Cards the runtime raises come from the gateway's attention step (`attention_tick`).
- A worker restart is simulated by cancelling the worker task in the middle of a Run, letting its lease expire and claiming the Run again with another worker: once mid-send (the broker took the order and the worker died before it heard back), once mid-turn after a watch was saved, and once mid-turn after two agent creations. Each time the restarted model, careless on purpose, asks for the same effect again under a new call.
- `tests/web/simple-lonora.spec.mjs` and `tests/mobile/simple-lonora.spec.mjs` type the same Arabic sentences into the real Web and Expo composers. `check_simple_lonora.py --ui-turn` stands in for the gateway worker: the real runtime with the scripted provider, then the attention step. The owner taps the cards in the browser (Web: a virtual authenticator for the passkey).

Journeys exercised (owner confirmations: what the vision's "when Lonora asks" rule gives, and the slice's journey list where it differs):

| Journey | Where | Confirmations | Evidence |
| --- | --- | --- | --- |
| J1 «أنشئ وكيل ذهب يدير صفقاتي على حسابي بنفسه، وخسارة يومية قصوى 2%» | check; Web; Mobile (cards only) | 1 | One owner sentence creates the gold agent (XAUUSD from the only account's catalog, no question, *Ask me*, no grant) and one grant card: gold only, every action, until stopped, own positions excluded, 2% of equity = 200.00 USD, "Resume trading too". One passkey tap signs it (on a device with no passkey yet: Authorize, then Register with the password, and the second system prompt follows at once; corrected after the review, `3f09972`), resumes trading and sets the daily loss limit; Lonora confirms in Arabic; one management Task starts. The pill reads «يتداول باستقلال · XAUUSD · حتى توقفه · الخسارة اليومية 200.00 USD» (Web, after fixes 1 and 5). The agent then buys on its own with no tap. |
| J2 «خلي لونورا تدير كل أزواجي بنفسها» | check | 2 (one per account; two accounts) | One grant card per account, all pairs preselected, the account's own 200 limit kept on the first and the 3% suggestion (300.00) on the second, the gold agent named on the first ("keep both"). After signing, Lonora trades without a tap; a stop-loss hit on its position wakes Lonora once with its normal authority (not observe-only), and a second reconciliation wakes nobody. |
| J3 «أوقف فتح صفقات جديدة اليوم، وكمّل مراقبة الذهب», later «رجّع التداول» | check; Web; Mobile | 1 | One restriction (all agents, until the end of the day, recorded from the owner's message); the watch keeps running; one Lift card with no model; every agent's pill says the same pause and end time; a new entry is refused with `trading_restriction_active` before any approval card (fix 3); «رجّع التداول» offers the same card, never a second; one tap lifts it and Lonora confirms in Arabic. Web and Mobile pills follow the tap (Mobile after fix 4). |
| J3b the same on two accounts | check | 2 (journey list assumes one account) | A restriction is per account, so a pause "on all my accounts" is one Lift card per account. |
| J4 «أنشئ وكيل أخبار يتابع الأخبار الاقتصادية ومحللي X ويبلغ وكيل الذهب بالمهم، وخلي وكيل ثاني يشرف عليهم» | check, with a worker restart | 2 (journey list: 1) | One news agent (*No trading*, reports to the gold agent), one supervisor over both (grants from the owner's message), Lonora's default grant over both, one Undo card each and one "Connect X" card, also after the restart and the repeated calls. Connecting X through a trusted MCP server (D3) is a secure card (the token goes straight to the owner API) and a trust tap on the tools the server reviewed (`place_order` blocked): two of the vision's asks. The news agent then reads X through the server and messages the gold agent, whose answer comes back to it. |
| J5 an agent adds a skill | check | 0 | The news agent installs a pinned instructions-only skill from github.com (trusted by default), with no analysis host running, and activates it itself; Capabilities lists it with Undo; no card. |
| J6 «أضف خادم MCP هذا: …» | check | 2 (journey list: 1) | One secure card (no token here) and one trust tap; the gold agent then uses the server's read tool with no declaration and no card; its order tool is refused. |
| J7 an uncertain trade | check | 1 | The broker applies the gold agent's order but its reply is lost and reconciliation cannot see it: one `operation_uncertain` (action required) item and one three-button card in the gold agent's conversation; the pill says one operation awaits the broker. One tap ("It executed") resolves it, the hold clears, the answer posts back to the same conversation, the attention item is withdrawn, nothing is resent. |
| J8 «ماذا فعل وكيل الذهب اليوم، ولماذا لم يدخل في افتتاح لندن؟» | check | 0 | Lonora reads the gold agent's overview and its own WAIT decision through `agent_inspect` under its visible grant; none of it was in Lonora's context before it asked. |
| J9 «ردودك قصيرة بالعربي، وراسلني بدل ما تتصل» told to the gold agent | check | 0 | Reach-me becomes "message" and the reply language Arabic; the line is added to the one owner profile, attributed to the gold agent and the owner's message; Lonora's next Run has it in its context. |
| J10 «راقب الذهب خلال جلسة لندن اليوم», later «وقف مراقبة الذهب» | check, with a worker restart | 0 | One watch with the London close as expiry, also after the restart and a repeated request (fix 2); the status line shows monitoring with the watch; `watch_cancel` stops it with Undo. |
| J11 one trade from an agent at *Ask me* | check; Web | 1 | One approval card with labeled values; nothing reaches the broker before the tap; after the tap the result is the broker's confirmation with its ticket. |
| J12 Stop all new trading from the phone | check; Mobile | 1 (and 1 to resume) | One request stops (exits stay allowed, the pill says so); one Resume clears both flags. |
| J13 «خلي وكيل المراقبة يشرف على وكيل الذهب ووكيل الفضة» | check | 0 | A silver agent from one sentence; the supervision grants come from the owner's message with an Undo card; the supervisor reads the silver agent and its trade attempt is refused (`agent_analysis_only`). |

Properties, across all the journeys of the check: every live operation an agent sent carried either a signed grant (`account_authority_id`) or the owner's approval of that exact operation (3 and 1); the three restarts left one operation, one watch, one agent per name and one pending card per effect, and the order sent before the crash reached the broker once and was confirmed by reconciliation (never resent); the pill, the cards and the records were compared at each step; neither the provider key nor the MCP token appears in any message, event, card, Run, attention item, approval, journal row, memory or owner profile, nor in any of the 61 model requests; and no conversation line carries a raw id or JSON (a colleague's result is read as the clients show it, without its wrapper).

Defects found and fixed, each in its own commit with tests:

1. `73b730d` The status line names the daily loss limit an agent trades under: the pill said "Trades on its own · XAUUSD · until you stop it" while the card and the records had the 200.00 USD limit.
2. `b93efdd` An identical watch request keeps the one live watch: without a `dedupe_key`, a model asking again after a worker restart created a second identical watch.
3. `eefa5fe` Brakes come before approval cards: an agent at *Ask me* raised an approval card for an entry that a pause or Stop new trading would refuse at send, so the owner could approve something that then failed. The tool now returns the boundary's code before any card; exits are still asked and decided by the executor. `check_trading_restrictions` and `check_execution_recovery` expect the earlier refusal.
4. `2726073` Mobile: the header pill follows a card the owner just decided (it polled every 15 seconds, so after a one-tap Lift it kept saying "paused").
5. `b7fb36d` The status line reads a granted account however many accounts the owner has: the projection read only the owner's first ten accounts, so in the full Web suite (many accounts left by earlier specs) the gold agent's pill said "No money limit set" next to a 200 USD limit.

Integration fix found by the full sweep: `0dde33f` `check_personal_agent` expected an approval card for Lonora's entry while new trading had never been started; it now expects the refusal first (fix 3), then starts trading and checks the card.

Open points (not changed here):

- Adding an MCP server, and "Connect X" through one, takes two owner steps: the secure card and the trust tap. That is the vision's own rule (a new credential, then a source outside the trusted list); the journey list counted one. A single connect-and-trust card would need the owner preview (`POST /trusted-sources/mcp/{id}/preview`) inside the credential card on Web and Mobile.
- A pause for "all my accounts" is one restriction and one Lift card per account.
- The restart is simulated by cancelling the worker task. The executor's own cancellation path then records the send as ambiguous at once; a process that dies without running any cleanup (the `tool_execution_uncertain` path) is covered by the E1 tests, not here.
- A colleague's result is stored in conversations inside its `<peer_outcome run_id=…>` wrapper; Web and Mobile strip it before showing it.
- Mobile was exercised on the Expo web export: cards, the composer, the pill and the sheet. The passkey ceremony on a phone was not.

Still needs a real broker, provider or device:

- **MetaApi**: a grant-signed order and its fill through MetaApi; a lost acknowledgement and its reconciliation through real deal history (the uncertain journey); a real stop-loss hit waking the agent that opened the position; the daily loss limit measured from real deals; the "all pairs" grant against a real symbol catalog.
- **Model provider**: whether a real model takes these journeys from the Arabic sentences alone, reaching `agent_create`, `owner_action_propose`, `trade_restriction_create` and `supervision_change` through `tool_call`; whether it reconciles instead of retrying after an uncertain result; reply language and length from the owner profile; real context budgets.
- **Devices**: the passkey card on iOS and Android (native WebAuthn), Arabic RTL rendering in the native apps, and off-app delivery (Wave 3).
- **Network sources**: a real X MCP server and its schema, RSS/news feeds over the network, SearXNG web search and the economic calendar provider.

Verification on the final code tree (`b7fb36d`; the documentation commit that follows changes nothing else), each database step on its own fresh PostgreSQL 16 database. A first full sweep at `2726073` found the `check_personal_agent` and status-line defects fixed above; everything below was run again after them:

| Check | Result |
| --- | --- |
| `bash scripts/build.sh`: `ruff check .`, `ruff format --check .`, strict `pyright`, `validate_resources`, `export_agent_tool_reference.py --check`, `export_native_visual_reference.py --check`, `check_policy_distribution.py`, `pnpm lint`, `pnpm check`, `pnpm build` (with `env -u AI_AGENT -u CLAUDECODE`) | Pass. Pyright 0 errors. `AGENTS.md` unchanged. No tool description or policy text changed; the tool reference and policy distribution checks pass unchanged. |
| `pnpm --filter @lonora/web i18n` | Pass. Arabic: 812 of 812 translated (no new messages). |
| `tsx --test` web and mobile | 189 and 51 passed. |
| Alembic: upgrade head, downgrade to `0035_agent_tool_usage`, upgrade head | Pass. One head, `0042_trusted_sources` (no migration in this slice). |
| `pytest tests` (fresh `lonora_main_test`) | 2015 passed, 5 skipped (APK), 0 failed. Phase 2 had 2012; the three new tests are `test_approval_brakes`, the identical-watch case in `test_proactive_wakes` and the granted-account case in `test_trading_readiness`. |
| All 114 `tests/check_*.py`, each on its own fresh database | 105 pass, with 460 PASS lines, among them the new `check_simple_lonora`. The 9 failures are the known harness and environment cases: the Playwright stdin helpers `check_chart_browser`, `check_group_ux`, `check_question_browser`, `check_rakazo_ui` and `check_task_browser` when run alone, and `check_analytical_workspace`, `check_analytics_profile`, `check_public_skill_package` and `check_workspace_container_runtime`, which need an administrator-reviewed analysis image and a Docker daemon. |
| `pytest tests/test_task_runtime.py` (`LONORA_TASK_TEST_DATABASE_URL`, fresh `*_test`) | 11 passed. |
| CI "authenticated durable runtime" and "persistent context, steering and concurrency" steps, re-extracted from `ci.yml` and run in order on one database, as in CI | Pass. 1 and 22 PASS lines. |
| Playwright `test:web` / `test:mobile` (system Chrome, each suite on its own fresh `*_ci` database) | Web: 109 passed, 9 failed. Seven are the phase 2 baseline (`agent-permissions:391`, `group-status:14`, `skills-management:121`, `visual-response:64` in all four variants); `avatar:110` is the known reduced-motion timing flake and passed alone on a fresh database; `inbox:120` failed in the phase 1 baseline too, passed in phase 2 and passed alone here. The new `simple-lonora` passes. In the first full run (`2726073`) `agent-permissions:257` (desktop EN dark) failed once; it passed alone and in this run. Mobile: 55 passed, 5 failed, exactly the baseline (`attention:4`, `chat-reliability:85`, `skills-management:67` in English and Arabic, `workspace:7`); the new `simple-lonora` passes. No failure is new. |

### Review of Wave 1.5 (2026-11-08)

Four reviewers (financial, security, experience, durability) reviewed the branch after the acceptance record (`e4b9e68`) and reported 27 findings. Each one was checked against the code, and every high finding was reproduced (the reviewers' scripts, then a regression test) before it was fixed. Every fix has its own test. No finding was rejected as not real; three low findings and parts of two others are deferred below with the reason. The fixes add one migration, `0043_owner_held_pauses` (`down_revision = 0042_trusted_sources`), which is now the single head.

- **Financial.**
  - Fixed (high, D1): a position the owner opened from Lonora's own Trading page counted as Lonora-opened, so a default grant that excludes the owner's own positions let an agent clear its stop and close it without a card. Only an entry an agent's leased Run sent is Lonora-opened now (`9b65a04`).
  - Fixed (high): an agent could undo the owner's own pause or cancel of its watches, routines and Tasks in any wake. Such a pause is now a hold of its own (`source='owner'`, no holder), and only the owner's Resume lifts it (`157a5ac`).
  - Fixed (high): the MCP money classifier let broker actions through (`open_long`, `mt5_execute`, `close_ticket`, `modify_sl`). It now also blocks broker platforms and trading terms, a trading term next to an acting verb, a broker named in the description, and order- or position-shaped input schemas. A server that offers any blocked tool can only be trusted to read, and the owner route refuses the write tier (`trusted_source_write_blocked`). The card and Capabilities copy says what is enforced (`3b777c4`).
  - Fixed (medium): raising or removing an execution cap the executor enforces (positions, pending orders, volume per symbol and direction, spread, entry drift, quote and account freshness) now needs the passkey ceremony, like a money limit. Adding or lowering a cap stays one request (`df2f9b3`).
  - Fixed (medium): the monotonic ladder is complete. A request that breaks any grant term (caps, equity floor, bounded stop rules, action budget), not only account, market or action, becomes an approval card instead of a refusal. The trade tool and Goal steps run the executor's own grant check read-only on the broker's current facts (`grant_covers`). Brakes are classified on the same facts before any card (`9b65a04`).
  - Fixed (low): a follow-up or synthesis Run after a peer's answer keeps the requester's observe-only narrowing (`625eb56`).
- **Security.**
  - Fixed (high): the "Run answers the owner's message" proxy no longer stands for the owner once the Run has read content someone else wrote. That covers a tool on the context engine's untrusted list (web, search, feeds, MCP, peers' memory, files, another model), recorded once per Run, and another agent's message in the thread. Supervision, agent creation and control, the owner profile and reach-me then fall back to the owner's card. Oversight for the calling agent itself, or over Lonora, is always a card the owner taps, also through `agent_create(supervises=...)` (`77aa171`).
  - Fixed (high): a created agent's responsibility is, while it is still the creating agent's text, a labelled `agent_authored` context section, never system-role instructions. `report_to` notes quote names as data (`77aa171`).
  - Fixed (medium): `agent_control` needs a supervision grant. On the owner's message only Lonora acts without one (`77aa171`), and the owner's own pauses are holds (`157a5ac`).
  - Fixed (medium): the memory guard refuses standing instructions to send memory, notes, the profile or secrets elsewhere, to fetch an address built from data, or naming `peer_send`. A tainted Run cannot write the profile or reach-me (`77aa171`).
  - Fixed (low): agent-declared critical alerts are capped at six per owner and rolling hour across every agent. Beyond that they count as an important change (`8ac467c`). Agent names and responsibilities lose Unicode direction controls, and `isolate()`/`isolated()` drop them before wrapping (`77aa171`).
- **Experience.**
  - Fixed (high): a signed grant card shows what was signed (`signed_facts`), not live state. It no longer shows a declined daily loss limit or names itself as the grant it replaces. While Stop still holds, it says the agent trades on its own once the owner resumes (`78a27de`).
  - Fixed (high): on a fresh install, an agent's first entry raises the one-tap Start trading card itself (`trading_not_started`) instead of a bare refusal. The permission frame tells a never-started install from the owner's own Stop, which stays the owner's brake (`78a27de`).
  - Fixed in part (medium): the status line counts the agent's pending decision cards (not Undo notices) and its own unsettled live operations. It reads "Waiting for you", "Awaiting broker confirmation" or "Uncertain" in Arabic and English, like the pill (`04bf977`).
  - Fixed (medium): registering a device continues straight into the card's passkey prompt on Web and Mobile, so a first grant is Authorize, then Register with the password, and the second system prompt follows at once. The Web specs count the registration tap separately. The J1 record above is corrected (`3f09972`).
  - Fixed (medium): Arabic names equity with one term, «حقوق الملكية», on the grant card, the pill, limits and the Web catalog. A vocabulary test keeps it that way (`78a27de`).
  - Fixed (low): with grants on several accounts the pill reads "Trades on its own on 2 accounts". When the owner has several accounts, it names the granted account the way the sheet does (`64c13b3`).
- **Durability.**
  - Fixed (high): deleting a supervisor dropped its holds (`ON DELETE CASCADE`) while the work stayed paused. Its live holds now become the owner's first, and the holder column is `ON DELETE SET NULL` (`157a5ac`, migration `0043`, whose downgrade refuses while a holder-less pause is live).
  - Fixed (medium): the `0041` and `0042` downgrades refuse while a grant the owner set or revoked, a live hold, or a source the owner added or removed exists. Before, a re-upgrade silently restored a revoked default (Lonora reading an agent again, all of GitHub trusted again). A refused downgrade changes nothing (`d4380ed`).
  - Fixed (medium): the `0039` downgrade writes every profile line the agent rows do not already hold back as a `# USER.md` section of the Personal Agent's document, and the re-upgrade merges it again. The revision history still goes with the tables (`d4380ed`).
  - Fixed (medium): the `0039` merge never pushes the profile past its 8,000-character limit. Whole agent blocks join oldest first while they fit; the rest is routed, never dropped, into that agent's own operating notes, once. An over-limit profile can be saved shorter (`d4380ed`).
  - Fixed (low): two gateways recording one item's first failure no longer raise a duplicate-key error out of `ItemGuard.run` (`2df05a2`).

Deferred, with the reason:

- **Telegram sender (security, low).** Inbound Telegram updates are still gated by chat id only, so in a group chat the owner allowed, any member's message is an owner message. Checking `message.from.id` needs an owner-configured Telegram user id: a new setting with Web and Mobile copy. Giving channel messages their own trigger changes what the owner can do from Telegram. Both belong with the channel work in Wave 3. Until then the external-content taint applies to these Runs like any other, and allowing a group chat stays the owner's choice.
- **Decision cards in the attention inbox (experience, part of a medium).** The status line now waits for cards, but a decision card raised in a background wake still shows up only in its conversation. Projecting decision kinds into attention items, and withdrawing them when the card settles, is listed for Wave 3 with the inbox work.
- **Compact Undo notices (experience, low).** `agent_created`, `supervision_created` and `agent_model_changed` still render as button cards. A one-line confirmation with an inline Undo is a shared card-spec change on both clients, listed for Wave 3.
- **Undo of profile and memory changes on Mobile (experience, low).** Per-change Undo of the owner profile and memory is still on Web only (`MemoryRevisions.tsx`). The Mobile revisions list is listed for Wave 3.
- **Residuals of fixed findings.**
  - A created agent's responsibility can still appear, JSON-escaped, as the agent's description in the server-listed agent directory. That is data the server lists, not an instruction block.
  - A whole-agent pause of an agent with money standing still follows the owner's untainted message when Lonora or a supervisor carries it, because the owner asked in their own words (the W15-6 rule).
  - `grant_covers` checks a batch against one broker snapshot taken before the send. If the state changes before the send, the executor's check under the account lock refuses instead of asking: it fails closed, never wider.
- D2 (the signed emergency reduction rule) stays in Wave 2, as decided.

Verification on the final code tree (`2c5092c`; the documentation commit that follows changes nothing else), each database step on its own fresh PostgreSQL 16 database. The first sweep at `d4380ed` found four integration defects, each fixed in its own commit and run again:

- Strict pyright, which `scripts/build.sh` runs over the tests too, found 24 type errors in three review-fix tests (`2387836`).
- `pnpm check` found the readiness params declaring `account_id` twice, and Biome warned about a non-null assertion in a test (`d41aa5d`).
- `pytest tests` failed `test_approval_brakes` on a fresh database. Saving the stopped default on a never-started install stores nothing, so the case got the Start trading card instead of the owner's Stop (`9e1cd30`).
- Playwright Mobile `capabilities:178` (en and ar) still expected the write tier for a server that offers a blocked money tool (`2c5092c`).

| Check | Result |
| --- | --- |
| `bash scripts/build.sh`: `ruff check .`, `ruff format --check .`, strict `pyright`, `validate_resources`, `export_agent_tool_reference.py --check`, `export_native_visual_reference.py --check`, `check_policy_distribution.py`, `pnpm lint`, `pnpm check`, `pnpm build` (with `env -u AI_AGENT -u CLAUDECODE`) | Pass at `9e1cd30`, and `pnpm lint` again at `2c5092c` (that commit changes one spec only). Pyright 0 errors. `AGENTS.md` unchanged. |
| `pnpm --filter @lonora/web i18n` | Pass. Arabic: 812 of 812 translated, 0 missing. |
| `tsx --test` web and mobile | 191 and 51 passed. |
| Alembic: upgrade head, downgrade to `0035_agent_tool_usage`, upgrade head | Pass. One head, `0043_owner_held_pauses`. |
| `pytest tests` (fresh `lonora_main_test`) | 2041 passed, 5 skipped (APK), 0 failed. The acceptance record had 2015. |
| All 116 `tests/check_*.py`, each on its own fresh database | 107 pass, among them the new `check_grant_coverage` and `check_lossless_downgrades`. The 9 failures are the known harness and environment cases. Five are the Playwright stdin helpers when run alone (`check_chart_browser`, `check_group_ux`, `check_question_browser`, `check_rakazo_ui`, `check_task_browser`). Four need an administrator-reviewed analysis image and a Docker daemon (`check_analytical_workspace`, `check_analytics_profile`, `check_public_skill_package`, `check_workspace_container_runtime`). The lanes started at `d4380ed`; the later commits change tests and TypeScript only, not the Python packages these checks run. |
| `pytest tests/test_task_runtime.py` (`LONORA_TASK_TEST_DATABASE_URL`, fresh `*_test`) | 11 passed. |
| CI "authenticated durable runtime" and "persistent context, steering and concurrency" steps, re-extracted from `ci.yml` (unchanged since the last extraction) and run in order on one database, as in CI | Pass. 1 and 22 PASS lines. |
| Playwright `test:web` / `test:mobile` (system Chrome, each suite on its own fresh `*_ci` database) | Web: 111 passed, 7 failed, exactly the phase 2 baseline (`agent-permissions:391`, `group-status:14`, `skills-management:121`, `visual-response:64` in all four variants). `avatar:110` and `inbox:120` pass, and so do `owner-actions` and `simple-lonora` with the counted registration tap. Mobile, after `2c5092c`: 55 passed, 5 failed, exactly the baseline (`attention:4`, `chat-reliability:85`, `skills-management:67` in English and Arabic, `workspace:7`). No failure is new. |

## Next, after PR #30 is merged (separate branches and PRs)

- **Reference UI for `apps/web`** from `docs/ui-reference/Lonora-Desktop-37.html`, in six phases, one PR each (see «Reference UI» below and `docs/ui-reference/CAPABILITY_MAP.md`).
- **Agent computer and domain scope** (D5–D7). Each agent gets a persistent isolated environment: a terminal, controlled internet through the SSRF-safe proxy, long jobs, Lonora tools callable from code, and server-injected credentials that the agent never sees, including OAuth connections. It gets no interactive browser, no hosting and no inbound ports, and broker or financial hosts are refused. A domain-scope rule sits in the protected core, with a permanent refusal test set.
- **More brokers** as adapters behind the single executor. Alpaca is dropped: the owner does not need it (2026-11-10, «لي Alpaca لا داعي نهائين ولانحتاجه»); its adapter (PR #36, branch `trading/alpaca-adapter`) was closed unmerged. MetaApi stays the only built-in broker (owner, 2026-11-10): other brokers and platforms come through MCP connections (read and analysis; trading tools stay refused) and, later, through plugins that trade only behind the single executor.

## Reference UI

`docs/ui-reference/Lonora-Desktop-37.html` is the single source of truth for the look and behaviour of the new `apps/web` (phone under 900px, desktop at 900px and above, dark and light, motion, gestures, loading, empty and error states). The backend is changed to serve it, not the other way round; nothing is faked or hidden behind a capability flag; the avatar stays Lonora's. `docs/ui-reference/CAPABILITY_MAP.md` maps every element of the reference to its backend source at `ab16645`, groups the missing backend into work packages (WP-A to WP-I), and records the contradictions and owner questions (money-safety invariants and owner decisions D1–D7 are never resolved silently). The owner's answers to the map's questions are recorded in `docs/ui-reference/OWNER_DECISIONS.md`; they are binding for phases 2–6 and supersede conflicting map recommendations. Six phases, one PR each:

1. Capability map, tokens and icons (`packages/ui-tokens/src/reference.{ts,css}`, `packages/ui-web/src/icons`, the map).
2. Layout, lists and sheets: glass top bar, floating tab bar and pager, desktop rail and panes, chat list with per-owner read state, pins, mute, archive and custom lists (WP-A, WP-B), unified search (WP-C), the sheet system, skeletons and interface states.
3. Conversation: header with status and alert capsule, one Message component with every kind, composer with the permission menu, mandate, limits and lift sheets, cards (approval, resolve, order line, undo notices, question, task), generative UI mapped to `RichContent` (WP-D to WP-G).
4. Agent and domain pages: agent page and sheets, identity and templates, groups, goals, knowledge, skills, schedules, tasks, files, activity, trades, the market chart sheet, the updates page.
5. Settings, onboarding and usage: settings root, owner profile with change log, notifications and reach-me, integrations (accounts, providers, MCP, feeds, skills), usage dashboard (WP-I), storage, privacy, help, legal, install, the authentication screens that exist on the server.
6. Calls: call screen, header capsule and strip, incoming call, call log messages (WP-E).

Each phase passes when the reference and the app match side by side (Playwright, 390x844 and 1280x800, dark and light) and the contradictions it touches are answered by the owner or left out of the build.

### Reference UI phase 2 status

Recorded 2026-11-09, branch `ui/phase-2-shell` (not pushed, not merged; GitHub CI still dark, so everything below ran locally). Phase 2 is delivered: every row of the Phase 2 table in `docs/ui-reference/CAPABILITY_MAP.md` carries **delivered**, and the rows that are still partial say what and why.

- **Implemented.** The reference shell on `apps/web` at both breakpoints and in both themes: the glass top bar with its scroll edge, the bare main tabs and inner pages (large title, floating back), the floating tab bar with its lens, fold and badges, the tab pager, the desktop rail, list pane (collapsible) and welcome pane, the sheet system (bottom sheet, centred modal, expandable detents, bar header with in-sheet pages, keyboard avoidance), skeletons, toast, network strip, update bar, not-found and render-error pages, maintenance overlay, permission sheets (microphone and camera; notifications hidden per Q10), heads-up banner (mute, archive and quiet hours suppress it; critical and action_required attention always shows, Q4), shortcuts, Back/Escape order and the unsaved-changes guard. The chat list: every agent and group as a row with preview, ticks (Q2), time, unread count or dot, muted and pinned marks, the paused badge and the group's member cluster (Lonora's avatar); pull-down filters, pins (three), selection mode and its toolbar, archive row and page with keep-archived, «مسح»/«حذف» hiding history only (Q1), custom lists with the full-height new-list sheet and emoji panel, the unified search (browse feed, categories, paging, jump to a message), the new-chat sheet with «إدارة الوكلاء», the agents page, the three-template «وكيل جديد» step and the offline queue (Q6). The conversation pane mounts the existing message list and composer inside the new shell (phase 3 owns one Message and one Composer). Dev-only items (the lab) are excluded from production builds.
- **Backend added for it.** Migrations `0044_thread_prefs` (`ln_thread_prefs`: read cursor, marked unread, mute, archive, favourite, pin order, the «مسح» cursor; `ln_agents.template` backfilled) and `0045_chat_lists` (`ln_chat_lists`, `ln_chat_list_members`, the pg_trgm index on Arabic-folded message text). Routes: `GET /api/threads/inbox` (the per-owner projection with `last_message`, `consumed` and the preference fields), `POST /api/threads/{id}/read`, `POST /api/threads/read-all`, `PATCH /api/threads/{id}/prefs`, `POST /api/threads/prefs`, `POST /api/threads/{id}/clear`, `GET`/`PUT /api/threads/settings`, `GET /api/threads/{id}/messages?around=`, `GET`/`POST /api/chat-lists`, `PUT`/`DELETE /api/chat-lists/{id}`, `PUT /api/chat-lists/{id}/members`, `GET /api/search` (WP-C), `POST /api/agents/create` (the `agent_create` input; template persisted, Q9), `POST /api/groups/create` with `purpose` and `lead_agent_id` (Q8), `GET /api/version` with the build id. Events `thread.read`, `thread.prefs_updated`, `chat_list.updated`; the keep-archived rule runs as the gateway step over `message.created`.
- **Side-by-side fixes (2026-11-09).** All eighteen findings of the side-by-side check were verified against `Lonora-Desktop-37.html` and applied, except where a phase boundary is noted below: no agent can be deleted from Web or Mobile any more (Q1; `DELETE /api/agents/{id}` and `DELETE /api/threads/{id}` lost their last clients); one `.app-shell` scope now holds the chrome and what the providers float above it (sheets, toast, menus), the shell's element defaults have zero specificity as in the reference, and the legacy element and component styles reach only screens outside the shell or inside `.legacy-surface`; `lists.css` loads after `shell.css`; bare pages keep their top inset; the list orders by the latest visible message, a chat with nothing said sorts last and a message written on this device lifts its chat at once (`@lonora/core` `chatRows`, the owner search's chat feed likewise); the group avatar is the reference's three-face cluster inside the slot; names and previews isolate with `<bdi>` without leaving the row's alignment; the welcome list is 360px with the reference's 22px mark; «إدارة الوكلاء» is in the new-chat sheet and the list menu, the personal agent's role reads «مساعدك الشخصي»; «وكيل جديد» posts `POST /api/agents/create` with the template and the web UI no longer posts `POST /api/agents`; search snippets follow the reference's 145-character window, knowledge hits are titled by their section heading in plain text (never a file name) and chat hits show the pair; the heads-up respects the owner's quiet hours; unread names are bold, the selection toolbar and the desktop filters have the reference's spacing, chips, rows and fields have their transitions; the desktop modal is as tall as the reference's (`min(88dvh, 780px)`) and sits above an on-screen keyboard; the unused `.tpl-inbox` rules, `AttentionCount` and the two delete hooks are gone. Because the owner's form now runs the `agent_create` service, its cap of 20 active agents no longer applies to the owner's own form (it never did on `POST /api/agents`); runs and cards keep it. Motion now runs on transform, opacity and clip-path only (`apps/web/src/shell/flip.ts`): the tab bar, the chats header, the desktop list, the sheet page morph and the expandable detent change their boxes at once and travel with transforms; the lens stretches with `scaleX`; the skeleton shimmer is a moving layer.
- **Side-by-side result** (`tests/ui-reference/side-by-side.mjs`, fresh `*_ci` database, mismatch % before → after the fixes; phone dark, phone light, desktop dark, desktop light):

| State | 390x844 dark | 390x844 light | 1280x800 dark | 1280x800 light |
| --- | --- | --- | --- | --- |
| `chats-rest` | 6.77 → 1.21 | 6.85 → 1.18 | 3.66 → 0.61 | 4.08 → 0.6 |
| `filters-revealed` | 6.78 → 1.26 | 6.86 → 1.23 | 3.66 → 0.63 | 4.08 → 0.62 |
| `archived` | 4.4 → 0.24 | 4.52 → 0.23 | 3.22 → 0.41 | 3.37 → 0.4 |
| `selection-2` | 7.05 → 1.13 | 7.12 → 1.11 | 3.59 → 0.59 | 4.01 → 0.58 |
| `custom-list` | 3.55 → 1.08 | 3.65 → 1.09 | 2.52 → 0.59 | 2.89 → 0.58 |
| `search-browse` | 5.43 → 5.03 | 5.46 → 5.06 | 3.82 → 0.62 | 4.24 → 0.61 |
| `search-results` | 1.91 → 1 | 1.87 → 0.94 | 1.88 → 0.54 | 2.2 → 0.53 |
| `sheet-new-chat` | 8.66 → 1 | 17.25 → 0.98 | 4.27 → 0.42 | 7.15 → 0.41 |
| `sheet-detent-rest` | 8.59 → 8.62 | 11.44 → 11.46 | 3.63 → 2.11 | 9.95 → 8.21 |
| `sheet-detent-expanded` | 6.78 → 6.77 | 6.88 → 6.87 | 3.67 → 3.66 | 3.77 → 3.76 |
| `new-list-keyboard` | 2.48 → 0 | 2.28 → 0 | 6.85 → 0.08 | 13.61 → 0.09 |
| `offline-queued` | 4.6 → 4.59 | 4.92 → 4.91 | 4.22 → 2.07 | 4.54 → 2.29 |
| `update-bar` | 6.78 → 1.23 | 6.86 → 1.21 | 3.66 → 0.62 | 4.08 → 0.61 |
| `not-found` | 8.79 → 0.21 | 9.24 → 0.21 | 4.5 → 0.48 | 4.65 → 0.47 |
| `chats-scrolled` | 13.29 → 2.38 | 13.76 → 2.31 | 4.37 → 0.94 | 4.69 → 0.92 |

  `chats-scrolled` and `filters-revealed` come from a re-run after the tab bar's fold stopped re-measuring the bottom inset, and `search-browse`, `search-results` and `sheet-new-chat` from a re-run after the chat search's order change; the other 36 pairs from the full run, which also ran the bindings pass. The bindings pass reports 0 step errors, no DELETE of an agent, group or thread, and the group kept after «حذف». Mean mismatch over the 60 pairs: 5.66% → 1.83%.
- **Remaining deviations from the reference, and why.**
  - The welcome greeting uses the e-mail's local part: the owner's name and form of address arrive with the phase 5 owner form (WP-H).
  - The conversation pane (`offline-queued`: message list, composer, wallpaper, the chat ⋮ menu as a sheet rather than the reference's popover, its «مسح المحادثة» entry) is phase 3; the market chart inside the expandable sheet (`sheet-detent-*`) is phase 4, and the seeded owner has no chart data, so the app shows its real empty state where the reference draws demo candles.
  - Data-only: the reference's «المستجدات» dot and «جديد» come from a seeded notification the API cannot create; tasks, files and knowledge are not seeded (creating a task starts a run), so `search-browse` at 390px shows fewer sections; operating notes the server wrote in English show as written in knowledge hits.
  - Motion: during the 200–340ms morphs the scaled glass pill and search field stretch their corners, the desktop list fades and slides out before the content pane widens, the expandable chart sheet is laid out at full height while it moves and re-lays out at rest, and the desktop modal's page change has no height motion (its pages slide). The end states match the reference.
  - The probe reads `nav`'s own box: its glass, border and shadow are now on `nav::before`, so the probe reports them missing on `nav` although the pixels match.
  - A chat whose history was hidden sorts as one with no message (the reference keeps its place after «مسح الرسائل» and drops it after «حذف»; the server has one cursor for both, Q1).
  - «وكيل جديد»: the «الإشراف على وكلاء آخرين» switch, the model choice and the agent page it lands on are phase 4 (`agent.new.templates`); the general template starts at «دون تنفيذ», the backend's template level (a money-safety invariant), where the reference says «تنفيذ بموافقة»; the trading template asks for the account and pair from the broker catalog instead of preselecting XAUUSD. Rows of the agents page open the conversation until the agent and group pages exist (phase 4). Field errors (`.field-err`) arrive with the phase 4 and 5 forms. Mobile's own new-agent screen still posts `POST /api/agents` (no template) until the mobile port.
- **Verification** (worktree `wt-ui2`, each database fresh):

| Check | Result |
| --- | --- |
| `ruff check .` / `ruff format --check .` | All checks passed; 1075 files already formatted. |
| `pyright` | 0 errors, 0 warnings. |
| `env -u AI_AGENT -u CLAUDECODE pnpm lint` | exit 0 (76 warnings, all pre-existing kinds; no errors). |
| `pnpm check` | 7 of 7 tasks, including `@lonora/mobile` (tsc). |
| `pnpm build` | 7 of 7 tasks. |
| `pnpm --filter @lonora/web i18n` | 1049 messages; Arabic 0 missing. |
| `tsx --test` (the CI list of `tests/web/*.test.ts`) | 98 of 100 pass; `chat-rows.test.ts` covers the new order, the outbox lift and quiet hours. The two failures read source files that `241b072` removed (`apps/web/src/pages/Shell.tsx` in `agent-create.test.ts:289`, `pages/shell/sidebar-activity.tsx` in `one-vocabulary.test.ts:56`) and fail on the branch before this work too. |
| `pytest tests -q` (fresh `lonora_ui2fix_pytest_test`) | 2084 passed, 5 skipped (APK), 0 failed. |
| Check scripts (each on its own fresh `*_test` database) | `check_thread_preferences`, `check_team`, `check_agent_create`, `check_personal_agent`: PASS. `check_team` read the old owner-search shape and failed since `deec2c2`; it now reads the categories. |
| Playwright `test:web` (system Chrome, fresh `*_ci` database) | 132 passed, 7 failed: exactly the baseline (`agent-permissions:391`, `group-status:14`, `skills-management:121`, `visual-response:64` in all four variants). The new `agents-entry` specs pass; the creation specs (`avatar-studio`, `flexible-agents`, `rakazo-parity`, `workspace:241`), `inbox:6` and `shell:84` were updated for the template creation, the reference's order and leftover badges. `avatar:110` and `inbox:123` (the former `inbox:120`) passed. |
| `tests/ui-reference/side-by-side.mjs` | See the table above; bindings 0 step errors, no forbidden DELETE. |

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
- **Deferred from the Wave 1.5 review.**
  - Check the Telegram sender (`message.from.id`) against a Telegram user id the owner configures, not only the chat id, and give channel-delivered messages their own trigger, so a group member never speaks for the owner.
  - Project decision cards (grant, trust, credential, create agent, supervise, model, limits; not Undo notices) into attention items, and withdraw them when the card settles.
  - Undo-only kinds (`agent_created`, `supervision_created`, `agent_model_changed`) as a compact one-line confirmation with an inline Undo, through the shared card spec.
  - The owner profile and memory revisions with per-change Undo on Mobile.

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
