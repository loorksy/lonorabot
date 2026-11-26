# Rakazo framework: processes, persistence, run lifecycle

Subject: https://github.com/elie222/rakazo (read-only clone). Audience: Lonora developers (Python/FastAPI server + worker, React web, Expo mobile, lead agent "Lonora" plus owner-created agents, MetaTrader 5).

All paths are repo-relative to the Rakazo checkout unless stated. Everything below was read in the code; where I did not find something I say so in "Not found / not done".

---

## 1. Component diagram (text)

```
 CLIENTS                                   EDGE (optional)
 apps/web (Vite/React)  ─┐                 infra/compose/Caddyfile.prod (TLS proxy)
 apps/mobile (Expo)     ─┼─ HTTPS/oRPC ──► tailscale-ingress / ingress provider (2nd listener, inbound-only)
 apps/desktop (Electron)─┘   + SSE stream   (apps/api/src/http/inbound-ingress.ts, packages/adapters/src/ingress)
 apps/desktop  ══ WebSocket (user device) ═══╗
                                             ║
 ┌───────────────────────────── API process (apps/api/src/index.ts, app.ts) ──────────────────────────┐
 │ Hono + oRPC router (router.ts, routes/*.ts)   auth (better-auth, packages/auth)                      │
 │ RunStarter  ← starts runs in-process the moment they are due (runs/wakeups/run-wakeup.ts)            │
 │ RunJobPublisher → writes runs.wakeAt, nudges RunStarter; other jobs → GraphileJobPublisher           │
 │ UserDeviceHub (websocket upgrade, auth/user-devices.ts)   messaging inbound sink (Telegram polling)  │
 │ createRunRuntime(...) → executor + job handlers (runs/assembly/run-runtime.ts)                       │
 └──────────────┬───────────────────────────────────────────────────────────────┬────────────────────┘
                │ Prisma / pg Pool                                              │ LISTEN/NOTIFY "rakazo_events"
                ▼                                                               ▼
 ┌───────────────────────────────  PostgreSQL 18  ─────────────────────────────────────────────────┐
 │ app tables (packages/db/prisma/schema.prisma, 148 models) + row-level security                   │
 │ graphile_worker.* (job queue)   leases / computer_execution_leases   events (per-thread seq)     │
 │ advisory lock (reconciler leader)   pg_notify (realtime fan-out, run handoff "runs:ready")       │
 └──────────────▲───────────────────────────────────────────────────────────────▲────────────────────┘
                │                                                               │
 ┌──────────────┴──────────────  WORKER process (apps/worker/src/index.ts) ──────┴───────────────────┐
 │ RunWorkerHost: subscribe "runs:ready" + 5 s recovery scan (run-wakeup.ts)                          │
 │ Graphile hosts: interactive / background / maintenance (wakeup.ts)                                 │
 │ createRunReconciler = job-reconciler.ts (leader via pg advisory lock, every 30 s)                  │
 │ same createRunRuntime(...) as API → executor.continueRun(runId)                                    │
 │ health file /tmp/rakazo-worker-health.json (health.ts, health-check.ts)                            │
 └──────────────┬────────────────────────────────────────────────────────────────────────────────────┘
                │ HTTP (token)                         │ model APIs (pi-ai SDK)       │ MCP / connectors / chat apps
                ▼                                      ▼                              ▼
   supervisor (infra/sandboxes/supervisor) → per-bot computer containers      LLM providers      external services
   (docker/E2B/Daytona/local-vm: packages/adapters/src/providers/computer)
```

There is no separate "relay" or "edge function" tier. The two server processes (API, worker) run the same run runtime; Postgres is the only shared bus. The one relay-like piece is the desktop websocket described in 3.4.

---

## 2. Processes and the files that define them

| Process | Entry | What it does |
|---|---|---|
| API | `apps/api/src/index.ts` -> `createApp()` in `apps/api/src/app.ts` | HTTP/oRPC server (Hono via `@hono/node-server`), auth, SSE event stream, websocket upgrade for desktop devices, **also starts runs** (`RunStarter`). Optional second listener `inboundOnly(app.fetch)` for a public tunnel (`apps/api/src/http/inbound-ingress.ts`). |
| Worker | `apps/worker/src/index.ts` | Takes handed-over runs, recovers dead runs, runs Graphile jobs, runs the reconciler. Runs the whole worker under `runAsSystem("worker process", main)`. |
| Web | `apps/web` (Vite preview in compose, `infra/compose/docker-compose.yml` service `web`) | React chat UI. |
| Mobile | `apps/mobile` | Expo app; talks to the same API. |
| Desktop | `apps/desktop/src/main/*` | Electron shell. `apps/desktop/src/main/this-computer/native-stack.ts` (`NativeStackController.appEnv`) launches a local API+worker stack with `WAKEUP_DRIVER: "graphile"`, `AGENT_RUNTIME: "pi"`, `SANDBOX_PROVIDER: "local-vm"`. |
| Supervisor | `infra/sandboxes/supervisor` (compose service `supervisor`) | Docker-socket holder that creates per-bot computer containers; API/worker reach it with `SANDBOX_SUPERVISOR_TOKEN`. |
| Postgres | compose service `postgres` (`postgres:18`) | Single store for data, job queue, realtime, locks. |
| Migrate | compose service `migrate` (`pnpm db:deploy`) | Runs Prisma migrations before API/worker start. |
| Edge functions | none | Not found. No serverless or edge-function code in `apps/` or `packages/`. |

Compose facts (`infra/compose/docker-compose.yml`): `worker` has `stop_grace_period: 50m`, a healthcheck `node dist/health-check.js`, and starts only after `api` is healthy (api applies/creates the DB login). The comment above `stop_grace_period` ties it to `JOB_DRAIN_TIMEOUT_MS` in `packages/adapters/src/runs/wakeups/wakeup.ts`. Both processes run `node dist/index.js` directly (not through pnpm) so SIGTERM reaches them.

Process boot order is the same in both (`packages/adapters/src/server/server-foundation.ts`, `startServerFoundation`): row-security check, secret store (`withSecretWriteAhead`), `installSecurityEventStore`/`installAuditEventStore`, `verifyContentKeys`, analytics, then `createThreadEvents(prisma, realtime, ...)`. API and worker differ only in the Prisma client and the realtime fan-out they pass in.

---

## 3. Communication

### 3.1 Client to API: oRPC over HTTP plus an SSE stream

