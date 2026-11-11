# Part 1.7 — Long-running and background work (map)

Repository `/home/user/lonorabot`, code as of `9f5b1da` (the checked-out HEAD is `0a03960`; `git diff --name-only 9f5b1da HEAD` lists only files under `docs/`, so every code line number below is unchanged). Read-only audit. Every claim cites
`path:line`. "UNSURE:" marks what was not confirmed. "Needed for safety" marks a refusal
that exists for the money-safety rules and must stay.

## 0. Summary of the most important findings

| # | Finding | Evidence |
|---|---|---|
| F1 | A watch on a symbol the broker does not list (`XAUUSD` vs `XAUUSDm`) is saved without any check, then every evaluation fails quietly; the watch never fires, is never quarantined and the owner is told nothing. | §3.5 |
| F2 | A routine, watch, webhook or broker wake whose Run fails produces no notification, no chat message and no error card. For a watch the trigger is already consumed, so the event is lost. | §4.5 |
| F3 | A failed subagent returns its raw internal code (for example `model_provider_unavailable`) as the body of a chat message in the owner's conversation. | §5.4 |
| F4 | A Task that needs the owner posts its explanation («... ردّ هنا ...») into the hidden work thread; the notification belongs to the origin conversation and the web link only opens the agent's chat (§1.7). | §1.7 |
| F5 | A Task waiting on a watch that was disabled, expired, paused or quarantined waits forever. No timer, no watchdog check, no notice. | §1.8 |
| F6 | The owner's Task page shows «بانتظار المراجعة» for both a failed Task and a healthy Task sleeping on a timer, with no reason and no steps. Tasks failed with recovery `modify_plan`, `terminal` or `reconcile/external` have no Resume at all. | §1.6 |
| F7 | A quarantined routine/watch tells the owner only «أُوقف عنصر في الخلفية بعد أخطاء متكررة؛ يستمر كل ما عداه في العمل» (web label, `apps/web/src/i18n/locales/ar/messages.po:243`; the off-app text is «أوقفت لونورا عنصرًا في الخلفية بعد أخطاء متكررة. يستمر كل ما عداه في العمل.», `packages/bus/src/lonora_bus/attention_messages.json:12`) — not which item, not why — and the link opens the Personal Agent's chat. | §6.2 |
| F8 | Goal-linked routines and watches, and Task watches, are switched off without any event when their plan moves on. | §2.5, §3.6 |
| F9 | All background notifications are in-app only; off-app channels carry only `critical`/`action_required` items, as one fixed catalog sentence per item code (no detail). | §4.4 |

---

## 1. Tasks

### 1.1 What a Task is

- A Task is a `TicketRow` whose `state["task"]` holds a `TaskState`
  (`packages/db/src/lonora_db/tasks.py:179-199`). It gets its own board, its own thread
  with `purpose="work"` and one Run with `trigger="tickets"` and metadata `task_id`,
  `origin_thread_id`, `lane: "work"` (`packages/db/src/lonora_db/tasks.py:169-226`).
- Work threads are not listed to the owner: `list_threads` returns only
  `purpose == "conversation"` (`packages/db/src/lonora_db/threads.py:98-100`).
- Tool that starts it: `task_start` — "Start durable background work as this same agent
  while the current conversation remains responsive. Use finite completion for bounded
  results, continuous for ongoing monitoring or management until stopped. Neither mode
  grants trading authority; never report invented progress."
  (`packages/tools/src/lonora_tools/tasks.py:105-111`). The owner can also create one
  from the API (`apps/api/src/lonora_api/routes/tasks.py:32-43`).
- Authority: a Task started from an observe-only wake inherits `authority: observe_only`
  (`packages/db/src/lonora_db/runs.py:93-115`). Needed for safety.

### 1.2 States

- Task statuses: `queued, running, waiting, paused, completed, failed, cancelled`
  (`packages/contracts/src/lonora_contracts/tasks.py:10`).
- Recovery kinds: `automatic, owner, reconcile, modify_plan, terminal`
  (`packages/contracts/src/lonora_contracts/tasks.py:11`).
- Completion modes: `finite`, `continuous`
  (`packages/contracts/src/lonora_contracts/tasks.py:12`).
- Run statuses: `queued, leased, running, waiting_input, waiting_takeover, completed,
  failed, cancelled` (`packages/contracts/src/lonora_contracts/runs.py:11-20`).
- The status the owner reads is derived in `snapshot`: from the newest Run when no Run is
  active, or `running`/`waiting`/`queued` from the active Run
  (`packages/db/src/lonora_db/tasks.py:271-289`).

### 1.3 Who advances a Task

| Actor | What it does | Evidence |
|---|---|---|
| Gateway workers | `maximum_subagents + 1` shared workers plus one `conversation` worker claim Runs. With the default 4 this is 5 shared + 1 conversation. | `packages/gateway/src/lonora_gateway/service.py:290-301`, `apps/api/src/lonora_api/env.py:98` |
| `claim_next` | Takes `queued` Runs, or `leased`/`running` Runs whose lease expired and whose `recovery_count < 5`; skips Runs whose `environment.retry.not_before` is in the future; one active Run per thread; never a paused agent's Run. | `packages/db/src/lonora_db/runs.py:194-206`, `packages/db/src/lonora_db/runs.py:234-245` |
| Task checkpoint | Before each model turn and each tool segment the loop applies the owner's pause/cancel/complete at a safe boundary. | `packages/agent-runtime/src/lonora_agent/tool_loop.py:395-396`, `packages/agent-runtime/src/lonora_agent/tool_loop.py:442`, `packages/db/src/lonora_db/tasks.py:642-681` |
| Step `task_waits` (every 5 s) | Wakes Tasks whose timer, watch or broker recovery is ready. | `packages/gateway/src/lonora_gateway/service.py:46`, `packages/db/src/lonora_db/task_wait.py:167-232` |
| Step `task_retries` (every 10 s) | Re-queues Tasks whose automatic retry is due. | `packages/gateway/src/lonora_gateway/service.py:44`, `packages/db/src/lonora_db/task_recovery.py:334-363` |
| Step `outcomes` (every 10 s) | Returns terminal Run outcomes that were not delivered (crash window), 20 per pass. | `packages/gateway/src/lonora_gateway/service.py:47`, `packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:330-361` |
| Owner | `pause, resume, cancel, revise` through `POST /tasks/control`; «تحديد كمكتملة» through `POST /tasks/{id}/complete`. | `apps/api/src/lonora_api/routes/tasks.py:54-73`, `packages/contracts/src/lonora_contracts/tasks.py:88-93` |
| Agent | `task_control` (same actions, own Tasks only), `task_step_update`, `task_wait`, `task_inspect`. | `packages/tools/src/lonora_tools/tasks.py:87-126` |

### 1.4 Budgets, continuation, deadlines

- Rounds per slice: `maximum_tool_rounds`, default 24, range 1–100
  (`apps/api/src/lonora_api/env.py:97`).
- A Task Run gets up to `MAXIMUM_SLICES = 4` slices
  (`packages/agent-runtime/src/lonora_agent/continuation.py:20`), so 96 model rounds by
  default; an ordinary Run gets one slice
  (`packages/agent-runtime/src/lonora_agent/continuation.py:26-27`). At the end of a
  slice the Run is checkpointed and re-queued
  (`packages/agent-runtime/src/lonora_agent/continuation.py:83-90`,
  `packages/agent-runtime/src/lonora_agent/tool_loop.py:411-416`).
- A real external wake (timer, watch, broker) starts a fresh budget: `rounds` is set to 0
  and `task_continuation` is dropped (`packages/db/src/lonora_db/task_wait.py:138-150`).
  A worker restart does not (`packages/agent-runtime/src/lonora_agent/continuation.py:24`).
- Two rounds before the end the model gets a notice; the last turn is a tool-less final
  report (`packages/agent-runtime/src/lonora_agent/tool_loop.py:114`,
  `packages/agent-runtime/src/lonora_agent/tool_loop.py:472-488`).
- Stop gates: a continuous Task that tries to end with text, or a finite Task with
  unfinished declared steps, is nudged at most `MAXIMUM_STOP_NUDGES = 2` times, then the
  work is handed to the owner (`packages/agent-runtime/src/lonora_agent/stop_gates.py:41`,
  `packages/agent-runtime/src/lonora_agent/stop_gates.py:126-129`,
  `packages/agent-runtime/src/lonora_agent/loop_outcomes.py:175-178`).
- Deadline: `due_at` is "When the owner expects the work done. A target, not a trigger."
  (`packages/contracts/src/lonora_contracts/tasks.py:49-51`). It is only written into the
  Task prompt as `"Due by: ..."` (`packages/db/src/lonora_db/tasks.py:244-245`). No code
  compares it to the clock: a search for `due_at` in `packages/**.py` outside attention
  and wait code finds only `packages/db/src/lonora_db/tasks.py:195` and
  `packages/db/src/lonora_db/tasks.py:244-245`. A missed deadline is never reported.
- Completion: a Run can complete only when all declared steps are `completed`/`skipped`,
  and never for a continuous Task (`packages/db/src/lonora_db/tasks.py:839-850`). A step
  can be marked completed only with ids of real successful tool calls; a financial call
  counts only when `confirmed` (`packages/db/src/lonora_db/tasks.py:703-752`). Needed for
  safety (no invented progress).

### 1.5 Waits

