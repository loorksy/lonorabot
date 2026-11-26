# Lonora roadmap from the eight gap analyses

Audience: Lonora developers. Lonora was read at `main` `d8193b98` (`/home/user/wt-agent/fxmain`, read only).
Inputs: `gap-{proactive,multiagent,memory,framework,ui,evals,loop,tools}.md` in this folder, and the reference reports
they cite. Binding texts: `VISION.md` (section 6 is never weakened; Amendments 1-3), plus Amendment 4 as recorded in
`/home/user/wt-agent/fxauth/docs/proposals/model-catalog-and-chatgpt-signin.md`.

Method:
1. I collected every adopt/adapt recommendation and merged duplicates across topics into 84 items.
2. Every item was checked against four rules: no weakening of section 6, no Stop control, no venue beyond MT5, and no
   other harness as Lonora's engine. None failed (see "Dropped and why").
3. I re-verified every P1 claim in the code (section "P1 verification", with `file:line`).
4. I ranked the items and grouped them into batches.

Tiers:
- **P1:** a correctness or reliability bug the owner would hit: lost events, duplicate runs, silent failures, first-run
  failure, or a mobile parity gap on something the owner must see.
- **P2:** a capability gap that matters for an always-on trading assistant.
- **P3:** nice to have.

Within a tier, items are ordered by value over effort.

Effort: **S** up to 2 developer-days, **M** 3 to 5 days, **L** 1 to 3 weeks. The reports used slightly different
scales; I normalized them to this one.

## Top table

The four rows marked "in progress" are already decided and being built. They are listed only so the touch points are
visible, and they are not planned again here.

| ID | Title | Tier | Effort | Batch | Needs owner? |
|---|---|---|---|---|---|
| IP-1 | Fixed model list from Rakazo (`models.json` from pi-ai 1.6.0) | in progress | - | - | decided |
| IP-2 | OpenAI Responses adapter | in progress | - | - | decided |
| IP-3 | Sign in with ChatGPT (official flow, Secret-card variant; no Claude subscription) | in progress | - | - | decided |
| IP-4 | Lonora Cloud provisioning (one server per customer from a prebuilt Hetzner snapshot, all on Hetzner) | in progress | - | - | decided |
| P1-01 | Skip a routine tick while an earlier run of that routine is unfinished; count the skips | P1 | S | B1 | no |
| P1-02 | Scan third-party tool results for stored secret values, and mark them as data | P1 | S | B2 | no |
| P1-03 | Unique, non-empty tool-call ids within a run | P1 | S | B2 | no |
| P1-04 | Visible heartbeat and client idle timeout on SSE and the mobile WebSocket | P1 | S | B3 | no |
| P1-05 | Agent-to-agent exchanges on mobile (peer card, as on web) | P1 | S | B4 | no |
| P1-06 | Detect and restart a wedged Gateway from outside it, and tell the owner | P1 | M | B5 | push only (D1) |
| P1-07 | First run needs no model: server greeting, model-key Secret card, Mandate card | P1 | M | B9 | no |
| P1-08 | Owner-only model failures of background work raise one item; failing routines are held | P1 | M | B7 | push only (D1) |
| P1-09 | One continuation per finished requester (peer fan-in) | P1 | M | B8 | no |
| P1-10 | Drain at a step boundary, within one deadline below the stop grace | P1 | M | B6 | no |
| P2-01 | One gate script mirrored by CI, covering all 11 core tests of 14.1.2 | P2 | M | B0 | no |
| P2-02 | Show the real host of agent-written links | P2 | S | B11 | no |
| P2-03 | Tell a late routine run that it is late, with the collapsed count | P2 | S | B1 | no |
| P2-04 | Alarm on owner and broker-event runs left queued | P2 | S | B5 | no |
| P2-05 | Index the agent's whole-history search, with the owner search's Arabic folding | P2 | S | B12 | no |
| P2-06 | Live eval scripts refuse to run on a hosted installation | P2 | S | B13 | no |
| P2-07 | Financial invariants as hard checks on every eval trial | P2 | S | B13 | no |
| P2-08 | Reuse the provider cache on every call of a run | P2 | M | B14 | no |
| P2-09 | Declared registry of owner-words-gated tools, with a coverage test | P2 | M | B10 | no |
| P2-10 | Expire stream events of finished runs; `resumed:false` for a cursor older than the log | P2 | M | B15 | no |
| P2-11 | "Your standing work" section on every wake | P2 | S | B16 | no |
| P2-12 | Coalesce `lonora wake` calls that have not started yet | P2 | S | B16 | no |
| P2-13 | Notice a cancelled run within about 2 s | P2 | S | B6 | no |
| P2-14 | Record what ended a Trade Approval card | P2 | S | B26 | no |
| P2-15 | Deep link in every Telegram alert | P2 | S | B11 | no |
| P2-16 | Strict `ScriptedModelAdapter` (`expect`, `assert_complete`) | P2 | S | B13 | no |
| P2-17 | A routine set in a chat names that chat | P2 | S | B16 | no |
| P2-18 | `session_search` time windows and an honest miss text | P2 | S | B12 | no |
| P2-19 | Do not recall memory that is already loaded whole | P2 | S | B22 | no |
| P2-20 | "You said" profile lines need a quote of the owner's own words | P2 | S | B17 | no |
| P2-21 | An observation the owner removed is never learned again | P2 | S | B17 | no |
| P2-22 | Redaction and leak scan for fixtures taken from real conversations | P2 | S | B13 | Cloud export only (D2) |
| P2-23 | Re-baseline the live eval for Full/Ask | P2 | M | B18 | no |
| P2-24 | Golden decision table for the execution door | P2 | M | B19 | no |
| P2-25 | Proactive behaviour bank with offline twins | P2 | M | B25 | no |
| P2-26 | Model-free `feed` watch kind | P2 | M | B21 | no |
| P2-27 | One transition gate for every run status write, plus invariant tests | P2 | M | B19 | no |
| P2-28 | One Gateway per installation by Postgres lock, with immediate recovery | P2 | M | B20 | no |
| P2-29 | Claim by wake priority and run age; a worker-count setting of its own | P2 | M | B20 | no |
| P2-30 | Dated memory entries with an end | P2 | M | B22 | no |
| P2-31 | Coalesce watch confirmations into a queued wake | P2 | M | B21 | no |
| P2-32 | Peer outcomes carry the child run's journal operations | P2 | M | B23 | no |
| P2-33 | The requester learns that the child waits on the owner | P2 | M | B23 | no |
| P2-34 | One-way peer notices; an empty outcome wakes no one | P2 | M | B23 | no |
| P2-35 | Market-hours gate on routines, chosen by the agent | P2 | M | B24 | no |
| P2-36 | Weekly memory upkeep inside the weekly-report run | P2 | M | B30 | no |
| P2-37 | Agent-to-agent behaviour bank | P2 | M | B25 | no |
| P2-38 | Live trials reported as k/N, a spend guard on the developer key, a strict compare | P2 | M | B18 | no |
| P2-39 | Generated TS wire types and server-made event fixtures | P2 | M | B27 | no |
| P2-40 | Release only a gated commit | P2 | M | O1 | yes (D5) |
| P2-41 | One shared thread reducer and subscription loop; one mobile socket | P2 | L | B28 | no |
| P2-42 | Web live deltas out of the root React context | P2 | M | B28 | no |
| P2-43 | MCP OAuth sign-in and several protocol revisions | P2 | L | B29 | card kind (D3) |
| P2-44 | Trusted MCP tools through the tool bridge | P2 | M | O2 | yes (D6) |
| P2-45 | Label memory revisions written after reading outside content | P2 | M | O3 | yes (D7) |
| P2-46 | Volatile context after the transcript | P2 | L | B31 | no |
| P2-47 | Owner-connected alert sources (TradingView or Pine alerts) | P2 | L | O4 | yes (D8) |
| P2-48 | Seal Secret card values in the app to the installation's key | P2 | L | O5 | yes (D9) |
| P3-01 | Retry a run's final commit on a transient database error | P3 | S | B6 | no |
| P3-02 | Pin MCP and OAuth connections to the address that passed validation | P3 | S | B29 | no |
| P3-03 | Prompt version and tool-schema hash on every run | P3 | S | B18 | no |
| P3-04 | Show a provider retry on the status line before the router sleeps | P3 | S | B32 | no |
| P3-05 | @mention: the longest name wins; a name several agents share wakes none | P3 | S | B23 | no |
| P3-06 | The same peer request under the same parent returns the existing run | P3 | S | B8 | no |
| P3-07 | Routine `ends_at`; the last run is told it is the last | P3 | S | B24 | no |
| P3-08 | Show memory budgets and omissions to the model | P3 | S | B22 | no |
| P3-09 | Recent-work brief of team agents for Lonora's runs | P3 | S | B16 | no |
| P3-10 | A short server-composed target on live steps | P3 | S | B32 | no |
| P3-11 | Model cost per run in routine history (a view, never a meter) | P3 | S | B24 | no |
| P3-12 | Failure categories on live eval records | P3 | S | B18 | no |
| P3-13 | Scratchpad item states (open, parked, done) | P3 | S | B22 | no |
| P3-14 | Delegation limits in one module | P3 | S | B23 | no |
| P3-15 | Silent-ending sentinel, only if a provider is measured to need it | P3 | S | B33 | no |
| P3-16 | Method and skill review in the weekly run | P3 | M | B30 | no |
| P3-17 | `LISTEN/NOTIFY` wake-up latch and one cursor publisher | P3 | M | B34 | no |
| P3-18 | Loopback model emulator for trading journeys | P3 | M | B35 | no |
| P3-19 | Per-model qualification report, for information only | P3 | M | B33 | customer view only (D4) |
| P3-20 | Optional meaning judge for the wording checks | P3 | M | B33 | no |
| P3-21 | Framework counters for the Lonora Cloud host agent | P3 | M | O6 | yes (D10) |
| P3-22 | Two-way Telegram | P3 | M | O7 | yes (D11) |
| P3-23 | Numeric runaway guard for unattended roots | P3 | M | O8 | yes (D12) |
| P3-24 | Weekly exploratory QA of the web and Android clients | P3 | M | O9 | yes (D13) |
| P3-25 | Simulated owner for the section 16 live run | P3 | L | B35 | no |
| P3-26 | Supervised stdio MCP host in the workspace | P3 | L | O10 | yes (D6) |

How the in-progress work touches this roadmap:
- **IP-1 (the model list)** changes `core/model_pricing.py`, and B14 rebases on it, because cache-write prices come from
  the list. B18 and B33 pick their evaluation models from the list.
- **IP-2 (the Responses adapter)** is where the OpenAI half of P2-08 (`prompt_cache_key`) belongs. P1-03 fixes call ids
  in the loop, so it covers the new adapter's `call_id`s too.
- **IP-3 (ChatGPT sign-in)** adds the Secret-card variant that B9 builds on. B7 must map its error codes (spec 4.8), and
  B29 reuses its sign-in card pattern.
- **IP-4 (Cloud provisioning)** must bake the compose and systemd changes from B5 and B6 into its snapshot. B9 is the
  first run of every provisioned server, B13 needs its hosted marker, and O5 and O6 depend on its edge and host-agent
  design.

## Delivery order

| Wave | Batches | Gate to start |
|---|---|---|
| 1 | B0 | none |
| 2 (P1, in parallel) | B1, B2, B3, B4, B5, B8 | B0 |
| 3 | B6 (after B5), B7 (after B1), B9 (after B4 and IP-3), B10, B11, B12, B13 | as listed |
| 4 | B14 (after IP-1 and IP-2), B15 (after B3), B16 (after B1), B17, B18 (after B13), B19 (after B6, B7, B8), B27 | as listed |
| 5 | B20, B21, B22, B23, B24, B25, B26, B28, B29 | see each batch |
| 6 | B30, B31, B32, B33, B34, B35; O1-O10 once decided | see each batch |

