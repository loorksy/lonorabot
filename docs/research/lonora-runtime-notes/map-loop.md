# Part 1.1 — The agent loop (map, guards, and every way a run ends unfinished)

Repository `/home/user/lonorabot`, HEAD `9f5b1da`. Read-only audit. All paths are relative to the repo root.
Short path aliases used below: `AR/` = `packages/agent-runtime/src/lonora_agent/`.

## 0. The five findings that matter most for the owner's complaint

1. **There is no completion check on an ordinary chat run.** The loop ends on the first model turn that has text and no tool call (`AR/tool_loop.py:590-611`). The only "is the job done?" gate (`task_stop_gate`) returns "stop" at once when the run is not bound to a Task (`AR/stop_gates.py:180-181`). So a reply that says "I could not read gold, shall I search for the right name?" is accepted as a finished answer. Nothing asks the model to take the safe read-only next step first.
2. **A failed tool reaches the model as a bare code.** Any `LonoraError` from a tool handler is converted to `{"ok": False, "code": error.code}` and nothing else (`AR/tool_dispatch.py:110-117`). The runtime then adds a generic recovery hint chosen by the code's suffix: every `*_not_found` code gets `category="not_found", next_action="inspect_existing_state"` (`AR/environment.py:80-81`). The recovery block also carries `schema_tool: "tool_environment"`, `attempt` and `retry_exhausted` by default (`packages/contracts/src/lonora_contracts/tool_environment.py:27-33`); the production trace shows exactly `{"category":"not_found","next_action":"inspect_existing_state","safe_to_retry":false,"schema_tool":"tool_environment","attempt":1,"retry_exhausted":false}` for both gold failures (`production-trace.md` Part 4, #15 and #17). So the model knows `symbol_not_found` and `broker_account_not_found` only as code words, with no candidates and no human sentence; the only tool it is pointed at is the catalogue tool `tool_environment`, not a symbol lookup. The lookup tool that does exist, `market_symbols` ("Use before guessing broker symbols or aliases; suffixes matter.", `packages/tools/src/lonora_tools/market.py:98-103`), has no `eager=` and was not among the 23 native tools in any production run (`production-trace.md` Part 1, BASELINE line), while the native `market_instrument` description tells the model to use "ONE exact broker symbol from market_symbols" (`packages/tools/src/lonora_tools/market.py:108`). This is the direct source of «رجعت **symbol_not_found**». (Correction by the checker: the first version said the recovery named no follow-up tool; the code and the trace show it names `tool_environment`.)
3. **No output filter removes internal codes.** The only reply filter is a privacy filter (credentials, private paths, private UUIDs) (`packages/core/src/lonora_core/public_reply.py:54-67`). Its header states the design: "Public capability names and ordinary diagnostic vocabulary are not credentials." and "Presentation is owned by the model's instructions, not a keyword veto on replies." (`packages/core/src/lonora_core/public_reply.py:3-4`). `docs/agent-operating-policy.md:69-71` says the policy "requires ... no narration of internal cards, tools, skills, runs, events or API plumbing"; in code this is prompt text only, with no enforcement. The doc is not wrong, but the reader should know the code does not enforce it.
4. **The runtime's own repair prompts point at asking or reporting, not at acting.** `NO_ANSWER` says "ask a necessary clarification with wait_for_input" (`AR/runtime_notices.py:96-99`); the same-tool failure warning ends "or report the blocker" (`AR/tool_guardrails.py:82-86`); the manual says "Report the practical failure and one concrete next step" (`packages/agent-runtime/resources/system/lonora.md:163`), which is what «الخطوة التالية المفيدة: أبحث لك ... إذا أردت» obeys literally. The manual is not one-sided, though: in the same core section it says "For an ordinary safe read failure, make a bounded meaningful correction or use a genuinely supported alternative source." (`packages/agent-runtime/resources/system/lonora.md:160`) and "Do not ask the owner whether to perform analysis, inspect a chart or build a plan they already requested: do that reversible work first." (`packages/agent-runtime/resources/system/lonora.md:135`), and its trading section says "Translate technical diagnostics into the owner's language without stack traces or hidden identifiers." (`packages/agent-runtime/resources/system/lonora.md:350`). The gold reply broke lines 135, 160 and 350; it was model non-compliance that nothing in the runtime checks, not obedience to a bad instruction. The runtime notices (R9, G2, T3, T14) are the part that really offers asking/reporting as an equal option.
5. **An identical failing read is locked for the rest of the request after 3 failures.** `blocked_route` refuses a call whose route (tool + exact arguments) failed 3 times (`AR/environment.py:127-131`) with `tool_route_exhausted` / `alternate_route_or_wait` (`AR/tool_dispatch.py:70-81`). The lock is lifted only by a real owner message, an external wake or an owner Task resume (`AR/environment.py:104-124`, called from `AR/tool_guardrails.py:218-223`; callers `AR/steering.py:47-48`, `AR/loop_restore.py:78`, `:104`). This is fine for an unchanged retry, and it does not stop the model from trying a different symbol, but the text it gets ("alternate_route_or_wait") again offers waiting as an equal option.

---

## 1. One run, from owner message (or wake) to final reply

### 1.1 Admission: message → Run or steering
- An owner message selects target agents; a paused agent is skipped and gets no Run at all (`packages/db/src/lonora_db/messages.py:514-515`). The owner then sees no reply for that agent. UNSURE: I did not check whether another layer tells the owner the agent is paused.
- If the agent already has a Run in the thread with status `queued/leased/running/waiting_input` (`packages/db/src/lonora_db/messages.py:516-525`) and it is conversational or waiting on a question (`packages/db/src/lonora_db/messages.py:533-536`), the message does not start a new Run. It becomes a `SteeringRow` on the active Run, and a `waiting_input` Run is set back to `queued` (`packages/db/src/lonora_db/messages.py:570-573`).
- Otherwise a new Run is created with trigger `user` (or `group`) (`packages/db/src/lonora_db/messages.py:576-580`).
- Wakes and background work use the triggers in `WORK_TRIGGERS` = tickets, routine, watch, webhook, subagent, broker_event, activation (`packages/contracts/src/lonora_contracts/runs.py:7-9`).

### 1.2 Claim and dispatch (worker)
- The gateway builds one `AgentRuntime(load_tools(), lease_seconds, maximum_rounds)` (`packages/gateway/src/lonora_gateway/service.py:102`), fed from settings (`apps/worker/src/lonora_worker/runtime.py:13-14`).
- `dispatch_one` claims the next Run (`packages/gateway/src/lonora_gateway/run_dispatch.py:50`) and calls `runtime.execute(context)` (`packages/gateway/src/lonora_gateway/run_dispatch.py:92`).
- `claim_next` takes `queued` Runs and Runs whose lease expired while `leased/running`, as long as `recovery_count < MAX_RUN_RECOVERIES` (`packages/db/src/lonora_db/runs.py:194-202`); it honours a checkpointed retry deadline (`packages/db/src/lonora_db/runs.py:205-206`); it never claims a Run of a paused agent (`packages/db/src/lonora_db/runs.py:244`, `:259`); one live Run per thread at a time (`packages/db/src/lonora_db/runs.py:234-240`). Each claim increments the lease fence (`packages/db/src/lonora_db/runs.py:280`).

### 1.3 `execute_run` (the outer shell)
- Starts a lease heartbeat task (`AR/executor.py:111`), sets the Run to `running` and emits `run.running` (`AR/executor.py:113-127`).
- Loops `execute_tool_loop` until an outcome ends the pass (`AR/executor.py:128-129`):
  - external wait (`task_wait`) → `settle_task_wait`; "continue" re-enters the loop (`AR/executor.py:131-141`);
  - waiting (question, approval, owner attention) → writes the question as an assistant message and sets `waiting_input` (`AR/executor.py:142-254`, status at `:245`); if steering arrived meanwhile it loops again instead (`AR/executor.py:154-155`);
  - otherwise `complete_run` (`AR/executor.py:255-257`). `complete_run` returns `False` when unread steering exists (`packages/db/src/lonora_db/runs.py:364-370`), which sends the executor round the loop again (`AR/executor.py:258-260`).