- `task_wait` kinds: `watch`, `broker_recovery`, `timer`; timer 5 s to 604800 s (7 days)
  (`packages/contracts/src/lonora_contracts/tasks.py:109-112`). Tool text: "Suspend this
  same durable Task until its owned market watch triggers, its broker recovery is
  verified, or a timer is due. ..." (`packages/tools/src/lonora_tools/tasks.py:89-96`).
- Admission checks the watch belongs to the same agent and thread and is enabled; else
  `task_wait_source_invalid` (`packages/db/src/lonora_db/task_wait.py:32-42`).
- Settlement puts the Run in `waiting_takeover`, the Task in `waiting` with reason
  `external_<kind>`, and posts the model's accompanying text to the **origin**
  conversation (`packages/db/src/lonora_db/task_wait_settlement.py:100-119`,
  `packages/db/src/lonora_db/task_wait_settlement.py:170-176`).
- Wake: `resume_ready_waits` selects 50 per pass and re-queues the same Run with a
  `last_wake` record (`packages/db/src/lonora_db/task_wait.py:207-222`,
  `packages/db/src/lonora_db/task_wait.py:131-153`); the loop delivers it to the model as
  `<runtime_wake>` once (`packages/agent-runtime/src/lonora_agent/loop_restore.py:105-113`).
- Owner question wait (`wait_for_input`): the Run goes to `waiting_input`
  (`packages/agent-runtime/src/lonora_agent/executor.py:245-253`).

### 1.6 Failure states and what the owner sees

How a failed Task Run is classified (`record_failure`):

| Condition | Recovery | Task status | Evidence |
|---|---|---|---|
| Unresolved financial operation, or an unresolved call to a tool that is not read-only | `reconcile` (`financial` / `external`) | `failed` | `packages/db/src/lonora_db/task_recovery.py:120-123`, `packages/db/src/lonora_db/task_recovery.py:163` |
| Code in `PLAN_CODES` (`model_request_rejected`, `context_limit_exceeded`, `tool_round_limit`, `task_steps_incomplete`, `task_wait_required`) | `modify_plan` | `failed` | `packages/db/src/lonora_db/task_recovery.py:25-33`, `packages/db/src/lonora_db/task_recovery.py:124-125` |
| Transient or owner-fixable code and attempts left | `owner`, or `automatic` when the policy allows and only reads are outstanding | `failed`, or `waiting`/`retry_backoff` | `packages/db/src/lonora_db/task_recovery.py:126-155`, `packages/db/src/lonora_db/task_recovery.py:179-181` |
| Any other code | `terminal` | `failed` | `packages/db/src/lonora_db/task_recovery.py:119` |

- Default retry policy: `mode="owner"`, `maximum_attempts=3`, `initial_delay_seconds=15`
  (`packages/contracts/src/lonora_contracts/tasks.py:15-18`). Automatic delay is
  `min(300, initial * 2^(attempt-1))` (`packages/db/src/lonora_db/task_recovery.py:164-171`).
- An automatic retry that itself fails five times is quarantined and the Task becomes
  `failed` with recovery `owner` (`packages/db/src/lonora_db/item_failures.py:26`,
  `packages/db/src/lonora_db/task_recovery.py:285-312`,
  `packages/db/src/lonora_db/task_recovery.py:353`).
- A reconciliation is never retried automatically
  (`packages/db/src/lonora_db/task_recovery.py:323-331`). Needed for safety.

What reaches the owner:

1. **No chat message on failure.** The final message to the origin conversation is
   written only when the Run has a result or rich content
   (`packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:128-153`); a
   failed Run has none.
2. **One notification.** `task.failed` becomes attention code `task_review`,
   `action_required` when recovery is `owner` or `modify_plan`, else `important_change`
   (`packages/core/src/lonora_core/attention.py:102-108`). Web label: `Task needs review`
   (`apps/web/src/components/ai/AttentionInbox.tsx:25`) = «المهمة تحتاج مراجعة»
   (`apps/web/src/i18n/locales/ar/messages.po:7010-7011`). Off-app text: «تحتاج المهمة إلى
   مراجعتك. افتح المحادثة لفحص سبب التوقف وخيارات الاستكمال.»
   (`packages/bus/src/lonora_bus/attention_messages.json:7`). The inbox row shows the
   label, the agent name and a symbol if any — no reason
   (`apps/web/src/components/ai/AttentionInbox.tsx:114-121`).
3. **Task page.** `failed` and `waiting` both render `Awaiting review`
   (`apps/web/src/shell/domain/TasksPages.tsx:40-42`) = «بانتظار المراجعة»
   (`apps/web/src/i18n/locales/ar/messages.po:1074-1075`). So a healthy Task sleeping on a
   timer reads the same as a failed one. The page shows title, description, agent, due
   time, criterion and buttons only — no failure reason, no steps, no last report
   (`apps/web/src/shell/domain/TasksPages.tsx:194-203`).
4. **Resume is offered only in some cases.** `can_resume` is true for `paused`, for
   `failed` with recovery `owner` (or a settled financial reconcile) and attempts left,
   and for an owner-attention wait (`packages/db/src/lonora_db/tasks.py:341-352`,
   `packages/db/src/lonora_db/tasks.py:385-392`). For `modify_plan`, `terminal` and
   `reconcile/external` the resume is refused with `task_cannot_resume` or
   `task_reconciliation_required` (`packages/db/src/lonora_db/task_recovery.py:236-244`),
   and after 3 attempts with `task_retry_limit`
   (`packages/db/src/lonora_db/task_recovery.py:245-246`). The Task page has no "revise"
   control; its buttons are "View conversation" (opens the origin thread,
   `apps/web/src/shell/domain/TasksPages.tsx:204-211`), Pause, Resume, Mark as completed,
   Delete (`apps/web/src/shell/domain/TasksPages.tsx:213-249`). The API accepts `revise`
   (`apps/api/src/lonora_api/routes/tasks.py:54-59`) and a revision turns `modify_plan`
   into `owner` (`packages/db/src/lonora_db/tasks.py:454-457`), but a search of `apps/web/src`
   and `apps/mobile` for `"revise"` found no client that sends it (every web and mobile caller of
   `/tasks/control` sends only pause, resume or cancel:
   `apps/web/src/shell/domain/api.ts:55`, `apps/web/src/components/ai/AgentLiveStatus.tsx:107-117`,
   `apps/web/src/conversation/sheets/AgentSheet.tsx:410-422`,
   `apps/web/src/pages/Board.tsx:557-561`, `apps/mobile/components/agent-live-status.tsx:147-150`);
   in practice only the agent tool `task_control` can revise
   (`packages/tools/src/lonora_tools/tasks.py:120-125`). So a Task that stopped at
   `tool_round_limit` or `context_limit_exceeded` as a *Run failure* is a dead end for the
   owner unless the agent can reach `task_control`. UNSURE whether it can: the production
   trace lists 23 native tools offered to the model and `task_control` is not among them
   (`TIMELINE_CORRECTION.md`, reading point 2), and the one `tool_environment` query made
   in that conversation returned an empty list (same file, reading point 4). Web text for these
   codes: "This task cannot resume in its current state. Review its plan or retry limit."
   (`apps/web/src/lib/user_error.ts:214-216`).
5. **Completion.** `task.updated` with status `completed` is `informational`
   (`packages/core/src/lonora_core/attention.py:115-116`) and informational items are off
   by default (`packages/contracts/src/lonora_contracts/attention.py:42`,
   `packages/db/src/lonora_db/attention.py:147-148`). The owner learns of completion from
   the final message in the origin conversation, if the Run produced text.

### 1.7 "Needs the owner" instead of failing (owner attention)

- At a work limit, after spent stop nudges, or after a long model outage the Task is not
  failed; the Run waits with a question of kind `owner_attention`
  (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:109-152`,
  `packages/agent-runtime/src/lonora_agent/tool_loop.py:302-311`,
  `packages/agent-runtime/src/lonora_agent/tool_loop.py:553-559`).
- Owner-facing Arabic strings, verbatim
  (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:142-169`):
  - `task_steps_incomplete`: «هذه المهمة لم تكتمل بعد.»
  - `task_wait_required`: «هذه المهمة المستمرة غير مراقَبة: لم يُحفظ أي انتظار مراقبة أو
    مؤقت مراجعة، لذلك لن تحدث أي متابعة تلقائية.»
  - `tool_round_limit`: «توقفت هذه المهمة قبل اكتمالها لأن هذه الجولة بلغت حدّ العمل، ولم
    يُنفَّذ أي إجراء بعد ذلك.»
  - `guardrail_halt`: «توقفت هذه المهمة قبل اكتمالها لأن استدعاء أداة تكرر دون تقدّم، ولم
    يُنفَّذ أي إجراء بعد ذلك.»
  - `model_unavailable`: «هذه المهمة معلّقة لأن كل النماذج المهيأة غير متاحة منذ مدة رغم
    المحاولات المتكررة؛ تقدّمها محفوظ ولم يُكرَّر أي إجراء.»
  - closing line: «أحتاج توجيهك قبل المتابعة: ردّ هنا، أو عدّل المهمة أو استأنفها أو أوقفها
    مؤقتًا أو ألغها.» (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:190-195`)
  - then «آخر تقرير: » plus the model's last text
    (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:203`).
- These sentences are jargon for a non-technical owner («الجولة», «حدّ العمل», «انتظار
  مراقبة», «استدعاء أداة») and all five carry the closing line, which asks him to choose
  between revise / resume / pause / cancel: `attention_notice` appends it unconditionally
  (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:190-195`). It also lists
  «الخطوات غير المكتملة: ...» when steps are open
  (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:180-189`).
