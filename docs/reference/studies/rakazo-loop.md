# Rakazo: agent loop and harness

Scope: how one agent turn runs end to end in `elie222/rakazo` (pnpm/turbo monorepo, Hono + oRPC API, a separate worker process, React/Expo clients, and `packages/adapters` which holds the loop). All paths are repo-relative. This was read-only static study; nothing was run.

Headline: **a run is a Postgres row with a lease, not an in-memory loop.** The API only writes `messages` / `tasks` / `runs` rows and nudges. A worker claims the run under a fencing token, assembles a prompt, drives a third-party agent loop (`@earendil-works/pi-agent-core` "Pi", v1.6.0) through a streaming adapter, and mirrors Pi's events into an append-only per-thread `events` table that clients tail. Everything that can pause, crash or hand over (questions, approvals, takeovers, shutdown, DB outage) is a checkpoint plus a requeue of the same run.

## 1. Moving parts

| Concern | Where |
|---|---|
| Message entry | `apps/api/src/routes/threads.ts` (`send`) -> `apps/api/src/threads/thread-target.ts` (`sendThreadMessage`) |
| Dispatch | `packages/adapters/src/runs/wakeups/run-wakeup.ts` (`RunJobPublisher`, `RunStarter`, `RunWorkerHost`), `wake-run.ts`, `background-job-handlers.ts` |
| Executor | `packages/adapters/src/runs/executor/executor.ts` (`createRunExecutor().continueRun`) |
| Lease / lifecycle | `runs/lifecycle/run-attempt.ts` (`claimRunAttempt`, `holdRun`, `releaseRunHold`), `run-lifecycle.ts` (`claimRun`, `retryRunSetup`, `requeueInterruptedRun`, `renewRunLease`) |
| Prompt assembly | `runs/assembly/run-assembly.ts` (`assembleRunTurn`) and `run-assembly-{records,history,capabilities,context}.ts` |
| Turn driver | `runs/turn/run-model-turn.ts` (`runModelTurn`, `modelTurnRequest`), `run-turn.ts` (`consumeRunEvents`) |
| Model loop + provider abstraction | `runtime/pi/pi-runtime.ts` (`PiAgentRuntime.runEvents`), `pi-runtime-fallback.ts`, `pi/stream/pi-runtime-stream.ts`, `pi/tools/pi-runtime-tools.ts` |
| Tool execution | `runs/tools/run-tools.ts` (`applyTool` -> `dispatchTool`), `runs/tools/run-tool-gate.ts` (`gateToolCall`) |
| Context policy / compaction | `runtime/context/runtime-context.ts` (`createRuntimeContextPolicy`), `context-selection.ts`, `context-pruning.ts`, `history-compaction.ts` |
| Persistence of events | `packages/db/src/threads/events.ts` (`appendEvent`, `finalizeRun`), `event-stream.ts` (`followThreadEvents`) |
| Realtime fanout | `packages/adapters/src/notifications/realtime.ts` (`PostgresRealtimeFanout`, `pg_notify`) |
| Scheduled work | `runs/assembly/run-routines.ts` (`wakeRoutine`), `wakeups/job-reconciler.ts`, Graphile worker (`wakeups/wakeup.ts`) |
| Worker process | `apps/worker/src/index.ts` |
| UI watch | `apps/api/src/routes/threads.ts` (`threads.subscribe`), `packages/core/src/threads/thread-subscription.ts` (`runThreadSubscription`), `apps/web/src/pages/shell/chat/use-thread-sync.ts` |

## 2. One turn, end to end (numbered control flow)

### A. Entry and run creation (API process)

1. Client calls the oRPC `threads.send` handler in `apps/api/src/routes/threads.ts` (the local `send` closure). It checks a model is configured (`modelSetup`, `MODEL_REQUIRED_SEND_ERROR`; a bare "stop" is exempt), resolves the target (`resolveThreadTarget`) and calls `sendThreadMessage`.
2. `sendThreadMessage` (`apps/api/src/threads/thread-target.ts`) first replays a duplicate send via `replayExistingSend` keyed on `clientNonce` (idempotent retries). Then one `prisma.$transaction`:
   - takes `SELECT id FROM threads WHERE id = ... FOR UPDATE` (the per-thread serialisation point),
   - creates the user `message` (`createThreadMessageInTransaction`),
   - loads `activeRuns` for the bot/thread,
   - branches: (a) a `waiting_input` run owned by the sender gets the text as its answer (`answerWaitingRunWithTextInTransaction`), (b) a bare "stop" calls `cancelThreadRuns` (`thread-stop.ts`), (c) a run is already active: creates a `steeringMessage` row so the running turn picks it up mid-flight, (d) otherwise `tx.task.create` + `tx.run.create({ status: "queued", trigger: "user", clientNonce, sourceMessageId })` and `cancelSupersededQueuedRuns`.
   - appends a `thread.message.created` event in the same transaction (`appendEventInTransaction`).
