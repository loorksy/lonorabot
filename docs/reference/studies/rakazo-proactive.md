# Rakazo: proactive agents (work without a user message)

Scope: how a Rakazo bot acts on its own, based on files read in the read-only clone of `elie222/rakazo`.
All paths are repo-relative. Nothing was executed.

## 0. One-paragraph model

Rakazo has no always-on agent loop and no "heartbeat prompt". Proactive work is **durable rows plus a job queue**:

- A **routine** row (`routines` table, `packages/db/prisma/schema.prisma`, `model Routine`) holds a prompt, cron(s), a timezone and `nextRunAt`.
- A Graphile-worker job named `routine.wakeup` is enqueued for `nextRunAt`. Its key is `routine:<id>`, so there is one pending wake per routine.
- When it fires, `wakeRoutine` creates a `Task` and a `Run` with `trigger: "routine"`, then enqueues `run.continue`. That is the ordinary agent turn.
- A **change watch** is a routine whose wake first runs a model-free checker, `tickRoutineWatch`. A run is created only if the fingerprint changed.
- **Outside events** (webhook, GitHub, email, chat message) do not create runs directly. They find the matching active routines and post a synthetic user message with `trigger: "webhook"`.
- A **leader-elected reconciler** (every 30 s) re-enqueues anything the queue lost. That includes routine wakes, queued runs and expired leases.
- "Tell the user or stay quiet" is decided **by the model**. It replies exactly `NO_RESPONSE` and the server suppresses the bubble and the push (section 6). There is no server-side importance score, digest or quiet-hours logic.

Things Rakazo does NOT have (searched, not found): a periodic heartbeat/inbox-poll agent, quiet hours or do-not-disturb windows, digests, importance scoring, a per-run or per-day token/cost budget for autonomous runs, file-event or data-feed push triggers (only polled watches). Details in section 9.

## 1. The moving parts (and the files)

| Piece | Files |
|---|---|
| Worker process (queue host, reconciler, health) | `apps/worker/src/index.ts` |
| Job names, payloads, keys | `packages/adapter-kit/src/background-jobs.ts` (`routineWakeupJob`, `routineRetryJob`, `runContinueJob`, `routineJobKey`) |
| Graphile publisher/host (dedupe by key, replace, interactive vs background task split) | `packages/adapters/src/runs/wakeups/wakeup.ts` (`GraphileJobPublisher`, `GraphileJobWorkerHost`) |
| Run-aware worker host and starter | `packages/adapters/src/runs/wakeups/run-wakeup.ts` (`RunStarter`, `RunJobPublisher`, `RunWorkerHost`, `withRunWorker`) |
| Job -> handler map (tenant scoping) | `packages/adapters/src/runs/wakeups/background-job-handlers.ts` (`createBackgroundJobHandlers`, `asOwner`) |
| The routine tick | `packages/adapters/src/runs/assembly/run-routines.ts` (`wakeRoutine`, `retryRoutineRun`, `scheduleRoutineRetry`) |
| Cron math | `packages/core/src/routines/schedule.ts` (591 lines; I used it only through its callers `nextRoutineRunDateAcross`, `nextCronDateAcross`, `isOneShotRoutineCrons`) |
| Change watcher | `packages/adapters/src/routines/routine-watch.ts`, `packages/contracts/src/routines/routine-watch.ts` |
| Event triggers | `apps/api/src/webhooks/webhook.ts`, `webhook-inbound.ts`; `apps/api/src/email/email-inbound.ts`; `apps/api/src/messaging/messaging-inbound.ts` (`wakeMessageRoutines`) |
| Agent-created schedules | `packages/adapters/src/tools/schedule-tools.ts` (`createScheduleFromTool`, `MAX_ACTIVE_ROUTINES_PER_BOT`) |
| Self-follow-up and daily check-in | `packages/adapters/src/runs/assembly/run-instructions.prompt.ts` (`FOLLOW_UP_INSTRUCTION`), `packages/adapters/src/routines/strategic-initiative.ts` |
| Silent/noisy decision | `packages/adapters/src/runs/assembly/silent-reply.ts`, `run-replies.prompt.ts`, `packages/adapters/src/runs/lifecycle/run-complete.ts` (`finalReply`) |
| Notify | `packages/adapters/src/runs/lifecycle/run-notifications.ts` |
| Failure policy | `packages/adapters/src/routines/routine-backoff.ts`, `routine-failure-pause.ts`, `run-routines.ts`, `packages/adapters/src/runs/lifecycle/run-fail.ts` |
| Unattended safety | `packages/core/src/runs/action-approval.ts`, `packages/adapters/src/approvals/approval-expiry.ts`, `packages/adapters/src/runs/assembly/run-trust.ts` |
| Control surface | `apps/api/src/routes/routines.ts`, `apps/api/src/routines/routine-runs.ts`, `packages/contracts/src/routines/routines-rpc.ts`, `docs/routines.md` |

## 2. Data model: what a "proactive job" is