- Exception exits are listed in section 6.

### 1.4 `execute_tool_loop` (one pass)
1. Read the checkpoint, the tool scope, the capability (BACKGROUND for work triggers, CONVERSATION otherwise) and whether this is a Task run (`AR/tool_loop.py:329-336`).
2. `restore_checkpoint`: restore `messages` and `pending` calls; on first entry build the context (`AR/loop_restore.py:54-56`); freeze the Run's tool exposure (`AR/loop_restore.py:62-64`).
3. Resume handling: a Task control that resumed held work (`AR/tool_loop.py:365-366`); a pending question (`AR/tool_loop.py:367-379`); an external wait (`AR/tool_loop.py:380-389`); a new wake delivered once as a `<runtime_wake>` user message (`AR/tool_loop.py:390-392`, `AR/loop_restore.py:105-112`).
4. `while True` (`AR/tool_loop.py:394`):
   - lease check and Task pause/cancel check (`AR/tool_loop.py:395-396`);
   - limit / halt boundary (`AR/tool_loop.py:399-438`), see sections 2 and 3;
   - run the pending tool block one segment at a time (`AR/tool_loop.py:441-454`);
   - merge steering, Task controls, skill-authority recheck (`AR/tool_loop.py:460-465`);
   - budget arithmetic and warning (`AR/tool_loop.py:467-488`);
   - one model turn (`AR/tool_loop.py:504-516`);
   - count the round (`AR/tool_loop.py:566`); empty conversational turn → `NO_ANSWER` notice and loop (`AR/tool_loop.py:573-579`);
   - append the assistant message, set `pending` to its tool calls, checkpoint (`AR/tool_loop.py:580-589`); if there are calls, loop (`AR/tool_loop.py:590-591`);
   - no calls: if steering arrived, loop (`AR/tool_loop.py:592-594`); else `final_answer` (`AR/tool_loop.py:595-611`).
5. `final_answer` applies the Task stop gates and appends the uncertain-outcome line when needed (`AR/loop_outcomes.py:155-184`). For a non-Task run it always returns the reply as final.
6. `complete_run` writes the assistant message only if there is text, an artifact or rich content, and never for trigger `tickets` (`packages/db/src/lonora_db/runs.py:379`), then sets `completed` (`packages/db/src/lonora_db/runs.py:424`).

Every checkpoint goes through `persist` (`AR/tool_loop.py:117-126`), which requires the live lease.

---

## 2. Iteration limits (exact numbers)

| Limit | Value | Where |
| --- | --- | --- |
| Model rounds per run (`maximum_tool_rounds`) | default **24**, allowed 1–100 | `apps/api/src/lonora_api/env.py:97`; runtime default `AR/runtime.py:8`; `.env.example:20` |
| Tool-offering turns in a chat run | **23**, then turn 24 is a tool-less final report | `executable = final_limit - rounds - 1` (`AR/tool_loop.py:471`); `executable <= 0` → `finish_turn` (`AR/tool_loop.py:472-485`) |
| Budget warnings | at 2 and at 1 executable rounds left (`BUDGET_WARNING_ROUNDS = 2`) | `AR/tool_loop.py:114`, `:486-488` |
| Task slices | `MAXIMUM_SLICES = 4` → 4 × 24 = **96** rounds; each slice is released and reclaimed | `AR/continuation.py:20`, `:83-90`; `AR/tool_loop.py:467-468` |
| New budget on owner input at a limit | rounds reset to 0, slice to 1 | `AR/tool_intent.py:111-121`, used at `AR/tool_loop.py:402-410` |
| Parallel tool calls | `MAXIMUM_PARALLEL_TOOLS = 4` | `AR/tool_batch.py:49` |
| Tool deadline | 45 s reads, 90 s mutations, none for financial | `packages/tools/src/lonora_tools/base.py:15-16`, `:99-104` |
| Same route failing | blocked from the 4th attempt (`failures >= 3`) | `AR/environment.py:129` |
| Transient read auto-retry | re-queued with `2**attempt` seconds delay; not retried after 3 failures | `AR/environment.py:219-224`, `:206-209`; `AR/tool_block.py:309-328` |
| Guardrail thresholds | see section 5.2 | `AR/tool_guardrails.py:56-73` |
| Task stop-gate nudges | `MAXIMUM_STOP_NUDGES = 2` | `AR/stop_gates.py:41` |
| Model failure streak, chat | `CONVERSATION = BackoffProfile(10.0, 60.0, 3)`: retry after failures 1 and 2, fail on the 3rd | `AR/model_recovery.py:59`, `:187-194` |
| Model failure streak, background/Task | `WORK = BackoffProfile(30.0, 900.0, 6)`; continuous Task also holds only after 12 h | `AR/model_recovery.py:61`, `:63` |
| Context-overflow retries | `MAXIMUM_OVERFLOW_RETRIES = 3`, each scaling input by 0.7, floor 0.3 | `AR/model_recovery.py:42-43`, `:166-173`; `packages/providers/src/lonora_providers/context.py:19` |
| Run lease | 120 s default (min 30), renewed every third | `apps/api/src/lonora_api/env.py:96`; `AR/executor.py:54` |
| Crash recoveries before quarantine | `MAX_RUN_RECOVERIES = 5` | `packages/db/src/lonora_db/runs.py:21` |
| Tool result kept inline | 120,000 characters, larger is stored and summarised | `AR/tool_block.py:255-256` |

**Doc vs code.** `docs/tool-execution-runtime.md:361-362` says a context overflow "tightens admission and compacts before one bounded retry". The code allows up to three (`AR/model_recovery.py:43`, `:169-173`). The code wins.

---

## 3. Stop conditions

A pass of the loop ends when one of these is true:
1. A model turn has no tool calls and (for Task runs) the stop gates allow it (`AR/tool_loop.py:595-611`).
2. `rounds >= limit`, or a guardrail halt is recorded, or a `limit_exit` report is already checkpointed (`AR/tool_loop.py:400`) → `finish_turn` (`AR/tool_loop.py:428-438`), unless owner input buys a new budget (`AR/tool_loop.py:402-410`) or a Task takes another slice (`AR/tool_loop.py:411-416`).
3. The next turn would be the last budgeted one (`AR/tool_loop.py:472-485`).
4. A tool result asks for a wait: owner question `_runtime_wait` (`AR/tool_block.py:370-375`, `:392-393`), trade approval `_runtime_retry` (`AR/tool_block.py:335-346`), external wait `_runtime_external_wait` (`AR/tool_block.py:363-369`, `:389-391`), or `group_silence` as the last call (`AR/tool_block.py:394-412`).
5. A scheduled retry releases the worker (`ToolRetryScheduled`): read retry (`AR/tool_block.py:326-328`), retry deadline not reached (`AR/tool_loop.py:446-447`), model backoff (`AR/tool_loop.py:552`), Task slice (`AR/tool_loop.py:416`).
6. An exception: lease lost, Task suspended, model failure, any other error (section 6).

---

## 4. Tool execution, streaming, steering

