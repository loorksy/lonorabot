## Axis 1. The agent loop

Repository at `9f5b1da`; the runtime is `packages/agent-runtime/src/lonora_agent/`. Production facts cite the trace by part.

### 1. One run, message or wake to final reply

1. **Admission.** A paused agent gets no Run (`packages/db/src/lonora_db/messages.py:514-515`). A live conversational or question-waiting Run takes the message as a steering row (`packages/db/src/lonora_db/messages.py:533-536`); otherwise a new Run (`packages/db/src/lonora_db/messages.py:576-580`).
2. **Claim and shell.** `dispatch_one` calls `runtime.execute` (`packages/gateway/src/lonora_gateway/run_dispatch.py:92`), looping the pass until the run waits or `complete_run` succeeds (`packages/agent-runtime/src/lonora_agent/executor.py:142-254`); `complete_run` refuses if unread steering exists (`packages/db/src/lonora_db/runs.py:364-370`).
3. **One pass** (`packages/agent-runtime/src/lonora_agent/tool_loop.py:394-611`): limit/halt boundary (`:399-438`) → first pending tool segment (`:441-454`) → merge steering (`:460-465`) → model turn (`:504-516`) → empty chat turn gets `NO_ANSWER` and loops (`:573-579`) → tool calls present: loop (`:590-591`); none but steering pending: loop (`:592-594`); else `final_answer` (`:595-611`).
4. **Final.** `final_answer` applies Task gates and the uncertain-outcome line (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:155-184`); `complete_run` writes a message only if there is content, never for trigger `tickets` (`packages/db/src/lonora_db/runs.py:379`).

### 2. Limits, stops, turn end versus continue

| Limit | Value | Where |
| --- | --- | --- |
| Model rounds per run | **24** (allowed 1-100) | `apps/api/src/lonora_api/env.py:97` |
| Tool-offering turns, chat | **23**; turn 24 is a tool-less final report | `packages/agent-runtime/src/lonora_agent/tool_loop.py:471-488` |
| Task slices | 4 x 24 = **96** rounds; owner input at a limit gives a new budget | `packages/agent-runtime/src/lonora_agent/continuation.py:20`; `packages/agent-runtime/src/lonora_agent/tool_loop.py:402-410` |
| Tool deadlines | 45 s read, 90 s mutation, none financial | `packages/tools/src/lonora_tools/base.py:15-16` |
| Same route failing; transient read | route blocked from the 4th attempt; read re-queued after failures 1 and 2, returned on 3 | `packages/agent-runtime/src/lonora_agent/environment.py:129`, `:206-224` |

After the limit: tool-less final report (R10), or R11 if that fails; the run completes `limited`; the owner must send a message to continue.

A turn with tool calls always continues. A pass ends when: a turn has no calls and, for Task runs only, the gates allow (`packages/agent-runtime/src/lonora_agent/tool_loop.py:595-611`); rounds hit the limit or a guardrail halts, unless owner input or a Task slice intervenes (`packages/agent-runtime/src/lonora_agent/tool_loop.py:400-416`); a tool asks for an owner question, trade approval, external wait or `group_silence` (`packages/agent-runtime/src/lonora_agent/tool_block.py:335-412`); a retry is scheduled; or an exception.

**Tools and steering.** Tools are serial; adjacent read-only, non-financial, `parallel_safe` calls run in parallel (semaphore 4), one segment per iteration (`packages/agent-runtime/src/lonora_agent/tool_batch.py:58-120`). A new owner message is noticed only at boundaries and never interrupts a running model request or tool; unexecuted calls get `{"ok": false, "code": "tool_call_superseded"}` (`packages/agent-runtime/src/lonora_agent/tool_intent.py:21-53`), a possibly-started effect gets `tool_execution_uncertain`.

### 3. Guards (SAFETY = money/privacy rule; RELIABILITY = bounds cost/loops; MIXED = mechanism needed, wording over-steers)

**Reply guards**

| # | Effect and exact text | Where | Class |
| --- | --- | --- | --- |
| R2 | Unverified financial result: reply replaced by «أقرّ الوسيط بالطلب، لكن التحقق المستقل من نتيجته لم يكتمل بعد. لن أكرر الإرسال.»; appended «نتيجة العملية غير مؤكدة بعد؛ أتحقق منها ولن أعيد إرسالها.» | `packages/agent-runtime/src/lonora_agent/context/financial_result.py:121-125`; `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:36-37` | SAFETY |
| R5 | Privacy redaction only ("Public capability names and ordinary diagnostic vocabulary are not credentials."); no filter removes internal codes | `packages/core/src/lonora_core/public_reply.py:3-4`, `:54-67` | SAFETY |
| R8 | Effect-claim pattern covers execute/open/close/send/activate/buy/sell/approve, not «تم الإلغاء» / «أُزيلت»; no guard compares a claimed effect with tool results | `packages/agent-runtime/src/lonora_agent/public_stream.py:16-17` | SAFETY (delay only) |
| R9 | Empty chat reply: `"No answer was provided for the selected request. Provide the substantive result or ask a necessary clarification with wait_for_input. Do not invent results."` Repeats each round to the limit | `packages/agent-runtime/src/lonora_agent/runtime_notices.py:96-99` | MIXED |
| R10 | `"This run reached its tool-round limit."` or `"This run stopped a repeating tool loop: <detail>."` + `" No tool call will execute any more. Write the final reply to the owner now, in the owner's language: report only results verified by tool observations in this run; name every operation whose outcome is unresolved or unverified without calling it successful; and give the concrete next steps. Do not invent progress."` `<detail>` is the guardrail's English sentence with the raw tool name | `packages/agent-runtime/src/lonora_agent/runtime_notices.py:117-129` | RELIABILITY + SAFETY |
| R11 | Fallback if the report call fails or is empty: «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.» (internal word «الجولة») | `packages/agent-runtime/src/lonora_agent/runtime_notices.py:132-139` | RELIABILITY |

**Loop guardrails** (texts `packages/agent-runtime/src/lonora_agent/tool_guardrails.py:78-130`). A block returns `"code": "guardrail_blocked"` (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:302-310`); a halt ends the loop via R10; owner input or a wake resets all.
- Other texts (identical failure, no-progress, identical call, cycle): RELIABILITY.
- **G2** MIXED, at the 3rd failure of one tool with any arguments (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:336-337`): "{tool} has failed {count} times in this run. Diagnose the latest error before another attempt: correct the arguments, use a narrower request or a genuinely different source, or report the blocker."
- **G3** MIXED: "{tool} failed {count} times in this run. Stop retrying this failing path." Halts the run at 8 failures of one tool even with different arguments (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:330-333`).
- **G10/G11** SAFETY: "{tool} has now run {count} times in a row with identical arguments. Each call is a separate effect, not a retry: check the earlier results and do not repeat it unless another identical effect is really intended."; the block adds "Use the earlier results, change the request, or report to the owner." `trade_close_positions` is counted (`packages/tools/src/lonora_tools/trade.py:780`): a sixth identical close in a row is blocked.