- Contracts shared by clients and server: `packages/contracts`. Handlers: `apps/api/src/routes/*.ts` (e.g. `routes/threads.ts`), routed in `apps/api/src/router.ts`, mounted by `apps/api/src/http/rpc-route.ts`.
- The live chat feed is a server-sent-event stream, not a websocket: `routes/threads.ts` builds `withHeartbeats(context, (signal) => deps.events.follow(target.threadId, input.cursor, signal), filter)`. The client passes a `cursor` (last event `seq`) and resumes from there.
- `apps/api/src/http/drain.ts` (`trackConnections`) closes SSE streams and upgraded sockets at once on a deploy so clients reconnect to the new release; ordinary requests finish (20 s).

### 3.2 Events: durable log + NOTIFY nudge + catch-up read

1. Every thread has `Thread.nextEventSeq`. `appendEventInTransaction` (`packages/db/src/threads/events.ts`) increments it (`tx.thread.update({ data: { nextEventSeq: { increment: 1 } } })`, which takes the thread row lock) and inserts an `Event` row with `seq = nextEventSeq - 1`. `@@unique([threadId, seq])` in the schema.
2. After commit, `notifyRealtime` (`packages/db/src/threads/event-stream.ts`) publishes on `threadTopic(threadId)`.
3. `PostgresRealtimeFanout` (`packages/adapters/src/notifications/realtime.ts`) sends `SELECT pg_notify('rakazo_events', {topic,payload})` (payload cap 7,900 bytes, throws above) and holds one dedicated `LISTEN rakazo_events` connection per process with jittered reconnect (250 ms to 10 s).
4. `followThreadEvents` subscribes, then loops `eventsAfter(prisma, threadId, seq, batch)`: the notification is only a wake-up latch; the data is always re-read from `events`. A missed NOTIFY costs latency, never correctness.
5. `InMemoryRealtimeFanout` (same file) is the test / embedded variant.

### 3.3 Run handoff between processes: topic `runs:ready`

`RUN_READY_TOPIC = "runs:ready"` in `runs/wakeups/run-wakeup.ts`. A process that cannot or must not run a due run publishes the run id on this topic (`RunStarter.handOff`); every worker's `RunWorkerHost.start` subscribes and calls `starter.take(runId)`. If nobody listens, the durable row is found by the 5 s scan (section 5.6).

### 3.4 Desktop / user device socket

The desktop app opens an outbound websocket to the API so bots can reach the user's own computer (`apps/api/src/index.ts`: `server.on("upgrade", handleUpgrade)`; `apps/api/src/auth/user-devices.ts`; `UserDevices` / `UserDeviceHub` in `packages/adapters`). The socket lives in one API process, so the worker **forwards** to whichever API holds it (`userDeviceForwardSecret`, `USER_DEVICE_FORWARD_PATH`; wired in `apps/worker/src/index.ts`). This is the only place Rakazo has an HTTP-forwarding hop between its own processes. Tables: `UserDevice`, `UserDeviceConnection`.

### 3.5 Queues

Two mechanisms, deliberately split (`docs/run-execution.md`, "Run dispatch"):
- **Runs are not queued in Graphile.** The run row in Postgres is the queue (status + `wakeAt`).
- **Graphile Worker** (`graphile_worker` schema, `packages/adapters/src/runs/wakeups/wakeup.ts`) carries the other jobs, typed in `packages/adapter-kit/src/background-jobs.ts`: `routine.wakeup`, `routine.retry`, `computer.sleep`, `computer.control-expire`, `skill.teaching-expire`, `run.forget-secrets`, `approval.expire`, `call.expire`, `messaging.send`, `messaging.inbound_settle`, `messaging.reply`, `team_chat.engage`, `team_chat.ambient`, `history.compact`, `memory.purge-history`, `connection.cleanup`, `computer.machine-cleanup`, `memory.retain-turn`, `push.receipt`, `cloud_agent.poll`, `purchase.poll`, `media.poll`, `email.lifecycle`, and the legacy `run.continue`. `parseBackgroundJob` zod-validates every payload; `dispatchBackgroundJob` routes it.
- The publisher is `RunJobPublisher` (wraps `GraphileJobPublisher`): `enqueue` of a `run.continue` job does `prisma.run.updateMany({ where: { id, status in RESUMABLE }, data: { wakeAt } })` and calls `starter.start(runId, at)`; everything else goes to Graphile with `jobKey`, `queueName`, `maxAttempts`, `jobKeyMode`.
- Graphile workers are split into three reserved hosts so long agent turns cannot starve other work: `createReservedGraphileJobWorkerHost` creates `interactive` (concurrency `GRAPHILE_WORKER_CONCURRENCY`, default 4), `background` (1) and `maintenance` (100, local queue 10).
- All three share the caller's `pg.Pool` (comment on `GraphileJobPublisher`); the worker refuses to boot with `DB_POOL_MAX < 6` unless `WAKEUP_DRIVER=memory`.
- `InMemoryJobQueue` (`runs/wakeups/in-memory-job-queue.ts`) is the `WAKEUP_DRIVER=memory` driver for embedded/test use. Desktop forces `graphile`.
- `job-give-up.ts` and `createDeadJobPruner` (in `wakeup.ts`) delete exhausted dead jobs; `createRoutineRetryNoticeReconciler` turns exhausted retry rows into durable notices.

### 3.6 Bot to bot

There is no separate agent bus. A bot "messaging" another bot is a database write plus a normal run (`packages/adapters/src/messaging/bot-messages.ts`, `messageBot`):

1. Sender calls the `message_bot` tool. Content/length checks, hop count: `nextBotMessageHop(sourceContext?.hop)`; `BOT_MESSAGE_MAX_HOPS = 100` (`packages/core/src/bots/bot-messages.ts`); `botMessageHopExhausted(hop)` blocks further hops unless it is a return to the sender.
2. Candidates are bots in the **same Space** that are not archived; target resolved with `resolveBotAddress`.
3. One transaction under thread locks (`THREAD_LOCK_TRANSACTION_OPTIONS`): confirm the sender run is still active, re-check the target is not archived, write an outbound `bot_message_sent` block into the sender's thread, an inbound `bot_message_received` block (with `fromBotId`, `hop`, `intent`, `returnToMessageId`) into the target's thread, create a `Task` and a `Run` for the target with `trigger: "bot_message"`, and append `thread.message.created` events to both threads.
4. After commit: `events.notify(...)` on both threads, then `wakeRun(deps.jobs, runId)`.
5. `deliveryKey` -> `clientNonce` gives an idempotent send; a unique-violation on `(threadId, clientNonce)` is treated as a replay.
6. The result returns to the requester through `returnBotMessageOutcome`. The reconciler (`job-reconciler.ts`) re-delivers an unreturned outcome (`runs.botOutcomeReturnedAt IS NULL`, trigger `bot_message`, status completed/failed) using the same delivery key `auto-outcome:<runId>`, so a crash after the run ended does not lose the reply.
7. A `bot_message` run is a "non-conversational" trigger (`NON_CONVERSATIONAL_RUN_TRIGGERS` in `packages/core/src/runs/run-state.ts`): a user message does not steer it.
8. Other bot-to-bot paths: tickets (`packages/adapters/src/tasks/ticket-wake.ts`, `wakeTicketAssignee` creates a run for the assignee with no chat message) and background helpers (`BACKGROUND_HELPER_TRIGGER`, `tasks/background-helpers.ts`).

