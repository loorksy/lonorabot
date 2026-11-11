# Journeys J4: background work and memory

Repository `/home/user/lonorabot`, HEAD `9f5b1da` (the working tree is unchanged; `git status --short` is empty). Paths in citations are relative to the repository root.
Database used: `audit_j4_test` (N = 4). Drivers: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/j4_*.py`. Raw output of every run: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/J4-*.txt` (stderr in `J4-*.err`).

## 0. How to read this file

- **REAL** in every run: the API app, PostgreSQL, the Personal Agent row, the real owner-message route, the context builder, `execute_run`, the tool loop, the tool registry and dispatch, guardrails, the environment/recovery layer, the task/routine/watch/memory/notification code, the gateway steps (`dispatch_routines`, `resume_ready_waits`, `check_watches`, `attention_tick`, `Watchdog.tick`, `claim_next`, `return_outcome`, `release_leases`), and the stored rows.
- **SCRIPTED**: only the model turns (which tool to call, which provider error to raise, which text to reply). Every scripted turn is labelled. A scripted final reply is never evidence of what a real model would say. The evidence is the tool result, the notice, the stored row, the notification, or the committed message that the runtime produced.
- **FAKE** (only J4-08b): the MetaApi RPC connection behind a real `MetaApiBroker` object is a fake SDK that lists only `BTCUSDm, EURUSDm, USOILm, XAGUSDm, XAUUSDm` and answers 404 for anything else. The 404 message text `Symbol not found` is an assumption (the same one `scratchpad/audit/scripts/j1_lib.py` documents). The mapping of that 404 to a Lonora code is real code.
- **Harness limits that matter**: the fixture leases a Run for 300 s (`tests/check_streaming.py:134`), production uses 120 s (`apps/api/src/lonora_api/env.py:96`, `packages/gateway/src/lonora_gateway/service.py:74`). The gateway steps are called directly instead of by the 2 to 10 second timers (`packages/gateway/src/lonora_gateway/service.py:40-64`).
- Rerun any journey (resets database 4 first, loads the env, runs the driver):
  `cd /home/user/lonorabot && /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/run4.sh <id> <driver> [arg]`
  which is the same as: `cd /home/user/lonorabot && /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/reset_db4.sh && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 4 && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/<driver> [arg]`
  (the drivers look up "the first Run with trigger X", so run them on an emptied database).
- "Owner-facing" text below is what the stored rows contain. Whether a client screen renders a given row is stated as UNSURE where I did not check it.

## 1. Summary

| Id | What the owner asked | What happened (runtime evidence) | Class |
|---|---|---|---|
| J4-01 | «ذكّرني كل ساعة أفحص الذهب» | The model gets a bare `invalid_cron` / `tool_arguments_invalid` (no message, no example) for a natural-language schedule; the schema has no format hint; tool discovery with ordinary words returns zero tools; the finished routine writes into a new thread that no notification points to | recoverable-not-led, leak |
| J4-02 | A Task fails or needs direction | Failed Task: `modify_plan`, no resume, no chat message, a generic alert that promises a reason nobody wrote. Owner-attention hand-off: the explanation is written (in English) into a hidden thread and the alert is retired by the next event (`attention_superseded_state`) | dead-end, bug, leak |
| J4-03 | A Task waits for a price / the owner cancels it | A Task waiting on a watch that expired stays `waiting` forever, the watchdog says nothing; cancelling a Task leaves its watch enabled and polled | dead-end, bug |
| J4-04 | The process restarts mid-run | One recovery works and the model gets its earlier tool results back; a graceful update resumes at once; a hard kill waits for the lease; a crash loop ends in a failed Run with no reply in the chat | mostly needed for safety; one gap |
| J4-05 | «ابحث … وأرجع لي بملخص» (delegation) | A failed, empty or limited subagent returns `<peer_outcome ...>` with a raw code or an English sentence as a chat message in the owner's conversation | leak, bug |
| J4-06 | An alert or a wake that is held, limited or silent | `owner_notify` is held for quiet hours or refused with a bare `owner_notify_rate_limited`; a watch wake whose Run ends empty or fails leaves the chat and the inbox untouched | silent, recoverable-not-led |
| J4-07 | The owner states a fact, a later run needs it | Facts saved with `memory_write` are injected into every later run; a fact only said in chat is not; a tool's own recovery text is overwritten by the runtime | recoverable-not-led, bug |
| J4-08 | «نبّهني لما الذهب يوصل 4100» | Malformed arguments return field paths without expected values; a watch on `XAUUSD` is saved as a success, then fails forever with `broker_account_not_found` and no notice | bug, leak, dead-end |
| J4-09 | (control) | A watch with `enabled=false` is not evaluated by the poller: the production observation is not reproduced here | UNSURE |

## 2. Journeys

### J4-01: «ذكّرني كل ساعة أفحص الذهب»: the schedule the model cannot guess

**Owner request**: «ذكّرني كل ساعة أفحص الذهب» (J4-01, J4-01b); «افحص لي الذهب كل ساعة وبلغني» (J4-01c).

**Commands** (drivers in the scripts folder): `run4.sh J4-01 j4_01_routine_schedule.py`; `run4.sh J4-01b j4_01b_routine_discovery.py`; `run4.sh J4-01c j4_01c_routine_result.py`. Raw: `runs/J4-01.txt`, `J4-01b.txt`, `J4-01c.txt`.

**What the model is offered.** The native tools of the owner's conversation run (printed in `runs/J4-01.txt`, "native tool names offered on SCRIPTED turn 1"): `peer_send, memory_read, memory_write, session_search, skills_list, skill_view, market_instrument, market_quote, market_candles, market_snapshot, market_sessions, watch_create, market_decision_record, market_decision_history, chart_snapshot, list_accounts, account_read, trade_execute, wait_for_input, agent_inspect, tool_environment, tool_call`. There is no `routine_create`, `task_start`, `owner_notify` or `subagent_spawn`. They are reachable only through `tool_call` (same shape as the production trace, point 2 of `TIMELINE_CORRECTION.md`).

**SCRIPTED turns (J4-01)**: seven `tool_call` bridge calls to `routine_create`, then a final text. Arguments: `cron="كل ساعة"`; `cron="every hour"`; `interval_seconds=30`; `cron="0 * * * *"` together with `interval_seconds=3600`; `run_at="2026-11-12T09:00:00"` (no zone); `cron="0 * * * *", timezone="Damascus"`; `interval_seconds=3600`.