Coordination with the mandate phases (VISION 15):
- **Phase 2 (mobile GenUI v2 renderer)** shares `message-bubble.tsx` and `thread.tsx` with B4 and B28.
- **Phase 3 (trading authority and the 14.3.5 move of the provenance helpers):** B10 should land before that move,
  and B17, B19 and B26 rebase on it.
- **Phase 5 (rewrite of `lonora.md` and the weekly report):** B22, B23 and B30 edit `lonora.md`, which means
  regenerating `manifest.json` (5.8.6).

## P1 verification

I checked each claim by reading the code. All ten P1 defects reproduce; no P1 claim was dropped. The sub-claims I
could not confirm are listed in "Dropped and why", and no fix depends on them.

| P1 | Claim | Evidence | Result |
|---|---|---|---|
| P1-01 | A due routine always creates a run, even while an earlier run of it is queued or running, so later ticks pile up | `packages/db/src/lonora_db/routines.py:83-94` (`due_query` checks enabled, due, agent unpaused and one-shot state only); `routines.py:141-155` (`create_run` with no check); `packages/contracts/src/lonora_contracts/routines.py:11` (`interval_seconds ... ge=60`); `packages/db/src/lonora_db/runs.py:287-290` (one leased or running run per thread, so later ticks wait behind it) | Confirmed |
| P1-02 | MCP and other third-party results reach the model and the stored receipts with stored secret values unscanned | `packages/tools/src/lonora_tools/mcp.py:448-451` (raw result), `mcp.py:455-458` (raw result written to `EffectReceiptRow`); `packages/tools/src/lonora_tools/registry.py:555-560` (marks external content but does not scan); `owner_scan` is called only at `terminal.py:86`, `artifacts.py:250`, `apps/api/src/lonora_api/cli/app.py:139` and `packages/gateway/src/lonora_gateway/service.py:396`; `packages/security/src/lonora_security/secrets.py:16-26` (`redact` matches key names and `Bearer` only) | Confirmed. The tools report gave no tier; this is P1 because of the MUST NOT in 7.2.6 |
| P1-03 | Provider tool-call ids are used verbatim, so an empty or repeated id collides receipts and Trade Approval ids | `packages/adapters/src/lonora_adapters/models/openai_compatible.py:209-213` (the id starts as `""` and fragments are concatenated), `:230-234` (copied into `ToolCall`); `packages/tools/src/lonora_tools/tool_results.py:24-25`; `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:43-55` (the stored receipt is returned); `packages/tools/src/lonora_tools/trade.py:408,847,900` (the approval id is derived from the call id); `packages/tools/src/lonora_tools/context.py:56-61` | Code path confirmed. Whether a current provider emits such ids was not reproduced |
| P1-04 | The SSE keepalive is invisible to `EventSource`, the WebSocket sends none, and neither client detects a silent connection after `ready` | `apps/api/src/lonora_api/routes/events.py:76-78` (`": keepalive"` is an SSE comment); no ping in `apps/api/src/lonora_api/websocket/events.py`; `apps/web/src/lib/events.ts:57,66` (startup timer, cleared on `ready`); `apps/mobile/lib/events.ts:32` (readiness timer only) | Confirmed |
| P1-05 | Mobile shows a peer exchange as an unattributed message | `apps/mobile/components/message-bubble.tsx:258` (renders the outcome body only); no `peer-messages` reference anywhere in `apps/mobile`; web fetches them at `apps/web/src/conversation/Conversation.tsx:207` and draws `PeerCard` at `Cards.tsx:549` | Confirmed |
| P1-06 | Nothing restarts a wedged Gateway, and nothing tells the owner | `infra/compose/docker-compose.prod.yml:76-98` (no `healthcheck` on `gateway`, while db :28, api :57, searxng :111, browser :139 and workspace-net :178 have one); `apps/worker/src/lonora_worker/main.py:11-23` (no stall guard, and no `faulthandler` or `os._exit` anywhere in `apps/worker` or `packages/gateway`); no client reads `/ready`; `packages/db/src/lonora_db/trading_readiness.py` never reads the heartbeat; `infra/systemd/lonora-gateway.service:11` (`Restart=on-failure`, which fires only on exit) | Confirmed |
| P1-07 | A new owner's first message fails, and chat offers no way to enter the first model key | `packages/db/src/lonora_db/personal_agent.py:41-49` (raises only the Mandate card); `packages/providers/src/lonora_providers/router.py:212` (`model_not_configured`); `apps/web/src/conversation/Cards.tsx:69-92` (the error card says "Open model settings") | Confirmed |
| P1-08 | A background run that fails on a rejected key, spent credit or unknown model raises nothing, and every later tick fails the same way | `packages/providers/src/lonora_providers/resilience.py:76-79,89` (`transient=False`); `packages/agent-runtime/src/lonora_agent/model_recovery.py:174-175` (`raise`); `packages/core/src/lonora_core/attention.py:43-61` (no `run.failed` branch; the default is `silent`); `packages/gateway/src/lonora_gateway/attention.py:144-187` (`projected` maps only broker, opportunity and watch wakes, and otherwise returns the event unchanged) | Confirmed |
| P1-09 | Each child returning to a completed parent starts its own follow-up | `packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:228-258` (no lookup of an existing queued follow-up of the same parent) | Confirmed |
| P1-10 | Shutdown cancels turns wherever they are, and the two waits exceed the stop grace | `packages/gateway/src/lonora_gateway/shutdown.py:8-14` (waits 25 s, then cancels); `service.py:156` (stop is checked only before a claim); `service.py:511-515` (run drain, then relay drain with `RELAY_DRAIN_SECONDS = 30` from `:44`, then `release_leases`); `docker-compose.prod.yml:96` and `lonora-gateway.service:13` (40 s grace); nothing under `packages/agent-runtime/src` reads a drain signal | Confirmed. P2 in the framework report and rank 2 in the loop report; P1 here because every update and every quiesce creates uncertain results and Settle cards |

Seven source P1s are confirmed in the code but moved to P2, because none of them is a bug the owner hits:

| Source P1 | Now | Evidence | Why not P1 |
|---|---|---|---|
| multi-agent 2, peer outcome evidence | P2-32 | `outcome_return.py:194` (the outcome is text only) | `packages/agent-runtime/src/lonora_agent/context/picture.py:139` (`team_book`) already gives every wake the team's broker tickets, so this is a capability gap |
| memory R1, cache reuse | P2-08 | `packages/db/src/lonora_db/agent_state.py:614` (`observed_at=utcnow()`); `context/team.py:88` (the exclude set lacks it); `model_runtime.py:67` (refreshed on every call); `anthropic.py:20-25` (every system message hoisted), `:84` (one breakpoint); `packages/core/src/lonora_core/model_pricing.py:16`; no `prompt_cache_key` anywhere in `packages/` | It costs money on the owner's key; it is not a correctness bug |
| UI R2, shared reducer | P2-41 | 37 files under `apps/web/src` use `revision` (`apps/web/src/hooks/useEvents.ts:7,16`) | Architecture work. The parity gap the owner sees is P1-05 |
| evals 1, the gate | P2-01 | `.github/workflows/ci.yml:828-851`; `docs/handoff/CURSOR_HANDOFF.md:60` ("CI does NOT run"); six of the eleven 14.1.2 core tests appear neither in `ci.yml` nor in `tests/run_foundation_checks.py` | A process gap. It still runs first, as B0 |
| evals 2, gated release | P2-40 | `scripts/release_manifest.py:44` (records the commit and migration head only) | A process gap, and it needs the owner |
| evals 3, re-baseline | P2-23 | `scripts/agent_eval/bank.py:158,170,188` (grant route and `sign_grant`); `acceptance.py:1252` (`set_trading_mode`); `docs/agent-eval.md:1`; `tests/fixtures/agent_eval/BASELINE.json:5` (recorded 2026-11-11) | Developer tooling |
| evals 4, invariants | P2-07 | no invariant, duplicate or resend check in `scripts/agent_eval/score.py` (grep) | Developer tooling |

## Batches

Each batch is one branch and one PR on top of the latest `main`. "Depends on" means rebase on, or wait for, that work.

### B0. One gate
**Items:** P2-01. **Effort:** M. **Depends on:** nothing. **Owner:** no. Whether CI must also pass before a release is
O1.

**Why first.** VISION 14.1.2 says the eleven core tests MUST pass after every step. Six of them appear neither in
`ci.yml` nor in `tests/run_foundation_checks.py`: `test_broker_effect_verification.py`, `test_execution_records.py`,
`test_preflight_identity.py`, `test_metaapi_reconciliation_history.py`, `test_tool_execution_core.py` and
`test_financial_admission.py`. CI does not run at all (`CURSOR_HANDOFF.md:60`), and every later batch adds tests that
need a gate.

**Change.**
- `scripts/gate.sh` does exactly what `CURSOR_HANDOFF.md` section 3 lists:
  - migrate a fresh database;
  - run the full `pytest tests`;
  - run `tests/run_foundation_checks.py --isolated-databases` and `scripts/agent_eval/acceptance.py --offline`;
  - run `scripts/build.sh` and the i18n and manifest checks;
  - run the web and mobile Playwright suites.
- `ci.yml` calls this script instead of its hand-picked list, and its Fernet fixture is fixed.

**Files.** New `scripts/gate.sh`, `.github/workflows/ci.yml`, `docs/handoff/CURSOR_HANDOFF.md`.

**Tests to add.** A test that the gate's list names every 14.1.2 file, so it fails if one is dropped.

**VISION.** 14.1.1, 14.1.2, and 6.1-6.9, whose tests then run on every change.

### B1. Routine runs: no stacking, honest lateness
**Items:** P1-01, P2-03. **Effort:** S + S. **Depends on:** B0. **Owner:** no.

**Change.**
- In `enqueue_routine`, check the routine's own work thread (`thread_id = row.thread_id`, `trigger = "routine"`):
  - If a run there is `queued`, `leased` or `running`, advance `next_run_at`, create no run, and count the skip.
  - A run in retry backoff is `queued`, so it blocks. This covers the model-outage case from the loop report.
  - A run in `waiting_input` does not block: an unanswered question must not stop the schedule.
- The next run carries `scheduled_for`, `missed_occurrences` (from the existing collapse) and `skipped_occurrences`
  (from overlap) in server-only metadata. Add these keys to the server-only list in `runs.py`, which `create_run`
  strips from callers.
- `context/routine.py` adds one fixed server sentence when a run starts more than 15 minutes after `scheduled_for`: the
  due time, the start time, the missed count, and "re-check what changed".
- `routine_history` shows the skipped counts.

**Files.** `packages/db/src/lonora_db/routines.py`, `packages/db/src/lonora_db/runs.py`,
`packages/agent-runtime/src/lonora_agent/context/routine.py`, `packages/automation/src/lonora_automation/delivery.py`,
`docs/proactivity.md`.

**Tests to add** (new `tests/test_routine_overlap.py`):
- A 60 s routine whose first run is held `running`: three dispatch passes leave one run, and the next run carries
  `skipped_occurrences = 2`.
- First run in retry backoff: still one run after five minutes.
- First run in `waiting_input`: a new run is created.
- A one-shot routine is unaffected.
- A routine due 3 hours ago gets the late sentence and `missed_occurrences`; one due 1 minute ago gets no sentence.
- `tests/test_background_silence.py` passes unchanged.

**VISION.** 11.5, 11.6, 17, P6; 5.2 and 5.4 (timing in the picture); 6.10 (fixed server text); Amendment 3.9; D11.
This is not a cap under P1: the routine still fires on its schedule once the earlier tick has ended.

### B2. The tool path: secrets out of third-party results, unique call ids
**Items:** P1-02, P1-03. **Effort:** S + S. **Depends on:** B0. **Owner:** no.