3. After commit, `enqueueRunsNeedingContinue(deps.jobs, runs)` (same file; also used by `thread-retry.ts`, `thread-reactions.ts`) calls `wakeRun` (`runs/wakeups/wake-run.ts`) which enqueues a `run.continue` job. `wakeRun` never throws: "the run row is the durable record and recovery starts a run whose nudge was lost".
4. In the worker, `RunJobPublisher.enqueue` (`wakeups/run-wakeup.ts`) turns `run.continue` into `UPDATE runs SET wakeAt = ... WHERE status IN (queued, waiting_input, waiting_takeover)` plus `RunStarter.start(runId, at)`. Other job names go to Graphile (`GraphileJobPublisher`, `wakeups/wakeup.ts`). If the API process is not the one with handlers, `RunStarter.handOff` publishes the run id on realtime topic `runs:ready` (`pg_notify`) and a worker takes it via `RunStarter.take`.

### B. Claiming (worker)

5. `RunStarter.begin` dedupes per run (`inFlight` / `dueAgain` sets), admits through `RunExecutionHost.execute(..., { waitForCapacity: false })` and calls `dispatchBackgroundJob(handlers, "run.continue")` -> `background-job-handlers.ts` `"run.continue"` -> `executor.continueRun(runId, workerId, onRunStarted)`.
6. `continueRun` (`runs/executor/executor.ts`): `findContinuableRun` (`run-attempt.ts`: refuses if the process is stopping, run is terminal, account deactivated, or sender left the Space) -> `claimRunAttempt` -> `holdRun`.
7. `claimRun` (`run-lifecycle.ts`) is a single fenced `updateMany`: status in (queued, waiting_input, waiting_takeover) or (leased/running with expired lease), `wakeAt` due, sets `leaseOwner`, `leaseFence = nextFence(...)`, `leaseExpiresAt = now + 5 min`, `checkpoint = null`; then `leased -> running`. Only one worker can win. `claimRunAttempt`/`startClaimedAttempt` then creates an `attempt` row; may take a `computerExecutionLease` (only for takeover resumes; ordinary turns take the computer lazily on first tool use).
8. `holdRun` (`run-attempt.ts`) returns a `RunHold`: `withRunLease(...)` wraps `deps.events.append` so **every event write for this run carries `{owner, fence}`**, plus a 60 s `setInterval` heartbeat that calls `renewRunLease` / `renewComputerExecutionLease`. If renewal fails (and no DB outage grace remains) `lease.valid=false` and `abort.controller.abort()`.
9. `onRunStarted()` is invoked right after claim so "model, integration and computer setup must not occupy a queue dispatch slot".

### C. Prompt and context assembly

10. `assembleRunTurn` (`runs/assembly/run-assembly.ts`) runs a fixed pipeline: `loadSavedTurn` (checkpoint of a paused turn) -> `loadRunRecords` -> `connectRun` (abort controller, memory scope, connectors) -> `readThreadHistory` -> `loadTurnContext` -> `startTurnModel` (model choice, pin checks, backups) -> `prepareRunComputer` -> `resolveRunCapabilities` -> `selectRunTools` -> `loadComputerInstructions` -> `createRunContext` -> `buildTurnPrompt` -> `turnMayStillStart` -> `loadModelFallbacks`. Returns undefined if setup ended or handed back the run.
11. History: `readThreadHistory` (`run-assembly-history.ts`) maps stored messages to history entries with speaker labels (`history-speakers.ts`), neutralised in groups (`neutralizeSpeakerLabels`) and, when the same bot replays its own tool history, the exact stored transcript (`messageTranscript` -> `mapTurnTranscript`). `selectCompactedHistory` (`runtime/context/history-compaction.ts`) uses a thread summary only if the messages after the cursor are contiguous, else keeps the full window.
12. `loadTurnContext` loads in parallel: images for the turn, `loadAgentMemoryContext` (`memory/memory-context.ts`), scratchpad (`runtime/context/scratchpad-context.ts`), tickets, and optional semantic recall (`semanticMemory.recall`, only when history was compacted or the provider recalls each run). Saved context is hidden for non-owner chat runs and owner-computer routines (`savedContextHidden`).
13. `buildTurnPrompt` (`run-assembly-context.ts`) builds the user-turn `prompt` string: reply context, meeting context, routine note, task prompt (skill references expanded), takeover/approval continuation notes, and a `<current_time>` block (per-turn on purpose: "the timestamp changes every call and would break the cacheable prefix"). `runtimeHistory = [compacted summary, kept history, recalled memory]` with recall placed last to keep history a cache-reusable prefix.
14. The system prompt is `userTurnInstructions(...)` in `runs/assembly/run-instructions.prompt.ts`, called from `modelTurnRequest` in `runs/turn/run-model-turn.ts`: platform instruction, bot instructions, history-retrieval guidance, tool usage line, computer/workspace instructions, bot directory, skills lines, reply guidance. The result is `AgentRunRequest` (`packages/adapter-kit/src/types.ts`) with `tools`, `history`, `model`, `fallbackModels`, `executeTool: applyTool`, `claimSteering`, `onToolCompleted`, `onUsage`, `onTranscript`, `turnCheckpoint`.
15. `promptVersion()` (`assembly/prompt-version.ts`) is stamped on the run row for release comparison (best effort).

