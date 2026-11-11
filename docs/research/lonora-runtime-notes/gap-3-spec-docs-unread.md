# Gap 3: the four spec documents that were not compared with the code

Repository `/home/user/lonorabot`, audited at 9f5b1da (the checkout is now 0a03960; `git diff --name-only 9f5b1da HEAD` lists only files under `docs/research/lonora-runtime-notes`, so every code line cited here is unchanged). Read-only audit. Where this file and `production-trace.md` differ, the trace wins. Every `path:line` below was re-opened after writing (see "Citation check" at the end).

Reproduction of everything marked RUN (pure functions of the real runtime; no database, no model; the only SCRIPTED part is which calls are fed in):

```
cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 8 && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/g3_spec_baseline.py
```
Raw output: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/g3-spec-baseline.txt`.

## 0. Summary of verdicts

| Item | Verdict |
|---|---|
| Plan R06 `:126` "Simple requests get direct execution" | FAILS in production; it is a sentence in a plan and prompt text, no runtime mechanism enforces it, and the first step the prompt prescribes (`market_symbols`) is not in the model's native tool list (it is reachable only through `tool_environment` + `tool_call`, which the model did not use) |
| Plan R06 `:132` "Expose stable error codes and parameters through existing contracts" | HOLDS for the Web/Mobile UI layer; FAILS for the chat reply. The sentence can be read as licence to show codes (see 1.2): it never says the code stays out of the owner-facing text, and no prompt line forbids quoting one |
| Plan R06 `:133` "Ask for clarification only when..." | FAILS as a rule: stated three different ways in the prompts, one of which (`lonora.md:225`) asks without the "cannot be inferred safely" test, and nothing in the runtime checks that a question was necessary |
| Study `:60` baseline gap "ordinary errors lose recovery metadata" | FIXED in code, but the recovery block it now attaches is generic: for `*_not_found` it names no tool and no candidates (this is exactly what the model got in production) |
| Study `:60` baseline gap "`advance_guard` ... aborts at repetition six" | FIXED: `advance_guard` no longer exists; replaced by result-aware guardrails whose 6th identical effect is blocked and never run. The doc `S19_CONTINUITY_AUDIT.md:37` still describes the old behaviour (stale doc) |
| Study `:60` baseline gap "hard 120,000-character guard replaces the entire result" | FIXED: ids/status are kept (RUN C) |
| Harness review `:15-16` vs `trace-guards.md` | Reconciled: the doc forbids using prose as PROOF of monitoring; the gates ignore «أراقبه» because they never run for chat runs, which is a different reason (scope), and nothing in the doc forbids a check that makes the claim require evidence |
| ADR 0001 `:17-19` | Holds as decision text. "No second runtime" holds in the code layout; the voice-handoff rule is the subject of another file (gap-1), only cross-checked here |

---

## 1. NANOBOT_PARITY_AND_RELIABILITY_PLAN.md, R06 (lines 122-135)

Section title (`docs/lonora-specs/NANOBOT_PARITY_AND_RELIABILITY_PLAN.md:122`): "R06 — Intelligent, Smooth, and Truthful Interaction". Its first paragraph (`:124`) already promises: "The user states an outcome naturally; Lonora selects tools, Skills, and delegation without making the user learn internal names, fixed commands, permission tiers, or worker topology."

### 1.1 `:126` "Simple requests get direct execution; complex work gets a concise plan only when useful."

Verdict: FAILS in production. Needed-for-safety refusals are not the cause here.

What the code/prompt side says:
- Prompt text agrees: "Do not ask the owner whether to perform analysis, inspect a chart or build a plan they already requested: do that reversible work first." (`packages/agent-runtime/resources/system/lonora.md:135`) and "Under active signed full management, choose size, stops and targets from current analysis within broker constraints; do not ask the owner to choose routine trading parameters." (`lonora.md:337`); the tool policy says "continue the already requested reversible work in the same turn" (`packages/agent-runtime/resources/constitution/tool-policy.md:3`).
- Nothing in the runtime enforces it. A chat run with no Task has no end-of-turn check at all: `task_progress` returns `None` when the run has no `task_id` (`packages/agent-runtime/src/lonora_agent/stop_gates.py:154-155`) and `task_stop_gate` then returns `continue_turn=False` (`stop_gates.py:180-181`). So an offer or an announced plan ends the turn unchallenged by the Task stop gate. Correction (checker): this is not "no end-of-turn check at all"; chat runs still pass the financial-truth gates and privacy redaction, and `final_answer` can append the uncertain-outcome line (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:179-183`), but none of those looks at offers, plans or unsupported "I am watching" claims (`trace-guards.md:508-512`).

