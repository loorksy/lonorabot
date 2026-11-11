# Lonora agent harness: what exists today and where new behaviour can attach

Read-only study. All paths are relative to the repo root `/home/user/lonorabot`.

**Baseline.** `git fetch origin main` done. `origin/main` = `9f5b1da` ("Merge pull request #56 ... mobile-conversation-5c65", 2026-11-11 10:32 UTC). The working-tree branch `study/rakazo-philosophy` points at the same commit (`9f5b1da`), `git diff origin/main HEAD` is empty and `git status` is clean. So **working tree == origin/main in code**; every citation below holds for both. One unmerged remote branch touches the item-8 files: `origin/fix/broker-symbol-resolution` (`161b66c`, 7 commits ahead of main, not merged). It is reported separately in section 8.

Abbreviations: `AR/` = `packages/agent-runtime/src/lonora_agent/`, `TL/` = `packages/tools/src/lonora_tools/`.

---

## 1. `AR/tool_dispatch.py`: dispatching one tool call

One public function: `dispatch_call(context, registry, state, call, scope, *, interrupted, before_effect) -> dict` (`AR/tool_dispatch.py:22-31`). It is called only from `execute_segment` in `AR/tool_block.py:196` (serial) and `:233` (parallel reads).

Order of decisions inside it:

1. Stored receipt first: `stored_result(context, call)` (`:42`). If a receipt exists it is returned instead of running the tool (`:53-54`), except an `ambiguous` receipt of a financial replay-safe tool, which is dropped so the handler reconciles (`:43-52`).
2. Blocked route (same tool + same arguments failed 3 times, or is ambiguous; see `blocked_route` `AR/environment.py:127-131`):
   - ambiguous + financial + replay-safe: the ORIGINAL call id is re-executed to reconcile, and the result is tagged `_runtime_reconciled` (`:55-69`);
   - otherwise a synthetic refusal (`:70-81`):
     ```
     {"ok": False, "code": "broker_result_ambiguous" | "tool_route_exhausted",
      "recovery": {"next_action": "reconcile_before_any_resend" | "alternate_route_or_wait"}}
     ```
3. Interrupted (in-flight marker survived a crash) and the tool is not read-only / replay-safe: `{"ok": False, "code": "tool_execution_uncertain"}` (`:82-95`).
4. Otherwise: `before_effect()` (persist intent) then `registry.execute(call, context-with-skill-access, scope)` (`:96-108`). Success is wrapped as `{"ok": True, **result}` (`:109`).

**Argument validation / casting.** Not in this file. `ToolRegistry.dispatch` (`TL/registry.py:509-516`) runs: `prepare_market_arguments` -> `validate_arguments(tool.input_type, arguments)` -> `guard_market_tool` -> handler -> `scope_market_result`. `validate_arguments` is Pydantic `model_validate(...).model_dump(mode="json")`, so casting is whatever Pydantic coerces (`TL/schema.py:72-76`). A failure raises `ToolArgumentsError` with code `tool_arguments_invalid`, status 422, and at most 12 `issues`, each `{"path": [...], "type": <pydantic type>, "code"?: <machine code>}`; submitted values and free-text messages are never copied (`TL/schema.py:45-69`).

**Error envelope the model sees: confirmed.** For any `LonoraError`:
```
error_result: dict[str, Any] = {"ok": False, "code": error.code}      # tool_dispatch.py:113
if isinstance(error, ToolArgumentsError):
    error_result["issues"] = error.issues; error_result["retryable"] = True   # :114-116
```
So a domain error is `{ok:false, code}` only. `LonoraError` itself carries only `code`, `status`, `diagnostic_message`, `diagnostic_type` (`packages/core/src/lonora_core/user_error.py:1-14`); no details dict reaches the model. `stale_lease` and `skill_continuation_unavailable` are re-raised, not turned into results (`:111-112`).

Other failures:
- `TimeoutError` / `ConnectionError`: `tool_read_timeout` / `tool_connection_failure` for a read-only tool, else `tool_execution_uncertain` (`:118-128`).
- Any other exception: logged by type only; `tool_internal_failure` for a read, else `tool_execution_uncertain` (`:129-138`).

**What is added after dispatch.** `observe()` (`AR/environment.py:134-216`), called from `run_and_record_segment` (`AR/tool_block.py:300`), adds `result["recovery"]` on failure: `{category, next_action, safe_to_retry, schema_tool:"tool_environment", attempt, retry_exhausted}` (`AR/environment.py:203-210`; contract `packages/contracts/src/lonora_contracts/tool_environment.py:27-33`). Guardrail warnings are attached as `result["runtime_notice"]` (`AR/tool_block.py:332-334`, `AR/runtime_notices.py:55-64`). The result is serialized to JSON as the `tool` message (`AR/tool_block.py:358-359`); if over 120000 chars it is replaced by `bounded_result` plus a stored-artifact pointer (`AR/tool_block.py:252-276`, `AR/environment.py:234-297`).

So the full failure shape today is `{ok:false, code, recovery:{...}, [issues, retryable], [runtime_notice]}`: codes and enum-like hints, never a sentence about what to do with the specific object.

**Timeouts.** Applied in `ToolRegistry.execute` with `asyncio.timeout(tool.dispatch_timeout())` (`TL/registry.py:494-501`). Defaults: 45 s reads, 90 s mutations (`TL/base.py:15-16`); per-tool `timeout_seconds` overrides; financial tools are never wrapped (`TL/base.py:99-104`, enforced at registration `TL/registry.py:143-152`).