- **Where the message goes.** The executor writes it to the Run's own thread
  (`packages/agent-runtime/src/lonora_agent/executor.py:143`,
  `packages/agent-runtime/src/lonora_agent/executor.py:176-187`). For a Task Run that is
  the hidden work thread (`packages/db/src/lonora_db/tasks.py:176-178`,
  `packages/db/src/lonora_db/tasks.py:212`). The notification (`task.attention_required`,
  `packages/db/src/lonora_db/tasks.py:787-795`) is attached to the **origin** conversation
  (`packages/gateway/src/lonora_gateway/attention.py:271-281`). On the web the item's
  "Open conversation" link goes to `/app/<agent_id>` with no thread in it
  (`apps/web/src/components/ai/AttentionInbox.tsx:123-130`, `:135-139`), and a page without
  a requested thread opens the saved thread, else the oldest one
  (`apps/web/src/hooks/usePersistentThread.ts:58-66`); UNSURE whether that is the origin
  thread when the owner has more than one conversation with the agent. The text says «ردّ هنا»,
  but an owner message steers only a Run in the thread it was sent to
  (`packages/db/src/lonora_db/messages.py:516-525`). The same applies to an ordinary
  `wait_for_input` question asked by a Task Run: it is posted in the work thread and
  raises no notification at all (`run.waiting_input` is not in `ATTENTION_KINDS`,
  `packages/core/src/lonora_core/attention.py:7-35`).
  UNSURE: whether any client screen opens a work thread. `work_thread_id` appears in the
  web type (`apps/web/src/shell/domain/api.ts:23`) and the gateway copies it into the
  attention item's parameters (`packages/gateway/src/lonora_gateway/attention.py:273`);
  a search of `apps/web/src` and `apps/mobile` found no other use. The Task page's "View
  conversation" button goes to the origin thread, not the work thread
  (`apps/web/src/shell/domain/TasksPages.tsx:204-211`).
- The owner's Resume (Task page) does continue such a Task and gives it a new budget
  (`packages/db/src/lonora_db/tasks.py:507-516`,
  `packages/agent-runtime/src/lonora_agent/loop_restore.py:68-88`).

### 1.8 Silent stalls of a waiting Task

- **Watch wait with a dead watch.** Readiness needs the watch to have a new
  `last_triggered` (`packages/db/src/lonora_db/task_wait.py:179-189`). The watch's
  enabled state is checked only when the wait is admitted
  (`packages/db/src/lonora_db/task_wait.py:40`). If the watch later expires
  (`packages/market/src/lonora_market/watchers.py:462-484`), is paused or cancelled
  (`packages/db/src/lonora_db/market_watches.py:172-179`), is quarantined
  (`packages/market/src/lonora_market/watchers.py:59-66`) or keeps failing to observe
  (§3.5), the Task stays `waiting` with no end. The watchdog counts only overdue *timer*
  waits (`packages/gateway/src/lonora_gateway/watchdog.py:266-275`).
- **Broker-recovery wait.** Ready only when the broker session reports `connected` with
  `observed_at >= wait.created_at` (`packages/db/src/lonora_db/task_wait.py:190-199`).
  There is no timeout. UNSURE: whether `observed_at` is refreshed for a broker that was
  already connected when the wait was created.
- **Paused agent.** Its Runs are not claimed (`packages/db/src/lonora_db/runs.py:244`);
  timers still fire into `queued` but nothing runs until the agent is resumed. Needed
  for safety when the owner paused it; silent otherwise.
- **Model outage, continuous Task.** Retries with backoff base 30 s, cap 900 s; the owner
  is told once after 6 failures; the work is held only after 12 hours
  (`packages/agent-runtime/src/lonora_agent/model_recovery.py:63`,
  `packages/agent-runtime/src/lonora_agent/model_recovery.py:187-197`). The notice is
  `task.degraded` (`packages/db/src/lonora_db/tasks.py:822-836`) → `task_degraded`
  (`packages/core/src/lonora_core/attention.py:112-114`) → "Task is retrying through a
  model outage" (`apps/web/src/components/ai/AttentionInbox.tsx:26`) = «المهمة تعيد
  المحاولة أثناء تعطل النموذج» (`apps/web/src/i18n/locales/ar/messages.po:7004-7005`). The
  off-app catalog has no `task_degraded` entry, so it would fall back to «يوجد تحديث محفوظ
  في Lonora.» (`packages/bus/src/lonora_bus/attention.py:19-21`,
  `packages/bus/src/lonora_bus/attention_messages.json:8`); but off-app delivery skips
  `important_change` anyway (§4.4).

### 1.9 Legacy tickets

- `ticket_start` runs a plain ticket as a Run with `trigger="tickets"` in the ticket's
  thread (`packages/agent-runtime/src/lonora_agent/automation/background.py:42-57`). A
  ticket Run's reply is never written as a message
  (`packages/db/src/lonora_db/runs.py:379`); only the ticket row gets `result` and a
  status (`done`, `waiting` for a limited Run, or the Run status)
  (`packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:99-113`). No
  notification follows. Tool description: "Run an owned ticket through the same agent
  runtime." (`packages/tools/src/lonora_tools/runtime_control.py:185-190`).

---

## 2. Routines

### 2.1 Schedule format

- Exactly one of three (`one_schedule_required`):
  `interval_seconds` (60 to 31536000), `cron` (a croniter expression) with `timezone`
  (default `"UTC"`), or `run_at` (one-shot, timezone required, not more than one minute
  in the past: `run_at_past`)
  (`packages/contracts/src/lonora_contracts/routines.py:13-27`,
  `packages/contracts/src/lonora_contracts/routines.py:33-48`).
- Cron and timezone are validated when the next time is computed: `invalid_cron`,
  `invalid_timezone` (`packages/core/src/lonora_core/cron.py:9-16`).
- Tool text: "Schedule this same agent with either a cron expression/timezone or an
  interval; work continues with the browser closed."
  (`packages/tools/src/lonora_tools/routine.py:107-112`). The description does not
  mention the one-shot `run_at` although the schema has it.

### 2.2 Who fires them

- Gateway step `routines`, every 5 s, timeout 120 s
  (`packages/gateway/src/lonora_gateway/service.py:43`,
  `packages/gateway/src/lonora_gateway/service.py:264`). `dispatch_routines` takes up to
  30 due routines and fires each in its own transaction
  (`packages/automation/src/lonora_automation/runner.py:6-20`).
- Due means: enabled, `next_run_at <= now`, agent not paused, and not an already fired
  one-shot (`packages/db/src/lonora_db/routines.py:101-112`).
- A fire creates a Run with `trigger="routine"` and the stored prompt in the routine's
  thread (`packages/db/src/lonora_db/routines.py:188-202`). The Run has scope `full`
  (`packages/tools/src/lonora_tools/base.py:53-58`); money still goes through the grant
  or an approval card at the executor: the doc line says "Money still follows the Agent's
  signed grant, the account limits, pauses and the manual-positions switch at the
  executor" (`docs/proactive-wakes.md:33-35`); the approval-card path is the repository's
  general rule, not stated in those lines. Needed for safety.
- The fire does not check whether the previous Run of the routine is still queued or
  running; it always adds a Run (`packages/db/src/lonora_db/routines.py:188-202`). Only
  one Run per thread executes at a time (`packages/db/src/lonora_db/runs.py:234-240`), so
  a slow routine with a short interval builds a queue.

### 2.3 Missed fires

- Recurring: "Collapse missed schedules into one wake; never replay a burst after
  downtime." The next time is computed from the old `next_run_at`, and from now if that
  is still in the past (`packages/db/src/lonora_db/routines.py:233-236`). After downtime
  the routine fires once, late.
- One-shot: it fires when the gateway next sees it due, however late, then switches off
  (`packages/db/src/lonora_db/routines.py:214-217`).
- Goal-linked one-shot: retries every 5 minutes while its goal can still reach the step
  (`packages/db/src/lonora_db/routines.py:17`,
  `packages/db/src/lonora_db/routines.py:218-220`).
- A paused agent's routines are skipped while paused and fire once after resume (same
  due query, `packages/db/src/lonora_db/routines.py:108`).
- Watchdog: routines more than 5 minutes overdue raise one `gateway_degraded` item
  (`packages/gateway/src/lonora_gateway/watchdog.py:47`,
  `packages/gateway/src/lonora_gateway/watchdog.py:249-292`).

### 2.4 Where the result goes

- A non-goal routine gets its own new thread titled with the first 80 characters of the
  prompt (`packages/db/src/lonora_db/routines.py:67-70`); the column default makes it a
  `conversation` thread (`packages/db/src/lonora_db/schema.py:227-229`). The Run's reply
  is written there (`packages/db/src/lonora_db/runs.py:379-394`).
- The web opens the thread requested in the link, else the thread last saved in the
  browser, else the *oldest* thread of the agent
  (`apps/web/src/hooks/usePersistentThread.ts:58-66`), so a routine's replies are not in
  the chat the owner normally sees. The schedules page has no result or history view (a
  search of `apps/web/src/shell/domain/SchedulesPages.tsx` for `thread`, `history`,
  `runs` finds none); the API has one (`apps/api/src/lonora_api/routes/routines.py:68-72`).
  UNSURE: whether another screen (Activity) links to a routine's thread.