What production shows (trace, not scripted):
- The model was offered only 23 native tools; `market_symbols`, `watch_cancel`, `watch_list`, `trade_close_positions` are not among them (`production-trace.md:20`, and `TIMELINE_CORRECTION.md` point 2). Yet the prompt for an unbound market says "for a single-symbol recommendation first discover the exact symbol with market_symbols" (`packages/agent-runtime/resources/prompts/trading_context.md:5`). `market_symbols` exists as a tool (`packages/tools/src/lonora_tools/market.py:98`; its description says "Use before guessing broker symbols or aliases; suffixes matter.", `market.py:100-101`) but is not in the offered list. Correction (checker): that does not make it unavailable "by construction". Native tools are a working set; the bridge description says "Invoke any listed capability that is not in your native tool list by its exact name" (`packages/tools/src/lonora_tools/registry.py:169`) and `tool_environment` says "Call a discovered tool that is not in your native tool list through tool_call" (`registry.py:157-160`; also `lonora.md:122`). `TIMELINE_CORRECTION.md` point 2 says the same for the watch/close tools: "reachable only through tool_environment and tool_call". So the step was reachable but not led: nothing tells the model, at the moment of `symbol_not_found`, to use the bridge for `market_symbols`. The same prompt line also warns "Gold may have broker suffixes or a different broker name; never guess or strip them." (`trading_context.md:5`); the model guessed `XAUUSD` anyway (missed by the first draft).
- Gold run 1ae9a14c: the model guessed `XAUUSD`, got `symbol_not_found`, then `broker_account_not_found`; it never called `tool_environment` although both recovery blocks pointed to it (`production-trace.md:246-248`, `:238`). Owner then had to type the suffix.
- Size question [24]: balance 13944.57, quote and contract (`volume_min` 0.01) were in hand (`production-trace.md:250-252`) and the model still asked (`TIMELINE_CORRECTION.md` point 13). Where the "choose your own lot size" instruction lives is the subject of another file; not re-derived here.
- `account_read` showed `"stop_loss":null,"take_profit":null` (`production-trace.md:254`); the plan was announced and nothing was set (`TIMELINE_CORRECTION.md` point 14).

Class of these outcomes: RECOVERABLE-NOT-LED for the symbol case (the owner-facing reply was an offer to do a safe read-only search that the agent could have run itself); BUG-shaped (announce without act) for [37]/[39]; the missing tools are a visibility issue being handled by another session (not designed here).

### 1.2 `:132` "Human-facing text uses localization keys with Arabic and RTL support. Symbols, IDs, prices, and URLs remain readable. Expose stable error codes and parameters through existing contracts, not inconsistent hardcoded messages."

Verdict: HOLDS for the apps; FAILS for the agent's chat reply; and the second sentence is ambiguous in a way that can be read as licence to show codes.

Where it holds: the Web layer maps codes to localized text. `apps/web/src/lib/user_error.ts:150-151` maps `symbol_not_found` to "This exact symbol is not available from your broker." and `:156-157` maps `broker_account_not_found` to "Broker account not found." The function is built on `errorCode(error)` and shared text from `@lonora/core` (`user_error.ts:14-26`). This is the "stable code through existing contract, localized text on the client" pattern the line asks for.

