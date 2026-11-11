# rakazo: agent loop, tool errors and recovery

Source: `/home/user/elie222/rakazo` at commit `cd7e20e5da754d8d8deaf2780671ed34a38e2241`. All paths are relative to that repo root. "(implemented)" = I read the code at the cited lines. "(stated)" = only docs/README say so. `node_modules` is not installed in the checkout, so nothing inside the Pi packages themselves was read; every statement about Pi's internal behaviour is taken from rakazo's own code or comments and is marked as such.

---

## 1. What runs the agent

**An existing harness, not a hand-written loop.** The model/tool loop is the `Agent` class from the Pi packages. (implemented)

- Dependencies, pinned exactly: `@earendil-works/pi-agent-core` 1.5.0, `@earendil-works/pi-ai` 1.5.0, `@earendil-works/pi-telemetry` 1.5.0 — `packages/adapters/package.json:36-38`. README lists "Pi" in the stack (`README.md:385`) (stated).
- `PiAgentRuntime` imports `Agent` from pi-agent-core and constructs one per run: `packages/adapters/src/pi-runtime.ts:2`, `packages/adapters/src/pi-runtime.ts:614-706`.
- It is the default runtime in both processes; the only alternative is a scripted test runtime selected with `AGENT_RUNTIME=scripted`: `apps/worker/src/index.ts:136-139`, `apps/api/src/app.ts:462-465` (the API reads it as `env.agentRuntime`, set from `AGENT_RUNTIME` with default `"pi"` at `apps/api/src/env.ts:289`).
- A code comment mentions "Pi 0.85.1" (`packages/adapters/src/pi-runtime-stream.ts:303-304`) while package.json pins 1.5.0. The comment looks stale; unsure.

**What rakazo wraps around Pi** (all implemented):

| Layer | What it does | Where |
|---|---|---|
| Event queue | Pi events are converted into rakazo `AgentRuntimeEvent`s (`text`, `progress`, `tool`, `thinking`, `turn`, `steered`, `ask`, `takeover`, `subagent`, `usage`, `checkpoint`, `done`) and pushed onto an in-memory async queue | event type `packages/adapter-kit/src/types.ts:707-763`; queue `packages/adapters/src/pi-runtime-tools.ts:975-1008`; conversion `packages/adapters/src/pi-runtime.ts:806-979` |
| Model stream wrapper | `fallbackAwareModelStream` (retries, backup-model switch, output-limit recovery, cut-reply continuation) around `reliableModelStream` (timeouts, idle watchdog) | `packages/adapters/src/pi-runtime.ts:617-622`, `packages/adapters/src/pi-runtime-fallback.ts:303-861`, `packages/adapters/src/pi-runtime-stream.ts:208-247` |
| Tool adapter | Every rakazo tool becomes a Pi `AgentTool` whose `execute` calls back into the executor (`request.executeTool` → `applyTool`), with argument normalisation, checkpoint capture, budget, result clipping and audit hook | `packages/adapters/src/pi-runtime-tools.ts:362-713`, `packages/adapters/src/executor.ts:1916-1919` |
| "Final answer" enforcement | Own bookkeeping on Pi's `turn_end`/`message_end` to decide whether the model actually answered after tools | `packages/adapters/src/pi-runtime.ts:879-919`, `packages/adapters/src/pi-runtime.ts:1208-1249` |
| Steering | `prepareNextTurnWithContext` hook claims queued user messages before each model request | `packages/adapters/src/pi-runtime.ts:643-696` |
| Pause/resume | Turn checkpoint captured before each tool call; resumed turns replay unresolved calls | `packages/adapters/src/pi-runtime.ts:712-766`, `packages/adapters/src/pi-runtime.ts:988-1112` |
| Transcript guard | Drops tool calls with an empty name (some gateways emit them) before sending the transcript | `packages/adapters/src/pi-tool-call-guard.ts:3-8`, `packages/adapters/src/pi-tool-call-guard.ts:26-60` |
| Durable run executor | Postgres-backed run row with lease + fence, heartbeat, attempts, finalisation, notifications | `packages/adapters/src/executor.ts:290-2025`, `packages/adapters/src/run-lifecycle.ts:378-444` |
| Optional session recording | Pi JSONL transcripts, opt-in via `PI_SESSION_RECORDING=true`, 30 days / 100 files per bot | `packages/adapters/src/pi-session.ts:9-10`, `packages/adapters/src/pi-session.ts:32-42`; gated in both processes (`apps/worker/src/index.ts:139`, `apps/api/src/app.ts:465`) |

---

## 2. One turn, end to end

1. **Inbound message → run row.** `sendUserMessage` writes the message, then in the same transaction looks for an active run of that bot in that thread (statuses in `QUEUE_HOLDING_RUN_STATUSES`). No busy run → creates `task` + `run` with status `queued`. Busy run → creates a `steeringMessage` row instead (see §7). `packages/db/src/events.ts:424-443`, `packages/db/src/events.ts:468-525`. (implemented)
2. **Dispatch.** The run starts in the same process that made it due, as an independent task (`RunStarter.start` → `begin` → `run.continue` job handler); no queue in between. `packages/adapters/src/run-wakeup.ts:49-63`, `packages/adapters/src/run-wakeup.ts:92-126`; doc: `docs/run-execution.md:3-10`. Admission is limited only by memory headroom, not by a run count: `packages/adapters/src/run-execution.ts:78-109`.
3. **Claim.** `claimRun` atomically moves the run to `leased` with `leaseFence+1` and a 5-minute lease, then to `running`. `packages/adapters/src/run-lifecycle.ts:378-444`.
4. **Computer lease, attempt row, heartbeat.** The run takes an execution lease on the bot's computer (background helper runs skip this); a busy computer requeues the run. An `attempt` row is created. A 60-second heartbeat renews run and computer leases; a failed renewal aborts the run. `packages/adapters/src/executor.ts:362-404`, `packages/adapters/src/executor.ts:435-437`, `packages/adapters/src/executor.ts:461-479`, `packages/adapters/src/run-lifecycle.ts:149-165`.
5. **Setup.** Model resolution, tools, history, memory, prompt assembly (several hundred lines I did not read in full; `packages/adapters/src/executor.ts:488-1740`). A setup error goes to `retryRunSetup` (§4).
6. **Runtime call.** `deps.runtime.run({...})` with prompt, instructions, history, tools, model, fallback models, and callbacks `executeTool`, `onToolCompleted`, `claimSteering`, `onCheckpoint`. `packages/adapters/src/executor.ts:1741-1973`.
7. **Inside `PiAgentRuntime`.** Builds history, creates the `Agent`, subscribes to events, then `agent.prompt(...)` (or `agent.continue()` for a resumed turn) and `agent.waitForIdle()`. `packages/adapters/src/pi-runtime.ts:333-339`, `packages/adapters/src/pi-runtime.ts:614`, `packages/adapters/src/pi-runtime.ts:806`, `packages/adapters/src/pi-runtime.ts:1111-1134`. After idle it decides the ending (§4) and pushes `done`. `packages/adapters/src/pi-runtime.ts:1141-1249`.
8. **Event consumption.** `consumeRunEvents` iterates the queue: streams text, shows tool steps, runs the loop guard, pauses on `ask`/`takeover`. It returns `true` when the attempt stopped before the turn ended. `packages/adapters/src/run-turn.ts:127-247`.
9. **Completion.** `completeRun` assembles the final blocks, redacts secrets, and calls `finalizeRun(outcome: "completed")`, which in one transaction sets run/attempt/task status, writes the bot message, appends `run.completed`, deletes transient progress events, and creates a continuation run if steering is still pending. `packages/adapters/src/run-turn.ts:766-1000`, `packages/db/src/events.ts:719-865`.
10. **Failure.** A throw from steps 6–9 normally goes to `failRun` → `finalizeRun(outcome: "failed", error, partialReply)`. Exceptions visible at the cited lines: a shutdown in progress returns without finalising (the run is requeued, §4 row 17), and a turn ended by a handoff is completed instead of failed. `packages/adapters/src/executor.ts:1977-1992`, `packages/adapters/src/run-turn.ts:1012-1150`.
11. **Always.** `finishRunAttempt` releases the computer lease, starts the bot's next waiting run, marks a still-`running` attempt `interrupted`. `packages/adapters/src/run-lifecycle.ts:538-594`.