- No notification is raised when a routine Run completes or fails: `run.completed`,
  `run.failed` and `message.created` are not in `ATTENTION_KINDS`
  (`packages/core/src/lonora_core/attention.py:7-35`). The owner hears of a routine's
  result only if the agent itself calls `owner_notify` (§4.3).
- A routine Run may end with no text at all: an empty turn is accepted for
  non-conversational triggers and recorded as `reply_outcome: "silent"`
  (`packages/agent-runtime/src/lonora_agent/tool_loop.py:573-579`,
  `packages/agent-runtime/src/lonora_agent/tool_loop.py:603-605`,
  `packages/core/src/lonora_core/run_state.py:33-34`).

### 2.5 Ways a routine stops silently

| Case | What happens | Owner told? | Evidence |
|---|---|---|---|
| Firing raises 5 times | Routine is disabled (`enabled = False`) | Generic item, §6.2 | `packages/automation/src/lonora_automation/runner.py:10`, `packages/db/src/lonora_db/routines.py:151-156` |
| Goal plan version changed, or its step is gone | `row.enabled = False; return False` | No event | `packages/db/src/lonora_db/routines.py:171-177` |
| Goal target review no longer pending | `row.enabled = False; return False` | No event | `packages/db/src/lonora_db/routines.py:181-187` |
| One-shot whose goal ended | `row.enabled = False` | No event | `packages/db/src/lonora_db/routines.py:221-223` |
| Supervisor or owner pause | Agent's `routine_toggle` to re-enable is refused with `work_paused_by_owner` / `work_paused_by_supervisor` | Needed for safety (owner's stop wins) | `packages/tools/src/lonora_tools/routine.py:64-73`, `packages/db/src/lonora_db/supervision.py:440-445` |
| The Run fails | Nothing; next fire is a new Run | No | §4.5 |
| The Run asks a question (`wait_for_input`) | Run stays `waiting_input` in the routine thread; later fires add new Runs | No notification | `packages/agent-runtime/src/lonora_agent/tool_block.py:370-375`, `packages/agent-runtime/src/lonora_agent/executor.py:245-253` |

---

## 3. Watches

### 3.1 Kinds and conditions

- Kinds: `price, indicator, position, account, calendar, dynamic`
  (`packages/contracts/src/lonora_contracts/market_watch.py:15`).
- Conditions: `above, below, cross_above, cross_below, changed, closed, opened, due`
  (`packages/contracts/src/lonora_contracts/market_watch.py:24-26`), evaluated in
  `packages/core/src/lonora_core/market_watch.py:4-23`.
- Dynamic watches carry a `detector` tree; relationship detectors force
  `evaluation_mode="scheduled"` and need two different symbols
  (`packages/contracts/src/lonora_contracts/market_watch.py:47-59`).
- Tool text: "Persist a server-side price, indicator, position, account, calendar or
  composite dynamic watch. ... It wakes this agent to reassess and never trades. One live
  watch per dedupe_key." (`packages/tools/src/lonora_tools/market_watch.py:237-244`).

### 3.2 Cadence and limits

| Setting | Value | Evidence |
|---|---|---|
| Poll step | every 2 s, timeout 120 s | `packages/gateway/src/lonora_gateway/service.py:56` |
| Batch | up to 200 due watches per pass, checked one after another | `packages/market/src/lonora_market/watchers.py:430`, `packages/market/src/lonora_market/watchers.py:436-444` |
| Per-watch observation timeout | 20 s | `packages/market/src/lonora_market/watchers.py:52`, `packages/market/src/lonora_market/watchers.py:513` |
| `interval_seconds` | default 30, minimum 5 | `packages/contracts/src/lonora_contracts/market_watch.py:31` |
| `cooldown_seconds` | default 300, minimum 30 | `packages/contracts/src/lonora_contracts/market_watch.py:30` |
| `required_observations` / `debounce_seconds` | 1–1000 / 0–86400 | `packages/contracts/src/lonora_contracts/market_watch.py:19-20` |
| `expires_at`, `confirmation_ttl_seconds` | optional | `packages/contracts/src/lonora_contracts/market_watch.py:17-18` |
| Stream-driven checks | a live quote or candle also triggers `check_watches` for matching price/indicator/dynamic watches | `packages/market/src/lonora_market/runtime.py:202-207`, `packages/market/src/lonora_market/runtime.py:299-304`, `packages/market/src/lonora_market/watchers.py:417-429` |

UNSURE: no limit on the number of watches per agent was found (a search for
`watch_limit`, `maximum_watches`, `MAX_WATCH` in `packages` found only
`relationship_watch_limit`, `packages/contracts/src/lonora_contracts/market_intelligence.py:105`,
and `WATCH_LIMIT = 8`, `packages/db/src/lonora_db/operational_state.py:55`). That constant is
not a creation limit: it caps how many enabled watches are listed in the agent's operational
state (`packages/db/src/lonora_db/operational_state.py:208-216`).

### 3.3 Lifecycle and firing

- Lifecycle: `pending → forming → confirmed`, `invalidated`, `expired`
  (`packages/market/src/lonora_market/watch_lifecycle.py:56-91`).
- Fires when confirmed and the cooldown has passed
  (`packages/market/src/lonora_market/watchers.py:632-635`,
  `packages/market/src/lonora_market/watch_control.py:6-11`); one fire per observation
  through `MarketWakeReceiptRow` (`packages/market/src/lonora_market/watchers.py:636-637`,
  `packages/market/src/lonora_market/watchers.py:703-714`).
- An ordinary watch creates a Run with `trigger="watch"` and the watch's prompt in the
  watch's thread (`packages/market/src/lonora_market/watchers.py:675-701`). A watch made
  in chat or by a wake belongs to the agent's conversation
  (`packages/tools/src/lonora_tools/market_watch.py:96-102`), so its Run's reply appears
  in the chat.
- A Task-owned watch creates no Run; the `task_waits` step resumes the Task
  (`packages/market/src/lonora_market/watchers.py:654-677`).
- A goal-linked watch fires only while its goal is active/waiting on that step
  (`packages/market/src/lonora_market/watchers.py:638-653`). Needed for safety.

### 3.4 Dedupe

- With `dedupe_key`: one live watch per agent and key; same condition returns it with
  `deduplicated: true`; a changed condition disables the old one with
  `state.code = "watch_replaced"` (`packages/tools/src/lonora_tools/market_watch.py:108-128`).
- Without a key: an identical live watch in the same thread/Task is returned
  (`packages/tools/src/lonora_tools/market_watch.py:103-107`). This matches
  `docs/proactive-wakes.md:91-101`.

### 3.5 F1 — a watch on a symbol that does not exist never fires and says nothing

1. `watch_create` validates only the shape (`watch_symbol_required`,
   `watch_price_required`, ...; `packages/contracts/src/lonora_contracts/market_watch.py:66-71`).
   The handler makes no broker call and no catalog lookup
   (`packages/tools/src/lonora_tools/market_watch.py:90-145`). The helper that maps a
   name to the broker's spelling, `canonical_broker_symbol`
   (`packages/tools/src/lonora_tools/symbols.py:18-35`), is not used by this module.
2. At evaluation the broker read raises a `LonoraError`. In the MetaApi adapter any 404
   outside the candles stage is mapped to `broker_account_not_found`, before the symbol
   test (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:52-58`); a candles 404
   that names the symbol gives `symbol_not_found`
   (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:59-60`). Both codes in the
   owner's example are produced here.
3. `check_watch` catches every `LonoraError` and timeout from the observation, writes a
   health record with that code, moves `next_check` forward and returns normally
   (`packages/market/src/lonora_market/watchers.py:517-539`).
4. Because it returns normally, `ItemGuard.run` records no failure
   (`packages/db/src/lonora_db/item_failures.py:124-143`), so the watch is never
   quarantined and the quarantine notice is never raised.
5. The only signal is one `watch.suspended_health` event when the health state changes
   (`packages/market/src/lonora_market/watch_health.py:28-41`). The classifier has no
   branch for it, so it stays `silent` / `internal_update`
   (`packages/core/src/lonora_core/attention.py:57-61`) and is suppressed as
   `runtime_only` (`packages/db/src/lonora_db/attention.py:143-144`).
6. `watch_create` returned the stored row as a success
   (`packages/tools/src/lonora_tools/market_watch.py:145`); nothing later corrects that.

Result of the code path: a watch on a name the broker does not know is stored as a success,
then fails every check, and no message ever says so. The only code in the repository that
maps a typed name to the broker's own spelling is `canonical_broker_symbol`
(`packages/tools/src/lonora_tools/symbols.py:18-35`); the read tools use it
(`packages/tools/src/lonora_tools/market.py:47`, `:58`, `:65`, `:78`) and `watch_create` does
not.

Trace caveat (the trace wins): in the production conversation this path was NOT what
happened. The trace shows four watches, all on `EURUSDm`, and "No watch on XAUUSDm and no
+100 USD close watch exists, although the agent said it was monitoring"
(`production-trace.md:71`; `TIMELINE_CORRECTION.md`, reading point 7). So the owner's
belief that gold was being watched came from replies written with no `watch_create` call,
not from a watch that failed quietly. F1 is a real defect in the code, but it was not
exercised there.

### 3.6 Other ways a watch stops silently