### D. Model call and Pi loop

16. `runModelTurn` calls `deps.runtime.run(request, {signal})`, which is `PiAgentRuntime.run` -> `runEvents` (`runtime/pi/pi-runtime.ts`), an async generator fed by a queue (`createQueue`). Runtime is swappable: `PiAgentRuntime` or `ScriptedAgentRuntime` (`runtime/scripted-runtime.ts`, chosen by `AGENT_RUNTIME=scripted` in `apps/worker/src/index.ts`) or an ACP CLI runtime (`runtime/acp/acp-runtime.ts`, which reuses `toAgentTools`).
17. `runEvents` builds a Pi `Agent` with `streamFn` = `uniqueToolCallIdStream(fallbackAwareModelStream(state, ctx, opts))`. Pi (third party, **not in this repo**) owns the core loop: call model -> collect tool calls -> run tools (parallel unless any call is `executionMode: "sequential"`) -> append results -> repeat until a turn has no tool calls, is aborted, or a hook returns `{action:"end"}`. Rakazo hooks: `finishTurn` (end on pause / terminating reply / tool budget; hand back between steps on shutdown), `prepareNextTurnWithContext` (claim steering messages and inject them as user messages before the next model request; also swap model/tools for computer mode).
18. Provider abstraction is Pi's `@earendil-works/pi-ai` (`Models.streamSimple`), wrapped by `reliableModelStream` (`pi/stream/pi-runtime-stream.ts`): header timeout (`MODEL_STREAM_TIMEOUT_MS=120s`), idle watchdog after a 2xx (`MODEL_STREAM_IDLE_TIMEOUT_MS=180s`, relabels aborts as "Model stream idle timeout"), `maxRetries` default 1 (`DEFAULT_MODEL_STREAM_MAX_RETRIES`, forced to 0 when backups exist). Codex is forced to SSE. Usage is recorded through `observedPiStream` (`pi/usage/pi-usage.ts`) and `onUsage`.
19. Context shaping before every call: `prepareContext` -> `createRuntimeContextPolicy().prepareContext` (`runtime/context/runtime-context.ts`). Default strategy is `DEFAULT_CONTEXT_STRATEGY = "retrieval"` (`adapter-kit/src/types.ts`): old turns become navigation snapshots (`navigationSnapshotsPrompt`) and the model uses `search_history` / `read_history` tools; old tool results are shortened (`shortenToolResultText`); the sent prefix is kept stable for provider prompt caching and only "rebuilt" when `rebuildPaysOff(...)` says the stale content saved outweighs the cache miss (a cost model: rebuild when `stale^2 >= 25 * fresh * growth`).
20. Tool call parse/validate: Pi validates arguments against the TypeBox/JSON schema (`validateToolArguments`) after Rakazo's per-tool `prepareArguments` coercion in `toAgentTool` (`pi/tools/pi-runtime-tools.ts`). Tool names are sanitised to `^[a-zA-Z0-9_-]{1,64}$` with stable-hash suffixes (`normalizeAgentToolNames`). Tool call ids are made unique per run (`runs/turn/tool-call-ids.ts`).
21. Tool execute (`toAgentTool(...).execute`): abort check -> if `host.pausePending` skip -> `host.captureCheckpoint` (saves the turn before the effect) -> `beginToolCall` (optional `MAX_TOOL_CALLS_PER_TURN` fuse) -> push `{type:"tool"}` event -> special cases (`request_takeover`, `ask_user`, `request_secret`, `find_tool`) -> otherwise `host.request.executeTool` = `applyTool` (`runs/tools/run-tools.ts`). Results are clipped (`boundAgentToolResult`, `TOOL_RESULT_TEXT_LIMIT = 12_000`). `executionId = JSON.stringify(["pi-tool", namespace, providerToolCallId])` is the idempotency key.
22. `applyTool` -> `dispatchTool`: a long list of refusal gates (disabled tool, helper-hidden tool, not-offered for owner-computer routines, page browser, image-capable), `resolveToolRequest`, `prepareToolRequest`, then `gateToolCall` (`runs/tools/run-tool-gate.ts`): decides run / ask owner for approval / auto-review (`turn/run-auto-review.ts`) / refuse, and records an `externalEffect` (claim/replay). Approved replays are drained (`approvedReplays.assertDrained()`). Handler results are audited (`auditToolCall`, `appendToolCompletionAudit`).
23. The result goes back to Pi as a `toolResult` message; Pi loops. Deferred tools are reached through `find_tool` + `use_tool` (`tools/lazy-tool-catalog.ts`, `toAgentTools` partitions via `partitionTools`), which unwraps to the real tool before gating.

### E. Streaming back to the UI during the turn