### 4.1 Tool execution: serial by default, bounded parallel for safe reads
- The pending block is split into ordered segments. A call may join a parallel segment only if the server registry marks it read-only, non-financial and `parallel_safe` (`AR/tool_batch.py:58-60`, `packages/tools/src/lonora_tools/base.py:106-108`). Two or more adjacent admissible calls form a parallel segment; a lone one stays serial; every other call is a barrier run alone (`AR/tool_batch.py:63-86`).
- Parallel segments run under a semaphore of 4 and return results in call order (`AR/tool_batch.py:95-120`). The loop always takes only the first segment of what is pending (`AR/tool_batch.py:89-92`, `AR/tool_block.py:295-296`), so steering and Task controls are checked between segments (`AR/tool_loop.py:441-445`).
- Before a serial call can cause an effect, skill authority is rechecked and an in-flight marker is checkpointed (`AR/tool_block.py:184-193`). A parallel read segment marks all its calls once (`AR/tool_block.py:228-229`).
- `dispatch_call` order: stored receipt (`AR/tool_dispatch.py:42-54`) → reconcile the same ambiguous financial operation (`AR/tool_dispatch.py:55-69`) → blocked route (`AR/tool_dispatch.py:70-81`) → interrupted non-replayable call becomes `tool_execution_uncertain` (`AR/tool_dispatch.py:82-95`) → execute (`AR/tool_dispatch.py:96-108`).
- Errors become observations, never exceptions: `LonoraError` → `{"ok": False, "code": ...}` (`AR/tool_dispatch.py:110-117`); timeout/connection → `tool_read_timeout` / `tool_connection_failure` for reads, `tool_execution_uncertain` for effects (`AR/tool_dispatch.py:118-128`); anything else → `tool_internal_failure` for reads, `tool_execution_uncertain` for effects (`AR/tool_dispatch.py:129-138`). Only `stale_lease` and `skill_continuation_unavailable` propagate (`AR/tool_dispatch.py:111-112`).
- `registry.execute` refuses unknown or out-of-scope tools with `tool_not_allowed` (`packages/tools/src/lonora_tools/registry.py:478-480`, `:483-484`) and financial tools outside full scope with `observe_only_execution_forbidden` (`packages/tools/src/lonora_tools/registry.py:481-482`, `:487-490`).
- `docs/tool-execution-runtime.md:163-178` matches this code.

### 4.2 Streaming
- Text deltas from the provider go through `PublicStream`, which publishes only whole words, at least 8 new characters and at most every 0.2 s (`AR/public_stream.py:41-46`, `:54-62`), coalesced with a 25 ms wait (`AR/stream_publication.py:46`), preview capped at 256,000 characters (`AR/stream_publication.py:10`), and re-chunked to 1,024 characters per event (`AR/progress.py:11`, `:62`).
- Incremental streaming is switched off for the whole turn when an unverified or unsettled financial result is in the transcript (`AR/model_runtime.py:106-109`), and for the rest of the turn the moment the text matches an effect-claim pattern such as «تم تنفيذ» / "order ... executed" or a privacy violation (`AR/public_stream.py:11-20`, `:47-51`). The text is not lost: the accepted final reply is published once at the end (`AR/model_runtime.py:282-291`).
- Each provider attempt starts a new stream generation (`AR/model_runtime.py:159-171`). A failed turn that will be retried has its preview discarded (`AR/executor.py:268-281`).

### 4.3 Steering by a new owner message mid-run
- Admission adds a `SteeringRow` (section 1.1). The loop notices it only at boundaries; it does not interrupt a model request or a tool that is already running.
- Before each tool segment: unexecuted calls are answered `{"ok": false, "code": "tool_call_superseded"}` and their approvals cancelled (`AR/tool_loop.py:443-445`, `:353-361`; `AR/tool_intent.py:21-32`, `:35-53`). A non-read-only call that may already have started is answered `tool_execution_uncertain` instead (`AR/tool_block.py:73-84`).
- After the block: the owner message is appended as a `user` message; real owner input resets the stop gates and the guardrails (`AR/steering.py:33-48`; `AR/tool_loop.py:460-461`).
- After a drafted final reply with no calls: steering makes the loop run another model turn instead of finishing (`AR/tool_loop.py:592-594`).
- At a limit: owner input starts one new bounded budget (`AR/tool_loop.py:402-410`).
- During a model-outage backoff: an owner message clears the backoff so the Run is claimed at once (`AR/executor.py:282-291`).
- An unpublished question is withdrawn when a new owner message arrives (`AR/tool_loop.py:377-379`).

---

## 5. Census (b): every guard that can rewrite or block a reply or a tool call

Classification key: **SAFETY** = needed for the money-safety rules; **RELIABILITY** = needed to bound cost/loops, not a money rule; **OVER-CAUTION** = pushes the agent to stop, ask or report where a safe read-only step exists; **MIXED** = the mechanism is needed, the wording over-steers.

### 5.1 Guards on the reply text

| # | Guard | Exact text injected / shown | Where | Class | Reasoning |
| --- | --- | --- | --- | --- | --- |
| R1 | Prose beside a proposed financial call is blanked | reply text set to `""` | `AR/model_runtime.py:225-228` | SAFETY | No "done" before the broker result exists. |
| R2 | Reply replaced when a financial result is confirmed but not independently verified | «أقرّ الوسيط بالطلب، لكن التحقق المستقل من نتيجته لم يكتمل بعد. لن أكرر الإرسال.» / "The broker acknowledged the request, but its resulting state is not yet independently verified. I will not resend it." | `AR/context/financial_result.py:121-125`, applied `AR/model_runtime.py:229-232` | SAFETY | Truthful status; forbids resend. Note it replaces the whole reply until the next owner message (`AR/context/financial_result.py:79-82`). |
| R3 | Reply beside `task_wait` replaced by known outcome facts | «تعذر تأكيد نتيجة الطلب؛ سأتحقق من حساب الوسيط قبل أي إعادة إرسال.» (`:152`); «لم تتأكد جميع نتائج طلبات التداول؛ سأتحقق من حالة الحساب قبل أي إعادة إرسال.» (`:194`); «لم يُنفّذ الطلب» + known cause (`:203`); «نتيجة الطلب غير محسومة؛ سأتحقق من حساب الوسيط قبل أي إعادة إرسال.» (`:209`) | `AR/context/financial_result.py:129-214`, applied `AR/model_runtime.py:233-238` | SAFETY | Same boundary for a continuous Task's update. |
| R4 | Uncertain-outcome line appended to the final reply | «نتيجة العملية غير مؤكدة بعد؛ أتحقق منها ولن أعيد إرسالها.» / "The outcome is not confirmed yet; I am checking it and will not resend it." | `AR/uncertain_outcome.py:36-37`, `:134-152`; called `AR/loop_outcomes.py:179-183` and `AR/tool_loop.py:299` | SAFETY | Appends only; reply kept. |
| R5 | Privacy redaction | sensitive spans → `[REDACTED]` | `packages/core/src/lonora_core/public_reply.py:26`, `:54-67`; applied `AR/model_runtime.py:246` | SAFETY (never print secrets) | Does not touch codes or tool names by design (`public_reply.py:3-4`). |
| R6 | Provider-supplied rich content dropped; only server-compiled cards kept | — | `AR/model_runtime.py:193` | SAFETY | Cards cannot be forged by a provider. |
| R7 | Suggested reply dropped beside calls, cards, unverified results or when it needed redaction | — | `AR/model_runtime.py:222-224`, `:249-260` | RELIABILITY | Cosmetic. |
| R8 | Incremental stream disabled on effect-claim wording | (no text; delays display to end of turn) | `AR/public_stream.py:11-20`, `:47-51` | SAFETY | Only delays; nothing removed. The Arabic pattern covers execute/open/close/send/activate/buy/sell/approve words only (`AR/public_stream.py:16-17`); «تم الإلغاء» / «أُزيلت» are not matched, and even a match never checks the claim against tool results. No reply guard compares a claimed effect with the run's tool observations (consistent with the trace: run ddae66ad replied «تم الإلغاء» after three `watch_create` calls and the saved state shows no rewrite, `production-trace.md` Part 4, finding 9). |
| R9 | Empty conversational reply is not accepted | `"No answer was provided for the selected request. Provide the substantive result or ask a necessary clarification with wait_for_input. Do not invent results."` | `AR/runtime_notices.py:96-99`; used `AR/tool_loop.py:573-579` | MIXED | Needed (an empty reply is worse). But the only two options it offers are "result" or "ask"; it never says "take the next safe read-only step". It also repeats every round with no cap of its own until the round limit. |
| R10 | Tool-less final report at a limit or halt | `"This run reached its tool-round limit."` or `"This run stopped a repeating tool loop: <detail>."` + `" No tool call will execute any more. Write the final reply to the owner now, in the owner's language: report only results verified by tool observations in this run; name every operation whose outcome is unresolved or unverified without calling it successful; and give the concrete next steps. Do not invent progress."` | `AR/runtime_notices.py:117-129`; used `AR/tool_loop.py:251-255` | RELIABILITY + SAFETY wording | Needed. Risk: the `<detail>` is the guardrail's English sentence containing the raw tool name (for example "market_quote failed 8 times in this run. Stop retrying this failing path.", `AR/tool_guardrails.py:87-89`), which the model may copy into its report. |
| R11 | Deterministic fallback when the final-report call fails or is empty | «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.» | `AR/runtime_notices.py:132-139`; used `AR/tool_loop.py:273-284` | RELIABILITY | Honest. It uses the internal word «الجولة» (run/round) and puts the next move on the owner. |
| R12 | Budget warning | `"This is the last model round in this run whose tool calls will execute."` / `"N model rounds whose tool calls will execute remain in this run, including this one."` + `" Prioritize the steps that matter most; after that no further tool calls will execute and you will be asked for a final report."` | `AR/runtime_notices.py:102-114`; used `AR/tool_loop.py:486-488` | RELIABILITY | Neutral. |