| Case | What happens | Owner told? | Evidence |
|---|---|---|---|
| Observation keeps failing for a real outage | Same path as §3.5: health record only | No | `packages/market/src/lonora_market/watchers.py:517-539` |
| Code outside the observation raises 5 times (an error from `create_run` or a goal lookup) | Watch disabled, `state.code = "watch_quarantined"` | Generic item, §6.2 | `packages/market/src/lonora_market/watchers.py:433`, `packages/market/src/lonora_market/watchers.py:59-66` |
| Expiry | `watch.expired` event | Yes, as `thesis_invalidated`: "Setup validity changed" = «تغيّرت صلاحية الإعداد» — the same label as an invalidated setup | `packages/market/src/lonora_market/watchers.py:462-484`, `packages/core/src/lonora_core/attention.py:86-87`, `apps/web/src/components/ai/AttentionInbox.tsx:22`, `apps/web/src/i18n/locales/ar/messages.po:6424-6425` |
| Goal completed/cancelled or plan version changed | `enabled: False`, no event | No | `packages/market/src/lonora_market/watchers.py:490-500` |
| Task that owns the watch ended | `enabled: False`, `state.code = "task_terminal"`, no event | No | `packages/market/src/lonora_market/watchers.py:658-665` |
| Agent paused | Not evaluated at all | No (needed for safety when the owner paused it) | `packages/market/src/lonora_market/watchers.py:399` |
| Fixed-market agent, other symbol | A watch on another symbol is refused when it is created (`packages/tools/src/lonora_tools/market_binding.py:120-122`, called from `packages/tools/src/lonora_tools/registry.py:514`). The same check runs again in every observation (`packages/market/src/lonora_market/watchers.py:211-215`), so it only bites a watch saved before the agent's binding changed; then it raises inside the observation → health record only | No | `packages/market/src/lonora_market/watchers.py:211-215` |
| Watch marked `enabled: false` but still checked | UNSURE. The poll query excludes `enabled` false (`packages/market/src/lonora_market/watchers.py:402`) and `check_watch` returns early for it (`packages/market/src/lonora_market/watchers.py:458`), yet the production trace shows three watches with `enabled false` in the payload whose health was still refreshed every 30 s (`production-trace.md:71`; `TIMELINE_CORRECTION.md`, reading point 10). I could not find in the code why; the other session on the watch lifecycle owns this | No | as cited |
| Confirmed, but the "opportunity" notification fails re-validation | Notification suppressed (`attention_setup_not_current`, `attention_revalidation_timeout`); the watch Run still runs | Only through the Run's reply | `packages/gateway/src/lonora_gateway/attention.py:55-84`, `packages/gateway/src/lonora_gateway/attention.py:366-379` |
| Owner turned off opportunity notifications | Suppressed `owner_opportunity_preference` | By the owner's choice | `packages/db/src/lonora_db/attention.py:145-146` |

---

### 3.7 How a watch is stopped (added by the checker)

- The agent has `watch_list` ("Read this agent's durable market watches."), `watch_cancel`
  ("Stop one of your own watches; its record stays, and watch_resume undoes it."),
  `watch_pause`, `watch_resume` and `watch_update`
  (`packages/tools/src/lonora_tools/market_watch.py:246`, `:254`, `:261`, `:268`, `:276`).
- The owner can cancel, pause, resume or extend any watch through the API
  (`apps/api/src/lonora_api/routes/watches.py:28-41`); the web agent live-status panel has a
  cancel button per watch (`apps/web/src/components/ai/AgentLiveStatus.tsx:60-64`) and shows
  «Task needs review» for a failed Task (`apps/web/src/components/ai/AgentLiveStatus.tsx:102-105`).
- Trace caveat: in the production conversation the model was offered 23 native tools and
  `watch_list` and `watch_cancel` were not among them; they are reachable only through
  `tool_environment` and `tool_call`, and the single `tool_environment` query returned an
  empty list (`TIMELINE_CORRECTION.md`, reading points 2 and 4). The tools exist; in that
  conversation the model never saw them. Another session owns that fix.

## 4. Wakes

### 4.1 Sources (every place a background Run is created)

| Trigger | Source | Evidence |
|---|---|---|
| `routine` | routine fire | `packages/db/src/lonora_db/routines.py:195` |
| `watch` | watch fire; opportunity transition | `packages/market/src/lonora_market/watchers.py:684`, `packages/trading/src/lonora_trading/opportunities.py:421` |
| `tickets` | Task or ticket | `packages/db/src/lonora_db/tasks.py:214`, `packages/agent-runtime/src/lonora_agent/automation/background.py:45` |
| `broker_event` | reconciliation found external broker activity | `packages/trading/src/lonora_trading/broker_recovery.py:238` |
| `activation` | review after a grant is activated | `packages/db/src/lonora_db/activation_review.py:104` |
| `goal` | trading goal | `packages/trading/src/lonora_trading/goals.py:351` |
| `subagent` | `subagent_spawn` | `packages/agent-runtime/src/lonora_agent/collaboration/subagents.py:57` |
| `peer`, `follow_up` | peer message; returned outcome after the parent finished | `packages/agent-runtime/src/lonora_agent/collaboration/peer_messages.py:100`, `packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:264` |
| `webhook` | signed `POST /api/webhook` | `apps/api/src/lonora_api/routes/webhook.py:16-34`, `packages/agent-runtime/src/lonora_agent/automation/webhooks.py:18` |

`WORK_TRIGGERS` = `tickets, routine, watch, webhook, subagent, broker_event, activation`
(`packages/contracts/src/lonora_contracts/runs.py:7-9`); they use the `BACKGROUND` model
capability (`packages/agent-runtime/src/lonora_agent/tool_loop.py:333-335`) and never the
reserved conversation worker (`packages/db/src/lonora_db/runs.py:224-228`).

### 4.2 Dedupe

- Webhook: receipt `webhook:<owner,nonce>`
  (`packages/agent-runtime/src/lonora_agent/automation/webhooks.py:13-20`).
- Watch: receipt per watch+observation+condition
  (`packages/market/src/lonora_market/watchers.py:636-637`).
- Task wake: receipts `task-wake:` and `task-watch-observation:`
  (`packages/db/src/lonora_db/task_wait.py:115-123`).
- Broker and opportunity wakes: stable run ids and receipts, per
  `docs/proactive-wakes.md:48-67` (not re-verified in `lonora_trading` here; UNSURE on
  exact lines).
- Outcome return: receipt `outcome:<run>:<fence>`
  (`packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:25-26`,
  `packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:54-56`).

### 4.3 Quiet hours and rate limits

- Quiet hours apply only to agent-raised alerts (`owner_notify`) and calls: everything
  but `critical` is held until they end
  (`packages/db/src/lonora_db/attention.py:425`,
  `packages/db/src/lonora_db/attention.py:467-469`). Server-raised items
  (`decide_attention`, `raise_system_attention`) have no quiet-hours check
  (`packages/db/src/lonora_db/attention.py:118-301`,
  `packages/db/src/lonora_db/attention.py:569-668`). `docs/incoming-attention.md:29-32`
  says Lonora's own alerts "follow the notification settings, whatever the channel"; it
  does not mention quiet hours, so the quiet-hours part rests on the code alone.
- Quiet hours do not stop wake Runs from running; they only hold alerts.
- `owner_notify`: 6 per agent per rolling hour, else the tool fails with
  `owner_notify_rate_limited` (`packages/db/src/lonora_db/attention.py:335`,
  `packages/db/src/lonora_db/attention.py:396-397`); 6 critical per owner per hour, then
  a critical is downgraded to `important_change`
  (`packages/db/src/lonora_db/attention.py:339`,
  `packages/db/src/lonora_db/attention.py:411-413`); one item per agent and `dedupe_key`
  for ever (`packages/db/src/lonora_db/attention.py:374-384`).
- Reach-me channel `activity`: a non-critical agent alert raises no item
  (`packages/db/src/lonora_db/attention.py:457-466`).
- Server items: one per logical transition; related transitions within 3 s coalesce;
  urgent ones are due at once (`packages/db/src/lonora_db/attention.py:157-183`,
  `packages/db/src/lonora_db/attention.py:243-276`).

### 4.4 Delivery

- Agent alerts are in-app only (`NOTIFY_DELIVERY = "in_app"`,
  `packages/db/src/lonora_db/attention.py:341`; `docs/incoming-attention.md:82-84`).
- A Telegram/webhook integration receives only `attention.ready` items of importance
  `critical` or `action_required`, as one catalog sentence
  (`packages/gateway/src/lonora_gateway/event_dispatch.py:124-151`), plus assistant
  messages of its configured thread
  (`packages/gateway/src/lonora_gateway/event_dispatch.py:107-110`,
  `packages/gateway/src/lonora_gateway/event_dispatch.py:152-153`).
- Native background push does not exist: "**Native background/killed-app delivery is
  unavailable**" (`docs/incoming-attention.md:113-117`).
- Consequence: if the app is closed, a watch that fires, a Task that stops and a routine
  result reach the owner only when he next opens the app (unless a Telegram integration
  is set and the item is urgent).

### 4.5 F2 — what a wake Run may do, and what happens when it fails

- Scope: `helper` for subagents, `observe_only` when metadata says so, else `full`
  (`packages/tools/src/lonora_tools/base.py:53-58`). Outside `full`, financial tools are
  not permitted (`packages/tools/src/lonora_tools/base.py:92-97`). Needed for safety.
- A wake Run may ask the owner a question: `wait_for_input` is not limited by trigger
  (`packages/agent-runtime/src/lonora_agent/tool_block.py:370-375`,
  `packages/agent-runtime/src/lonora_agent/tool_block.py:392-393`). The question is
  written to the Run's thread (`packages/agent-runtime/src/lonora_agent/executor.py:176-187`)
  and no notification is raised.