24. Pi events are translated in `agent.subscribe(...)` in `pi-runtime.ts` into `AgentRuntimeEvent`s on the queue: `text`, `thinking`, `tool`, `progress` (activity lines), `turn`, `steered`, `ask`, `takeover`, `subagent`, `usage`, `yielded`, `done`. It de-duplicates streamed vs completed text, handles cut replies (continuation prompts, `MAX_SELF_RECOVERIES_PER_RUN = 3`) and empty-reply repeats.
25. `consumeRunEvents` (`runs/turn/run-turn.ts`) is the only consumer: for each event it re-checks the lease (`runLeaseLost`, throttled to one DB read per second, plus a 1 s watchdog timer so Stop is seen during quiet model calls), then `streamText` batches text deltas at most every 250 ms into `thread.progress` events (`flushProgress`, `lifecycle/run-progress.ts`), `onToolCalled` (`run-turn-tools.ts`) appends `agent.tool.called`, `thread.meta {activity:{thinking}}` marks thinking, `publishSubagent` writes `thread.subagent`. Secrets are redacted on the way out (`reply.redactor`, `redactSecrets`).
26. Every append is `appendEvent` (`packages/db/src/threads/events.ts`): one autocommit CTE that bumps `threads.nextEventSeq`, checks `runs` row with `FOR SHARE` using the lease (`r."leaseFence" = fence AND leaseOwner = owner`; cancelled runs write nothing), and inserts into `events`. Then `notifyRealtime` -> `pg_notify('rakazo_events', {topic:"thread:<id>", payload:{cursor}})`.

### F. Stop conditions

27. Normal end: Pi ends when a model turn has no tool calls. `pi-runtime.ts` then resolves the final text (`toolWorkPendingFinal` tracks "tools ran but no final prose yet"; one `followUp` nudge up to `MAX_SILENT_TOOL_CONTINUATIONS`, otherwise `ModelOutputError(MISSING_TOOL_FINAL_RESPONSE_ERROR)` unless `allowSilentEmpty`), pushes `{type:"done"}`. `consumeRunEvents` returns false and `runModelTurn` calls `completeRun` (`lifecycle/run-complete.ts`).
28. Other ends: (a) tool pause (`ask_user`, approval, `request_secret`, takeover) sets `host.pausePending`, the tool returns `terminate: true` and `host.abortTurn()`; the executor calls `pauseForAnswer` / `pauseForTakeover` (`turn/run-turn-pause.ts`) which persists the checkpoint and calls `events.pauseRunForInput` / `pauseRunForTakeover`; (b) tool-call fuse `toolCallBudgetFor`; (c) **loop guard** in `onToolCalled` -> `advanceToolCallLoopGuard` (`turn/tool-loop.ts`): same call with same args failing 6 times (`MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS`), digit-only-different calls 25 times, same tool returning the same result 25 times, or over-limit `computer_act` batches 4 times; then `stopStuckToolLoop` aborts the runtime, flushes, and *completes* the run with a user message "I got stuck calling X ..." (a stop, not a failure); (d) lease lost / cancelled -> return true, nothing more is written; (e) shutdown -> `finishTurn` hands back between steps.
29. `completeRun`: flush computer checkpoint, `finalReply` assembles blocks (silent-reply rules in `assembly/silent-reply.ts`, `NO_RESPONSE` sentinel), `renewRunLease`, then `events.finalizeRun` (`db/threads/events.ts` `finalizeRunOnce`): one transaction under the thread lock that moves run `running -> completed|failed` fenced by owner+fence, closes `attempt` and `task`, creates the bot `message` (+ `toolHistory` with transcript), appends `thread.message.created` and `run.completed|failed`, **deletes transient events** (`thread.progress`, thinking meta) for the run, deletes run secrets, releases/consumes steering rows, and `createPendingSteeringRun` (a continuation run for messages that arrived while the run was ending). After it: `enqueueConversationRetention` (`memory.retain-turn` job), `enqueueHistoryCompaction` (only when strategy is `"current"` and `shouldEnqueueCompaction`), routine bookkeeping.

### G. Release

30. `finally { releaseRunHold }` -> `finishRunAttempt` clears heartbeat, releases the computer lease, settles helpers and starts the next waiting run for the same bot (`startNextWaitingRun`: person-triggered runs before background). The `run.continue` handler then calls `publishSpaceChange(spaceId,"runs")` and delivers messaging replies.

## 3. Retries, backoff, fallback (three layers)

1. **Inside one model call** (`pi-runtime-fallback.ts` `fallbackAwareModelStream`, `run()` loop):
   - Same-model repeats with `MODEL_PROVIDER_RETRY_DELAYS_MS = [2s, 8s, 20s]`, bounded by the per-attempt `timeoutMs` budget.
   - Reactive fixes without a backup: learn the real context window from the provider error and re-prepare (`reportedContextWindow`, `onContextLimit`, `groqRequestContextWindow`), reduce output reservation (`affordableOpenRouterOutput`, `state.outputCaps`), narrow rejected reasoning efforts (`acceptedReasoningEfforts`), drop thinking blocks on signature mismatch (`isThinkingSignatureMismatch`, `withoutThinkingBlocks`), repeat an empty reply `EMPTY_REPLY_RETRIES = 2`, continue cut replies.
   - Token pacer for local providers (`models/endpoints/token-pacer.ts`).