**Retries.**
- Automatic retry exists only for read-only tools with a code in `TRANSIENT_READ_CODES` (`AR/environment.py:92`; list at `packages/core/src/lonora_core/runtime_failure.py:10-21`). On `safe_to_retry` the loop schedules a backoff of `2**attempt` seconds, checkpoints and raises `ToolRetryScheduled` (`AR/tool_block.py:309-328`, `AR/environment.py:219-224`); the executor re-queues the Run (`AR/executor.py:261-304`).
- After 3 failures of the same route: `safe_to_retry=False`, `next_action="alternate_route_or_wait"`, `retry_exhausted=True` (`AR/environment.py:206-209`), and later identical calls are refused without running (`blocked_route`, `:127-131`).
- Mutations are never auto-retried; an uncertain one becomes an `ambiguous` route that blocks until reconciled (`:156-163`, `:181`).
- Loop guardrails (`AR/tool_guardrails.py`) sit before/after each call: warn after 2 identical failures (`:56`), halt after 8 failures of one tool (`:58`), block an identical read after 5 unchanged results (`:60`), halt after 5 identical calls or cycles (`:64`), block the 6th identical effect (`:69`). `before_call` `:277-299`, `after_call` `:313-400`, blocked shape `:302-310`.

**Attach points.**
- Richer error envelope: `tool_dispatch.py:113-117` is the single place where a `LonoraError` becomes the model's result. A new typed error subclass carrying a `details` dict could be merged here (the unmerged branch does exactly this for symbols, section 8).
- Per-code guidance: `observe()` at `AR/environment.py:203-210` already mutates the result; a "next step" sentence or candidates could be added there or via `attach_notice(result, kind, text)` (`AR/runtime_notices.py:55`).
- Pre-dispatch argument repair (e.g. symbol normalisation) already has a hook: `prepare_market_arguments` at `TL/registry.py:510`.

---

## 2. `AR/environment.py`: `classify` and the "environment" guidance

`classify(code, tool) -> dict` (`:35-93`) maps one error code to a `ToolRecovery` (`category`, `next_action`, `safe_to_retry`). Default is `terminal_domain_failure` / `alternate_route` (`:36-37`). Rules in order:

| Code | category | next_action | line |
|---|---|---|---|
| `tool_arguments_invalid` | invalid_tool_arguments | inspect_schema_and_repair | 38-39 |
| `tool_result_too_large` | result_too_large | narrow_query | 40-41 |
| ambiguous set | ambiguous_mutation | reconcile_before_any_resend | 42-43 |
| transient read codes | temporary_unavailable | inspect_health | 44-45 |
| version/stale-state conflicts | version_conflict | reload_authoritative_state | 46-47 |
| stale quote/evidence | stale_state | refresh_evidence | 48-49 |
| approval/device required | authorization_required | request_owner_authorization | 50-55 |
| not allowed / scope / restriction | permission_denied | respect_scope | 56-69 |
| `risk_*` | risk_limit_blocked | inspect_risk_assessment | 70-73 |
| `*_unconfigured` etc. | not_configured | inspect_authorized_alternative | 74-79 |
| **any `*_not_found`** | **not_found** | **inspect_existing_state** | **80-81** |
| reconciliation/health/disabled/emergency | health_blocked | wait_for_authoritative_recovery | 82-88 |

Confirmed: every code ending `_not_found` (symbol, watch, account, order, operation...) gets the same `inspect_existing_state` (`:80-81`). `symbol_ambiguous` matches no rule and falls to the default `terminal_domain_failure` / `alternate_route`.

`safe_to_retry` is true only for a read-only tool with a transient read code (`:92`).

The "environment" is a dict inside the Run checkpoint, `state["environment"]` (`environment_state`, `:96-101`): `routes` (per tool+arguments record, max 32, `:193-200`), `recent` (last 12 records, `:201`), `phase` (`recovering`/`working`/`waiting`, `:202`), plus `retry`, `wait`, `wait_update`, `last_wake`, `inflight_calls`. It stores codes and counters only, no reasoning or arguments (module docstring `:1-5`). The model never sees this dict directly; it sees only the `recovery` object attached to each failed result (`:210`) and, for a settled-unconfirmed result, `stale_state` / `reload_authoritative_state` (`:211-215`). There is no prose next-step guidance: `next_action` is a short token.

Other public pieces: `route_key(call)` hash of tool+arguments (`:31-32`); `expire_read_routes` clears exhausted read routes on real owner input or a wake (`:104-124`); `schedule_retry` / `retry_pending` (`:219-231`); `bounded_result` (`:234-297`); exception `ToolRetryScheduled` (`:27-28`).

**Attach points.** `classify` is the one table to extend per code (e.g. split `symbol_not_found` from other not-founds, give `symbol_ambiguous` its own action). `observe` (`:203-210`) is where a richer, code-specific hint can be written into the result. `ToolRecovery.next_action` is a free string up to 80 chars (`packages/contracts/src/lonora_contracts/tool_environment.py:29`), so new action tokens need no contract change; new fields do.

---

## 3. `AR/stop_gates.py`: every stop gate

There are exactly two gates, both about Tasks, both structural (no reply text is read: "No text classifier decides whether monitoring exists", `:95-96`). Entry: `task_stop_gate(context, state)` (`:178-184`) -> `task_progress` (`:149-175`) -> `apply_stop_gates` (`:86-129`).

| Gate | Fires when | State key | Exhaustion code |
|---|---|---|---|
| Continuous task | the Run is bound to a continuous Task and the model gives a final answer instead of a saved wait | `continuous_stop_gate` (`:42`) | `task_wait_required` (`:100`) |
| Incomplete steps | the Run is bound to a finite Task with declared steps not `completed`/`skipped` | `task_completion_gate` (`:43`) | `task_steps_incomplete` (`:102`) |

If the Run has no Task (`model_metadata.task_id` absent) the gate returns "stop" immediately (`:153-155`, `:180-181`). **Ordinary chat Runs therefore have no stop gate at all.**

What it does on a hit: returns `StopGateVerdict(continue_turn=True, nudge=...)` (`:129`). The caller `final_answer` appends the nudge as a `completion_check` runtime notice and returns `None`, so the loop takes another model turn (`AR/loop_outcomes.py:170-174`). Injected text: `CONTINUOUS_NUDGE` (`:45-54`) or `_steps_nudge` listing up to 12 unfinished steps (`:72-83`).