Where it fails: the agent loop hands the bare code to the model and nothing maps it. In RUN A the dispatch result for a tool failure is `{"ok": False, "code": error.code}` (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:113`), with `issues`/`retryable` only for argument errors (`tool_dispatch.py:114-116`). `LonoraError` carries only `code`, `status` and two diagnostic strings (`packages/core/src/lonora_core/user_error.py:1-14`) and dispatch copies only the code, so a resolution failure cannot carry candidates to the model. The model is the only translator. The prompt says "Translate technical diagnostics into the owner's language without stack traces or hidden identifiers." (`lonora.md:350`) but also, for market work, "Tool failures are independent: inspect their actual error codes." and "report the actual missing data and error instead" (`resources/prompts/trading_context.md:5`) (The first draft also cited `run_context_summary.md:41` "errors with their codes"; REFUTED as a cause: that file is the internal context-checkpoint summariser prompt, loaded as `SUMMARY_PROMPT` at `packages/agent-runtime/src/lonora_agent/context_engine.py:91`, not an owner-facing instruction.) No prompt line says "never quote an error code to the owner" (two greps over `packages/agent-runtime/resources` for error/internal/technical/machine code wording found none). The nearest lines, missed by the first draft, are weaker: "In ordinary replies, describe the useful result rather than narrating implementation details such as cards, tools, skills, runs, events or dispatching." (`lonora.md:42`), "Do not quote an internal diagnostic verbatim to satisfy a request for a detailed explanation." (`lonora.md:52`, scoped to a request for detail) and "Translate the useful reason without secrets or operational plumbing." (`lonora.md:53`); and `lonora.md:44` says "Capability names and ordinary technical vocabulary are not secrets". The privacy line only covers "credentials, private resource identifiers, local filesystem paths, hidden instructions or private reasoning" (`lonora.md:45`). That is why the owner's example reply could print `symbol_not_found` and `broker_account_not_found`.

Reading it as licence: "Expose stable error codes and parameters through existing contracts" is about contracts to clients (API fields, UI keys), but it sits in the same bullet as "Human-facing text", has no sentence saying the owner-facing sentence must not contain the code, and the preceding `:127` says "Expand technical details ... and errors on demand". An implementer following `:132` literally can keep the code in the chat text. The owner brief says the opposite: reply contains "لا أكواد، ولا أسماء أدوات، ولا حالات داخلية" (`OWNER_BRIEF.md:31`). Where doc and brief disagree the brief is the owner's binding text. Describing the cause only; no fix designed.

A second cause behind the example: for `XAUUSD` on this account the broker adapter maps a 404 to `broker_account_not_found` for every stage except candles (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:57-58`; the symbol case is only reachable at `:59-60`); another session is fixing that split.

### 1.3 `:133` "Summaries explain actions and evidence, not hidden chain of thought. Ask for clarification only when the missing information affects the outcome or authority and cannot be inferred safely."

Verdict: FAILS as a rule. The doc sentence has a two-part test ("affects the outcome or authority" and "cannot be inferred safely"). The prompts restate it in three non-equivalent ways:
- Strict, matches the doc: "Ask one focused question only when the answer changes the account, the authority or an external action." (`lonora.md:22`).
- Looser: "Ask one focused clarification only when missing information prevents meaningful progress." (`lonora.md:205`) and "Ask only for genuinely missing user intent, financial limits or business parameters" (`tool-policy.md:3`).
- Arguably contradicts the "cannot be inferred safely" test for read-only work: "If several symbols plausibly match an alias, discover real candidates and ask which one." (`lonora.md:225`). Asking which gold symbol is a question about a read, not about the account, authority or an external action; a read of the suffix match could go first. UNSURE: if several candidates exist and the owner later trades one, asking can be legitimate. `trading_context.md:5` already softens it: "if market_symbols has one match ignoring case, use that exact spelling and do not ask the owner to retype it."
- Also "Ask for owner preferences or missing financial limits; derive technical entry, invalidation, size and target proposals from current broker evidence when the owner's limits allow it." (`lonora.md:136`), against `:337` (do not ask the owner for routine trading parameters under signed management). The model asked for size anyway ([24]).