**Change (P1-02).**
- In `ToolRegistry.execute` (`registry.py:529-561`), when `returns_external_content(call.name)` is true:
  - pass the result through `owner_scan(context.secrets, context.workspace_given, context.cli_tokens).data(result)`,
    before the external-content receipt and before the result is returned;
  - add `"_provenance": "third_party"` to the result.
- `mcp_execute` writes its at-most-once `EffectReceiptRow` with the raw result (`mcp.py:455-458`) before the registry
  sees it. Scan there as well, or write that receipt after the scan, so no stored receipt holds a secret value.
- Cache the secret read once per run.

**Change (P1-03).**
- After `model_turn` returns, and before the reply is appended and checkpointed (`tool_loop.py`, about lines 631-640,
  and the ignored calls in `finish_turn`, about 293-296), rewrite every call id that is empty, repeated within the
  reply, or already present in the run's transcript.
- The new id is `stable_id(run_id, f"call:{round}:{index}")`. Provider ids that are already unique stay untouched, so
  existing checkpoints and receipts still match. The original id goes into `provider_metadata`.
- Do it in the loop, not per adapter, so the Responses adapter (IP-2) is covered as well.

**Files.** `packages/tools/src/lonora_tools/registry.py`, `packages/tools/src/lonora_tools/mcp.py`,
`packages/tools/src/lonora_tools/terminal.py` (reuse `owner_scan`),
`packages/agent-runtime/src/lonora_agent/tool_loop.py` (or `model_runtime.py`).

**Tests to add.**
- A scripted MCP transport echoes its bearer token and the token's base64 form. The tool result, the stored tool result
  and the effect receipt all show `[secret:NAME]` (the test sentence of 7.2.6).
- A web-tool result carries `_provenance`.
- A fake adapter emits `""` and a repeated `call_0` across rounds. The second call executes, there is no
  `tool_result_identity_conflict`, and the transcript stays valid.
- Two `trade` calls in one run with the same provider id get different Trade Approval ids (`trade.py:408`).
- The 14.1.2 core tests pass.

**VISION.** 7.2.6 (MUST NOT) and 6.10. 6.2, 6.3, 5.3.3 and 17 are strengthened, and none of them changes.

### B3. An honest live connection
**Items:** P1-04. **Effort:** S. **Depends on:** B0. **Owner:** no.

**Change.**
- SSE: replace the `": keepalive"` comment with an `event: ping` frame with no `id:`, so `Last-Event-ID` never moves.
  Send it every 15 to 20 s.
- WebSocket: send `{"type":"ping"}` on the same period.
- Both clients: after 45 s with no frame at all, close and reconnect with the existing backoff.
- Mobile also reconnects on `NetInfo` and `AppState` changes.
- A ping never moves the cursor.

**Files.** `apps/api/src/lonora_api/routes/events.py`, `apps/api/src/lonora_api/websocket/events.py`,
`apps/web/src/lib/events.ts`, `apps/mobile/lib/events.ts`.

**Tests to add.**
- API, on both transports: pings arrive on schedule and carry no id.
- Web and Expo event specs: the server goes silent after `ready`, the client shows "Reconnecting" within 45 s, and it
  resumes from its cursor without duplicate events.

**VISION.** 10.3.1 (a drifted card must show as drifted), 11.4, 17 (the status line reflects what is really
happening), D36.

### B4. Mobile peer card
**Items:** P1-05. **Effort:** S. **Depends on:** B0. Coordinate with mandate phase 2, whose mobile v2 renderer also
edits `message-bubble.tsx`. **Owner:** no.

**Change.**
- Move `peersByMessage` and the peer-label logic from `apps/web/src/conversation/Cards.tsx` into `packages/core`, next
  to `peer-outcome.ts`.
- `apps/mobile/app/thread.tsx` fetches `/peer-messages?thread_id=`.
- New `apps/mobile/components/peer-card.tsx` draws the web frame: who asked whom, the status, and a link to the other
  conversation. `message-bubble.tsx` renders it for peer messages.

**Files.** As above, plus the mobile i18n catalog.

**Tests to add.**
- A core unit test of the shared logic, giving the same output for web and mobile.
- An Expo Playwright spec: a peer request and its outcome show A → B, the status and the link.
- The web peer-card spec passes unchanged.

**VISION.** 3.2.3, 3.1.5, 3.1.6, 13.1, Amendment 3.13, D36.

### B5. Gateway health seen from outside
**Items:** P1-06, P2-04. **Effort:** M + S. **Depends on:** B0. IP-4's snapshot must pick up the compose change.
**Owner:** D1 decides whether a stopped worker also sends a push.

**Change (P1-06).**
1. **Loop-stall guard.** A plain `threading.Thread`, started in `apps/worker/src/lonora_worker/main.py`, watches a
   timestamp the event loop updates every second. Past a limit (for example 120 s), it dumps the stacks with
   `faulthandler`, logs a stable code and calls `os._exit(70)`. Then `restart: unless-stopped` and `Restart=on-failure`
   bring the process back. A restart is safe: leases are fenced, and uncertain sends are reconciled and never resent
   (6.3).
2. **Container healthcheck.** The `gateway` service gets a `healthcheck` that reads a liveness file the heartbeat step
   writes.
3. **Owner-visible line.** The API, a separate process that is still alive, shows one honest line on web and mobile
   while no Gateway heartbeat is fresh (`gateway_health`). It goes in `trading_readiness.py` or in the attention view.

**Change (P2-04).** One new watchdog check:
- It looks for a run with trigger `user`, `group`, `broker_event` or a system-alert wake that has been due and
  unclaimed for more than 60 s.
- Such a run opens one `gateway_degraded` episode with reason `runs_delayed`. It uses the same episode and withdrawal
  mechanism as `overdue_wakes`.
- The check also logs `run.queue_delayed`, with counts and the oldest wait.
- The reason gets Arabic and English text.

**Files.** `apps/worker/src/lonora_worker/main.py`, `apps/worker/src/lonora_worker/health.py`,
`packages/gateway/src/lonora_gateway/{heartbeat,health,watchdog}.py`, `infra/compose/docker-compose.prod.yml`,
`infra/systemd/lonora-gateway.service`, `packages/db/src/lonora_db/trading_readiness.py`,
`apps/api/src/lonora_api/health.py`, the attention label catalogs (ar/en, web and mobile), `docs/gateway-reliability.md`,
`docs/operations.md`.

**Tests to add.**
- A subprocess blocks its loop with a 2 s limit: it exits with code 70 and writes the stacks.
- The `gateway` service has a healthcheck.
- API: a stale heartbeat shows the stopped-worker line, and a fresh one removes it.
- Watchdog: an owner-message run left queued for 61 s opens one episode, and the episode is withdrawn when the run is
  claimed.

**VISION.** P6, 3.1.5, 11.7, 17, and Amendment 3 (the host agent already reads service state). Section 6 is untouched.

### B6. Drain at a step boundary, prompt cancel, durable final commit
**Items:** P1-10, P2-13, P3-01. **Effort:** M + S + S. **Depends on:** B5 (same compose and systemd blocks), and a
rebase on B2 (`tool_loop.py`). **Owner:** no.

**Change (P1-10).**
- The Gateway sets a draining flag before `drain(loops)`, and `ToolContext` exposes it.
- The tool loop checks the flag at the top of each round (`tool_loop.py:435`), before each tool segment (`:483`), and
  before each model turn. When the flag is set:
  - the loop persists `environment.retry = {"not_before": now, "reason_code": "gateway_drained"}` and raises
    `ToolRetryScheduled`;
  - this is the path Task continuations already take (`continuation.py:86-90`), and `executor.py:298-341` requeues the
    run;
  - the fence and the checkpoint are kept, and the run is not counted as a recovery.
- A call that is already past `before_effect` is never interrupted. It ends within its own deadline.
- There is one shutdown deadline below the stop grace, and the run drain and the relay drain run at the same time.
  Today they run one after the other, and 25 s plus 30 s is more than the 40 s grace.
- The 25 s cancel stays as the backstop.

**Change (P2-13).** A watcher next to `keep_lease` reads `status` and `lease_fence` about every 2 s. When the fence has
moved, it calls the existing `lose()` (`executor.py:107-110`). Optionally, it waits while a call that is not read-only
is past `before_effect`.

**Change (P3-01).** Wrap the final writes (`complete_run`, the `waiting_input` write and the retry release) in the same
bounded retry for transient errors that `keep_lease` uses, while the lease is still valid.

**Files.** `packages/gateway/src/lonora_gateway/{service,shutdown}.py`,
`packages/agent-runtime/src/lonora_agent/{executor,tool_loop}.py`, `packages/tools/src/lonora_tools/context.py`,
`infra/compose/docker-compose.prod.yml` (`stop_grace_period`), `infra/systemd/lonora-gateway.service`
(`TimeoutStopSec`), `docs/gateway-reliability.md`.

**Tests to add.**
- A drain case in `tests/check_execution_recovery.py`: a run with a slow read tool gets the stop signal. It is requeued
  at a boundary with no uncertain marker, and the next claim continues from the same checkpoint.
- A financial call in flight at stop is journaled once and never resent.
- Shutdown finishes, and `release_leases` runs, inside the grace.
- A cancel during a long fake model call stops the run within 3 s, with no fenced write after the cancel.
- One injected transient error at `complete_run` leaves the run completed, not failed.

**VISION.** 6.3 and 6.8 (fewer uncertain operations; the rules themselves are unchanged), 6.9, 14.1.2, 17, Amendment
3.6 and 3.9, D11. The cancel serves 4.6, 4.7 and 7.1.5: it is the owner's cancel of work, not the Stop control that
Amendment 1 removed.

### B7. Owner-only model failures of background work
**Items:** P1-08. **Effort:** M. **Depends on:** B1. Coordinate with IP-3. **Owner:** D1 decides whether it also sends
a push.

**Change.**
1. **One attention item** (code `model_access_failed`) per provider route and cause:
   - It is raised when a background run fails with AUTH, BILLING, PERMISSION or MODEL_NOT_FOUND.
   - Its text is fixed server text: the provider's name and the failure family only, never the provider's message.
   - It is withdrawn when a run on that route succeeds, or when the credential changes.
   - Lonora cannot write this item, because Lonora's own model is what fails.
2. **Held routines.** While the item stands, due routines of agents whose every model candidate fails for that cause
   advance without a run and count as skipped, using B1's mechanism.
   - Saving a credential through `ProviderCredentials` releases them at once.
   - Watches keep evaluating without a model. Their confirmations already fall back to owner items through
     `projected`.
3. **No new push kind.**

**IP-3.** The ChatGPT plan's errors map onto the same reasons (spec 4.8: usage limit to billing, invalid user to auth),
so this item already covers them. Whichever of the two lands second makes the text say "ChatGPT plan" and releases the
hold on a new sign-in.