- Model outage: background Runs retry the same checkpoint with base 30 s, cap 900 s, and
  give up after 6 consecutive failures (`WORK = BackoffProfile(30.0, 900.0, 6)`,
  `packages/agent-runtime/src/lonora_agent/model_recovery.py:61`); with these numbers
  that is about 15 minutes of waiting (30+60+120+240+480 s plus jitter,
  `packages/agent-runtime/src/lonora_agent/model_recovery.py:147-152`). A non-Task Run
  then fails with the provider's code
  (`packages/agent-runtime/src/lonora_agent/tool_loop.py:553-560`). A non-transient error
  (missing model, rejected key) fails at once
  (`packages/agent-runtime/src/lonora_agent/model_recovery.py:174-175`).
- When a wake Run fails:
  - `fail_run` emits `run.failed` (`packages/db/src/lonora_db/runs.py:478-487`); it is
    not an attention kind (`packages/core/src/lonora_core/attention.py:7-35`).
  - `return_outcome` writes to the origin conversation only for `broker_event`,
    `activation` and opportunity watches, and only when the Run has a result
    (`packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:164-185`).
  - The web error card is shown only for triggers `user` and `group` with no parent:
    "Failures belong to the owner's actual input, never to a background activity footer."
    (`apps/web/src/lib/failed-replies.ts:3-10`).
  - The manual retry endpoint refuses anything but `user`/`group` Runs
    (`packages/db/src/lonora_db/run_retry.py:26`,
    `packages/db/src/lonora_db/run_retry.py:91-98`).
  - For a watch, `last_triggered` and the wake receipt were written when the Run was
    created (`packages/market/src/lonora_market/watchers.py:703-715`), so the same
    observation never fires again and the cooldown applies.
- So a failed routine, watch, webhook or broker wake leaves no trace the owner sees. The
  exception is a Run quarantined after 5 worker crashes (§6.1).