### 5.2 Guards on tool calls (loop guardrails)

Thresholds (`AR/tool_guardrails.py:56-73`): exact-failure warn 2; same-tool failure warn 3, halt 8; no-progress warn 2, block 5, halt 7; identical consecutive call notice 3, halt 5; identical effect warn 2, block after 5, halt on 2nd refusal; cycle period 2–4, notice at 3 laps, halt at 5; history 32. Warnings and halts are attached to the tool result as a `runtime_notice` (`AR/tool_block.py:329-334`); a block or halt before execution returns the synthetic result `{"ok": False, "code": "guardrail_blocked", "executed": False, ...}` (`AR/tool_guardrails.py:302-310`, `AR/tool_block.py:181-182`). A halt makes the loop finish with R10 (`AR/tool_loop.py:453-457`, `:400-401`). Real owner input or a wake resets all of it (`AR/tool_guardrails.py:218-223`).

| # | Code | Exact message | Lines | Class | Reasoning |
| --- | --- | --- | --- | --- | --- |
| G1 | `repeated_exact_failure_warning` | "{tool} has failed {count} times with identical arguments. Inspect the error and change strategy instead of retrying it unchanged." | `AR/tool_guardrails.py:78-81` | RELIABILITY | Good: tells the model to change strategy. |
| G2 | `same_tool_failure_warning` | "{tool} has failed {count} times in this run. Diagnose the latest error before another attempt: correct the arguments, use a narrower request or a genuinely different source, or report the blocker." | `:82-86` | MIXED | Fires at the 3rd failure of the same tool with any arguments (`:336-337`). Three wrong symbol guesses on `market_quote` already trigger "or report the blocker". |
| G3 | `same_tool_failure_halt` | "{tool} failed {count} times in this run. Stop retrying this failing path." | `:87-89` | MIXED | Halts the whole run at 8 failures of one tool even when every attempt used different arguments (`:330-333`). A symbol search by trial (XAUUSD, XAUUSDm, GOLD, XAUUSD.a, …) counts toward 8. A successful read of the same tool resets the count (`:339-340`). |
| G4 | `idempotent_no_progress_warning` | "{tool} returned the same result {count} times. Use the result already provided or change the request instead of repeating it unchanged." | `:90-93` | RELIABILITY | Correct. |
| G5 | `idempotent_no_progress_block` | "{tool} was not executed: the identical read already returned the same result {count} times. Use that result or change the request." | `:94-97` | RELIABILITY | Correct. |
| G6 | `idempotent_no_progress_halt` | "{tool} kept being requested unchanged after it was refused for making no progress." | `:98-100` | RELIABILITY | Correct. |
| G7 | `identical_call_warning` | "This is call {count} in a row to {tool} with identical arguments and an identical result. Do not repeat it; change the arguments, use a different tool or proceed with what you have." | `:101-105` | RELIABILITY | Correct. |
| G8 | `identical_call_halt` | "{tool} was called {count} times in a row with identical arguments and an identical result." | `:106-108` | RELIABILITY | Correct. |
| G9 | `identical_cycle_warning` / `identical_cycle_halt` | "The last {count} rounds repeated the same cycle of {period} calls (ending with {tool}) with identical arguments and results. Repeating it is not progress." / "The same cycle of {period} calls (ending with {tool}) repeated {count} times with identical arguments and results." | `:109-116` | RELIABILITY | Correct. |
| G10 | `identical_effect_warning` | "{tool} has now run {count} times in a row with identical arguments. Each call is a separate effect, not a retry: check the earlier results and do not repeat it unless another identical effect is really intended." | `:117-121` | SAFETY | Stops duplicated orders. |
| G11 | `identical_effect_block` | "{tool} was not executed: it already ran {count} times in a row with identical arguments in this run, and this call changed nothing. Use the earlier results, change the request, or report to the owner." | `:122-126` | SAFETY | Same. The rule covers every non-read-only, non-poller tool (`:236-237`), so an identical close call would be counted too, but only after five identical executions in a row, and reconciliation of the same operation is exempt (`:260-282`). Exits stay admissible in practice. Checked: `trade_close_positions` is `financial=True` and keeps the default `read_only=False`, `poller=False` (`packages/tools/src/lonora_tools/trade.py:780`; `packages/tools/src/lonora_tools/base.py:72`, `:82`), so it is counted by this rule; only a sixth identical close in a row is blocked. |
| G12 | `identical_effect_halt` | "{tool} kept being requested with identical arguments after it was refused for repeating the same effect {count} times." | `:127-130` | SAFETY | Same. |

**Doc vs code.** `docs/tool-execution-runtime.md:238` says an identical read is "block at 5, halt after 2 ignored blocks". In code the refused attempt itself is counted (`AR/tool_guardrails.py:294`), so the first refused repeat is a block and the second refused repeat is the halt (`AR/tool_guardrails.py:62`, `:295-298`). The code wins: one block, then halt.

### 5.3 Other blocks on tool calls inside the loop