**Files.** `packages/agent-runtime/src/lonora_agent/model_recovery.py` (or the executor's failure path),
`packages/contracts/src/lonora_contracts/attention.py`, `packages/core/src/lonora_core/attention.py`,
`packages/db/src/lonora_db/{attention,routines}.py`, `packages/providers/src/lonora_providers/credentials.py`, the
attention labels (ar/en, web and mobile), `docs/proactivity.md`.

**Tests to add.** With a provider stub that answers 401:
- The first routine failure raises one item, and the next ticks create no run.
- Saving a key withdraws the item, and the routine fires on its next tick.
- An agent on a different, working provider keeps running.
- A 429, which is transient, raises no item.

**VISION.** 11.7; 11.5 (silence must never hide a failure only the owner can fix); P6; 12.1; D6 and D41. Nothing is
limited under P1: the held runs could not run.

### B8. Peer fan-in
**Items:** P1-09, P3-06. **Effort:** M + S. **Depends on:** B0. **Owner:** no.

**Change (P1-09).** In `return_outcome`, the branch for `parent.status == "completed"` changes:
- First, look for a queued, unstarted `follow_up` with the same `parent_run_id`. If there is one, attach the outcome to
  it: advance `input_seq`, or add a `SteeringRow`, as the `queued` branch already does.
- If that follow-up is running, steer it.
- Optionally, hold the first follow-up while sibling peer children of the same parent are still active. This is a
  fan-in, not a cap.
- The `peer_send` result gets one sentence: "the outcome returns here on its own; end your turn when nothing else needs
  doing".

**Change (P3-06).** A second `peer_send` with the same task to the same target, under the same parent run, while the
first is not terminal, returns the existing run with `duplicate: true`.

**Files.** `packages/agent-runtime/src/lonora_agent/collaboration/{outcome_return,peer_messages}.py`,
`packages/tools/src/lonora_tools/message.py`.

**Tests to add** (in `tests/check_runtime_collaboration.py`):
- Two children returning to a completed parent produce one follow-up, which sees both outcomes.
- A child returning while that follow-up runs steers it.
- A cancelled child starts nothing.
- Collaboration sessions behave as before.
- A duplicate request returns the first run.

**VISION.** 3.1.5, 11.5, 5.3.1.

### B9. A first run that needs no model
**Items:** P1-07. **Effort:** M. **Depends on:** IP-3 merged, because it changes the same card and the same files.
Rebase on B4 (`thread.tsx`, `Cards.tsx`), and verify on the first boot of a server provisioned by IP-4. **Owner:** no.

**Change.** In `ensure_personal_agent()`, or in the first owner session after it:
- Lonora posts one fixed greeting: catalog text, Arabic first, with no model call.
- The server raises a system Secret card with target `model_provider`:
  - its fields are set by the server (7.2.3);
  - it links to the provider's own key page, as the D41 guides describe;
  - it offers IP-3's "Continue with ChatGPT" variant where `LONORA_CHATGPT_SIGN_IN` is on.
- The existing Mandate card stays.
- Once the key is saved, the existing `secret_cards.py` wake hands over to Lonora, which then connects MT5 in chat (9.2).
- The `model_not_configured` error card points at that card in the conversation, not at a settings page.

**Files.** `packages/db/src/lonora_db/personal_agent.py`, `packages/db/src/lonora_db/owner_actions.py`
(`raise_system_card` for `secret`), `packages/db/src/lonora_db/secret_cards.py`, a greeting catalog
(`packages/bus/src/lonora_bus/attention_messages.json` or a new one), `apps/web/src/conversation/Cards.tsx`,
`apps/mobile/app/thread.tsx`, `apps/mobile/lib/i18n.ts`.

**Tests to add.**
- Onboarding creates the owner. Lonora's conversation then holds the greeting, the Secret card and the Mandate card,
  and the router was never called.
- Saving a key wakes Lonora once.
- Web and Expo first-run specs.
- The error card links to the Secret card.

**VISION.** P5, 4.3.1, 7.2.1-7.2.3, 12.1 (as amended by Amendment 4), 16.1, D41.

### B10. Declared owner-words gates
**Items:** P2-09. **Effort:** M. **Depends on:** B0. Land it before the 14.3.5 move of the provenance helpers (mandate
phases 3 and 6), so that the move is checked. **Owner:** no.

**Change.**
- Add `Tool.owner_words: Literal["none", "required", "conditional"]` and classify every tool.
- The checks stay in the handlers, because several are conditional. For example, `trade.py:1029` applies only to
  tickets the agent does not own.
- Classify according to the mandate's target state (14.3.5): Lonora's lead actions and its behavioural profile writes
  are not gated.

**Files.** `packages/tools/src/lonora_tools/{base,registry}.py`, each tool definition, and a new test next to
`tests/test_owner_intent.py`.

**Tests to add.**
- Every catalog tool is classified, in the style of `tests/test_context_engine.py:1296-1347`.
- For each `required` tool, a run that has an external-content receipt gets that tool's `*_requires_owner_message`
  refusal and causes no effect.

**VISION.** 6.10, 14.3.5, 14.1.1.

### B11. Links and Telegram alerts
**Items:** P2-02, P2-15. **Effort:** S + S. **Depends on:** B0. **Owner:** no.

**Change.**
- **Links.** For `[label](https://host/...)` where the label is not the host, show the host after the label, or ask
  once on tap ("Open broker-login.example?"). This applies on web and mobile; bare URLs are unchanged.
- **Telegram.** Each alert gets a link that opens the conversation at the card: the app scheme or the installation's
  web URL, with the same `thread_id` and `around` the push uses. The link only opens the fixed card, which reads the
  live record, and it carries nothing sensitive (the push rule).

**Files.** `apps/web/src/conversation/Markdown.tsx`, `packages/chat-ui/src/markdown.web.tsx`,
`apps/mobile/components/markdown.tsx`, `packages/gateway/src/lonora_gateway/event_dispatch.py`,
`packages/gateway/src/lonora_gateway/push.py` (`push_record`), the Expo linking handler.

**Tests to add.**
- Both renderers show the host for a disguised link and not for a bare one.
- Telegram dispatch: the outbound text carries the link with `thread_id` and `around`, and no price, volume or account
  number.

**VISION.** 6.10, 7.2, 9.2; 11.4.

### B12. History search that lasts
**Items:** P2-05, P2-18. **Effort:** S + S. **Depends on:** B0. **Owner:** no.

**Change.**
- **Index.** A migration adds a GIN index on the exact expression `full_text_statement` uses.
- **Arabic folding.** The agent's literal arm and `conversation.py` use the same folding as owner search (`folded_sql`,
  migration 0045). Today they fold diacritics only, not the alef, hamza and taa-marbuta variants.
- **Time windows.** `SessionSearchInput` gets `since` and `until` (ISO times, or `24h`, `3d`). With no query, it lists
  the scoped messages in the window, newest first, bounded like `read`.
- **Miss text.** "No message matched these words, which does not show it never happened."

**Files.** A new migration under `packages/db/migrations/versions/`,
`packages/memory/src/lonora_memory/{sessions,conversation}.py`, `packages/tools/src/lonora_tools/session_search.py`.

**Tests to add.**
- On 50,000 seeded messages, a whole-history query finds an old match without falling back to the 5,000-message window.
- Alef, hamza and taa-marbuta variants match.
- Window queries, and the miss text.

**VISION.** 3.1.5, 3.1.6, 11.1, P6, 13.1.

### B13. Eval hardening
**Items:** P2-16, P2-07, P2-06, P2-22. **Effort:** M in total. **Depends on:** B0, and on IP-4's hosted marker
(`LONORA_HOSTED_PORTAL_URL`, cloud task P1-T6, or whatever provisioning sets). **Owner:** only for the customer-export
part of P2-22 (D2). Without that export, no customer data ever becomes a fixture.

**Change.**
- **P2-16.** `ScriptedModelAdapter` gets an optional `expect(messages, tools)` per reply and `assert_complete()`. Fix,
  in the same PR, the latent slack this exposes in the `check_*` scripts.
- **P2-07.** `score.py` adds hard invariants, checked on every trial:
  - each terminal send matches exactly one journal reservation (6.2);
  - no second send for an operation whose outcome is unknown (6.3);
  - no new risk in Ask without the exact approved request (6.7);
  - no send on a ticket owned by another agent or by the owner (3.3.4);
  - nothing is called filled without a broker deal (6.4).
- **P2-06.** `scripts/verify_agent_journeys.py`, `run.py --live` and `acceptance.py --live` refuse to start on a hosted
  installation.
- **P2-22.** A leak scan over `tests/fixtures/agent_eval/**`, run by the gate:
  - it reports a category and a path only, never the matched text;
  - categories are MT5 logins, tickets, MetaApi ids, emails, URLs, absolute paths and key shapes;
  - an allowlist covers the values the self-hosting owner consented to.

**Files.** `packages/adapters/src/lonora_adapters/models/fake.py` and its callers,
`scripts/agent_eval/{score,runner,broker,acceptance,run}.py`, `scripts/verify_agent_journeys.py`, new
`scripts/agent_eval/redact.py`, `scripts/gate.sh`, `tests/test_agent_eval.py`.

**Tests to add.**
- Each invariant fails a crafted recording that breaks it, and the baseline still passes.
- Leftover scripted replies fail the run.
- With the hosted marker set, the live scripts exit before any request.
- The scan flags a planted ticket.

**VISION.** 6.1-6.4, 6.6, 6.7, 3.3.4, Amendment 2; Amendment 3.3, 3.4, 3.7; 7.2; 14.1.2.

### B14. Provider cache reuse
**Items:** P2-08. **Effort:** M. **Depends on:** IP-1 (pricing) and IP-2 (the OpenAI half). **Owner:** no.

**Change.**
1. **Routing frame.** Exclude `observed_at` from the model-facing `live_agent_state` dump (the exclude set at
   `team.py:88`), and give the current time in a trailing per-call note after the transcript, the way `model_runtime.py`
   already places the visual-capabilities block. The protected operational state and the permission frame stay on
   every call (5.8.7).
2. **Anthropic.**
   - Keep the policy breakpoint (`anthropic.py:84`) and add a rolling `cache_control` on the last content block.
   - Send runtime blocks appended after the transcript as a labelled user-role block
     (`context_origin="runtime_context"`), instead of hoisting them into `system` (`anthropic.py:20-25`).
3. **OpenRouter.** Add `cache_control` for `anthropic/*` models.
4. **Accounting.** Record `cache_creation_input_tokens`. Store each run's section names, sizes and shed list in
   `model_metadata`, for evals.
5. **OpenAI.** The `prompt_cache_key` is added in IP-2's Responses adapter, not here. Check whether the ChatGPT plan
   accepts it: that plan rejects `prompt_cache_retention`.

**Files.** `packages/agent-runtime/src/lonora_agent/context/team.py`,
`packages/agent-runtime/src/lonora_agent/model_runtime.py`, `packages/adapters/src/lonora_adapters/models/anthropic.py`,
`packages/adapters/src/lonora_adapters/models/openrouter.py`, `packages/llm-usage`,
`packages/core/src/lonora_core/model_pricing.py` (after IP-1).

**Tests to add.**
- Golden test: two consecutive Anthropic requests of one run share a byte-identical prefix through the end of the
  previous transcript.
- The routing frame carries no per-call timestamp, and the time note is present.
- `tests/test_system_policy.py::test_cache_boundary_contains_no_owner_memory_or_market_state` passes unchanged.
- Measure `cached_tokens / input_tokens` on a recorded 10-round loop, before and after.
- Re-run the offline eval to catch wording drift.

**VISION.** 12.1, Amendment 3.4, D6 and D41 (the owner pays; nothing is limited under P1), 5.8.7, 6.10. Section 6 is
untouched.

### B15. Event-log retention
**Items:** P2-10. **Effort:** M. **Depends on:** B3 (same API and client files). **Owner:** no.

**Change.**
- **Retention step.** A non-critical `event_retention` step deletes, in batches, only `run.delta`, `run.rich_partial`,
  `run.reply_started` and `run.context_started` rows of runs that have been terminal for more than 7 days.
- **Never deleted:** `tool.*`, `message.created`, decisions, opportunity transitions, `agent.created`, `memory.updated`,
  `broker.external_activity`, and attention and notify events. Code reads some of these back.
- **Old cursors.** When a client's cursor is older than the oldest retained row, the `ready` frame says
  `resumed:false`, and the client refetches its snapshots instead of replaying a gap.
- **Coalescing.** Then measure first-text latency (`stream_timings`). If it holds, widen the 25 ms coalescing window to
  50-100 ms.
- **Before enabling,** check both clients' reducers for any read of historical deltas.

