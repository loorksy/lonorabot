# J2: How an agent run ends without the job done (loop endings)

Repository `/home/user/lonorabot` at `9f5b1da`, read-only. Database 2 (`audit_j2_test`). All `path:line`
citations are relative to the repo root and were re-opened before this file was finished.

## 0. What is real and what is scripted

- REAL: the API app, PostgreSQL, the Personal Agent row, the owner-message admission route, `execute_run`,
  the tool loop, the tool registry, dispatch, guardrails, runtime notices, run completion/failure, stream
  events, and (for the gold journeys) a real `MetaApiBroker` object over a FAKE SDK whose catalogue has
  `XAUUSDm` but not `XAUUSD` (`scripts/j1_lib.py`, same fake the J1 journeys use).
- SCRIPTED: only the model. Every "model turn" below that picks a tool call or writes text is SCRIPTED
  (`Recorder` in `scripts/j2_lib.py`). A scripted final reply is never evidence of what a real model would say.
  The evidence is the tool result, guard text, notice, event, committed chat message or error card the
  runtime produced.
- Scripts: `scripts/j2_lib.py` (harness), `scripts/j2_loop.py` (journeys L1..L9). Raw output: `runs/J2-L1.txt` ..
  `runs/J2-L9.txt`. (All under `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/`.)
- Rerun any journey:
  `cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 2 && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/j2_loop.py L1`
  (replace `L1` by `L2` .. `L9`).
- The harness uses `maximum_rounds=6` for L1 and L3 to keep output short. Production default is 24
  (`apps/api/src/lonora_api/env.py:97`, `packages/agent-runtime/src/lonora_agent/runtime.py:8`).