---

## 4. Persistence

Postgres only (via Prisma, `packages/db/prisma/schema.prisma`, 3,153 lines, 148 models, migrations in `packages/db/prisma/migrations`). Status fields are plain `String` columns, not Prisma enums (there are no `enum` declarations).

Main tables relevant to the framework:

| Table (model) | Role |
|---|---|
| `Space`, `SpaceMember`, `Organization`, `User`, `Session` | Tenancy and identity. `Space` has `deletingAt` and per-space keys (`SpaceKey`). |
| `Bot` | An agent: name, instructions, `instructionHistory`, model fields, `computerId`. |
| `Thread` | One continuous chat per bot (`botId @unique`), also group and external-conversation threads. Holds `nextEventSeq`, `nextMessageSeq`, `historyCompactedUpToSeq`. |
| `Message` | Chat content blocks, `clientNonce` for idempotent sends (`@@unique([threadId, clientNonce])`). |
| `Event` | **Append-only per-thread log**: `seq`, `type`, `payload`, `runId`; `@@unique([threadId, seq])`. Types seen: `thread.message.created`, `run.started`, `run.completed`, `run.failed`, `run.cancelled`, activity events. Transient run events are deleted at finalize (`transientRunEventsWhere`). |
| `Task` | The prompt/unit of work a run executes; status mirrors the run outcome. |
| `Run` | The lifecycle row (see section 5). |
| `Attempt` | One row per claim of a run (`fence`, `status`, `error`, `startedAt`, `finishedAt`). |
| `SteeringMessage` | A user message that arrived while a run is going; claimed by that run or turned into a continuation run. |
| `ExternalEffect` | Idempotency + approval record for side effects (`idempotencyKey @unique`, `status`, `request`, `result`). **Also holds the saved turn checkpoint** as a reserved row (`kind = status = "runtime_checkpoint"`, `RUN_TURN_CHECKPOINT_KIND` in `packages/db/src/runs/run-turn-checkpoint.ts`). |
| `Routine` | Scheduled / watching / event-triggered work: `crons`, `timezone`, `nextRunAt`, `watch`, `watchState`, `endsAt`, failure counters. |
| `Lease` | Generic key/fence/expiry lease (`key`, `fence BigInt`, `expiresAt`). |
| `Computer`, `ComputerExecutionLease`, `ComputerRun` | Per-bot sandbox, the lease that grants one run at a time its use (`@@unique([computerId, botId])`, `fence`, `expiresAt`), and billed running time. |
| `UsageRecord` | Per model call: tokens (input/output/cache/reasoning), `costUsd`, `provider`, `model`, `runId`, `botId`, `billing`, `operationKind`, `pricingSnapshot`. Deliberately has no foreign keys so spend survives deletion. |
| `ModelCreditAccount/Entry/Lot`, `BillingAccount`, `SpendingLimit`, `Purchase`, `PaymentWallet` | Credits and money. |
| `AuditEvent`, `SecurityEvent`, `BillingAuditEvent` | Audit trails. |
| `Secret`, `BotSecret`, `VaultCredential`, `UserModelCredential` | Credentials, encrypted. |
| `McpServer`, `Connection`, `CapabilityInstall` | Extension/connectors. |
| `Board`, `Ticket`, `TicketComment` | Shared work board between agents. |
| `MemoryDocument`, `MemoryRevision`, `Artifact`, `Page`, `PageVersion` | Memory, files, pages. |

Encryption: `packages/db/src/encryption/*` seals chosen columns with a per-space key (`contentEncryptionOf(prisma).sealRow("Event", row)` in `insertEventAlone`); desktop turns it off (`CONTENT_ENCRYPTION: "off"`).

Files on disk: `DATA_DIR` (`/data` in compose) holds agent homes, artifacts and Pi session files (`createAgentHomeStore`, `createArtifactStore`, `resolvePiSessionRoot` in `apps/worker/src/index.ts`).

---

## 5. Run lifecycle

### 5.1 States and legal transitions

`packages/core/src/runs/run-state.ts`:

```ts
const allowed: Record<RunStatus, RunStatus[]> = {
  queued: ["leased", "cancelled"],
  leased: ["running", "queued", "cancelled"],
  running: ["waiting_input", "waiting_takeover", "completed", "failed", "cancelled", "leased"],
  waiting_input: ["queued", "leased", "cancelled"],
  waiting_takeover: ["queued", "leased", "cancelled"],
  completed: [],
  failed: ["queued"],
  cancelled: [],
};
```