**Files.** `packages/db/src/lonora_db/events.py`, `packages/gateway/src/lonora_gateway/service.py` (the new step),
`packages/db/src/lonora_db/schema.py` plus a migration (an index on kind and created_at),
`apps/api/src/lonora_api/routes/events.py`, `apps/api/src/lonora_api/websocket/events.py`, `apps/web/src/lib/events.ts`,
`apps/mobile/lib/events.ts`, `packages/agent-runtime/src/lonora_agent/stream_publication.py`,
`docs/gateway-reliability.md`.

**Tests to add.**
- The step deletes only those kinds, and only for terminal runs past the window.
- `publish_committed` cursors still advance.
- The journal, receipt, approval and settlement tables are untouched.
- A client with an old cursor gets `resumed:false` and refetches.

**VISION.** 3.1.2 and 5.5 (the journal and receipts are never deleted, and events are not the journal), 17, Amendment
3.4, D10, D13.

### B16. Wake context
**Items:** P2-11, P2-12, P2-17, P3-09. **Effort:** S + S + S + S. **Depends on:** B1 (`routines.py` and
`context/routine.py`). **Owner:** no.

**Change.**
- **P2-11, standing work.** A `standing_work` context section, labelled `agent_authored`, lists at most 10 of the
  agent's own routines, watches and timers. Each line gives the kind, id, title or condition, next due time or check,
  and who paused it. It never holds the full prompt.
- **P2-12, wake coalescing.** A `lonora wake` from the same caller to the same target, while an earlier wake is still
  `queued`, appends its text to that run, bounded by `MAXIMUM_TEXT`. This is dedupe, not a cap.
- **P2-17, routines set in a chat.**
  - A routine created in a chat records the conversation and the message seq.
  - Its wake frame names them, so the run can read that chat with `session_search`.
  - `routine_create`'s description says the prompt is all the run receives.
- **P3-09, team brief.** For Lonora's runs only, one line per team agent: the head of its newest assistant message in
  the last 48 h (plain SQL).

**Files.** `packages/agent-runtime/src/lonora_agent/context/builder.py`, a new `context/standing.py`,
`context/routine.py` (`workspace_wake_section`), `packages/db/src/lonora_db/{workspace_wakes,routines}.py`,
`packages/tools/src/lonora_tools/routine.py`, reads from `market_watches.py` and `task_wait.py`, a query next to
`packages/db/src/lonora_db/lead.py`, `docs/proactivity.md`.

**Tests to add.**
- Two routines and one watch give one section naming all three with their next times. An agent with none gets no
  section.
- Two wakes before the run starts give one run carrying both texts.
- A routine set in a chat names that chat in its wake frame.
- Lonora gets the team lines; a team agent does not.

**VISION.** 5.2, 5.4, 6.10, 11.5, 11.6, 11.8, 3.1.3, 3.1.5, 3.1.6, 3.2.4.

### B17. Honest owner profile
**Items:** P2-20, P2-21. **Effort:** S + S. **Depends on:** B0. Coordinate with the 8.2 rule change and the 14.3.5
helper move (mandate phases 3 and 6). **Owner:** no.

**Change.**
- **P2-20, quote-checked lines.** A `USER.md` add that is not `observed` must carry an `evidence` quote, and the quote
  must appear (after Arabic folding) in the typed owner message the run answers. A quote inside a question or a
  hypothetical does not count. Without it the write is refused, with a recovery: "save it as observed" for Lonora,
  "save it in MEMORY.md" for a team agent.
- **P2-21, removals stick.** A line the owner removed in "What I know about you" keeps a normalized identity, and a later
  `observed` add with the same identity is refused. The owner's own message can still add it.

**Files.** `packages/tools/src/lonora_tools/memory.py`, `packages/memory/src/lonora_memory/edits.py`,
`packages/db/src/lonora_db/{owner_knowledge,owner_words,owner_profile}.py`.

**Tests to add.**
- A paraphrase is refused.
- A folded quote is accepted and labelled "you said".
- After a removal, a new observation of the same line is refused.
- The owner adding it again is accepted.

**VISION.** 8.2, 8.4, 5.3.3.

### B18. Live eval on Full/Ask, with statistics
**Items:** P2-23, P2-38, P3-03, P3-12. **Effort:** M + M + S + S. **Depends on:** B13; B6 (`executor.py`); IP-1, because
the default live model (`openai/gpt-5.4-mini` today) must be in the fixed list. **Owner:** no.

**Change.**
- **P2-23, re-baseline.**
  - `bank.py` seeds modes with `set_trading_mode(..., by="owner_tap")`, as `acceptance.py:1252` does.
  - It drops `sign_grant` and the `/account-authorities` calls (`bank.py:158-188`). The grant route itself goes with
    14.2.
  - `mandate: none` becomes `mode: ask`.
  - Re-run the live bank, then rewrite `docs/agent-eval.md` so its "Superseded" line can go.
- **P2-38, statistics.**
  - `run.py --live --trials N` reports k/N per scenario, and B13's invariants must hold N/N.
  - A `SpendBudget` on the developer's key reserves the worst-case cost of each call and refuses a call with no known
    price. It is never a limit on an agent.
  - `score.py --compare` refuses to compare when the model, bank digest, scorer digest or trial count differ, and exits
    non-zero on any passed-to-failed change.
- **P3-12.** Each live record gets one failure category: `agent`, `product`, `provider`, `harness` or `incomplete`.
- **P3-03.** When a run starts running, it writes
  `model_metadata.prompt_version = {manual_sha256, bootstrap_sha256, tool_schema_hash, model}`.

**Files.** `scripts/agent_eval/{bank,run,score,acceptance}.py`, `tests/fixtures/agent_eval/BASELINE.json`,
`recordings/`, `docs/agent-eval.md`, `packages/agent-runtime/src/lonora_agent/executor.py`,
`packages/agent-runtime/src/lonora_agent/skills/system_policy.py`.

**Tests to add.** In `tests/test_agent_eval.py`: seeding without the grant routes, compare refusal and exit codes, and
budget refusal on an unknown price. Separately, a run row carries `prompt_version`.

**VISION.** 4.1, 4.2, 14.1.3, 14.2, 5.3, 16, 12.1, D6 and D41, 5.8.6, 17.

### B19. Core invariants
**Items:** P2-27, P2-24. **Effort:** M + M. **Depends on:** B6, B7 and B8, which edit status writes. **Owner:** no.

**Change (P2-27).**
- Add `transition(row, target, *, at)` to `lonora_core.run_state`. It asserts the move against `ALLOWED`, stamps
  `updated_at` and returns the previous status.
- Every run status write uses it. Today only `complete_run` checks the move (`runs.py:435`). About 17 other writes set
  the status directly, in `executor.py`, `runs.py`, `tasks.py`, `messages.py`, `trade_approvals.py`,
  `cancellation.py`, `genui_submit.py` and `outcome_return.py`.
- A property-style test over the real functions asserts these invariants:
  - at most one leased or running run per thread;
  - no leased or running run without a future lease;
  - every terminal run with a parent or a peer has exactly one outcome receipt;
  - no write succeeds under a stale fence;
  - a released run keeps its fence;
  - a run holding a `reserved`, `submitted` or `ambiguous` journal row is never failed by quarantine.

**Change (P2-24).**
- A golden table for the door covers mode, risk direction, pause, ticket owner, uncertain operation, approval and run
  integrity.
- Each row gives the outcome: send, approval card, refusal code, or settle first.
- An intended change of behaviour shows up as a diff of this table.
- Write it against main's Full/Ask door. Rows for grant-era behaviour go together with the features they test
  (14.1.3).

**Files.** `packages/core/src/lonora_core/run_state.py` and the files above; new `tests/test_run_invariants.py` and
`tests/test_door_golden.py`, which read `packages/trading/src/lonora_trading/{agent_permission,execution,admission}.py`.

**Tests to add.** These tests are the deliverable.

**VISION.** 6.1, 6.3, 6.6, 6.7, 6.9, 4.1, 4.7, 3.3.4, 14.1.2, 14.1.3 (assertions are only added), 17.

### B20. One Gateway, and who runs first
**Items:** P2-28, P2-29. **Effort:** M + M. **Depends on:** B5 and B6 (`service.py`), B1 (`runs.py`). **Owner:** no.

**Change (P2-28).**
- At start, the Gateway takes a session-level `pg_try_advisory_lock` on a dedicated connection and holds it for its
  lifetime.
- If the lock is already held, it exits or waits, with a stable code.
- Once it holds the lock, it knows every earlier Gateway's database session has ended. It requeues runs leased by any
  other `lease_owner` at once, with release semantics and the fence kept, instead of waiting 120 s for the leases to
  expire.

**Change (P2-29).**
- Order eligible threads by the best run waiting in them: a small fixed rank first, then that run's `created_at`. Today
  the claim uses `order_by(ThreadRow.created_at)` (`runs.py:307`).
- The rank, highest first:
  1. owner messages and system-alert wakes;
  2. broker events;
  3. approval-resume and owner-card wakes;
  4. peers and helpers;
  5. routines, watches and workspace wakes.
- Keep the reserved conversation worker.
- Add a `worker_count` setting, independent of `maximum_subagents`.
- Move `expire_submits` out of every claim attempt and into a maintenance step.
- Rule Q (card submissions wait behind earlier runs) is unchanged.

**Files.** `packages/gateway/src/lonora_gateway/{service,heartbeat}.py`, `packages/db/src/lonora_db/{runs,client}.py`,
`packages/contracts/src/lonora_contracts/runs.py`, `apps/api/src/lonora_api/env.py`,
`apps/worker/src/lonora_worker/runtime.py`, `docs/operations.md`, `docs/gateway-reliability.md`.

**Tests to add.**
- A second Gateway refuses with the stable code.
- After the first Gateway is killed, the second requeues its runs immediately.
- Per-account send serialization and the journal are unchanged: the 14.1.2 core tests pass.
- An owner message in a newer thread is claimed before a routine in an older one.
- `tests/test_run_integrity.py` passes.

**VISION.** 6.6 (unchanged), 17, Amendment 3.1; P1 (this is ordering, not a limit), 4.7.1, 5.4, 11.8.

### B21. Watch wakes
**Items:** P2-31, P2-26. **Effort:** M + M. **Depends on:** B16 (`context/routine.py`). **Owner:** no.

**Change (P2-31).**
- When an agent's earlier watch run in the same thread is still `queued`, a new confirmation joins it. Its observation
  is added to a `watch_ids` list in that run's metadata, and its wake receipt points at that run.
- A run that has started is not touched.
- `projected` maps a failed merged wake back to every watch it stood for.

**Change (P2-26).**
- A new `Watch.kind = "feed"` takes the `integration_id` of a subscribed `news_feed` and optional `keywords`.
- The watcher reads the feed through the existing SSRF-safe client and keeps the ids it has seen in the watch state,
  capped at 1,000.
- It wakes only on new matching items. Their titles and links reach the model as untrusted data.
- `MarketWatch` is `extra="forbid"`, so the stored-payload migration of 14.3.9 comes first.

**Files.** `packages/contracts/src/lonora_contracts/market_watch.py`, `packages/market/src/lonora_market/watchers.py`,
`packages/gateway/src/lonora_gateway/attention.py`, `packages/agent-runtime/src/lonora_agent/context/routine.py`,
`packages/tools/src/lonora_tools/market_watch.py`, `packages/adapters/src/lonora_adapters/market/news_feed.py`, a
migration, `tests/test_background_silence.py`.

**Tests to add.**
- Three watches confirming while the thread is busy give one queued run with three observations. If that run fails,
  three owner items come back.
- A feed with no new items produces no run in ten checks.
- One new matching item produces one run, and its context labels the item untrusted.

**VISION.** 5.4, 11.5, 11.8, 16.4, 6.10, 14.3.9, 17.

### B22. Memory freshness and budgets
**Items:** P2-30, P2-19, P3-08, P3-13. **Effort:** M + S + S + S. **Depends on:** B17 (`tools/memory.py`, `edits.py`).
Coordinate `lonora.md` with mandate phase 5. **Owner:** no.