Runtime check: none. The `wait_for_input` handler validates only the `execution_authorization` purpose (`packages/tools/src/lonora_tools/runtime_control.py:64-73`), wording privacy (`:74-82`) and a pending approval (`:83-98`), then returns `{"_runtime_wait": True, ...}` (`:100`). It never tests whether a safe read-only step was still available. The two production question cards were the model's own `wait_for_input` calls (`TIMELINE_CORRECTION.md` point 15). The only stop-gate text that tells the model not to "ask routine trading questions" is inside the continuous-task nudge (`stop_gates.py:45-54`, wording at `:52-53`; `lonora.md:337` is separate and conditional on signed full management), which a chat run never receives (see 2.3).

Classification of the "asked instead of acting" outcomes seen: size question [24] BUG-shaped/technical-question; "أبحث لك ... إذا أردت" RECOVERABLE-NOT-LED (a safe read-only search was available).

---

## 2. NANOBOT_ARCHITECTURE_STUDY.md:60 baseline gaps: still in the code?

Quoted gap line (`docs/lonora-specs/NANOBOT_ARCHITECTURE_STUDY.md:60`): "ordinary errors lose recovery metadata; the hard 120,000-character result guard replaces the entire result with `tool_result_too_large`; `advance_guard` counts the latest tool/argument hash without error classification and aborts at repetition six; retry timing/attempt state is not a coherent tool-environment contract."

### 2.1 "ordinary errors lose recovery metadata": fixed, but generic

- `observe` attaches `result["recovery"]` to every failed result (`packages/agent-runtime/src/lonora_agent/environment.py:203-210`), built by `classify` (`environment.py:35-93`), with attempt count and retry exhaustion (`environment.py:205-209`). It is called for every recorded call (`packages/agent-runtime/src/lonora_agent/tool_block.py:300`).
- RUN A (SCRIPTED calls, real `observe`) reproduces the production block byte for byte:
  `{"ok": false, "code": "symbol_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}` and the same for `broker_account_not_found` (attempt 2). Production: `production-trace.md:246`.
- So the gap as written is closed. The residue is what the block says: every code ending `_not_found` gets the same `category "not_found"` and `next_action "inspect_existing_state"` (`environment.py:80-81`); the action string names no tool and no candidates, and `schema_tool` is always `tool_environment` (`packages/contracts/src/lonora_contracts/tool_environment.py:31`; the `not_found` category is at `:18`). Production: the model "ignored" both hints (`production-trace.md:238`); `tool_environment` was called once in the whole conversation, and for a different purpose, returning an empty list (`TIMELINE_CORRECTION.md` point 4).
- Safe retry is only for transient read codes (`environment.py:92`; the set at `packages/core/src/lonora_core/runtime_failure.py:10-21`). `*_not_found` is never retried by the runtime.
- Doc/code: the study line says metadata is lost; code says it is attached. Code wins.

### 2.2 `advance_guard` abort at repetition six: gone, replaced