`apps/api/src/runs.ts` is only the activity list (active/recent runs for the sidebar); it has no part in execution. `apps/api/src/runs.ts:68-120`.

`packages/adapters/src/run-execution.ts` is only the memory-admission host (`RunExecutionHost`); the turn logic is in `executor.ts` and `run-turn.ts`. `packages/adapters/src/run-execution.ts:54-136`.

---

## 3. Limits

**Things that are NOT limited in rakazo's own code** (I found no constant for them):

- **No max step / iteration count per turn.** The only tool-count fuse is optional and off by default: `MAX_TOOL_CALLS_PER_TURN`, "Unset, empty, or 0 means unlimited (default)". `packages/adapters/src/pi-runtime-tools.ts:64-71`. Whether Pi 1.5.0 has its own step cap: unsure (package not readable).
- **No wall-clock limit per run.** The lease is renewed every 60 s for as long as the process lives (`packages/adapters/src/executor.ts:461-479`). Docs: "Active model streams have no new duration limit." (`docs/run-execution.md:103`) (stated; consistent with code read).

**Model call limits** (`packages/adapters/src/pi-runtime-limits.ts`):

| Limit | Value | Line |
|---|---|---|
| Wait for response headers, per attempt | 120 000 ms (`MODEL_STREAM_TIMEOUT_MS`) | `:6` |
| Connection establishment | 30 000 ms | `:8` |
| Stream silence after headers (idle watchdog) | 180 000 ms | `:14` |
| SDK retries per call | 1 (env 0–5) | `:15`, `:26-30` |
| Default output cap, non-reasoning model | 4 096 tokens (`DEFAULT_MODEL_MAX_TOKENS`) | `packages/contracts/src/model-connections.ts:7`, used at `:182` |
| Default output cap, reasoning model | 32 768 tokens | `:139` |
| Output reserve never more than | 1/4 of the context window | `:142-144` |

**Same-model retry / backup switch** (`packages/adapters/src/pi-runtime-fallback.ts`):

- Retry delays for transient provider errors on the same model: 2 s, 8 s, 20 s, all inside the per-call window `timeoutMs` (default = the 120 s header timeout, `:452`) (`:61`, `:662-686`). This branch is only reached when the failed call had produced no visible output yet and no backup model could take over (`:633-659`). An idle-timeout gets exactly one renewal of that window (`:664-675`).
- With backup models configured, the SDK's own retry is set to 0 and the next backup is tried instead (`:511-513`, `:647-659`). Backups are skipped with a recorded reason if they have no credential, cannot fit the context, cannot see required images, etc. (`:373-426`, `:238-301`).
- `MAX_SELF_RECOVERIES_PER_RUN = 3`: shared budget for "repeat the call with more output room", "lower the thinking level", and "continue a cut reply" (`:134`, `:192-216`, `:743-765`, `:806-824`).

**Tool-side limits:**

- Tool result text given to the model: 12 000 characters shared across all text parts of one result (`TOOL_RESULT_TEXT_LIMIT`). `packages/adapters/src/pi-runtime-limits.ts:69-107`. `skill_read` and `list_fleet` are exempt (`packages/adapters/src/runtime-context.ts:35`), as are MCP servers the user marked "keep whole" (`packages/adapters/src/pi-runtime-tools.ts:504-506`).
- Shell command timeout: default 5 minutes, max 60 minutes via `SANDBOX_COMMAND_TIMEOUT_MS`. `packages/core/src/sandbox-command.ts:1-9`, used at `packages/adapters/src/run-tools-computer.ts:468`.
- `computer_act` / `browser_act`: at most 24 actions per call (`packages/adapters/src/tool-loop.ts:49`).
- In-turn subagents: at most 4 in parallel, no nesting (`packages/adapters/src/pi-runtime-subagent.ts:32`, `:53`).
- Silent-turn nudges: at most 3 (`MAX_SILENT_TOOL_CONTINUATIONS`, `packages/adapters/src/pi-runtime.ts:114`).

**Loop / repeat detection** (executor side, `packages/adapters/src/tool-loop.ts` + `packages/adapters/src/run-turn.ts:550-583`):

- Same tool + identical arguments, **and the result keeps failing**: stop on the 6th call (5 failures in a row). `tool-loop.ts:37-38`, `:141-150`.
- Same tool + arguments that differ only by digits ("shape"), or identical calls that keep succeeding: stop at 25 in a row. `tool-loop.ts:39-42`, `:148-150`; shape definition `packages/core/src/events.ts:467-488`.
- An identical call whose last answer is *new* resets the count (it is treated as polling). `tool-loop.ts:132-137`.
- Any model text resets the streak (`packages/adapters/src/run-turn.ts:300`); calls from the same model response count as one step (`tool-loop.ts:130-131`).
- 4 consecutive over-limit action batches also stop the run (`tool-loop.ts:45-47`, `packages/adapters/src/run-turn.ts:571-583`).
- Result fingerprint = sha256 of what the model saw, prefixed `failed:` for failures (`tool-loop.ts:91-109`).

---

## 4. Every way a turn ends, what the user sees, what happens next

Run statuses and legal transitions: `packages/core/src/run-state.ts:50-59`.