**Other tool-call blocks**
- **T1** OVER-CAUTION by omission: any tool error becomes bare `{"ok": False, "code": error.code}`; handler knowledge is discarded (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:110-117`).
- **T2** MIXED: `*_not_found` gets `not_found` / `inspect_existing_state`; the named `schema_tool` is the catalogue tool, not a lookup (`packages/agent-runtime/src/lonora_agent/environment.py:80-81`).
- **T3** MIXED: 3 identical failures give `tool_route_exhausted`, `next_action: "alternate_route_or_wait"` (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:70-81`).
- **T14** MIXED: `group_silence` in direct chat returns `reply_required`: "You were selected to answer this request. Give the substantive answer, or use wait_for_input for a necessary clarification. Do not stay silent." (`packages/tools/src/lonora_tools/runtime_control.py:107-118`).

**Task stop gates (Task runs only).** S1, continuous Task answered in prose with no saved wait, max 2 nudges: "This responsibility is continuous. A text answer does not complete it or save monitoring. ... Do not invent activity, ask routine trading questions, or poll the model continuously. ..." (`packages/agent-runtime/src/lonora_agent/stop_gates.py:45-54`; RELIABILITY, pushes toward acting). **Chat runs have no gate**: `task_stop_gate` returns stop with no Task (`packages/agent-runtime/src/lonora_agent/stop_gates.py:179-181`). The manual says "make a bounded meaningful correction or use a genuinely supported alternative source" (`packages/agent-runtime/resources/system/lonora.md:160`); nothing in the loop checks it.

### 4. Every way a run ends without the job done

Error card family: `packages/core/src/lonora_core/runtime_failure.py:39-52`; Arabic from `apps/web/src/i18n/locales/ar/messages.po`.

