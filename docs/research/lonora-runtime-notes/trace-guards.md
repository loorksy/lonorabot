# Why the reply guards let false claims through

Scope: repository `/home/user/lonorabot` at main `9f5b1da`, read-only. Production facts come from
`production-trace.md` (UTC). All `path:line` references are relative to the repository root and
were re-opened before this file was finished. Reproductions use the real runtime with SCRIPTED
model turns (labelled) on audit database 7.

Checked: this file was verified by a second, independent pass (every citation opened, every
script rerun). What that pass changed is listed in "Verification log" at the end; text it added
is marked "(checker)". `production-trace.md` Part 4 (tool calls and results of seven runs) was
used to settle most of the earlier "TRACE BODIES MUST CONFIRM" items.

Build note (checker): the production runs discussed here ran on three builds (2477c22 up to
09:54:14 UTC, cd2cc91 up to 10:23, 9f5b1da from 10:38:12). `git diff --stat cd2cc91 9f5b1da --
packages/agent-runtime packages/tools packages/core/src/lonora_core/public_reply.py
packages/db/src/lonora_db/messages.py` is empty, and `git diff 2477c22 9f5b1da` over the same
paths touches none of the guard modules cited below (`uncertain_outcome.py`, `stop_gates.py`,
`loop_outcomes.py`, `tool_loop.py`, `tool_block.py`, `tool_guardrails.py`, `public_stream.py`,
`context/financial_result.py`, the constitution files); in `model_runtime.py` it only adds the
card-capabilities system message now at
`packages/agent-runtime/src/lonora_agent/model_runtime.py:81-90`, and in `market_watch.py` only
the three `taint_row_from` lines (`packages/tools/src/lonora_tools/market_watch.py:144`). So the line-by-line reading of main
below applies to every run of 2026-11-11, not only to the runs after 10:38:12.

## 0. Headline