2. **Backup models** (`resolveNext` / `switchToNext`): `request.fallbackModels` are resolved lazily per credential (`resolveFallbackModel`), skipped with a recorded reason if incompatible (`fallbackIncompatibility`: credentials, tool/context/image fit via `prepareForTarget`), and switching persists the new model on the run row through `onModelChange` (fenced update) so retries/pins rerun it. The final error aggregates outcomes (`modelFallbackFailure`). Only before any visible output.
3. **Run level**:
   - Setup failure -> `retryRunSetup` (`run-lifecycle.ts`): requeue with `computerRetryDelay(fence) = min(10s, 250ms * 2^(fence-1))` (or `providerOutageRetryDelay` 15s..5min for sandbox/provider outages), counted by `setupFailureStreak` over `attempt` rows; fails after `RUN_SETUP_FAILURE_LIMIT = 8`. Computer-busy and DB outages retry forever without counting.
   - DB outage mid-turn -> `requeueRunAfterDatabaseOutage` (checkpoint flush then requeue; `retryWhileDatabaseUnavailable` on every fenced write).
   - Turn failure -> `failRun` (`lifecycle/run-fail.ts`) -> `finalizeRun(outcome: "failed", retryable)`. User runs get a user-driven retry (`thread-retry.ts`) when it was fence 1, a `TransientModelError`, no tool started and no partial reply. Routines get `scheduleRoutineRetry` (`run-routines.ts`: one retry after `ROUTINE_RETRY_DELAY_MS = 12 min`, only if no tool ran and no message was posted), repeated failures pause the routine (`pauseRoutineAfterRepeatedFailures`).
   - Stale leases: any `leased|running` run whose `leaseExpiresAt <= now` is rescanned and re-claimed (`RunWorkerHost.scanLane`); the new claim bumps the fence so the old attempt's writes are rejected.

## 4. Cancellation

- Stop button or bare "stop" text -> `cancelThreadRuns` (`apps/api/src/threads/thread-stop.ts`): under the thread lock, marks active runs (and helper runs started from that chat) `cancelled`, clears steering, writes `run.cancelled`; `finishThreadStop` cancels computer work.
- The worker notices through the fence/status check in `runLeaseLost` (1 s throttle + 1 s watchdog timer) -> `ctx.abortController.abort()` -> `withRuntimeCleanup` (`runtime/runtime-stream.ts`) aborts executor tool work before closing the iterator -> `PiAgentRuntime.run().return()` aborts Pi. Late writes from the cancelled attempt are rejected by `appendEvent`'s `r.status <> 'cancelled'` predicate.
- `turnMayStillStart` rechecks status/lease just before opening the model stream (stop during setup must not open the model).

## 5. Concurrency (agents, subagents, computers)

- **Between runs of one bot/thread:** serialised by the thread row lock in the send transaction; if a run is active the new message becomes a `steeringMessage` and is injected into the *running* turn at the next step boundary (`prepareNextTurnWithContext` -> `claimRunSteering` -> `events.claimSteering`, also emits `{type:"steered"}` so the UI can split the reply). `cancelSupersededQueuedRuns` drops queued runs superseded by a newer send.
- **Between runs of different bots / processes:** `RunStarter` runs each run as its own task, no queue ordering; `RunExecutionHost` bounds in-flight work per process; others get the run through `runs:ready`. `RunWorkerHost` scan has two lanes (interactive vs `routine`/`reaction`) paged by `(createdAt,id)` so background work cannot starve chat.
- **One run per bot computer:** `computerExecutionLease` (`computers/computer-lifecycle.ts`): runs that find it held requeue *without a timer* (`requeueComputerRun(..., untilReleased)`) and the releasing run calls `startNextWaitingRun`. `findRunRecoveryBlockers` skips runnable rows blocked by a takeover hold and expires abandoned holds.
- **Subagents ("helpers"):** `run_subagent` tool -> `startBackgroundHelper` (`tasks/background-helpers.ts`): inside a thread+bot lock it inserts a *separate run* with trigger `BACKGROUND_HELPER_TRIGGER` and a `subagent` card message; cap `MAX_PARALLEL_SUBAGENTS = 4`; helper runs cannot call hidden tools (`SUBAGENT_HIDDEN_TOOLS`) and cannot start helpers; the result comes back as a `HELPER_RESULT_TRIGGER` run (`returnHelperOutcome`). So subagents are first-class runs in the same table, same lease and event machinery, not in-process sub-loops.
- **Agent to agent:** `bot_message` trigger runs; `returnBotMessageOutcome` (`messaging/bot-messages.ts`) posts the result/status back to the requesting bot.
- **Worker leadership:** one reconciler leader via Postgres advisory lock (`createPostgresReconciliationLeadership`, `pg_try_advisory_lock`).