- Production tool list differs from the harness: the production trace offers 23 native tools without
  `market_symbols` and without `task_start`, with `web_search` (`production-trace.md`, lead's reading item 2).
  The harness agent was offered 24 native tools including `market_symbols` and `task_start`
  (`runs/J2-L9.txt`, "native tool names offered"). UNSURE: why the sets differ (production agent has
  scope_mode fixed_market; the harness agent comes from `ensure_personal_agent`). It does not change any loop
  mechanism below; where it matters (L9b) I used the `tool_call` bridge, which is offered in both lists.

### Honest scope statement (read first)

The production trace shows **none** of the loop endings reproduced here. The reply-producing runs ended after 1 to 5
rounds, with no guard halt and no limit (`production-trace.md:241`, `:266-275`). The only production run failures
were `model_not_configured` (`production-trace.md:16`). So the owner's complaint in the gold run
is not caused by the round limit or the repeat guards. These journeys document the *other* ways a run can end
unfinished, and each one is a way the same "I can't / it did not work" outcome reaches the owner. The main
production mechanism (the model writing a text reply and the runtime accepting it as final) is journey J2-8.

## 1. Summary table

| Id | Ending | What the owner sees | Language | Class |
|---|---|---|---|---|
| J2-1 | Round limit (24 rounds in production) | a model-written report if the wrap-up call works; otherwise a fixed generic Arabic line | model's, else Arabic | dead-end / recoverable-not-led |
| J2-2 | Same failing tool 8 times (even with 8 different arguments) or identical read 5 times | same as J2-1 | same | dead-end / recoverable-not-led |
| J2-3 | Empty model replies | same fixed line, which says "reached its limit" although the cause was empty replies | Arabic if owner wrote Arabic | bug (wrong reason) |
| J2-4 | Provider error / timeout / not configured / context overflow | an error card (web UI), no chat message; four different causes share one text | UI locale | bug / leak (misleading) |
| J2-5 | Unknown tool name, malformed arguments | nothing directly; the model gets thin codes | n/a | recoverable-not-led |
| J2-6 | Stop gate / rewrite of the final reply | Task: English or Arabic attention text in the Task thread; chat: a claim next to a money tool call is blanked | mixed | needed for safety (blanking); bug (Task language) |
| J2-7 | New owner message mid-run (steering) | works; the discarded read is repeated | n/a | works as designed; small waste |
| J2-8 | A text reply after one failed read is accepted as final | the model's text, untouched | model's | dead-end (the main production mechanism) |

---

## J2-1. The run reaches the tool-round limit

- Owner request (Arabic): «راجع كل محادثاتنا السابقة عن الذهب ولخّصها لي»
- Rerun: `... j2_loop.py L1`  Raw: `runs/J2-L1.txt`
- SCRIPTED turns: five `session_search` calls (queries "ذهب 1" .. "ذهب 5"); then a final turn.
  L1a: final = SCRIPTED text. L1b: final model call raises a provider TIMEOUT (SCRIPTED error).
- Runtime facts (REAL), with `maximum_rounds=6`:
  - After 5 executed rounds the runtime does not offer tools on the 6th turn: the last budgeted turn is a tool-less
    report (`packages/agent-runtime/src/lonora_agent/tool_loop.py:471-485`).
  - The model first receives a budget warning two rounds before the end (`tool_loop.py:486-488`,
    `packages/agent-runtime/src/lonora_agent/runtime_notices.py:102-114`).
  - The final request carries this notice, verbatim from `runs/J2-L1.txt`:
    `<runtime_notice>{"kind": "work_limit", "source": "lonora_runtime", "message": "This run reached its tool-round limit. No tool call will execute any more. Write the final reply to the owner now, in the owner's language: report only results verified by tool observations in this run; name every operation whose outcome is unresolved or unverified without calling it successful; and give the concrete next steps. Do not invent progress."}</runtime_notice>`
    and 0 native tools (`runs/J2-L1.txt`, "what SCRIPTED model turn 6 was sent: 0 native tools").
  - Run outcome L1a: `status: completed`, `exit_reason: tool_round_limit`, `reply_outcome: limited`, `rounds: 5`.
- What the owner sees:
  - L1a: whatever the model writes (SCRIPTED here).
  - L1b (the wrap-up call fails): the fixed line, committed as the assistant message:
    «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.»
    (Arabic unless the owner's last message has no Arabic letters and at least 8 Latin letters with a space; then the English twin: `runtime_notices.py:84-93`, `:132-139`).
- Root cause (path:line):
  - A provider error in the wrap-up call is swallowed and replaced by the fixed line: `tool_loop.py:273-279`
    (`reply, selection = ModelReply(), None`) then `tool_loop.py:284`
    (`text = reply.text.strip() or limit_fallback(prefers_arabic(messages))`).
  - The fixed line is `runtime_notices.py:132-139`. It says "ask me to continue" and offers nothing the agent could
    do next, and it says nothing about what was found.
  - A conversation run has exactly one slice of rounds. Only a Task run gets more slices
    (`packages/agent-runtime/src/lonora_agent/continuation.py:20` `MAXIMUM_SLICES = 4`,
    `tool_loop.py:411-416` schedules a continuation only for `reason == "tool_round_limit"` and a Task).
    So for the owner's chat, the limit is a hard stop; he must type again.
  - The wrap-up call is tool-less by design (`tool_loop.py:265-272`): the agent cannot take the one safe read it
    would need to finish. "Owner input buys a new budget" (`tool_loop.py:402-410`) only when he writes again.
- Class: dead-end for the run; recoverable-not-led for the owner (the fixed line asks him to restart the work himself).
- Needed for safety? The tool-less wrap-up is cost/safety control. The generic content of the fallback line is not.

## J2-2. The same failing call repeated until a guardrail blocks it

### J2-2a. Identical failing read, 8 times
- Owner request: «كم سعر الذهب الآن؟»  Raw: `runs/J2-L2.txt`  Rerun: `... j2_loop.py L2`
- SCRIPTED turns: `market_quote(account_id=<the account>, symbol="XAUUSD")` eight times, then a final text.
- Runtime results (REAL, verbatim, `account_id` shortened):
  1. `{"ok": false, "code": "broker_account_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`
  2. same plus `"runtime_notice": [{"kind": "tool_guardrail", "source": "lonora_runtime", "message": "market_quote has failed 2 times with identical arguments. Inspect the error and change strategy instead of retrying it unchanged."}]`
  3. same code, notice says 3 times.
  4. to 8.: `{"ok": false, "code": "tool_route_exhausted", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 4, ...}` with the same notice; the 8th notice reads `"market_quote failed 8 times in this run. Stop retrying this failing path."`
  - The broker was reached only 3 times: the log shows three `broker_rpc_failed code=broker_account_not_found ... message=Symbol not found` lines for the eight calls (`runs/J2-L2.txt:15-17`). Calls 4 to 8 were answered by the runtime without executing.
  - Then the run state holds the halt: `{"action": "halt", "code": "same_tool_failure_halt", "tool": "market_quote", "count": 8, ...}`, `exit_reason: guardrail_halt`, `reply_outcome: limited`, `rounds: 8`.
  - The wrap-up request carries: `"This run stopped a repeating tool loop: market_quote failed 8 times in this run. Stop retrying this failing path.. No tool call will execute any more. Write the final reply to the owner now, ..."` (note the doubled period; `runtime_notices.py:117-129`). 0 tools offered.
- Root cause (path:line):
  - After 3 identical failures the route is "blocked", even for a read: `packages/agent-runtime/src/lonora_agent/environment.py:127-131` (`record.get("failures", 0) >= 3`).
    Dispatch then answers without executing: `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:70-81`
    (`"code": "tool_route_exhausted"`, `"next_action": "alternate_route_or_wait"`).
  - The `recovery` block that reaches the model is overwritten by the generic classifier, so it says
    `terminal_domain_failure` / `alternate_route`: `environment.py:35-37` (default category) applied to the new code at `environment.py:203-209`.
    The model is told to use an alternate route but not which.
  - The first code, `broker_account_not_found` for a missing symbol, is the J1 MetaApi 404 mapping (another session fixes it).
  - The failure message 82-86 of `packages/agent-runtime/src/lonora_agent/tool_guardrails.py` ends with "or report the blocker": the guard itself names "report the blocker" as an acceptable move.
  - Halt threshold: `tool_guardrails.py:58` (`SAME_TOOL_FAILURE_HALT_AFTER = 8`), decision at `tool_guardrails.py:332-333`.
- Class: recoverable-not-led (the run ends at the exact point where one `market_symbols` read would have fixed it, see J2-8b) + leak (internal codes in what the model must paraphrase).

### J2-2b. Eight DIFFERENT guesses on the same tool still halt the run
- SCRIPTED: `market_quote` with `XAUUSD`, `GOLD`, `XAUUSD.a`, `XAUUSD.`, `XAU/USD`, `GOLDUSD`, `XAUUSD.pro`, `XAUUSD-ECN`.
- Results: each returns `broker_account_not_found` with `"attempt": 1`; the 8th carries the notice "market_quote failed 8 times in this run. Stop retrying this failing path." and the run halts (`exit_reason: guardrail_halt`, `rounds: 8`). The broker was reached 8 times (`runs/J2-L2.txt:341-348`).
- Root cause: the same-tool counter is keyed by tool name only (`tool_guardrails.py:329-333`, `per_tool[call.name]`), so a model that is correctly varying its guess is stopped as if it were repeating. The run ends without ever trying `market_symbols`.
- Class: recoverable-not-led. The cap is a cost bound ("needed for safety" as a bound); the choice to end the run rather than lead the model to a different tool is the gap.

### J2-2c. Identical successful read, 5 times
- SCRIPTED: `list_accounts` five times. Results: the 2nd to 4th results carry `"list_accounts returned the same result 2 times. Use the result already provided or change the request instead of repeating it unchanged."`, the 5th `"list_accounts was called 5 times in a row with identical arguments and an identical result."`; run halts, `code: identical_call_halt`, `exit_reason: guardrail_halt` (`runs/J2-L2.txt`, L2c).
- Root cause: `tool_guardrails.py:63-64` (`IDENTICAL_CALL_NOTICE_AFTER = 3`, `IDENTICAL_CALL_HALT_AFTER = 5`), `tool_guardrails.py:377-387`.
- Class: dead-end for the run; behaves as designed. This one is the least harmful.

## J2-3. Empty model replies

- Owner request: «كم سعر الذهب الآن؟»  Raw: `runs/J2-L3.txt`  Rerun: `... j2_loop.py L3`
- SCRIPTED: six empty `ModelReply()` turns (no text, no tools), `maximum_rounds=6`.
- Runtime facts (REAL): each empty turn is not committed. The runtime appends
  `<runtime_notice>{"kind": "no_answer", "source": "lonora_runtime", "message": "No answer was provided for the selected request. Provide the substantive result or ask a necessary clarification with wait_for_input. Do not invent results."}</runtime_notice>`
  and asks again. The round counter still goes up for every empty turn. After the budget notice and the "work_limit" notice, the final tool-less turn is also empty, and the fixed line is committed:
  «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.»
  Run outcome: `status: completed`, `exit_reason: tool_round_limit`, `reply_outcome: limited`, `rounds: 5`.
- Root cause:
  - `tool_loop.py:566` increments `rounds` before the empty check at `tool_loop.py:573-579`, so each empty reply spends a round (with the production limit, 23 empty replies before the limit).
  - The fixed line is used (`tool_loop.py:284`). It tells the owner the "run reached its limit", which is the effect, not the cause (empty replies from the provider).
  - The NO_ANSWER text is English-only runtime guidance (`runtime_notices.py:96-99`); it never reaches the owner. Fine.
- Class: bug (wrong reason shown) and dead-end. Not seen in production.
- UNSURE: whether any production provider returns empty content; no production run had it (`production-trace.md:241`).

## J2-4. Provider error / timeout / not configured

- Owner request: «كم سعر الذهب الآن؟»  Raw: `runs/J2-L4.txt`  Rerun: `... j2_loop.py L4`
- SCRIPTED provider errors (`ModelProviderError` from the fake model): L4a three TIMEOUT errors, one per worker claim; L4b AUTH; L4c CONTEXT_OVERFLOW on every attempt; L4d OVERLOADED after a successful `list_accounts`, then recovery.
- Runtime results (REAL):
  - L4a, pass 1: run goes back to `queued` with `environment.retry` `{"reason_code": "model_provider_retry", "code": "model_provider_unavailable", "attempt": 1}` and stream event `run.retry_scheduled` (`retry_at` 11 s later). Pass 2 schedules another (about 20 s). Pass 3: `status: failed`, `error_code: model_provider_unavailable`, `failure: {"family": "timeout", "retry_after_seconds": null}` and event `run.failed`. No assistant message was written to the chat (last chat message is still the owner's).
    The harness re-claims the run immediately and does not wait out the back-off; in production the worker waits `retry_at`.
  - L4b: `status: failed`, `error_code: model_credentials_rejected`, `failure: {"family": "model"}`. No retry.
  - L4c: three compaction retries (`input_scale` 0.7, 0.49, 0.343) then `status: failed`, `error_code: context_limit_exceeded`, `family: model`.
  - L4d: after the provider error the run is queued with the finished `list_accounts` result kept; pass 2 completes the run (`rounds: 2`). The tool is not repeated.
- What the owner sees: the web error card from `apps/web/src/conversation/Cards.tsx:72-82` (the Arabic strings are from `apps/web/src/i18n/locales/ar/messages.po`):
  - timeout (L4a): title «انتهت مهلة الرد», text «لم يصل الرد في الوقت المحدد، وقد يكون الاتصال ضعيفًا.», button «إعادة المحاولة».
  - model family (L4b AUTH, L4c context overflow, and every code starting `model_`, including `model_not_configured`): title «النموذج غير متاح حاليًا», text «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.», buttons «تغيير النموذج» and «إعادة المحاولة».
  - The specific per-code texts (`apps/web/src/lib/user_error.ts:88-105`, e.g. "The provider rejected this API key.") are only used for the family `other` (`Cards.tsx:82`).
  - Language follows the UI locale catalogue, not the owner's message language. UNSURE: mobile client (`apps/mobile`) was not checked.
- Root cause (path:line):
  - Conversation back-off profile is short: 10 s base, 60 s cap, escalate at the 3rd failure (`packages/agent-runtime/src/lonora_agent/model_recovery.py:59`, `:187-194`). Non-transient reasons raise at once (`model_recovery.py:174-175`).
  - Family mapping: any code starting `model_` and `context_limit_exceeded` become family "model" (`packages/core/src/lonora_core/runtime_failure.py:36`, `:50`). So `model_not_configured` (the production cause of «النموذج غير متاح», `production-trace.md:16`) shows the text "could not be reached", which is false for that cause. The Arabic/English card lines are the same for four different causes.
  - The failure leaves no chat message (events: `run.failed` only), so the owner's message simply has no answer until he sees the card.
- Class: leak/bug (misleading text) for the shared "model" card; owner-needed for AUTH and not-configured (only he can fix the key or routing; the card does say "تغيير النموذج"); recoverable for L4a/L4d (auto retry works as designed).
- Needed for safety? No part of this is money-related. Not repeating executed tools after a provider error (L4d) is needed for safety and works.

## J2-5. Unknown tool name and malformed arguments

- Owner request: «كم سعر الذهب الآن؟»  Raw: `runs/J2-L5.txt`  Rerun: `... j2_loop.py L5`
- SCRIPTED calls and REAL results (verbatim, trimmed):
  1. Unknown tool `market_symbol_search {"query":"gold"}` ->
     `{"ok": false, "code": "tool_not_allowed", "recovery": {"category": "permission_denied", "next_action": "respect_scope", "safe_to_retry": false, "schema_tool": "tool_environment", ...}}`
  2. `market_quote {"symbol":"XAUUSD"}` ->
     `{"ok": false, "code": "tool_arguments_invalid", "issues": [{"path": ["account_id"], "type": "missing"}], "retryable": true, "recovery": {"category": "invalid_tool_arguments", "next_action": "inspect_schema_and_repair", ...}}`
  3. wrong types plus an extra field -> `"issues": [{"path": ["account_id"], "type": "string_type"}, {"path": ["symbol"], "type": "string_type"}, {"path": ["depth"], "type": "extra_forbidden"}]`
  4. well-formed but invented account id -> `{"ok": false, "code": "broker_sessions_not_found", ...}` plus the 3rd-failure warning "Diagnose the latest error before another attempt: correct the arguments, use a narrower request or a genuinely different source, or report the blocker."
  5. Bridge with unknown target `tool_call {"name":"market_symbol_search", ...}` -> `{"ok": false, "code": "tool_call_target_unknown", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", ...}}`
  6. Bridge target with arguments omitted -> `tool_arguments_invalid`, `account_id` missing.
  7. Bridge target with arguments as broken JSON text `"{\"account_id\": "` -> `{"ok": false, "code": "tool_arguments_invalid", "issues": [{"path": ["arguments"], "type": "dict_type"}], "retryable": true, ...}`
  Also L8: `trade_execute {"action": "open", ...}` -> `issues: [{"path": ["action"], "type": "literal_error"}]` (no list of allowed values).
- What the owner sees: nothing from these calls directly; the model sees the results. The run is not ended by them.
- Root cause (path:line):
  - A tool name that is not in the registry is reported as a permission problem: `packages/tools/src/lonora_tools/registry.py:479-480` (`raise LonoraError("tool_not_allowed", 403)`), and the classifier maps that code to `permission_denied` / `respect_scope` (`environment.py:56-69`, `tool_not_allowed` at `:57`). "Respect scope" reads as "stop", though the real cause is a wrong name. (The bridge path has its own code, `registry.py:222`, but it gets the default `terminal_domain_failure`/`alternate_route` from `environment.py:35-37`.)
  - Argument errors give path and Pydantic type only (`tool_dispatch.py:113-117`, `packages/tools/src/lonora_tools/schema.py:50`, `:69`): no expected type, no allowed values, no example. The recovery says `schema_tool: tool_environment`, so the model must make another call to learn the shape.
  - Not-found codes carry no candidates (`environment.py:80-81`).
- Class: recoverable-not-led (the model can recover only by guessing the next tool). Another session owns the resolution error contract; this journey records the other error kinds the same contract should cover.

## J2-6. Stop gates and rewrites of the final reply

### J2-6a. Task stop gate (continuous and finite)
- Request: the owner asks the SCRIPTED model to start a task («تابع الذهب وأخبرني»); the SCRIPTED model calls `task_start`; the Task run then answers in prose. Raw: `runs/J2-L6.txt`  Rerun: `... j2_loop.py L6`
- Continuous Task, SCRIPTED prose answers "سأواصل مراقبة الذهب." three times. Runtime injected twice (REAL, verbatim):
  `<runtime_notice>{"kind": "completion_check", ... "message": "This responsibility is continuous. A text answer does not complete it or save monitoring. Continue useful authorized work, or use task_wait with a real owned watch, verified broker-recovery source, or a deliberate review timer. Discover the capability through tool_environment if needed. ..."}`
  After two nudges the run becomes `waiting_input` with an owner-attention message in the Task's work thread:
  «هذه المهمة المستمرة غير مراقَبة: لم يُحفظ أي انتظار مراقبة أو مؤقت مراجعة، لذلك لن تحدث أي متابعة تلقائية. أحتاج توجيهك قبل المتابعة: ردّ هنا، أو عدّل المهمة أو استأنفها أو أوقفها مؤقتًا أو ألغها.»
  followed by «آخر تقرير: SCRIPTED prose answer 3: ...». The owner's chat thread got only the SCRIPTED "started." reply.
- Finite Task with two declared steps, SCRIPTED prose "ما قدرت أقرأ الذهب." three times: same two nudges ("This task is not complete: these declared steps are not completed yet: read: Read the gold price; report: Report to the owner. ..."), then the attention message **in English**:
  "This task is not finished. Steps not completed yet: Read the gold price; Report to the owner. I need your direction before continuing: reply here, or revise, resume, pause or cancel the task."
- Root cause:
  - Two nudges maximum: `packages/agent-runtime/src/lonora_agent/stop_gates.py:41` and `:126-127`; continuous branch `:99-100`.
  - The gate exists only for Task runs: `stop_gates.py:178-181` (`progress is None` -> `continue_turn=False`). A chat run has no stop gate (see J2-8).
  - The attention text language comes from `prefers_arabic(messages)` (`runtime_notices.py:84-93`): the last owner-origin message in the Task run decides. In the finite case it chose English although the Task title was Arabic (observed in `runs/J2-L6.txt`). UNSURE which message it read; I did not dump the Task run's user messages.
  - The attention message and its question land in the Task thread, not the chat thread (`runs/J2-L6.txt`, "last messages in the Task work thread" versus "owner chat thread").
- Class: dead-end that asks the owner (owner-needed), with a language bug in one branch.

### J2-6b. A claim text next to a money tool call is blanked
- Owner request: «اشترِ ذهب»  Raw: `runs/J2-L8.txt`  Rerun: `... j2_loop.py L8`
- SCRIPTED turn: `trade_execute` (with invalid arguments, so nothing can execute) and the text «تم فتح الصفقة بنجاح وأنا أراقبها الآن.»
- Runtime result: the stored assistant message has content `""` (the text is gone); the tool result is `tool_arguments_invalid` (`issues: [{"path": ["action"], "type": "literal_error"}]`). The owner never sees the claim.
- Root cause: `packages/agent-runtime/src/lonora_agent/model_runtime.py:225-228` (`if proposed & FINANCIAL_CALLS: ... "text": ""`). Related replacements: `model_runtime.py:229-231` (reply replaced by the fixed text of `packages/agent-runtime/src/lonora_agent/context/financial_result.py:121-125` when a broker result is confirmed but not independently verified: «أقرّ الوسيط بالطلب، لكن التحقق المستقل من نتيجته لم يكتمل بعد. لن أكرر الإرسال.»).
- Class: **needed for safety**. These rewrites key off structured financial tool results and proposed financial calls only. Nothing rewrites a claim about a watch, a cancellation or a read (cross-reference `trace-guards.md`, section 0).

## J2-7. A new owner message arrives mid-run (steering)

- Raw: `runs/J2-L7.txt`  Rerun: `... j2_loop.py L7`
- L7a: «كم سعر الذهب الآن؟»; while the SCRIPTED model "thinks" it proposes `market_quote(XAUUSD)`; the owner's «ضع حرف m يعني XAUUSDM» arrives through the real admission route (its message seq is 66 and the response returns the already running run, whose `input_seq` is 65: no new run).
  - Result (REAL): the proposed read is dropped: `{"ok": false, "code": "tool_call_superseded"}` and the stream shows `tool.cancelled`. The next model turn sees the new owner message as the last user message. The run completes with the SCRIPTED final text.
- L7b: owner writes «وبالمرة الفضة» while the model drafts a final answer. The runtime does not commit the draft: two `run.reply_started` events, one `run.reply_committed`; the chat shows only the second reply.
- Root cause (path:line): `tool_loop.py:443-445` (steering before the next call), `tool_loop.py:460` (merge between block and model turn), `tool_loop.py:592-594` (a message arriving after the draft forces a new draft), `packages/agent-runtime/src/lonora_agent/tool_intent.py:26` (code `tool_call_superseded`).
- Assessment: works as designed. The only cost: a harmless read (the gold quote) is thrown away and must be asked again, and the model sees the code `tool_call_superseded` in a tool result. UNSURE whether a real model reliably re-issues it; I only scripted it.
- Class: not a failure (small waste).

## J2-8. The main production mechanism: a text reply after one failed read is final

- Owner request: «شو وضع الذهب» (the gold run of the owner's chat). Raw: `runs/J2-L9.txt`  Rerun: `... j2_loop.py L9`
- J2-8a. SCRIPTED turns: (1) `market_quote(XAUUSD)`; (2) a text reply that is the owner's verbatim message [10], including «symbol_not_found» and «أبحث لك عن اسم الذهب الصحيح على هذا الحساب إذا أردت». This text is SCRIPTED, copied from the owner's chat, to test what the runtime does with it.
  - Tool result (REAL): `{"ok": false, "code": "broker_account_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`
  - Runtime reaction: nothing. No repair prompt, no nudge, no second chance. Run `status: completed`, `reply_outcome: answered`, `rounds: 2`; the reply is committed byte for byte, including the raw `**symbol_not_found**`.
- J2-8b. SCRIPTED turns: (1) the same failing `market_quote(XAUUSD)`; (2) `tool_call(name="market_symbols", arguments={account_id})`; (3) `market_quote(XAUUSDm)`; (4) SCRIPTED final.
  - Results (REAL): `market_symbols` -> `{"ok": true, "symbols": ["BTCUSDm", "EURUSDm", "USOILm", "XAGUSDm", "XAUUSDm"]}`; `market_quote(XAUUSDm)` -> `{"ok": true, "symbol": "XAUUSDm", "bid": "4049.73", "ask": "4049.97", ...}` (fake SDK price).
  - Meaning: the safe read-only next step the owner was offered («أبحث لك…») exists in the current tool set and works. The model only has to take it. Nothing in the runtime leads it there.
- Root cause (path:line):
  - Any non-empty text without tool calls goes to `final_answer` (`tool_loop.py:595`), where the only gate is the Task gate (`stop_gates.py:178-181`), which returns "stop" for a chat run. So "I can't, shall I search?" is accepted.
  - The recovery block shows `next_action: inspect_existing_state` for every `*_not_found` code (`environment.py:80-81`); it names no tool (`market_symbols`) and no candidate.
  - The runtime's end-of-run text rules (financial truth, privacy redaction) do not inspect the reply for offers, "I cannot" or leaked codes (`model_runtime.py:220-262`; see `trace-guards.md` section 0, which reaches the same conclusion from the production trace).
- Class: dead-end, and recoverable-not-led (the tool result gives no lead; the reply is accepted). It is also a leak: code names inside the committed reply are not filtered.
- Needed for safety? No. This path is read-only.

---

## 2. Cross-cutting findings (all in the area "agent loop endings")

1. The loop ends a conversation run whenever the model returns non-empty text. Only Task runs have a completion gate (`stop_gates.py:178-181`; J2-6a vs J2-8a). This is the ending that matches the owner's complaint; the production runs ended this way after 1 to 5 rounds.
2. Every hard ending (round limit, repeat halt, empty replies, failing wrap-up) ends in the same fixed line when the wrap-up model call returns nothing (`runtime_notices.py:132-139`). It states the cause as "this run reached its limit", for causes that are not that (J2-3), and it leads nowhere (J2-1).
3. The repeat guards count by tool name (`tool_guardrails.py:329-333`) and block identical reads at 3 failures (`environment.py:129`). Neither tells the model which tool to switch to; the warning text even lists "report the blocker" as an option (`tool_guardrails.py:82-86`). (J2-2)
4. After a halt the model has no tools (wrap-up call: `tool_loop.py:265-272`), so it cannot take the recovery step itself; the owner must send another message.
5. Error and recovery codes: unknown tool names look like permission errors (`registry.py:479-480` with `environment.py:56-69`); argument errors carry no schema; not-found carries no candidates. (J2-5)
6. The failure card for provider problems is one text for four causes, including «النموذج غير متاح» for `model_not_configured`, which is false (`runtime_failure.py:50`, `Cards.tsx:81`). (J2-4)
7. Rewrites of the final reply exist only for money (blank a claim beside a financial call; replace a confirmed-but-unverified result). Needed for safety, and it works (J2-6b).
8. Steering is solid (J2-7).

## 3. Where a doc and the code disagree

I found none in this area. I did not re-verify the pre-existing mapping notes in `docs/research/` against the trace beyond the figures cited here.

## 4. What I could not reproduce or confirm

- Round limit, repeat halts and empty replies did not occur in production; they are reproduced only with SCRIPTED models.
- The model's own behaviour after a halt is not testable here (the model is scripted).
- Mobile client rendering of the error card (not checked).
- Which owner-origin message the Task-run language heuristic read in J2-6a (finite case).
- Why the harness agent's native tool list differs from production (see section 0).
- The repository working tree was clean (`git status --short` empty) after the runs. An untracked `docs/research/` directory appeared and disappeared during the session; it is not from these scripts.