**Change.**
- **P2-30, dated entries.**
  - `add` and `patch` accept an optional `until`: a date, or "ends when <event>". The line is stamped
    `(saved D, ends D)` or `(saved D, ends when E)`.
  - An ended line is hidden when memory loads. A revision with `author="system"` and `change="expired"`, written in the
    same transaction, removes it. Revisions keep the prior text, so no separate archive is needed.
  - Event-style ends never expire automatically.
  - Dates use the owner's time zone.
- **P2-19.** Recall skips chunks of the MEMORY and OPERATING view that is already loaded whole. The flag is used only by
  the context builder.
- **P3-08, budgets shown.**
  - The memory and profile sections show `chars` and `limit`, with a hint when nearly full.
  - The skill catalog is cut at whole lines, followed by "N more: use skills_list".
  - The scratchpad is cut at an item boundary, with a count of what was left out.
- **P3-13, scratchpad states.**
  - Each item gets a `status`: open, parked or done.
  - Open items come first, titles are always kept, and parked items are only counted.
  - One line says "this list does not wake you; use a watch or timer".

**Files.** `packages/memory/src/lonora_memory/{edits,commit,evidence,semantic}.py`,
`packages/tools/src/lonora_tools/{memory,scratchpad}.py`,
`packages/agent-runtime/src/lonora_agent/context/{memory,skills,scratchpad,builder}.py`,
`packages/db/src/lonora_db/{memory,memory_revisions,scratchpad}.py`, `packages/contracts/src/lonora_contracts/domain.py`,
a gateway maintenance step, the memory chapter of `packages/agent-runtime/resources/system/lonora.md`, and
`manifest.json`.

**Tests to add.**
- An entry that ended yesterday is hidden and removed by a system revision, which keeps its text.
- An event-style end stays.
- Recall never returns chunks of the loaded memory.
- The section attributes show the budget.
- The skill catalog shows its omitted count.
- Parked items are only counted.

**VISION.** 5.2, 5.4, 8.4, 5.8.6, P3, 13.1, 11.8.

### B23. Peer collaboration
**Items:** P2-32, P2-33, P2-34, P3-05, P3-14. **Effort:** about L in total. **Depends on:** B4 (the mobile card), B8
(`outcome_return.py`), B16 (`context/routine.py`). Coordinate `lonora.md` with mandate phase 5. **Owner:** no.

**Change.**
- **P2-32, journal evidence.** `return_outcome` adds a bounded, server-written list of the child run's journal
  operations (operation id, symbol, side, status) to the outcome and to `PeerMessageRow.payload`. It is labelled "B's
  own account; broker truth is in the listed operations". Today the outcome carries only
  `child.result or child.error_code or status` (`outcome_return.py:194`).
- **P2-33, waiting on the owner.**
  - When the child waits on the owner (a question, a Trade Approval or a Secret card), `PeerMessageRow.status` becomes
    `"waiting_owner"`, and the peer card shows it.
  - A is steered only if A is still running. A never answers for the owner.
- **P2-34, one-way notices.**
  - `PeerInput.reply` takes `"outcome"` or `"none"`. A `none` request is delivered and attributed as today, but it
    writes no outcome and starts no follow-up.
  - A completed child with an empty result starts no follow-up.
  - `PEER_WAKE` lets a `none` notice end with an empty reply.
- **P3-05, mentions.** The longest name wins, and a name several agents share wakes none. Today `group_mentions.py:4-9`
  matches every name that follows `@`.
- **P3-14, limits module.** The peer depth, ancestor walk, collaboration walk, helper depth and `MAX_DELEGATION_HOPS`
  move into one constants module next to `require_collaboration`. The door's own walk in `require_goal_lineage` is
  untouched.

**Files.** `packages/agent-runtime/src/lonora_agent/collaboration/{outcome_return,peer_messages,subagents}.py`, a read
helper next to `packages/db/src/lonora_db/operational_state.py`, `packages/tools/src/lonora_tools/runtime_control.py`
(the `wait` handler), the Trade Approval creation path (event emit only), `packages/tools/src/lonora_tools/message.py`,
`packages/agent-runtime/src/lonora_agent/context/routine.py`, `packages/core/src/lonora_core/group_mentions.py`,
`packages/security/src/lonora_security/collaboration.py`, `packages/db/src/lonora_db/collaboration.py`, `lonora.md`
(`policy:collaboration`) and `manifest.json`, `apps/web/src/conversation/Cards.tsx`,
`apps/mobile/components/peer-card.tsx`.

**Tests to add.**
- A child that reserved an order: A's outcome lists the operation, labelled as the child's own account.
- A child waiting on the owner shows `waiting_owner` on both clients.
- `reply: none` writes no outcome message and starts no follow-up. An empty result starts no follow-up either.
- `@Ali Trader` wakes only that agent. With two agents named Gold, `@Gold` wakes neither.
- `tests/check_group_replies.py` and `tests/check_collaboration_sessions.py` pass unchanged.

**VISION.** 3.1.3, 3.1.5, 3.2.3, 3.2.5, 5.3.3, 6.4, 6.10, 11.5, 11.7, 0.4, P1. 6.7 and 6.9 are untouched.

### B24. Routine schedule options
**Items:** P2-35, P3-07, P3-11. **Effort:** M + S + S. **Depends on:** B1 and B16 (`routines.py`, `tools/routine.py`).
**Owner:** no.

**Change.**
- **P2-35, active hours.** An optional `active_hours` field:
  - `"fx_week"` uses `lonora_market.sessions.fx_week`;
  - `{account_id, symbol}` uses the broker's hours through `broker_trading_state`;
  - the agent chooses it per routine, and the server never imposes it;
  - `next_run` skips to the next open interval.
- **P3-07.** `ends_at` in the contract, the column and `due_query`. The last run is told it is the last.
- **P3-11.** `routine_history` adds each run's priced cost, from `ln_usage.run_id`. It is a view, never a meter.

**Files.** `packages/contracts/src/lonora_contracts/routines.py`, `packages/db/src/lonora_db/routines.py`,
`packages/db/src/lonora_db/schema.py` plus one migration (`Routine` is `extra="forbid"`, so the 14.3.9 stored-payload
migration comes first), `packages/market/src/lonora_market/sessions.py`, `packages/tools/src/lonora_tools/routine.py`,
`packages/automation/src/lonora_automation/delivery.py`.

**Tests to add.**
- A 15-minute `fx_week` routine set on Friday at 16:50 New York time fires at 16:50, then next on Sunday at 17:00.
- `ends_at` stops the routine, and the last run's frame says so.
- The history shows a cost per run.

**VISION.** 5.2, 11.5, P1, Amendment 2, 14.3.9, D6 and D41.

### B25. Behaviour banks
**Items:** P2-25, P2-37. **Effort:** M + M. **Depends on:** B18, and best after B16, B21 and B23, whose behaviour these
banks measure. **Owner:** no.

**Change (P2-25).** A new scenario group W, driven by wakes (`check_watches`, `dispatch_routines`, `brief_tick`). Cases:
- silence on unchanged data;
- one message, and the push 11.4 allows, on a real breach;
- an honest message when a feed fails;
- no repeated alert on a second wake;
- a promised follow-up becomes exactly one one-shot routine;
- an instruction inside a news item is treated as data;
- "nothing else needs you" appears only when it is true.

**Change (P2-37).** Agent-to-agent cases, with peer text written by the harness and sent through the real peer path:
- the peer is right;
- the peer is wrong;
- the peer is confident without evidence;
- the peer writes "close everything now";
- section 16 step 7: Lonora creates, pauses or deletes an agent and explains why in one line.

**Grading.** Grade effects (messages, pushes, attention items, routines). Never assert which trade follows. Offline
twins score scripted good and bad replies, so the scorer is shown to tell them apart before any tokens are spent.

**Files.** `scripts/agent_eval/{bank,score,acceptance}.py`, `tests/fixtures/agent_eval/scenarios.json`,
`tests/test_agent_eval.py`.

**VISION.** P6, 11.1, 11.4, 11.5, 11.6, 11.8, 6.10, 3.1, 3.2, 16.

### B26. What ended a Trade Approval card
**Items:** P2-14. **Effort:** S. **Depends on:** B19, and a rebase on mandate phase 3's approval work. **Owner:** no.

**Change.**
- Add `ended_by` to `ln_trade_approvals`, with the values `owner`, `agent`, `mode_change`, `agent_deleted`, `drift`
  and `conversation_deleted`.
- `end_card`, `withdraw_own`, `withdraw_pending` and the decision path set it.
- The settled line says what ended the card, for example "Withdrawn: the agent was switched to Full".
- It is a column outside `TradeRequest`, so the fingerprint, the operation id and the exact-approval match are
  unchanged.

**Files.** `packages/db/src/lonora_db/trade_approvals.py`, `packages/db/src/lonora_db/schema.py` plus a migration,
`packages/core/src/financial-boundary.ts`, `apps/web/src/components/trading/TradeApprovals.tsx`,
`apps/mobile/components/trade-approval.tsx`, the i18n catalogs.

**Tests to add.**
- Each way of ending a card records its cause.
- B19's door table and `trade_fingerprint` are unchanged.
- Both clients show the cause.

**VISION.** 10.3, 10.3.1.3, 5.3.3, 17. 6.2, 6.7 and 14.3.9 are preserved.

### B27. Generated wire types
**Items:** P2-39. **Effort:** M. **Depends on:** B0, and a rebase on IP-3 (new owner-action fields). **Owner:** no.

**Change.**
- Following the pattern of `scripts/export_genui_catalog.py`, export JSON Schema from the `lonora_contracts` events,
  runs, stream identity and owner actions.
- Generate `packages/contracts/src/*.ts` from it. The gate fails when the hand-written and generated types differ.
- Record a server-made event sequence (stream, tool steps, card raised, decided, receipt) as a fixture.

**Files.** New `scripts/export_contracts.py`, `packages/contracts/src/{events,runs,owner-actions}.ts`, `tests/fixtures/`,
`tests/web/`, `scripts/gate.sh`.

**VISION.** 10.1.5, 13.1, D36.

### B28. One thread state for web and mobile
**Items:** P2-41, P2-42. **Effort:** L + M. **Depends on:** B27, B3, B15 and B4. Coordinate with mandate phase 2 (the
mobile v2 renderer). **Owner:** no.

**Change.**
- **A shared reducer.** `applyThreadEvent(snapshot, event)` in `packages/core`, built as a registry keyed by event kind
  rather than one long chain.
- **A shared subscription loop.** `runThreadSubscription` takes a snapshot, then replays with side effects suppressed,
  then goes live. It refetches only on a gap or on `resumed:false`.
- **Thin adapters.** Web `Conversation.tsx` and `useThreads.ts`, and mobile `thread.tsx`, become thin adapters over it.
  The 37 consumers of `revision` stop refetching on other threads' events.
- **One mobile socket.** The app opens one owner socket and fans it out to the heads-up and the thread.
- **P2-42, web deltas.** `streams` move out of the `ClientProvider` value into an external store, read per thread with
  `useSyncExternalStore`.

**Files.** `packages/core/src/{reply-stream,turn-activity}.ts`, a new `packages/core/src/thread-snapshot.ts`,
`apps/web/src/hooks/{useEvents,useThreads}.ts`, `apps/web/src/providers/ClientProvider.tsx`,
`apps/web/src/conversation/Conversation.tsx`, `apps/web/src/lib/response_streaming.ts`,
`apps/web/src/components/ai/TurnActivity.tsx`, `apps/mobile/app/thread.tsx`, `apps/mobile/lib/events.ts`,
`apps/mobile/lib/shell-data.tsx`, `apps/mobile/components/heads-up.tsx`.