**Literal runtime results the model receives (trimmed, verbatim)**

```
cron="كل ساعة"          {"ok": false, "code": "invalid_cron", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}
cron="every hour"       {"ok": false, "code": "invalid_cron", "recovery": {... same ...}}
interval_seconds=30     {"ok": false, "code": "tool_arguments_invalid", "issues": [{"path": ["interval_seconds"], "type": "greater_than_equal"}], "retryable": true, "recovery": {"category": "invalid_tool_arguments", "next_action": "inspect_schema_and_repair", ...}, "runtime_notice": [{"kind": "tool_guardrail", "source": "lonora_runtime", "message": "routine_create has failed 3 times in this run. Diagnose the latest error before another attempt: correct the arguments, use a narrower request or a genuinely different source, or report the blocker."}]}
cron + interval         {"ok": false, "code": "tool_arguments_invalid", "issues": [{"path": [], "type": "value_error", "code": "one_schedule_required"}], ...}
run_at without zone     {"ok": false, "code": "tool_arguments_invalid", "issues": [{"path": [], "type": "value_error", "code": "run_at_timezone_required"}], ...}
timezone="Damascus"     {"ok": false, "code": "invalid_timezone", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", ...}, "runtime_notice": [... "has failed 6 times in this run" ...]}
interval_seconds=3600   {"ok": true, "id": "351bc6e2-...", "interval_seconds": 3600, "cron": null, "timezone": "UTC", "enabled": true, "next_run_at": "2026-11-11T16:31:16.053644+00:00", ...}
```