1. **Model gives up or asks in prose.** No calls, accepted as final, `reply_outcome: "answered"` (`packages/agent-runtime/src/lonora_agent/tool_loop.py:590-611`). Owner sees the model's text, including copied codes. Production, run 1ae9a14c (gold): `market_snapshot` → `symbol_not_found`, `market_instrument` → `broker_account_not_found`, both with `{"category":"not_found","next_action":"inspect_existing_state","safe_to_retry":false,"schema_tool":"tool_environment","attempt":1,"retry_exhausted":false}` and no candidates (trace Part 4, #15, #17), then a final text. `market_symbols` was not among the 23 native tools (trace Part 1), though `market_instrument` says to use "ONE exact broker symbol from market_symbols" (`packages/tools/src/lonora_tools/market.py:108`). Run e09ad476 likewise asked in prose with no call (trace Part 1).
2. **Round limit or guardrail halt, chat.** Model's R10 report or R11; `reply_outcome: "limited"` (`packages/agent-runtime/src/lonora_agent/tool_loop.py:314-322`).
3. **Empty replies until the limit** (R9): ends as 2.
4. **Silent completion:** non-conversational trigger, empty turn: no message (`packages/db/src/lonora_db/runs.py:379`). 5. **Reply replaced by a fixed financial sentence** (R2), SAFETY.
6. **Task stop gate exhausted, Task limit or halt.** Owner sees «أحتاج توجيهك قبل المتابعة: ردّ هنا، أو عدّل المهمة أو استأنفها أو أوقفها مؤقتًا أو ألغها.» after the runtime sentence, then «آخر تقرير: » + held answer (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:172-203`); sentences: «هذه المهمة لم تكتمل بعد.», «توقفت هذه المهمة قبل اكتمالها لأن هذه الجولة بلغت حدّ العمل، ولم يُنفَّذ أي إجراء بعد ذلك.» (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:143-157`).
7. **Model calls `wait_for_input`:** the question is posted and the run waits; the loop never checks whether a read could answer it (`packages/agent-runtime/src/lonora_agent/tool_block.py:370-375`). Production: both question cards were the model's own; the run then continued without acting (lead's trace reading, item 15).
8. **Intended or quiet stops:** trade approval card (SAFETY); `task_wait`; Task paused or cancelled; agent paused, no Run; owner stop shows «أوقفتَ الرد» (`apps/web/src/conversation/Message.tsx:423-425`).
9. **Re-queued, owner waits:** transient provider or read failure (`packages/agent-runtime/src/lonora_agent/tool_loop.py:528-552`).
10. **Chat model failure streak (3rd):** the Run fails (`packages/agent-runtime/src/lonora_agent/executor.py:310-312`). Owner sees «النموذج غير متاح حاليًا» + «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.» (`ar/messages.po:7331-7336`), with Retry.
11. **Non-transient provider failure** raises at once (`packages/providers/src/lonora_providers/resilience.py:75-97`). Production «النموذج غير متاح»: all five failed runs were `model_not_configured` (trace Part 1), family `model` by prefix (`packages/core/src/lonora_core/runtime_failure.py:50-51`), so the card claimed the provider was unreachable, untrue for that cause. The accurate string (`apps/web/src/lib/user_error.ts:88-89`) is used only for family `other` (`apps/web/src/conversation/Cards.tsx:82`). Unfixable context overflow gets the same card (`packages/core/src/lonora_core/runtime_failure.py:36`).
12. **Internal state errors, `runtime_error`, crash loop** `run_recovery_limit` after 5 recoveries (`packages/db/src/lonora_db/runs.py:547-558`), and withdrawn skill authority: owner sees «تعذّر على الوكيل الرد» + «تعذر إكمال الطلب. أعد المحاولة.» (`ar/messages.po:7099-7100`, `:7416-7417`) with no Retry button (`apps/web/src/conversation/Cards.tsx:96`).

**Why no check fired in production.** All 41 runs are trigger `user` (trace Part 1), so no gate applied (`packages/agent-runtime/src/lonora_agent/stop_gates.py:153-155`). ddae66ad made three `watch_create` calls, all `ok`, then said «تم الإلغاء»: `effect_streak` 2 is only the G10 warn threshold (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:68`), `halt: null`, and nothing compares the claim with tool results (R8). e343c96a (only `wait_for_input`, then prose) and fb1d4b5a (no call) are ending 1.

### 5. Doc versus code

| Doc | Code | Verdict |
| --- | --- | --- |
| Overflow "tightens admission and compacts before one bounded retry" (`docs/tool-execution-runtime.md:361-362`) | up to three retries (`packages/agent-runtime/src/lonora_agent/model_recovery.py:43`) | Code wins |
| Identical read "block at 5, halt after 2 ignored blocks" (`docs/tool-execution-runtime.md:238`) | one block, then halt (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:294-298`) | Code wins |
| Policy "no narration of internal cards, tools, skills, runs, events or API plumbing" (`docs/agent-operating-policy.md:69-71`) | prompt only (`packages/core/src/lonora_core/public_reply.py:54-67`) | Not enforced |