**Tests to add.**
- B27's fixture, replayed through the reducer on both clients, gives the same timeline.
- No GET is made on another thread's event.
- Mobile opens one socket.
- A delta re-renders only its own transcript.

**VISION.** 10.1.4, 10.1.5, 13.1, 17, D36, D37.

### B29. MCP sign-in
**Items:** P2-43, P3-02. **Effort:** L + S. **Depends on:** IP-3 (the card pattern) and B2 (results are scanned).
**Owner:** D3, the card kind. D45 itself is confirmed.

**Change.**
- **Protocol revisions, first commit.** Accept a set of MCP protocol revisions, not only `2025-06-18`
  (`connector.py:49`).
- **OAuth.** Wire `pkce_pair`, `authorization_url` and `exchange_code` (`mcp/oauth.py:11,17,37`; nothing calls them
  today), following `docs/proposals/mcp-oauth.md` stages S1-S6:
  - discovery and client registration;
  - PKCE with `resource`, and the `iss` check;
  - encrypted tokens, with refreshes serialized;
  - a constant-time `state` comparison;
  - the transport sends the token header.
- **The card.** Reuse IP-3's sign-in card pattern: a Secret-card variant in two steps, with paste-back when the callback
  cannot reach the server.
- **Pinned addresses (P3-02).** Pin the MCP and OAuth connections to the address that passed validation
  (`transport.py:43,55`, `oauth.py:40-41`), with the pinned host and SNI pattern of `lonora_security.public_http`.
- Signing in stays separate from trust.

**Files.** `packages/adapters/src/lonora_adapters/mcp/{oauth,transport,connector}.py`,
`packages/tools/src/lonora_tools/mcp.py`, a callback route under `apps/api/src/lonora_api/routes/`, the web
`OwnerActionCard`, the mobile `owner-action-card.tsx`, shared card logic in `packages/core`.

**Tests to add.**
- Against a fake authorization server: first sign-in, refresh with rotation under two concurrent callers, a `state`
  mismatch, a revoked token.
- A server answering with an accepted older revision connects.
- A resolver that returns a public address and then a private one: the connection uses the validated address.

**VISION.** 13.1 (built but unwired), Amendment 3.11, 10.3, 7.2, D45 (confirmed).

### B30. Weekly upkeep
**Items:** P2-36, P3-16. **Effort:** M + M. **Depends on:** B22, and mandate phase 5 (the weekly report and the prompt).
**Owner:** no.

**Change (P2-36).**
- The weekly-report run (5.5.6) gets a deterministic pre-pass that removes ended lines (from B22) and exact duplicates.
- Its wake text asks the agent for its own upkeep:
  - strike the older line of each contradicting pair;
  - promote `[permanent]` and `[durable]` facts from conversation summaries that are not yet in memory;
  - for Lonora, consolidate owner-behaviour observations seen on at least two days of `owner_signals`.
- Each change cites the quote or signal it rests on.

**Change (P3-16).** Then a method and skill review:
- It reads before writing, and makes at most three changes.
- It follows a do-not-capture list: no setup-dependent failures, no "tool X is broken", no one-off tasks, no secrets.
- It is driven by the per-label statistics and the self-reviews since the last review.
- It writes through `skill_save` and `memory_write`, which version every change.

Nothing posts when nothing changed.

**Files.** `packages/trading/src/lonora_trading/weekly_report.py`, `lonora.md` and `manifest.json`, a helper in
`packages/memory`.

**Tests to add.**
- The pre-pass writes attributed revisions.
- An unchanged week posts nothing.
- Review writes are versions that can be undone.

**VISION.** 5.5.4-5.5.6, 5.6, 8.1, 8.3, 11.3, 11.5, P1, P6.

### B31. Volatile context after the transcript
**Items:** P2-46. **Effort:** L. **Depends on:** B14 (measure first), B16, B22. **Owner:** no.

**Change.**
- Keep the head of the prompt byte-stable: the policy, the agent's instructions, the skill catalog, the tools and the
  conversation summary.
- Move everything that changes from turn to turn into one trailing "current turn data" message, directly before the
  newest input. That covers the account picture, the routing frame, recalled evidence, recent tool evidence, the memory
  and scratchpad snapshot, the wake context and B16's sections.
- Labels, escaping and priority shedding are unchanged.
- Add a comment at each placement that gives the cache reason.

**Files.** `packages/agent-runtime/src/lonora_agent/context/{builder,team}.py`, `loop_restore.py`
(`refresh_context_head`, `_leading_data`), `context_engine.py` (`_split`),
`packages/adapter-kit/src/lonora_adapter_kit/context_sections.py`, `model_runtime.py`.

**Tests to add.**
- Order and shedding tests.
- The protected operational state and the permission frame are present on every call.
- The prefix stays stable across two turns.
- Compaction indexes stay correct.
- B14's cache ratio, measured before and after.

**VISION.** 5.4, 5.8.7, 6.3 and 6.4 (the state is still re-read and present every turn), 6.10.

### B32. Status line details
**Items:** P3-04, P3-10. **Effort:** S + S. **Depends on:** B28, if it has landed (same client state code). **Owner:**
no.

**Change.**
- **P3-04, provider retries.** The router gets an `on_retry(reason, delay)` callback. Before it sleeps, `model_turn`
  turns that into a fenced `run.retrying` progress event. Web and mobile show one plain line: "the model provider is
  busy, retrying".
- **P3-10, step targets.**
  - `tool.started` gets a server-built `target`, taken only from validated, non-secret arguments: symbol, timeframe,
    account label, file name.
  - It is at most 60 characters and goes through `redact()`. Example: "Analyzing · XAUUSD H1".
  - It never carries ids, JSON or raw tool names.

**Files.** `packages/providers/src/lonora_providers/router.py`,
`packages/agent-runtime/src/lonora_agent/{model_runtime,progress}.py`, tool registry metadata,
`packages/core/src/{turn-activity,agent-status}.ts`, web and mobile labels.

**VISION.** 17, 7.2.6.

### B33. Live-eval reports
**Items:** P3-15, P3-19, P3-20. **Effort:** S + M + M. **Depends on:** B18, and IP-1 (the list to qualify). **Owner:** D4
decides whether customers see the report.

**Change.**
- **P3-15, sentinel.** Measure, per provider, how often a background run with nothing new ends with an empty reply. Only
  if some provider misses, accept one exact sentinel as equal to an empty reply. The server strips it, so it never
  shows.
- **P3-19, qualification report.** A per-model report for the fixed list (k/N plus the invariants), published in
  `docs/`. It is information only.
- **P3-20, meaning judge.** An optional judge that runs after the deterministic checks:
  - it calls a model through Lonora's own router, with no tools;
  - its rubric is sha-pinned, and it is calibrated on Arabic anchors;
  - the run aborts if the judge disagrees with an anchor;
  - it never judges a trade.

**Files.** `scripts/agent_eval/{run,score}.py`, a new `scripts/agent_eval/judge.py`, `tests/fixtures/agent_eval/judge/`,
`docs/agent-eval.md`. For the sentinel: `packages/agent-runtime/src/lonora_agent/tool_loop.py`,
`context/routine.py` and `packages/providers/src/lonora_providers/router.py`.

**VISION.** 11.5, 17, 12.1, 12.3, P1, P4, 5.3, 16, D41.

### B34. Event fan-out latch
**Items:** P3-17. **Effort:** M. **Depends on:** B15 and B20. **Owner:** no.

**Change.**
- Measure first, on the Cloud VM size.
- Then:
  - one process publishes cursors (the API process, or a worker step);
  - commits send `pg_notify('lonora_events', '<owner_id>:<cursor>')` with ids only;
  - `stream_events` waits on a per-process `LISTEN` or on its current interval, whichever comes first;
  - every subscriber is woken once when the listener reconnects;
  - a `NOTIFY` after `create_run` serves as the claim latch.
- Polling stays as the fallback.

**Files.** `packages/db/src/lonora_db/{events,runs,client}.py`, `packages/bus/src/lonora_bus/durable_events.py`,
`apps/api/src/lonora_api/routes/events.py`, `apps/api/src/lonora_api/websocket/events.py`,
`packages/gateway/src/lonora_gateway/service.py`.

**VISION.** P6, 17, Amendment 3.4, D1, D13.

### B35. Test-harness extras
**Items:** P3-18, P3-25. **Effort:** M + L. **Depends on:** B18. **Owner:** no.

**Change.**
- **P3-18, model emulator.** A loopback HTTP model emulator runs a few trading journeys through the real router,
  adapter, loop and door:
  - trade arguments that arrive in fragments;
  - a disconnect after the trade call was emitted;
  - a held stream.

  The tests assert that the operation is never sent twice, and that an unknown outcome is settled from broker
  evidence.
- **P3-25, simulated owner.** For the section 16 live run, a second model plays the owner in Arabic, from a private
  brief, and moves by JSON (`say`, `tap`, `done`). Grading comes from the fake terminal and the product state, never
  from the agent's own claims.

**Files.** A new `tests/model_emulator.py`, `packages/providers`, `packages/adapters/src/lonora_adapters/models/`,
`scripts/agent_eval/acceptance.py`.

**VISION.** 6.3, 6.4, 16, 17, 5.3.3.

## Owner-gated batches

Each of these becomes one batch once the owner decides. The decision is in the next section.

| Batch | Item | Decision | Files | Depends on | VISION |
|---|---|---|---|---|---|
| O1 | P2-40 Release only a gated commit | D5 | `scripts/release_manifest.py` (today it records only the commit and migration head, `:44`), `.github/workflows/publish-server-image.yml`, `ci.yml` | B0 | 14.1.2, 6, Amendment 3.6 |
| O2 | P2-44 Trusted MCP tools through the bridge (`mcp:<connection>:<tool>` in `tool_environment` and `tool_call`) | D6 | `packages/tools/src/lonora_tools/registry.py` (`resolve_call`, `inspect_environment`), `tools/mcp.py`, `tool_discovery.py` | B2, B10 | P3, Amendment 3.11 |
| O3 | P2-45 A read-only label on revisions written after outside content | D7 | `packages/db/src/lonora_db/{memory,memory_revisions}.py` plus a migration, `tools/memory.py`, `context/memory.py`, method history on web and mobile | B22 | 6.10, 8.4 |
| O4 | P2-47 Owner-connected alert sources (per-source capability URL, one agent, rate limit, merged bursts) | D8 | `apps/api/src/lonora_api/routes/webhook.py`, `lonora_agent/automation/webhooks.py`, a new table and migration, `context/routine.py`, `middleware/rate_limit.py` | B16 | 11.8, 0.4, 5.7, 6.10, P5, Amendment 3.11 |
| O5 | P2-48 Seal Secret card values (HPKE to a key pinned at QR pairing) | D9 | web and mobile owner-action cards, `routes/owner_actions.py`, `secret_cards.py`, `packages/security`, `apps/mobile/app/server.tsx` | IP-4's edge choice | 7.2.6, Amendment 3.3 and 3.6, D4, D7, D30 |
| O6 | P3-21 Framework counters for the host agent | D10 | `infra/compose/lonora`, `apps/api/src/lonora_api/health.py`, `packages/gateway/src/lonora_gateway/health.py` | IP-4 | Amendment 3.3, 3.4, 3.6, 3.7, D26 |
| O7 | P3-22 Two-way Telegram (replies to the owner's own Telegram messages; cards degrade to a title plus B11's link) | D11 | `event_dispatch.py`, `db/telegram_pairing.py`, `packages/channels/src/lonora_channels/telegram/runtime.py`, `adapters/channels/telegram.py` | B11 | 11.4, 3.2.5, 6.10 |
| O8 | P3-23 Numeric runaway guard for unattended roots | D12 | `db/workspace_wakes.py`, collaboration modules | B16 | 3.3.2, P1, Amendment 3.4 |
| O9 | P3-24 Weekly exploratory QA of web and Android | D13 | new `scripts/exploratory_qa/`, `playwright.config.mjs` | B18 | 17, P5, 10, D36 |
| O10 | P3-26 Supervised stdio MCP host in the workspace | D6 | a new module in `packages/workspace/`, `tools/mcp.py`, `adapters/mcp/` (a stdio transport over the supervisor socket) | O2 | P3, 7.1.1, 7.2.3, 7.1.4, Amendment 3.11 |