- `advance_guard` does not exist in the code: a search of `*.py` finds no definition or use; only docs name it (`docs/lonora-specs/NANOBOT_ARCHITECTURE_STUDY.md:60`, `docs/lonora-specs/S19_CONTINUITY_AUDIT.md:37`). The replacement removes the old state key: "The previous single-key repeat counter raised a Run failure; it is retired." (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:177-178`) and the constants say "The previous release failed the Run on the 6th identical success, after that effect had already run; now the 6th never executes." (`tool_guardrails.py:65-67`).
- It is now result-aware: failures are counted by exact signature and per tool (`tool_guardrails.py:329-337`), identical reads by result digest (`:347-356`), identical effects by arguments only (`:357-373`), cycles up to period 4 (`:72`, `:421-446`). `S19_CONTINUITY_AUDIT.md:37-41` is therefore a stale description; code wins.
- RUN B (SCRIPTED: `watch_create` with identical arguments, 8 times, real `before_call`/`after_call`): calls 1 executed; calls 2-5 executed with `identical_effect_warning`; call 6 NOT executed, `action=block code=identical_effect_block`: "watch_create was not executed: it already ran 5 times in a row with identical arguments in this run, and this call changed nothing. Use the earlier results, change the request, or report to the owner."; call 7 `halt` `identical_effect_halt`. Thresholds: `tool_guardrails.py:68-71`, block/halt logic `:240-257`.
- What a halt does to the owner: the run does not fail; the loop takes a graceful finish (`packages/agent-runtime/src/lonora_agent/tool_loop.py:400-401` selects reason `guardrail_halt`; `:453-455` finishes after the halting call), and the model is told "This run stopped a repeating tool loop ... No tool call will execute any more. Write the final reply to the owner now, in the owner's language ..." (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:117-129`). So the final wording that reaches a chat owner after a halt is model-written. Correction (checker): there is also a fixed fallback on this path: `text = reply.text.strip() or limit_fallback(prefers_arabic(messages))` (`packages/agent-runtime/src/lonora_agent/tool_loop.py:284`), used for both `tool_round_limit` and `guardrail_halt` when the model's finish reply is empty or the model is unavailable (`tool_loop.py:273-279`); its Arabic text, "توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.", says "limit" even after a repeat-loop halt (`runtime_notices.py:132-139`). The Task-attention Arabic texts are `runtime_notices.py:142-162`.
- Side observation (production, ddae66ad): its saved guardrail state shows `effect_streak [hash,2,0]` and no halt, and the third `watch_create` was an idempotent upsert returning the same id as the second (`production-trace.md:233`). A streak of 2 only produces a warning inside the tool result (`tool_guardrails.py:68`, `:370-373`), so the guardrails could not have stopped that reply (see 3.2).
- Needed-for-safety: the block of the 6th identical effect and the "no resend on ambiguous" route handling (`tool_dispatch.py:70-81`) exist so a loop cannot repeat money-moving effects; they are not what produces the owner's complaint.

### 2.3 "hard 120,000-character result guard replaces the entire result" (same line): fixed

`result_content` stores an oversized result and gives the model a bounded form (`packages/agent-runtime/src/lonora_agent/tool_block.py:252-276`); `bounded_result` keeps `code`, `status`, `operation_id`, `broker_reference`, `artifact_id`, `approval_id`, `chart_id`, `id`, `symbol` (`environment.py:246-258`) and keeps the ambiguity marker (`environment.py:260-271`). RUN C (SCRIPTED 208,089-character `trade_execute` result): the model gets `"status": "filled", "operation_id": "op-123", "symbol": "XAUUSDm"` with `result_omitted: true` and a `narrow_query` recovery. RUN C had no database, so storage failed and the fallback marked `"result_persisted": false, "result_storage_error": "tool_result_storage_unavailable"`; that is the documented fallback path (`tool_block.py:263-275`), not a defect of the main path.

### 2.4 Failure outcomes in `tool_dispatch.py` classified (reader rules)

Result codes produced in `tool_dispatch.py`, and what `classify` then attaches (`environment.py:35-93`). Class column is my judgement from the code only.