- Working: `queued`, `leased`, `running`. Waiting on the user: `waiting_input` (question/approval card), `waiting_takeover` (the user takes the bot's screen). Terminal: `completed`, `failed`, `cancelled` (`isTerminal`). `failed -> queued` exists for the user's "retry" (`canRetryRun`: only a failed `user`-trigger run with `retryable`).
- `Run.trigger` values seen in code: `user`, `follow_up`, `reaction`, `messaging`, `routine`, `webhook`, `created`, `tickets`, `bot_message`, `helper`, `call_end`, `skill`, `resume`. The scheduler splits **interactive** (everything except `routine`/`reaction`) from **background** (`routine`, `reaction`).
- `Attempt.status` values seen: `running`, `interrupted`, `completed`, `failed`, `setup_failed`.

### 5.2 Creating a run (control flow, user message)

1. Client calls the send RPC; `sendThreadMessage` in `apps/api/src/threads/thread-target.ts` runs one transaction: write the `Message` (with `clientNonce` for idempotency), and either (a) attach a `SteeringMessage` to the run already going, (b) answer a waiting run, or (c) `tx.run.create({ status: "queued", ... clientNonce: sendRunClientNonce(...) })`. `@@unique([spaceId, clientNonce])` on `Run` makes the create replay-safe.
2. After commit the API calls `wakeRun(jobs, runId)` (`runs/wakeups/wake-run.ts`). It never throws: "the run row is the durable record and recovery starts a run whose nudge was lost".
3. `RunJobPublisher.enqueue` sets `runs.wakeAt` and `RunStarter.start(runId, at)`. With no delay it calls `begin(runId, local=true)` straight away; with a delay it sets an unref'd timer (a leaving process skips the timer; recovery will start it).
4. HTTP returns at once; the client follows the reply over the SSE stream.

Other creators use the same path: bot-to-bot (`messageBot`), routines (`wakeRoutine`), tickets (`wakeTicketAssignee`), webhooks, messaging inbound (`apps/api/src/messaging/messaging-inbound.ts`), approvals (`apps/api/src/integrations/mcp-approval.ts`), retries.

### 5.3 Starting and claiming (`RunStarter.begin` then `executor.continueRun`)

1. `RunStarter.begin` keeps an `inFlight` set (a second wake while running sets `dueAgain`). It asks `RunExecutionHost.execute(..., { waitForCapacity: false })` (`runs/lifecycle/run-execution.ts`) for admission. Admission is **memory based, not a run-count cap**: `admissionMemory` compares `process.availableMemory()` (plus reclaimable cgroup file cache) and V8 heap headroom with a reserve of `ATTACHMENT_MAX_BYTES * 4`. If declined, a local start hands the run to another process via `runs:ready`; a handed-over run (`take`) never hands on again. Interactive work is scanned before background in the recovery scan.
2. The job body runs inside `runCorrelatedJob({ name: "run.continue", payload })` and `runAsSystem("run dispatch", ...)`, then dispatches the `run.continue` handler.
3. `createRunExecutor(...).continueRun(runId, workerId, onRunStarted)` (`runs/executor/executor.ts`):
   - `findContinuableRun` (`runs/lifecycle/run-attempt.ts`): refuse if the process is stopping (`stoppingSignal`/`shutdownSignal`), load the run, `enrichLogContext` with run/bot/thread/space/user ids, drop terminal runs, cancel runs of deactivated accounts or former members.
   - `claimRunAttempt` -> `claimRun` (`runs/lifecycle/run-lifecycle.ts`): one `updateMany` inside a transaction (after `spaceTakesWork`, so a Space being deleted starts nothing) that matches `status in (queued, waiting_input, waiting_takeover)` **or** `status in (leased, running) AND leaseExpiresAt <= now`, and wakeAt due, and sets `status: "leased"`, `leaseOwner`, `leaseFence: nextFence(...)`, `leaseExpiresAt: now+5min`, clears `error`, `checkpoint`, `wakeAt`. Then a second `updateMany` `leased -> running` guarded by owner+fence. If either returns `count !== 1`, the run is not ours (`holdRunForChat` is tried for chat-ordering waits).
   - `holdRun` (`run-attempt.ts`): sets up the heartbeat, `withRunLease(deps, runId, {owner, fence})` so every later history write is fenced, and run-scoped state.
   - `onRunStarted()` fires: from here the durable lease + heartbeat carry recovery; model/tool setup no longer occupies a dispatch slot.
   - `assembleRunTurn(services, hold)` (`runs/assembly/run-assembly.ts`) builds history, instructions, tools, model. `runModelTurn(services, hold, turn)` (`runs/turn/run-model-turn.ts`) runs the turn and tool loop.
   - `catch` -> `retryRunSetup` (setup failures); `finally` -> `releaseRunHold` -> `finishRunAttempt`.

### 5.4 Lease, fence and heartbeat

- Run lease: `Run.leaseOwner`, `Run.leaseFence` (int), `Run.leaseExpiresAt` (5 minutes ahead at claim and each renewal).
- Heartbeat: `RUN_HEARTBEAT_MS = 60_000` (`run-attempt.ts`). Each beat calls `renewRunLease` (`updateMany where status:"running", leaseOwner, leaseFence` -> `leaseExpiresAt = now+5min`) and `renewComputerExecutionLease`. If either returns false, `lease.valid = false` and the run's abort controller is aborted. A thrown database error is tolerated only while `Date.now() < lease.renewedAt + EXECUTION_LEASE_MS - RUN_HEARTBEAT_MS`; after that window another worker may have the run, so this attempt stops (`databaseOutage.failed(...)` branch).
- Fence: a new claim increments `leaseFence`; `appendEventInTransaction`/`insertEventAlone` only write when the run's `leaseFence` and `leaseOwner` still match, so a fenced-out attempt "writes nothing" (`RunHistoryWriteError`). `finalizeRun` is likewise `where: { status: "running", leaseOwner, leaseFence }` and returns `null` if it lost.
- Computer lease: `ComputerExecutionLease` (`EXECUTION_LEASE_MS = 5 * 60_000`, `packages/adapters/src/computers/computer-lifecycle.ts`). A bot uses its computer for one run at a time; others wait queued with no timer and `startNextWaitingRun` (in `finishRunAttempt`) starts the next one when the holder releases. Released leases are kept as tombstones so the fence still rises.

### 5.5 Finishing

`finalizeRun` (`packages/db/src/threads/events.ts`, `finalizeRunOnce`), one transaction:
1. `SELECT ... FROM threads WHERE id = ... FOR UPDATE` (thread lock first, run second, everywhere).
2. `run.updateMany` `status: "running"` + owner + fence -> `completed` or `failed` with `completedAt`, lease cleared.
3. Delete the turn-checkpoint effect row, update `Attempt` (`status`=outcome) and `Task`.
4. Write the final bot `Message` and `thread.message.created`, then `run.completed` or `run.failed {error, retryable}` events; delete transient run events and the run's secrets.
5. Settle steering messages; `createPendingSteeringRun` creates a **continuation run** if a user message arrived during the turn.
6. Executor wraps it in `retryWhileDatabaseUnavailable({ source: "run finalize", signal })` so a failover does not lose the outcome; the lease fence makes the retry safe.

After the attempt (`finishRunAttempt`): end run-scoped connector state if the run is over for this worker, release screen + computer lease, `startNextWaitingRun`, `startRunsWaitingOnChat`, and if the process is shutting down `requeueInterruptedRun`.

### 5.6 Waiting (user input, approval, takeover)

- A tool asks the user (`pauseForAnswer` in `runs/turn/run-turn-pause.ts`): renew lease, flush computer checkpoint, `persistTurnCheckpoint` (the model transcript as `TurnCheckpoint`, `runs/turn/turn-checkpoint.ts`: `version`, `provider`, `model`, `systemPrompt`, `pendingToolCallId`, `messages`, `toolCallCount`, `effectOccurrences`, optional `reply`), then `events.pauseRunForInput(...)` which moves the run to `waiting_input` and posts the card. The lease is released.
- The answer/approval makes the run `queued` again and `wakeRun`s it; `claimRun` accepts `waiting_input`. The executor reloads the checkpoint (`loadRunTurnCheckpoint`) and replays approved effects (`APPROVED_EFFECT_REPLAY_ORDER`, `runs/lifecycle/run-effects.ts`).
- Pending approval expiry: Graphile job `approval.expire`. Unattended waiting: `reconcileStuckWork` (`runs/lifecycle/stuck-work.ts`): statuses `queued` and `waiting_takeover`; notify after `STUCK_WORK_NOTIFY_AFTER_MS` = 4 h, expire after `STUCK_WORK_EXPIRE_AFTER_MS` = 24 h (overridable by env, bounded 1 min to 30 days; `packages/core/src/runs/stuck-work.ts`).

### 5.7 Failure, retries, backoff

- Setup failure (before the model turn): `retryRunSetup`. Counted by `setupFailureStreak`; `RUN_SETUP_FAILURE_LIMIT = 8` consecutive failures then the run fails (`status: "setup_failed"` attempts; busy-computer and database waits do not count). Delays: `computerRetryDelay(fence) = min(10 s, 250 ms * 2^min(fence-1,5))`; `providerOutageRetryDelay(n) = min(5 min, 15 s * 2^min(n,5))`.
- Turn failure: `runs/lifecycle/run-fail.ts` maps errors (`ModelAccountError`, `TransientModelError`, `ModelOutputError`, `SandboxRateLimitError`, ...) to user text (`userRunError`), may requeue (`requeueInterruptedRun`, `computerRetryDelay`), schedules routine retry (`scheduleRoutineRetry`), backs off a routine after account errors (`routines/routine-backoff.ts`) and pauses it after repeated failures (`routines/routine-failure-pause.ts`).
- Tool loop guard: `runs/turn/tool-loop.ts` (`loopGuardStop`, `MAX_CONSECUTIVE_OVER_LIMIT_ACTION_CALLS = 4`, `MAX_ACTIONS_PER_CALL = 24`) ends a run that repeats the same call.
- Database outage: `databaseOutage` / `retryWhileDatabaseUnavailable` / `databaseCapacityBackoffMs` (`@rakazo/db`) keep processes alive and retrying instead of crashing (worker `index.ts` comment on 53300).

### 5.8 Recovery after a crash or restart (the important part)

There is no "recovery table"; recovery is **re-deriving work from run rows**.

1. A crashed worker stops heartbeating; `leaseExpiresAt` passes.
2. `RunWorkerHost` (`run-wakeup.ts`) scans at startup and every 5 s (`intervalMs ?? 5_000`), plus on every `runs:ready` notification. `scanLane` selects, per lane (interactive/background) with a `(createdAt, id)` cursor and batch 100:
   - `status = queued` and due (`wakeAt` null or past),
   - `status in (leased, running)` and `leaseExpiresAt <= now`,
   - `status in (waiting_input, waiting_takeover)` and `wakeAt <= now`.
3. `findRunRecoveryBlockers` (`runs/lifecycle/run-recovery.ts`) drops runs whose bot computer is held by another run's lease reaching more than `2 * EXECUTION_LEASE_MS` ahead (a takeover hold); abandoned holds (run gone or terminal) are expired as tombstones. A takeover hold the user has not acted on is ended so chat work is not blocked (`endTakeoverWaits`).
4. Each candidate goes to `starter.take(id)` -> `claimRun`; the atomic `updateMany` and fence guarantee exactly one claimant even with many processes ("however many API and worker processes run, a run executes once").
5. The saved `TurnCheckpoint` and `ExternalEffect` rows let the new attempt resume rather than redo (`claimRun` clears the run's `checkpoint` column; the turn state is the `runtime_checkpoint` effect row).
6. The leader-elected reconciler (`createJobReconciler`, `job-reconciler.ts`, `DEFAULT_INTERVAL_MS = 30_000`, `createPostgresReconciliationLeadership`: a session advisory lock `pg_try_advisory_lock(RECONCILIATION_LOCK_NAMESPACE, 1)`; followers retry each interval) does the slower repairs: `reconcileStuckWork`, queued/expired-lease runs, undelivered bot outcomes, background-helper outcomes, `reconcileCallRequests`, `reconcileComputerRuns`, routine wake-ups within `ROUTINE_LOOKAHEAD_MS = 60 s`, abandoned queued Graphile locks older than `ABANDONED_QUEUED_LOCK_MS = 5 min`, dead-job pruning, home-storage sweep.
7. Queue-health alarm: every 30 s `checkQueueAge` logs `run.queue_delayed` (error) if an interactive run has been due and unstarted for 30 s, with `queue.delayed_runs`, `queue.oldest_wait_ms`, `worker.active_runs`, `db.pool.*`, `event_loop.delay_*`; `run.queue_recovered` on clear.

### 5.9 Graceful shutdown and deploy

- SIGTERM on worker (`stopOnShutdownSignals`): `shutdown.abort()`; `RunStarter` stops claiming; each running turn is told to stop via `shutdownSignal` (`drainRuns(signal, limitMs)`): with `RUN_DRAIN_ENABLED=true` a stopping worker lets runs end their current step for up to `RUN_DRAIN_MS = 5 min`, renewing leases and claiming nothing new; a turn that finishes a step while stopping saves the turn plus the reply so far and hands the run back (`requeueInterruptedRun`, status back to `queued`, no failure recorded). Without drain, runs are requeued at once.
- API: SIGTERM requeues its runs at once; `deploy-main.sh` sends `SIGUSR2` (`RUN_DRAIN_SIGNAL` in `apps/api/src/http/drain.ts`, announced by image label `org.rakazo.run-drain-signal`) so a replaced API closes its listener, lets turns end, and the new API takes new requests.
- `uncaughtException` / `unhandledRejection` in the worker log, set `exitCode = 1`, drain, exit; except database-outage rejections which are ignored once logged.

---

## 6. Concurrency and locking (summary)

| Mechanism | Where | Purpose |
|---|---|---|
| Atomic `UPDATE ... WHERE status/lease/fence` | `claimRun`, `renewRunLease`, `finalizeRun`, `requeueInterruptedRun` | Exactly-once claim, fenced writes |
| `leaseFence` increments | `Run`, `ComputerExecutionLease` | Reject writes from stale attempts |
| Thread row `FOR UPDATE` (then run row) | `finalizeRunOnce`, `insertEventAlone`, `THREAD_LOCK_TRANSACTION_OPTIONS` | Single writer per thread, ordered `seq` |
| `@@unique([threadId, seq])`, `@@unique([threadId, clientNonce])`, `@@unique([spaceId, clientNonce])`, `ExternalEffect.idempotencyKey` | schema | Idempotent sends, replays, effects |
| `ComputerExecutionLease` `@@unique([computerId, botId])` | schema, `computer-lifecycle.ts` | One run per bot computer |
| Postgres advisory lock | `createPostgresReconciliationLeadership`; `packages/adapters/src/locks/advisory-lock.ts` | Single reconciler leader |
| Graphile `jobKey` and named queues, `JobQueueOrder.pendingUntil/releaseFollowersIn` | `wakeup.ts`, `named-queue-order.ts` | Dedupe, ordering within a queue |
| In-process `inFlight` / `dueAgain` | `RunStarter` | One start per run per process |
| Chat ordering | `chat-wait.ts`, `claimWaitsForChat` | A routine run in a chat or a bot message waits for the run under way there; 5-minute recheck backup; after 5 min a routine hands its task to the working run (`docs/run-execution.md`) |
| Memory admission | `RunExecutionHost.execute` | Back-pressure by free RAM/heap, no fixed run cap |

---

## 7. Configuration

- Env parsing: API `apps/api/src/env.ts` (`loadEnv`, e.g. `wakeupDriver: source.WAKEUP_DRIVER ?? "graphile"`); worker `runRuntimeEnvFromProcess` in `packages/adapters/src/runs/assembly/run-runtime.ts` (`RunRuntimeEnv`: `dataDir`, `encryptionKey`, deployment model key/provider/model, MCP stdio flags, labs, phone call settings, upload limits, `webOrigin`). Both call `resolveDeploymentModel(source)` "so both processes agree on provider, model and key".
- Root `.env` loaded by `loadRootEnv()`; secrets can be unwrapped from a key manager (`unwrapEnvFromKeyManager`).
- Key knobs seen: `DATABASE_URL`, `REALTIME_DATABASE_URL`, `DB_POOL_MAX` (worker default 8, API jobs pool 4), `WAKEUP_DRIVER` (`graphile`|`memory`), `GRAPHILE_WORKER_CONCURRENCY`, `RUN_DRAIN_ENABLED`, `AGENT_RUNTIME` (`pi`|`scripted`), `SANDBOX_PROVIDER`, `SANDBOX_SUPERVISOR_URL/TOKEN`, `STUCK_WORK_*_AFTER_MS`, `LOG_LEVEL`, `AXIOM_*`, `SENTRY_*`, `WEB_ORIGIN`, `BETTER_AUTH_*`, `INGRESS_*`.
- Feature "labs": `deploymentLabsFromEnv` (`runs/labs-env.ts`).
- Per-bot/space/user settings live in the DB (`SpaceSettingOverride`, `DeploymentSettings`, `UserModelPreference`, `SpaceModelPreference`, ...), not in files.

---

## 8. Multi-user and tenancy

- Hierarchy: `Organization` -> `Space` -> (`Bot`, `Thread`, `Run`, `Routine`, `Computer`, ...). A user is a `SpaceMember`. Nearly every table carries `spaceId`; user-scoped ones also `userId`.
- **Postgres row-level security**, enforced per request: `packages/db/src/database/row-security.ts`. An `AsyncLocalStorage<DbContext>` holds `{kind:"tenant", spaceId, userId}` or `{kind:"system", reason}`; without a context "protected tables return no rows and reject writes". `runAsTenant(...)` for request/job code; `runAsSystem(reason, fn)` is an audited bypass ("`grep -rn "runAsSystem("` lists every one"). `ROW_SECURITY_MODELS` lists protected models (Thread, Message, Event, MemoryDocument, Secret, ...). `describeRowSecurity` is checked at boot and warns (`startServerFoundation`).
- Jobs that act for one run/routine/computer re-enter a tenant context from that row (`asOwner(...)` in `runs/wakeups/background-job-handlers.ts`), so even a query that forgets a filter stays in the owner's Space.
- The worker itself is cross-tenant by design: its one bypass is `runAsSystem("worker process", main)`.
- Bot-to-bot messaging is restricted to the same Space (`messageBot` candidate query on `spaceId`); cross-space is an explicit opt-in (`crossSpaceCommunicationAllowed`).
- Account deactivation / leaving a Space cancels runs (`cancelDeactivatedAccountRuns`, `cancelRunOfFormerMember`); a Space being deleted starts nothing (`spaceTakesWork`).
- Auth: `packages/auth` (better-auth: passwords, passkeys, OIDC, social), session lookup in `apps/api/src/auth`. SCIM tables exist (`ScimUser`, `ScimGroup`, ...).

---

## 9. Deployment and self-hosting

- Primary target: Docker Compose (`infra/compose/docker-compose.yml`, `.prod.yml`, `.standalone.yml`, `.topology.yml`; Caddy `Caddyfile.prod`; scripts `deploy-main.sh`, `backup-prod.sh`, `backup-drill.sh`, `harden-host.sh`, `host-alert.py`, `audit-ship.py`). Docs: `docs/self-host*.md`, `docs/deployment/*`.
- Other targets: Railway (`railway.json`, `infra/railway`), Kubernetes docs (`docs/self-host-kubernetes.md`), cloud-init for a VPS (`infra/cloud-init`), systemd units (`infra/systemd`), a desktop-embedded native stack (`NativeStackController`).
- Services in compose: `postgres`, `supervisor`, `computer` (image build only, `command: ["true"]`), `data-init`, `migrate`, `api`, `worker`, `web`, optional `tailscale-ingress`.
- Database logins: migration role vs application role (graphile schema "installed or upgraded ... as the migration role", comment in `wakeup.ts`; `app.rls_bypass_key` per login in `row-security.ts`).
- Rolling-upgrade compatibility is explicit: legacy `run.continue` Graphile deliveries remain supported and "drain safely against the same database claims"; a compat trigger stamps retry backoff for older workers (`docs/run-execution.md`).

---

## 10. Observability

- Structured logging: `packages/logging` (`createRootLogger(SERVICE_NAMES.worker)` in `axiom.ts`). Sinks: console, optional Axiom (`AXIOM_TOKEN`+`AXIOM_DATASET`), optional Sentry (`sentry.ts`); `logSinkHealth()` is exposed in `/internal/health` and the worker health file. `redaction.ts`, `pseudonym.ts` keep content/ids out of logs. `runCorrelatedJob` and `enrichLogContext` attach `run.id`, `bot.id`, `thread.id`, `space.id`, `run.trigger`, `routine.id`, `user.id`.
- Event-loop watch: `watchEventLoopStalls("api.event_loop_stalled" / "worker.event_loop_stalled")`.
- Run timing logs: `run.execution_started`, `run.first_response`, `run.finished` with `run.pre_run_wait_ms`, `run.queue_wait_ms`, `run.first_response_ms`, `run.total_ms`, `run.execution_wall_ms` (`packages/db/src/runs/run-timing.ts`; `Run.firstResponseAt` persisted in the same transaction as the first reply, `docs/run-execution.md`).
- Admission logs: `run.admission_wait`, `run.admission_resumed`; queue alarm `run.queue_delayed` (an APL alert example for Axiom is in `docs/run-execution.md`; the app emits the signal, alert routing is the deployment's job).
- Health: API `/health` (constant), `/ready` (503 if degraded or the DB probe with 1.5 s statement timeout fails), `/internal/health` (private network only, no forwarding headers) in `apps/api/src/http/health.ts`. Worker writes `/tmp/rakazo-worker-health.json` every 30 s (`heartbeat`, `reconciled`, `telemetry`) for the Docker healthcheck (`apps/worker/src/health.ts`).
- Model tracing: Pi telemetry spans (`withPiTelemetrySpan`, `recordPiTelemetryContent` imported in `runtime/pi/usage/pi-usage.ts`; `shutdownPiTelemetry()` on stop).
- **Usage and cost accounting**: every model call is normalized to `AgentUsage` (`normalizePiUsage`, `packages/adapters/src/runtime/pi/usage/pi-usage.ts`; it zeroes a rejected request) and stored as `UsageRecord` (tokens by bucket, `costUsd`, `provider`, `model`, `runId`, `botId`, `operationKind`, `billing` = subscription / api_key / custom_endpoint / credits / deployment, `pricingSnapshot`). Other writers: history compaction, auto-review, team-chat judge, media spend (`media-spend.ts`), operator review. Credits: `ModelCreditAccount/Lot/Entry` reconciled by `model-credit-reconciler.ts`. Sandbox time: `ComputerRun`.
- Audit: `AuditEvent` (+ forwarding via `AuditEventForwarding`, `audit-forwarding.ts`), `SecurityEvent`.
- Product analytics: `createProductAnalytics()` (optional).
- Operator diagnostics export: `apps/api/src/telemetry/diagnostics.ts` (opaque ids, no content).

---

## 11. Extension points

1. **Adapter slots** (`packages/adapter-kit/src/registry.ts`): `AdapterRegistry` with `register(slot, adapter)` and slots `runtime`, `sandbox`, `memory`, `home`, `artifacts`, `secrets`, `jobs`, `realtime`, `notifications`, `models`, `connector`, `connection-auth`, `runner`, `voice`, `web`, `browser`, `cloud-agent`, `auto-review`. Interfaces in `packages/adapter-kit/src/interfaces.ts` (e.g. `JobPublisher`, `JobWorkerHost`, `RealtimeFanout`, `AgentRuntime`, `SandboxProvider`). Factories pick implementations from env (`resolveSandboxProvider`, `createSecretStore`, `createWebProvider`, ...). The worker is a manual composition root: the registry class exists, but `apps/worker/src/index.ts` builds objects directly and passes them to `createRunRuntime`.
2. **Agent runtime**: `PiAgentRuntime` (pi-agent-core) default; `ScriptedAgentRuntime` for tests (`AGENT_RUNTIME=scripted`); an ACP runtime for external coding agents (`packages/adapters/src/runtime/acp`).
3. **Sandbox providers**: `packages/adapters/src/providers/computer` (Docker via supervisor, E2B, Daytona, local-vm, host computer).
4. **Connectors**: `createConnectorRuntime` (MCP client with OAuth broker and stdio allow-list, Composio, Pipedream, installed capabilities, cloud agents).
5. **Plugins** (`docs/build-a-plugin.md`): data only. A plugin is a public GitHub repo with `plugin.json` + `mcp.json` pointing at a hosted `streamable-http`/`sse` MCP server. "Rakazo reads the plugin files; it never runs code from the repository." No in-process plugin API found.
6. **Skills** (`docs/skills.md`; `AgentSkill`, `TaughtSkill` tables) and **routines** (`Routine`) are the user-level extension surfaces.
7. **Messaging providers**: `packages/adapters/src/messaging` (Telegram, WhatsApp, Slack, iMessage/SMS surfaces via `ChatSdkMessagingSurface`, `installedMessaging`). Only the API process polls inbound (`pollInboundMessages: false` in the worker).

---

## 12. Proactivity (how an always-on agent is driven)

Proactive behavior is just more runs created by timers and reconciliation, all through `wakeRun`:
- **Routines** (`Routine` row + Graphile `routine.wakeup` job): `wakeRoutine` (`runs/assembly/run-routines.ts`) verifies `nextRunAt === scheduledAt` (so stale jobs no-op), skips deactivated owners (keeps schedule), re-pauses routines of archived bots, optionally runs a **model-free change check** first (`tickRoutineWatch`: "only news becomes a run"), then in a transaction advances `nextRunAt` and creates the run (`trigger: "routine"`). Recurring timer routines coalesce into one pending catch-up run (`routines/routine-coalescing.ts`); a run starting 15+ minutes late is told both times (`routine-lateness.ts`); failures back off and then pause the routine.
- **Strategic initiative** (`routines/strategic-initiative.ts`): a daily check-in (`STRATEGIC_INITIATIVE_INTERVAL_MS = 24 h`) per bot from open scratchpad items, restricted to safe tools (`ask_user`), with a 7-day backoff after a failed check-in. Follow-ups the bot set itself are covered (`pendingFollowUps`).
- **Tickets/board**: assigning a ticket wakes the assignee with no chat message (`wakeTicketAssignee`).
- **Event triggers**: routines can fire on webhooks, GitHub, messages, email senders (`routine-triggers.ts`).
- **Reconciler** re-wakes lost work (section 5.8).

---

## 13. What I could not find / what the code does not do

- No separate relay, edge function or serverless tier. The only forwarding hop is worker -> API for the desktop device socket.
- No dedicated agent-to-agent protocol, message broker or shared agent bus; bot-to-bot is a Postgres transaction + a new run.
- No run-count concurrency limit; admission is memory-only. A runaway number of runs is bounded by memory, not by policy.
- No distributed tracing across processes beyond log correlation and Pi telemetry spans (no OpenTelemetry collector config found in the paths I read).
- No metrics endpoint (Prometheus or similar) found; metrics are log events and the health files.
- Heavy dependence on Postgres: realtime (NOTIFY, 7.9 KB cap), queue, locks and the log all share it; there is no Redis or other broker.
- I did not read the web/mobile code (state management, reconnect logic), the Pi runtime internals, the sandbox supervisor, or the migrations; claims about them come from docs and call sites only.
- `AGENTS.md` and parts of `CLAUDE.md` in the checkout were not used as sources.
- Package `packages/adapters/src/runs/turn/run-model-turn.ts` and `runs/assembly/run-assembly.ts` were identified as the turn entry points but not read line by line here (the loop is covered by a separate Rakazo loop report).

---

## 14. What Lonora should copy / avoid

Lonora context: always-on trading assistant, Python FastAPI server + worker, MT5, lead agent Lonora plus owner-created agents. Money is at stake, so durability and exactly-once matter more than for a chat product.

### Copy

1. **The run row is the queue; the notification is only a nudge.** `wakeRun` never throws, the row (`status`, `wakeAt`, lease) is authoritative, and a 5 s scan finds anything the nudge missed. In Python: a `runs` table with `status`, `wake_at`, `lease_owner`, `lease_fence`, `lease_expires_at`; `NOTIFY` (or in-process call) to start now; periodic `SELECT ... WHERE status='queued' AND wake_at<=now() OR (status IN ('leased','running') AND lease_expires_at<=now()) ... FOR UPDATE SKIP LOCKED`.
2. **Atomic claim with a fence.** One `UPDATE ... WHERE (queued or expired-lease) RETURNING`, bump `lease_fence`, and make every later write (events, results, order records) conditional on `(lease_owner, lease_fence)`. A fenced-out attempt writes nothing. This is the single most valuable pattern for crash recovery; it is what keeps two workers from placing the same trade.
3. **Heartbeat shorter than the lease, with an outage grace rule.** 60 s heartbeat, 5 min lease, tolerate a DB blip only while the lease can still be valid, then abort the attempt (`run-attempt.ts`).
4. **Append-only per-thread event log with a per-thread `seq` allocated under a row lock**, a unique `(thread_id, seq)`, clients resuming by cursor, and NOTIFY as a latch only. Gives mobile/web reconnect for free and an audit trail.
5. **Idempotency everywhere a side effect happens**: client nonce on messages and runs, `ExternalEffect.idempotency_key` unique, effect rows with status (`approved`/`executing`/`uncertain`/`completed`). The `uncertain` status in `PASSED_EFFECT_STATUSES` is exactly the "order sent, no confirmation" state Lonora must model for MT5.
6. **Checkpoint the model transcript at pause and handover** (`TurnCheckpoint`) so waiting for an approval, a restart, or a deploy resumes the turn instead of repeating a model call or a tool call; pair it with effect replay in a stable order.
7. **Graceful drain with hand-back instead of failure**: on SIGTERM stop claiming, let the current step finish (bounded), save, mark `queued` with no error. Never record a failure for a deploy.
8. **Leader-elected reconciler via a Postgres advisory lock**, running slow repairs (stuck waits, undelivered outcomes, lost wake-ups) with batching and a cursor. Plus a **queue-age alarm** (`run.queue_delayed`): an interactive run due but unstarted for 30 s is an error.
9. **Interactive vs background lanes** (and reserved job workers) so a long background run or routine never delays a user message; scan interactive first.
10. **One run per agent's resource at a time** (`ComputerExecutionLease`). For Lonora the equivalent resource is the **MT5 account/terminal**: one run holds it, others stay queued with no timer and the releaser starts the next.
11. **Bot-to-bot as a transactional write + a normal run**, with a hop counter, same-tenant restriction, echo block on both sides, delivery key, and reconciler redelivery of the outcome. Fits "Lonora delegates to owner-created agents" with no new infrastructure.
12. **Routines with a model-free change check** (`tickRoutineWatch`): poll cheaply (price, margin, news diff) and only create a run when something changed. This is the core of a proactive trading assistant that does not burn tokens.
13. **Timer runs coalesce and know they are late** (pending catch-up run reuse, "started 40m late" text to the agent). After downtime the agent must not assume the scheduled time is now, which matters for market data.
14. **Row-level security with an explicit audited system bypass** (`runAsTenant` / `runAsSystem(reason)`), so a forgotten WHERE cannot leak another owner's data. Even for a single-owner start it prepares multi-owner.
15. **Usage ledger without foreign keys**, attributed to run/agent/provider with the billing source and a pricing snapshot, so deleting an agent never erases spend.
16. **Structured timing logs** with explicit definitions (`pre_run_wait`, `queue_wait`, `first_response`, `total`, `execution_wall`) and a health file for the container healthcheck separate from the log sink.
17. **Loop guard and per-turn tool cap** to stop a runaway agent.

### Avoid or adapt

1. **Do not put realtime, queue, locks and log on one Postgres without sizing it.** Rakazo needs `DB_POOL_MAX >= 6` just for listeners and leadership; NOTIFY payload is capped at 7.9 KB. Keep payloads to ids.
2. **Do not copy the 148-model schema or string statuses without constraints.** Rakazo status columns are free strings; use a CHECK constraint or enum in Postgres plus a Python state machine like `canTransition`.
3. **Memory-only admission is not enough for trading.** Add a hard per-agent and global cap and a priority for risk-reducing runs (close/stop) over new-position runs. Rakazo has no such cap.
4. **Do not let the same process both serve HTTP and execute runs without a clear drain story.** Rakazo does it (API starts runs in-process) and needs SIGUSR2 plus image labels to deploy safely. In Lonora, prefer FastAPI only writing the run row and `NOTIFY`, with the worker executing; keep one in-process start only if latency demands it.
5. **Avoid the sprawl of triggers and special cases** (13+ trigger strings, many bespoke job kinds). Start with `user`, `routine`, `agent_message`, `broker_event`, `resume`.
6. **Do not rely on a model-visible tool call being replayed safely.** Rakazo replays approved effects; for money, an effect must be recorded as `intended` before the broker call and reconciled against MT5 afterwards (position/order lookup by magic number or comment), because a crash between send and record leaves it `uncertain`.
7. **No plugin execution model to copy.** Rakazo plugins are MCP URLs only (data, never code). For Lonora that is the right safety posture, but anything touching order placement must stay inside the trusted server, not an external MCP tool.
8. **Observability gap:** Rakazo has logs and health but no metrics endpoint or tracing across processes. Add Prometheus counters (queue age, runs by status, lease expirations, fenced writes rejected, reconcile repairs) from day one.
9. **Desktop-style forwarding hop (worker -> API socket holder)** is only needed for a user-device websocket. If Lonora needs a push channel to a user's machine (e.g. an MT5 bridge), put the socket in the worker or a dedicated gateway to avoid cross-process forwarding.
10. **Stuck-work policy:** 4 h notify / 24 h expire for waiting runs is fine for chat, too slow for a trade approval. Make approval expiry per action type (minutes for market orders).