## 6. Long-running / always-on work

- **Schedules ("routines"):** `routine.wakeup` job (Graphile, `routineWakeupJob(routineId, scheduledFor)`). `wakeRoutine` (`runs/assembly/run-routines.ts`) validates `routine.nextRunAt === scheduledFor` (stale-wake guard), checks active / Space deletion / owner deactivation / `endsAt`, runs an optional model-free **watch tick** first (`tickRoutineWatch` in `routines/routine-watch.ts`; only "news" becomes a run), then in one transaction advances `nextRunAt` (so the *next* wake is always enqueued), coalesces onto a pending tick (`findPendingRoutineTick`), skips if the previous tick is still active, dedupes by `clientNonce = routineTimerNonce(routineId, scheduledFor)`, creates `task` + `run(trigger:"routine")`, then `wakeRun` and a `routine.fired` event. Late runs are tagged (`lateSince`).
- **Delayed / waiting runs:** `runs.wakeAt` is the single timer. `RunStarter.start(runId, at)` keeps an in-process `setTimeout` as an optimisation; the durable truth is the row, rescanned every 5 s by `RunWorkerHost` (interval) and on `runs:ready`. `waiting_input` / `waiting_takeover` runs with `wakeAt <= now` are also resumed (expiry path).
- **Reconcilers:** `job-reconciler.ts` (30 s interval, leader only) re-enqueues routines/controls due soon, handles abandoned queued locks, stuck waits (`lifecycle/stuck-work.ts` -> reminders and expiry via `expireStuckRun`), bot-message outcomes, call requests. `reconcileComputerRuns` (`@rakazo/db`) not read.
- **Graceful drain:** `drainRuns` + `RUN_DRAIN_MS = 5 min` in `run-wakeup.ts`; on shutdown the process stops claiming, keeps renewing leases, and each run hands itself back *between steps* via `finishTurn` -> `{type:"yielded", checkpoint}` -> `handBackBetweenSteps` (saves reply + checkpoint, `requeueInterruptedRun`) so the next worker resumes with the next model call instead of repeating one.
- **Memory/compaction jobs:** `memory.retain-turn`, `history.compact` (`background-job-handlers.ts`). The `history.compact` handler early-returns unless `contextStrategy` is `"current"`; since the default is `"retrieval"`, compaction summaries are the legacy path.
- Not found/read: a free-running "daemon" agent loop. Always-on behaviour is entirely schedules, watches, wakeups (`wakeAt`), webhooks/messaging inbound triggers and bot-to-bot messages, each creating a normal run.

## 7. Persistence of runs and events

- Tables touched (from code, schema file not read): `runs` (status, trigger, `leaseOwner`, `leaseFence`, `leaseExpiresAt`, `wakeAt`, `checkpoint`, `clientNonce`, `modelProvider/modelId/modelPinned`, `promptVersion`, `firstResponseAt`), `attempts` (one per fence), `tasks`, `messages` (+ `toolHistory` with exact transcript), `steering_messages`, `events` (per-thread monotonic `seq` from `threads.nextEventSeq`), `external_effects` (tool idempotency + `RUN_TURN_CHECKPOINT_KIND` rows), `computer_execution_leases`, `run secrets`.
- Status machine `queued -> leased -> running -> completed|failed|cancelled`, side states `waiting_input`, `waiting_takeover` (`ACTIVE_RUN_STATUSES`, `assertTransition`).
- Turn checkpoint (`runs/turn/turn-checkpoint.ts` `TurnCheckpoint`): provider/model, system prompt, `messages`, `pendingToolCallId`, `effectOccurrences`, `toolCallCount`, optional `reply`. Saved *before* each tool executes (`host.captureCheckpoint`) and on pause (`persistTurnCheckpoint`). On resume `pi-runtime.ts` replays unresolved tool calls (parallel siblings get an "uncertain effect" error result; the pending call is re-executed through the idempotent gate, or answered with `resumeToolResult` for ask/takeover).
- Optional Pi JSONL session recording (`runtime/pi/pi-session.ts`, `PiJsonlSessionRecorder`) per run for debugging; gated on `context.userId`.

## 8. How the UI watches progress