What the model is told, and not told:
- `invalid_cron` and `invalid_timezone` carry no message, no field name, no accepted format, no example. The runtime classifies them as `terminal_domain_failure` with `next_action: "alternate_route"` because the classifier has no branch for them (`packages/agent-runtime/src/lonora_agent/environment.py:35-37` sets the default; the branches that exist are `environment.py:38-91`). `invalid_cron` comes from `packages/core/src/lonora_core/cron.py:10-11`, `invalid_timezone` from `packages/core/src/lonora_core/cron.py:13-15`; both are raised only after the arguments passed validation (`packages/db/src/lonora_db/routines.py:20-24`).
- The validation errors keep only the path, the type and (for Lonora's own validators) a machine code: `packages/tools/src/lonora_tools/schema.py:45-69`. The accepted range of `interval_seconds` (60 to 31536000) appears nowhere in that result: `greater_than_equal` has no number (`packages/contracts/src/lonora_contracts/routines.py:13`).
- `routine_create`'s description says "Schedule this same agent with either a cron expression/timezone or an interval; work continues with the browser closed." (`packages/tools/src/lonora_tools/routine.py:107-112`). It does not say that `cron` is a five-field croniter expression, that `timezone` must be an IANA name, or that a one-shot `run_at` exists.

**J4-01b: can the model look the format up?** SCRIPTED: `tool_environment` with `query="remind every hour schedule"`, then `query="routine"`, then `tool_name="routine_create"`.
```
query "remind every hour schedule" -> {"ok": true, "tools": [], "total": 0, "next_offset": null, ...}
query "routine"                    -> names: ["routine_toggle", "routine_list", "routine_create"]
tool_name "routine_create"         -> input_schema.properties.cron = {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null}
                                      interval_seconds = {"anyOf": [{"maximum": 31536000, "minimum": 60, "type": "integer"}, {"type": "null"}], "default": null}
```
Cause of the empty first answer: the search takes the rarest query word as a gate and drops every tool that lacks it (`packages/tools/src/lonora_tools/tool_discovery.py:62` and `:69-71`). The word "every" occurs in no tool, so one ordinary word in the query returns nothing. The tool's own text says "Use English terms for the first-party catalog" (`packages/tools/src/lonora_tools/environment.py:16`). The `cron` field has no description at all, so the schema returned by an exact lookup does not teach the format either.

**J4-01c: where does the answer of a routine go?** SCRIPTED: `routine_create(title="فحص الذهب", prompt=..., interval_seconds=3600)`; then the real `dispatch_routines`; then a SCRIPTED routine Run replies "SCRIPTED routine report: ...".
```
owner_chat thread: c657c572-...   routine thread: 00d07d11-...
GET /threads -> [{"id": "00d07d11", "title": "Check the gold price and report to the owner."}, {"id": "c657c572", "title": "افحص لي الذهب كل ساعة وبلغني"}]
owner's main chat: [user "افحص لي الذهب كل ساعة وبلغني"], [assistant "SCRIPTED: تم، سأفحص كل ساعة."]   (nothing from the routine)
routine's own thread: [assistant "SCRIPTED routine report: الذهب 4050، لا تغيير مهم."]
owner notifications: []
```
Root cause: the routine gets a new thread titled with the first 80 characters of its prompt, not its title (`packages/db/src/lonora_db/routines.py:68`); the Run's reply is written there; a finished routine Run raises no notification (`run.completed` is not in `ATTENTION_KINDS`, `packages/core/src/lonora_core/attention.py:7-35`). Because the prompt is written by the model in English (skills and prompts are English by owner rule), the thread title the owner sees in the list is English. UNSURE: whether a client screen other than the thread list leads to that thread (`scratchpad/audit/map-background.md` section 2.4 says none was found; I did not re-check the clients).

**What the owner sees**: nothing from a failed schedule attempt. The only evidence is the model's own wording. Three or more identical failures make the runtime add the notice quoted above; there is no halt before the 7th call in this run. If the model gives up, the owner gets "I can't schedule that" style prose; if it recovers, the first hourly report lands in a thread he does not open.

**Class**: recoverable-not-led (a safe, correctable error with no guidance), leak (codes are the only feedback the model has to turn into prose), owner-needed only by accident (the model may ask the owner for a "cron expression").
Needed for safety: none of this. A routine runs with scope `full` but money still goes through the grant or an approval card (`docs/proactive-wakes.md:32-36`; `packages/tools/src/lonora_tools/base.py:53-58`).

---

### J4-02: a Task fails, or needs the owner, and what he is told

**Owner request**: «تابع الذهب وأخبرني» (a Task is started by a SCRIPTED `task_start` through the bridge; "chat" turn). The Task run is then driven with a SCRIPTED background model. Commands: `run4.sh J4-02a j4_02_task_fails.py a`, `... b`, `... c`, `... d`, `... e`, and `run4.sh J4-02f j4_02f_attention_superseded.py`. Raw: `runs/J4-02a.txt` to `J4-02f.txt`.

#### J4-02a: finite Task, the provider rejects the request after one real read

SCRIPTED Task-run turns: `list_accounts`, then a raised `ModelProviderError(FORMAT_ERROR)`.
```
Task Run row: {"status": "failed", "error_code": "model_request_rejected", "failure": {"family": "model", ...}}
task snapshot: status "failed", phase "failed", can_resume false, failure {"code": "model_request_rejected", "recovery": "modify_plan", "attempt": 1, "next_retry_at": null}, steps: read=pending, report=pending
hidden Task work thread messages: []
owner's chat thread: [... "SCRIPTED: started."]   (nothing about the failure)
ln_attention: [{"code": "task_review", "importance": "action_required", "status": "ready", "parameters": {"task_id": ..., "work_thread_id": ...}}]
```
What the owner gets: one in-app item whose off-app text is «تحتاج المهمة إلى مراجعتك. افتح المحادثة لفحص سبب التوقف وخيارات الاستكمال.» (`packages/bus/src/lonora_bus/attention_messages.json:7`) and whose in-app label is «المهمة تحتاج مراجعة» (`apps/web/src/components/ai/AttentionInbox.tsx:25`, `apps/web/src/i18n/locales/ar/messages.po:7010-7011`). The text sends him to "inspect the reason" in the conversation, and the conversation holds no reason: a failed Run writes no message (the final message is written only when the Run has a result or rich content, `packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:130-132`). The Task page shows «بانتظار المراجعة» for both `failed` and `waiting` (`apps/web/src/shell/domain/TasksPages.tsx:40-42`, `messages.po:1074-1075`) with no reason and no steps (`TasksPages.tsx:194-203`), and no Resume button because `can_resume` is false (`TasksPages.tsx:223`).
Root cause: `model_request_rejected` is a plan code, so the failure is classified `modify_plan` (`packages/db/src/lonora_db/task_recovery.py:25-31`, `:124-125`); resume is refused for `modify_plan` (`task_recovery.py:236-241`, `packages/db/src/lonora_db/tasks.py:385-392`). The alert importance comes from `packages/core/src/lonora_core/attention.py:102-108`.

#### J4-02d: the owner then asks «شو صار بالمهمة؟». What the agent reads and what it can do

SCRIPTED chat turns: `task_inspect`, then `task_control resume`, then `task_control revise` (with the real `expected_version`), then a final text.
```
task_inspect -> {"ok": true, "tasks": [{... "status": "failed", "phase": "failed", ... "failure": {"code": "model_request_rejected", "recovery": "modify_plan", "attempt": 1, ...}, ..., "can_resume": false, "can_cancel": true}]}
task_control resume -> {"ok": false, "code": "task_cannot_resume", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", ...}}
task_control revise -> {"ok": true, ... "status": "failed", "plan_revision": 2, "instruction": "Retry with a shorter plan: ...", "failure": {..., "recovery": "owner"}, "can_resume": true, ..., "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", ...}}
```
Findings:
- The model reads `model_request_rejected` and `modify_plan`, never a sentence. Nothing in the result says "revise the plan, then resume". Resume without a revision returns a bare `task_cannot_resume`. A revision converts `modify_plan` to `owner` (`packages/db/src/lonora_db/tasks.py:454-457`) but leaves the Task `failed`; a second call, `resume`, is still needed. The Task page has no revise control and no client sends `revise` (search of `apps/web/src` and `apps/mobile` found none; `TasksPages.tsx:220-247` lists Pause, Resume, Mark as completed, Delete).
- **Bug found while running this**: the successful `revise` result carries a `recovery` block of `terminal_domain_failure` / `alternate_route`. Cause: the runtime counts any tool result with `"status": "failed"` as a failed call (`packages/agent-runtime/src/lonora_agent/environment.py:164-165`), and a Task snapshot of a failed Task has exactly that field. The result is attached at `environment.py:210`. A successful task action on a failed Task is therefore recorded as a failure, with the code `tool_failed` (`environment.py:145`), and three identical routes are then blocked (`environment.py:127-131`).

#### J4-02b: continuous Task, provider outage (`ModelProviderError(SERVER_ERROR)`)
```
Task Run row: status "queued", error_code null, environment.retry {"reason_code": "model_provider_retry", "code": "model_provider_unavailable", "attempt": 1, "not_before": ...+30 s},
              model_recovery {"failures": 1, "reason": "server_error"}
task snapshot: status "queued"; ln_attention: []; chat: nothing new
stderr: model_turn_retry_scheduled code=model_provider_unavailable attempt=1 notify=False
```
The Task retries on its own with backoff 30 s up to 900 s and the owner is told only after the sixth consecutive failure (`packages/agent-runtime/src/lonora_agent/model_recovery.py:48-51` for the profile fields, `:63` for the continuous profile, `Decision.notify` at `:71-72`). This part is sound. Not reproduced here: the notification after six failures and the 12-hour hold (`model_recovery.py:63`).

#### J4-02c: tool-round budget exhausted (rounds=3)
The Run is re-queued with `environment.retry.reason_code: "task_continuation"` and the Task stays `queued`; no alert, no message, no failure. By design: `packages/agent-runtime/src/lonora_agent/continuation.py:83-90` bumps the slice and sets `retry.reason_code = "task_continuation"` (at most `MAXIMUM_SLICES = 4`, `continuation.py:20`). It is correct for a healthy long Task; it also means a Task stuck on a repeating loop looks like progress until the slices run out.

#### J4-02e and J4-02f: the Task keeps answering with text; the stop gate hands it to the owner
SCRIPTED Task-run turns: four prose replies «ما قدرت أقرأ الذهب» (finite Task, two declared steps).
```
Task Run row: status "waiting_input"; task snapshot: status "waiting", waiting_reason "owner_attention", can_resume true
hidden Task work thread: [assistant "This task is not finished. Steps not completed yet: Read the gold price; Report to the owner. I need your direction before continuing: reply here, or revise, resume, pause or cancel the task.\n\nLatest report: SCRIPTED prose 3: ما قدرت أقرأ الذهب."]
owner's chat thread: [user "تابع الذهب وأخبرني"], [assistant "SCRIPTED: started."]   (nothing else)
```
Two defects:
1. **The explanation is in the wrong thread and in English.** The executor writes the question to the Run's own thread (`packages/agent-runtime/src/lonora_agent/executor.py:176-187`), which for a Task Run is the hidden work thread (`packages/db/src/lonora_db/tasks.py:176-178` creates the work thread with `purpose="work"` and `:212` puts the Run in it; the owner's thread list returns only conversation threads, `packages/db/src/lonora_db/threads.py:98-100`). The language is chosen by `prefers_arabic(messages)` (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:125`); that function looks only at owner-role messages and answers False when one has at least eight Latin letters (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:84-93`). The Task's English description is such a message, so the owner gets English. The Arabic strings exist («هذه المهمة لم تكتمل بعد.» and the closing line «أحتاج توجيهك قبل المتابعة: ردّ هنا، أو عدّل المهمة أو استأنفها أو أوقفها مؤقتًا أو ألغها.», `runtime_notices.py:142-195` as listed in `map-background.md` section 1.7).
2. **The alert is retired before anyone can see it (new finding).** Run `J4-02f` traces the events one by one:
```
task.* events before the attention step: [1049 task.created], [1061 task.updated v2 running], [1073 task.updated v3 waiting owner_attention], [1074 task.attention_required v3]
receipts, in the order processed: [1074 task_review action_required pending], [1061 internal_update silent suppressed attention_superseded_state], [1073 internal_update silent suppressed runtime_only]
ln_attention: [{"code": "task_review", "importance": "action_required", "status": "suppressed", "suppression_code": "attention_superseded_state"}]
```
Cause: the gateway sorts loud events first (`packages/gateway/src/lonora_gateway/attention.py:466-473`). Event 1074 creates the `task_review` item. Event 1073 is the silent `task.updated` of the same Task version, emitted in the same transaction (`save_task` emits it, `packages/db/src/lonora_db/tasks.py:100-111`; the attention event follows, `tasks.py:787-795`). It passes the version check (`packages/gateway/src/lonora_gateway/attention.py:274`) because both carry version 3. A silent event retires every pending or ready item in the same scope (`packages/db/src/lonora_db/attention.py:186-202`: the status filter at `:193` includes `pending` when the new event is silent). So the owner is not notified that his Task needs him. In J4-02a the failure path did not hit this (the silent update there had an older version, so it was dropped at `attention.py:274`).
The production ticket for the Task «إدارة حساب التداول» ended in `waiting_reason: owner_attention` (`production-trace.md`, Part 1, Q5), which is this path; the trace holds no attention table, so I could not confirm the production item was suppressed. UNSURE for production; reproduced here with the code of main.