Limits: `MAXIMUM_STOP_NUDGES = 2` (`:41`). The counter lives in the checkpoint, so restarts cannot reset it (`:94-95`, `:108`); it resets only when the task plan revision changes (`:122-125`) or on real owner input / external wake (`reset_stop_gate`, `:66-69`, called from `AR/steering.py:47`, `AR/loop_restore.py:77,103`). After 2 nudges the verdict is `exhausted=<code>` (`:126-127`) and `final_answer` converts the held answer into an owner-attention question (`AR/loop_outcomes.py:175-178`, `request_owner_attention` `:109-152`) instead of failing the Run.

`TaskProgress.contract_satisfied()` (`:140-146`) is also used at the round limit to decide whether a Task may complete (`AR/tool_loop.py:308-311`).

**Attach points.** `apply_stop_gates` takes keyword conditions and picks one (key, code, nudge) triple (`:99-104`); a third condition (for example an unanswered open request in an ordinary chat Run) would be a new branch here plus dropping the "no Task -> stop" early return in `task_stop_gate` (`:180-181`). The verdict type, the bounded counter, the reset rules and the notice delivery are all reusable as they are.

---

## 4. The "reply guards from PR #42"

**Finding: the text-reading reply guards were removed before PR #42 merged. Only one structured guard survives.**

History (`git log --all --oneline | grep -i -E "guard|#42"`): `1a33626` added `reply_gates.py` ("reply guards for stop requests, effect claims and D5 code"); `c93a738`, `1514678`, `b8c495e` reworked it; the last commit of the branch, `67d5107` "keep only the structured uncertain-outcome line", deleted `reply_gates.py` (658 lines) and its two test files and added `uncertain_outcome.py`. Its message states that the completion-claim recogniser and its repair turn, the stop/resume guard, the owner-word tool promotion, the D5 code-block replacement and the limit refusal for memory notes were all removed because wording-based guards "kept failing in both directions". Merge commit `aa50e8e` therefore changed only `loop_outcomes.py`, `loop_restore.py`, `tool_loop.py`, new `uncertain_outcome.py`, two constitution files and three tool descriptions. `reply_gates.py` does not exist on main or in the working tree; a grep for inability/done-claim/reply_guard in `AR/` and `TL/` finds nothing.

What exists today:

**(a) Uncertain-outcome line** (`AR/uncertain_outcome.py`), the PR #42 survivor.
- Checks: structured tool results only, never wording (`:3`). For a Run the owner started by typing (triggers `user`/`group`, `:22`, `:40-48`), it reads every result of `trade_execute`, `trade_close_positions`, `goal_step_execute` since the request start (`:23`, `:78-112`), including nested and batch rows (`:51-62`) and reconciliations (`:105-109`). An operation is uncertain if its latest `status` or `code` is in `UNCERTAIN` (`:24-33`).
- On a hit: appends one fixed sentence in Arabic or English (`:36-37`, `:115-118`) to the reply text, to the stored assistant message and to the card (`append_uncertain_line`, `:134-152`). It never replaces the reply and never causes another model turn.
- Where it runs: at the final answer of a normal turn (`AR/tool_loop.py:595-609` with `outcome_line=True`, applied in `AR/loop_outcomes.py:179-183`) and on the round-limit / guardrail report (`AR/tool_loop.py:298-299`). Request start is recorded once on Run entry (`AR/loop_restore.py:57-58`).