| Outcome (source) | Recovery attached | Class |
|---|---|---|
| `tool_arguments_invalid` with `issues`, `retryable: true` (`tool_dispatch.py:114-116`) | `inspect_schema_and_repair` (`environment.py:38-39`) | RECOVERABLE (led) |
| any `LonoraError` code, e.g. `symbol_not_found` (`tool_dispatch.py:113`) | by suffix; `*_not_found` -> `inspect_existing_state` (`environment.py:80-81`) | RECOVERABLE-NOT-LED |
| `tool_read_timeout` / `tool_connection_failure` for a read tool (`tool_dispatch.py:119-128`) | `temporary_unavailable`, `safe_to_retry` true, runtime retries (`environment.py:44-45`, `:92`; `tool_block.py:309-328`) | RECOVERABLE (runtime-led) |
| `tool_internal_failure` for a read tool (`tool_dispatch.py:133-137`) | no transient classification; default `terminal_domain_failure` / `alternate_route` (`environment.py:36-37`) | RECOVERABLE-NOT-LED |
| `tool_execution_uncertain` for a non-read tool (`tool_dispatch.py:95`, `:126-127`, `:136-137`) | `ambiguous_mutation` / `reconcile_before_any_resend` (`environment.py:42-43`) | NEEDED FOR SAFETY (OWNER-NEEDED if unresolved) |
| `broker_result_ambiguous`, `tool_route_exhausted` for a blocked route (`tool_dispatch.py:70-80`) | `reconcile_before_any_resend`; the exhausted-route case is later overwritten by the generic default (`environment.py:210`) | NEEDED FOR SAFETY / DEAD-END if the route stays exhausted |
| `guardrail_blocked` (`tool_guardrails.py:302-310`) | message says "report to the owner" | NEEDED FOR SAFETY (loop bound) |
| `approval_required`, `device_*_required` (`environment.py:50-55`) | `request_owner_authorization` | OWNER-NEEDED, needed for safety |
| `risk_*` (`environment.py:70-73`) | `inspect_risk_assessment` | RECOVERABLE (resize), needed for safety |
| `*_unconfigured`, `model_not_configured`, `search_not_configured` (`environment.py:74-79`) | `inspect_authorized_alternative` | OWNER-NEEDED |