**Class**: J4-02a/d dead-end plus leak (codes are the only text; the alert promises a reason that is absent); J4-02e owner-needed but unseen (bug, language); J4-02f bug.
Needed for safety: the refusal to resume a `reconcile/external` failure (`task_recovery.py:236-241`) and never retrying a reconciliation automatically are for money safety. `modify_plan` and `terminal` are not.

---

### J4-03: a Task waits for a condition that never comes; the owner cancels it

**Owner request**: «تابع الذهب وأخبرني» (continuous Task; the production Task «إدارة حساب التداول» has this shape: `production-trace.md`, Q5). Command: `run4.sh J4-03 j4_03_wait_never.py`. Raw: `runs/J4-03.txt`.
SCRIPTED Task-run turns: `watch_create` (price `XAUUSDm` above 999999 on a simulation account), then `task_wait(kind="watch", source_id=<that watch>)` with the accompanying text «SCRIPTED owner update: أراقب السعر وأرجع لك عند الوصول.». Everything after is real gateway code.

A. Waiting on a live watch:
```
Run: waiting_takeover; Task: status "waiting", waiting_reason "external_watch", can_resume false
owner's chat gets the accompanying text (the update is posted to the origin conversation after the server accepts the wait)
resume_ready_waits x3 -> [0, 0, 0]     Watchdog.tick() -> {"steps": 0, "runs": 0, "overdue": 0, "operations": 0, "ended": 0}
```
B. The watch dies (its `expires_at` passes; the real poller `check_watches` marks it expired):
```
watch row: {"enabled": true, "lifecycle": "expired", "lifecycle_reason": "watch_expired", "task_id": ...}
resume_ready_waits x3 -> [0, 0, 0]     Watchdog.tick() -> all zeros
Task: still status "waiting", waiting_reason "external_watch", version 4 (unchanged)
ln_attention: [{"code": "thesis_invalidated", "importance": "important_change", "status": "pending", ...}]
```
Findings:
- The Task never wakes and never fails. Readiness needs the watch to have a `last_triggered` value (`packages/db/src/lonora_db/task_wait.py:179-189`); the watch's `enabled` flag is checked only when the wait is created (`task_wait.py:40`). An expired, paused, cancelled or health-suspended watch leaves the Task asleep with no timer. The watchdog's overdue check counts only `timer` waits (`packages/gateway/src/lonora_gateway/watchdog.py:249-275`, the `timer` filter at `:270`).
- The one notice the owner may get is the expiry event mapped to the label of an invalidated trade idea: `watch.expired` becomes `thesis_invalidated` (`packages/core/src/lonora_core/attention.py:86-87`), shown as «تغيّرت صلاحية الإعداد» (`apps/web/src/components/ai/AttentionInbox.tsx:22`, `apps/web/src/i18n/locales/ar/messages.po:6424-6425`). It names the symbol, not the Task, and it is `important_change`, which the off-app channel skips (only `critical` and `action_required` go out, `packages/gateway/src/lonora_gateway/event_dispatch.py:130`).
C. The owner cancels the Task from the interface (real `POST /tasks/control`, action `cancel`):
```
cancel result: {"status": "cancelled", "phase": "cancelled", "waiting_reason": "external_watch", "version": 5}
watch row after cancel, poll 1 and 2: {"enabled": true, "lifecycle": "pending", "evaluation_status": "suspended_health", "code": "quote_unavailable", "task_id": ..., "task_run_id": ...}
```
The watch of the cancelled Task stays enabled and keeps being evaluated. It is switched off only at the moment it triggers: `row.payload = {**row.payload, "enabled": False}` with `state["code"] = "task_terminal"` (`packages/market/src/lonora_market/watchers.py:657-665`). The cancel call does not touch watches. This is the mechanism behind the production observation that watch `3789e892` still pointed at the cancelled Task (`production-trace.md`, Q4 note and `TIMELINE_CORRECTION.md` point 10, second half). (`quote_unavailable` here is only because the simulation account has no quotes.) The stored Task also keeps the stale `waiting_reason`.