**PR #42 contains no guard that reads the reply.** Nothing on main compares what the agent
*says* in its reply text ("done", "I will", "I am watching", "I have no tool") with what the run
*did*. (Checker: the one place where displayed wording is tested against evidence is the
generated-card compiler, section 6.3; it reads cards only, and every assistant row of this
thread has `rich_content` null, `production-trace.md` Part 3, so it was never in play.) The
hypothesis in the assignment ("any successful side-effecting tool result satisfies the
effect-claim guard") is wrong in its premise: there is no effect-claim guard to satisfy. A reply
with three unrelated `watch_create` results and a reply with zero tool calls take exactly the
same path and both are committed byte for byte.

What PR #42 (merge `aa50e8e`) actually added, complete list from `git show aa50e8e --stat`:

| Piece | What it is | Where |
|---|---|---|
| Uncertain-outcome line | One fixed sentence appended to the final reply when a **financial** tool result of this request is still uncertain. Reads structured results only. | `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:1-9`, wired at `loop_outcomes.py:179-183`, `tool_loop.py:299`, `tool_loop.py:608`, `loop_restore.py:58` |
| One constitution paragraph | Prompt text only (see section 6.2). | `packages/agent-runtime/resources/constitution/trading-policy.md:7` |
| One constitution sentence about code deliverables | Prompt text only. | `packages/agent-runtime/resources/constitution/identity.md:1` |
| Guidance strings inside three tool results/descriptions | `model_list` "next", `wait_for_input` "guidance", `memory_write` description word "limits". | `packages/tools/src/lonora_tools/models.py:179-182`, `runtime_control.py:69-72`, `memory.py:282` |
| Tests | 12 test functions (21 collected cases with parametrisation), all about the uncertain line. | `tests/test_uncertain_outcome.py` |

(Checker: the merge commit's own title is "Agent behaviour: uncertain-outcome line and
owner-control routing (G0 baseline)", `git show aa50e8e`; the stat lists exactly the ten files
above.)

The module says so itself: "Structured results only: no wording of the owner or the model is
read." (`uncertain_outcome.py:3`). Two of its own tests pin the behaviour seen in production:

- `tests/test_uncertain_outcome.py:280-288` (`test_a_question_reply_without_financial_calls_is_untouched`):
  a SCRIPTED reply «تم.» with no tool call at all must be stored unchanged.
- `tests/test_uncertain_outcome.py:138-140` (`test_other_tools_and_earlier_requests_are_not_read`):
  a `watch_create` result is never read, even with `status: ambiguous`.

## 1. Everything a final reply passes through on main (in order)

This is the full list for an owner conversation run (`trigger=user`, no Task). Each production
run in section 2 is judged against it.

**A. Inside `model_turn` (per model reply), `packages/agent-runtime/src/lonora_agent/model_runtime.py`**

1. Incremental streaming admission, `PublicStream.offer` (`public_stream.py:33-65`). It stops
   *incremental* publication when `EFFECT_CLAIM` matches or a privacy pattern matches
   (`public_stream.py:47-51`). It does not block the reply: the full text is still published at
   the end (`model_runtime.py:282-291`). File docstring: "Incremental privacy admission; effect
   claims remain final-only." (`public_stream.py:1`).
   - (checker) Before the gates, a trailing `<suggested_reply>` tag is cut out of the text
     (`model_runtime.py:195-201`, `suggested_reply.py:31-43`). Formatting only; no claim check.
2. Financial-truth gates, all keyed on tool names in `FINANCIAL_CALLS = {"trade_execute",
   "trade_close_positions", "goal_step_execute"}` (`context/financial_result.py:9`):
   - the reply proposes a financial call → reply text is blanked (`model_runtime.py:225-228`);
   - a financial result of this request is `confirmed` but not `verified` → text replaced by a
     fixed sentence (`model_runtime.py:229-232`, sentence at `context/financial_result.py:122-124`);
   - the reply proposes `task_wait` after an unsettled financial result → text replaced
     (`model_runtime.py:233-238`, `context/financial_result.py:129`).
   - (checker) All three look only at financial results that come after the latest owner
     message (`context/financial_result.py:79-82`, `context/financial_result.py:156-159`), so
     the `trade_execute` of run 65e8b682 could not influence any later run either.
   - (checker) Between the gates and redaction the text goes through the visual projector
     (`model_runtime.py:243-244`), which compiles a generated card if the reply contains one.
     The card compiler has its own checks (section 6.3). A reply without a card block is not
     judged there.
3. Privacy redaction `redact_private_reply` (`model_runtime.py:246`;
   `packages/core/src/lonora_core/public_reply.py:54-67`): credentials, private paths/tags and
   UUIDs only (`public_reply.py:10-25`). Tool names and internal words are explicitly allowed:
   "registry names are intentionally not private" (`public_reply.py:40-41`); "Presentation is
   owned by the model's instructions, not a keyword veto on replies." (`public_reply.py:4`).
   The runtime states the policy at `model_runtime.py:239-241`: "Style is model guidance, never
   a second generation or a failed user request."

**B. Inside the loop, after a reply with no tool calls** (`tool_loop.py:588-611`)

4. `final_answer` (`loop_outcomes.py:155-184`):
   - `task_stop_gate` (`loop_outcomes.py:170`, `stop_gates.py:178-184`). It first loads the
     run's Task: `identifier = run.model_metadata.get("task_id")`; `if not identifier: return
     None` (`stop_gates.py:153-155`); and `if progress is None: return
     StopGateVerdict(continue_turn=False)` (`stop_gates.py:180-181`). A chat run has no
     `task_id`, so the gate never continues the turn and never escalates.
   - `append_uncertain_line` (`loop_outcomes.py:179-183`), section 6.1.
   - `return LoopOutcome(text, metadata)` (`loop_outcomes.py:184`): the model's text, unchanged.
5. An empty reply (no text, no card, no calls) gets the `NO_ANSWER` notice and another turn
   (`tool_loop.py:573-579`; conversational triggers only, `tool_loop.py:574`,
   `packages/core/src/lonora_core/run_state.py:33-34`). Any non-empty text ends the run.

**C. Around tool calls**

6. Tool-loop guardrails (`tool_guardrails.py`): repetition only (identical arguments/results,
   failure streaks, cycles). They never look at the reply and never judge whether a call fits
   the request.

**D. After the loop (checker)**

7. `complete_run` (`packages/agent-runtime/src/lonora_agent/executor.py:255-257`,
   `packages/db/src/lonora_db/runs.py:360-378`): `require_completed_task_steps` returns at once
   for a run without `task_id` (`packages/db/src/lonora_db/tasks.py:839-842`);
   `resolve_reply_artifacts` and `validated_rich_content` handle attachments and card shape
   (`runs.py:377-378`). None of them reads claim wording; the answer is stored as the message
   content and as `row.result` (`runs.py:385`, `runs.py:425`).

That is all. (Checker: confirmed by two independent searches. `grep -rn "re\.compile\|re\.search\|re\.findall\|re\.match\|re\.sub" packages/agent-runtime/src`
finds no pattern applied to reply text other than `EFFECT_CLAIM`, the `<suggested_reply>` tag,
card fences and the Arabic-letter language test; and a search for every caller of
`append_uncertain_line`, `redact_private_reply`, `public_reply_violation`,
`unverified_financial_result`, `unsettled_wait_result`, `task_stop_gate` and `apply_stop_gates`
finds only the call sites listed in this section plus the card code in `visual_response.py` and
`genui_compile.py`.) There is no step that reads Arabic or English claim wording in the final reply, no
check that a claimed effect has a matching tool result, no check for promises, no check for
"I am monitoring" outside continuous Task runs, no check for "I cannot / no tool", and no
re-generation ("repair") of a reply.

## 2. The production runs

Reproduction for all of them: `scripts/trace_guards.py` → `runs/trace-guards.out` (stderr empty,
`runs/trace-guards.err`). Real API app, context builder, `model_turn`, tool loop, registry,
`market_watch` tools, `wait_for_input`, simulation broker; personal agent with
`trading_account_id null`, `scope.mode fixed_market` (`runs/trace-guards.out:2-15`), as in
production. Every model turn is SCRIPTED; the final Arabic replies are copied verbatim from
`lonora-chat.md`. For every case the output shows:

- `committed reply == SCRIPTED reply (byte for byte): true`, `stored assistant message == SCRIPTED reply: true`;
- `runtime notices appended as messages: []`;
- `uncertain-outcome line appended: false`;
- `EFFECT_CLAIM (stream-only regex) matches the reply: false`; `redact_private_reply changes the reply: false`;
- `run.model_metadata.reply_outcome: "answered"`, no `exit_reason`;
- `approval rows for this run: 0`.

### (1) Run ddae66ad, [63] «تم الإلغاء. المهمة/المتابعة على **EURUSDm** أُزيلت ولم تعد شغالة…»

Production facts (trace part 2): `wait_for_input` 09:56:33 → owner answer «ألغِ المهمة بالكامل»
09:56:46 → `watch_create` ×3 (09:56:48, :49, :51), all `ok` → completed 09:56:53. No
`watch_cancel` anywhere in the thread.

(Checker) Trace Part 4 adds the bodies:

- The question and its four choices were the model's own; the choice the owner tapped has the
  model-chosen id `cancel_watch` and the label «ألغِ المهمة بالكامل» (Part 4, #62 and
  `input_requests`). The model receives the answer as an ordinary owner message holding the
  label text only (`packages/agent-runtime/src/lonora_agent/steering.py:33-40`); the choice id
  stays in `input_requests` (`packages/db/src/lonora_db/messages.py:538-551`).
- `rounds` is 5: one model turn for the question, **three separate model turns** for the three
  `watch_create` calls, one for the reply. So the model read each result before the next call.
- Call 1: `{"symbol":"EURUSDm","kind":"price","condition":"above","level":1.2,"prompt":"placeholder"}`
  → new row 69c9e0bb, `"enabled": true`. Call 2: `below 1.11305`, `"prompt":"placeholder"` → new
  row 6050e419, `"enabled": true`. Call 3: identical to call 2 → the **same id 6050e419**, no
  new row.
- `tool_guardrails`: no failures, `halt: null`, `effect_streak [hash, 2, 0]`, three history
  entries. This is the same shape as the reproduction (`runs/trace-guards.out:400-431`).
- No blocked, rewritten or repair field in `execution_state` (Part 4, finding 9).

Path through the code, step by step:

1. `wait_for_input` returns `{"_runtime_wait": True, ...}` (`packages/tools/src/lonora_tools/runtime_control.py:100`);
   the loop stores `pending_input_request` and returns the question (`tool_block.py:370-375`,
   `tool_block.py:392-393`). The owner's answer marks the question answered, removes
   `pending_input_request` and re-queues the same run (`packages/db/src/lonora_db/messages.py:537-552`,
   `messages.py:571-573`). Nothing records *what the chosen option obliges the agent to do*.
2. Three `watch_create` calls. Before each: `before_call` (`tool_block.py:174`,
   `tool_guardrails.py:277-282`) only refuses an effect after 5 identical runs in a row
   (`IDENTICAL_EFFECT_BLOCK_AFTER = 5`, `tool_guardrails.py:69`, `tool_guardrails.py:250`).
   Dispatch: `registry.execute` checks existence, run scope and, for financial tools only, the
   run's authority (`packages/tools/src/lonora_tools/registry.py:478-493`). No check relates the
   call to the owner's request.
3. Final reply. `model_turn`: no financial call was proposed or is in the transcript, so the
   three gates at `model_runtime.py:225-238` are skipped; `redact_private_reply` finds nothing.
   Loop: `pending` is empty (`tool_loop.py:588-591`) → `final_answer` (`tool_loop.py:595-609`).
4. `final_answer`: `task_stop_gate` → no `task_id` → `continue_turn=False`
   (`stop_gates.py:153-155`, `stop_gates.py:180-181`). `append_uncertain_line` →
   `uncertain_operations`: the run is owner-started, but the calls it considers are only those
   with `call.name in FINANCIAL_EFFECTS` (`uncertain_outcome.py:85-90`, set at
   `uncertain_outcome.py:23`); `watch_create` is not one, so the set is empty,
   `uncertain_line` returns `None` (`uncertain_outcome.py:115-118`) and the text is returned
   unchanged (`uncertain_outcome.py:136-138`). `return LoopOutcome(text, metadata)`
   (`loop_outcomes.py:184`).

**Exact reason it was accepted:** no condition anywhere takes the reply text or the *kind* of
the successful tool results as input. The three `watch_create` successes did not "satisfy" a
guard; they were simply not looked at. Cases 4a, 4c and 5a-5c below pass identically with zero
tool calls, which proves the successes were irrelevant.

(Checker) Two instructions that this run broke were in the model's request, as text only:
"Do not invent a price threshold or trade parameters merely to fill a watch"
(`packages/agent-runtime/resources/constitution/tool-policy.md:5`; the production calls used
`above 1.2` with the prompt "placeholder") and "Say something was done only when a successful
tool result in this request shows it." (`trading-policy.md:7`). Both strings are present in the
first request of the reproduction runs (`runs/trace-guards-check-context.out`). UNSURE: the
production request bodies are not in the trace, so their presence there is inferred from the
same code, not observed.

Reproduction (`runs/trace-guards.out:165-480`, "CASE 1"): SCRIPTED `wait_for_input` with the
four options of [61] → run `waiting_input` → answer with choice «ألغِ المهمة بالكامل» → SCRIPTED
turn with three `watch_create` (above 1.2; below 1.11305; below 1.11305 again; prompt
"placeholder") → SCRIPTED reply [63] verbatim. Result: run `completed`, reply committed byte for
byte, no notice message, guard keys in the checkpoint are only `owner_started`,
`owner_request_start` and the guardrail history. Watch table afterwards
(`runs/trace-guards.out:447-480`): the pre-existing EURUSDm watch is still `enabled: true` and
two new "placeholder" rows exist. Nothing was cancelled; the owner is told «تم الإلغاء».

(Checker) Differences between this reproduction and production, none of which changes a guard
decision: the script puts the three `watch_create` calls in one SCRIPTED turn (production: three
turns); it passes `timeframe` and `evaluation_mode` explicitly (production left them to the
defaults, which are the same values, `packages/contracts/src/lonora_contracts/market_watch.py:21`
and line 32 of the same file); its choice ids are `keep/change/pause/cancel` (production:
`keep_eurusd/change_symbol/pause_watch/cancel_watch`). Rerun by the checker on the same database:
`runs/trace-guards.check.out`, same ten results (the watch tables there also show rows left by
the first run, because the script does not clean up).

**"A third watch_create returned ok with no new row"** (`packages/tools/src/lonora_tools/market_watch.py:90-145`).
`create` has three ways to return success without inserting:

- (a) `market_watch.py:93-95`: a row with this call's `resource_id` already exists. `resource_id`
  is derived from run id + call id (`packages/tools/src/lonora_tools/context.py:49-51`), so this
  needs the same call id twice in one run.
- (b) `market_watch.py:104-107` → `identical_watch` (`market_watch.py:55-87`): when the call has
  **no** `dedupe_key`, an existing watch of the same owner, agent and thread
  (`market_watch.py:76-78`) that is `enabled` true (`market_watch.py:79`) with a stored payload
  equal to what this call would store and the same Task id (`market_watch.py:85`) is returned
  with `"deduplicated": True`.
- (c) `market_watch.py:108-114` → `keyed_watch` (`market_watch.py:32-52`): with a `dedupe_key`,
  an enabled watch of this agent with the same key and an equal stored payload is returned with
  `"deduplicated": True`. (A different payload under the same key instead disables the old row
  and inserts a new one, `market_watch.py:115-136`.)

In all three the handler returns a normal resource dict and dispatch stamps `"ok": True`
(`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:109`), so the event log shows
`ok:true` exactly like a creation.

Reproduced path (b): the third SCRIPTED call, identical to the second, returned the second
row's id with `"deduplicated": true` and no new row (`runs/trace-guards.out:293-337`). It also
carried a guardrail notice **for the model only**: "watch_create has now run 2 times in a row
with identical arguments. Each call is a separate effect, not a retry…" (text at
`tool_guardrails.py:117-121`; threshold `IDENTICAL_EFFECT_WARN_AFTER = 2`,
`tool_guardrails.py:68`; attached at `tool_block.py:332-334`). A warning does not stop anything.

SETTLED by trace Part 4 (checker): production took **path (b)**. The third call's arguments
were identical to the second, it carried no `dedupe_key` (so not path c), it was a separate
model turn with its own call (so not path a), and it returned the second row's id 6050e419 with
that row's evaluation state already filled in (Part 4, #69/#70). Both rows were created
**enabled** (`"enabled": true` in #66 and #68; the model passed no `enabled` argument and the
default is true, `packages/contracts/src/lonora_contracts/market_watch.py:29`). So "two new
disabled watches" in the assignment text describes the rows at export time, not at creation:
from 09:56:48 the agent had armed two extra live watches while telling the owner «تم الإلغاء».

The stored `effect_streak [hash, 2, 0]` means the identical-effect counter reached 2 on the
third call (`tool_guardrails.py:364-373`), which is the warning threshold, so by the code the
third result carried the "has now run 2 times in a row" notice shown above. TRACE BODIES MUST
CONFIRM: the notice itself and the `"deduplicated": true` flag in #70 (the export cuts that
result at 1500 characters, before the end of the object). If confirmed, the model wrote «تم
الإلغاء» directly after a result that said the same watch already existed and warned it about
repeating the call.

UNSURE (not this file's subject): what set `enabled=false`, version 2, on the two rows later.
No tool call of this thread did. `trace-watch-lifecycle.md` (another audit file, not re-verified
here) attributes it to a cancel through the owner's own route at about 12:29 UTC.

### (2) Run e343c96a, [69] «تمام، سأحذف **كل المتابعات والمهام الفرعية فقط**…»

Production: only `wait_for_input`; after the answer at 09:59:45 the run completed at 09:59:47
with no tool call. (Checker, trace Part 4: `rounds` 2; the owner's choice id was `tasks_only`;
`execution_state` has `input_requests` and no `tool_guardrails` key. The missing key is
expected, not a sign of a different path: an owner message merged into a run clears the
guardrail and stop-gate state, `packages/agent-runtime/src/lonora_agent/steering.py:42-48`, and
no tool ran afterwards to recreate it. The same reset explains why ddae66ad's history has three
entries and not four.)

Is there a guard for a promise of future action with no tool call? **No.**

- The reply follows the same path as (1) step 3-4 and nothing in it reads the text.
- The only place the runtime ties a promise to a saved effect is the stop gate for **continuous
  Task runs**: `CONTINUOUS_NUDGE` contains "only a successful saved wait can support a promise
  to follow up" (`stop_gates.py:45-54`), applied only `if continuous:` (`stop_gates.py:99-100`)
  and only when the run has a Task (`stop_gates.py:153-155`). Even there it is structural, not
  textual: "No text classifier decides whether monitoring exists: the successful wait path
  settles it." (`stop_gates.py:95-96`).
- A `wait_for_input` answer creates no obligation: after `messages.py:552` removes
  `pending_input_request` there is no state that says "the owner chose delete; a delete must
  follow".
- The constitution sentence "A brief acknowledgement does not finish the requested work."
  (`packages/agent-runtime/resources/constitution/tool-policy.md:9`) is prompt text; it was in
  the request (`runs/trace-guards-context.out`) and is not enforced.

Reproduction (`runs/trace-guards.out:481-626`, "CASE 2"): SCRIPTED `wait_for_input` with the two
options of [67] → answer «احذف كل المتابعات والمهام الفرعية فقط» → SCRIPTED reply [69] verbatim.
Run `completed`, `tool calls in the run: ["wait_for_input"]`, reply committed unchanged, watch
table unchanged (three enabled rows).

### (3) Run e79b4bf2, [77] (after [76] «جرب»): a watch created with prompt "cancel-test"

Production (ran on 9f5b1da = main): one `watch_create` → `ok`, row b9c1017a (`enabled false`,
prompt "cancel-test", `dedupe_key cancel-test-1`). (Checker, trace Part 4 #78/#79: arguments
`{"symbol":"EURUSDm","kind":"price","condition":"below","level":"1.11305","prompt":"cancel-test","enabled":false,"dedupe_key":"cancel-test-1"}`;
result `version 1`, `state {}`. The model was asked to try `watch_cancel` and called the one
watch tool in its native list instead; it did not call `tool_call`.)

Does anything stop a side-effecting trial call? **No.** Checks a `watch_create` passes:

1. `before_call` (`tool_guardrails.py:277-282`): repetition only.
2. `registry.execute` (`packages/tools/src/lonora_tools/registry.py:475-507`): tool exists;
   `tool.permitted(scope)`; authority is checked **only** `if tool.financial`
   (`registry.py:481-493`).
3. `guard_market_tool` (`packages/tools/src/lonora_tools/market_binding.py:97-141`): symbol/account
   binding applies only to a fixed-market agent; `if not fixed_market(agent): return args`
   (`market_binding.py:113-114`), and `fixed_market` requires a bound account:
   `return bool(agent.trading_account_id) and not flexible_scope(agent)`
   (`packages/db/src/lonora_db/agent_binding.py:35-36`). The personal agent has
   `trading_account_id null`, so the fixed-market binding does not restrict the account or
   symbol it passes. UNSURE (checker): whether anything else in the create path verifies that
   `account_id` belongs to the owner or that the symbol exists; I found no such check in
   `market_watch.py:90-145` or `market_binding.py:82-141` and did not follow
   `MarketWatchRepository.create` to the end.
4. The handler `create` (`market_watch.py:90-145`) has no approval, no owner-intent check and no
   check of the `prompt` content (the contract only requires 1 to 8000 characters,
   `packages/contracts/src/lonora_contracts/market_watch.py:28`).

Under which authority: the run scope. A `trigger=user` run is `"full"`
(`packages/tools/src/lonora_tools/base.py:53-58`), and `Tool.permitted` returns `True` for
`"full"` (`base.py:92-94`). `watch_create` is registered as neither `read_only` nor `financial`
(`market_watch.py:237-244`), so its effect class is "change"
(`packages/agent-runtime/src/lonora_agent/tool_block.py:153-155`; the trace shows
`market/change`). Approval cards exist only on the financial path
(`packages/trading/src/lonora_trading/agent_permission.py:38`, `agent_permission.py:62`). The
tool's own description frames it as harmless: "It wakes this agent to reassess and never
trades." (`market_watch.py:239`). No instruction or check says "do not create a resource to
test a tool".

Also note the reply [77] names `watch_cancel` and "watch" to the owner; that is allowed by
design (`public_reply.py:40-41`).

Reproduction (`runs/trace-guards.out:627-803`, "CASE 3"): SCRIPTED `watch_create` with
`enabled false`, prompt "cancel-test", `dedupe_key cancel-test-1` → `ok: true`, a fourth row in
the table (`enabled: false`, prompt "cancel-test"), `approval rows for this run: 0`, reply [77]
committed unchanged.

### (4) Runs 8114abdd [43] «مراقب… إذا وصل لهذا المستوى، أغلقه فورًا», 6e4aa88f [47] «فأنا أتابعه», 7e7da121 [57] «أراقب **XAUUSDm**…»

Production: 8114abdd and 7e7da121 made no tool call; 6e4aa88f made one `account_read`. No watch
on XAUUSDm and no +100 USD watch exists (trace Q4).

(Checker) 8114abdd and 6e4aa88f ran on build 2477c22 and 7e7da121 on cd2cc91; see the build
note at the top for why the reading of main applies.

Guard conditions evaluated: the same as in section 1, with the same outcome. For 6e4aa88f the
`account_read` result is not read by any reply check either (`account_read` is only used to
collect public position ids, `context/financial_result.py:12-67`).

A check that monitoring really exists is present only for continuous Task runs
(`stop_gates.py:99-100`, with the header statement "Prose is an update, never proof of a saved
monitoring or scheduling action." at `stop_gates.py:6`). These were chat runs with no Task, so
`task_stop_gate` returned at `stop_gates.py:180-181`.

Prompt side: the system manual has the rule "Do not claim monitoring is active unless an actual
watch or schedule exists." (`packages/agent-runtime/resources/system/lonora.md:393`) and
"Persist a relevant watch or Task timer wait before promising monitoring."
(`lonora.md:620`). In the reproduction neither sentence was in the request the model received,
in a no-tool run or in a run that called `watch_create` (`runs/trace-guards-context.out`, all
three columns `false`). UNSURE: whether production requests contained them (the chapters are
selected per run; the trace export has no request bodies).

Reproduction (`runs/trace-guards.out:804-1104`, "CASE 4a/4b/4c"): [43] and [57] SCRIPTED with no
tool call, [47] after a SCRIPTED `account_read`; all three committed unchanged, one model turn
(two for 4b), no notice; the table after case 4 has no XAUUSDm watch.

### (5) Runs c22a6810 [29], 1638329a [71], fb1d4b5a [73]

**c22a6810 [29]** (status answered with no live read). No tool call in the trace; the reply
itself says «وقت آخر تحقق». Nothing requires a read tool before a status answer: the
constitution says "Use tools for current facts."
(`packages/agent-runtime/resources/constitution/identity.md:1`), prompt only. Reproduced
("CASE 5a", `runs/trace-guards.out:1105-1178`): one SCRIPTED turn, reply committed unchanged.

**1638329a [71]** «ما عندي أداة حذف مباشر للمتابعات» with no tool call. Nothing requires a
`tool_environment` call before a claim of inability. The rule exists as text only, in the
capability inventory inserted into every request: "inspect it with tool_environment first when
you do not know its input schema, and before claiming an ability is absent"
(`packages/tools/src/lonora_tools/registry.py:425-431`, inserted at `model_runtime.py:66-75`).
The same request also contained "A watch is cancelled with watch_cancel or changed with
watch_update" and "Reach a tool outside your native list with tool_call."
(`trading-policy.md:7`); the reproduction confirms all three sentences are in the first request
of a no-tool run (`runs/trace-guards-context.out`). So the model had the tool's name and the way
to reach it in front of it and still said no tool exists; no code compared the claim with the
registry. Reproduced ("CASE 5b", `runs/trace-guards.out:1179-1252`).

(Checker) Three additions:

- In the reproduction the capability inventory itself lists the tools by name. The `market:`
  line of the `<available_capabilities>` block in the first request of a no-tool run reads
  "…market_symbols, watch_cancel, watch_create, watch_list, watch_pause, watch_resume,
  watch_update" and the block ends "Listed 126 of 126 permitted capabilities."
  (`runs/trace-guards-check-context.out`; the list is built at `registry.py:415-422` and
  `registry.py:470-472`). `trade_close_positions` and `goal_list` are in it too. UNSURE: whether
  the production request carried the full block; the inventory is optional guidance that
  admission may shed (`model_runtime.py:66-69`) and the trace holds no request bodies.
- The same request also contains "Use only the tools provided in this run."
  (`packages/agent-runtime/resources/constitution/tool-policy.md:1`), next to "Reach a tool
  outside your native list with tool_call." (`trading-policy.md:7`). The two sentences pull in
  opposite directions for a tool that is listed in the inventory but is not native. This is an
  observation about the prompt text, not a proven cause of [71].
- Trace Part 4 shows that 1638329a made no tool call at all, and that when the model did look,
  one hour later (run 3fa683e6, `tool_environment {"query":"watch cancel task routines goals"}`),
  the answer was `{"tools": [], "total": 0}`. That empty result belongs to tool discovery
  (another session); for this file it matters only because nothing compared «ما في أداة حذف»
  [75] with the registry either.

**fb1d4b5a [73]** «…ولا أقدر أدّعي الإلغاء بدون رد أداة ناجح» (ran on 9f5b1da = main).

- What it paraphrases: the last sentence of the paragraph PR #42 added to the constitution,
  `packages/agent-runtime/resources/constitution/trading-policy.md:7`:
  "Say something was done only when a successful tool result in this request shows it."
  A second, older sentence says the same: "Validate the returned machine status before claiming
  success." (`packages/agent-runtime/resources/constitution/tool-policy.md:1`). Both are in the
  request of every run in the reproduction (`runs/trace-guards-context.out`).
- Was a guard triggered in that run? **No, and none could have been.** The run made no tool
  call, was a chat run (no Task), and finished in about 4 seconds. No injected runtime message
  exists for this situation, so the model was reciting its instructions, not reacting to a
  guard. Reproduced ("CASE 5c", `runs/trace-guards.out:1253-1325`): one SCRIPTED turn, reply
  committed unchanged, `runtime notices appended as messages: []`, checkpoint guard keys only
  `owner_started` and `owner_request_start`.
- What the run record would show if a guard had fired (what the code stores):

  | Mechanism | Trace it leaves |
  |---|---|
  | Uncertain-outcome line | Only the text: `run.result` and the stored message end with `LINE_AR`/`LINE_EN` (`uncertain_outcome.py:36-37`, `uncertain_outcome.py:139-152`). No flag. The checkpoint always has `owner_started`/`owner_request_start` (`uncertain_outcome.py:19-20`, `uncertain_outcome.py:47-48`), fired or not. |
  | Task stop gate | `execution_state["continuous_stop_gate"]` or `["task_completion_gate"]` = `{version, attempts, plan_revision}` (`stop_gates.py:42-43`, `stop_gates.py:108`); a runtime-notice message of kind `completion_check` in `execution_state.messages` (`loop_outcomes.py:172`); when exhausted, run status `waiting_input` with `model_metadata.exit_reason`, `owner_attention` and `reply_outcome: "needs_owner_attention"` (`loop_outcomes.py:83-96`). |
  | Tool guardrails | `execution_state["tool_guardrails"]` (`tool_guardrails.py:53`, `tool_guardrails.py:159-168`); `runtime_notice` inside the tool result (`tool_block.py:334`); a blocked call has `code: "guardrail_blocked"` (`tool_guardrails.py:302-310`); a halt ends with `model_metadata.exit_reason: "guardrail_halt"` (`tool_loop.py:400-401`, `tool_loop.py:314-321`). |
  | Financial-truth replacement | Nothing but the fixed sentence as the reply (`context/financial_result.py:122-124`). `provider_metadata` has `"public_rewrite": False` (constant) and `privacy_redacted` (`model_runtime.py:266-267`), but `selection_metadata` does not copy either into the run (`tool_loop.py:178-190`). |

  SETTLED by trace Part 4, finding 9 (checker): "execution_state has no blocked, rewritten or
  repair fields for ddae66ad, e343c96a or fb1d4b5a"; fb1d4b5a has "no tool messages; rounds 1,
  pending [] … No guard or stop-gate record." UNSURE: that finding lists the keys present as
  `pending`, `rounds`, `task_continuation`, `selection` (plus `input_requests` and
  `tool_guardrails` where they apply) and does not name `owner_started` /
  `owner_request_start`, which `record_request_start` writes on every run's first entry
  (`loop_restore.py:58`, `uncertain_outcome.py:42-48`) and which the reproduction shows
  (`runs/trace-guards.out:1309-1312`). The list is plainly not exhaustive (it also omits
  `messages` and `environment`, which Part 1 and Part 4 read from), so this is most likely an
  omission of the digest; only the raw `execution_state` can confirm the two keys are there.

## 6. What the existing guards DO detect

### 6.1 The PR #42 uncertain-outcome line (the only runtime check PR #42 added)

- **Structural check, no wording.** At the end of a run, `uncertain_operations`
  (`uncertain_outcome.py:78-112`) fires only if all of these hold:
  - the run was started by the owner typing: `trigger in {"user", "group"}` and an owner message
    exists (`uncertain_outcome.py:22`, `uncertain_outcome.py:40-48`);
  - a tool result **after the owner's last message at run start** (`uncertain_outcome.py:93`)
    belongs to a call named `trade_execute`, `trade_close_positions` or `goal_step_execute`
    (`uncertain_outcome.py:23`, `uncertain_outcome.py:85-90`);
  - the latest result for that operation has `status` or `code` in `{"ambiguous",
    "operation_ambiguous", "tool_execution_uncertain", "submitted", "reserved",
    "broker_result_ambiguous"}` (`uncertain_outcome.py:24-33`, `uncertain_outcome.py:65-75`),
    looking also at a nested `result` and a `results` list (`uncertain_outcome.py:51-62`) and
    letting a reconciliation of the same operation settle it (`uncertain_outcome.py:105-110`).
- **Text added** (verbatim): `LINE_AR = "نتيجة العملية غير مؤكدة بعد؛ أتحقق منها ولن أعيد إرسالها."`
  (`uncertain_outcome.py:36`); `LINE_EN = "The outcome is not confirmed yet; I am checking it and
  will not resend it."` (`uncertain_outcome.py:37`). Language by `prefers_arabic`
  (`uncertain_outcome.py:118`; `runtime_notices.py:84-93`).
- **Repair rounds: zero.** Nothing is sent back to the model. The line is appended once to the
  text, the stored assistant message and the card (`uncertain_outcome.py:134-152`,
  `uncertain_outcome.py:121-131`). "The reply and its card are never replaced."
  (`uncertain_outcome.py:9`).
- **When "repair fails":** there is no failure mode; if the conditions do not hold the reply is
  returned as is (`uncertain_outcome.py:137-138`).
- **What the owner sees:** the model's reply, unchanged, plus that one sentence as a last
  paragraph. It is applied on the normal final reply (`loop_outcomes.py:179-183`, enabled at
  `tool_loop.py:608`) and on the round-limit/guardrail report (`tool_loop.py:299`). It is
  **not** applied on the silent-final path (`tool_block.py:399-410`, no `outcome_line`) or on a
  `wait_for_input` question.
- 21 collected test cases (12 test functions) pass on main against database 7
  (`runs/trace-guards-pytest.out`; rerun by the checker: `21 passed`).

### 6.2 The PR #42 constitution paragraph (prompt only, verbatim, `trading-policy.md:7`)

> Owner controls are tools, never prose and never a trade. A request to stop or pause new trading (today, a symbol, an agent) is trade_restriction_create, with valid_until for a time limit; a new entry never answers it. Resuming trading, lifting a pause, risk limits (such as a maximum risk per trade) and authority are owner_action_propose cards: only the owner's tap applies them, and a card waits only once you proposed it. memory_write never records a limit, permission or rule the server enforces. A watch is cancelled with watch_cancel or changed with watch_update, a recurring review is routine_create, and the AI model an agent runs on (its language model, not a skill) is chosen with model_list, then model_request. Reach a tool outside your native list with tool_call. Say something was done only when a successful tool result in this request shows it.

It is present in the model's request (`runs/trace-guards-context.out`) and has no enforcement.
Its presence explains [73] (the model quotes it to the owner) and did not prevent [63], [69],
[71] or [77].

### 6.3 Checks that existed before PR #42 (so the lead knows what is already there)

| Mechanism | Detects | Patterns / condition | Repair text | Rounds | On failure | Owner sees |
|---|---|---|---|---|---|---|
| Financial-truth gates (`model_runtime.py:217-238`) | Prose next to an unproven **financial** result | Tool names in `FINANCIAL_CALLS` (`context/financial_result.py:9`); result `status == "confirmed"` without `details.verification.status == "verified"` (`context/financial_result.py:95-110`) | None; the text is replaced by «أقرّ الوسيط بالطلب، لكن التحقق المستقل من نتيجته لم يكتمل بعد. لن أكرر الإرسال.» (`context/financial_result.py:122`) or, with `task_wait`, one of the sentences at `context/financial_result.py:152-212` | 0 | n/a | The fixed sentence instead of the model's text |
| Stream admission (`public_stream.py:11-19`, `public_stream.py:47-51`) | Effect-claim wording **while streaming** (plain text). The same regex has one more user, the card compiler, next row | `EFFECT_CLAIM`. Arabic part, verbatim: `(?:تمت?\s+(?:تنفيذ|فتح|إغلاق|اغلاق|إرسال|ارسال|تفعيل|شراء|بيع|الموافقة))` and `(?:فتحت|فتحنا|أغلقت|اغلقت|نفذت|نفّذت|فعّلت|فعلت|أرسلت|ارسلت)\s+(?:(?:لك|بنجاح|الآن|الان)\s+)?(?:صفقة|أمر|امر|السوبر|سوبر)`; English part: I/we executed/opened/closed/placed/bought/sold/approved/sent/activated; order/trade/position/request/super bot … executed/opened/closed/placed/approved/sent/activated/confirmed/completed; a leading `Done|Completed|Confirmed|Approved` | None | 0 | n/a | Only timing: the text arrives at the end instead of incrementally. Trading verbs only: «تم الإلغاء», «أُزيلت», «سأحذف», «مراقب», «أتابعه», «أراقب», «ما عندي أداة» do not match (`runs/trace-guards.out`, every case `false`; also `runs/bc_effect_claim_regex.out`) |
| Generated-card compiler (checker; `packages/agent-runtime/src/lonora_agent/genui_compile.py:421-428`, called from `visual_response.py:655-657`) | Inside a **card** only: a market/account number typed by the model instead of read from a tool result (`genui_compile.py:671-672`, `genui_compile.py:289-308`); private text (`genui_compile.py:736-738`); effect-claim wording while the card is still streaming (`if not final:` → `EFFECT_CLAIM`, `genui_compile.py:739-743`) | `FACT_TOOLS` names and `EFFECT_CLAIM` | None | 0 | `CardError` (`card_fallback_typed_fact`, `card_fallback_private`, `card_effect_claim`); the handling of that error was not traced here | UNSURE: what the owner sees on a rejected card. Not relevant to this thread: no assistant message had a card (`rich_content` null, trace Part 3), and plain reply text never reaches these checks |
| Privacy redaction (`public_reply.py:10-25`, `public_reply.py:54-67`) | Credentials, private paths/tags, UUIDs not proven public | Regexes at `public_reply.py:10-25` | None; span replaced by `[REDACTED]` (`public_reply.py:26`) | 0 | n/a | The reply with `[REDACTED]`. Tool names, error codes, `waiting`, `owner_attention`, broken `**` pass |
| Task stop gate (`stop_gates.py:86-129`, `loop_outcomes.py:170-178`) | A final answer in a **Task** run that is continuous or has unfinished declared steps | Structural: `continuous` (`stop_gates.py:99-100`) or `incomplete_steps` (`stop_gates.py:101-102`) | `CONTINUOUS_NUDGE` (`stop_gates.py:45-54`) or `_steps_nudge` (`stop_gates.py:72-83`), appended as a `completion_check` runtime notice (`loop_outcomes.py:172`) | `MAXIMUM_STOP_NUDGES = 2` (`stop_gates.py:41`, `stop_gates.py:126-129`); reset by real owner input or a wake (`steering.py:42-48`, `loop_restore.py:77`, `loop_restore.py:103`) | `exhausted` → `request_owner_attention` (`loop_outcomes.py:175-178`, `loop_outcomes.py:109-152`) | A resumable question: the runtime's own notice first, e.g. «هذه المهمة المستمرة غير مراقَبة: لم يُحفظ أي انتظار مراقبة أو مؤقت مراجعة، لذلك لن تحدث أي متابعة تلقائية.» (`runtime_notices.py:150-151`), then «آخر تقرير: » + the held answer (`runtime_notices.py:199-203`) |
| Tool guardrails (`tool_guardrails.py:56-73`) | Repeated identical calls/results, failure streaks, cycles | Counts only | Notice in the tool result (texts at `tool_guardrails.py:77-131`) | warn at 2-3, block at 5, halt at 5-8 depending on the rule | `halt` → `finish_turn` with one tool-less final report (`tool_loop.py:400-438`, `tool_loop.py:223-322`; instruction text `runtime_notices.py:117-129`) | The model's final report, or «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها…» if it writes nothing (`runtime_notices.py:132-139`) |
| Empty reply (`tool_loop.py:573-579`) | No text, no card, no call, in a conversational run (`tool_loop.py:574`) | Structural | `NO_ANSWER` (`runtime_notices.py:96-99`) | Bounded by the round budget | Round limit → `finish_turn` | Nothing until a non-empty reply |
| `wait_for_input` wording (`runtime_control.py:74-82`) | Private identifiers in a question or its options | `public_reply_violation` | Tool result `question_wording_private` with guidance | Normal loop | n/a | Nothing (the question is not shown) |

### 6.4 Gaps against the principles, and the existing extension points (names only, no design)

- **Principle 3 (a reply that ends with an offer), 7 (inability without evidence), 8 (promise or
  "done" without a successful result; trial side effects), 12 (codes, tool names, internal
  states, broken markdown):** none of these has any check today. (Checker: the same holds for
  principle 5, a stated condition with no saved trigger, cases 4a-4c, and principle 11, a status
  answer with no live read, case 5a.) Everything that exists keys on
  the three financial tool names or on Task structure.
- Where a tool-less final reply is decided, and where a turn can already be continued with an
  injected notice instead of ending:
  - `final_answer` (`loop_outcomes.py:155-184`): every normal final reply passes here; returning
    `None` continues the turn (`loop_outcomes.py:171-174`, caller `tool_loop.py:595-611`).
  - `task_stop_gate` / `apply_stop_gates` / `StopGateVerdict` (`stop_gates.py:57-63`,
    `stop_gates.py:86-129`, `stop_gates.py:178-184`): the bounded continue/stop verdict with a
    checkpointed counter; today it returns early for runs without a Task (`stop_gates.py:180-181`).
    `reset_stop_gate` (`stop_gates.py:66-69`) defines the review epoch.
  - `append_notice` (`runtime_notices.py:67`): how a nudge reaches the model.
  - `request_owner_attention` / `attention_notice` / `attention_message`
    (`loop_outcomes.py:109-152`, `runtime_notices.py:172`, `runtime_notices.py:199`): what
    happens when nudges are spent (Task runs only today).
- Where "what happened in this request" is already computed from structured results:
  - `record_request_start` and `uncertain_operations` (`uncertain_outcome.py:40-48`,
    `uncertain_outcome.py:78-112`): the request boundary (`owner_request_start`) and the walk
    over this request's tool results; the tool set is the constant `FINANCIAL_EFFECTS`
    (`uncertain_outcome.py:23`). The same three names are duplicated as `FINANCIAL_CALLS`
    (`context/financial_result.py:9`).
  - `unverified_financial_result` / `unsettled_wait_result` (`context/financial_result.py:70`,
    `context/financial_result.py:129`): the pre-publication equivalents inside `model_turn`.
- Where reply text is replaced or filtered before the owner sees it:
  - the gate block in `model_turn` (`model_runtime.py:217-248`);
  - `redact_private_reply` / `public_reply_violation` (`public_reply.py:37-67`), currently
    forbidden by its own docstring from judging style or names (`public_reply.py:1-5`);
  - `PublicStream.offer` and `EFFECT_CLAIM` (`public_stream.py:11-19`, `public_stream.py:33-65`):
    text is streamed to the owner while it is generated, so a check that runs only after the
    reply is complete judges text that may already be on screen. The existing answer to that is
    a new stream turn when the final text does not extend what was sent
    (`model_runtime.py:282-287`).
- Exits that do **not** go through `final_answer` with `outcome_line`, so a new end-of-turn check
  placed only there would miss them (PR #42 had to add a second call for this reason,
  `tool_loop.py:299`):
  - `finish_turn` (`tool_loop.py:223-322`), the round-limit/halt report;
  - the silent-final path (`tool_block.py:394-412`);
  - `question_outcome` (`loop_outcomes.py:71-80`), a `wait_for_input` question;
  - `external_wait_outcome` (`loop_outcomes.py:39-68`), a Task wait update.
- Where a tool call can be refused before it runs (relevant to "no trial side effects"):
  `before_call` (`tool_guardrails.py:277-299`) and `ToolRegistry.execute`
  (`registry.py:475-507`). Neither knows the owner's request today.
- Where an answered question could leave an obligation: the answer handling in
  `packages/db/src/lonora_db/messages.py:537-552` and the `input_requests` history kept by the
  executor (`packages/agent-runtime/src/lonora_agent/executor.py:160`, `executor.py:211`).

UNSURE: what the client shows for text already streamed in a turn that a stop gate then
continues (the assistant message stays in the transcript, `tool_loop.py:580-587`); not tested
here.

### 6.5 For the three runs the lead named: the nearest existing check and the exact line where it let go (checker)

| Run | Reply | Nearest existing check | Why it did not fire |
|---|---|---|---|
| ddae66ad | «تم الإلغاء… أُزيلت» after three `watch_create` | `task_stop_gate` in `final_answer` (`loop_outcomes.py:170`) | The run has no `task_id`: `task_progress` returns `None` (`stop_gates.py:153-155`) and the gate returns `continue_turn=False` (`stop_gates.py:180-181`). Even for a Task run the gate is structural and would not have compared «تم الإلغاء» with the calls (`stop_gates.py:95-96`). |
| | | `append_uncertain_line` (`loop_outcomes.py:179-183`) | Only calls named in `FINANCIAL_EFFECTS` are collected (`uncertain_outcome.py:85-90`); `watch_create` is not one, and its results were `ok`, not uncertain. |
| | | Tool guardrails | Counted two identical effects and warned the model inside the tool result (`tool_guardrails.py:364-373`, `tool_block.py:332-334`); a warning neither blocks the call nor touches the reply. |
| | | Financial-truth gates and redaction in `model_turn` | No financial call proposed or in the request (`model_runtime.py:225-238`); nothing private in the text (`model_runtime.py:246`). |
| e343c96a | «تمام، سأحذف…» with no tool call after the answer | `task_stop_gate` | Same early return (`stop_gates.py:153-155`, `stop_gates.py:180-181`). The sentence "only a successful saved wait can support a promise to follow up" exists only inside `CONTINUOUS_NUDGE` (`stop_gates.py:45-54`), which is sent only to continuous Task runs (`stop_gates.py:99-100`). |
| | | `append_uncertain_line` | No financial call in the request, so `uncertain_operations` is empty (`uncertain_outcome.py:85-112`). |
| | | The answered question | Answering removes `pending_input_request` and records the choice (`messages.py:538-552`); nothing afterwards requires a tool call that matches the choice. |
| fb1d4b5a | «…ولا أقدر أدّعي الإلغاء بدون رد أداة ناجح» | None applies | No tool call, no Task, one model turn. The text paraphrases `trading-policy.md:7`; no runtime message with that meaning exists (the only injected notices are listed in section 6.3). |

There is no check in `stop_gates.py` or elsewhere that "should have fired" under the code as
written: each of the three replies is outside the stated scope of every existing check.

## 7. Open items

- SETTLED by trace Part 4 (checker): the three `watch_create` calls of ddae66ad were three model
  turns; rows were created with `enabled` true; the third call took dedupe path (b).
- TRACE BODIES MUST CONFIRM: the tail of the third result (#70, cut at 1500 characters):
  `"deduplicated": true` and the `runtime_notice` of kind `tool_guardrail`.
- SETTLED for ddae66ad, e343c96a and fb1d4b5a by trace Part 4, finding 9: no blocked, rewritten
  or repair record. TRACE BODIES MUST CONFIRM for 1638329a, 8114abdd and 7e7da121 (not among
  the seven runs of Part 4): `execution_state.messages` contain no runtime notice (expected:
  none; the digest shows no tool call and a normal completion).
- UNSURE: whether production `execution_state` holds `owner_started` / `owner_request_start`
  (not named in Part 4, finding 9; see case 5c).
- UNSURE: what disabled watches 69c9e0bb and 6050e419 (version 2) after 09:56; no tool call in
  this thread did. See `trace-watch-lifecycle.md`.
- UNSURE: whether the manual sentences `lonora.md:393` and `lonora.md:620` reached the model in
  production; in the reproduction they did not.
- UNSURE: whether the production requests carried the full capability inventory and the
  constitution sentences quoted in this file; the trace has no request bodies, and the claim
  rests on the reproduction plus the unchanged code (build note at the top).
- UNSURE: how a rejected card (`CardError`) is shown to the owner (section 6.3); not traced.
- Note on test fidelity: `tests/test_uncertain_outcome.py` replaces
  `lonora_agent.tool_loop.model_turn` (`tests/test_uncertain_outcome.py:231`), so those tests do
  not exercise the gates inside `model_turn`. `scripts/trace_guards.py` patches only the
  router's `complete`, so `model_turn`, redaction and stream admission ran for real.

## 8. Files

- Script: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/trace_guards.py`
- Output: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/trace-guards.out` (stderr: `runs/trace-guards.err`, empty)
- Script: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/trace_guards_context.py`
- Output: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/trace-guards-context.out`
- Test run: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/trace-guards-pytest.out` (21 passed)
- Repository state after the work: `git status --short` empty.
- Checker rerun of the main script: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/trace-guards.check.out` (stderr `runs/trace-guards.check.err`, empty)
- Checker rerun of the context script: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/trace-guards-context.check.out` (identical to the original output)
- Checker script (more sentences, the inventory block): `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/trace_guards_check_context.py` → `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/trace-guards-check-context.out`

## Verification log

Method: every `path:line` in this file was opened at main 9f5b1da and compared with the
adjacent claim; quoted guard texts, Arabic strings and the regex fragments were compared with
the source character for character (section 6.2 and the two Arabic regex fragments by program);
the three reproduction commands were rerun on database 7; absence claims were tested with two
independent searches each; every production statement was compared with `production-trace.md`
Parts 1 to 4. `git -C /home/user/lonorabot status --short` is empty after the work.

**Citations.** About 190 distinct `path:line` references in the original text, in about 45
files, all opened (217 distinct references after this pass). Where a short file name is used
(`market_watch.py`, `registry.py`, `messages.py`, `runs.py`, `memory.py`), it means the file
whose full path is given at its first mention in the same passage. All point at the code they are said to point at. No line number had to be changed. Two
were weak rather than wrong and were left with this note: `agent_permission.py:38` and
`agent_permission.py:62` show where `trade_approval_required` is raised, which supports
"approval exists on the financial path" but does not by itself prove "only there"; the "only"
rests on `registry.py:481-493`, where authority is checked `if tool.financial`.

**Reproductions rerun.**

- `scripts/trace_guards.py` → `runs/trace-guards.check.out`: exit 0, stderr empty, the same ten
  `byte for byte: true`, ten `[]` notices, ten `false` for the uncertain line, `EFFECT_CLAIM`
  and redaction, ten `reply_outcome: "answered"`, no `exit_reason`, the same deduplicated third
  call with the same guardrail notice. Differences are ids, sequence numbers and extra watch
  rows left in the database by the first run.
- `scripts/trace_guards_context.py` → identical output.
- `pytest tests/test_uncertain_outcome.py` → `21 passed`.
- The output line ranges quoted for each case (`runs/trace-guards.out:165-480` and so on) match
  the case headings in that file.

**Corrected.**

1. Headline and section 6.3: "nothing compares what the agent says with what the run did" and
   "EFFECT_CLAIM (stream-only regex)" were too broad. `EFFECT_CLAIM` has a second user, and a
   typed-number check exists, both in the generated-card compiler (`genui_compile.py:671-672`,
   `genui_compile.py:739-743`). The headline now says "reply text" and the table has a row for
   the card compiler. The conclusion for this thread is unchanged (no cards were produced).
2. Case 1, "TRACE BODIES MUST CONFIRM" block: replaced by what trace Part 4 shows. The original
   inference (path b; rows created enabled) is confirmed. New from the trace: three separate
   model turns, the owner's choice id `cancel_watch`, and a stored `effect_streak` of 2, which
   by the code means the third result carried the repetition warning.
3. Case 5c and section 7: the "TRACE BODIES MUST CONFIRM" items that Part 4, finding 9 answers
   are marked settled; the ones it does not cover (three other runs; the cut tail of #70) remain.
4. "21 tests" → 12 test functions, 21 collected cases.
5. Stop-gate reset: `steering.py:42-48` added (the owner's answer to a question card resets the
   stop-gate and guardrail state; the original listed only `loop_restore.py`).
6. Empty-reply rule: applies to conversational triggers only (`tool_loop.py:574`).

**Downgraded to UNSURE.**

1. Case 3, "it may create a watch on any owned account and symbol": the cited lines show that
   the fixed-market binding does not apply; they do not show an ownership or symbol check, and
   none was found. Reworded and marked UNSURE.
2. Every statement of the form "the sentence was in the request" now says that it is observed
   in the reproduction and inferred for production (no request bodies in the trace).
3. Case 5c: the production key list in Part 4 does not name `owner_started` /
   `owner_request_start`; noted as a probable omission of the digest, to be confirmed.

**Refuted.** No claim about why a reply passed was refuted. For each "the guard passes because
X" claim the guard was read again for a missed condition: `task_stop_gate` (no other entry than
`task_progress`), `uncertain_operations` (the name filter at `uncertain_outcome.py:85-90` is
applied before any result is read), the three `model_turn` gates (all need a name in
`FINANCIAL_CALLS` or `task_wait`), `redact_private_reply` (three regexes, none matches the
replies), `before_call` (needs five identical executions). None has a branch that the
production replies could have reached.

**Added.**

1. Build note: the guard modules are byte-identical between cd2cc91 and main, and unchanged in
   substance since 2477c22, so the analysis covers all runs of the day.
2. Section 1: the steps the original list left out (suggested-reply cut, visual projector,
   `complete_run` after the loop), with the reason each is irrelevant to claims.
3. Case 1: `tool-policy.md:5` "Do not invent a price threshold or trade parameters merely to
   fill a watch" was in the request and was broken by the "placeholder" watches; the list of
   differences between the reproduction and production.
4. Case 2: why `tool_guardrails` is absent from e343c96a's state.
5. Case 5b: in the reproduction the capability inventory lists `watch_cancel`, `watch_list` and
   `watch_pause` by name ("Listed 126 of 126"); the request also holds two sentences that pull
   against each other ("Use only the tools provided in this run." and "Reach a tool outside
   your native list with tool_call.").
6. Section 6.5: the per-run table the lead asked for (nearest check, exact line of the early
   return) for ddae66ad, e343c96a and fb1d4b5a.
7. Section 6.4: principles 5 and 11 added to the list of unguarded behaviours.