`model Routine` (`packages/db/prisma/schema.prisma:1582`) has these fields. I list only the proactive-relevant ones.

- Identity: `botId`, `userId` (the owner whose accounts it runs with), `threadId` (group chat, or null = bot's own chat), `name`, `prompt`.
- Timing: `crons String[]` (several allowed), `timezone`, `nextRunAt`, `lastRunAt`, `endsAt`, `active`.
- Event triggers: `webhookEnabled`, `githubEnabled`, `messageProvider`, `emailSenders` (`"owner"` or `"domain"`).
- Watch: `watch Json?` (the spec), `watchState Json?` (last fingerprint and detail).
- Per-routine model pin: `modelProvider`, `modelId`, `thinkingLevel`.
- Notification and placement: `notify Boolean @default(true)`, `inChat Boolean` (run as a turn in the chat vs alongside it).
- Safety/health: `accountFailures` (backoff counter), `failurePausedAt`, `resumeOnRestore`, `computerPromptHash` (owner-approved prompt for using the owner's own computer).

A routine with only event triggers has `crons: []` and `nextRunAt: null` (see `eventsOnly` in `createScheduleFromTool`).

One-time reminders are routines whose cron is the `ONCE_ROUTINE_CRON` sentinel (`isOneShotRoutineCrons`). After firing, `active` goes false.

The run row carries `trigger` (`routine`, `webhook`, `messaging`, `bot_message`, `tickets`, `user`, ...), `routineId`, `clientNonce` (idempotency) and `lateSince`. See `packages/core/src/runs/run-state.ts` for trigger groups.

## 3. Flow A: "a scheduled job fires"

Numbered, with exact functions.

1. **Arming.** A routine is created or edited through one of two paths. Both end in `jobs.enqueue(routineWakeupJob(id, nextRunAt))`, which writes a Graphile job with `runAt = nextRunAt` and `jobKey = routine:<id>` (replace semantics, so re-arming just moves the time).
   - UI path: `routes/routines.ts` `create`/`update` handlers.
   - Agent path: `createScheduleFromTool` in `schedule-tools.ts`. If the enqueue throws, the row is deleted, or deactivated if the delete also fails, and the tool returns "Could not schedule the reminder".
2. **Dispatch.** The worker (`apps/worker/src/index.ts`) boots a Graphile host via `createReservedGraphileJobWorkerHost` wrapped by `withRunWorker`. Concurrency is `GRAPHILE_WORKER_CONCURRENCY`, default 4. At `runAt`, `background-job-handlers.ts` runs the `"routine.wakeup"` handler.
3. **Tenant scoping.** `asOwner(routine, ...)` does a narrow `runAsSystem` read of the routine's `{spaceId, userId}`. It then calls `runAsTenant` so row-level security applies to everything the handler and its tools touch.
4. **`executor.wakeRoutine(routineId, scheduledFor)`** is `wakeRoutine` in `run-routines.ts`. It is a chain of guards:
   - Ignore if the routine is inactive or deleted. Also ignore if `routine.nextRunAt !== scheduledAt`. This is the stale-job guard: an edit that moved the schedule makes old jobs no-ops.
   - `deferFutureRoutine`: if the job fired early (more than 1 s before the time), re-enqueue for the exact time.
   - Past `endsAt` -> `endRoutinePastItsEnd` and return.
   - `accountDeactivated(owner)` -> skip this occurrence. A recurring or watching routine keeps its schedule; a one-shot is spent.
   - Archived bot -> re-pause the routine with `resumeOnRestore: true`.
   - `routineGroupThreadId` (`routine-thread.ts`) picks the chat: the group it was made in, or the bot's own thread.
5. **Watch gate (only if `routine.watch != null`).** `tickRoutineWatch` runs with no model. If it returns `{run:false}` the wake ends. See flow B-3.
6. **Compute the next occurrence.** `nextScheduledRunAt` is null for one-shot. For a watch it is `watchTick.nextRunAt`. It is clipped by `runBeforeEnd(next, endsAt)`.
7. **One transaction claims the occurrence.** `prisma.$transaction`:
   - `spaceTakesWork(tx, spaceId)` refuses if the Space is being deleted.
   - `tx.routine.updateMany({where:{id, userId, active:true, nextRunAt: scheduledAt, ...}, data:{lastRunAt, nextRunAt, ...}})`. This is an optimistic claim. If `count !== 1`, another worker or an edit won, and it returns.
   - The prompt is re-read inside the claim, so a prompt edit cannot pair with an older model pin. Skill references are expanded by `expandSkillReferencesInPrompt`. A watch note is appended.
   - For recurring timer ticks, `timerNonce = routine-timer:<routineId>:<scheduledFor>` (`routine-coalescing.ts`).
     - `findPendingRoutineTick` **coalesces catch-up backlog**. If an unstarted run with the same prompt/model already exists, the new tick reuses it. Surplus duplicates are cancelled with `run.cancelled {reason: "routine_coalesced"}`.
     - If an earlier tick of this timer is still active (including waiting for the user), return `"skipped"`.
     - If a run for this exact nonce already exists, return `"skipped"`. The `(spaceId, clientNonce)` unique index backs this.
   - Otherwise create `Task{status: queued, prompt}` and `Run{trigger:"routine", routineId, clientNonce, ...routineRunModelPin}`.
8. **After commit.**
   - `wakeRun(jobs, runId, {keepExisting: coalesced})` enqueues `run.continue`. `wakeRun` (`wake-run.ts`) never throws. The run row is the durable record and the reconciler recovers a lost nudge.
   - Best-effort append of a `routine.fired` event to the thread.
   - Re-arm: enqueue the next `routine.wakeup`, or `jobs.cancel(routineJobKey)` if there is no next run. Skipped one-shots with `endsAt` are deleted by `deleteSpentRoutine`.
9. **Chat serialisation.** `run.continue` claims the run. `claimWaitsForChat` (`runs/lifecycle/chat-wait.ts`) makes a routine run wait while the same bot is busy in that chat, unless `routine.inChat === false`.
   - After `CHAT_WAIT_MS` (5 min) a still-waiting routine **hands its prompt to the running turn** (`handQueuedRunToWorkingRun`, text from `dueRoutineHandoverPrompt`: "Your scheduled task "X" came due. Do it now: ...").
   - A routine that was queued from a watch is not handed over, because the note quotes watch data.
10. **The agent turn.** Assembly (`run-assembly-context.ts`) adds `routineRunInstruction`: "This is one scheduled run... do the work now, and do not schedule it again..."
    - If the run started at least 15 min after its due time (`lateRoutineRunDueAt`, `LATE_ROUTINE_RUN_MS`), it also adds `lateRoutineRunInstruction`.
    - The reply guidance is `ROUTINE_SILENT_REPLY_GUIDANCE` (section 6).
    - Tools: `schedule_update` is hidden from routine runs (`ROUTINE_RUN_HIDDEN_TOOLS`).
11. **Completion.** `run-complete.ts`:
    - `finalReply` -> `stripNoResponseReply`. If silent, no bubble and `markUnread` is false.
    - `clearRoutineBackoff`.
    - `deleteSpentRoutine` for finished one-shots.
    - Finish notification via `notifyRun` (section 6).
12. **Failure.** `run-fail.ts`: see section 8.
13. **Self-healing.** Every 30 s the elected reconciler (`createJobReconciler`) pages through `routines where active and nextRunAt <= now + 60s` and re-enqueues `routineWakeupJob(id, nextRunAt)`. Replace-by-key makes it idempotent. A lost job or a crashed worker therefore only delays a routine.

## 4. Flow B: "an outside event wakes an agent"

### B-1 Webhook (also used by email/chat)

1. `POST /api/v1/bots/:botId/webhook` is in `apps/api/src/webhooks/webhook.ts` (`mountWebhookHttpRoutes`).
2. Body is bounded to `WEBHOOK_MAX_BODY_BYTES = 64 KiB` **before** any lookup, so size limits do not reveal which bots exist.
3. `loadWebhookTarget`:
   - Bot must be non-archived, have a thread and a `webhookSecretId`, and its owner must not be deactivated.
   - The secret is decrypted through a 30 s cache. The secret row must match the bot's user and space, and be re-checked after decrypt in case of rotation.
4. Auth is either `Authorization: Bearer <key>` (`hasValidBearerToken`) or an HMAC signature (`hasValidWebhookSignature`, `webhook-id`/`webhook-timestamp`/`webhook-signature` or the `svix-*` headers). Every failure returns the same 401.
5. Find routines: `prisma.routine.findMany({where:{botId, spaceId, userId: bot.userId, active:true, webhookEnabled:true}, orderBy updatedAt desc, take: 5})`. **No routine -> `{ok:true, ignored:true}`.** A webhook never wakes the bot on its own.
6. `parseWebhookPayload` + `formatWebhookPrompt`. The idempotency key is the signed `webhook-id`, an `Idempotency-Key` header, or the raw body if the payload has an `id`/`event_id`.
7. `deliverWebhookEvent` (`webhook-inbound.ts`) builds the prompt. The owner's routine prompts come first as `Run routine "<name>":\n<prompt>`, then a labelled untrusted block (`Inbound webhook payload:` / `Inbound email:` / `Inbound messaging event:` / `Inbound GitHub event metadata:`). Order and exact-match structure let `inboundRoutinePrompts` (`packages/core/src/routines/inbound-routine.ts`) later separate owner words from payload text.
8. `events.sendUserMessage({blocks:[{kind:"delivery"}, text...], trigger:"webhook", clientNonce, modelPin})` creates the message and the queued run in one call. Then `wakeRun(jobs, runId)`.
9. The run is an ordinary agent turn, but with outside-text rules (section 7).

### B-2 Email and chat

- **Email.** `apps/api/src/email/email-inbound.ts`:
  - Looks up the bot by its own address (`BotEmailAddress`).
  - Requires an authenticated sender, rejects automated mail, bot-sent mail and mail where the bot is only BCC'd.
  - `allowed` is `["owner","domain"]` for the owner's address, `["domain"]` for the owner's domain, else none.
  - Routines are matched with `emailSenders in allowed`. Every message is stored in the bot's inbox (500/day cap, `INBOX_DAILY_LIMIT`) whether or not it starts anything.
  - If there is no routine, an owner-written mail to the bot (`To:` only, verified, DKIM-authenticated) starts a normal turn.
  - It then calls the same `deliverWebhookEvent` with `source: "email"`.
- **Chat message.** `wakeMessageRoutines` in `apps/api/src/messaging/messaging-inbound.ts` finds routines with `messageProvider = event.provider` owned by the identity's person. Then it calls `deliverWebhookEvent(source:"messaging", allowParallelRun:true)`, optionally claiming a deferred external message in the same transaction so the agent cannot also answer it. If any message routine exists, it owns delivery and the normal reply path is skipped.

### B-3 Change watch (polling; the only "monitor")

1. `schedule_create` with `watch`, or the UI, stores `routine.watch` and arms `firstWatchCheck()` (about 2 s later).
2. At each wake, `wakeRoutine` -> `tickRoutineWatch` -> `checkRoutineWatch`. Kinds (`RoutineWatchSchema`): `files` (path size/mtime in the bot's computer), `command` (shell output), `tool` (read-only connector tool), `http` (public HTTPS GET, no headers, no redirects). `track` narrows JSON to named fields so a timestamp is not a change.
3. `compareReading(previous, reading, now)` gives `baseline | unchanged | changed | failed` plus a human description. No model is called.
4. Outcomes:
   - **changed:** returns `{run:true, state, nextRunAt, note}`. `wakeRoutine` appends `routineWatchNote(...)` ("This run was started because something you watch changed (...)") to the prompt and persists `watchState` inside the claim transaction.
   - **unchanged/baseline:** updates `watchState` and `nextRunAt`, enqueues the next wake, creates **no run**. If `watch.loud` is true, it posts a `role:"system"` meta line "<name> routine: no changes" without a model run.
   - **transient failure** (`RoutineWatchRetry`, `VaultKeyUnavailableError`): retry in 60 s. For HTTP, retry at the normal interval and post one "I'll keep checking" line.
   - **hard failure:** pause the routine (`active:false`), cancel the job, and post a bot message "I paused the X routine because its change check failed: ... Reply here and I'll help fix it."
5. Bounds: interval 5 min to 1440 min (`ROUTINE_WATCH_MIN_MINUTES = 5`), default 15. `command` watches run "without a model or per-run approval, equivalent to the bot running the command itself" (comment in `contracts/src/routines/routine-watch.ts`). `validateRoutineWatch` and `assertWatchToolReadOnly` restrict tool watches to read-only tools.

### B-4 Wakes that are follow-ups of the agent's own earlier work

- **Delegated async jobs wake the originating run** with a canned prompt (`runs/wakeups/wakes.prompt.ts`):
  - `cloudAgentWakePrompt`: "Cloud agent X is <status>. Use cloud_agent_status..."
  - `purchaseWakePrompt` and `mediaVideoWakePrompt`.
  - The pollers are jobs `cloud_agent.poll`, `purchase.poll`, `media.poll` in `background-job-handlers.ts`. `pollCloudAgent` (`cloud-agents/cloud-agent-poll.ts`) uses a DB lease (`withLease`) and re-schedules itself.
- **Bot-to-bot.** `messageBot` (`packages/adapters/src/messaging/bot-messages.ts`) writes a message in the other bot's thread and creates a `trigger:"bot_message"` run, woken by `wakeRun`.
  - Hop limit: `nextBotMessageHop` / `botMessageHopExhausted`. When exhausted: "bot-to-bot message limit reached for this chain; report back to the user".
  - The reply returns to the asker (`returnBotMessageOutcome`), and the reconciler retries undelivered outcomes. See `job-reconciler.ts`.
  - `bot_message` runs are "unattended" for approvals (section 7).
  - `PEER_NOTHING_NEW_REPLY = "Nothing new to add."` replaces a `NO_RESPONSE` for peer asks (`peerReplyWithoutSentinel`).

## 5. How an agent schedules its own follow-ups

- The prompt (`FOLLOW_UP_INSTRUCTION` in `run-instructions.prompt.ts`) says: "Do not wait to be asked about open loops. When something is left open until a known time, you may schedule_create one one-shot follow-up for then that checks the scratchpad item and stays silent if it is done, and record the follow-up's routineId in that item's notes. When the item is resolved, complete it and schedule_cancel its follow-up. Never follow up on something the user declined."
- Tools: `schedule_create`, `schedule_list`, `schedule_update`, `schedule_cancel` (`SCHEDULE_TOOL_NAMES`). They are also used for "remind me in 20 minutes".
- Cost guard: `MAX_ACTIVE_ROUTINES_PER_BOT = 50` ("Each routine is an unattended model run, so a looping bot must not stack them.") and a same-name conflict check in `activeRoutineConflict`.
- Approval: `schedule_create` and `schedule_update` are in the built-in approval list in `action-approval.ts`. `lastingWriteKind` classifies them as a `"routine"` lasting write. That means a prompt-injected run cannot silently plant a standing instruction; the owner's own words are what the review judges against.
- Daily check-in (`strategic-initiative.ts`):
  - Hourly sweep inside the elected reconciler (`createStrategicInitiativeReconciler`).
  - Eligible: bot has `dailyCheckIns`, has open scratchpad items untouched for at least 12 h, is not on a computer-using run, and has no check-in in the last 24 h (7 days after a failed one).
  - Skipped if the owner has no model access (`memberHasModelAccess`) when billing is on.
  - Creates a `trigger:"routine"` run with `clientNonce = STRATEGIC_INITIATIVE_NONCE_PREFIX:<bot>:<day-bucket>` (one per day per bot, enforced by the unique nonce).
  - **Tool allowlist is only `ask_user`** (`STRATEGIC_INITIATIVE_SAFE_TOOL_NAMES`, enforced both when offering tools and at dispatch).
  - The prompt (`strategic-initiative.prompt.ts`) says: "If no high-signal action is needed right now, the entire final reply must be exactly NO_RESPONSE... This check-in cannot do or start the work itself, so never say you are doing it."
  - Items untouched 14 days are auto-parked (`parkForgottenOpenWork`), unless a pending one-shot follow-up covers them.
  - Its failure is never notified (`!isStrategicInitiativeRun(run)` in `run-fail.ts`).

## 6. Tell the user or stay quiet

There is no importance classifier. The policy is split between the prompt and a few server rules.

1. **Model-side decision.** For routine/webhook runs `runReplyGuidance` returns `ROUTINE_SILENT_REPLY_GUIDANCE` (`run-replies.prompt.ts`): "...the entire final assistant reply must be exactly NO_RESPONSE — no surrounding prose, no variants, no progress updates, no all-clear... Do not call message_user unless you have something to report. Nobody is waiting on this run: call ask_user only for a real decision the person must make".
2. **Server-side enforcement** (`silent-reply.ts`, used in `run-complete.ts` `finalReply`):
   - `isExactNoResponse` accepts the sentinel once or repeated.
   - `stripNoResponseReply` drops the text blocks, so no bubble is created.
   - Mixed (sentinel plus prose) fails closed and the reply is kept.
   - Stray sentinels at the edges of real prose are trimmed.
   - A lone "." or invisible text counts as a placeholder (`isPlaceholderText`).
3. **Unread/notify follow.** `completionMarksUnread(trigger, text)` returns true for routine/webhook runs only if they actually produced text. An empty run does not mark the chat unread.
4. **Push/alert policy** (`run-notifications.ts`, `notifyRun`):
   - Completion push is on if `thread.groupId || bot.notifyOnFinish`. A routine's own `notify` flag decides only its **failure** notices.
   - Failures, questions and takeovers always reach the run's user (not the whole Space), even when the chat is snoozed.
   - Completions go to every Space member, except those who snoozed that thread (`membersSnoozing`, `threadRead.snoozedUntil`).
   - `tickets` background runs are silent except for `help`/`takeover` notices.
   - Pushes carry the unread-chat badge.
   - Text is capped at 180 chars (`COMPLETION_NOTIFICATION_MAX_CHARS`) and redacted for secrets.
5. **Stuck waits.** `reconcileStuckWork` (`runs/lifecycle/stuck-work.ts`): a run waiting on the user for `STUCK_WORK_NOTIFY_AFTER_MS = 4 h` gets a reminder push (claimed in the DB with a 2 min TTL so retries do not double-send), then is cancelled after `STUCK_WORK_EXPIRE_AFTER_MS = 24 h`. Both are env-overridable.
6. **Not present:** quiet hours or do-not-disturb schedules, digests/batching of many small notices, per-source importance. Only per-chat snooze, per-bot `notifyOnFinish`, per-routine `notify` and the `loud` flag for watch "no changes" lines.

## 7. Safety for unattended runs

- **Outside-text trust.** `trigger: "webhook"` runs (also email and chat wakes) are treated as carrying attacker-writable text. `outsideRunToolRequiresApproval(trigger, tool)` in `action-approval.ts` returns true for every built-in tool not in `OUTSIDE_RUN_SAFE_BUILTIN_TOOLS` (look-only tools, `message_user`, `ask_user`, `schedule_list`, and so on).
- **Owner words.** `loadOwnerWords` in `run-trust.ts` returns, for `routine` runs, `routineTaskInstructions(taskPrompt)`. That is the prompt saved when the routine fired, minus the watch note. For `webhook` runs it returns only the routine prompts recovered by `inboundRoutinePrompts`. Auto-review judges new sites, memory writes and lasting writes against these words only.
- **Unattended approvals expire.** `approvalCardExpires(trigger)` is true for `routine, webhook, bot_message, spawn, tickets`. `scheduleApprovalExpiry` enqueues `approval.expire` in the same transaction that pauses the run. `expireApprovalCard` auto-answers "deny" with `expired:true` and wakes the run. Default 30 min, env `UNATTENDED_APPROVAL_EXPIRE_AFTER_MS` (`docs/routines.md`).
- **Owner computer.** A routine may use the owner's own computer only if its prompt hash matches `computerPromptHash`. A DB trigger clears the hash when the prompt, owner or bot changes (comment on `Routine.computerPromptHash`).
- **Event routines run only as the bot's creator.** Every query filters `userId: bot.userId`.
- **Watch command** runs with no approval but is owner-authored.
- **Quarantined unknowns:** webhook/email payloads are fenced under a labelled untrusted heading after the owner's instructions.

## 8. Cost, budget and failure guards for autonomous runs

What exists:

- **Fan-out caps:** 50 active routines per bot; webhook picks at most 5 routines per delivery (`take: 5`); watch min interval 5 min; 64 KiB webhook bodies; 500 inbox mails/day/bot.
- **De-duplication:** per-occurrence nonce (`routine-timer:<id>:<iso>`), coalescing of unstarted catch-up ticks, skip while an earlier tick of that timer is active, and webhook idempotency keys. This is what stops backlog storms after downtime.
- **Lateness note** to the model after a 15 min delay.
- **Per-routine model pin** (cheaper model for a daily check, from `docs/routines.md`). `routineRunModelPin` and `inboundRoutineModelPin` copy it to the run.
- **Billing gate:** the daily check-in is skipped when the owner has no model access (`memberHasModelAccess`). Model credit billing is a separate subsystem (`modelCreditBillingEnabled`). I did not read it.
- **Account-error backoff** (`routine-backoff.ts`):
  - When a provider refuses the owner's key, plan, credit or model (`ACCOUNT_REFUSAL_KINDS`: auth, access, key, credit, spending, model), `backOffRoutineAfterAccountError` pushes the next run out by 5 min x 2^(n-1), capped at 24 h. If the provider names a reset time it uses that instead (capped at a day).
  - `clearRoutineBackoff` runs on the next success.
  - `releaseRoutineBackoffs` runs when the owner saves a new connection, so held routines resume immediately.
- **Auto-pause after repeated failure** (`routine-failure-pause.ts`): 5 consecutive failed runs of the same failure cause (`ROUTINE_FAILURE_PAUSE_AFTER`) set `active:false`, `failurePausedAt`, and post "I paused the **X** routine because its last 5 runs failed: <reason>. Reply here and I'll help fix it." Server-side internal errors do not count.
- **One transient retry** (`scheduleRoutineRetry`): a `TransientModelError` before any tool call or message gets one retry 12 min later (`ROUTINE_RETRY_DELAY_MS`). It is skipped if the next occurrence is within 30 min.
- **Failure notice:** after the retry is exhausted, `notifyRoutineRetryAttemptsExhausted` pushes a "failed" notice (the reconciler-driven `createRoutineRetryNoticeReconciler` backs this up) and deletes an ended routine.
- **End date:** `endsAt` stops the routine. The last run is told it is the last. Webhook/event routines cannot have an end date.
- **Stuck work:** 4 h reminder and 24 h cancel (section 6).
- **Wake path robustness:** Graphile retries, `keepExisting` dedupe, dead-job pruning (`createDeadJobPruner`), lease expiry recovery in the reconciler, a Space-deletion guard (`spaceTakesWork`), and deactivated-account skipping.

What does NOT exist (searched `budget`, `quota`, `cap`, `token` in `routines`, `runs` and docs): no per-run token or dollar ceiling for routine runs, no daily spend cap per routine or per bot, and no "stop all autonomous work now" switch other than pausing routines one by one or archiving the bot (which re-pauses its routines with `resumeOnRestore`). I saw `groq-request-budget.ts` and `openrouter-output-budget.ts` in the file list but did not read them. They are provider request budgets, not autonomy budgets.

## 9. Heartbeats, always-on loops, data feeds: what the code actually does

- "Heartbeat" in this repo means SSE keep-alives (`apps/api/src/routes/account.ts`, `threads.ts`) and **run lease heartbeats** (`stopHeartbeatAfterCompletion` in `run-complete.ts`). It does not mean "wake the agent every N minutes with a checklist".
- Always-on loops are infrastructure, not agent logic:
  - `createJobReconciler`: 30 s interval, Postgres-advisory-lock leader election (`createPostgresReconciliationLeadership`), housekeeping passes for cloud agents, purchases, video, model credits, retention, idle computers, dead jobs, and the strategic-initiative sweep.
  - The Graphile worker poll loop.
  - Worker `health.ts` (`startWorkerHealth(reconciler.lastCompletedAt)`; I read only the call site).
- Data feeds: no push feed subscriptions. A "feed" is a `tool` or `http` watch polled every 5 min or more. Calendar and meeting sync exist (`meeting.calendar-sync` job) but I did not read them, so I make no claim about their proactive behaviour.
- File changes: only through `files` watches that stat paths on the bot's computer each interval. No inotify-style push.
- Heavy "release-watch" code in `routines/release-watch.ts` is **eval scaffolding** (emulated GitHub releases, model id for tests), not a runtime feature.

## 10. User visibility and control

- **Chat-native creation:** "Every weekday at 8am, summarize my inbox" -> the bot calls `schedule_create` and a `routine_event` system row ("created/updated/enabled/disabled/deleted") appears in the chat (`postRoutineNotice`, `routine-notice.ts`). The block has no text, so the model never sees it. It never contains the prompt, and a webhook key is only flagged, never included.
- **RPC surface** (`packages/contracts/src/routines/routines-rpc.ts`, handlers in `apps/api/src/routes/routines.ts`):
  - `routines.list(botId)`, `listForMentions`
  - `history({routineId, before, limit})` -> `listRoutineRuns`
  - `create`, `update`, `remove`, `testRun`
- **Update rules:** any member of the Space may toggle `active` or delete (`remove`). Only the owner may change prompt, schedule, triggers or model (`FORBIDDEN` otherwise). Archived bots keep routines paused.
- **Pause/resume:** `update({active})` also sets `resumeOnRestore:false` so a bot restore does not undo an explicit choice. If the schedule needs syncing the handler re-enqueues or cancels the wake job (`routineWakeupJob` / `jobs.cancel(routineJobKey)`).
- **Run now:** `testRun` uses the same chat a tick would (`routineRunNowTarget`) and a client nonce for idempotency.
- **History:** `listRoutineRuns` returns id, status, `error` (via `runFailureError`), `createdAt/startedAt/completedAt`, `lateSince`, and the id of the first bot message the run posted (`messageId`), so silent runs are visible but have no link. Cursor-paged (`ROUTINE_HISTORY_PAGE_SIZE`). Web and mobile format lateness via `routineRunLateness` (`packages/core/src/routines/routine-runs.ts`).
- **Live state:** `routineScheduleDelayed` (`packages/core/src/routines/routine-dispatch.ts`) flags a routine whose `nextRunAt` is more than 5 min stale, because "a stale dispatch time is not proof that the worker is offline". The UI shows **Running** plus **Stop** for an active run.
- **UIs (listed, not read):** `apps/web/src/pages/routines/*` (RoutineEditor, RoutineList, RoutineRunHistory, trigger-cards) and `apps/mobile/app/routine*.tsx`, `apps/mobile/components/routines/*`. Per `docs/routines.md`, mobile edits name, instruction and schedules but only displays webhook/Git/Slack/watch triggers and per-routine model.
- **Edit-race safety:** `update` uses a conditional write and returns `CONFLICT "Routine changed; retry."` on `P2025` instead of overwriting.

## 11. Gaps and things the code does not do

1. No agent-level wake that is not a routine row. Even "daily check-in" is a synthetic routine-trigger run with a nonce. There is no free-form "think about what to do now" loop.
2. No server-side importance or digest. If a model forgets `NO_RESPONSE`, the user is notified.
3. No quiet hours.
4. No spend or token budget for autonomous runs. The only cost brakes are counts (50 routines, 5 per webhook, 5 min watch floor), model pinning and failure/account backoffs.
5. Watches cannot be combined with a schedule (`docs/routines.md`). Event-only routines cannot have an end date.
6. A watch `command` runs with no approval (by design, owner-authored).
7. I did not read: `schedule.ts` internals, `run-wakeup.ts` internals (queue ordering), the web/mobile routine UI, `routine-owner-computer.ts`, `routine-end.ts` bodies beyond the head, `apps/api/src/routines/routines.ts` beyond grep, `github-webhook.ts` beyond its imports, billing internals, or `docs/run-execution.md`. Claims about those are limited to what the files I did read call into.

## 12. What Lonora should copy / avoid

Lonora context: MT5 trading assistant, FastAPI server and worker, web and Expo clients, lead agent "Lonora" plus owner-created agents.

### Copy

1. **One durable row + one keyed queue job per schedule.** `routine.wakeup` keyed by routine id means re-arming is idempotent. The handler's `nextRunAt === scheduledFor` check turns stale jobs into no-ops. Do the same with your Python worker (a `schedules` table, `UPDATE ... WHERE next_run_at = :scheduled_for` as the claim).
2. **Claim the occurrence in the same transaction that creates the run**, with a per-occurrence unique nonce (`routine-timer:<id>:<iso>`). Coalesce catch-up ticks after downtime and skip while the previous tick is still active. For a trading bot this prevents a restart from firing 40 stale "check positions" runs.
3. **A reconciler that re-enqueues everything due** (routines in the next 60 s, queued runs, expired leases) under leader election. Treat the queue as a hint and the DB as truth.
4. **Model-free watchers.** A checker that fingerprints something and only starts a model run on change. Directly useful: poll MT5 positions, equity drawdown, a news feed or calendar, and only wake the agent on a diff. Copy the `baseline/unchanged/changed/failed` outcome set, `track` fields to ignore noise, a minimum interval, and "pause and explain in chat after a hard failure, back off quietly on a transient one".
5. **Silent-by-default instruction + exact sentinel enforced server-side.** Copy the sentinel stripping (`NO_RESPONSE`, fail closed on mixed text, repeated sentinel tolerance) and the rule that a silent run does not mark the chat unread or push. Add what Rakazo lacks: a server-side severity field (`info | needs_attention | urgent`) so risk events always notify and routine chatter can be batched.
6. **Account-error backoff and auto-pause after N identical failures.** Copy `ACCOUNT_REFUSAL_KINDS`, the doubling backoff capped at 24 h, release on reconnect, and "5 same-cause failures -> pause and tell the user in chat".
7. **Late-run note** to the model ("this run was due 09:00, now 09:40, adapt"). Time-of-day assumptions matter more for trading sessions.
8. **Unattended-approval expiry.** Approval cards from autonomous runs auto-deny after about 30 min and the run resumes told "nobody answered". For Lonora, trade-approval cards from autonomous agents should expire the same way and fail closed.
9. **Outside text is never owner instructions.** Keep the exact-match owner-words structure (`inboundRoutinePrompts`) so an email, webhook or broker/news payload cannot be mistaken for the owner's mandate. Gate every state-changing tool on runs started by outside events.
10. **Agent follow-ups as a first-class tool.** `schedule_create` one-shot with the id recorded in the work item's notes, cancelled when the item resolves. Rakazo's cap of 50 active schedules per bot is a cheap guard. Keep follow-ups owner-approved as a "lasting write".
11. **Run history with silent runs visible.** The history lists every run with status, error, lateness and "first message" link, even when nothing was posted. For trading this is the audit trail of "the agent checked and decided to do nothing".
12. **Daily strategic check-in** restricted to a tiny allowlist (`ask_user` only). A good pattern for the Lonora lead agent's morning review: read-mostly, one question or one reminder, otherwise `NO_RESPONSE`.
13. **Bot-to-bot with a hop limit** and return-to-sender semantics (`nextBotMessageHop`, `returnBotMessageOutcome`, `Nothing new to add.` instead of the sentinel for peers). Needed for Lonora-to-agent delegation without loops.
14. **Per-routine model pin** so cheap checks do not use the premium model.

### Avoid or improve

1. **No budget for autonomous runs.** Add per-agent and per-day token/cost ceilings, a global "autonomy kill switch" (pause all agent schedules and watches, keep the broker kill switch separate), and a per-run step/tool-call cap for scheduled runs. Rakazo relies on counts and provider backoff only.
2. **Notification policy lives in a prompt.** Add server-side quiet hours, per-severity delivery (push vs in-app vs digest), and a rate limit for pushes per agent. Rakazo's only knobs are per-chat snooze, `notifyOnFinish` and per-routine `notify`.
3. **Polling-only monitors.** The 5 min floor is wrong for price and risk events. MT5 gives you a live connection, so make broker events (fills, margin level, disconnects) **push triggers** into the same wake path rather than watches. Keep the watch checker for slow sources (news, calendar).
4. **Webhook creates no run if no routine matches** (good), but an inbound payload that mixes owner and outside text relies on string-prefix matching. Prefer storing the owner's instructions and the payload in separate structured fields instead of re-parsing the task prompt.
5. **Cron-only scheduling** in the user's timezone does not know market sessions. Add schedule kinds like "at London open", "every N minutes during the session", and "skip when the market is closed or on a holiday", computed server-side.
6. **Heartbeat naming confusion.** If Lonora adds a periodic "heartbeat" agent turn, make it a real routine row with a visible schedule, not a hidden loop. Rakazo's only always-on logic is infrastructure, which is a good property to keep (nothing proactive is invisible).
7. **Edit-race handling** (`CONFLICT "Routine changed; retry."`) is good. Do not copy the very large single `update` handler (about 300 lines); split by concern.
8. **Do not let a watch run arbitrary shell without approval** in a trading context. Rakazo allows it because the owner wrote it. For Lonora, restrict watches to read-only broker and market tools.
9. **Owner-approved computer access via prompt hash** is clever (a DB trigger clears it on edit) but has no equivalent need in Lonora. Adapt the idea to "trading authority granted for this exact prompt", so editing an agent's standing instruction revokes its autonomous authority until re-approved.

## 13. Where to start reading (shortest path)

1. `packages/adapters/src/runs/assembly/run-routines.ts` (`wakeRoutine`).
2. `packages/adapters/src/routines/routine-watch.ts` (`tickRoutineWatch`).
3. `apps/api/src/webhooks/webhook.ts` and `webhook-inbound.ts`.
4. `packages/adapters/src/runs/assembly/silent-reply.ts` and `run-replies.prompt.ts`.
5. `packages/adapters/src/runs/lifecycle/run-notifications.ts`.
6. `packages/adapters/src/runs/wakeups/job-reconciler.ts`.