| # | Guard | What the model receives | Where | Class | Reasoning |
| --- | --- | --- | --- | --- | --- |
| T1 | Tool error → bare code | `{"ok": false, "code": "<code>"}` (+ `issues`, `retryable` only for argument errors) | `AR/tool_dispatch.py:110-117` | **OVER-CAUTION by omission** | The handler's knowledge (which symbols exist, which account is bound) is thrown away. This is the main feeder of the owner's example. |
| T2 | Recovery hint by code family | `recovery: {category, next_action, safe_to_retry}`; `*_not_found` → `not_found` / `inspect_existing_state`; default → `terminal_domain_failure` / `alternate_route` | `AR/environment.py:35-93` (`:80-81`, `:36-37`) | MIXED | Useful structure, but `inspect_existing_state` names no lookup tool; the only tool named is the default `schema_tool: "tool_environment"` (`packages/contracts/src/lonora_contracts/tool_environment.py:31`), a catalogue/schema tool, not `market_symbols`. The permission, risk, health and authorization branches (`AR/environment.py:50-73`, `:82-88`) are SAFETY ("respect_scope", "request_owner_authorization", "wait_for_authoritative_recovery"). |
| T3 | Route exhausted | `{"ok": false, "code": "tool_route_exhausted", "recovery": {"next_action": "alternate_route_or_wait"}}` | `AR/tool_dispatch.py:70-81`, `AR/environment.py:127-131` | MIXED | Blocking the 4th identical failing read is fine. "or_wait" invites stopping. |
| T4 | Ambiguous financial route | `{"ok": false, "code": "broker_result_ambiguous", "recovery": {"next_action": "reconcile_before_any_resend"}}` | `AR/tool_dispatch.py:70-81` | SAFETY | No blind resend. |
| T5 | Interrupted effect | `{"ok": false, "code": "tool_execution_uncertain"}` | `AR/tool_dispatch.py:82-95`, `:118-138`; `AR/tool_block.py:73-84` | SAFETY | An effect that may have happened is never repeated. |
| T6 | Superseded / not executed | `{"ok": false, "code": "tool_call_superseded"}` or `"tool_call_not_executed"` (+ `reason`) | `AR/tool_intent.py:21-32`; `AR/tool_block.py:86`, `:125` | SAFETY + RELIABILITY | Old intent never runs after new owner input, a limit or a wake; linked approvals are cancelled (`AR/tool_intent.py:35-53`). |
| T7 | Unknown / out-of-scope tool | `tool_not_allowed`, `observe_only_execution_forbidden` | `packages/tools/src/lonora_tools/registry.py:478-490` | SAFETY | Authority boundary. |
| T8 | Skill authority withdrawn mid-run | serial call: Run fails with `skill_continuation_unavailable` (fence code, `AR/context_engine.py:122`); parallel reads: each call gets `{"ok": false, "code": <code>}` (`AR/tool_block.py:214-227`) | `AR/tool_block.py:184-189` | SAFETY | Withdrawn instructions cannot drive new effects. |
| T9 | Read deadline | `tool_read_timeout` after 45 s (re-queued after the 1st and 2nd failure; the 3rd failure is returned with `retry_exhausted`) | `packages/tools/src/lonora_tools/registry.py:494-501`; `AR/environment.py:206-209` | RELIABILITY | Fine. |
| T10 | Oversized result | result replaced by a bounded summary with `"context_notice": "tool_result_too_large"`, `next_action: "narrow_query"` | `AR/tool_block.py:252-276`; `AR/environment.py:234-245` | RELIABILITY | Fine. |
| T11 | `wait_for_input` used as trade consent | `"code": "financial_consent_requires_trade_request"`, guidance "An order or close is trade_execute. ..." | `packages/tools/src/lonora_tools/runtime_control.py:64-73` | SAFETY | Consent only through the approval card. |
| T12 | Question with private wording | `"code": "question_wording_private"` | `packages/tools/src/lonora_tools/runtime_control.py:74-82` | SAFETY | Privacy. |
| T13 | Question while an approval is pending | `"code": "trade_confirmation_already_pending"` | `packages/tools/src/lonora_tools/runtime_control.py:94-99` | SAFETY | One consent surface. |
| T14 | `group_silence` in a direct chat | `"code": "reply_required"`, guidance "You were selected to answer this request. Give the substantive answer, or use wait_for_input for a necessary clarification. Do not stay silent." (also `silence_requires_group`) | `packages/tools/src/lonora_tools/runtime_control.py:107-118` | MIXED | Needed; again offers "ask" as the only alternative to answering. |

The `wait_for_input` tool description itself says "Use this whenever a genuinely missing owner decision blocks progress ... First recover previous answers and continue work already requested." (`packages/tools/src/lonora_tools/runtime_control.py:200-201`). That wording is balanced; the problem is that nothing in the loop checks whether the "missing decision" could have been resolved by a read.

### 5.4 Task stop gates (Task runs only)

| # | Gate | Exact text | Where | Class | Reasoning |
| --- | --- | --- | --- | --- | --- |
| S1 | Continuous Task answered in prose without a saved wait (max 2 nudges) | "This responsibility is continuous. A text answer does not complete it or save monitoring. Continue useful authorized work, or use task_wait with a real owned watch, verified broker-recovery source, or a deliberate review timer. Discover the capability through tool_environment if needed. Put any concise owner update in the same assistant message as task_wait; only a successful saved wait can support a promise to follow up. Use wait_for_input only for genuinely missing owner information or authority. Do not invent activity, ask routine trading questions, or poll the model continuously. The owner can pause or stop this work." | `AR/stop_gates.py:45-54`; applied `AR/loop_outcomes.py:170-174` | RELIABILITY (truthfulness) | Good model for a chat-run gate: it pushes toward acting and limits asking. |
| S2 | Finite Task with unfinished declared steps (max 2 nudges) | "This task is not complete: these declared steps are not completed yet: {id: title; …}. A final answer cannot complete the task. Continue the remaining authorized work and record each finished step with task_step_update citing the successful tool call that proves it. If a step is genuinely blocked, explain the blocker or ask the owner with wait_for_input. Never mark or describe unfinished work as done." | `AR/stop_gates.py:72-83` | RELIABILITY | Good. |
| S3 | Nudges spent → owner attention | see ending E6 below | `AR/stop_gates.py:126-127`; `AR/loop_outcomes.py:175-178` | RELIABILITY | Honest hand-over; the owner must act to continue. |
| S4 | Owner resumed held Task | "The owner reviewed this unfinished task and {resumed|revised} it. Continue the remaining authorized work from the current state: check the task plan and the earlier tool results first, and do not repeat effects that already happened." | `AR/runtime_notices.py:206-212`; `AR/loop_restore.py:83-87` | SAFETY wording | Fine. |
| S5 | `complete_run` refuses an unfinished Task | raises `task_wait_required` / `task_steps_incomplete` | `packages/db/src/lonora_db/tasks.py:839-850` | RELIABILITY | Backstop behind S1–S3. |

**There is no S-gate for chat runs.** `task_stop_gate` returns `StopGateVerdict(continue_turn=False)` when `task_progress` is `None` (`AR/stop_gates.py:179-181`), and `apply_stop_gates` returns the same when the Task is neither continuous nor has incomplete steps (`AR/stop_gates.py:99-104`).

---

## 6. Every way a run can end without the job being done, and what the owner sees

Arabic strings for the web error card are from `apps/web/src/i18n/locales/ar/messages.po`. The error card has a title by failure family (`apps/web/src/conversation/Cards.tsx:69-75`) and a body (`apps/web/src/conversation/Cards.tsx:76-83`); the Retry button is hidden for family `other` (`apps/web/src/conversation/Cards.tsx:96`). Family is derived in `packages/core/src/lonora_core/runtime_failure.py:39-52`.

**A. The run "completes" but the work is not done**