**What the owner sees**: «بانتظار المراجعة» on the Task page for a healthy wait and for a dead one alike (`apps/web/src/shell/domain/TasksPages.tsx:40-42`); no explanation that the watch he relied on has ended.
**Class**: dead-end (silent stall) and bug (orphan watch). Needed for safety: a watch never trades, it only wakes the agent (`packages/tools/src/lonora_tools/market_watch.py:239`); disabling an orphan is safe.

---

### J4-04: the process restarts with a run in flight

**Owner request**: «شو وضع الذهب» (conversation run), and a continuous Task run. Commands: `run4.sh J4-04a j4_04_restart.py a`, `b`, `c`, `d`. Raw: `runs/J4-04a.txt` to `J4-04d.txt`.
Method: a SCRIPTED model makes one real call (`list_accounts`), then the scripted step raises a `BaseException` subclass that nothing in `execute_run` handles: this stands for SIGKILL or a container recreation. Recovery then uses the real `claim_next` / `Watchdog` / `release_leases`.

A. Hard kill, one recovery:
```
right after the kill: Run status "running", lease_owner "scripted-streaming-fixture", recovery_count 0 (lease 299 s here, 120 s in production)
claim_next while the dead worker's lease has not expired -> None
after the lease expired -> {"claimed": true, "recovery_count": 1, "status": "leased"}
the SCRIPTED model on the recovered pass is sent: assistant tool call list_accounts, the earlier tool result, then the evidence-identity system note (no "restart" notice, no repeat of the tool call)
```
The owner waits for the lease to expire (default 120 s: `apps/api/src/lonora_api/env.py:96`; eligibility `packages/db/src/lonora_db/runs.py:196-200`) and sees nothing in between. After recovery the run continues from the checkpoint. A claim that comes from a crash increments `recovery_count` (`runs.py:269`) and emits `run.recovered` (`runs.py:287`).

D. Graceful update (the case of the three updates in the production conversation):
```
release_leases(...) -> ["4eb11380-..."]; Run status "queued", lease_expires_in_seconds null, recovery_count 0
claim_next right away -> {"claimed": true, "recovery_count": 0, "status": "leased"}; resumed with the same tool result in context
```
On stop the gateway drains for 25 s and then returns its leases to the queue (`packages/gateway/src/lonora_gateway/shutdown.py:8-14`, `:17-27`; `packages/gateway/src/lonora_gateway/service.py:310-319`), so a normal update costs the run seconds, as the trace shows for run `57dcaeb0` (queued 09:54:48, leased 09:54:56; `production-trace.md`, Part 2).