1. Initial load: `threads.get` (`threadSnapshot` in `apps/api/src/threads/thread-snapshot.ts`) returns messages + `cursor` (last event seq) + active runs.
2. `threads.subscribe` (oRPC async generator in `routes/threads.ts`) wraps `deps.events.follow(threadId, cursor, signal)` in `withHeartbeats`, filters peer/background-run events (`shouldForwardPeerThreadEvent`, `shouldForwardBackgroundThreadEvent`) and emits `heartbeat` frames.
3. `followThreadEvents` (`db/threads/event-stream.ts`): `eventsAfter(seq)` in batches of 200, then waits on a `ChangeLatch` woken by the Postgres NOTIFY (`threadTopic`), with a periodic catch-up poll (30 s push mode / 400 ms poll-only). Missed NOTIFYs are therefore harmless: the cursor is the truth, NOTIFY is only a wakeup.
4. Web: `runThreadSubscription` (`packages/core/src/threads/thread-subscription.ts`, shared by web and mobile) loads head, subscribes from the cursor, reconnects with backoff (`reconnectDelayMs`, respects 4xx as terminal and 429 Retry-After), treats `IDLE_TIMEOUT_MS = 45 s` without a frame as a half-open stream, and replays events from storage if its snapshot is stale (phases `snapshot` / `replay` / `live`). `useThreadSync` (`apps/web/src/pages/shell/chat/use-thread-sync.ts`) applies each event through `reduceThreadSnapshot` (`packages/core/src/threads/thread-snapshot-events.ts`, not read in full).
5. Transient events (`thread.progress`, thinking) are deleted at `finalizeRun`, so history stays small and a reload shows only durable messages. Space-level lists use `publishSpaceChange(spaceId, "runs"|"routines")` topics (`followSpaceChanges`).

## 9. Clever things worth noting

- **Fenced writes everywhere.** The lease `(owner, fence)` is baked into `withRunLease` so a stalled worker physically cannot write after reclaim: the append SQL checks the run row `FOR SHARE`. This removes whole classes of split-brain without distributed locks.
- **Run row = queue.** `wakeAt` + status + lease replaces a job queue for runs; the job system is just a nudge. Recovery is a 5 s scan of due/expired rows with lane fairness, and handoff is `pg_notify`. Very few moving parts, no Redis.
- **Checkpoint before effect + idempotent effect keys** (`executionId`, `external_effects`) make pause/resume/crash safe for side-effecting tools.
- **Drain by handing back between steps** (`yielded`) rather than killing turns.
- **Loop guard with result fingerprints** (`toolResultFingerprint`): distinguishes polling a changing page from a stuck loop, and ends the run as a clean, explained stop.
- **Steering instead of queueing**: new user messages during a run are injected into the next model request, with an event so the UI can break the bubble.
- **Provider resilience is layered and stateful per run**: learned context window, learned output cap, learned accepted reasoning efforts, dropped thinking signatures, cut-reply continuation with overlap trimming, empty-reply repeat, lazy per-credential backups.
- **Cache-aware context policy** with a cost model for when to rebuild the prefix; per-turn volatile data (time, recall) deliberately placed after the stable prefix.
- **Subagents as runs**: reuse all lifecycle machinery, visible as cards, cancellable from the chat, capped.
- **Prompt data is wrapped as untrusted** (`escapePromptData`, `<compacted_thread_summary>`, "untrusted historical data, not instructions") and secrets are redacted both ways (`redactSecrets`, `reply.redactor`).

## 10. Weaknesses / risks

- **Core loop is a third-party dependency** (`@earendil-works/pi-agent-core`/`pi-ai` 1.6.0). Much of `pi-runtime.ts` (1400 lines) is compensating for Pi behaviour (parallel result publishing, abort messages, steering poll timing). Upgrades are risky; the hooks used are not a public contract we control.
- **Size and coupling.** `assembleRunTurn` threads ~15 intermediate objects (`records`, `connected`, `turnContext`, `capabilities`, `tools`, `ctx`, ...) with type aliases `Awaited<ReturnType<...>>`; `pi-runtime.ts` and `pi-runtime-fallback.ts` (969 lines) are dense stateful closures. Hard to test or port in isolation.
- **Postgres is the single backbone** (events, realtime NOTIFY with a 7.9 KB payload cap, advisory-lock leadership, queue). A saturated pool is a recurring theme (`retryWhileDatabaseUnavailable`, `databaseOutage`, "53300" handling in `apps/worker/src/index.ts`).
- **Per-event DB round-trips**: each progress/tool event is a CTE touching `threads`, `runs`, `events`; text is throttled to 250 ms but tool/activity events are not.
- **1 s polling of the run row** while streaming, per active run (`runLeaseLost`).
- **At-least-once tool repeats are mitigated, not eliminated**: a turn cut mid-step "repeats its model call and tool call on the next process" (comment in `run-wakeup.ts`); effect idempotency relies on every tool going through the gate.
- **Routine retry is a single fixed 12 min retry** and only when nothing visible happened; user runs only get a user-driven retry.
- **Default context strategy "retrieval"** makes history quality depend on the model using `search_history`; the legacy summary compaction is effectively dormant (gated on strategy `"current"`).
- **Not read:** the Prisma schema, `reconcileComputerRuns`, `thread-snapshot-events.ts` reducer details, the approvals internals (`approvals/*`), and the ACP runtime beyond its imports. The Pi library's own loop code was not available to read.

## 11. What Lonora should copy / avoid

Lonora is FastAPI + React web + Expo mobile, a trading assistant. The domain raises the cost of duplicate or phantom side effects, which makes several Rakazo ideas directly valuable.

