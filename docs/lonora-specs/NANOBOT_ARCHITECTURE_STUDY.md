# Nanobot source study for Lonora specification 19

Study date: 2026-10-16. Reference: [HKUDS/nanobot](https://github.com/HKUDS/nanobot), pinned at **`faf1efaf09d2d69d1887b6ac6b0c6441e3ccccb2`**. Lonora baseline: **`21293ad606b6c97d247079bd91ab6f3f625861c7`**, branch `feat/agent-operating-environment`. Comparisons below describe that baseline; implementation acceptance remains in `IMPLEMENTATION_MATRIX.md`.

The reference checkout was inspected read-only outside Lonora. Paths beginning `nanobot/` and `tests/agent/` below refer to that pinned reference unless explicitly identified as Lonora paths. These are source/test inspections, not a claim that Nanobot's test suite was executed. No reference implementation code was copied into Lonora by this study.

## License and attribution boundary

The pinned `LICENSE` is MIT, copyright **2025-present Xubin Ren and the nanobot contributors**. It requires preserving its copyright and permission notice for copies or substantial portions. Conceptual comparison alone does not import Nanobot code. Any later direct source reuse must preserve that notice, identify the reused modules and update Lonora's third-party notice inventory. Nanobot is an engineering reference, not a replacement dependency or a new runtime inside Lonora.

## Findings that affect implementation

1. This revision is substantially more capable than the original small Nanobot loop: a shared `AgentRunner`, transactional SQLite sessions, ordered state operations, governed context, goal continuation, checkpoint recovery, private child sessions, application-owned MCP connections, and session-bound automation are already present.
2. Its most useful lesson is a failed tool result becoming the **next model observation**, with the objective and bounded context retained. A thrown tool exception does not automatically terminate the owner's request.
3. Nanobot's restart policy deliberately requires owner confirmation before executing more work. Its child tasks are marked interrupted. Lonora's PostgreSQL leases, fences, durable runs, task controls, receipts and financial reconciliation are stronger foundations for specification 19's unattended recovery. Importing Nanobot's restart policy would regress Lonora.
4. Nanobot's generic MCP transient retry does not establish external effect idempotency. It must not be imported for broker or arbitrary external mutations.
5. Nanobot's `/goal` opt-in syntax, global unified default session, workspace-wide editable identity files, per-session model selection and reasoning payload storage conflict with explicit Lonora requirements. Their useful boundaries can be adapted without importing those behaviors.

## Actual execution traces

### User request, tools, persistence and completion

`BaseChannel._handle_message` in `nanobot/channels/base.py` applies sender access/pairing policy and publishes an `InboundMessage` to `MessageBus`. `session_key_for_channel` in `nanobot/session/keys.py` selects a channel/chat session, or the optional unified default session.

`AgentLoop.run` in `nanobot/agent/loop.py` consumes inbound messages. `_dispatch_inbound` handles priority controls, validates existing-session requirements and recovery admission, and `_enqueue_session_message` creates **one session worker**. More input for the same session goes to its existing inbox. `_journal_pending_message` records injectable WebUI follow-ups before they enter the process-local queue. Other sessions can execute independently.

`_run_session_queue` dispatches FIFO input through `_dispatch_one` and `_process_message`. A turn passes the explicit stages **restore → compact → command → build → run → save → respond**. `_restore_turn` binds the session generation and delivery, applies disabled-tool policy and restores interruption records. `_persist_user_message_early` persists acknowledged user input before fallible model work. `_build_turn` combines canonical history, current input, selected runtime, runtime context and tools.

`ContextBuilder.build_transcript` in `nanobot/agent/context.py` produces identity/bootstrap files, memory, active skills/catalog, session summary, history and the current input. `AgentRunner.run/_run_core` in `nanobot/agent/runner.py` calls the provider through the context governor. Tool responses are executed through `execute_tool_calls`, converted to matching `role=tool` observations and fed into the **next internal model iteration**. No new owner message is needed for that continuation.

The runner checkpoints `awaiting_tools` before tool execution, `tools_completed` after the batch's results, and `final_response` before terminal persistence. `AgentLoop._persist_turn/_save_turn` persists the transcript and clears pending/checkpoint markers through `SessionState.finish_turn`; delivery then projects the committed outcome to the channel.

**Persistence limit:** the checkpoint is at a batch boundary. A crash during a batch can leave external effects uncertain. The runner checkpoint itself is not an execution receipt or financial journal.

**Lonora mapping:** existing API/channel admission → `lonora_db.messages.send_message` → existing run/steering admission → `Gateway.worker_loop/dispatch_one` → `AgentRuntime.execute` → `execute_run` → `execute_tool_loop` → `build_context/model_turn` → global router → `ToolRegistry.execute` → fenced checkpoint/result/events. Extend those components rather than introducing a Nanobot loop, bus, session store or scheduler.

### Background work, durable wait and wake

There are several distinct upstream mechanisms, not a single fully durable workflow engine:

- `CronService` in `nanobot/cron/service.py` loads workspace `cron/jobs.json`, persists schedules/run history and arms the nearest bounded timer. Its callback submits session-bound agent work through `run_bound_cron_job`, `submit_cron_turn` and `AutomationTurnCoordinator`. Active-session automation can be deferred until the accepted owner input finishes. `_on_timer` always rearms after exceptions. A dirty schedule snapshot is saved before older disk state can be reloaded and executed again. A corrupt initial store is preserved and startup fails instead of replacing it with an empty store.
- `LocalTriggerStore` in `nanobot/triggers/local_store.py` persists deliveries in inbox/processing/failed directories, uses a file lock and atomic writes, and retains attempt counts. `run_local_trigger_queue` claims a delivery, submits the bound turn, waits for its completion, then acknowledges it. Startup recovers processing files. Agent-completed failures are distinguished from failures to deliver. Delivery retries stop after ten attempts.
- Heartbeat is a **protected cron job**, not a separate agent engine. `nanobot/cli/gateway_runtime.py` reads the active-task section of `HEARTBEAT.md`, skips empty work and submits the heartbeat session through the same agent. Dream consolidation is another protected cron job.
- Sustained goals are session metadata in `nanobot/session/goal_state.py`. `AgentRunner` consults a live continuation callback before treating a final response as terminal. `nanobot/session/turn_continuation.py` can enqueue an internal continuation slice at a model iteration limit, suppressing an artificial owner-facing completion and preserving request origin. The outer continuation budget is capped at twelve slices. This is bounded continuation, not a broker-state machine or a general durable wait-condition scheduler.

**Failure limits:** process-local automation futures/inboxes disappear at restart; local triggers explicitly recover disk deliveries. A crash after an external side effect but before delivery acknowledgement is not magically exactly-once. Cron schedule persistence is defensive, but not a substitute for a mutation journal.

**Lonora mapping:** `lonora_automation`, gateway scheduler, durable wake/event rows, `TicketRow` task state, `RunRow`, existing market watches and goal recovery. Do not recreate cron JSON files, trigger directories or an LLM heartbeat that checks every market tick. Keep deterministic filtering and durable wake identity before a semantic model invocation.

### Tool failure, diagnosis and continuation

`ToolRegistry.prepare_call` in `nanobot/agent/tools/registry.py` resolves the **exact** tool name, may suggest a unique normalized spelling without executing an alias, normalizes the arguments envelope, casts according to schema, and validates. Invalid input becomes a typed `ToolResult.error` marker around textual guidance. `_execute_tool_call` in `nanobot/agent/tools/execution.py` converts ordinary exceptions into observations, calls error hooks, records an error event, and returns control to the runner. Cancellation/control-flow exceptions are not converted into successful observations.

The next model turn receives the failed result and guidance to decide how to proceed toward the owner's goal. This permits changing arguments or choosing another tool; the runtime does not itself infer a safe alternate financial action. Workspace/SSRF errors receive explicit non-bypass guidance. Per-turn repeated external lookups and repeated boundary attempts are counted deterministically. These counters are not durable general-purpose retry state.

`AgentRunner._request_model` separately handles malformed provider tool-call envelopes: one repair request, then a no-tools fallback if malformed output repeats. Blank final responses and output-length continuations have explicit finite budgets. Provider transport retries live in `nanobot/providers/base.py`, separate from tool execution.

`ContextGovernor.normalize_tool_result` in `nanobot/agent/context_governance.py` offloads oversized text to a session/call-specific file and returns a bounded preview plus readable reference. Follow-up file reads can retrieve the actual result. If offloading fails, the runner uses a bounded fallback instead of making persistence failure fatal. This avoids losing the only useful observation when a result is large.

**Lonora baseline gaps:** `ToolLoop` already returns `LonoraError` as an observation and `ToolArgumentsError.issues` enables same-turn correction. However, ordinary errors lose recovery metadata; the hard 120,000-character result guard replaces the entire result with `tool_result_too_large`; `advance_guard` counts the latest tool/argument hash without error classification and aborts at repetition six; retry timing/attempt state is not a coherent tool-environment contract. The existing context governor does preserve some operation identity when omitting results from model context; the earlier hard result guard must not erase that safety information first.

**Lonora owner:** extend existing tool metadata/registry, `ToolLoop`, bounded context governance and existing task/run checkpoint state. Retry state must survive restart. Safe-read recovery may continue; ambiguous mutations must use existing receipts/journal/reconciliation and must never be automatically reissued because a generic error looked transient.

### Restart and recovery

`SqliteSessionStore` in `nanobot/session/sqlite_store.py` uses WAL, `synchronous=FULL`, transactional writes, session revisions/generations and separate session/message/checkpoint/pending-input records. `SessionState` in `nanobot/session/state.py` owns short ordered mutations through bounded admission, one writer executor and detached reads. Model calls, tools and event publication occur outside SQLite write transactions. Shutdown rejects new operations and drains already admitted work.

Gateway startup claims process ownership before `SubagentManager.recover_interrupted` and `RecoveryCoordinator.scan`. `runtime_checkpoint_is_well_formed` verifies known phases, assistant/tool-call identities and matching completed/pending results. `restore_runtime_checkpoint` materializes the checkpoint once; pending tools become explicit interrupted results and are **not executed by restoration**. Unsynchronized provider continuation state is discarded.

`RecoveryCoordinator._recover_session` in `nanobot/webui/recovery.py` applies these policies:

| Persisted condition | Upstream result |
| --- | --- |
| Valid `final_response` | Restore the durable answer without new model/tool work. |
| `awaiting_tools` or pending calls | `awaiting_user`, reason `tool_state_unknown`. |
| Other valid interrupted work | `awaiting_user`, reason `restart_requires_confirmation`. |
| Unknown/malformed checkpoint | Discard unsafe checkpoint, expose review-only recovery state. |
| Already interrupted recovery attempt | Loop guard; require owner action. |

Newer owner input can supersede a recovery rather than being processed after obsolete work. Pending WebUI follow-ups are requeued from the durable journal. This is sound conservative recovery for a local assistant but intentionally does not meet Lonora's unattended safe-read/task recovery requirement by itself.

**Lonora stronger foundation:** `lonora_db.runs.claim_next/require_lease/renew_lease/checkpoint` use owner, expiry and incrementing fence; the obsolete worker cannot commit after takeover. `execute_run` renews the lease and cancels a worker that loses it. Tasks reuse existing tickets/runs and typed plan/control state. Financial effects and returned peer outcomes use durable receipts. Retain these mechanisms; add any new continuation, retry, wait and replay records under their same ownership boundaries.

### Subagent delegation and parent continuation

`SubagentManager._create_task` in `nanobot/agent/subagent.py` creates an owner-bound child session and task status before launching execution. Capacity/concurrency are bounded. `_build_tools` uses `ToolLoader.load(scope="subagent")` and isolated request/file/process context. `_run_admitted_subagent` uses the **same `AgentRunner`**, bounded task input, child transcript and selected runtime, not the entire parent's history.

Follow-up messages are bounded and have accepted/delivered/undelivered receipts. `_SubagentHook` updates actual phase, iteration, partial result and tool events. Cancellation seals the outcome before yielding, prevents late results from winning and keeps resistant processes tracked until cleanup really finishes. Execution errors, iteration-limit partial results and successful completion are distinct outcomes.

`_announce_result` checks parent/child ownership, publishes an attributed system inbound result with the parent's effective session key, and the existing session queue injects it or dispatches a later parent turn. `AgentLoop._persist_subagent_followup` durably records the child result before fallible prompt/model operations. Restart recovery marks active child tasks `interrupted` with `host_restarted`; it does not resume their tool execution.

**Lonora mapping:** `collaboration/subagents.py` already creates child `RunRow` and work thread with stable resource identity/depth limit; ToolLoop makes subagent/observe-only runs read-only. `collaboration/outcome_return.py` returns results under receipt/fence checks, repairs the commit/return crash window through `return_pending_outcomes`, and coordinates one synthesis run through existing collaboration state. Preserve read-only authority and durable result deduplication. Subagent capabilities must never amplify the parent's financial authority.

## Subsystem comparison and disposition

Dispositions below are engineering decisions, not a blanket implementation-complete claim. **ADOPTED** means the concept is already consistent with the retained Lonora architecture. **ADAPTED** identifies the concept to implement through existing Lonora ownership; behavioral verification belongs to the implementation matrix.

| ID | Actual Nanobot component and behavior | Lonora equivalent / relative strength | Decision and owner |
| --- | --- | --- | --- |
| N01 | `AgentLoop`, `AgentRunner`: one shared multi-step loop for channel, automation and child execution. | `AgentRuntime` → executor → ToolLoop already equivalent in architectural ownership. Failure classification is weaker at the baseline. | **ADOPTED**: retain one runtime; extend `packages/agent-runtime`, not a second agent class. |
| N02 | `AgentLoop._enqueue_session_message`, session inbox and injection snapshots preserve a sole worker per session. | PostgreSQL thread/run admission, steering and fenced commits support multiple workers and are stronger across process death. | **LONORA_ALREADY_STRONGER**: retain DB admission; use bounded, safely consumed steering at existing tool boundaries. |
| N03 | `SessionState`, `SqliteSessionStore`: ordered short writes, detached snapshots, bounded queue, generations/revisions. | Existing PostgreSQL transactions, ownership checks, leases/fences and typed durable entities. | **LONORA_ALREADY_STRONGER**: keep PostgreSQL source of truth; adopt short-transaction discipline, not SQLite/files. |
| N04 | Early persisted user input and pending WebUI follow-up journal prevent acknowledged input loss. | `send_message`, ordered messages, client nonce, steering rows. | **ADOPTED**: preserve message+run/steering atomicity and existing client nonce semantics. |
| N05 | Tool schema validation/coercion and useful same-turn errors. Exact tool name is required; suggestions are not execution aliases. | Pydantic input types, actual schemas, binding checks, `ToolArgumentsError.issues`. | **ADAPTED**: extend safe introspection/recovery metadata in `packages/tools`; no hidden symbol aliases or unsafe coercion. |
| N06 | Tool exceptions become observations; next runner iteration can repair or choose another action. | Existing ToolLoop catches domain errors but has incomplete error/recovery semantics. | **ADAPTED**: typed error category plus safe next action in the current ToolLoop; do not translate every failure into an owner request. |
| N07 | Per-turn repeated lookup/boundary throttles and finite blank/malformed/length recovery. | Durable `execution_state.guard` already persists call repetition, but lacks a meaningful classified failure route. | **ADAPTED**: bounded durable signatures/attempts and strategy change; authorization errors remain non-bypassable. |
| N08 | Oversized tool text offloaded with bounded preview, exact readable path and call/session ownership. | Artifacts and bounded model-context omission exist; hard ToolLoop size rejection loses helpful context. | **ADAPTED**: retain safe result identity/summary and targeted bounded read options through existing tools/artifacts. Never turn a successful financial effect into an apparent failure. |
| N09 | `ContextBuilder`: identity/bootstrap, memory, always-on skills, catalog, history summary and fresh input remain distinct. | Existing constitution, identity/binding, skills, memories, team/goals/evidence, transcript builder. | **ADOPTED**: reuse `context/builder.py` and existing skill runtime. No second prompt composition system. |
| N10 | `ContextGovernor`: token pressure, reserved output budget, actual provider usage, protocol-complete exchanges, portable summaries/provider compaction. | Lonora has character budgets, tool-exchange boundaries, durable history summaries and global router. Provider-specific accounting is less sophisticated. | **ADAPTED**: bounded operational summaries and complete exchanges remain mandatory; extend current governance when justified, not provider-native private state wholesale. |
| N11 | `RuntimeContextBlock` marks provenance, bounds selected quotes and separates model-only metadata from visible owner text. | Existing bounded scope/team/task/goal/evidence context; untrusted attachments have explicit envelopes. | **ADAPTED**: safe provenance and schema/error context inside existing builder; untrusted content cannot confer authority. |
| N12 | `SkillsLoader`: pinned snapshot while composing, always-on content plus progressive catalog/tool loading, dependency availability checks. | Installed skills registry/resolver/loader, mandatory constitution and skill selection already present. | **ADOPTED**: retain Lonora skills and exact capabilities; no directory-tree clone or replacement skill engine. |
| N13 | `MemoryStore`: workspace MEMORY/SOUL/USER files plus append-only history, monotonic cursors and bounded Dream batches. | Agent-owned PostgreSQL memory/versioning, semantic retrieval, explicit memory tools and bounded context. Lonora isolates agent ownership better. | **LONORA_ALREADY_STRONGER** on ownership/retrieval. Keep per-agent memory and existing retrieval; do not create magical shared memory across bots. |
| N14 | `Consolidator`, `MemoryArchiver`, `AutoCompact`: archive raw useful history, summarize at real boundaries, compact idle sessions under the same session lock. | `context/compaction.py` persists summary boundary under the lease; memory compaction/retrieval already exist. | **ADAPTED**: same-store safe bounded compaction; no automatic edits of financial authority or scope through learned memory. |
| N15 | Dream cron uses restricted file tools, cursor advances only on completed consolidation, and optional Git records durable edits. | Existing versioned memory, explicit memory commits and skill lifecycle. No need for a second background memory agent. | **ADAPTED** conceptually for bounded, provenance-aware learning; **NOT_APPLICABLE** for importing workspace Git/Dream scheduler mechanics. Owner: existing memory/automation. |
| N16 | Sustained-goal metadata and bounded continuation slices preserve objective and request origin after runner budget boundaries. | Typed Ticket task plan/run relationship, goals, controls, watches and scheduler exist; ordinary round-limit handling can still end useful work. | **ADAPTED**: continue/wait through existing task/run/checkpoint state; durable budgets must not reset on restart. |
| N17 | `/goal` plus `goal_requested` gates goal creation/replacement, disallowing peer/history authorization. | Lonora natural-language intent plus server-authoritative typed controls and financial grants. | **REJECTED_WITH_REASON** for mandatory command syntax. Retain provenance/authority boundary; model understands intent, server validates state. |
| N18 | Cron persisted JSON/action log, corrupt-store preservation, protected jobs, bounded run history and rearming. | PostgreSQL routines/scheduler/wakes already stronger for transactional deduplication and ownership. | **LONORA_ALREADY_STRONGER**: no JSON scheduler; preserve restart/corruption/duplicate-wake tests in existing automation. |
| N19 | Local trigger persisted inbox/processing/failed files, bounded attempts and startup requeue. | Existing durable event/wake ledger and broker/market state transitions. | **LONORA_ALREADY_STRONGER**: retain durable event identities/receipts; do not import at-least-once filesystem replay as financial execution. |
| N20 | Heartbeat parses active tasks and skips empty work, scheduled through normal cron. | Gateway process heartbeat is operational; routines/watches/tasks represent actual work. | **ADAPTED**: deterministic idle filtering and meaningful wakes; **NOT_APPLICABLE** for an LLM parsing a heartbeat file as authoritative task state. |
| N21 | Recovery validates phase, restores final answers once, marks uncertain tools and requires explicit restart continuation. | PostgreSQL fenced run takeover and safe effect reconciliation support unattended recovery. | **LONORA_ALREADY_STRONGER**: keep safe automatic takeover. **REJECTED_WITH_REASON** for requiring owner action on every process restart. |
| N22 | Private child sessions, bounded task context, concurrency, ownership, explicit outcomes and parent-session result routing. | Durable child runs, read-only restrictions, depth limits, peer outcomes and synthesis receipts. | **ADAPTED**: bounded context and truthful partial/status/results through existing collaboration. Do not import task/session authority shortcuts. |
| N23 | Child status persists, but restart seals active children as interrupted rather than resuming. | Existing child Run leases and outcome-return repair are stronger. | **LONORA_ALREADY_STRONGER**: maintain run recovery and receipt-fenced return. |
| N24 | `MCPProvider` owns long-lived connections/readiness, refreshes stale wrappers and closes resources in lifecycle order. | Current MCP tools build/initialize/close connectors per invocation. Explicit owner config and secrets remain server-side. | **ADAPTED** only when a persistent connector is needed: use existing adapters/gateway lifecycle, ownership and bounded connect waits. No new MCP runtime. |
| N25 | `MCPToolWrapper.execute` reconnects terminated sessions and retries some transient calls once after one second; timeouts are returned as errors. | Generic MCP mutation safety cannot be inferred from transport health. Broker mutations have journal/reconciliation. | **REJECTED_WITH_REASON** for blanket mutation replay. Adapt reconnection and retry only for proven safe/idempotent reads. |
| N26 | `MessageBus`: process-local inbound/outbound queues and ordered awaited subscribers; `publish_nowait` retains local dispatch tasks but is not a global FIFO. | PostgreSQL durable events/cursors plus transient reply streaming. | **LONORA_ALREADY_STRONGER**: preserve ledger vs stream distinction. No second bus or claims that a local async queue survives restart. |
| N27 | Channel allowlists/pairing, per-channel transport, optional `unified:default`, last-route tracking. | Owner/agent/thread identity and channel adapters; voice must use selected agent+thread. | **ADAPTED** for channel continuity, **REJECTED_WITH_REASON** for a global conversation merging distinct owners/agents or permissions. |
| N28 | Channel audio transcription forwards text to normal input; the studied loop is not a complete Lonora realtime voice transport. | `lonora_voice` already binds selected agent/thread, commits final transcripts and delegates through `send_message`. | **LONORA_ALREADY_STRONGER** in realtime foundation. Extend same-task steering/disconnect continuity; no Voice Agent or copied channel transcription runtime. |
| N29 | Foreground gateway owns channels/agent/MCP/cron/config watcher/triggers; file-locked process identity prevents duplicate local hosts, bounded shutdown drains resources. | Resident worker hosts existing Gateway, supervisors, services, heartbeat and shutdown. | **ADOPTED**: existing one Gateway remains owner; preserve supervised service loops and graceful drain, no second host process. |
| N30 | Upstream per-session model presets/provider state and runtime overrides. | Lonora explicitly uses a single global capability router with OpenAI/Anthropic/DeepSeek/Z.ai/OpenRouter configuration. | **REJECTED_WITH_REASON**: no per-agent/session model selection introduced by operating environment recovery. |
| N31 | Network DNS/IP validation, pinned request targets, redirect checks, SSRF guards; canonical workspace roots and optional bwrap/Seatbelt shell isolation. | Existing security/URL/runtime-storage boundaries and no general cloud-computer requirement. | **ADAPTED** boundary principles in existing security/adapters. **NOT_APPLICABLE** for importing shell/OS-computer capability solely to imitate Nanobot. Application path checks are not an OS sandbox. |
| N32 | Failed SSRF/workspace attempts become model observations with explicit non-bypass guidance; repetition is throttled. | Existing security and financial checks must remain authoritative even during recovery. | **ADOPTED**: recovery is never permission escalation or permission-bypass strategy search. |
| N33 | `AgentProgressHook`, runtime events, stage timing, usage, turn completion and notification-audience policy distinguish transport/lifecycle/interactive output. | Existing durable event projections, live state, attention/deduplication and public stable error codes. | **ADAPTED**: expose real phase/recovery/wait transitions via existing projection; not each retry as chat/spoken interruption. |
| N34 | Runner/history may retain `reasoning_content` and `thinking_blocks`; progress hooks emit reasoning deltas. | S19 explicitly forbids hidden reasoning storage/exposure. Operational summaries are sufficient. | **REJECTED_WITH_REASON**: persist actions, errors, evidence refs, public rationale and next safe state only. Do not copy private reasoning payload handling. |
| N35 | Plugins/tool entry points dynamically discover code, tolerate import failures and can overwrite some registered names with warnings. | Lonora explicit tool modules and duplicate registration rejection are easier to audit for financial authority. | **LONORA_ALREADY_STRONGER**: retain explicit safe registry; introspection metadata does not authorize arbitrary plugin code or collisions. |
| N36 | `LLMProvider` in `nanobot/providers/base.py` separates standard finite retries from persistent mode, honors Retry-After, caps persistent delay and stops after a threshold of identical transient errors. Changed transient errors can extend persistent mode without a total finite attempt count. | Lonora's global router owns provider retries/fallback; task/run state must own any longer wait budget. | **ADAPTED** for typed provider errors and bounded backoff; **REJECTED_WITH_REASON** for importing an effectively indefinite request loop or a second router. Persist retry state in existing durable work and release the worker while waiting. |

## Voice integration boundary in current Lonora

The real implementation already has `lonora_voice.sessions.create_voice_session` validating an owned agent/thread pair before paid negotiation; `voice_context` retrieves that agent's memory, scratchpad, live state and bounded history; `commit_transcript` ignores non-final speech and passes final speech to the same `send_message` admission path. `RealtimeVoiceSession.delegate` in `packages/voice/src/lonora_voice/realtime.py` waits for complete captured transcript segments, uses stable voice nonces and stores actual run IDs. Pending financial approvals remain button interactions rather than being converted into a new steering message. `barge_in.py` and bridge speech-interrupt state stop speech without declaring durable work cancelled.

These are stronger foundations than adding another voice reasoning loop. S19 still requires scenario verification that an active Task survives silence/disconnect, a later voice/text status question reads real task state and owner steering revises the same task safely. A realtime spoken acknowledgement alone is not task completion. Native Android acceptance cannot be inferred from TypeScript or this source study; the owner's current instruction prohibits building the application.

## Reference tests inspected and what they establish

| Source tests | Behavioral evidence inspected |
| --- | --- |
| `tests/agent/test_runner_errors.py` | Scripted model → thrown tool error → second model response; error remains an observation, not terminal goal failure. Typed error-result marker is distinguished from successful output beginning with the word Error. Cancellation/control flow propagates. Provider policy blocks do not execute returned tools. |
| `tests/agent/test_runner_core.py` | Complete tool exchanges, finite empty/length/malformed responses, provider state boundaries, no-tools finalization, finite iteration limits. Contains reasoning-preservation tests that Lonora deliberately must not copy. |
| `tests/agent/test_runner_goal_continue.py` | Live continuation can become active mid-turn; finite iteration budget remains enforced; no continuation after provider error. |
| `tests/agent/test_runner_persistence.py` | A 20,000-character result becomes a readable persisted file plus a bounded 2,048-character observation; follow-up and replay preserve the reference; storage failures do not end the tool loop. |
| `tests/agent/test_runner_governance.py`, `test_context_governance.py` | Actual request pressure, current input/tool block retention, provider compaction boundaries, orphan/missing tool-result repair in the model working copy, refusal of requests that still cannot fit. |
| `tests/agent/test_loop_recovery.py` | Explicit recovery continuation works without a sustained goal; request origin survives until new owner input, including late child results. It does not prove autonomous restart execution. |
| `tests/agent/test_session_atomic.py` and session-state tests | Private provider state, clear/fork behavior, transactional persistence/generation boundaries. |
| `tests/agent/test_subagent_control.py`, `test_subagent_lifecycle.py` | Bounded follow-ups/receipts, partial iteration-limit outcome, cancellation/late-result races, cleanup ownership, no sibling process cancellation and parent result routing. |
| `tests/agent/test_mcp_transient_retry.py`, MCP reconnect tests | Finite transient reconnect/retry, timeout not retried, non-transient errors not retried. These are transport tests, not financial at-most-once proof. |
| `tests/cron/test_cron_persistence.py`, `test_cron_active_rearm.py` | Atomic store saves, preserved corrupt files/action logs, active timer behavior and no accidental empty scheduler replacement. |
| `tests/triggers/test_local_triggers.py` | Persisted processing recovery, wait-for-turn-before-ack, interrupted delivery requeue, completed agent failures not redelivered and bounded audit content. |
| `tests/agent/test_runtime_context.py` | Bounded quote metadata, escaping envelope markers, model-only vs public-history separation. |
| `tests/agent/test_runner_safety.py`, security/network/workspace tests | Non-bypass boundary observations, repeated boundary-attempt throttle, network and path constraints. |

No upstream test was run against real money or production services by this study. None of these source tests verify Lonora behavior; Lonora must use its own scripted AgentRuntime, disposable PostgreSQL, simulation broker and recovery scenarios.

## Required Lonora acceptance work derived from the study

The implementation matrix must track these independently rather than marking S19 complete because this document exists:

1. Safe tool environment inspection with actual input schema, scope/authority/effect/retry metadata and stable error recovery contracts; never disclose configured secrets.
2. Scripted actual `AgentRuntime` loops proving invalid arguments repair, bounded oversized-result alternative, safe-read recovery and repeated-failure strategy change without another owner message.
3. Durable failure signatures, retry/backoff budgets and logical Task continuation across restart; worker takeover respects fences, completed task steps and effect receipts.
4. Existing broker recovery and mutation reconciliation as the only recovery owners; no tool-loop financial resend, even when the model changes tool-call IDs.
5. Same logical task for text/voice steering/status and disconnect continuation; no partial speech mutation or false acknowledgement-as-completion.
6. Parent/child bounded context, authority restriction, durable result return and one synthesis per collaboration round under duplicate events/restart.
7. Honest live state and attention routing backed by real durable transitions; failures preserve the understood goal and report actual execution blockers.
8. Current skill/task/market/trade/voice/collaboration regressions remain passing. S19 acceptance requires those scenario results and concrete external blockers; this study does not substitute for them.

## Cross-spec ownership constraints

- S01 skills and S04 task state remain the existing skills and ticket/run systems.
- S03 Super Bot and S05 exact specialist/Personal Agent scope do not gain authority from recovery metadata.
- S06/S07 collaboration/mentions remain explicit attributed state and retain permissions.
- S08–S13/S16/S17 evidence, market health, exposure, manual intervention, execution quality, journal and broker recovery remain domain authorities, not prompt-only recovery suggestions.
- S14/S18 attention/live projections consume useful transitions; raw internal attempts are not automatically notifications.
- S15 voice is a channel to the same identity, thread, tools, task, memory and authorization. It is not a source of new financial permission.

The result should be Lonora's existing persistent agent runtime with a coherent operating environment, not Nanobot plus a second state store, filesystem scheduler or adapter-specific retry engine.

## S19 comparative acceptance update (2026-10-18)

The36 dispositions above were revisited against the integrated code. Adopted/adapted behavior remains in Lonora's existing owners: safe registry introspection, typed operational observations, stable failure/operation identity, bounded safe-read retries with worker release, Task source waits/wakes, bounded charts/results, Agent-scoped event-based operational knowledge, revision provenance, actual live state, same-Task voice and active-host synthesis. Local acceptance references are in S19_ACCEPTANCE.md and the S19 matrix.

The stronger Lonora mechanisms were retained: PostgreSQL fences, read/work lanes, shared domain safety, approvals, exact symbol scope, journal/reconciliation and durable return receipts. Additional fault injection caught two important boundaries: unknown unreceipted effects cannot replay after a worker dies, and optional Goal current-step calls must freeze their first step/attempt so checkpoint recovery cannot select a later financial action. Legacy checkpoints without provable effect identity are fenced; only inspected legacy receipt paths opt into replay. A model-call rename does not create a new financial operation during reconciliation.

Rejected mechanisms remain rejected: command-only Goal activation, arbitrary MCP resend, private reasoning persistence, per-Agent model routing and a second local scheduler/state store. No source was imported. Native Android acceptance remains blocked under the owner's no-build instruction; the source study does not certify native microphone, WebRTC or device behavior.