B. Crash loop on a conversation run (every new worker dies at once):
```
claim_next recoveries 1, 2, 3, 4, 5 -> claimed; the sixth claim -> None ("refused")
Watchdog.tick() -> {"runs": 1}; Run: status "failed", error_code "run_recovery_limit"
ln_attention: [{"code": "run_quarantined", "importance": "action_required", "status": "ready"}]
chat messages the owner sees: [user "شو وضع الذهب"]  (no reply)
```
C. Same for a Task run: Task `failed`, `failure.code "run_recovery_limit"`, `recovery "owner"`, `can_resume true`; alert `task_review` (same text as J4-02a), work thread and chat empty.
Cap and quarantine: `packages/db/src/lonora_db/runs.py:21`, `:200`; `quarantine_run` `runs.py:529-575`; the watchdog step `packages/gateway/src/lonora_gateway/watchdog.py:191-217`, `:219-247` (a Task's own failure is not double-reported, `:230-231`). Off-app text for B: «توقف عمل بعد انقطاعات متكررة. افتح المحادثة لمراجعته.» (`packages/bus/src/lonora_bus/attention_messages.json:13`). It sends the owner to the conversation, where the only thing he finds is his own unanswered message. UNSURE: whether the web client renders a failed conversation Run as an error card (the stored thread has no assistant message; I did not run a browser).

**Class**: A and D work as designed. B and C: dead-end after five crashes, with a generic alert and no reply (small gap; leak-free).
Needed for safety: the cap on re-leasing, the hold (not fail) of a Run with an unresolved financial operation (`runs.py:554-555`, `docs/gateway-reliability.md:104-110`), and never auto-retrying a reconciliation. Doc and code agree here.

---

### J4-05: a delegated subagent fails or returns nothing

**Owner request**: «ابحث في أخبار الذهب اليوم وأرجع لي بملخص». Commands: `run4.sh J4-05a j4_05_subagent.py a`, `b`, `c`. Raw: `runs/J4-05a.txt` to `c.txt`.
SCRIPTED parent turns: `subagent_spawn(task="Research today's gold news and report the three most important points.")` through the bridge, then «SCRIPTED: أرسلت مساعداً للبحث وسأرجع لك بالنتيجة.». SCRIPTED subagent turn: (a) raise `ModelProviderError(FORMAT_ERROR)`; (b) thirty empty replies; (c) one normal text. The real `return_outcome` (the gateway's `outcomes` step does this) then runs.
```
spawn result: {"ok": true, "status": "queued", "trigger": "subagent", "parent_run_id": ..., "model_metadata": {"depth": 1, "return_thread_id": <owner chat>, ...}}
(a) subagent Run: failed, error_code "model_request_rejected", result null
    GET /threads/<owner chat>/messages -> [user ...], [assistant "SCRIPTED: أرسلت مساعداً ..."], [assistant "<peer_outcome run_id='28a57c9a-...' status='failed'>\nmodel_request_rejected\n</peer_outcome>"]
(b) subagent Run: completed, reply_outcome "limited", result "I stopped before finishing because this run reached its limit, and nothing further was executed after that point. Ask me to continue when you want me to resume." (8 model turns consumed)
    owner chat: [assistant "<peer_outcome run_id='f6c68cbc-...' status='limited'>\nI stopped before finishing ... Ask me to continue when you want me to resume.\n</peer_outcome>"]
(c) owner chat: [assistant "<peer_outcome run_id='3e871d9b-...' status='completed'>\nSCRIPTED subagent result: 1) ... 2) ... 3) ...\n</peer_outcome>"]
In all three: a queued Run with trigger "follow_up" on the owner's thread; ln_attention: []
```
Findings:
- **The return value is posted as an assistant message in the owner's conversation, tag and all.** `outcome = f"<peer_outcome run_id='{child.id}' status='{status}'>\n{child.result or child.error_code or status}\n</peer_outcome>"` (`packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:217`) is written as a `MessageRow` in the parent's thread (`outcome_return.py:218-228`). Neither `apps/web/src` nor `apps/mobile` mentions `peer_outcome` (searched), so I found no client code that hides it. UNSURE: whether the message renderer drops XML-like tags. For a failed child the body is the internal code (`model_request_rejected`), as `child.error_code` is the fallback.
- The `follow_up` Run is meant to turn it into a real answer: "Use the returned peer outcome to complete the owner's request." (`outcome_return.py:266`). In my run it stayed `queued` (I did not execute it). If that run's model is unavailable too, the owner is left with the raw message above.
- A subagent whose Run ends at the limit speaks English to the owner: the fallback sentence is chosen by `prefers_arabic(messages)` (`packages/agent-runtime/src/lonora_agent/tool_loop.py:284`, `runtime_notices.py:84-93`), and a subagent's context starts from the model's English task. The Arabic sentence exists: «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.» (`runtime_notices.py:132-140`).
- Empty replies from a subagent are re-asked (it counts as conversational, `packages/core/src/lonora_core/run_state.py:33-34`; `tool_loop.py:573-579`) until the budget ends: "returns nothing" turns into the English "limited" text, not into an honest "found nothing".
- Spawn limits that apply: depth 2 and a per-parent count (`packages/agent-runtime/src/lonora_agent/collaboration/subagents.py:22-23`, `:38-47`). Needed for safety / cost.

**Class**: leak (raw tag and code in the owner's chat), bug (English owner-facing text), recoverable-not-led (a failed helper is not retried or replaced).

---

### J4-06: a wake or an alert that is held, limited or silent

**Owner request**: «نبّهني إذا تغيّر شيء مهم» (a), «نبّهني وأخبرني إذا وصل الذهب 4100» (b, c). Commands: `run4.sh J4-06a j4_06_suppressed.py a`, `b`, `c`. Raw: `runs/J4-06a.txt` to `c.txt`.

A. SCRIPTED turns: `owner_notify` (bridge) with distinct `dedupe_key`s, first under the default policy, then after the owner sets quiet hours around now through the real `PUT /owner/preferences`, then five calls in a row.
```
default policy, important_change   -> {"ok": true, "status": "pending", "delivery": "in_app", ...}
quiet hours, important_change      -> {"ok": true, "status": "held_for_quiet_hours", "held_until": "2026-11-11T16:06:00+00:00", ...}
quiet hours, action_required       -> {"ok": true, "status": "held_for_quiet_hours", "held_until": "2026-11-11T16:06:00+00:00", ...}
quiet hours, critical              -> {"ok": true, "status": "ready", ...}
the 7th alert within the hour      -> {"ok": false, "code": "owner_notify_rate_limited", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", ...}}   (then k8, k9 the same; the third adds the "failed 3 times" guardrail notice)
ln_attention: k1 pending (due now), k2 k3 k5 k6 pending (due in 29 min), k4 ready
```
Quiet hours hold everything except `critical`, including an agent-raised `action_required` (`packages/db/src/lonora_db/attention.py:425`, `:467-469`); the limit is six per agent per hour (`attention.py:335`, `:396-397`) and its refusal is a bare code. The model is told `status` and `held_until` but not what to tell the owner. Needed for safety / owner preference: quiet hours and the limit (spam control, owner's reach-me choice); the doc agrees (`docs/proactive-wakes.md:118-126`).

B. A watch wake whose Run ends with no text. SCRIPTED: `watch_create` (simulation account, `XAUUSDm` above 4100) in chat; then the real `check_watches` with a quote of 4101; the wake Run (trigger `watch`, in the owner's chat thread) is given three empty replies.
```
check_watches -> 1 wake; wake Run created: {"trigger": "watch", "status": "queued", "thread_is_owner_chat": true}
wake Run row: {"status": "completed", "error_code": null, "result": "", "reply_outcome": "silent"}
owner's chat: [user ...], [assistant "SCRIPTED: أراقب الذهب."]   ln_attention: []
```
C. Same wake, the SCRIPTED model raises `ModelProviderError(FORMAT_ERROR)`:
```
wake Run row: {"status": "failed", "error_code": "model_request_rejected", "result": null}
owner's chat: unchanged; ln_attention: []
```
Cause: an empty turn is accepted for `routine, webhook, created, tickets, watch` triggers (`packages/core/src/lonora_core/run_state.py:33-34`, `packages/agent-runtime/src/lonora_agent/tool_loop.py:574` is skipped for them) and recorded as `reply_outcome: "silent"` (`tool_loop.py:603-605`). A failed watch/routine Run raises no attention item: `run.failed` is not in `ATTENTION_KINDS` (`packages/core/src/lonora_core/attention.py:7-35`), and the watch's trigger is recorded as consumed when it fires (a wake receipt per observation, `packages/market/src/lonora_market/watchers.py:636-637`); whether the same condition fires again after the cooldown (`cooldown_seconds`, default 300, `packages/contracts/src/lonora_contracts/market_watch.py:30`) was not tested: UNSURE. The empty reply in B is my scripted choice; a real model rarely does it, so B shows the runtime would accept it, not that it happens.

**Class**: silent / recoverable-not-led. The owner asked to be alerted; a held or failed wake produces no message.

---

### J4-07: the owner states a fact; a later run needs it (memory)

**Owner request**: «تذكّر: أنا أتداول الذهب فقط، وما أبغى أي صفقة فوق 0.05 لوت», then «أفضّل التقارير مختصرة بثلاثة أسطر» (said, not saved), then «ذكّرني كل ساعة بفحص الحساب». Command: `run4.sh J4-07 j4_07_memory.py`. Raw: `runs/J4-07.txt`.
SCRIPTED turns: chat run 1 calls `memory_write` twice (a wrong `version` guess, then the right one) adding a USER.md line; chat run 2 only replies; chat run 3 creates an hourly routine (bridge); the real `dispatch_routines` fires it; the routine Run (new thread) is scripted to call `memory_write` for USER.md and then reply.
```
memory_write (version=7, guess)   -> {"ok": true, "document": "owner_profile", "version": 2, "chars": 43, "changed": true, "applied": [{"action": "add", "section": "USER.md", "changed": true}]}
memory_write (version=1)           -> {"ok": true, ..., "changed": false, "applied": [{... "duplicate_of": "Trades gold only; no trade above 0.05 lot."}]}
routine run, first model request:  fact 1 FOUND in a user-role context block: ...{"profile": "Trades gold only; no trade above 0.05 lot.\n", "reply_language": "latest_owner_message", "reach_me": ...
                                   fact 2 (said in chat, never saved): NOT FOUND
routine run: memory_write USER.md  -> {"ok": false, "code": "owner_profile_requires_owner_message", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}
```
Findings:
- **Injection works for saved facts.** Every run reads the owner profile, the agent's OPERATING notes and MEMORY into the context (`packages/agent-runtime/src/lonora_agent/context/builder.py:145`, `:228`; text in `packages/agent-runtime/src/lonora_agent/context/memory.py:27-34`). A background run, in its own thread, therefore starts with the saved fact. Semantic recall is a separate step I did not exercise (it needs an embedding credential: UNSURE).
- **A fact only said in chat is lost to other threads.** Nothing saves it unless the model calls `memory_write`: the only writers of the profile are the memory tool, the owner's own API routes and the voice setup (`packages/tools/src/lonora_tools/memory.py:112`, `:125`, `:245`; `apps/api/src/lonora_api/routes/memory.py:122`; `packages/voice/src/lonora_voice/incoming.py:84`). I found no automatic extraction. Other threads are reached only through `session_search` (`docs/agent-memory-and-recall.md:393-394`).
- **Bug: the tool's own recovery text never reaches the model.** `OWNER_MESSAGE_REQUIRED` carries `"recovery": "Nothing was saved. The shared owner profile records only what the owner said in the conversation this run answers; keep other observations in MEMORY.md."` (`packages/tools/src/lonora_tools/memory.py:94-99`). The runtime overwrites any `recovery` with its generic block (`packages/agent-runtime/src/lonora_agent/environment.py:210`), so the model sees `terminal_domain_failure` / `alternate_route`, the sentence is lost, and "keep it in MEMORY.md" is the advice that disappears. The refusal itself is needed for safety (a background run must not write the shared profile as if the owner said it; `memory.py:123-124`).
- A stated limit is accepted into the profile: «no trade above 0.05 lot» saved without error. The tool description says "No credentials, prices, limits or authority claims" (`memory.py:282`) and the profile note says a hard limit belongs in a restriction or account limit (`context/memory.py:27-34`), but nothing in `memory_write` enforces this. The owner may believe a limit exists. (Server limits are enforced only through restrictions, not memory. Out of scope for J4, noted.)
- `memory_write` requires a `version` the model must obtain from `memory_read` first (`memory.py:58`, `:266-274`); for USER.md operations the version is not checked (a wrong guess succeeded above), for the agent's own document it is.

**Class**: recoverable-not-led (a fact the owner states in a conversation is not saved unless the model chooses to), bug (overwritten recovery text).

---

### J4-08: a watch on a symbol the broker does not list; a malformed condition

**Owner request**: «نبّهني لما الذهب يوصل 4100». Commands: `run4.sh J4-08a j4_08_watch_bad.py a`, `run4.sh J4-08b j4_08_watch_bad.py b`. Raw: `runs/J4-08a.txt`, `J4-08b.txt`. The account is a real `MetaApiBroker` over a FAKE SDK (see section 0).

A. SCRIPTED: eight `watch_create` calls with wrong shapes.
```
level="4100$"                        -> tool_arguments_invalid, issues [{"path": ["level"], "type": "decimal_parsing"}]
condition="فوق"                      -> tool_arguments_invalid, issues [{"path": ["condition"], "type": "literal_error"}]
price watch without level            -> issues [{"path": [], "type": "value_error", "code": "watch_price_required"}]
kind "dynamic", no detector          -> issues [{"path": [], "type": "value_error", "code": "watch_dynamic_detector_required"}]
detector {"kind": "golden_cross"}    -> issues [{"path": ["detector", "id"], "type": "missing"}, {"path": ["detector", "kind"], "type": "literal_error"}]
indicator watch, timeframe="ساعة"    -> {"ok": true, "id": "52a16149-...", "payload": {... "timeframe": "ساعة", ...}}   (accepted)
account_id="gold-account"            -> {"ok": false, "code": "broker_connection_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", ...}}
```
A `literal_error` lists no allowed values; the model must call `tool_environment` to see them (`packages/tools/src/lonora_tools/schema.py:45-69`). The allowed conditions are `above, below, cross_above, cross_below, changed, closed, opened, due` (`packages/contracts/src/lonora_contracts/market_watch.py:24-26`). The free-text `timeframe` is not validated (`market_watch.py:32`): a watch with `timeframe: "ساعة"` is saved and will never evaluate sensibly. Whether it fails later: not tested.

B. SCRIPTED: `watch_create(account, symbol="XAUUSD", kind="price", condition="above", level="4100", ...)`, text «SCRIPTED: أراقب الذهب وأبلغك عند 4100.»; then the real poller three times.
```
watch_create -> {"ok": true, "id": "e6eb6e0f-...", "payload": {... "symbol": "XAUUSD", "condition": "above", "level": "4100", "enabled": true ...}, "state": {}, ...}
poll 1, 2, 3 -> 0 wakes; state: {"code": "broker_account_not_found", "evaluation_status": "suspended_health", "health": {"state": "unavailable", "reason_code": "broker_account_not_found", "symbol": "XAUUSD", ...}, "next_check": +30 s}; payload.enabled still true
events: watch.suspended_health (once)
ln_attention: []     owner's chat: [user ...], [assistant "SCRIPTED: أراقب الذهب وأبلغك عند 4100."]
stderr: broker_rpc_failed code=broker_account_not_found type=NotFoundException message=Symbol not found
```
Cause chain (all real code):
1. `watch_create` validates the shape only; it makes no broker or catalogue call (`packages/tools/src/lonora_tools/market_watch.py:90-145`, contract rules `packages/contracts/src/lonora_contracts/market_watch.py:45-89`), so the unknown symbol is stored as a success.
2. At evaluation the MetaApi adapter maps a 404 outside the candles stage to `broker_account_not_found` before it looks at the symbol (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:52-58`); `symbol_not_found` appears only on the candles stage (`metaapi.py:59-60`). These are the two codes in the owner's own gold message.
3. The poller catches the error, writes a health record with that code, moves `next_check` forward and returns (`packages/market/src/lonora_market/watchers.py:513-535`, health record `packages/market/src/lonora_market/watch_health.py:15-31`). Because it returns normally it is never counted as a failure, so the watch is not quarantined (`ItemGuard.run` records a failure only when the action raises, `packages/db/src/lonora_db/item_failures.py:124-132`).
4. The single `watch.suspended_health` event is classified `silent` / `internal_update` (`packages/core/src/lonora_core/attention.py:57-61`) and then suppressed as `runtime_only` (`packages/db/src/lonora_db/attention.py:143-144`).
Result: «أراقب الذهب» is false from the first second and nothing says so. In the production trace the same shape appeared in a different form: no watch on `XAUUSDm` existed although the agent said it was watching (`production-trace.md`, Q4 note). Symbol resolution and the 404 split are being fixed by other sessions; this entry records the downstream silence.

**Class**: bug (success reported for a watch that cannot work), leak (the misleading code is the only trace), dead-end for the owner's request.

---

### J4-09: control, a disabled watch

SCRIPTED: `watch_create(... enabled=False ...)`, then the real poller, with and without a stream quote.
```
watch_create -> ok, payload.enabled false, state {}
poll (no quote): wakes 0; state {}     stream quote update: wakes 0; state {} (version 1)
```
The poller query excludes watches whose payload says `enabled: false` (`packages/market/src/lonora_market/watchers.py:402`). The production export shows three such watches with `evaluation_status: active` and updates every 30 s (`production-trace.md`, Q4 note; `TIMELINE_CORRECTION.md` point 10, first half). I did **not** reproduce that. UNSURE what writes those rows in production (a path other than `check_watches`, or a payload that differs from the one a fresh `watch_create(enabled=False)` writes). Left to the session that owns the watch lifecycle.

## 3. Root causes that cut across the journeys

1. **Codes without sentences.** Every refusal the model gets is a code plus the runtime's generic `recovery` block. For codes the classifier does not know (`invalid_cron`, `invalid_timezone`, `owner_notify_rate_limited`, `task_cannot_resume`, `owner_profile_requires_owner_message`) the block says `terminal_domain_failure` / `alternate_route` (`packages/agent-runtime/src/lonora_agent/environment.py:35-37`). A tool's own guidance string is overwritten (J4-07, `environment.py:210`). The model has to invent the owner-facing sentence from the code (owner-facing leak) or ask the owner (technical question).
2. **The owner is told that something needs review, never why.** `task_review` and `run_quarantined` send him to "the conversation", where no reason is written (J4-02a, J4-04b/c). Task explanations are written into hidden work threads (J4-02e) or not written at all.
3. **Silent classes by default.** Failed routine / watch / webhook Runs, health suspension of a watch, a dead watch under a waiting Task and an empty reply of a background Run raise nothing (J4-03, J4-06, J4-08b). The classifier's default is `silent` (`packages/core/src/lonora_core/attention.py:57-61`).
4. **Alerts can be retired before they are shown.** A silent same-version event supersedes the loud one that was created from the same transaction (J4-02f; `packages/db/src/lonora_db/attention.py:186-202`).
5. **Owner-facing language is chosen per Run context, not per owner.** English Task and subagent contexts produce English owner messages (J4-02e, J4-05b); the owner's `reply_language` is read as `latest_owner_message` in the profile block (J4-07) and is empty in production (`production-trace.md`, Q6).
6. **Discoverability.** `routine_create`, `task_start`, `owner_notify`, `subagent_spawn` are not native (J4-01), and the catalogue search drops everything when one word has no match (`tool_discovery.py:62-71`), which is how a first lookup in ordinary words returns nothing.

## 4. Refusals in this area that exist for the money-safety rules (needed for safety; keep)

- Never resend a financial call after a crash; a Run with an unresolved journal operation is held, not failed; a reconciliation is never retried automatically (`packages/db/src/lonora_db/runs.py:554-555`, `packages/db/src/lonora_db/task_recovery.py:236-241`, `docs/gateway-reliability.md:104-110`).
- The cap on crash recoveries (`runs.py:21`, `:200`).
- A watch never trades; a Task's or routine's Run still reaches money only through the grant or an approval card (`packages/tools/src/lonora_tools/market_watch.py:239`, `docs/proactive-wakes.md:32-36`).
- A background run cannot write the shared owner profile (`packages/tools/src/lonora_tools/memory.py:123-124`).
- Quiet hours, the hourly limit and the critical-alert cap are owner-preference and spam controls, not money rules (`packages/db/src/lonora_db/attention.py:335-339`).

## 5. Corrections and cross-checks against other files

- `scratchpad/audit/map-background.md` section 1.7 (F4) says the Task's question is in the hidden work thread and the alert opens the origin conversation. Confirmed (J4-02e). Added here: the alert is retired by the same-version silent event (J4-02f), so the pointer may never be shown. The same file's F3 (raw internal code in a subagent's chat message) is confirmed and extended: the whole `<peer_outcome ...>` wrapper is posted (J4-05).
- `scratchpad/audit/map-background.md` section 3.5 (F1) says `watch_create` saves a symbol the broker does not list and the owner is told nothing. Confirmed by a run (J4-08b). Its note that quarantine never triggers matches `item_failures.py:124-132` and the run in J4-08b (the watch stayed enabled after three polls).
- `TIMELINE_CORRECTION.md` point 10, first half (disabled watches still evaluated): not reproduced (J4-09). Second half (cancelled Task leaves its watch active): reproduced with the code of main (J4-03 C).
- `TIMELINE_CORRECTION.md` point 11 (updates cost one run eight seconds): consistent with the graceful release path (J4-04 D).
- Docs vs code: I found no disagreement in this area. `docs/gateway-reliability.md:104-110` (recovery cap, `run_quarantined`, `task_review`) matches J4-04; `docs/proactive-wakes.md:118-126` (quiet hours, rate limit, critical cap) matches J4-06. Where a doc says an item "reaches the owner as `task_review`" (`docs/gateway-reliability.md:75-76`, `:108-109`), the failure path does (J4-02a, J4-04c); the owner-attention path is not documented there and, by the code, can be suppressed (J4-02f).

## 6. What I could not confirm

- Whether any client screen renders the routine's own thread, a work thread, or hides the `<peer_outcome>` wrapper (no browser run).
- Whether the production attention item for the owner-attention Task was suppressed (no attention table in the export).
- Whether a watch whose wake Run failed is re-armed after its cooldown (J4-06 C stops at the failed Run).
- The notification after six consecutive model failures of a continuous Task and the 12-hour hold (J4-02b stops at the first retry).
- Semantic recall in a background run (needs an embedding credential; not configured in this database).
- Why production watches with `enabled=false` kept updating (J4-09).