### Copy

1. **Durable run row + lease + fence token.** Model a `runs` table (`status`, `lease_owner`, `lease_fence`, `lease_expires_at`, `wake_at`, `checkpoint`, `client_nonce`) and make every event/message write conditional on `(fence, owner)`. In Python: one `UPDATE ... WHERE ... RETURNING` claim, a heartbeat task renewing every 60 s with a 5 min expiry, and `status <> 'cancelled' AND lease_fence = :fence` inside the event insert. Prevents a zombie worker from posting stale trade chatter after a restart.
2. **Append-only per-thread `events` with a monotonic `seq` and cursor-based SSE**, `pg_notify` only as a wakeup plus periodic catch-up poll. Fits FastAPI `StreamingResponse`/SSE and the same reducer can be shared by React and Expo (Rakazo shares `runThreadSubscription` in `packages/core`). Delete transient progress events at finalize.
3. **Idempotency key per tool call** (`executionId`) plus a saved checkpoint *before* the effect, and replay of unresolved calls with an "uncertain effect" result. For broker orders this maps directly to client order ids and the existing not-sent/ambiguous states; never re-execute an order tool on resume, reconcile it.
4. **Pause = checkpoint + requeue.** `ask_user`/approval/trade-confirmation should end the model loop (tool returns terminate), persist the transcript, set `waiting_input`, and resume the same run on answer. Do not hold a coroutine open waiting for the human.
5. **Steering instead of queueing**: inject new user messages into the next model request of a running turn, with an explicit `steered` event; and a bare "stop" that cancels runs under the thread lock (Stop must also be a hard fence for order submission).
6. **Loop guard on tool-call fingerprints** (same args N times failing, same result N times) that ends the run with a clear user-facing stop message, and a configurable tool-call fuse per turn.
7. **Layered provider resilience as per-run state**: bounded same-model retries with backoff, learn the context window/output cap from the error, lazy backup models with recorded skip reasons, drop thinking blocks on signature mismatch, repeat empty replies, continue cut replies. Lonora's own `E4` error taxonomy/fallback work lines up; borrow the "recover before switching model" ordering.
8. **Subagents as ordinary runs** with a cap (4), hidden tools, and a result-return run. Keeps one lifecycle, one audit trail, one cancel path. Good for parallel market analysis helpers.
9. **Schedules as "next wake" bookkeeping**: advance `next_run_at` and create the run in one transaction, dedupe on `routine:<id>:<scheduled_for>` nonce, coalesce if the previous tick is still active, validate the wake against the stored `next_run_at`, and run a cheap model-free **watch tick** first so the model is only paid when something changed (price level, news, position change). Also a lane split so scheduled/background runs cannot starve interactive chat.
10. **Graceful drain that hands runs back between steps** and a leader-elected reconciler (`pg_try_advisory_lock`) for stuck waits, abandoned leases and expiry reminders.
11. **Cache-friendly prompt layout**: stable system prompt + history prefix first, volatile bits (`<current_time>`, recalled memory, market snapshot) last and tagged as data; `prompt_version` stamped on each run for A/B and regression comparison.
12. **Redact secrets on the way out and wrap recalled/summarised text as untrusted data** (broker credentials, account numbers).

### Avoid

1. **Depending on an opaque third-party loop for the control plane.** If Lonora uses a library loop (e.g. a Python agent SDK), keep it behind a narrow `AgentRuntime` interface (as `packages/adapter-kit` does with `run(request) -> AsyncIterator[event]`) and keep pause/steer/checkpoint logic outside it. Do not copy the 1400-line adapter shape; keep the event vocabulary small (`text`, `tool`, `ask`, `done`, `usage`, `yielded`).
2. **The mega-assembly pipeline with 15 intermediate objects.** Prefer a single typed `TurnContext` dataclass built by a few small functions.
3. **Per-event DB round trips with a run-row check on every progress delta.** Throttle or batch progress (Rakazo batches text at 250 ms but not tool events) and keep the fence check only on durable events; for progress use an in-memory pubsub with a DB catch-up.
4. **1 s DB polling per running run for cancel.** Use a cancel NOTIFY/Redis flag or check at step boundaries plus a slower poll.
5. **Silent "retrieval" history default without a fallback summary.** For a trading assistant keep a deterministic, structured state block (positions, open orders, mandate/limits) injected every turn rather than relying on the model to call `search_history`.
6. **Single fixed routine retry and a "no tool ran" gate** is too weak for market-hours jobs; give scheduled runs bounded exponential retries with a deadline (a stale pre-open job should be dropped, not retried at noon).
7. **At-least-once model+tool repeat after crash** ("a turn cut mid-way repeats its model call and tool call"). For order-submitting tools Lonora must treat any tool without an idempotent broker-side key as non-replayable and surface an ambiguous state.
8. **Postgres NOTIFY payload limits and pool saturation** as an unmanaged risk: cap payloads to ids/cursors only (as Rakazo does) and budget connections for listeners.