- **E1. The model gives up or asks in plain prose (the owner's example).** No tool call in the turn → accepted as final (`AR/tool_loop.py:590-611`; no gate for chat, `AR/stop_gates.py:180-181`). Owner sees: whatever the model wrote, including codes copied from tool results (T1). Run status `completed`, `reply_outcome: "answered"` (`AR/tool_loop.py:603-605`). Nothing marks it as unfinished.
- **E2. Round limit in a chat run.** After 23 tool-offering turns the 24th is the tool-less report (`AR/tool_loop.py:472-485`). Owner sees the model's report, or R11 «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها…» if that call fails or is empty (`AR/tool_loop.py:273-284`). Run is `completed` with `reply_outcome: "limited"` (`AR/tool_loop.py:314-322`); peers see «توقف عند حد العمل» (`apps/web/src/conversation/Cards.tsx:597-598`; `ar/messages.po:6828-6829`). The owner must send a message to continue.
- **E3. Guardrail halt in a chat run** (G3, G6, G8, G9, G12). Same path with reason `guardrail_halt` (`AR/tool_loop.py:400-401`, `:428-438`). Owner sees the model's report written from R10, or R11.
- **E4. Empty replies until the limit.** Each empty turn costs a round (`AR/tool_loop.py:566`, `:573-579`); ends as E2.
- **E5. Silent completion.** Non-conversational triggers (routine, webhook, created, tickets, watch; `packages/core/src/lonora_core/run_state.py:33-34`) with an empty turn complete with `reply_outcome: "silent"` (`AR/tool_loop.py:603-605`) and no message is written (`packages/db/src/lonora_db/runs.py:379`). Owner sees nothing. Trigger `tickets` never writes a chat message even with text (`packages/db/src/lonora_db/runs.py:379`).
- **E5b. Reply replaced by a fixed financial-status sentence** (R2/R3). The model's own explanation is dropped; the owner sees only the fixed sentence. Needed for safety.

**B. The run stops and waits for the owner**

- **E6. Task stop gate exhausted** (2 nudges). Owner sees an attention message that starts with the runtime's own sentence, then «أحتاج توجيهك قبل المتابعة: ردّ هنا، أو عدّل المهمة أو استأنفها أو أوقفها مؤقتًا أو ألغها.», then «آخر تقرير: » + the held answer (`AR/runtime_notices.py:172-203`). Lead sentences: «هذه المهمة لم تكتمل بعد.» (`AR/runtime_notices.py:143-146`) or «هذه المهمة المستمرة غير مراقَبة: لم يُحفظ أي انتظار مراقبة أو مؤقت مراجعة، لذلك لن تحدث أي متابعة تلقائية.» (`AR/runtime_notices.py:147-152`). Run `waiting_input` (`AR/executor.py:240-246`).
- **E7. Task at its final limit (96 rounds) with steps unfinished or no declared steps.** «توقفت هذه المهمة قبل اكتمالها لأن هذه الجولة بلغت حدّ العمل، ولم يُنفَّذ أي إجراء بعد ذلك.» + the same request for direction (`AR/runtime_notices.py:153-157`; `AR/tool_loop.py:302-311`; contract rule `AR/stop_gates.py:140-146`).
- **E8. Task guardrail halt.** «توقفت هذه المهمة قبل اكتمالها لأن استدعاء أداة تكرر دون تقدّم، ولم يُنفَّذ أي إجراء بعد ذلك.» (`AR/runtime_notices.py:158-162`).
- **E9. Task during a long model outage.** «هذه المهمة معلّقة لأن كل النماذج المهيأة غير متاحة منذ مدة رغم المحاولات المتكررة؛ تقدّمها محفوظ ولم يُكرَّر أي إجراء.» (`AR/runtime_notices.py:163-168`; `AR/tool_loop.py:553-559`).
- **E10. The model calls `wait_for_input`.** The question is posted and the Run waits (`AR/tool_block.py:370-375`, `:392-393`; `AR/loop_outcomes.py:71-80`; `AR/executor.py:176-246`). Owner sees the model's question and choices. This is the "asks him technical questions" path; the loop accepts any question without checking that a read could have answered it.
- **E11. Trade approval card.** `_runtime_retry` → waiting with `trade_approval_id` (`AR/tool_block.py:335-346`). Owner sees the approval card. **Needed for safety.**
- **E12. `task_wait` (external wait).** Run suspends with an optional owner update (`AR/tool_block.py:363-369`; `AR/loop_outcomes.py:39-68`; `AR/executor.py:131-141`). Intended, not a failure.
- **E13. Task paused or cancelled by an owner control.** `TaskSuspended` ends the pass quietly (`AR/tasks.py:16-44`; `AR/executor.py:305-306`); Run becomes `waiting_takeover` or `cancelled` (`packages/db/src/lonora_db/tasks.py:653-670`). No new chat text from the loop.

**C. The run is re-queued (not an end, but the owner waits)**

- **E14. Model provider transient failure.** Same checkpoint retried after backoff; preview withdrawn; event `run.retry_scheduled` with `reason_code` (`AR/tool_loop.py:528-552`; `AR/executor.py:261-304`). UNSURE: I did not trace how clients render `run.retry_scheduled`.
- **E15. Transient read failure.** Re-queued with `2**attempt` s delay, up to 3 failures (`AR/tool_block.py:309-328`; `AR/environment.py:219-224`).
- **E16. Task slice boundary.** Re-queued immediately for the next 24 rounds (`AR/continuation.py:83-90`; `AR/tool_loop.py:411-416`).
- **E17. Graceful drain.** Leases released back to `queued` with `reason_code: "gateway_drained"` (`packages/db/src/lonora_db/runs.py:490-526`).

**D. The run fails (error card)**

- **E18. Model failure streak in chat** (3rd consecutive transient failure, about 10 s then 20 s backoff plus up to 25 % jitter; `AR/model_recovery.py:59`, `:148-149`, `:187-194`). `plan_failure` returns `escalate`, a non-Task run re-raises (`AR/tool_loop.py:553-560`) and `record_failure` fails the Run with the provider code (`AR/executor.py:310-312`, `:76-96`). Codes: `model_provider_unavailable`, `model_rate_limited` (`packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:80-99`). Owner sees: «النموذج غير متاح حاليًا» + «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.» (`ar/messages.po:7331-7336`), or «طلبات كثيرة في وقت قصير» (`:7826-7827`), or «انتهت مهلة الرد» + «لم يصل الرد في الوقت المحدد، وقد يكون الاتصال ضعيفًا.» (`:7412-7413`, `:7408-7409`), with a Retry button.
- **E19. Non-transient provider failure** (rejected key, no access, billing, model not found, content policy, rejected request, truncated output, invalid response, not configured). `is_transient` is false (`packages/providers/src/lonora_providers/resilience.py:75-97`, `:130-134`) → immediate raise (`AR/model_recovery.py:174-175`; `AR/tool_loop.py:560`). Owner sees the `model` or `quota` card («نفدت حصة مزوّد النموذج», `ar/messages.po:7359-7360`). **This is the production «النموذج غير متاح» case.** All five failed runs were `model_not_configured` (`production-trace.md` Part 1, KEY FINDINGS). That code is `NOT_CONFIGURED` → non-transient (`packages/providers/src/lonora_providers/resilience.py:96`; `packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:97`), and because it starts with `model_` its family is `model` (`packages/core/src/lonora_core/runtime_failure.py:50-51`), so the card shows «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.» (`ar/messages.po:7335-7336`). The accurate sentence exists ("Connect a provider and choose a global model in Settings.", `apps/web/src/lib/user_error.ts:88-89`) but is used only for family `other` (`apps/web/src/conversation/Cards.tsx:82`). Same mechanism as E20.
- **E20. Context overflow that compaction cannot fix** (3 tries or scale at 0.3). Fails with `context_limit_exceeded` (`AR/model_recovery.py:166-170`). **Mismatch worth fixing:** this code is in `MODEL_CODES` (`packages/core/src/lonora_core/runtime_failure.py:36`), so the family is `model` (`:50-51`) and the owner sees «النموذج غير متاح حاليًا / تعذّر الوصول إلى مزوّد النموذج…», which is not the real cause. The accurate sentence exists ("This message is too large to process, even after older history was summarized. ...", `apps/web/src/lib/user_error.ts:217-220`) but the card only uses `userError` for family `other` (`apps/web/src/conversation/Cards.tsx:82`).
- **E21. Skill authority withdrawn** → `skill_continuation_unavailable` (`AR/tool_loop.py:463-465`; `AR/tool_dispatch.py:111-112`). Family `other`; body "An active skill is no longer available. Review its settings before resuming this task." (`apps/web/src/lib/user_error.ts:60-61`). Needed for safety.
- **E22. Internal state errors**: `run_checkpoint_invalid` (`AR/recovery.py:12-13`), `task_stop_gate_state_invalid` (`AR/stop_gates.py:107`, `:110`, `:121`), `task_continuation_state_invalid` / `task_continuation_budget_invalid` (`AR/continuation.py:30`, `:36`, `:46`), `task_run_mismatch` (`AR/stop_gates.py:165`), `task_wait_identity_invalid` (`AR/loop_outcomes.py:43`), `input_question_identity_conflict` (`AR/executor.py:174`), `context_identity_missing` (`AR/context/builder.py:76`). All go through `AR/executor.py:310-312`. Owner sees title «تعذّر على الوكيل الرد» (`ar/messages.po:7099-7100`) and body «تعذر إكمال الطلب. أعد المحاولة.» (`ar/messages.po:7416-7417`; default branch `apps/web/src/lib/user_error.ts:227-228`), with **no Retry button** (`apps/web/src/conversation/Cards.tsx:96`). The body says "try again" while the card offers no way to do it.
- **E23. Unexpected exception** → `runtime_error` (`AR/executor.py:313-315`). Same generic card as E22.
- **E24. Crash loop.** After 5 consecutive lease-expiry recoveries the watchdog fails the Run with `run_recovery_limit` (`packages/db/src/lonora_db/runs.py:547-558`), or holds it when an unresolved financial operation exists (`packages/db/src/lonora_db/runs.py:554-555`, needed for safety). Same generic card.

**E. The run is stopped from outside**

- **E25. Owner presses stop.** `cancel_run` sets `cancelled` and bumps the fence (`packages/db/src/lonora_db/cancellation.py:21-25`); the next lease check raises `stale_lease` (`packages/db/src/lonora_db/runs.py:302-310`; checkpoint at `AR/cancellation.py:5-7`), which the executor swallows without recording a failure (`AR/executor.py:310-311`). Owner sees «أوقفتَ الرد» (`apps/web/src/conversation/Message.tsx:423-425`; `ar/messages.po:8652-8653`). An in-flight tool is not interrupted until the next lease check.
- **E26. Lease lost.** Renewal fails past the margin or with an unknown error → the run's task is cancelled (`AR/executor.py:61-71`, `:106-109`) and the `CancelledError` is swallowed (`AR/executor.py:307-309`). The Run stays `leased/running` with an expired lease and is reclaimed (`packages/db/src/lonora_db/runs.py:197-201`), counting toward E24. Owner sees a pause, then the run resumes from its checkpoint; interrupted effects become `tool_execution_uncertain` (T5).
- **E27. Agent paused.** A queued Run is never claimed (`packages/db/src/lonora_db/runs.py:244`, `:259`), and a new message creates no Run (`packages/db/src/lonora_db/messages.py:514-515`). No text from the loop.

Note: the client has a string for a failure code `tool_round_limit` ("I paused at this run's step budget. Send a message and I continue from here.", `apps/web/src/lib/user_error.ts:225-226`), but the runtime no longer fails a Run with that code: it is only an `exit_reason` on a completed Run (`AR/tool_loop.py:401`, `:314-322`). The string is unreachable from the loop.

---

## 7. How the owner's example is produced, step by step (mechanism only, no transcript invented)

Trace facts (run 1ae9a14c, `production-trace.md` Part 2 and Part 4): `list_accounts` ok; `market_snapshot` with symbol `XAUUSD` → `symbol_not_found`; `market_instrument` with `XAUUSD` (about five seconds) → `broker_account_not_found`; both with the same recovery block; no further call; the reply is message 8. The account id passed was correct both times.

1. The model guesses `XAUUSD` without listing symbols. `market_symbols` exists (`packages/tools/src/lonora_tools/market.py:98-103`) but was not native in any production run (`production-trace.md` Part 1, BASELINE line). `market_snapshot` fails with `symbol_not_found`; the loop records `{"ok": false, "code": "symbol_not_found"}` plus the recovery block (`AR/tool_dispatch.py:110-117`; `AR/environment.py:80-81`, `:203-210`; default fields `packages/contracts/src/lonora_contracts/tool_environment.py:31-33`). UNSURE: which raise produced it, the catalogue check (`packages/tools/src/lonora_tools/symbols.py:15`) or the MetaApi 404 mapping (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:59-60`); the trace holds no stack.
2. `market_instrument` does not require the symbol to exist: `canonical_broker_symbol` returns the guess unchanged when it is not in the catalogue (`packages/tools/src/lonora_tools/market.py:47`; `packages/tools/src/lonora_tools/symbols.py:31-35`). Any MetaApi 404 outside the candles stage is mapped to `broker_account_not_found` (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:57-58`), which fits the observed code for a valid account and an unknown symbol. (Inference from code plus trace; another session owns the 404 split.)
3. The model writes a final text. No runtime rule requires another read first: no chat stop gate (`AR/stop_gates.py:180-181`; `task_progress` returns `None` when the Run has no `task_id`, `AR/stop_gates.py:153-155`). The manual lines that should have steered it (`packages/agent-runtime/resources/system/lonora.md:135`, `:160`, `:350`) are prompt text only; the line its reply resembles is `packages/agent-runtime/resources/system/lonora.md:163`.
3b. The same pattern repeats one message later: run e09ad476 («ضع حرف m») made no tool call and replied with a prose question «محتاج أوضح المقصود من "ضع حرف m"…» (`production-trace.md` Part 1, run list). A prose question with no tool call is accepted as a final answer exactly like E1; it is not even routed through `wait_for_input`.
4. The text passes the only output filter unchanged because codes are deliberately not filtered (`packages/core/src/lonora_core/public_reply.py:3-4`).
5. The Run completes as `answered` (`AR/tool_loop.py:603-605`). The owner has to type the fix himself; his message starts a new Run (`packages/db/src/lonora_db/messages.py:576-580`) or steers the old one if it is still active.

### 7b. Why no loop check fired in the three runs the lead named (ddae66ad, e343c96a, fb1d4b5a)

- All 41 runs in the thread have trigger `user` (`production-trace.md` Part 1, "41 runs, all trigger=user"), so they are CONVERSATION runs (`AR/tool_loop.py:333-335`). The only completion check is `task_stop_gate`, which returns "stop" when the Run has no `task_id` (`AR/stop_gates.py:153-155`, `:180-181`). The saved state of the three runs holds no stop-gate keys (`production-trace.md` Part 4, finding 9), which is what this path produces. UNSURE: the export does not print `model_metadata.task_id` for these runs; the absence of any gate record is consistent with it being empty.
- ddae66ad: after the owner's answer the run made three `watch_create` calls, all `ok` (`production-trace.md` Part 2). No failure → no G1-G3; the identical 2nd/3rd call gives `effect_streak` 2, which is the G10 warning threshold (`AR/tool_guardrails.py:68`); the trace shows `effect_streak ["16737922…",2,0]` and `halt: null`. UNSURE whether the G10 warning text was attached to the third result: the export cut that result at 1500 characters. Either way G10 only warns. Nothing in the loop or the reply guards compares «تم الإلغاء» with the tool results (R8 note above).
- e343c96a and fb1d4b5a: e343c96a called only `wait_for_input` and then answered in prose; fb1d4b5a made no tool call (`production-trace.md` Part 4, findings 5 and 9). Both are E1: a text turn with no calls is final.

## 8. Loop-level change candidates (none touches a money rule)

These are read-only or wording changes; none moves money, weakens an approval, or alters the journal.
1. **A bounded "unfinished chat" gate**, modelled on S1/S2: when the last tool results since the owner's message include a failed read with `recovery.category` in {`not_found`, `invalid_tool_arguments`, `stale_state`, `result_too_large`} and no later successful read, give one or two nudges ("resolve it with a read-only lookup before replying; ask only if a real owner decision is missing") before accepting the reply. Structural trigger, no keyword matching, bounded like `MAXIMUM_STOP_NUDGES` (`AR/stop_gates.py:41`).
2. **Carry safe handler detail through T1**: allow a whitelisted `hint`/`candidates` field on tool errors instead of only `code` (`AR/tool_dispatch.py:113-116`), and make `not_found` name the lookup tool instead of only `inspect_existing_state` + `schema_tool: "tool_environment"` (`AR/environment.py:80-81`; `packages/contracts/src/lonora_contracts/tool_environment.py:31`). (Symbol resolution and the error contract are being fixed in other sessions; listed here only as the loop-side cause.)
3. **Reword R9, G2, T3, T14** so the first option is "take the next safe read-only step", and asking/reporting comes last.
4. **Do not count different-argument read failures toward the 8-failure halt** (G3) as fast as identical ones, or raise it for read-only tools; the halt currently punishes legitimate search by trial (`AR/tool_guardrails.py:330-333`).
5. **Fix the two card mismatches**: E20 (context overflow shown as "model unavailable") and E22 ("Try again" with no Retry button).
6. **Owner-facing fallback R11** should not use «الجولة» and could offer to continue by itself where safe.

## 9. Docs checked against code

| Doc claim | Code | Verdict |
| --- | --- | --- |
| Parallel only for read-only, non-financial, `parallel_safe`; semaphore 4 (`docs/tool-execution-runtime.md:167-170`) | `AR/tool_batch.py:49`, `:58-60`; `packages/tools/src/lonora_tools/base.py:106-108` | Match |
| Deadlines 45 s / 90 s, none on financial (`docs/tool-execution-runtime.md:214-219`) | `packages/tools/src/lonora_tools/base.py:15-16`, `:99-104` | Match |
| Guardrail table (`docs/tool-execution-runtime.md:234-241`) | `AR/tool_guardrails.py:56-73` | Match except the "2 ignored blocks" wording (section 5.2) |
| Tool-less final report, deterministic notice if the model is unavailable (`docs/tool-execution-runtime.md:277-287`) | `AR/tool_loop.py:223-322` | Match |
| At most two Task nudges, then owner attention (`docs/tool-execution-runtime.md:310-315`) | `AR/stop_gates.py:41`, `:126-129`; `AR/loop_outcomes.py:175-178` | Match |
| Context overflow: "one bounded retry" (`docs/tool-execution-runtime.md:361-362`) | `AR/model_recovery.py:43` (three) | **Code wins** |
| Policy "requires ... no narration of internal ... tools ... or API plumbing" (`docs/agent-operating-policy.md:69-71`) | Not enforced in code; filter is privacy only (`packages/core/src/lonora_core/public_reply.py:3-4`, `:54-67`) | Prompt-only; no enforcement |
| "Public prose admission ... and financial-truth checks remain server responsibilities. There is no presentation-model call." (`docs/chat-runtime-repair.md:131-133`) | `AR/model_runtime.py:225-246` (no second generation) | Match |
| Activity is a projection in the leased progress transaction (`docs/chat-latency-activity.md:50-53`) | `AR/progress.py:18-39` | Match |

## 10. Not confirmed

- UNSURE: how the mobile app renders a failed Run. I only confirmed the generic strings «تعذر إكمال العمل» (`apps/mobile/lib/i18n.ts:75`) and «تعذر تنفيذ الطلب. حاول مرة أخرى.» (`apps/mobile/lib/i18n.ts:574`) exist; I did not trace which one a failed Run uses.
- UNSURE: whether tool error codes are shown in the activity/steps UI. The activity reducer stores the code as `error_code` (`packages/core/src/turn-activity.ts:88`); I found no place in `apps/web/src/conversation/Cards.tsx` that prints it, but I did not read every renderer.
- UNSURE: the router's in-request retries and fallbacks (`context.router.complete`, `AR/model_runtime.py:174-185`) were not traced beyond the recovery table.
- Not in this part: tool handlers, market guards (`guard_market_tool`, `packages/tools/src/lonora_tools/registry.py:514`), the full manual text, context building and compaction.

## Verification log

Checker pass, read-only on the repository. Repository HEAD at check time is `3f09572`, which adds only files under `docs/research/` on top of `9f5b1da` (`git diff --stat 9f5b1da HEAD`); every code citation is therefore valid for `9f5b1da`.

- Citations opened: 412 `path:line` references in the original file (every one printed and read, including repeats), plus 61 new citation references (including repeats) added by the checker; the full set of 473 was printed again from the edited file and checked for missing files and out-of-range lines (none).
- Citations corrected: 4. `AR/model_recovery.py:60` → `:59` (CONVERSATION profile; table and E18), `:62` → `:61` (WORK), `:64` → `:63` (CONTINUOUS). The original lines were comments or a blank line.
- Verbatim quotes: all English and Arabic quotes in sections 0-6 were compared with the source lines; no wording errors found (the wait_for_input quote uses "..." for an elided middle, which is correct).
- Totals: the file states no numeric totals other than thresholds; all thresholds (24/23 rounds, 4 slices, 4 parallel, 45/90 s, 3 route failures, 2/3/8, 2/5/7, 3/5, 2/5/2, 3/5 laps, 32 history, 2 nudges, 3/6 model failures, 3 overflow retries, 0.7/0.3, 120 s lease, 5 recoveries, 120000 chars) match the cited constants.

Claims refuted or downgraded:
1. Finding 2, "no named follow-up tool": refuted in part. `ToolRecovery` defaults `schema_tool` to `"tool_environment"` (`packages/contracts/src/lonora_contracts/tool_environment.py:31`), and the production trace shows it in both gold results. Rewritten: the hint names the catalogue tool, not a symbol lookup.
2. T2, "`inspect_existing_state` names no tool": same correction.
3. Finding 4 and section 7 step 3, "the manual line it follows is lonora.md:163": downgraded. The same core section also says to correct a safe read failure first (`packages/agent-runtime/resources/system/lonora.md:160`) and to do reversible work before asking (`packages/agent-runtime/resources/system/lonora.md:135`), and the trading section says to translate diagnostics (`packages/agent-runtime/resources/system/lonora.md:350`). The reply broke these; it did not obey a bad rule. The runtime notices remain the real "ask or report" push.
4. T9, "auto-retried up to 3 times": wrong count. A transient read is re-queued after failure 1 and 2 and returned on failure 3 (`AR/environment.py:206-209`; `AR/tool_block.py:309-328`).
5. Section 7 step 1 UNSURE (was a symbol-listing tool available?): resolved. `market_symbols` exists (`packages/tools/src/lonora_tools/market.py:98-103`) and was not native in any production run.
6. G11 UNSURE (flags of `trade_close_positions`): resolved; `financial=True`, default `read_only=False`, `poller=False`.
7. Section 7 was written before the trace; it now uses the trace's tool sequence (list_accounts → market_snapshot → market_instrument) instead of a generic "market read".

Not refuted (checked and kept): no completion gate for chat runs (`AR/stop_gates.py:153-155`, `:180-181`); bare-code error results (`AR/tool_dispatch.py:110-117`); no reply filter for internal codes (two independent greps over `model_runtime.py`, `public_stream.py`, `public_reply.py`, `visual_response.py` for code/snake-case/leak filters found nothing; `public_reply_violation` explicitly discards tool names, `packages/core/src/lonora_core/public_reply.py:37-42`); route lock at 3 identical failures; doc-vs-code verdicts on overflow retries (`docs/tool-execution-runtime.md:361-362` vs `AR/model_recovery.py:43`) and on the no-progress block/halt (`AR/tool_guardrails.py:291-299`: the 6th identical read is blocked, the 7th halts).

Added by the checker (also written into the body):
1. `market_symbols` is not native while the native `market_instrument` description points to it (`packages/tools/src/lonora_tools/market.py:108`) — section 0 item 2 and section 7.
2. `market_instrument` passes an unknown symbol through unchanged and MetaApi maps any non-candles 404 to `broker_account_not_found` (`packages/tools/src/lonora_tools/symbols.py:31-35`; `packages/adapters/src/lonora_adapters/brokers/metaapi.py:57-58`) — section 7 step 2 (cause only; the 404 split is another session's fix).
3. The production «النموذج غير متاح» card: `model_not_configured` falls into family `model` and shows the "provider could not be reached" text, although an accurate string exists (`apps/web/src/lib/user_error.ts:88-89`) — E19.
4. No reply guard checks a claimed non-trade effect («تم الإلغاء», «أُزيلت») against tool results; the effect-claim pattern has no cancel/delete words (`AR/public_stream.py:16-17`) — R8.
5. The manual's own counter-instructions (`packages/agent-runtime/resources/system/lonora.md:135`, `:160`, `:350`) — finding 4.
6. Section 7b: why no loop check fired in runs ddae66ad, e343c96a, fb1d4b5a.
7. Section 7 step 3b: run e09ad476 asked a prose clarification with no tool call, accepted as final (E1).