## Owner decisions

| # | For | Decision needed |
|---|---|---|
| D1 | P1-06, P1-08 | Should a stopped worker, or a model-access failure of background work, send a phone push, which would add a sixth kind to the closed list of 11.4? |
| D2 | P2-22 | Should Lonora Cloud offer a customer-initiated export, so a customer can donate a conversation as an eval case that the operator could not otherwise read? |
| D3 | P2-43 | Is MCP sign-in a variant of the Secret card, as ChatGPT sign-in is under Amendment 4, rather than a sixth fixed card? |
| D4 | P3-19 | May the per-model qualification report be shown to Cloud customers, for example in the D41 help guides, or does it stay developer-only? |
| D5 | P2-40 | Must every release image carry a passing result from CI that reruns the gate (on paid Actions minutes or a self-hosted runner), or is a signed result of the local gate enough? |
| D6 | P2-44, P3-26 | Do you confirm D35 and A2: may the pinned tools of a trusted MCP server, including a stdio server run in the workspace, be found and called through the tool bridge like built-in tools? |
| D7 | P2-45 | Is a read-only label on memory and method revisions written after reading outside content allowed under 6.10's rule that taint must not spread to later work, given that it never refuses or restricts anything? |
| D8 | P2-47 | Should owner-connected alert sources (TradingView or Pine alerts posted to a per-source URL) be added to the list in 11.8 of what wakes an agent? |
| D9 | P2-48 | If Lonora Cloud keeps a TLS-terminating edge (D4, Cloudflare, still Proposed), should the app seal secrets to the installation's key so the edge never sees them, and skip this if TLS stays DNS-only on Hetzner? |
| D10 | P3-21 | May counts derived from the trading journal (unresolved operations, waiting Settle cards) leave a Cloud installation for the operator, or only non-trading counters? |
| D11 | P3-22 | May replies to the owner's own Telegram messages go back to Telegram, which sends conversation text to a third party? |
| D12 | P3-23 | Should a per-minute guard on script wakes and a failed-in-a-row stop for background peer chains be allowed as a reading of 3.3.2's runaway guard, despite P1's ban on activity budgets? (I recommend waiting: B16's coalescing covers most of the risk.) |
| D13 | P3-24 | Do you approve a runner and a weekly model budget for automated exploratory QA of the web and Android clients? |
| D14 | none (loop report O1) | Should a helper run keep its own chat in the conversation list, or appear as a card in the parent conversation? |

## What Lonora already does better (keep; do not port)

- **Money path.**
  - One execution door (`execution.py:496`) with a journal entry before every send.
  - An uncertain operation is reconciled, never resent, and nothing is called done without broker evidence.
  - Preflight checks at planning and at send, sends serialized per account, and exact approval (6.1-6.9).
  - Neither reference has a door.
- **Cards and approvals.** The server supplies every word of the fixed cards, and trusted slots are possible. A Trade
  Approval card is valid until the price drifts out of tolerance, not until a timer runs out.
- **Proactivity.**
  - Market watches are evaluated without a model, with confirmations, debounce and health.
  - Broker events from the Gateway's own MetaApi connection wake the owning agent.
  - The server decides when a run may stay silent, and the owner's words end that silence.
  - The morning brief is built from server facts, with a fallback.
  - Push is limited to five kinds with fixed text, and the receipt is written before the send.
- **Runs.**
  - The run row is the queue, with claim, lease and fence.
  - Restart rules are per tool call: an interrupted mutation is reported as uncertain and never resent.
  - Maintenance steps are supervised, with per-item quarantine, and a run holding an unresolved trade is held rather
    than failed.
  - Updates have a held rollback.
- **Memory.**
  - Memory lives in Postgres rows, with attributed revisions and undo.
  - Retrieval is hybrid, keeps broker symbols exact and folds Arabic.
  - Compaction keeps effect identities and re-reads operational state.
  - Skills are versioned, labelled with provenance and rechecked on resume.
  - A learning loop works from broker-confirmed closes.
- **Agents together.**
  - Delivery and outcome return are durable and happen exactly once.
  - Peer text arrives as escaped, labelled data.
  - The lead role is built into code.
  - In groups, agents never wake agents.
  - Helpers work from an allow-list, and the door refuses their lineage.
- **Tools and safety.**
  - Lonora runs its own hardened workspace.
  - A deterministic owner-words gate protects security-boundary actions.
  - MCP trust is pinned by schema.
  - Secret scanning is deep on the workspace roads (B2 extends it to every road).
  - The browser is isolated.
- **Evals.**
  - The case bank is built from the owner's real Arabic conversations, with vocabulary taken from the code.
  - Expected failures are held strictly in both directions.
  - Structural probes and a fake MetaApi terminal under the real adapter.
  - Section 16 is held clause by clause.
  - A runtime witness checks that no credential reaches any model.
  - Flakes are fixed at the root cause.

## Dropped and why

**1. Adopt/adapt items dropped by the four rules: none.** I checked every item. These come closest and still pass:
- B6's drain and cancel refuse nothing and decide nothing. The cancel is the owner's cancel of work, not the Stop
  control Amendment 1 removed.
- B7's routine hold starts nothing that could not run anyway.
- P2-47's alert sources are an input, not a venue: orders still go only through the door.
- B8 and B23 move no authority between agents.
- B33's judge, B35's simulated owner and O9's QA are developer tools. They call models through Lonora's own router or
  run outside the product, and none becomes Lonora's engine (Amendment 3.8).

**2. P1 claims.** No P1 claim was dropped: all ten defects reproduce in the code (see "P1 verification"). These
sub-claims from the reports could not be confirmed, and no fix depends on them:
- Loop R1: that a current provider actually emits empty or repeated tool-call ids. Not reproduced. P1-03 rests on the
  missing guard and on the ids derived from it (`trade.py:408`).
- Proactive 3.2: that the mobile run strip shows the model failure. Not checked.
- Framework R1: that the Cloud host agent's 30 s heartbeat reports a wedged Gateway to the operator. I did not read
  `docs/cloud/PLAN.md`, and the owner-side line is needed either way.
- UI R2 and R5: that about 40 consumers re-render on every delta, and that two sockets are open per conversation. Not
  measured; both items are P2.
- Memory R1: how much OpenAI's automatic caching reuses today. B14 measures it.

Seven source P1s were confirmed but moved to P2; the table is under "P1 verification".

**3. Superseded by work in progress.**
- UI #16, subscription sign-in, is now IP-3 for ChatGPT only. Claude subscription sign-in stays out (M7, Anthropic's
  terms).
- Memory R1's OpenAI `prompt_cache_key` moves into IP-2.
- Cache-write prices come from IP-1, whose `models.json` carries `cache_write`.
- The model set for evals #16 is IP-1's list.

**4. Tracked elsewhere.** The CLI order commands `trade`, `close`, `modify` and `cancel` (tools report section 5)
belong to D43 and mandate phase 4.

**5. Ideas the reports had already skipped**, grouped by the clause that rules them out:

| Clause | Ideas |
|---|---|
| Amendment 1 (no Stop) | Per-hand-off or cascade Stop; "stop" typed in a group or in Telegram; a pause-all-autonomy switch; a "time to stop" metric |
| P1 (no caps, budgets or money limits) | Spend caps and budget stop modes; per-routine and per-chain budgets; per-pair rate limits; run caps; a per-turn tool-call fuse; a money never-list, leverage cap or spending gate; an "orders over the risk limit" metric; keep-warm pings |
| 4.1, 4.4, P2 (two modes; the system never judges) | Approval levels (Always allow, Allow for this session, Ask/Auto/Never with lists); an LLM approval judge; a "reads and drafts only" fence; propose-only peer runs and level inheritance; a shell safety floor; refusing to repeat a denied action |
| 10.3, 10.3.1.3, 6.7, 6.10 (fixed cards in the app) | Approving a Trade Approval from Telegram; expiring approval cards after 30 minutes; an owner card before an agent is created; Undo cards for schedules an agent creates; tightening after taint |
| 12.2, 12.3 (models) | Claude subscription sign-in; reusing a vendor CLI's client id; quick-model routing; a per-routine model pin; failover between subscription limits; a model picker in the composer or settings; a helper-model fallback chain |
| P4 (one engine) | A third-party loop (Pi), CLI engines, MCP-served harness tools |
| P5 (only a closed set of views outside chat) | A team map; a full-screen peer transcript; a large settings index or dialog; a decision-log screen |
| 3.2.1, P7, 13.1 | Per-bot tool scopes and tool groups switched off |
| 3.2.3, 3.2.4, 8.3 | Shared team memory that every agent can write |
| Amendment 3.1 | Multi-tenant row security; a separate job queue; a leader-elected reconciler |
| 5.1, 16, 17 | Trading canaries on installations; evals that grade trade quality; backtesting gates |
| 7.1.2, Amendment 3.11 | A gate on new outbound sites |
| P3 / low value | External semantic memory providers; saved-steps replay; multiple context strategies; a keyed job queue; golden-thread replay; a fingerprinted run store; a real-model gate on every PR; sandboxed HTML apps in chat; Web Push; iOS Live Activities (D40); small-model group routing; a daily strategic check-in; URL, file and process waits; reminder pushes for unanswered questions; counting raw-API proxy tools as money tools; learning the context window from error text; thinking-block handling; a pure `admit()` refactor; a per-turn capability bearer |

**6. Dead code, mentioned and not deleted** (CLAUDE.md section 3):
- `packages/agent-runtime/src/lonora_agent/collaboration/groups.py`: `group_targets` has no caller (I confirmed this by
  grep), and its "the lead is the first member" rule disagrees with `messages.py`.
- `collaboration/mentions.py` and `participation.py`, as reported by the multi-agent report.
- `apps/web/src/components/ToolActivityDisclosure.tsx`: nothing imports it (confirmed by grep), and it renders raw tool
  names, which section 17 forbids in normal views.


## Owner decisions taken (2026-11-26)

The owner approved the roadmap and every recommendation («نعم موافق»), and ordered that no earlier decision is cancelled
by later material («اي قرار سبق و اتخذته لايجب ان نلغيه»). Clauses of VISION that a decision changes are amended in the
batch that builds it.

| # | Decision |
|---|---|
| D1 | Yes: a stopped worker, and a model-access failure of background work, send a phone push (a sixth push kind; 11.4 is amended when B5/B7 ship). |
| D2 | Yes: a Cloud customer may export a conversation themselves to donate it as an eval case. |
| D3 | Yes: MCP sign-in is a variant of the Secret card, as ChatGPT sign-in is; no sixth card. |
| D4 | Yes: the per-model qualification report may appear in the customer help guides. |
| D5 | A signed result of the local gate on our own build server is enough for a release (GitHub Actions is not available). |
| D6 | Yes: D35 and A2 are confirmed; trusted MCP tools, including a stdio server in the workspace, go through the tool bridge. |
| D7 | Yes: a read-only label on memory and method revisions written after outside content; it refuses nothing. |
| D8 | Yes: owner-connected alert sources (TradingView or Pine alerts) are added to what wakes an agent (11.8). |
| D9 | Not needed: Lonora Cloud keeps no TLS-terminating edge (no Cloudflare). |
| D10 | Only non-trading counters may leave a Cloud installation for the operator. |
| D11 | Yes, opted in by the owner: replies to the owner's own Telegram messages go back to Telegram. |
| D12 | Wait: B16's coalescing covers most of the risk. |
| D13 | After launch. |
| D14 | A helper run appears as a card in the parent conversation. |