**(b) Financial-truth gates inside `model_turn`** (older than PR #42, still the only reply rewriting), `AR/model_runtime.py:217-238`:
- text beside a proposed financial call is blanked (`:225-228`);
- if the latest financial result is `confirmed` but not independently verified, the whole reply text is replaced by a fixed sentence (`:229-232`; text at `AR/context/financial_result.py:121-125`);
- beside a `task_wait`, an unsettled result summary replaces the prose (`:233-238`).

**(c) Streaming-only effect-claim filter.** `EFFECT_CLAIM` regex (`AR/public_stream.py:11-19`) stops incremental streaming when the partial text looks like "I executed / تم تنفيذ" (`:47-51`); the final text is not altered by it. The same regex rejects a generated card (`AR/genui_compile.py:740-743`).

**(d) Privacy redaction** on the final text, section 9.

Not present: any check for inability claims ("I can't"), done claims in ordinary replies, or leaked internal codes. Those are prompt rules only (section 9).

**Attach point.** `final_answer` (`AR/loop_outcomes.py:155-184`) is the single choke point every final reply passes: it already supports "continue the turn with a notice" (`:170-174`), "escalate to the owner" (`:175-178`) and "append a line" (`:179-183`). A new structured check belongs here. The history above is a direct warning that checks reading the model's or owner's wording were tried three times and withdrawn; checks keyed on tool results or stored state fit the surviving pattern.

---

## 5. `tool_environment` and `tool_call` (the two bridge tools) and `tool_discovery.py`

Both are created inside `ToolRegistry.__init__` and cannot be registered by anyone else (`TL/registry.py:153-178`); names at `:62-63`, set `BRIDGE_TOOLS` `:74`. Both are always in the native tool list (`:288-289`, `:317`).

**How the model learns what exists.**
- Native schemas: a per-Run "exposure" chosen once and frozen in the checkpoint (`AR/tool_exposure.py:79-128`): eager profile tools (`core` + `market` or `research`, + `coordination`, + `task`; `:31-49`) plus up to 6 remembered long-tail tools within a 4100-char budget (`TL/registry.py:84-85`, `:270-304`). Successful long-tail use is remembered for later Runs (`AR/tool_exposure.py:151-181`).
- A capability inventory system message on every model turn: all permitted tool names grouped by toolset, max 8000 chars, with instructions to call non-native ones through `tool_call` and to inspect with `tool_environment` "before claiming an ability is absent" (`TL/registry.py:406-473`; inserted at `AR/model_runtime.py:66-75`).

**`tool_environment`** (input `EnvironmentInput`: `tool_name`, `query`, `offset`, `limit` 1..40; `TL/environment.py:10-19`), handler `inspect_environment` (`TL/registry.py:336-397`):
- `tool_name`: exact lookup among permitted tools; unknown or not permitted -> `tool_not_allowed` 403 (`:349-353`); returns `{tool: {...with input_schema, invoke, available}, invocation, execution_authorized: False}` (`:355-359`).
- `query`: `search_definitions` over permitted definitions, at most 12 results (`:361-366`); each entry has metadata plus `input_schema` while a 16000-char budget lasts, else `input_schema_omitted` + `required` (`:370-381`); returns `{tools, total, next_offset: None, invocation, execution_authorized: False}` (`:382-388`).
- neither: a page of all permitted tools without schemas (`:389-397`).
- Each entry: `name, purpose, side_effect, safe_automatic_retry, ..., crash_replay, batch_execution, toolset, invoke: "direct"|"tool_call", available, unavailable_reason?` (`TL/base.py:110-129`, `TL/registry.py:320-334`, `TL/environment.py:34-57`).

**`tool_call`** (input `BridgeInput {name, arguments}`, `TL/environment.py:22-31`). It is unwrapped before anything else sees it: `resolve_call` turns a well-formed bridge call into the real `ToolCall` with the same id (`TL/registry.py:180-208`), applied by `model_turn` via `resolve_calls` (`AR/model_runtime.py:202-203`, wired at `AR/tool_loop.py:512`). So guardrails, receipts, approvals and the financial gates see the real tool. A bridge call that cannot be unwrapped reaches `unresolved_bridge`, which only raises: `tool_call_target_invalid` (400), `tool_call_unresolved` (409), or `tool_call_target_unknown` (404) (`TL/registry.py:213-222`). Note `tool_call_target_unknown` does not end in `_not_found`, so `classify` gives it the default `alternate_route`.

**Search algorithm** `search_definitions(definitions, query, limit=12) -> list[str]` (`TL/tool_discovery.py:44-89`):
- Tokens: NFKC + casefold, split on non-word and underscore, Unicode-aware (`:40-41`). No stemming, no synonyms, no translation.
- Corpus per tool: name + description + top-level parameter names (`:52-57`).
- **Rarest-word gate:** `gate = min(query_tokens, key=(document frequency, token))` (`:62`). A tool is skipped unless it contains the gate token (`:69-73`). A query token that appears in no tool has frequency 0, so it becomes the gate and **every tool is skipped**: one unknown word in the query yields zero results. Exception: a query equal to an exact tool name always matches (`:67`, `:87`).
- Coverage: with 4 or more answerable tokens, a tool must contain at least half of them (`:63-64`, `:71`).
- Ranking: BM25-style score (`:74-86`), exact name first, ties by name (`:87-89`).

**Catalogue language.** English. Tool descriptions are English, and both the tool description and the `query` field say so: "using concise English catalog terms" (`TL/registry.py:157`), "Use English terms for the first-party catalog" (`TL/environment.py:16`). An Arabic query tokenizes fine but matches nothing in an English corpus, and by the gate rule returns nothing.

**Zero hits.** `search_definitions` returns `[]` (`:50-51` or an empty ranked list). `inspect_environment` then returns `{"tools": [], "total": 0, "next_offset": None, "invocation": ..., "execution_authorized": False}` wrapped as `ok: True`. There is no hint, no fallback to a looser match, no suggestion to list or to retry with other words. Because it is a successful read with an identical result, repeating it trips the no-progress guardrail (warn at 2, block at 5; `AR/tool_guardrails.py:59-60`).

**Attach points.** Zero-hit behaviour: `TL/registry.py:361-388` (add a hint or a fallback such as dropping absent tokens before choosing the gate). The gate itself: `TL/tool_discovery.py:62`. Catalogue language: the corpus line `:52-57` is where aliases or translated keywords could be appended per tool.

---

## 6. `scripts/genui_eval`: structure to copy for a `scripts/agent_eval`

Three files (185 / 498 / 885 lines) plus fixtures under `tests/fixtures/genui_decision/` (`cases.jsonl` with 109 cases, `contexts.json`, `tool_bank.json`, `recordings/`).

**`bank.py`: fake tools, real registry.** "The runner keeps every Tool's definition, order, validation and guards and swaps only handlers. No broker, network or model is reached from here" (`scripts/genui_eval/bank.py:1-6`).
- `fixture_registry(tools, calls)` loads the real tools and replaces each handler with one that records `{tool, call_id, arguments, answered}` and answers from the bank (`:162-185`). Pass-through real handlers: `skills_list`, `skill_view`, `wait_for_input` (`:35`). A tool missing from the bank is recorded and raises `eval_tool_not_executed` (`:30`, `:171-173`).
- Bank entry forms: a fixed `result`; or `by` + `results` + `otherwise` keyed on argument values; `contexts` overrides per case seed; `echo` for write tools; `{"error": code}` raises `LonoraError(code, 404)` (`:144-159`, `:131-141`).
- `materialize` substitutes real ids for `{account_id}`-style placeholders and shifts all timestamps to now (`:121-128`). `CONTRACTS` maps each bank result to the product contract model it must satisfy (`:38-79`).

**`run.py`: real model, real loop, disposable database.** It drives "Lonora's own prompt assembly, model router, provider adapter and tool loop (`execute_run` with the production lease and round limits)" (`scripts/genui_eval/run.py:3-10`).
- Requires `--live` (`:496-497`) and a PostgreSQL database whose name ends `_test`/`_verify`/`_ci` (`:79-85`). The provider key is a placeholder; a network proxy injects the real one (`:8-10`, `:61`).
- `seed` migrates a template database, creates the owner, model route, a simulation account and three extra agents through the real API in-process (`:131-177`).
- `run_case`: clone the template database, seed earlier turns, POST the owner message to `/threads/{id}/messages`, take a lease, set a `RecordingAdapter` on the router, call `execute_run(context, bank.fixture_registry(...), 120, 24)` under a 300 s timeout (`:347-383`, constants `:64-65`). Then it reads the Run row, the last assistant message, the checkpoint transcript and the tool exposure (`:385-396`).
- Record per case and sample: `case, sample, model, prompt_hash, status, error_code, reply, reply_tool_calls, transcript, requests, tool_calls, tool_exposure, usage, latency_ms, content, rich_content` (`:408-425`), scrubbed of run-specific ids and refused if it contains a key-shaped string (`:255-289`).
- Output: full runs go to `tests/fixtures/genui_decision/recordings/<model>-<date>.jsonl` (`--baseline` -> `recordings/baseline/`); partial runs to `.runtime/genui_eval/` (`:292-297`). Flags: `--model`, `--cases`, `--limit`, `--samples`, `--baseline` (`:486-494`).

**`score.py`: deterministic, offline.** "no model judge, no network, no database" (`scripts/genui_eval/score.py:1-8`).
- A case is one JSON line with `id, lang, domain, context{type,label,seed}, follow_up, message, shape, also, kind, checks, safety, single_label, tools_expected, expect_state, must_not, seed_id` (first line of `tests/fixtures/genui_decision/cases.jsonl`; loader `score.py:118-120`).
- `observe(record, case)` re-projects the recorded raw reply with today's production projector and derives the observed shape, kinds, tools called, violations (`:374-...`).
- `judge(case, samples)` takes the majority across samples and returns `expected / observed / consistency / shape_ok / kind_ok / route_ok / violations` (`:565-599`); a case passes with an accepted shape and no safety violation (`:602-604`).
- `score` aggregates metrics, slices (language, domain, follow-ups, safety; `:607-614`) and cases lost against the previous recording (`:627-...`); `gate` compares against `THRESHOLDS` (`:100-108`, `:782-797`); `report` prints Markdown (`:821-869`).
- `replay(records, cases, previous)` is the offline regression guard: same prompt hash, same compiled output, no safety violation, thresholds met (`:800-818`). It is exercised by `tests/test_genui_decision_eval.py` (imports the scripts at `:22-23`).

**For an `agent_eval`.** Reusable unchanged: the whole of `bank.py` (handler swap, error entries let a case script `symbol_not_found`), and `run.py`'s seed / clone / lease / `execute_run` / recording / scrub pipeline. Only `score.py` is specific to cards: a behaviour scorer would read the same record fields (`transcript`, `tool_calls`, `status`, `content`) and replace `observe` / `judge`. Real model for recording, deterministic replay for CI is the established pattern.

---

## 7. The loop, and where thread-level state can live

**Files.** `AR/executor.py` `execute_run(context, registry, lease_seconds, maximum_rounds)` (`:99-101`) wraps `AR/tool_loop.py` `execute_tool_loop(context, registry, maximum_rounds) -> LoopOutcome` (`:325-327`). "the one loop that drives every Run's model" (`AR/tool_loop.py:1-4`).

**Shape of one pass** (`AR/tool_loop.py`):
1. Restore the checkpoint from `RunRow.execution_state` (`:329-339`; `AR/loop_restore.py:31-65`), which builds the context on first entry and freezes the tool exposure.
2. Resume cases: resumed owner attention (`:365-366`), a pending question (`:367-379`), an external wait (`:380-389`), a new wake delivered as a `<runtime_wake>` user message (`:390-392`, `AR/loop_restore.py:91-114`).
3. `while True` (`:394`): cancellation and task checkpoints; limit check; run the pending tool block segment by segment (`:441-454`); merge steering; budget check; one `model_turn` (`:505-516`); append the assistant message, set `pending = reply.tool_calls`, checkpoint (`:580-589`); if no tool calls, go to `final_answer` (`:595-611`).

**Iteration limit.** `maximum_rounds` comes from settings `maximum_tool_rounds`, default 24 (`apps/api/src/lonora_api/env.py:97`; passed at `apps/worker/src/lonora_worker/runtime.py:14`). A "round" is one model turn (`state["rounds"] += 1`, `AR/tool_loop.py:566`). Task Runs get up to `MAXIMUM_SLICES = 4` slices of that size (`AR/continuation.py:20`, `:23-47`, `:50-93`).

**What happens at the limit.**
- With 2 or fewer executable rounds left, a `budget` notice warns the model (`AR/tool_loop.py:114`, `:486-488`; text `AR/runtime_notices.py:102-114`).
- When no executable round remains, or a guardrail halted, `finish_turn` runs (`:400-438`, `:472-485`): pending calls are closed as `tool_call_not_executed` (`:246-248`), a `work_limit` notice tells the model to write the final report from verified results only (`:251-255`; text `AR/runtime_notices.py:117-129`), and one tool-less model call is made (`:265-272`). Empty or failed -> fixed fallback sentence in Arabic or English (`:284`; `AR/runtime_notices.py:132-139`). The text is checkpointed as `state["limit_exit"]` so a restart reuses it (`:241-243`, `:300-301`).
- Ordinary Run: completes with `reply_outcome: "limited"` (`:314-322`). Task Run with an unsatisfied contract: becomes an owner-attention question, not a completion (`:302-311`).

**Steering by a new owner message.** New messages for a running Run are `SteeringRow`s (`packages/db/src/lonora_db/schema.py:405-411`; `user_interrupt_pending` and `consume_steering` at `packages/db/src/lonora_db/steering.py:9,26`).
- Between tool segments: an owner message supersedes calls that never started (`tool_call_superseded`); a call that may have started is reported `tool_execution_uncertain` (`AR/tool_loop.py:353-361`, `:443-445`; `AR/tool_block.py:50-95`).
- `merge_steering` appends the messages as `user` messages and, for real owner input, resets the stop gates and guardrails (`AR/steering.py:20-51`). It runs after the tool block (`AR/tool_loop.py:460-461`) and again after a tool-less reply, in which case the turn continues instead of finishing (`:592-594`).
- At a limit, owner input buys one new budget (`:402-410`, `start_budget_epoch` `AR/tool_intent.py:111-121`).
- `complete_run` refuses to complete while unconsumed steering exists, so the loop runs again (`packages/db/src/lonora_db/runs.py:364-370`; `AR/executor.py:255-260`).

**How the final reply is produced and persisted.**
- `model_turn` post-processes the provider reply: drops provider rich content (`AR/model_runtime.py:193`), splits off the suggested reply (`:195-201`), resolves bridge calls (`:202-203`), applies the financial-truth gates (`:217-238`), compiles cards (`:243-244`), redacts private spans (`:246`), publishes stream deltas (`:282-291`).
- `final_answer` applies the Task stop gates and the uncertain-outcome line and returns `LoopOutcome(text, metadata, waiting, external_wait, input_request)` (`AR/loop_outcomes.py:25-31`, `:155-184`).
- `execute_run` then either settles an external wait (`AR/executor.py:131-141`), or writes a question message and sets the Run `waiting_input` (`:142-254`), or calls `complete_run` (`:255-257`), which inserts the assistant `MessageRow` (content, rich content, suggested reply), settles the stream, emits `message.created`, and sets `status="completed"`, `result=answer` (`packages/db/src/lonora_db/runs.py:360-425`).

**Where state lives today.**
- **Per-Run:** `RunRow.execution_state` JSON (`packages/db/src/lonora_db/schema.py:397`), written only by `persist` (`AR/tool_loop.py:117-126`). Holds `messages`, `pending`, `rounds`, `environment`, `tool_guardrails`, the stop-gate counters, `tool_exposure`, `pending_input_request`, `input_requests` (last 20, `AR/executor.py:209-212`), `limit_exit`, `owner_started`. It ends with the Run: a new owner message in an idle thread starts a new Run whose context is rebuilt from thread history.
- **Per-thread, generic:** `ThreadRow` has `context_summary`, `summary_seq`, `title`, and `options` JSON, described as "Per-chat options the agent reads ({"web_search": bool})" (`packages/db/src/lonora_db/schema.py:220-240`). `thread_options` reads only `web_search` and ignores unknown keys; `set_thread_options` merges keys (`packages/db/src/lonora_db/threads.py:13-16`, `:30-35`). **There is no per-thread conversational state store** (no "pending offer" / "open request" record). A pending offer made in an earlier Run exists only as prose in the message history.
- **Durable resource tables that carry `thread_id` + `state` + `payload` + `version`** (`ResourceRow`, `schema.py:661-673`): tasks are `TicketRow` / `ln_tickets` (`:750-751`; the Task lives in `row.state["task"]`, bound to a Run by `payload["run_id"]`, `AR/stop_gates.py:156-166`), watches `MarketWatchRow` / `ln_market_watches` (`:775-776`), trading goals `TradingGoalRow` / `ln_trading_goals` (`:836-837`), agent goals `AgentGoalRow` / `ln_agent_goals` (`:718-721`), scratchpad `ScratchpadRow` / `ln_scratchpad` (`:697-698`; tools `scratchpad_read` / `scratchpad_write`, `TL/scratchpad.py:41-48`). Owner cards: `OwnerActionRow` / `ln_owner_actions` (`:965-974`); trade approvals `TradeApprovalRow` / `ln_trade_approvals` (`:862-863`).

**Attach points for a thread-level "open request / pending offer".** (1) Smallest: a new key in `ThreadRow.options` JSON; needs `thread_options` to stop ignoring it but no migration. (2) A new `ResourceRow` subclass keyed by `thread_id` (migration, but versioned and evented like watches). (3) Reuse `ln_tickets`: a Task already gives a Run declared steps, a stop gate and owner-attention escalation, so "open request" modelled as a light Task gets the gate in section 3 for free. Whatever store is chosen, it would be read in `build_context` (`AR/context/builder.py:55`, called at `AR/loop_restore.py:54-55`) and checked in `final_answer`.

---

## 8. Four specific claims: confirm or refute

Working tree and `origin/main` are the same commit, so each verdict below is for both. The unmerged branch is noted per item.

**8a. `TL/symbols.py` `catalog_symbol`: exact or case-only match. CONFIRMED.**
```
if symbol in catalog: return symbol                      # symbols.py:9-10
matches = [n for n in catalog if n.casefold() == folded] # :11-12
if len(matches) == 1: return matches[0]                  # :13-14
raise LonoraError("symbol_ambiguous" if matches else "symbol_not_found", 404)  # :15
```
No suffix/prefix handling ("XAUUSD" does not find "XAUUSDm"), no common names ("gold", "الذهب"), and the error carries no candidates. `canonical_broker_symbol` swallows the error and returns the input unchanged unless `require_exists=True` (`:18-35`); callers that require existence: `TL/market.py:78`, `TL/market_analysis.py:140,215,305`, `TL/owner_actions.py:85`; callers that do not: `TL/market.py:47,58,65`, `TL/chart_indicator.py:20`, `TL/trade.py:634`.
*Unmerged `origin/fix/broker-symbol-resolution`:* rewrites this file (+246 lines): adds `SymbolNotResolved(LonoraError)` with `details = {requested_symbol, candidates, next, similar_symbols?}`, and `catalog_symbol` raises it; adds `order_symbol`, `read_symbol`; and adds three lines to `tool_dispatch.py` after line 116 that merge `error.details` into the model's error result.

**8b. `packages/market/src/lonora_market/instruments.py` `resolve_instrument`: exact match only. CONFIRMED, and it is dead code.**
The whole file is 9 lines: `matches = [item for item in instruments if item.symbol == symbol]`; not exactly one match -> `LonoraError("broker_symbol_not_found", 404)` (`:5-9`). Case-sensitive, no normalisation. A repo-wide grep finds no caller outside its own definition (none in `packages/`, `apps/`, `scripts/` or `tests/`).
*Unmerged branch:* keeps this function unchanged and adds about 100 lines of catalogue matching beside it (codes wrapped in broker affixes, common names).

**8c. `packages/adapters/src/lonora_adapters/brokers/metaapi.py` `provider_error` 404 mapping. CONFIRMED: a 404 outside the candles stage is always reported as a missing account.**
```
if status == 404:                                              # metaapi.py:52
    ...
    if stage != "candles" or "account" in message and missing:  # :57
        return LonoraError("broker_account_not_found", 404)     # :58
    if "symbol" in message and missing:                         # :59
        return LonoraError("symbol_not_found", 404)             # :60
    return LonoraError("broker_candles_not_found", 404)         # :61
```
Because of operator precedence (`stage != "candles"` OR (...)), any 404 from an RPC call, including a symbol specification or price read for an unknown symbol, becomes `broker_account_not_found`. RPC failures are diagnosed with stage `"rpc"` (`:434`). Combined with section 2, the model sees `{ok:false, code:"broker_account_not_found", recovery.next_action:"inspect_existing_state"}` for a mistyped symbol.
*Unmerged branch:* adds a `stage == "symbol"` branch returning `symbol_not_found` and passes stage `"symbol"` for `get_symbol_*` RPC methods.

**8d. `TL/market_watch.py` cancel / steer restricted to the calling agent's own watches. CONFIRMED.**
`steer` passes `agent_id=context.agent_id` to `control_watch` (`TL/market_watch.py:172-182`); `cancel`, `pause`, `resume` all go through `steer` (`:191-200`); `update` passes `context.agent_id` to `steered_watch` and `update_watch` (`:209-218`). `steered_watch` raises `market_watches_not_found` (404) when the row is missing, belongs to another owner, or `agent_id` is given and differs: "Another agent's watch reads as not found, so an agent can neither steer nor probe it" (`packages/db/src/lonora_db/market_watches.py:115-125`). `watch_list` also lists only this agent's watches (`TL/market_watch.py:148-157`). Tool descriptions say "one of your own watches" (`:255`, `:262`, `:269`, `:277`). Consequence: the Personal Agent cannot cancel a watch created by another agent even when the owner asks it to; it gets a not-found code with `inspect_existing_state`. Also, an agent resuming a watch held by the owner or a supervisor is refused unless its Run answers an owner message (`market_watches.py:168-171`).
*Unmerged branch:* does not touch `market_watch.py` or `market_watches.py`.

---

## 9. Owner-facing text: where it is produced, sanitised and localised

**Produced by the model**, then passed through `model_turn` (`AR/model_runtime.py:191-248`). Server-side processing of the final text, in order:
1. Suggested-reply trailer split off (`:195-201`; `AR/suggested_reply.py`).
2. Financial-truth replacement or blanking (`:225-238`), section 4(b).
3. Card compilation: `VisualReplyProjector.project` turns `lonora-ui` fences into `rich_content` and leaves the text alternative (`:243-244`).
4. Privacy redaction `redact_private_reply` (`:246`): replaces with `[REDACTED]` (a) credentials and key/token/password assignments, (b) private locations (`sandbox:`, `file://`, `/mnt/data`, `/workspace`, `/tmp`, internal XML-like tags), (c) UUIDs not in the verified public broker-id set (`packages/core/src/lonora_core/public_reply.py:10-26`, `:54-67`). "Safe replies are byte-for-byte unchanged" (`:57`).

**Not present server-side:** no markdown normalisation; no stripping of code blocks; no stripping of internal error codes or tool names (snake_case codes such as `symbol_not_found` pass through untouched: the module says "Public capability names and ordinary diagnostic vocabulary are not credentials. Presentation is owned by the model's instructions, not a keyword veto on replies", `public_reply.py:1-5`). The D5 code-block replacement that PR #42 briefly added was removed (section 4). These are prompt rules only: "Do not quote an internal diagnostic verbatim", "Translate the useful reason without secrets or operational plumbing" (`packages/agent-runtime/resources/system/lonora.md:52-53`), "Translate technical diagnostics into the owner's language without stack traces or hidden identifiers" (`lonora.md:350`).

**No server-side translation.** Language is handled three ways:
- Prompt: "Reply in the owner profile's reply_language, else the language of the owner's latest message" (`lonora.md:58`); "Respond in the user language; Arabic is fully supported" (`packages/agent-runtime/resources/constitution/identity.md:1`). The owner profile block gives the model `reply_language` or the literal `latest_owner_message` (`AR/context/memory.py:131`); the stored value is `ar` / `en` / null (`packages/db/src/lonora_db/schema.py:473,483`), set by `owner_preferences_update` or the API.
- Runtime-authored sentences are hard-coded Arabic/English pairs chosen by `prefers_arabic(messages)` (`AR/runtime_notices.py:84-93`): latest owner message containing Arabic letters -> Arabic; containing a space and 8+ Latin letters -> English; default Arabic. Used for the limit fallback (`AR/runtime_notices.py:132-139`), owner-attention text (`:142-203`), the uncertain line (`AR/uncertain_outcome.py:36-37`) and the unverified-broker line (`AR/context/financial_result.py:112-125`). Note this heuristic does not consult the profile's `reply_language`.
- A separate DB helper `conversation_locale` does consult the profile first, then the last 16 owner messages, then a setting (`packages/db/src/lonora_db/conversation_locale.py:13-35`); it is used outside the loop.
- Runtime notices to the model (`<runtime_notice>`, nudges, guardrail messages) are English and never shown to the owner (`AR/runtime_notices.py:18-31`).

**Attach point.** Any deterministic owner-facing sanitiser (code-token stripping, markdown clean-up) belongs next to `redact_private_reply` at `AR/model_runtime.py:246`, which is also the point after which the stream is reconciled with the final text (`:282-291`). New runtime-authored sentences should follow the existing AR/EN pair + `prefers_arabic` convention.

---

## 10. Money-safety enforcement points (brief)

| Invariant | Where | Notes |
|---|---|---|
| **Single executor** | `ExecutionService.execute` in `packages/trading/src/lonora_trading/execution.py:144-158`; one instance is built per runtime at `packages/gateway/src/lonora_gateway/runtime.py:73` | Every broker mutation goes through it. Tools reach it only via `trade_execute` etc. (`TL/trade.py:753`). The registry refuses financial tools outside a `full` scope, re-checking the Run row (`TL/registry.py:481-490`), and never wraps them in a timeout (`TL/base.py:99-101`). |
| **Idempotent operation journal** | `reserve_operation` in `packages/db/src/lonora_db/trading_journal.py:23-49`; table `TradingJournalRow` / `ln_trading_journal` (`packages/db/src/lonora_db/schema.py:676-694`) | One row per `operation_id`, inserted with `ON CONFLICT DO NOTHING`; a second request with the same id returns the stored receipt or `idempotency_conflict` (`execution.py:162-168`). **Strictly "append-only": not found.** The row's `status` and `result` are updated in place (`execution.py:252-254`, `:610-617`); each transition emits a `trading.operation_updated` event (`packages/trading/src/lonora_trading/operation_events.py:1-8`), and the owner-attestation audit event is documented as "events are never deleted" (`operation_events.py:114`). |
| **Signed grant (mandate)** | `require_authority` in `packages/db/src/lonora_db/account_authority.py:174-200`; executor-side terms in `require_account_execution`, `packages/trading/src/lonora_trading/account_authority.py:226-...` | Checks agent, `active` status, expiry, `request_hash(envelope) == envelope_hash`, scope, and that the signing device is not revoked (`:178-199`). Table doc: "Immutable signed account scope" (`schema.py:124`). Device proof verification: `verify_bound_assertion`, `packages/auth/src/lonora_auth/devices.py:281`. `grant_covers` runs the same check read-only before asking (`trading/account_authority.py:159-194`). |
| **Exact owner approval (trade card)** | `TL/trade.py:304` (approval id = `stable_id(run_id, "approval:" + call_id)`), pending -> `_runtime_wait` + `_runtime_retry` (`:399-404`), re-checked as `approved` inside the executor's `authorization` callback (`:430-438`; called at `execution.py:176-177`) | The loop turns `_runtime_retry` into a waiting outcome carrying `trade_approval_id` (`AR/tool_block.py:335-346`). Superseded proposals have their approvals cancelled (`AR/tool_intent.py:35-53`). |
| **Owner-only actions as cards** | Tool `owner_action_propose` (`TL/owner_actions.py:288-291`), handler `propose_card` (`:240-262`), table `OwnerActionRow` (`schema.py:965-974`) | "nothing changes until the owner taps it" (`TL/owner_actions.py:292-293`). Kinds include resume_trading, lift_restriction, resolve_operation, set_account_limits, grant_authority. |
| **Exits always admissible** | `require_trading(control, risk_reducing=...)` in `packages/core/src/lonora_core/trading_control.py:6-18`; classification `risk_reducing` / `may_reduce_risk` in `packages/trading/src/lonora_trading/admission.py:70-72,100` (policy text `:1-45`) | "Trading OFF and Emergency Stop stop new risk; they never trap an exit". Applied at `execution.py:179-190` and again at send (`:356`). The decision comes from the fresh broker target, never the model's description. |
| **Restrictions and global stop** | `require_unrestricted` (`packages/trading/src/lonora_trading/restrictions.py:99`); `apply_controls` (`packages/trading/src/lonora_trading/controls.py:23-44`) | `classify` maps `trading_restriction_active` to `permission_denied` / `respect_scope` so the model does not route around it (`AR/environment.py:62-63`). |
| **No replay of uncertain effects** | `AR/tool_dispatch.py:55-95`, `AR/environment.py:156-181`, in-flight markers `AR/tool_intent.py:75-108` | A possibly-sent mutation is reconciled by its original id, never resent. |
| **No premature success in prose** | `AR/model_runtime.py:225-238`, `AR/uncertain_outcome.py`, `AR/public_stream.py:11-19` | Section 4. |

All of these sit below or beside the loop. A harness behaviour that only adds notices, classification hints, discovery fallbacks or stop-gate conditions does not cross any of them, provided it never calls a financial tool itself and never rewrites a financial result.

---

## Short list of attach points

| New behaviour | Existing place |
|---|---|
| Error results that say what to do next | `AR/tool_dispatch.py:113-117`, `AR/environment.py:35-93` and `:203-210` |
| Hint or fallback on empty tool search | `TL/registry.py:361-388`, `TL/tool_discovery.py:62` |
| "Do not stop yet" for ordinary chat Runs | `AR/stop_gates.py:86-129` and `:178-184`; delivered by `AR/loop_outcomes.py:170-174` |
| Check on the final reply (structured) | `AR/loop_outcomes.py:155-184` |
| Deterministic clean-up of owner text | `AR/model_runtime.py:246` |
| Message to the model mid-run | `append_notice` / `attach_notice`, `AR/runtime_notices.py:55-81` |
| Thread-level open request / pending offer | `ThreadRow.options` (`packages/db/src/lonora_db/schema.py:239`), or a new `ResourceRow`, or `ln_tickets` |
| Behaviour evaluation | copy `scripts/genui_eval/bank.py` and `run.py`; write a new scorer |