- Round limit in a wake Run: it ends with a tool-less report and `reply_outcome:
  "limited"` (`packages/agent-runtime/src/lonora_agent/tool_loop.py:314-322`); if the
  model is unavailable for that report the fallback is «توقفت قبل إنهاء العمل لأن هذه
  الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.»
  (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:132-139`,
  `packages/agent-runtime/src/lonora_agent/tool_loop.py:284`).

---

## 5. Subagents

### 5.1 How spawned

- `subagent_spawn(task, model?)`: "Start a bounded temporary research run without
  creating a permanent agent identity, optionally on another of the owner's allowed
  models." (`packages/tools/src/lonora_tools/subagent.py:49-55`).
- It creates a new thread (default purpose `conversation`, title = first 80 characters of
  the task) and a Run with `trigger="subagent"`, `parent_run_id`, `depth + 1`,
  `return_thread_id` (`packages/agent-runtime/src/lonora_agent/collaboration/subagents.py:48-68`).
  The call returns at once with the queued Run's data; the parent does not block.
- A model outside the owner's allowed list is refused with
  `{"ok": False, "code": "subagent_model_not_allowed", "allowed_models": [...]}`
  (`packages/agent-runtime/src/lonora_agent/collaboration/subagents.py:29-37`).

### 5.2 Limits

- Depth: `context.depth >= 2` → `delegation_depth_exceeded`
  (`packages/agent-runtime/src/lonora_agent/collaboration/subagents.py:22-23`). In
  practice a helper cannot spawn at all: `subagent_spawn` is not read-only
  (`packages/tools/src/lonora_tools/subagent.py:49-55`) and a helper is permitted only
  read-only tools plus `workspace_execute` and `artifact_create`
  (`packages/tools/src/lonora_tools/base.py:50`,
  `packages/tools/src/lonora_tools/base.py:92-97`).
- Number: at most `maximum_subagents` (default 4, range 1–12) children of one parent Run
  in `queued, leased, running, waiting_input`, else `subagent_limit`
  (`packages/agent-runtime/src/lonora_agent/collaboration/subagents.py:38-47`,
  `apps/api/src/lonora_api/env.py:98`).
- Budget: one slice of `maximum_tool_rounds` (24)
  (`packages/agent-runtime/src/lonora_agent/continuation.py:26-27`).
- Model-outage profile: a subagent of a conversation uses `CONVERSATION` (base 10 s, cap
  60 s, 3 failures); a subagent of a Task uses `WORK`
  (`packages/agent-runtime/src/lonora_agent/tool_loop.py:208-220`,
  `packages/agent-runtime/src/lonora_agent/model_recovery.py:59`).

### 5.3 Tools they get

- Scope `helper`: read-only tools, `workspace_execute`, `artifact_create`; no financial
  tool, no memory write, no peer message, no new agent, no `wait_for_input`
  (`packages/tools/src/lonora_tools/base.py:46-50`,
  `packages/tools/src/lonora_tools/base.py:92-97`; `docs/proactive-wakes.md:15`). The
  executor also refuses broker mutations from a helper lineage
  (`docs/proactive-wakes.md:21-24`). Needed for safety.

### 5.4 How results return, and F3

- On a terminal child Run `return_outcome` writes a message into the parent's thread:
  `<peer_outcome run_id='…' status='…'>\n{child.result or child.error_code or status}\n</peer_outcome>`
  (`packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:216-229`).
- If the parent is still active the message is attached as steering; a parent in
  `waiting_input` is re-queued
  (`packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:245-252`).
  If the parent already completed, a `follow_up` Run is created with the prompt "Use the
  returned peer outcome to complete the owner's request."
  (`packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:253-274`).
  If the parent failed or was cancelled, the message is written and nothing reads it.
- A child that stopped at its limit is reported as `limited`, never `completed`
  (`packages/db/src/lonora_db/runs.py:28-37`).
- The parent can poll with `subagent_inspect`
  (`packages/tools/src/lonora_tools/subagent.py:56-65`).
- **F3 — raw code in the owner's chat.** For a failed child with no result the message
  body is `child.error_code` (same line 217), for example `model_provider_unavailable`,
  `runtime_error` or `run_recovery_limit`. The message is a normal assistant message in
  the parent's thread, announced with `message.created`
  (`packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:218-244`).
  The clients strip only the wrapper and show the body: "the owner sees only the result"
  (`packages/core/src/peer-outcome.ts:3-11`); mobile renders
  `peerOutcome(message.content).body` as Markdown
  (`apps/mobile/components/message-bubble.tsx:164`). So the owner sees a bare internal
  code as a chat bubble. UNSURE: the exact web rendering for a subagent outcome that has
  no peer-message row; on the web `peerOutcome` is called only in `PeerCard`
  (`apps/web/src/conversation/Cards.tsx:563-567`). Trace caveat: `subagent_spawn` is not
  among the 23 native tools the model was offered in the production conversation
  (`TIMELINE_CORRECTION.md`, reading point 2), so F3 is a code-path finding that the
  conversation did not exercise.
- Subagent threads are created as ordinary `conversation` threads
  (`packages/agent-runtime/src/lonora_agent/collaboration/subagents.py:48-50`,
  `packages/db/src/lonora_db/threads.py:47-49`), so `list_threads` returns them next to
  the owner's chat (`packages/db/src/lonora_db/threads.py:98-105`).

### 5.5 Failure handling

- A failed child goes through `fail_run` then `return_outcome`
  (`packages/agent-runtime/src/lonora_agent/executor.py:84-94`).
- A child that crashes its worker 5 times is quarantined, an attention item
  `run_quarantined` is raised and its outcome returned
  (`packages/gateway/src/lonora_gateway/watchdog.py:219-247`).
- Compatibility tool `child_agent_create` creates a permanent child agent; its
  description says to prefer `agent_create`
  (`packages/tools/src/lonora_tools/subagent.py:66-72`).

---

## 6. Faults, restarts, and what survives

### 6.1 Process model

- `lonora-api` and `lonora-gateway` are separate processes (`entrypoint.sh:5-10`). The
  API creates Runs and serves reads; its lifespan starts no background loop: it only
  ensures the Personal Agent and closes connections
  (`apps/api/src/lonora_api/app.py:86-96`). All background work is in the gateway
  (`apps/worker/src/lonora_worker/main.py:11-23`).
- The gateway runs every maintenance step as its own supervised task with its own
  interval and timeout (`packages/gateway/src/lonora_gateway/service.py:40-66`,
  `packages/gateway/src/lonora_gateway/liveness.py:99-138`).
- Graceful stop (SIGTERM/SIGINT, `apps/worker/src/lonora_worker/signals.py:6-9`): 25 s
  grace, then tasks are cancelled (`packages/gateway/src/lonora_gateway/shutdown.py:8-14`);
  this process's leased Runs go back to `queued` with reason `gateway_drained`
  (`packages/db/src/lonora_db/runs.py:490-526`).
- Hard kill: the lease (default 120 s, `apps/api/src/lonora_api/env.py:96`) expires and
  the Run is claimed again with `recovery_count + 1` and a new fence
  (`packages/db/src/lonora_db/runs.py:197-201`,
  `packages/db/src/lonora_db/runs.py:266-281`). The lease is renewed every third of its
  length while a Run executes (`packages/agent-runtime/src/lonora_agent/executor.py:44-73`).
- After 5 crash recoveries the watchdog fails the Run with `run_recovery_limit`, unless
  it has an unresolved financial operation, in which case it is held (needed for safety)
  (`packages/db/src/lonora_db/runs.py:21`,
  `packages/db/src/lonora_db/runs.py:529-577`). A non-Task Run raises `run_quarantined`:
  "Work stopped after repeated interruptions" = «توقف عمل بعد انقطاعات متكررة»
  (`packages/gateway/src/lonora_gateway/watchdog.py:230-242`,
  `apps/web/src/components/ai/AttentionInbox.tsx:33`,
  `apps/web/src/i18n/locales/ar/messages.po:8528-8529`). A Task Run becomes a Task failure
  with recovery `owner` (`packages/db/src/lonora_db/task_recovery.py:46-47`).

### 6.2 F7 — per-item quarantine

- A routine, watch, Task retry, Task wait, outcome, attention event or integration that
  raises (or exceeds 45 s) backs off 10 s doubling to 600 s and is quarantined after 5
  failures (`packages/db/src/lonora_db/item_failures.py:26-32`,
  `packages/db/src/lonora_db/item_failures.py:51-52`,
  `packages/db/src/lonora_db/item_failures.py:180-187`).
- The owner item is `maintenance_item_quarantined` with parameters
  `{"item_kind": ..., "reason_code": ...}` and no agent or thread
  (`packages/db/src/lonora_db/item_failures.py:222-232`), so it opens the Personal
  Agent's conversation (`packages/db/src/lonora_db/attention.py:561-562`). Label: "A
  background item was paused after repeated errors; everything else keeps running"
  (`apps/web/src/components/ai/AttentionInbox.tsx:32`) = «أُوقف عنصر في الخلفية بعد أخطاء
  متكررة؛ يستمر كل ما عداه في العمل» (`apps/web/src/i18n/locales/ar/messages.po:242-243`).
  The inbox row prints neither `item_kind` nor the item's name
  (`apps/web/src/components/ai/AttentionInbox.tsx:114-121`).
- Importance is `important_change` (`packages/db/src/lonora_db/attention.py:35`), so it
  is not sent off-app (§4.4).
- `task_wait` and `outcome` items have no quarantine action
  (`packages/db/src/lonora_db/task_wait.py:223`,
  `packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:353`): after 5
  failures the ledger row blocks them for good
  (`packages/db/src/lonora_db/item_failures.py:55-70`) and the owner gets only the
  generic item above. A Task blocked this way stays `waiting`; an outcome blocked this
  way is never returned to its parent.

### 6.3 Gateway watchdog

- Every 30 s (`packages/gateway/src/lonora_gateway/service.py:64`): stalled critical
  steps, crash-looping Runs, overdue routines/timer waits, uncertain financial
  operations older than 15 minutes (`packages/gateway/src/lonora_gateway/watchdog.py:44-48`,
  `packages/gateway/src/lonora_gateway/watchdog.py:84-90`). "It never sends, resends or
  decides a trade" (`packages/gateway/src/lonora_gateway/watchdog.py:5-6`). Needed for
  safety.
- `gateway_degraded` label: "Background service is running late" = «خدمة الخلفية متأخرة»
  (`apps/web/src/components/ai/AttentionInbox.tsx:36`,
  `apps/web/src/i18n/locales/ar/messages.po:1108-1109`); off-app sentence «خدمة الخلفية في
  لونورا متأخرة. ستستمر في المحاولة وتبلغك عند الحاجة.»
  (`packages/bus/src/lonora_bus/attention_messages.json:15`). It gives the owner nothing
  to do.
- The watchdog runs inside the gateway. If the gateway process is down, nothing raises
  an item; only the health endpoint reports not ready
  (`packages/gateway/src/lonora_gateway/health.py:20-42`).

### 6.4 What survives a restart

| Thing | Survives? | Evidence |
|---|---|---|
| Run checkpoint (messages, pending calls, rounds, budgets, stop-gate counters) | Yes, in `RunRow.execution_state` | `packages/agent-runtime/src/lonora_agent/tool_loop.py:117-126`, `packages/db/src/lonora_db/runs.py:330-333` |
| Task state, steps, attempts, failure | Yes, in the ticket row | `packages/db/src/lonora_db/tasks.py:88-99` |
| Timers: routine `next_run_at`, Task `wait.due_at`, retry `not_before`, watch `next_check` | Yes, all database values polled by steps | `packages/db/src/lonora_db/routines.py:107`, `packages/db/src/lonora_db/task_wait.py:200-203`, `packages/db/src/lonora_db/runs.py:205-206`, `packages/market/src/lonora_market/watchers.py:410-412` |
| Tool-call receipts / effect receipts | Yes (`EffectReceiptRow`) | `packages/db/src/lonora_db/task_wait.py:52-73` |
| Model-outage streak and backoff | Yes, in the checkpoint | `packages/agent-runtime/src/lonora_agent/model_recovery.py:89-93`, `packages/agent-runtime/src/lonora_agent/tool_loop.py:529-535` |
| Final report at a limit | Yes: "a restart commits the same text instead of making another model call" | `packages/agent-runtime/src/lonora_agent/tool_loop.py:237-243` |
| Failure ledger (backoff, quarantine) | Yes (`ItemFailureRow`) | `packages/db/src/lonora_db/item_failures.py:154-169` |

### 6.5 What is lost or delayed

| Thing | Effect | Evidence |
|---|---|---|
| The in-flight model request | Repeated from the last checkpoint after re-claim | `packages/agent-runtime/src/lonora_agent/tool_loop.py:329-339` |
| An in-flight mutating tool call without a receipt | Treated as uncertain, not re-executed (needed for safety) | `docs/lonora-specs/S19_ACCEPTANCE.md:38` |
| Time | Up to the lease length (120 s) after a hard kill before the Run resumes | `packages/db/src/lonora_db/runs.py:197-198`, `apps/api/src/lonora_api/env.py:96` |
| Step liveness records and watchdog episodes | In memory; rebuilt; old "running late" items are withdrawn by the next watchdog | `packages/gateway/src/lonora_gateway/liveness.py:69-73`, `packages/gateway/src/lonora_gateway/watchdog.py:78-80`, `packages/gateway/src/lonora_gateway/watchdog.py:147-189` |
| Per-owner service objects (broker connections, voice tasks) | Rebuilt on first use | `packages/gateway/src/lonora_gateway/service.py:144-157`, `packages/gateway/src/lonora_gateway/service.py:97` |
| Missed recurring routine fires | Collapsed into one | `packages/db/src/lonora_db/routines.py:235-236` |
| Watch observations during downtime | Not replayed; price `cross_*` conditions compare against the stored last value at the next check | `packages/market/src/lonora_market/watchers.py:576-580`, `packages/core/src/lonora_core/market_watch.py:11-14` |

The owner is not told that a restart happened; a drained Run emits only `run.queued`
with `reason_code: "gateway_drained"` (`packages/db/src/lonora_db/runs.py:517-525`).

---

## 7. Complete list: background work that dies silently or ends with a technical message

"Silent" = no chat message in the owner's conversation and no attention item.

| # | Situation | What the owner gets | Evidence |
|---|---|---|---|
| 1 | Watch on a wrong or unknown symbol | Silent, for ever | §3.5 |
| 2 | Watch cannot observe during a broker outage | Silent | `packages/market/src/lonora_market/watchers.py:517-539`, `packages/core/src/lonora_core/attention.py:59-61` |
| 3 | Watch fired, its Run failed (model down, error) | Silent; trigger consumed | §4.5 |
| 4 | Routine Run failed | Silent | §4.5 |
| 5 | Routine Run succeeded | Reply only in the routine's own thread; no notification | §2.4 |
| 6 | Routine or wake Run asked a question | Question in that Run's thread; no notification | §2.5, §4.5 |
| 7 | Goal-linked routine or watch switched off after a plan change | Silent | `packages/db/src/lonora_db/routines.py:171-187`, `packages/market/src/lonora_market/watchers.py:490-500` |
| 8 | Task waits on a dead watch | Silent, for ever; Task page says «بانتظار المراجعة» | §1.8 |
| 9 | Task missed its `due_at` | Silent | §1.4 |
| 10 | Task failed | One item «المهمة تحتاج مراجعة» with no reason; no chat message | §1.6 |
| 11 | Task failed with `modify_plan` / `terminal` / `reconcile external` | Same item; no Resume; refusal text "This task cannot resume in its current state. Review its plan or retry limit." | §1.6 |
| 12 | Task needs direction | Technical Arabic text posted in the hidden work thread; item opens another thread | §1.7 |
| 13 | Task asked an ordinary question | Question in the hidden work thread; no item | §1.7 |
| 14 | Task completed | Final message if any; the "Task completed" item is off by default | §1.6 |
| 15 | Subagent failed | Raw code as a chat bubble | §5.4 |
| 16 | Subagent returned after its parent failed or was cancelled | Outcome message written, nobody acts on it | `packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:245-257` |
| 17 | Routine/watch quarantined after 5 errors | «أُوقف عنصر في الخلفية بعد أخطاء متكررة؛ يستمر كل ما عداه في العمل» — no name, no reason, opens Lonora's chat | §6.2 |
| 18 | Task wait or outcome delivery blocked after 5 errors | Same generic item; the Task stays waiting / the parent never hears | §6.2 |
| 19 | Legacy ticket Run finished or failed | Nothing in chat; ticket row only | §1.9 |
| 20 | Agent alert beyond 6 per hour | Tool fails with `owner_notify_rate_limited`; the owner sees nothing unless the agent says it in a reply | `packages/db/src/lonora_db/attention.py:396-397` |
| 21 | Agent alert during quiet hours | Held until they end (`held_for_quiet_hours`) — by the owner's choice | `packages/db/src/lonora_db/attention.py:467-469` |
| 22 | App closed | Everything above waits for the next app open; off-app carries only urgent items as one generic sentence | §4.4 |
| 23 | Gateway process down | Nothing raises an item | §6.3 |
| 24 | Run crashed its worker 5 times | «توقف عمل بعد انقطاعات متكررة» (web label) / off-app «توقف عمل بعد انقطاعات متكررة. افتح المحادثة لمراجعته.» — nothing in the conversation explains it | `packages/gateway/src/lonora_gateway/watchdog.py:230-242`, `packages/bus/src/lonora_bus/attention_messages.json:13` |

Refusals in this area that exist for the money-safety rules and must stay ("needed for
safety"): no automatic retry of an unresolved financial or unknown mutating call
(`packages/db/src/lonora_db/task_recovery.py:144-153`,
`packages/db/src/lonora_db/task_recovery.py:254-255`); a Run with an unresolved financial
operation is held, not failed (`packages/db/src/lonora_db/runs.py:554-555`); no retry of a
reply that touched the executor (`packages/db/src/lonora_db/run_retry.py:91-103`);
helpers and observe-only wakes cannot trade (`packages/tools/src/lonora_tools/base.py:92-97`);
`wait_for_input` cannot be used as financial consent
(`packages/tools/src/lonora_tools/runtime_control.py:64-73`); the owner's pause beats the
agent's resume (`packages/db/src/lonora_db/supervision.py:440-441`); cancelling a Task
cancels its pending approvals (`packages/db/src/lonora_db/tasks.py:537-552`).

---

## 8. Docs versus code

| Doc statement | Code | Verdict |
|---|---|---|
| `docs/lonora-specs/S19_CONTINUITY_AUDIT.md:16`: "`lonora_gateway/scheduler.py` dispatches `retry_due_tasks`" | The gateway runs each scheduler function as its own step (`packages/gateway/src/lonora_gateway/service.py:264-268`). `scheduler_tick` (`packages/gateway/src/lonora_gateway/scheduler.py:11-25`) does loop over `dispatch_routines`, `retry_due_tasks`, `dispatch_activation_reviews` and `resume_ready_waits`, so the doc line is true of that file, but it has no caller in `packages` or `apps` (two searches: for `scheduler_tick`, and for imports of the `scheduler` module, found only the definition). | The doc names dead code; the running path is `service.py:264-268` (code wins). |
| `docs/lonora-specs/S19_ACCEPTANCE.md:37`: "Safe reads have at most two automatic retries." | Retry while `failures < 3`, delays `2**attempt` s (`packages/agent-runtime/src/lonora_agent/environment.py:205-209`, `packages/agent-runtime/src/lonora_agent/environment.py:219-225`). | Agree. |
| `docs/proactive-wakes.md:15`: helper gets "read-only tools plus `workspace_execute` and `artifact_create`" | `packages/tools/src/lonora_tools/base.py:50`, `packages/tools/src/lonora_tools/base.py:97` | Agree. |
| `docs/proactive-wakes.md:91-101`: watch dedupe with and without a key | `packages/tools/src/lonora_tools/market_watch.py:103-128` | Agree. |
| `docs/incoming-attention.md:73`: "At most 6 alerts per Agent per rolling hour" | `packages/db/src/lonora_db/attention.py:335` | Agree. |
| `docs/lonora-specs/04_LONG_RUNNING_TASK_RUNTIME_AND_CONTEXTUAL_STEERING.md:905-919`: after a worker dies the Task "must not disappear" and resumes from its checkpoint | Lease expiry and re-claim (`packages/db/src/lonora_db/runs.py:194-201`); capped at 5 recoveries, then failed (`packages/db/src/lonora_db/runs.py:21`) | Agree, with the cap the spec does not mention. |
| `packages/tools/src/lonora_tools/routine.py:109`: routine description lists cron or interval | The schema also accepts one-shot `run_at` (`packages/contracts/src/lonora_contracts/routines.py:15-25`) | The tool description is incomplete (code wins). |

Unused code noticed (not changed): `scheduler_tick`
(`packages/gateway/src/lonora_gateway/scheduler.py:11`), `routine_tick`
(`packages/agent-runtime/src/lonora_agent/automation/routines.py:5`), `wake_agent`
(`packages/agent-runtime/src/lonora_agent/automation/wakes.py:8`), `expired_runs`
(`packages/gateway/src/lonora_gateway/recovery.py:7`), `ScheduledWake`
(`packages/automation/src/lonora_automation/types.py:6`). A search of `packages` and
`apps` found no caller for any of them. UNSURE: tests may use them.

---

## Verification log

Checker pass, code as of `9f5b1da` (checked-out HEAD `0a03960` differs only under `docs/`).

- Citations opened: 413 occurrences, 381 distinct `path:line[-line]` references in the
  original file, all extracted by script and printed from the repository. For ranges longer
  than 7 lines the bulk print shows only the first 7 lines; the ranges that a claim depends
  on (about 30, for example `task_recovery.py:126-155`, `item_failures.py:124-232`,
  `watchers.py:436-545`, `outcome_return.py:164-185`, `runtime_notices.py:142-203`,
  `model_recovery.py:160-197`) were read in full. Every file exists; no cited line is past
  the end of its file. All 28 Arabic `«...»` strings in the file were searched in the
  repository and all exist (one was in a different place than implied, see below).
- Citations corrected: 2 (`service.py:98` is `self.identity`, the voice task dict is
  `service.py:97`; the page-selection range in `usePersistentThread.ts` was widened to
  58-66 because the saved thread comes before the oldest). Quotes corrected: 2 (§7 item 24
  gave an English phrase in quotation marks that is not in the source, now the real Arabic
  off-app text, `attention_messages.json:13`; the F7 summary quote was the off-app sentence
  cut short and mixed with the web label, now both given with their citations).
- Claims refuted or downgraded (15):
  1. §1.7 "three of them ask him to choose between revise / resume / pause / cancel":
     refuted, all five causes carry the closing line (`runtime_notices.py:190-195`,
     appended unconditionally).
  2. §1.7 and F4 "the notification opens the origin conversation": downgraded; the item is
     attached to the origin thread, but the web link goes to `/app/<agent_id>` with no thread
     (`AttentionInbox.tsx:123-130`), so which thread opens is UNSURE.
  3. F1 "the owner believes gold is being watched; it is not": downgraded to a code-path
     finding; the trace shows no gold watch was ever created (`production-trace.md:71`).
  4. F1 "safe read-only next step... resolve the symbol before saving": removed, it was a
     fix design and the symbol-resolution fix belongs to another session; the existing
     helper and its users are cited instead.
  5. §3.6 "fixed-market agent, other symbol: health record only": refuted as stated; a watch
     on another symbol is refused at creation (`market_binding.py:120-122`); the
     observation-time check only matters if the binding changed later.
  6. §1.6 "dead end unless he asks the agent in chat": downgraded to UNSURE; `task_control`
     was not among the 23 tools the model was offered in the production conversation.
  7. §4 "approval card" attributed to `docs/proactive-wakes.md:32-36`: the lines do not
     mention an approval card; wording narrowed to what they say.
  8. §4.3 "This matches `docs/incoming-attention.md:29-32`": downgraded; those lines say
     nothing about quiet hours.
  9. §8 scheduler row "the doc describes an older layout": refined; `scheduler_tick` does
     dispatch `retry_due_tasks` (`scheduler.py:11-25`) but nothing calls it.
  10. §2.4 "web opens the oldest thread unless one is requested": incomplete; it opens the
      requested thread, else the one saved in the browser, else the oldest.
  11. F3 (raw code in chat): kept, but marked as not exercised in production, because
      `subagent_spawn` was not offered to the model there.
  12. F9 "with a generic sentence": narrowed to one fixed catalog sentence per item code;
      `task_review` has its own sentence (`attention_messages.json:7`).
  13. §1.6 item 4 listed the Task page buttons without "View conversation"
      (`TasksPages.tsx:204-211`): completed.
  14. §3.2 UNSURE about a per-agent watch limit: kept, but the one hit `WATCH_LIMIT = 8`
      is explained (it caps the watches listed in operational state, not creation).
  15. Header "HEAD `9f5b1da`": the checked-out HEAD is `0a03960`; code identical, noted.
- Checked and confirmed without change (absence claims, two independent searches each):
  no clock check of `due_at` (greps for `due_at` in `packages` and `apps`); no client sends
  `revise` (grep for the string, then grep of every `/tasks/control` caller); `work_thread_id`
  has no client use beyond the type; `scheduler_tick`, `routine_tick`, `wake_agent`,
  `expired_runs` and `ScheduledWake` have no callers; the ledger row of a quarantined
  `task_wait` or `outcome` item is never deleted (only `item_failures.py:137` and `:203`
  delete rows); the schedules page has no result view.
- Added by the checker (7): watch lifecycle tools and the owner's watch controls with the
  trace caveat (§3.7); a watch with `enabled: false` still checked in production, UNSURE
  why (§3.6); what `WATCH_LIMIT` is (§3.2); the attention link carries no thread (§1.7);
  every other `/tasks/control` caller and the agent live-status panel (§1.6); the
  incomplete-steps line of the owner notice (§1.7); `task_control` not natively offered
  (§1.6).
- Not verified: behaviour at runtime (nothing was executed); `broker_ready` refresh of
  `observed_at` (still UNSURE as in the body); lines of `docs/proactive-wakes.md:48-67` beyond
  the first 7.