| # | Ending | Trigger | What the user sees | What happens next | Where |
|---|---|---|---|---|---|
| 1 | Normal completion | Model writes text with no tool call after its last tool results | Final bot message; push "‹Bot› finished" only when the trigger sends finish notifications, the reply marks the chat unread, there is preview text and no continuation run (`:960-965`) | Continuation run if steering pending | `packages/adapters/src/run-turn.ts:919-974` |
| 2 | Tools ran, model ended with no text | Pi turn ends after tool results with empty assistant message | Nothing yet | Up to 3 automatic follow-up user-role prompts (text in §8). If still empty: run **fails** with `MISSING_TOOL_FINAL_RESPONSE_ERROR` (see string below). Runs with `allowSilentEmpty` (trigger `reaction`, `routine`, background `tickets`, plus messaging-channel runs and some bot-to-bot messages) may end silently instead | `packages/adapters/src/pi-runtime.ts:902-917`, `:1228-1234`; `packages/core/src/run-error.ts:11-12`; `packages/adapters/src/executor.ts:822-823`; `packages/adapters/src/run-replies.ts:24-26`; `packages/core/src/run-state.ts:43` |
| 3 | Empty reply, no tools | Model returns nothing at all, no tool was called, and the run is not `allowSilentEmpty` | The literal text "No response. Try again." (or a per-run `emptyResponseText`) as a normal bot message; run is `completed` | Nothing | `packages/adapters/src/pi-runtime.ts:1244-1247` |
| 4 | Provider error after retries/backups | Stream error not recovered in §3 | Text already streamed is kept as a partial reply above the error for runs whose trigger promotes mid-turn narration (not scripted, not handed off, not an explicit no-response, and only if it contains no secret; `run-turn.ts:1044-1057`); run `failed`; the web client passes the stored error through `normalizeRunError` in the composer area; push "‹Bot› failed" with the error text unless a continuation run or a routine retry follows (`run-turn.ts:1134-1141`) | No automatic retry for chat runs. Routine runs stopped by a *transient* error before any tool call/message get one retry after 12 minutes | `packages/adapters/src/pi-runtime.ts:1146-1182`, `packages/adapters/src/run-turn.ts:1040-1071`, `:1134-1148`; `packages/adapters/src/run-routines.ts:33`, `:52-74`; `apps/web/src/pages/shell/composer-error.tsx:119-121` |
| 5 | Output limit, nothing visible written | `stopReason: "length"` with no text/tool call | Nothing unless recovery fails | One repeat with doubled output budget or one thinking level lower; if that fails: "The model hit its output limit before writing a response." | `packages/adapters/src/pi-runtime-fallback.ts:806-824`, `packages/adapters/src/pi-runtime-errors.ts:61-63`, `packages/core/src/run-error.ts:18` |
| 6 | Output limit mid-reply | `length` stop with text | Reply continues in the same bubble | Automated "continue" prompt quoting the last words; overlap is de-duplicated; after 3 recoveries fails with "The model hit its output limit before finishing its reply." | `packages/adapters/src/pi-runtime-fallback.ts:766-805`, `packages/adapters/src/pi-runtime.ts:129-138`, `:949-977`, `packages/core/src/run-error.ts:21` |
| 7 | Connection dropped mid-reply | Transient error after visible text, no tool call in that message | Reply continues in the same bubble | Automated prompt "Your previous reply was cut off by a connection error…" | `packages/adapters/src/pi-runtime-fallback.ts:690-721`, `packages/adapters/src/pi-runtime.ts:121-123` |
| 8 | Loop guard | §3 repeat detection | Steps so far are published with outcome "stopped", then a bot message (string below; background-trigger runs get no text, `:649`). Run is marked **`completed`**, not failed | Model stream aborted; continuation run if steering pending | `packages/adapters/src/run-turn.ts:616-686` |
| 9 | Optional tool-call budget | `MAX_TOOL_CALLS_PER_TURN` exceeded (off by default) | Progress line "Stopped: more than N tool calls in one turn." then reply text "I stopped after reaching the limit of N tool calls in this turn. Send another message to continue." Run `completed` | Further calls return "Skipped: tool-call limit reached." | `packages/adapters/src/pi-runtime-tools.ts:519-524`, `:825-827`, `:940-946`; `packages/adapters/src/pi-runtime.ts:1208-1217` |
| 10 | `ask_user` | Model calls the tool (2–4 options required) | Ask card with buttons; push "‹Bot› needs an answer"; status `waiting_input` | Turn checkpoint saved; answering resumes the same turn with the answer as that tool call's result (`packages/adapters/src/pi-runtime.ts:1040-1047`). Reminder push after 4 h, auto-cancel after 24 h with "Stopped. This was still waiting for an answer." | `packages/adapters/src/pi-runtime-tools.ts:551-581`, `packages/adapters/src/run-turn.ts:398-445`, `packages/core/src/stuck-work.ts:5-13`, `:64-73` |
| 11 | Approval pending | Tool gate returns a pause result | Approval card (not read in detail) | Same pause/checkpoint path; approved call is executed on resume before any new model request | `packages/adapters/src/pi-runtime-tools.ts:643-648`, `packages/adapters/src/pi-runtime.ts:988-1084`; gate itself `packages/adapters/src/run-tool-gate.ts` (only grepped) |
| 12 | `request_takeover` | Model asks the human to use the screen | Computer card + push "‹Bot› needs you on the screen"; status `waiting_takeover` | Auto-cancel after 30 minutes (it holds the bot's computer) | `packages/adapters/src/run-turn.ts:447-510`, `packages/core/src/stuck-work.ts:11-13` |
| 13 | Tool ends the turn itself | A tool returns a "terminating reply" result | That reply text becomes the final answer; no further model call | — | `packages/adapters/src/pi-runtime.ts:807-809`, `:1218-1227`; `packages/adapters/src/pi-runtime-tools.ts:681-684` |
| 14 | User stop | Stop request → `cancelThreadRuns` sets status `cancelled`, deletes pending steering | `run.cancelled` event per cancelled run in the thread. The system note "Stopped. Anything already done stays done." is written only when the caller passes a `note` (the constant is named `STOPPED_BY_MESSAGE_NOTE`, i.e. Stop sent as a chat message); `stopThreadRuns` passes none (`:48-50`, `:167-172`). A stopped routine gets its own note `Stopped the routine "‹name›".` (`:33-35`, `:157-166`) | The worker notices within ~1 s (a 1 s lease-watch timer reads the run row) and aborts the model and tools | `apps/api/src/thread-stop.ts:31`, `:76-83`, `:98-105`, `:145-152`, `:167-172`; `packages/adapters/src/run-turn.ts:157-164`, `:253-267` |
| 15 | Setup failure (before the model is called) | Throw in step 5 of §2 | Nothing while retrying (run goes back to `queued` with error "Run setup failed; retrying") | Retried with backoff (`min(10 s, 250 ms × 2^min(fence−1, 5))`, so 250 ms doubling to 8 s; the 10 s cap is never reached. Provider outages: 15 s doubling, capped at 5 min). After 8 consecutive setup failures the run fails and the failure push is sent (not for background helpers, and not when a continuation run was created). Busy computer / DB pool exhaustion retry forever | `packages/adapters/src/run-lifecycle.ts:167-168`, `:199-209`, `:450-535`, `:80-136` |
| 16 | Worker crash / lost lease | Process dies; lease (5 min) expires | Nothing immediately | Recovery scan every 5 s in each worker picks up `leased`/`running` rows with expired leases and re-claims them under a new fence. The turn restarts from the beginning (turn checkpoints exist only for human waits). A tool call that is tracked as an external effect and whose record is still in status `executing` is treated as uncertain and gets an "outcome is unknown" error instead of re-running (string in §8). Which tools are tracked this way was not traced (unverified) | `packages/adapters/src/run-wakeup.ts:218`, `:371-375`; `packages/adapters/src/run-lifecycle.ts:401-406`; `docs/agent-verification.md:49-50` (stated); `packages/adapters/src/approval-effect.ts:448-450`, `:473-486` |
| 17 | Graceful shutdown / deploy | `shutdownSignal` aborted | Nothing | Run is requeued (`queued`, no failure recorded) and another process takes it | `packages/adapters/src/run-lifecycle.ts:315-341`, `:580-586`; `packages/adapters/src/executor.ts:1731-1737` |
| 18 | Queued and never started | Run sits `queued` | Reminder after 4 h, cancelled after 24 h with "Stopped. This stayed queued without starting." | — | `packages/core/src/stuck-work.ts:5-9`, `:64-73`; `packages/adapters/src/stuck-work.ts:54-134` |
| 19 | Unknown model id | Model cannot be resolved | Text "Unknown model ‹provider›/‹id›" followed by `done` from the runtime, so the executor would complete the run with that text (executor side not traced for this case) | — | `packages/adapters/src/pi-runtime.ts:254-262` |
| 20 | Model refusal | — | I found no handling of a refusal stop reason in the non-test files I grepped; refusal text would pass through as an ordinary reply. Unsure | — | — |

Key user-facing strings (verbatim):

- Loop guard (`packages/adapters/src/tool-loop.ts:7-10`, `:24-27`):
  > "I got stuck calling ‹Tool› with the same input 6 times in a row without making progress, so I stopped early. Try rephrasing this, or ask me to try a different approach."
- Missing final answer (`packages/core/src/run-error.ts:11-12`):
  > "The tools finished, but the model did not write a final answer. Rephrase the request and try again."

**How failure text is cleaned before the user sees it** (implemented):

- `userRunError` drops stack frames, replaces server file paths with `[path]`, and turns any database error into "Internal server error". `packages/core/src/run-error.ts:78-110`.
- `sanitizeSensitiveText` redacts API-key-like strings and bearer tokens. `packages/adapters/src/pi-runtime-errors.ts:68-80`.
- `normalizeRunError` maps recognised provider errors to one short translatable summary plus at most one recovery action ("connection" / "model" / "plan"), keeping the raw text under "details". Not every message is rewritten: one branch returns the raw text as the summary (`:298`). Default summary: "The model provider returned an error."; internal errors: "Something went wrong. Try again." `packages/core/src/run-error.ts:225-234`, `:300-302`, `:382`, `:540-548`.
- Client-side helper `userErrorMessage` replaces any message that matches a "technical" pattern (stack frames, JSON, `ECONNRESET`, HTTP status dumps, "is not a function"…) with the client's own fallback copy. `packages/core/src/user-error.ts:33-46`, `:100-114`.
- Model failures are classified into `TransientModelError` / `ModelOutputError` / `ModelAccountError` / plain `Error`. `failRun` logs those three classes and two sandbox errors (`SandboxRateLimitError`, `SandboxAllowanceUsedError`) as warnings; everything else is logged as an error. `packages/adapters/src/pi-runtime-errors.ts:107-147`, `packages/adapters/src/run-turn.ts:1073-1098`.

`packages/adapters/src/run-recovery.ts` is narrow: it only decides which recoverable runs are blocked by another run's computer lease, and expires abandoned takeover holds. `packages/adapters/src/run-recovery.ts:18-51`.

---

## 5. Tool execution

- **Parallel by default, per rakazo's comment about Pi**: "Pi runs a turn's tool calls concurrently by default… Pi runs the whole batch in order when any call in it is sequential." Rakazo marks schedule tools, `remember`, `request_secret`, the `use_tool` wrapper and a tool built in `pi-runtime-computer-mode.ts` (I read only its definition lines) as `executionMode: "sequential"`. `packages/adapters/src/pi-runtime-tools.ts:372-381`, `:100-101`; `packages/adapters/src/pi-runtime-computer-mode.ts:122`. (Pi's actual default not verified.)
  - **Docs disagree**: `docs/agent-verification.md:48-49` says "Main tool batches execute sequentially so a pause captures completed preceding calls." The code instead keeps completed parallel siblings in a side map so a pause can include them (`packages/adapters/src/pi-runtime.ts:709-711`, `:806-820`) and records `executionMode: "parallel" | "sequential"` in the checkpoint (`:721-745`).
- **Order of work inside one call** (`packages/adapters/src/pi-runtime-tools.ts:489-711`): abort check → computer-mode check → skip if a pause is pending → capture turn checkpoint → budget check → push `tool` event → run → clip result → in `finally`: abort the turn if a pause/terminating result happened, report completion to the executor (`onToolCompleted`, best effort).
- **Executor side** (`packages/adapters/src/run-tools.ts:68-193`): a chain of refusals (daily check-in restriction, handed off, tool disabled, helper not allowed, page browser unavailable, model cannot see images, argument resolution, connector name conflict, request preparation, approval gate), then the tool-family handler. Refusals are returned as `{ error: "…" }` objects tagged with a log-only code (`packages/adapters/src/tool-refusal.ts:1-19`).
- **Timeouts**: there is no generic per-tool timeout wrapper in the Pi adapter; each tool family has its own (shell 5 min default, §3). A shell command whose output goes quiet for 10 s (1 s if it shows a sign-in link plus one-time code) is returned to the model while still running, with notice "Still running. Tell the user any one-time code or sign-in URL in the output."; its final output is injected later as a user-role message before the next model request. `packages/adapters/src/shell-command-stream.ts:14`, `:20`, `:44-45`, `:186-187`, `:230-232`; `packages/adapters/src/pi-runtime.ts:627-642`. (I confirmed the two timers and the notice constant; the code that attaches the notice to the returned result was not opened.)
- **Truncation**: results over 12 000 chars are either hard-clipped with "…" (context strategy `current`) or shortened by `shortenToolResultText` (default strategy `retrieval`, `packages/adapter-kit/src/types.ts:552`), which tries history-, MCP-envelope- and structured-JSON-aware shortening first and falls back to head+tail of plain text around a marker. Markers the model sees: "[Tool result truncated to fit context; omitted evidence is unavailable.]" / "[Tool result truncated to fit context; inspect original evidence before claiming omitted details.]" / "[Earlier result shortened after you read it; statements made from it stand. Re-run the tool only if you need the omitted text.]". `packages/adapters/src/pi-runtime-tools.ts:739-762`, `packages/adapters/src/context-selection.ts:264-269`, `:489-514`.
- **Deferred tools**: tools not listed up front are reached through `find_tool` / `use_tool`; an unknown name throws "‹name› is not available. Use a name find_tool lists." `packages/adapters/src/pi-runtime-tools.ts:73-125`.

---

## 6. Streaming to clients

- Runtime → executor: the in-memory queue (§1). Text deltas are pushed as they arrive; text in a turn that also has a tool call is treated as narration, and only text after the last tool results counts as the final reply. `packages/adapters/src/pi-runtime.ts:855-878`, `:885-890`.
- Executor → clients: text deltas are redacted for secrets and appended as `thread.progress` events, throttled to one flush per 250 ms; the first flush replaces the "working…" placeholder. `packages/adapters/src/run-turn.ts:284-307`, `packages/adapters/src/run-progress.ts:222-250`.
- Tool activity: on each tool start the runtime emits one human-readable line (`describeToolActivity`) — e.g. "Searching the web: ‹query›", "Reading ‹path›", "Running: ‹command›", fallback "Using ‹toolName›" — clipped to 90 chars, URLs stripped of query/userinfo. `packages/adapters/src/pi-runtime.ts:828-843`, `packages/adapters/src/pi-runtime-tools.ts:189`, `:214-282`, `:773-787`.
- Thinking indicator: `thread.meta` events `{ activity: { thinking: true|false } }`. `packages/adapters/src/run-turn.ts:134-153`.
- Routine and background runs publish no text or progress events (the thinking indicator is skipped only for background and scripted runs, `run-turn.ts:137`). `packages/adapters/src/run-turn.ts:314`, `packages/adapters/src/run-progress.ts:227-234`.
- Durable interim chat messages (promoted narration + `message_user`) are capped: max 3 per run, only once the turn is at least 60 s old; promoted narration is capped at 500 chars, `message_user` at 500 by default or `RAKAZO_MESSAGE_USER_MAX_CHARS`. `packages/adapters/src/user-progress.ts:8`, `:11`, `:55`, `:62-66`, `:73-82`.
- Transient progress events are deleted when the run is finalised. `packages/db/src/events.ts:844-846`.
- Clients follow via realtime notifications keyed by thread and event sequence (`packages/adapters/src/run-messages.ts:109-114`); the HTTP send returns immediately (`docs/run-execution.md:5-6`, stated). I did not read the realtime transport.
- `packages/adapters/src/runtime-stream.ts` is just a wrapper that aborts executor tool work before closing an interrupted event iterator. `packages/adapters/src/runtime-stream.ts:4-27`.

---

## 7. Steering: a new user message during a run

It is **injected into the running turn at the next model-request boundary**; it does not interrupt the current model call or tool, and it does not start a second run. (implemented)

1. API: while a run is active, the new message becomes a `steeringMessage` row attached to that run (`runId: busy.id`), or held with `runId: null` if it cannot steer that run. `packages/db/src/events.ts:503-525`.
2. Who can steer: only the run's own user; never a webhook; never into routine / webhook / creation-intro / ticket / bot-to-bot runs (those messages wait for a follow-up run); a connected-chat (`messaging`) message steers only a run started from the same channel. `packages/core/src/run-state.ts:29-35`, `:151-162`; `packages/db/src/events.ts:449-456`.
3. Runtime: before every model request Pi calls `prepareNextTurnWithContext`; rakazo calls `claimSteering` (a DB transaction under the thread lock that marks rows claimed and appends a `run.steering.claimed` event) and returns the messages as extra user messages for the next request. Messages already waiting when the run starts are appended to the first prompt under "Additional user context:". `packages/adapters/src/pi-runtime.ts:319`, `:361-367`, `:643-696`; `packages/db/src/thread-steering.ts:34-164`.
4. Wording the model sees (`packages/adapters/src/user-progress.ts:29-34`):
   > "The person sent this while you were working:\n\n‹text›\n\nIf it asks something or changes the plan, answer briefly with message_user, then continue the task."

   The reason given in the comment: a plain-text answer would end the turn and the task with it (`packages/adapters/src/user-progress.ts:24-28`).
5. Executor: a `steered` event restarts the interim-message budget so the bot may answer at once — at most 3 times per run and at most once per 60 s. `packages/adapters/src/run-turn.ts:349-396`, `packages/adapters/src/user-progress.ts:51-52`.
6. After the run: on completion, claimed steering rows are deleted and unclaimed ones released; if any remain and no other run of the bot is active in the thread, a continuation run is created with the fixed prompt "Respond to the user's steering context." (a webhook-origin batch uses the message text as the prompt instead) On failure, steering that a reply already answered is discarded and newer steering is released for its own run. `packages/db/src/events.ts:792-809`, `:852-861`; `packages/db/src/thread-steering.ts:211-257`; `packages/core/src/run-state.ts:134`.
7. A user Stop deletes all pending steering for the thread. `apps/api/src/thread-stop.ts:98-105`.

Docs agree: "A message sent while a run is going steers that run instead of waiting." (`docs/run-execution.md:25-26`).

---

## 8. Tool errors: what the model sees, retries, and what pushes it to continue

### 8.1 Shape of a failed tool result

There are two shapes, and neither is rewritten into friendlier text for the model:

**(a) Returned error object (most common).** Handlers and refusals return `{ error: "…" }`. The Pi adapter serialises whatever the executor returned with `JSON.stringify` into one text part. So the model receives a normal tool result whose text is literally `{"error":"…"}`. `packages/adapters/src/pi-runtime-tools.ts:649-663`, `:739-748`; examples `packages/adapters/src/run-tools.ts:126-142`, `packages/adapters/src/run-tools-integrations.ts:64-66`, `:80`. A connector (MCP/Composio/…) failure is `{ error: event.message }` — the provider's own message, unmodified apart from what the connector layer did (`packages/adapters/src/run-tools-integrations.ts:64-66`). Whether Pi flags such a result as `isError`: rakazo's comment says no — "Tools can return an `error` or MCP `isError: true` instead of throwing. Pi keeps that result in `details` without populating `completion.error`… without changing the result that reaches the model and lets it react to the failure." `packages/adapters/src/tool-result-error.ts:7-11`.

**(b) Thrown error.** Some paths throw (shell failures re-throw at `packages/adapters/src/run-tools-computer.ts:522`; argument validation, e.g. `packages/adapters/src/pi-runtime-tools.ts:561`; unknown deferred tool `:113`). The adapter re-throws to Pi (`:677-679`). How Pi 1.5.0 turns a thrown error into a tool result is **not verified** (package not in the checkout). The only in-repo evidence of the intended shape is rakazo's own replay path, which builds `content: [{type:"text", text: sanitizeError(error.message)}], isError: true` (`packages/adapters/src/pi-runtime.ts:1048-1059`).

In both cases the run does **not** fail: the error goes back to the model as a tool result and the loop continues. A tool error only ends a run through the loop guard (§3) or when the tool deliberately returns a terminating reply.

### 8.2 Retries and fallbacks at the tool level

- **No automatic retry of a failed tool call** in the files I read. Retrying is left to the model.
- **Deliberate non-retry for tracked effects.** If the stored effect record of a call is still `executing` (an earlier execution was interrupted), or its result could not be stored, the model gets one of three variants; the default one is (`packages/adapters/src/approval-effect.ts:448-450`, `:473-486`; `packages/adapters/src/run-tool-gate.ts:738-739`; also used for unresolved parallel siblings on resume, `packages/adapters/src/pi-runtime.ts:1004-1016`):
  > "The earlier ‹tool› execution was interrupted, so its outcome is unknown. It was not replayed to avoid a duplicate side effect. Verify the destination before proposing another action."
- **Denied approval** (`packages/adapters/src/approval-effect.ts:417-418`):
  > "The user denied this action. Do not retry or rephrase it; tell the user and ask what they want instead."
- **A prompt rule limits model-side retries to one.** When the `task_catalog` tool is offered (`packages/adapters/src/executor.ts:1339-1341`), the instructions include (`packages/adapters/src/task-catalog.ts:29`):
  > "If a tool returns an error, do not repeat the same tool call with the same arguments. Correct the specific field once as a separate attempt; if that attempt fails, stop and explain the blocker instead of narrating more retries. A different command is not a retry."

  This pushes toward stopping and reporting after one corrected attempt, i.e. the opposite of "keep trying other ways". How often `task_catalog` is offered was not traced.
- Model-level fallbacks (backup models, retries) are in §3; they concern model calls, not tools.

### 8.3 Mechanisms that keep the bot working instead of stopping

1. **Silent-turn nudge** — the main anti-"stopped early" mechanism. If the model ends a turn right after tool results without text, rakazo injects up to 3 follow-ups in the user role, labelled as automated (`packages/adapters/src/pi-runtime.ts:111-119`, `:902-917`):
   > "Your last turn ended right after a tool result, without a reply. Continue the original task from the latest tool result. If you need information or a decision from the user, ask them instead of guessing; otherwise use any remaining tools needed, then give the user the final answer."

   The comment explains why it is marked automated: "otherwise models read it as the user telling them never to stop, and keep going instead of asking." (`:115-116`).
2. **Narration is not an answer.** Text in the same turn as a tool call never counts as the final reply; the run stays open until a text-only turn (`packages/adapters/src/pi-runtime.ts:885-890`). If none arrives, the run fails rather than pretending success (`:1228-1234`; rationale at `:143-145`).
3. **Error strings that name the next step.** Many tool errors are written as instructions to the model, in both directions:
   - continue differently: "computer_act accepts at most 24 actions but got N; none ran. Send the first 24 or fewer now, then the rest in a separate call." (`packages/adapters/src/computer-tools.ts:32-35`); "‹name› is not available. Use a name find_tool lists." (`packages/adapters/src/pi-runtime-tools.ts:113`); "This service is unavailable right now. Try another one." (`packages/adapters/src/paid-service-tools.ts:99`); "Redacted history exceeds the response budget. Retry with limit 1 or a narrower linked run." (`packages/adapters/src/run-tools-memory.ts:78`).
   - stop and report: "…Don't retry; tell the user." (`packages/adapters/src/run-tool-gate.ts:387`, `:400`; `packages/adapters/src/spending-gate.ts:14-15`); "Don't try it another way; tell the user it's blocked." (`packages/adapters/src/run-tool-gate.ts:399`).
4. **Prompt lines against premature refusal** (the few I found):
   - "A website with no connected app is still yours to use in the computer's browser, now and in scheduled routines, so a missing connection alone is never a reason to decline." (`packages/adapters/src/executor.ts:1385`)
   - Page tools: "If an action fails, inspect the current state before continuing; do not replay completed or uncertain actions. When page tools cannot operate, use desktop tools if available" (`packages/adapters/src/run-instructions.ts:189`)
   - Shell: "If `python` is not found, retry with `python3`. A command-syntax refusal is not a filesystem permission error; continue ordinary file work with supported tools." (`packages/adapters/src/run-instructions.ts:144`)
   - History search: "search before saying something did not happen… If a search is empty, try the single project or topic word before concluding the evidence is missing." (`packages/adapters/src/run-instructions.ts:360`)
   - Page content is not a stop command: "…continue executing until the user's objective is completed." (`packages/adapters/src/run-instructions.ts:25`)
5. **Loop guard as the backstop** so persistence cannot become an endless loop (§3, §4 row 8).

**What I did not find:** a general instruction of the form "when a tool fails, try another approach before telling the user you can't". I grepped `packages/adapters/src`, `packages/core/src` and `packages/contracts/src` (non-test) for phrases such as "give up", "try another", "try a different", "before concluding", "never a reason", "instead of giving up"; the hits are the ones listed above. The checker repeated a wider grep and found one general tool-error rule the first pass missed: `TASK_CATALOG_GUIDANCE` (`packages/adapters/src/task-catalog.ts:29`, quoted in §8.2), which tells the model to correct once and then stop and explain, not to try alternatives. `run-instructions.ts` was not read end to end, so a differently worded line could still exist. Rakazo's recovery from a tool failure therefore rests on: the raw error reaching the model, error strings that carry a next step, tool-specific prompt lines, and the model's own persistence.

### 8.4 Verification of "done" claims

- `docs/agent-verification.md` is about **test layers** (scripted tests, a loopback model emulator driving the real Pi loop, Docker browser replay, live evals), not about checking the agent's claims at run time. `docs/agent-verification.md:5-25`, `:58-69`. It states coverage includes "tool failures, rejected model requests, interrupted streams, cancellation of a quiet stream" (`:66-67`) (stated; test files not opened).
- At run time I found **no verifier that checks a "done" claim** against tool outcomes. The related runtime guards are narrower: the missing-final-answer failure (§4 row 2), the "outcome is unknown… Verify the destination" result (§8.2), tool-step outcomes recorded per call and shown on the steps block (`packages/adapters/src/executor.ts:1926-1949`), and the prompt lines in §8.3.4.
- One prompt line asks the model itself to verify, when `task_catalog` is offered: "For an open task, perform the work with the exposed tools, verify the result, then use scratchpad_update or scratchpad_complete. Never mark work done before verification." (`packages/adapters/src/task-catalog.ts:27`). This is an instruction, not a runtime check.
- `packages/adapters/src/run-auto-review.ts` and `auto-review*.ts` exist (approval auto-review, by name); not read, so unsure whether they touch this.

---

## Observations for Lonora (interpretation, not rakazo facts)

- The "symbol XAUUSD not found → give up" case maps to §8.3.3: rakazo's stronger tool errors tell the model the next action inside the error text itself. The equivalent would be a broker-tool error such as "Symbol XAUUSD not found. Call the symbol search with 'XAU' to find this broker's name for it, then retry." This is cheap and does not depend on a general prompt rule.
- The silent-turn nudge plus "narration is not an answer" (§8.3.1–2) addresses a different failure (stopping after a tool result without replying), not a model that explicitly says "I can't".
- For "exposes technical matters": rakazo's cleaning applies to **run failures** (`userRunError`, `normalizeRunError`, `isTechnicalErrorMessage`), i.e. what the product shows when the run breaks. It does not filter what the model itself writes in its reply, and it does show tool activity lines such as "Running: ‹command›" (see weaknesses).

---

## Weaknesses and risks seen in this area

1. **No step or time cap by default.** The tool-call fuse is opt-in and unset means unlimited (`packages/adapters/src/pi-runtime-tools.ts:64-71`); there is no run wall-clock limit (`docs/run-execution.md:103`). The only default stop is the loop guard, which needs 6 identical failing calls or 25 near-identical calls (`packages/adapters/src/tool-loop.ts:37-42`). A model that varies its arguments or writes a sentence between calls (text resets the streak, `packages/adapters/src/run-turn.ts:300`) can run and spend without bound.
2. **The optional tool budget is process-local.** "Optional fuse is process-local. continueRun on another worker starts at zero." (`packages/adapters/src/pi-runtime-tools.ts:55-56`).
3. **Loop-guard stop is recorded as `completed`.** The run that gave up is finalised with `outcome: "completed"` (`packages/adapters/src/run-turn.ts:639-650`), so status alone cannot distinguish success from "stuck". The message also pushes the work back to the user ("Try rephrasing this…", `packages/adapters/src/tool-loop.ts:9-10`) — the exact behaviour Lonora's owner complains about.
4. **Raw provider/connector error text reaches the model unshaped.** `{ error: event.message }` (`packages/adapters/src/run-tools-integrations.ts:64-66`) is serialised as JSON text (`packages/adapters/src/pi-runtime-tools.ts:747`). Nothing stops the model from repeating that technical text to the user; there is no filter on the model's own reply.
5. **Technical detail in live activity lines.** The activity line is "Running: ‹shell command›", "Reading ‹path›", "Using ‹server›: ‹tool›" or the fallback "Using ‹toolName›" (`packages/adapters/src/pi-runtime-tools.ts:233-240`, `:279-281`); a tool that defines a `label` shows that label instead (`:225`). Fine for developers, wrong for a non-technical owner.
6. **Hard-coded English user-facing strings in the runtime**: "No response. Try again." (`packages/adapters/src/pi-runtime.ts:1245`), the loop-guard text (`packages/adapters/src/tool-loop.ts:7-10`), the budget text (`packages/adapters/src/pi-runtime-tools.ts:825-827`), the stop note (`apps/api/src/thread-stop.ts:31`). These are stored as bot/system messages, not translated at display time like run errors are (`packages/core/src/run-error.ts:154-160`).
7. **"Missing final answer" fails the whole run after tools already ran.** After 3 nudges the run throws `MISSING_TOOL_FINAL_RESPONSE_ERROR` (`packages/adapters/src/pi-runtime.ts:1228-1234`) and the user is told to "Rephrase the request and try again." (`packages/core/src/run-error.ts:11-12`), although side effects may already have happened.
8. **A crash restarts the turn from scratch.** Checkpoints cover human waits only (`docs/agent-verification.md:49-50`, stated); a re-claimed run after lease expiry (`packages/adapters/src/run-lifecycle.ts:401-406`) repeats model calls, and interrupted side effects come back as "outcome is unknown" (`packages/adapters/src/approval-effect.ts:473-486`), which the model must then explain to the user. Lease expiry is 5 minutes from the last claim or 60-second renewal (`packages/adapters/src/run-lifecycle.ts:162`, `:413`), so a crashed run can sit silent for up to about that long before the 5-second scan re-claims it.
9. **Very large, intricate runtime file.** `pi-runtime.ts` is 1 284 lines and `executor.ts` 2 078 lines; the final-answer logic alone tracks `streamed`, `currentMessageStreamed`, `streamedBeforePendingFinal`, `joinCutReply`, `limitContinuation`, `joinDropped`, `toolWorkPendingFinal`, `terminatedReply` across several event handlers (`packages/adapters/src/pi-runtime.ts:779-805`, `:920-978`, `:1183-1248`). Much of it exists to work around provider quirks (e.g. `:111-113`, `:896-897`, `:1143-1145`). Not something to copy wholesale for a single-user bot with one or two models.
10. **Cut-reply stitching relies on string overlap heuristics** (4–240 chars, optional leading ellipsis) and on asking the model to repeat its last words (`packages/adapters/src/pi-runtime-fallback.ts:135-176`, `packages/adapters/src/pi-runtime.ts:129-138`). A wrong match silently drops or duplicates reply text.
11. **Injected user-role control messages.** Nudges, finished-shell output and steering are all sent in the user role (`packages/adapters/src/pi-runtime.ts:631-636`, `:910-916`, `:681-685`). Rakazo needs an "automated" label to stop models over-obeying them (`:115-116`); without that care the same trick causes the opposite problem.
12. **Low default output cap.** 4 096 output tokens for non-reasoning models (`packages/contracts/src/model-connections.ts:7`) makes the length-recovery machinery (§4 rows 5–6) run more often than it would with a higher cap; each recovery is an extra paid model call.
13. **Abort detection by message text.** `finishWithThrownError` gives any thrown error whose message matches `/abort|cancel/i` the stop reason `aborted` instead of `error` (`packages/adapters/src/pi-runtime-fallback.ts:331-335`); a thrown provider error that merely contains "cancel" would be labelled the same way. What the rest of the runtime then does with it was not traced (unverified).
14. **Docs drift.** `docs/agent-verification.md:48-49` says main tool batches execute sequentially; code runs them in parallel unless a tool is marked sequential (`packages/adapters/src/pi-runtime-tools.ts:372-381`). A stale "Pi 0.85.1" comment sits beside a 1.5.0 pin (`packages/adapters/src/pi-runtime-stream.ts:303-304`, `packages/adapters/package.json:36`).
15. **No general "try another way" rule and no runtime check of "done" claims** (§8.3, §8.4). The one general tool-error rule found says the opposite: correct once, then "stop and explain the blocker" (`packages/adapters/src/task-catalog.ts:29`). Rakazo is not a ready-made answer to Lonora's main complaint; its useful parts are the instructive error strings, the silent-turn nudge, and the failure-text cleaning.

---

## Not read / unsure

- **Pi internals** (`@earendil-works/pi-agent-core`, `pi-ai` 1.5.0): not installed in the checkout. Unverified: whether Pi has its own max-step limit; the exact tool-result shape Pi produces when a tool's `execute` throws; whether tool calls really run in parallel by default; semantics of `steeringMode: "all"`, `agent.steer` vs `agent.followUp`.
- `packages/adapters/src/executor.ts:525-1380` (model resolution, tool selection, history, memory, computer setup) — skimmed only by grep; `:1380-2025` read.
- `packages/adapters/src/run-tool-gate.ts` (980 lines, approvals/auto-approve), `run-tool-request.ts`, `run-context.ts`, `turn-checkpoint.ts`, `run-auto-review.ts`, `auto-review*.ts` — only grepped for specific strings. The approval card flow and its exact user-visible text are therefore not described.
- `packages/adapters/src/run-instructions.ts` — only grepped (lines 25, 144, 189, 360 opened), not read end to end; a general persistence instruction could exist in wording my grep missed.
- `packages/adapters/src/run-progress.ts` — only `flushProgress` read (`:222-250`).
- `packages/adapters/src/pi-runtime-subagent.ts` — only limits and error-return lines read.
- `packages/adapters/src/runtime-context.ts`, `context-selection.ts` (context budgeting, history compaction) — only the truncation markers and `shortenToolResultText` read.
- `packages/adapters/src/job-reconciler.ts` — only the default interval (30 s, `:20`) and the run query read; its relationship to the 5-second scan in `run-wakeup.ts:218` (which matches the docs) is not fully traced.
- Realtime transport, web/mobile rendering of progress, ask cards and step blocks — not read, except `apps/web/src/pages/shell/composer-error.tsx:119-121`.
- Model refusal handling: none found by grep for refusal/content-filter stop reasons in non-test `packages/adapters/src`; not confirmed against Pi's stop-reason list.
- Whether a failed chat run offers a "retry" action in the UI (the state machine allows `failed → queued`, `packages/core/src/run-state.ts:57`): not traced.
- Test files were not opened as evidence; statements that something "is tested" come from docs only.

---

## Verification log

Independent check of every `path:line` citation against the checkout at commit `cd7e20e5da754d8d8deaf2780671ed34a38e2241`. Each cited range was opened and compared with the sentence it supports. No test suite was run; no repository file was changed.

**Citations checked:** about 290 citation tokens (full paths plus `:line` shorthands) in the original text, covering 50 files. All pointed at the right file. One line range was off by two lines; the other corrections below are about what the cited code says, not where it is. Verbatim quotes (prompts, error strings, doc sentences) were compared character by character against the source lines and matched.

**Corrections made (before -> after):**

1. §1 event list: 11 event types -> 12; `checkpoint` was missing. Added the type definition citation `packages/adapter-kit/src/types.ts:707-763`.
2. §1 runtime selection: `apps/api/src/app.ts:464` -> `:462-465`, plus `apps/api/src/env.ts:289` for the `AGENT_RUNTIME` mapping (the cited line alone did not show the env variable).
3. §1 session recording: added the lines that actually gate it in both processes (`pi-session.ts:37-42`, `apps/worker/src/index.ts:139`, `apps/api/src/app.ts:465`).
4. §2 step 7: `pi-runtime.ts:1113-1134` -> `:1111-1134` (`agent.continue()` is on 1111); added `:614` and `:806` for "creates the Agent" and "subscribes".
5. §2 step 4: "One run per bot may hold the bot's computer" -> lease on the bot's computer, background helpers skip it (`executor.ts:364-365`).
6. §2 step 10: "Any throw … goes to failRun" -> "normally"; shutdown and handoff-ended turns do not (`executor.ts:1977-1987`).
7. §3 retries: added that same-model retry only happens before any visible output and when no backup took over (`pi-runtime-fallback.ts:633-659`), and where the window comes from (`:452`).
8. §4 row 1: unconditional "push finished" -> conditional (`run-turn.ts:960-965`).
9. §4 row 2: "Routine/reaction/background runs" -> the actual `allowSilentEmpty` definition with citations (`executor.ts:822-823`, `run-replies.ts:24-26`); the original had no citation for this.
10. §4 row 3: added the conditions (no tool call, not `allowSilentEmpty`) from `pi-runtime.ts:1244`.
11. §4 row 4: "Any text already streamed is kept" -> conditional (`run-turn.ts:1044-1057`); failure push -> conditional (`:1134-1141`); "error summary shown in the composer area" narrowed to what the cited lines show.
12. §4 row 8: added that background-trigger runs get no stop text (`run-turn.ts:649`).
13. §4 row 14 (wrong claim): "System note 'Stopped. Anything already done stays done.'" on every stop -> only when the caller passes `note`; `stopThreadRuns` passes none (`thread-stop.ts:48-50`, `:167-172`). Routine note added.
14. §4 row 15 (wrong number): "250 ms doubling to 10 s" -> doubling to 8 s; the exponent is capped at 5 so the 10 s cap is never reached (`run-lifecycle.ts:199-201`). Failure push made conditional (`:121-134`).
15. §4 row 16 and §8.2: "Side-effecting tools whose earlier execution was interrupted" -> calls tracked as an external effect whose record is still `executing` (`approval-effect.ts:448-450`); which tools are tracked is marked unverified. Added the other call sites and that the quoted sentence is one of three variants (`approval-effect.ts:477-482`).
16. §4 row 19: "run completes normally" -> runtime emits text + `done`; executor side not traced.
17. §4 cleaning: "only plain Error is logged as a server error" -> two sandbox error classes are also logged as warnings (`run-turn.ts:1073-1098`).
18. §4 cleaning: `normalizeRunError` "maps raw provider errors to one short summary" -> "recognised" errors; one branch returns the raw text as summary (`run-error.ts:298`).
19. §5: "the computer-mode transition tool" -> a tool built in `pi-runtime-computer-mode.ts` (only its definition lines were read by either pass).
20. §5 order of work and refusal chain: added the steps the original list skipped (computer-mode check; daily check-in, connector name conflict, request preparation).
21. §5 shell: added the lines where the two timers are applied (`shell-command-stream.ts:186-187`, `:230-232`) and a note that the code attaching the notice was not opened.
22. §5 truncation: "shortened head+tail around a marker" -> head+tail is only the plain-text fallback; structured shorteners run first (`context-selection.ts:497-502`).
23. §6: "Routine and background runs do not stream progress at all" -> no text/progress events; thinking indicator is skipped only for background/scripted (`run-turn.ts:137`).
24. §6: "each at most 500 chars" -> 500 for narration; `message_user` cap is env-configurable (`user-progress.ts:73-82`).
25. §7.2: added the connected-chat same-channel rule (`run-state.ts:158-161`).
26. §7.6: "fixed prompt" -> webhook-origin batches use the message text (`thread-steering.ts:251-254`); continuation only when no other active run (`:215-223`).
27. §8.2/§8.3/§8.4 (missed evidence that contradicts a negative claim): the report said no general tool-failure instruction exists. `packages/adapters/src/task-catalog.ts:29` is one, injected when `task_catalog` is offered (`executor.ts:1339-1341`): correct once, then stop and explain. Added it, plus the "Never mark work done before verification" line (`task-catalog.ts:27`). Weakness 15 updated.
28. §8.3.3: added `run-tool-gate.ts:399` wording.
29. Weakness 5: added that a tool `label` replaces the technical line (`pi-runtime-tools.ts:225`).
30. Weakness 8: lease timing wording tightened (`run-lifecycle.ts:162`, `:413`).
31. Weakness 13: "would be handled as a user stop" -> gets stop reason `aborted`; downstream effect marked unverified.

**Confirmed without change (selection):** Pi package pins; all values in the limits table; loop-guard thresholds 6/25/4 and 24 actions; `MAX_SELF_RECOVERIES_PER_RUN = 3`; `MAX_SILENT_TOOL_CONTINUATIONS = 3`; 12 000-char tool result limit and its exemptions; shell timeout 5 min / 60 min; subagent limit 4 and no nesting; lease 5 min, heartbeat 60 s, recovery scan 5 s, lease watch 1 s; setup failure limit 8; stuck-work 4 h / 24 h / 30 min; routine retry 12 min; steering reset 3 per run / 60 s; progress flush 250 ms; activity detail 90 chars; loop-guard stop finalised as `completed`; the docs-vs-code disagreement on sequential tool batches; the stale "Pi 0.85.1" comment.

**Remaining doubts:**

- Nothing inside the Pi packages could be read (no `node_modules`). Every statement about Pi's own behaviour (parallel tool execution by default, how a thrown tool error becomes a tool result, any built-in step cap, `steer` vs `followUp` semantics) rests on rakazo's comments only.
- Negative claims cannot be proven by citation: "no max step count", "no wall-clock limit", "no generic per-tool timeout", "no automatic tool retry", "no refusal handling", "no runtime verifier of done claims". I re-grepped for the tool-failure wording (and found item 27) and saw no timeout wrapper in `pi-runtime-tools.ts:489-711`, but did not search the whole repository for the others.
- `executor.ts:488-1740` (setup) was not read by either pass beyond the lines cited; statements about what setup does are a summary, not verified line by line.
- How often `task_catalog` (and therefore the "correct once, then stop" rule) is offered to a normal chat run was not traced.
- Which tools go through the external-effect record (and so can return "outcome is unknown") was not traced.
- The approval card flow, the realtime transport and client rendering remain unread, as the original already says.
- `apps/api/src/runs.ts:68-120`: only the start of the function and its status filter were opened; "no part in execution" is an inference from that.