Count of the 10 rows above by primary class (recounted by the checker; the first draft's "families as FailureCategory" label and its safety total of 4 did not match the table): RECOVERABLE (led) 3 (rows 1, 3, 9), RECOVERABLE-NOT-LED 2 (rows 2, 4), NEEDED FOR SAFETY 3 (rows 5, 6, 7), OWNER-NEEDED 2 (rows 8, 10; rows 8 and 9 are also needed for safety). Row 6 is DEAD-END only conditionally. BUG 0 in the dispatch layer itself. Categories are `FailureCategory`, `packages/contracts/src/lonora_contracts/tool_environment.py:9-24`. UNSURE: whether the BUG count is really 0 for `tool_route_exhausted`: I did not run a blocked-route journey.

---

## 3. AGENT_HARNESS_SOURCE_REVIEW.md:15-16 versus the guards

### 3.1 What the doc says
`docs/lonora-specs/AGENT_HARNESS_SOURCE_REVIEW.md:11-17`: the typed `StopGateVerdict` and bounded protocol nudge are adapted from Hermes; "Unlike the reference's unrelated coding gates, Lonora checks its real persisted Task identity and requires actual suspension. No English intent regex or claim such as "I will monitor" proves a continuation. Two checkpointed nudges bound a review; exhaustion is an inspectable plan-repair failure, not fake completion or endless self-polling."

### 3.2 What the code does (code wins where different)
- Prose never counts. `apply_stop_gates` takes no reply text at all (RUN D prints its signature: `(state, *, continuous, incomplete_steps)`), and its docstring says "No text classifier decides whether monitoring exists: the successful wait path settles it." (`stop_gates.py:95-96`); the file header says "Prose is an update, never proof of a saved monitoring or scheduling action." (`stop_gates.py:6`). This matches the doc line.
- Two nudges: `MAXIMUM_STOP_NUDGES = 2` (`stop_gates.py:41`); RUN D (SCRIPTED three final answers on a continuous task): #1 and #2 continue with the nudge, #3 `continue=False exhausted=task_wait_required`. Matches.
- Mismatch on the exhaustion outcome: the doc says "plan-repair failure". The code does not fail the Run: `StopGateVerdict.exhausted` is documented as "the held answer then goes to the owner as a resumable attention request instead of failing the Run" (`stop_gates.py:61-63`) and `request_owner_attention` makes a question with no choices (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:109-152`; called from `loop_outcomes.py:175-178`). The owner-facing text is deterministic and bilingual: "هذه المهمة المستمرة غير مراقَبة: لم يُحفظ أي انتظار مراقبة أو مؤقت مراجعة، لذلك لن تحدث أي متابعة تلقائية." (`runtime_notices.py:147-152`). Code wins; the doc's word is wrong or loose.
- Scope is what makes the gates ignore «أراقبه»: `task_progress` returns `None` for a run with no Task (`stop_gates.py:154-155`), so `task_stop_gate` returns `continue_turn=False` (`stop_gates.py:180-181`), and `final_answer` then just commits the text (`loop_outcomes.py:170-184`). `trace-guards.md` section (4) (line 357) covers 8114abdd, 6e4aa88f, 7e7da121, and section 6.5 (line 571) covers ddae66ad, e343c96a, fb1d4b5a; it concludes "each of the three replies is outside the stated scope of every existing check" (`trace-guards.md:585`).

### 3.3 Reconciliation
The doc's sentence is a statement of what may be accepted as proof: a text claim never substitutes for a saved wait. It says nothing against a check that REQUIRES evidence when the text makes a claim. Therefore:
- The doc is not "the documented reason the gates ignore «أراقبه»". The reason is structural scope (Task runs only) plus the fact that no reply guard keys on watch or monitor wording (`trace-guards.md` section 0 and 6.4). The doc's stance (no regex on prose as PROOF) is compatible with a guard that blocks or flags a claim lacking proof; the doc even implies "only a successful saved wait can support a promise" in the nudge text (`stop_gates.py:50-51`).
- The same stance is a design pull in the other direction for any fix that tries to detect «أراقبه» with a regex: the doc says no English intent regex; the existing effect-claim regex is trading verbs only and does not match «أراقبه» (`trace-guards.md:508`). Whether a structural alternative (watches or waits actually saved in this request's tool results) fits the doc's stance: it does, because it reads results and not prose. I describe the cause only.
- The chat-run gap is therefore a documented-scope gap, not a documented decision to ignore claims. The doc covers continuous TASKS (`AGENT_HARNESS_SOURCE_REVIEW.md:5-9`); it is silent about chat runs.
- Money-safety reading: none of this touches the single executor, grants or journals; it is about owner-facing truth, so any structural check here is outside the money-safety rule set.

---

## 4. ADR 0001, lines 17-19

Text (`docs/architecture/decisions/0001-agent-first-evolution.md:17`): "Extend the existing Agent, Gateway, tools, memory, and financial services. Do not install Hermes or Nanobot as a second runtime, and do not create a second task, trading, voice, or authorization authority." And `:19`: "A transcript synchronization failure must remain distinct from unintelligible speech; it must never create financial work from an incomplete utterance or tell the owner to repeat a request solely because the handoff is late."

Cross-check with code:
- No second runtime: the guards examined above are Hermes/Nanobot adaptations placed inside the existing runtime with MIT notices and no engine import (`stop_gates.py:1-29`, `tool_guardrails.py:1-41`), and the harness review says "No new Nanobot engine or local session database was imported." (`AGENT_HARNESS_SOURCE_REVIEW.md:20-21`). Holds.
- Relevance to the owner's complaint: ADR `:17` also names "do not create a second ... authorization authority", which is why every "needed for safety" refusal in section 2.4 (approval_required, risk_*, ambiguous reconcile) stays; ADR `:21` keeps "approvals where required, idempotency, execution journals, and broker reconciliation authoritative". Nothing in this gap suggests loosening those.
- `:19` voice rule: the ADR evidence line says tested with "all 14 cases in `tests/voice/test_live.py`" (`0001-agent-first-evolution.md:34`) and calls the voice change "a mitigation, not the final protocol redesign" (`:36`). Production note: the two voice notes were transcribed as Turkish gibberish with an empty `reply_language` (`TIMELINE_CORRECTION.md` point 9). That is a transcription-language issue, not the late-handoff case `:19` covers, so the ADR rule neither explains nor excuses it. UNSURE: I did not run the voice path in this gap (covered in `gap-1-voice-calls.md`).

---

## 5. What this does not claim
- I did not run a real model; RUN A-D feed scripted calls into the real runtime functions. No scripted reply is evidence of what a model would say.
- I did not reproduce the three production runs' databases; `trace-guards.md` and `production-trace.md` are their evidence.
- No repository file was changed: `git status --short` is empty.

## Citation check
Superseded by the independent check below.

## Verification log

Independent check against the code at 0a03960 (code identical to 9f5b1da, see header). Every cited line was printed with line numbers and read.

- Citations opened: about 115 `path:line` citations in the body (code, prompts, docs, and the audit's own `production-trace.md`, `TIMELINE_CORRECTION.md`, `trace-guards.md`, `OWNER_BRIEF.md`), plus the quoted study, plan, harness-review, S19 and ADR lines.
- Citations corrected: 10. `stop_gates.py:153-155` to `:154-155` (the body had it in three places; line 153 is the `identifier =` assignment); `stop_gates.py:51-52` to `:50-51`; `tool_dispatch.py:133-136` to `:133-137`; `:126-128` to `:126-127`; `:136-138` to `:136-137`; `runtime_failure.py:10-20` to `:10-21`; `tool_environment.py:10-24` to `:9-24`; `OWNER_BRIEF.md section 1` to `:31`; trace-guards run list made exact (section 4 vs 6.5); HEAD note. The "Citation check" paragraph was replaced.
- Verbatim quotes checked: all Arabic and English quotes match the source (plan lines 126/132/133, study line 60, harness review 15-17, ADR 17/19, `lonora.md` 22/45/135/136/205/225/337/350, `tool-policy.md:3`, `trading_context.md:5`, the `task_wait_required` Arabic text at `runtime_notices.py:147-152`, the guardrail block message). No quote needed changing.
- Reruns: `g3_spec_baseline.py` rerun with the same command; output identical to `runs/g3-spec-baseline.txt` (diff empty); copy at `runs/chk-g3-rerun.txt`. RUN A, B (calls 2-5 warn, 6 block, 7 halt), C and D match the body.
- Claims refuted or downgraded:
  1. REFUTED: "direct execution unavailable by construction" for `market_symbols`. The bridge (`tool_call`) reaches any listed capability (`registry.py:169`); reworded to reachable-but-not-led.
  2. REFUTED: `run_context_summary.md:41` as a cause of codes reaching the owner. It is the internal context-checkpoint summariser prompt (`context_engine.py:91`).
  3. DOWNGRADED: "A chat run with no Task has no end-of-turn check at all". Financial-truth gates, redaction and the uncertain-outcome line still run; only the Task stop gate is absent.
  4. CORRECTED: "the fixed Arabic fallback exists only for the round-limit and Task attention". `limit_fallback` is also used after a `guardrail_halt` finish when the model reply is empty or the model is unavailable (`tool_loop.py:284`).
  5. DOWNGRADED: `lonora.md:225` "contradicts" the inference test; now "arguably", with UNSURE.
  6. CORRECTED: "`LonoraError` has no details field"; it has code, status and two diagnostic strings, but dispatch copies only the code.
  7. CORRECTED: the class count of section 2.4 (safety total 4 did not match the table; recounted 3+2+3+2 = 10 rows).
- Absence claim "no prompt line says never quote an error code": CONFIRMED with two greps over `packages/agent-runtime/resources` (error/internal/technical/machine code wording; `codes` in `lonora.md`); nearest lines now cited.
- Absence claim "`advance_guard` does not exist in code": CONFIRMED (no match in `*.py`; only the two docs name it).
- Missed by the author, now in the body (5 added): the model ignored the suffix warning in `trading_context.md:5`; the `market_symbols` description ("suffixes matter", `market.py:100-101`); the bridge text and `lonora.md:122` that make the "missing" native tools reachable; `lonora.md:42/44/52/53` as the nearest plain-language lines; the exact fallback at `tool_loop.py:284`.
- Not re-verified: the message numbers [24], [37], [39] (from the audit's trace files; only lines 20, 233, 238, 246-254 spot-checked). UNSURE about `tool_route_exhausted` blocked-route behaviour (author did not run it, nor did I).
