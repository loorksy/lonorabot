# Watch and Task lifecycle, and tool visibility: what the trace shows and what the code does

Repository `/home/user/lonorabot`, main HEAD 9f5b1da. Paths are relative to the repository root.
Reproduction: `scripts/wl_lifecycle.py` (real runtime, real API routes, simulation broker, database 8,
every model turn SCRIPTED) with raw output in `runs/wl_lifecycle.out`; `scripts/wl_exposure_budget.py`
(pure registry) with output in `runs/wl_exposure_budget.out`. Both under
`/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/`.
Section labels such as "A2" or "B3" below are the headings in `runs/wl_lifecycle.out`.

## Summary of findings

| # | Question | Finding |
|---|---|---|
| a | Are watches with `enabled=false` still evaluated? | **No, not on main and not on any build of that day.** The claim rests on the `updated_at` column, which the evaluator never writes. Trace Part 4 shows watches 2 and 3 were created with `enabled: true`; `updated_at` + `version 2` + `enabled=false` means something outside the evaluator switched watches 1 to 3 off at 12:29:15 to 12:29:18 UTC: a cancel or pause (owner route or agent tool) or a generic `PUT /api/watches/{id}`. Which one is not settled (a.4). The real defects nearby are different: see a.5. |
| b | Task cancelled, its watch stays | **Confirmed defect.** Cancelling a Task touches the Task, its Run, its trade approvals and (to release it) a supervision hold; nothing touches the watch. The orphan keeps being polled (one broker quote read per 30 s at most) until its condition is met; then it disables itself with `task_terminal` and wakes nothing. |
| c | Why «waiting» / «owner_attention» | The account-management Task is `continuous`. Its Run must end with a saved `task_wait`; a prose answer is refused twice and the third hands the Task to the owner. The question is written into the Task's own work thread, not the chat. |
| d | Tool visibility | Native tools are a fixed set chosen by a per-tool `eager` label. A character budget for that set is asserted by a test (not cut at run time) and is full (8 characters free). `watch_list`, `watch_cancel`, `trade_close_positions` and every goal tool carry no label. They work through `tool_call` with no prior discovery, and the watch id is in the model's context on every turn. |
| e | `agent_inspect` and the «EURUSDm» answer | `work` returns every watch row (disabled ones too) and raw Task states. The Task has no symbol; the only symbol in the agent's records was the Task's own watch on EURUSDm. |

---

## a. `enabled`: where it lives, who evaluates, and whether a disabled watch is evaluated

### a.1 Where `enabled` is stored

- It is a field of the watch contract, default true: `packages/contracts/src/lonora_contracts/market_watch.py:29`. Because the contract is the input type of `watch_create` (`packages/tools/src/lonora_tools/market_watch.py:237-244`), **the model can pass `enabled: false` when it creates a watch**.
- It is stored inside the JSON `payload` column. `ln_market_watches` has no `enabled` column: the row type is the generic resource row (`packages/db/src/lonora_db/schema.py:775-776`, columns at `schema.py:661-673`).
- `updated_at` has a default only and no on-update hook (`packages/db/src/lonora_db/schema.py:673`). This matters in a.4.

### a.2 Who evaluates watches, and how often

- The gateway runs a supervised step named `watches` every 2 seconds (`packages/gateway/src/lonora_gateway/service.py:56`; the fields are name, interval, timeout: `packages/gateway/src/lonora_gateway/liveness.py:22-25`). The step calls `dispatch_market_wakes` (`service.py:222-223`), which calls `check_watches` (`packages/gateway/src/lonora_gateway/wake_dispatch.py:6-7`).
- `check_watches` (`packages/market/src/lonora_market/watchers.py:379-445`) selects up to 200 watches that are due (`state.next_check` empty or in the past, `watchers.py:407-412`, `:430`) and checks each one. After each check it sets `next_check = now + interval_seconds` (`watchers.py:589`); `interval_seconds` defaults to 30 (`packages/contracts/src/lonora_contracts/market_watch.py:31`). So each enabled watch is evaluated about every 30 seconds. The same selection also leaves out the watches of a paused agent (`watchers.py:399`), expired ones (`watchers.py:403`) and quarantined ones (`watchers.py:404`).
- A price watch reads the quote through the market runtime, which serves a stored quote for up to 15 seconds (`packages/market/src/lonora_market/runtime.py:102-105`).
- The same function also runs on streamed quotes and candles (`packages/market/src/lonora_market/runtime.py:202-204`, `:299-301`). The streams themselves are opened only for enabled watches (`runtime.py:423`, `:433`).

### a.3 The evaluator respects `enabled` in three places

1. The SQL selection excludes disabled rows: `MarketWatchRow.payload["enabled"].as_boolean().is_not(False)` (`watchers.py:402`).
2. `check_watch` returns at once for a disabled watch: `if not config.enabled or not original.agent_id or not original.thread_id: return triggered` (`watchers.py:458-459`).
3. Every later write re-reads the row under lock and stops if it was disabled meanwhile (`watchers.py:521`, `:545`), and the trigger test itself requires `enabled` (`watchers.py:633-635`, `packages/market/src/lonora_market/watch_control.py:6-11`).

These lines are identical in the builds that served that day (`git show efb4911:…/watchers.py`, `2477c22`, `cd2cc91`, `f9fffe3`: the same line numbers 402, 458, 521, 545, 633-634).

**Reproduced (A1 to A3).** A SCRIPTED `watch_create` with `enabled: false` (EURUSDm below 1.11305, prompt «placeholder») stores `payload.enabled=False`, `state={}`, version 1. One evaluation tick leaves it untouched while the enabled control watch gets health, `evaluation_status`, `next_check`, `lifecycle`. When the price is moved to 1.10900, so that both conditions are true, the enabled watch fires (a `watch` Run is queued) and the disabled one is still untouched: `state={}`, version 1, no Run.

So a disabled watch cannot "fire". It is never observed, so it never reaches the code that creates a wake.

### a.4 What the trace actually shows

The trace note says watches 1 to 3 have `enabled=false` yet "are being polled every 30s (updated 12:29)". The inference from `updated` is wrong:

- The evaluator writes `row.state` only (`watchers.py:533-538`, `:722`). It never sets `updated_at`, and the column does not update itself (`schema.py:673`). In the reproduction the evaluated control watch keeps `updated` equal to `created` after every tick (A2, A3: `created=15:01:57.488946 updated=15:01:57.488950`).
- **Three** code paths set a watch's `updated_at` and add 1 to `version` (corrected by the checker; the first draft said "exactly one"). A search for `updated_at` over `packages/market/src`, `packages/db/src/lonora_db/market_watches.py`, `packages/db/src/lonora_db/transactions.py` and `packages/tools/src/lonora_tools/market_watch.py` finds only these:
  1. `_changed` (`packages/db/src/lonora_db/market_watches.py:128-139`), called by `control_watch` for cancel, pause and resume (`market_watches.py:172-179`, `:189-192`), by `update_watch` (`:229-230`) and by `restore_expiry` (`:260`). Cancel and pause also set `payload.enabled=false` and `state.code` (`market_watches.py:176-177`), and `_changed` adds `state.steered_by` and `state.steered_at` (`market_watches.py:131`).
  2. The generic resource update, `PUT /api/watches/{id}` (`apps/api/src/lonora_api/routes/watches.py:13`, `apps/api/src/lonora_api/routes/__init__.py:57-67`), which replaces the whole payload, adds 1 to `version`, sets `updated_at` and **does not touch `state`** (`packages/db/src/lonora_db/transactions.py:197-199`). A payload with `enabled: false` sent this way leaves no `code` and no `steered_by`. Reproduced by the checker (`runs/wl_check_extra.out`, part 2): two generic updates moved the row from version 2 to 4, changed `updated_at` and `payload.enabled`, and changed no state key. No screen in `apps/web/src` or `apps/mobile` sends this PUT for a watch (the only user of the generic watch service, `apps/web/src/components/market/MarketWatch.tsx:55-98`, lists and creates), but the route is open to any client holding the owner's session.
  3. A keyed `watch_create` that replaces a live watch with the same `dedupe_key` and a different condition: the old row gets `enabled=false`, `state.code = "watch_replaced"`, version + 1 and `updated_at` (`packages/tools/src/lonora_tools/market_watch.py:108-119`). It always creates a new row beside the old one (`market_watch.py:129-136`). No such new row exists in trace Q4, and watches 2 and 3 have no key, so this path is excluded for the production rows.
- Paths that disable a watch **without** writing `updated_at` (so they cannot explain "updated 12:29"): the quarantine (`packages/market/src/lonora_market/watchers.py:59-66`), an obsolete goal watch (`watchers.py:495-499`) and the `task_terminal` self-disable (`watchers.py:661-664`).
- `control_watch` is reached from the owner's route `POST /api/watches/{watch_id}/control` (`apps/api/src/lonora_api/routes/watches.py:28-41`; called by the web client at `apps/web/src/components/ai/AgentLiveStatus.tsx:64`, `apps/web/src/shell/domain/SchedulesPages.tsx:258`, `:294`, `apps/web/src/shell/agent/AgentPage.tsx:191`, `:201`, `apps/web/src/conversation/sheets/WatchesSheet.tsx:25`, and by the mobile client at `apps/mobile/components/agent-live-status.tsx:108`), from the agent tools `watch_cancel` / `watch_pause` (`packages/tools/src/lonora_tools/market_watch.py:172-196`) and from a supervising agent's pause of a watch (`packages/db/src/lonora_db/supervision.py:612-614`; only one agent exists in production, so this one does not apply).

**Reproduced (A4).** A watch that was being evaluated is cancelled through the owner's route. The row then reads: version 2, `payload.enabled=False`, `updated_at` = the moment of the cancel, and a `state` that still says `"evaluation_status": "active"` with health `market_quote_healthy` and `"lifecycle": "pending"`, because cancel only appends `code`, `steered_by`, `steered_at` at the end of the state (`market_watches.py:131`, `:177`). In the reproduction `"code"` starts at character 813 of the state JSON and `"steered_by"` at 840; the trace query cut state at 700 characters, so those keys were not visible. The next tick does not touch the row.

That is the picture of trace watches 1 to 3: version 2, `enabled=false`, `updated` 12:29:15 / 12:29:16 / 12:29:18, `evaluation_status active`; watch 1 also shows `next_check 12:29:45` (its last poll was at about 12:29:15, three seconds before its `updated`). Watch 4, created with `enabled=false` at 10:54:14, is `v1`, `state {}`, `updated` = `created`: never evaluated and never changed, the same as the reproduction's disabled-from-birth watch. The same picture (version 2, `enabled=false`, a fresh `updated_at`, a state that still says `active`) is also what the generic `PUT` leaves; the two differ only in the state keys after character 700.

Reading: watches 1 to 3 were enabled and polled every 30 seconds from their creation until about 12:29:15 UTC, and were then switched off one after another within three seconds, newest first (3, then 2, then 1), which is the order in which the watch lists are returned (`packages/db/src/lonora_db/transactions.py:78`, `packages/db/src/lonora_db/agent_state.py:349`). The trace export was taken just after.

**Confirmed by trace Part 4** (this was an inference in the first draft): the three `watch_create` calls of Run ddae66ad carried no `enabled` argument; the results for 69c9e0bb and 6050e419 said `"enabled": true`, version 1; the third call had arguments identical to the second and returned the same id 6050e419, already with a health state, `evaluation_status: "active"` and `next_check 09:57:20` (so the row had been evaluated at 09:56:50, one second after its creation). The code path for that third call is the identical-request lookup (`packages/tools/src/lonora_tools/market_watch.py:104-107`, `:72-86`). Reproduced (A1b): repeating an **enabled** request returns the existing row with `"deduplicated": true` and adds nothing; repeating an `enabled: false` request creates **another row every time**, because both dedupe lookups only match enabled rows (`market_watch.py:47`, `:79`).

So "enabled=false yet still evaluated" has no support left in the trace: the rows were enabled while they were evaluated, and the note's "polled every 30s" was read off `updated`, which no evaluation writes.

TRACE BODIES MUST CONFIRM (Part 4 does not carry these):
- the full `state` of watches 1 to 3 (keys after character 700). `code: watch_cancelled` or `watch_paused` with `steered_by: owner` or `agent` means `control_watch`; no `code` and no `steered_by` means the generic `PUT`;
- `ln_events` rows of kind `market_watches.updated` at 12:29:15 to 12:29:18 (both paths emit one: `market_watches.py:132-139`, `transactions.py:200-208`), and `ln_supervision_holds` rows for those watch ids with `source='owner'` (only an owner cancel or pause through `control_watch` records one: `market_watches.py:163-167`, `packages/db/src/lonora_db/supervision.py:382-395`; seen in the reproduction's E1 and E2 as `pauses_by_supervisors … "by": "owner"`);
- the API access log for 12:29:15 to 12:29:18 (`POST /api/watches/<id>/control` or `PUT /api/watches/<id>`); the container logs exist from 10:37 UTC.

UNSURE: who switched the three watches off at 12:29, and by which of the two routes. No Run exists in thread 3c25305d after 11:20:45, and three changes in three seconds fit either three taps on the «cancel» buttons of the live-status list or a script; the export alone cannot tell.

### a.5 The defects that are real here

- **The model can create dead watches.** `enabled` is exposed in the `watch_create` schema, and a watch created disabled is a row that never watches. Run e79b4bf2 did exactly this («watch جديد معطّل», [77]); trace Part 4 has the call: `{"…","prompt":"cancel-test","enabled":false,"dedupe_key":"cancel-test-1"}`. Each repeat adds another row (A1b); a `dedupe_key` does not prevent it, because the keyed lookup matches enabled rows only (`packages/tools/src/lonora_tools/market_watch.py:47`).
- **A watch can be switched off with no trace of who did it.** The generic `PUT /api/watches/{id}` changes the payload without a state code, a `steered_by` or a supervision hold (a.4, path 2).
- **A disabled watch still looks alive in its own state.** After a cancel the state keeps `evaluation_status: "active"`, healthy health and `lifecycle: "pending"` (A4), and `watch_summary` reports `"lifecycle": "pending"` for it (`packages/db/src/lonora_db/agent_state.py:52`). Only the separate `enabled` flag tells the truth.
- **`agent_inspect` lists disabled watches beside live ones** (`packages/tools/src/lonora_tools/supervision.py:169-177`, `:229-232`), which is how a model counts "3 متابعات" whatever their state (section e).
- **`evaluation_mode` is ignored for price watches.** It is read only for dynamic watches (`watchers.py:743`; the price branch reads the live quote, `watchers.py:244-258`). Trace watch 1 says `candle_close` on 15m with the prompt "closed below 1.11305 on 15m", but it would trigger on the first polled bid below the level.

---

## b. The Task «إدارة حساب التداول» and its orphan watch

### b.1 Where the Task and the watch come from

- Signing a full mandate creates the Task. In `finish_activation`, when the envelope's `management_mode` is `full`, `create_task` is called with the title `attention_text("account_management_task", locale)` and `completion_mode="continuous"` (`packages/auth/src/lonora_auth/account_authority.py:131-165`). The title string is «إدارة حساب التداول» (`packages/bus/src/lonora_bus/attention_messages.json:11`). The Task id is derived from the grant id (`account_authority.py:164`).
- `create_task` creates a board, a separate **work thread**, the ticket and one Run with trigger `tickets` in that work thread (`packages/db/src/lonora_db/tasks.py:169-227`).
- **The signing does not create a watch.** The Task's description tells the model to «persist meaningful market-triggered follow-up» (`account_authority.py:154-155`), and the Task's Run created the watch itself with `watch_create`. A watch created inside a Task Run is stamped with `state.task_id` and `state.task_run_id` and lives in the Task's work thread (`packages/tools/src/lonora_tools/market_watch.py:96-102`, `:137-142`). This matches trace watch 1: thread ea0e47c6 ("OTHER thread"), `task_id 780fb5ea…`, `task_run_id 779e4761…`, created 09:44:53, 89 seconds after the Task (09:43:24).
- Reproduced (B0, C1): after the card is signed a ticket «إدارة حساب التداول» exists with `completion_mode: continuous`, status `queued`, its own work thread and a queued `tickets` Run; no watch is added by the signing; the SCRIPTED Task Run's `watch_create` returns a row with `state.task_id` / `state.task_run_id` in the work thread.

### b.2 What the interface's cancel does

- Route: `POST /api/tasks/control` (`apps/api/src/lonora_api/routes/tasks.py:54-59`), called by the web client's `controlTask` (`apps/web/src/shell/domain/api.ts:55-60`). It calls `control_task` (`packages/db/src/lonora_db/tasks.py:397-554`).
- For a Task whose Run is waiting, `cancel` does this (`tasks.py:530-553`): releases any live supervision hold on the Task (`tasks.py:413-423` passes `paused=request.action == "pause"`, which is false for a cancel, and `packages/db/src/lonora_db/supervision.py:378-381` then only releases; corrected by the checker, the first draft said it "records the owner's hold"), sets the Run to `cancelled` (`tasks.py:533`), sets the Task's `status` and `phase` to `cancelled` (`tasks.py:534-535`), cancels the Run's pending trade approvals (`tasks.py:537-552`), saves the Task (`tasks.py:553`).
- **It does not clear `waiting_reason`**, so the cancelled Task keeps `waiting_reason: owner_attention`. This is the trace's ticket: «status CANCELLED, phase cancelled, waiting_reason owner_attention». It also shows that the cancel came through `control_task` and not through a revoke of the mandate: that path uses `finish_task`, which does clear it (`tasks.py:137-138`; `packages/db/src/lonora_db/account_authority.py:216-227`). `control_task` has three callers besides the owner's route: the agent tool `task_control` (`packages/tools/src/lonora_tools/tasks.py:65`) and two supervision paths (`packages/db/src/lonora_db/supervision.py:621`, `:787`). The trace has no `task_control` tool event and no Run at 10:51:04, and only one agent exists, so the owner's route is the one that fits.
- **It does not touch any watch.** `packages/db/src/lonora_db/tasks.py`, `packages/db/src/lonora_db/cancellation.py` and `apps/api/src/lonora_api/routes/tasks.py` contain no reference to the watch table (`grep -c "MarketWatch\|market_watch"` gives 0 for each, and so does a case-insensitive `grep -ci watch`). A second search, for readers of the link itself, finds `task_run_id` read in one place only, the evaluator (`packages/market/src/lonora_market/watchers.py:656`), and `state.task_id` read only by the identical-request lookup (`packages/tools/src/lonora_tools/market_watch.py:85`). The link between the two exists only on the watch side (`state.task_id`, `state.task_run_id`); nothing reads it when a Task ends. The same is true of `finish_task` (`tasks.py:115-139`), so a Task that ends by revoke or completion leaves its watches too.

Reproduced (B1, B2): the route returns `status: cancelled, phase: cancelled, waiting_reason: owner_attention`, the Run is `cancelled`, and the Task's watch is unchanged: version 1, `enabled=True`, still pointing at the cancelled Task and Run.

### b.3 What the orphan watch does

- While its condition is not met it is evaluated like any enabled watch (B3, first tick: "EVALUATED"), about every 30 seconds, each time reading a quote (served from a stored copy for up to 15 seconds, `packages/market/src/lonora_market/runtime.py:102-105`) and rewriting its state.
- When the condition is met, the evaluator looks at the Run named in `task_run_id`. If that Run is missing or `completed`, `failed` or `cancelled`, it disables the watch, sets `state.code = "task_terminal"` and returns without creating anything (`packages/market/src/lonora_market/watchers.py:654-665`). For a Task watch no wake Run is ever created in any case (`watchers.py:675-677`); a live Task is resumed by the separate `task_waits` step, which only takes Runs in `waiting_takeover` whose Task is `waiting` (`packages/db/src/lonora_db/task_wait.py:213-215`).
- So **the orphan does not wake the cancelled Task and does not start a Run**. Reproduced (B3, second tick, price 1.11200): `triggered=0`, no new Run, the watch becomes `enabled=False`, `code=task_terminal`, version 2; the Task stays `cancelled`.
- Until that happens the orphan is shown as live work everywhere: it counts in `active_watches` and is listed in the model's per-turn state (section e.3), and it is in the owner's watch list. If the price never reaches the level and the watch has no expiry (trace watch 1 has none), it is polled indefinitely.
- The `task_terminal` self-disable adds 1 to `version` but leaves `updated_at` alone (`watchers.py:661-664`), another reason `updated_at` cannot be read as "last evaluated".

---

## c. Why the Task shows «waiting» / «owner_attention»

What the state is: `status: waiting`, `phase: needs_attention`, `waiting_reason: owner_attention`, with the Task's Run in `waiting_input` holding a pending question of kind `owner_attention`. It is written by `request_task_attention` (`packages/db/src/lonora_db/tasks.py:758-795`), which the executor calls when a Task Run's outcome carries `owner_attention` (`packages/agent-runtime/src/lonora_agent/executor.py:240-246`). The Task reads as `status: waiting, phase: waiting, waiting_reason: owner_attention` through `snapshot` (`tasks.py:282-289`, `:330-338`, `:363-371`), which is what `agent_inspect` and the per-turn state show.

Why a freshly created account-management Task gets there. The Task is `continuous`, so a text answer can never complete it:

1. Each time the model ends a turn with prose, the stop gate refuses it and appends a notice, at most `MAXIMUM_STOP_NUDGES = 2` times (`packages/agent-runtime/src/lonora_agent/stop_gates.py:41`, `:99-100`, `:126-129`). The notice text is `CONTINUOUS_NUDGE` (`stop_gates.py:45-54`): «This responsibility is continuous. A text answer does not complete it or save monitoring. Continue useful authorized work, or use task_wait with a real owned watch, verified broker-recovery source, or a deliberate review timer. …».
2. On the third prose answer the gate returns `exhausted="task_wait_required"` (`stop_gates.py:126-127`) and the loop hands the work to the owner (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:175-178`, `:109-152`).
3. The way to yield cleanly is a successful `task_wait` (native in a Task Run, `packages/tools/src/lonora_tools/tasks.py:89-96`). It takes one of three sources: a watch the Task owns, which must be the same agent's, in the Task's work thread, not a goal watch and enabled (`packages/db/src/lonora_db/task_wait.py:32-42`), a broker recovery (`task_wait.py:43`) or a timer (`task_wait.py:70`). It sets `waiting_reason` to `external_` plus the kind, for example `external_watch` (`task_wait.py:74-78`). (The first draft named the watch only.) The notice also allows `wait_for_input` «only for genuinely missing owner information or authority».

Creating a watch is therefore not enough: the model must also call `task_wait` with that watch's id (or with a timer).

Reproduced (C1, C2): the SCRIPTED Task Run calls `watch_create`, then answers in prose three times. Two `completion_check` notices appear, then the Run goes to `waiting_input` with `pending_input_request … "kind": "owner_attention", "reason": "task_wait_required"` and the ticket reads `status=waiting phase=needs_attention waiting_reason=owner_attention`. In the trace the Task's `last_checkpoint` (09:44:53) equals the creation second of watch 1 (09:44:53): the last tool work the Run did was creating the watch, which fits this path.

Two other paths lead to the same state and cannot be excluded from the digest: a round or guardrail limit in a Task Run (`packages/agent-runtime/src/lonora_agent/tool_loop.py:302-311`) and a model failure that escalates (`tool_loop.py:553-559`).

TRACE BODIES MUST CONFIRM: for Run 779e4761 (thread ea0e47c6): the tool calls it made, whether `task_wait` was called and with what result, and `execution_state.pending_input_request.reason` (`task_wait_required` would settle it).

Where the owner was told. The question is committed as an assistant message in **the Run's own thread**, which for a Task is the work thread (`executor.py:176-189`). Reproduced (C2): the text is in the TASK WORK thread and the chat thread has nothing. The text (Arabic notice at `packages/agent-runtime/src/lonora_agent/runtime_notices.py:150` and `:191`) is:

> «هذه المهمة المستمرة غير مراقَبة: لم يُحفظ أي انتظار مراقبة أو مؤقت مراجعة، لذلك لن تحدث أي متابعة تلقائية. أحتاج توجيهك قبل المتابعة: ردّ هنا، أو عدّل المهمة أو استأنفها أو أوقفها مؤقتًا أو ألغها.»

followed by «آخر تقرير:» and the model's last prose. Consistent with the trace: none of the 78 messages of thread 3c25305d carries it. An event `task.attention_required` is also emitted for the origin thread (`tasks.py:787-795`) and classified `action_required` (`packages/core/src/lonora_core/attention.py:109-111`).
UNSURE: how that event reached the owner's screen on 2026-11-11 (notification, status line); not traced here.

Net effect for the owner: from about 09:45 UTC the "account management" he had just signed was not running and not monitored. It sat waiting for him in a thread he was not reading, while the chat said «أراقب» and «أتابعه».

---

## d. Tool visibility

### d.1 The rule

Native tools are a **fixed set chosen by a label on each tool, inside a character budget**. There is no routing score and no per-message selection.

- Each tool may declare `eager` profiles (`packages/tools/src/lonora_tools/base.py:88-89`). A Run's profiles come from the agent and the kind of Run: `core`; `market` for an agent bound to an account **or the personal agent**; `coordination` for the personal agent outside a trading Task Run; `task` for Task Runs (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:31-49`). `scope_mode` and the missing account binding play no part: `trading = bool(agent.trading_account_id) or agent.role == "personal"` (`tool_exposure.py:43`).
- Native = every tool whose `eager` set meets the Run's profiles, minus tools reported unavailable, plus the two bridge tools (`packages/tools/src/lonora_tools/registry.py:260-268`, `:284-289`).
- On top: at most 6 "promoted" tools within 4,100 schema characters, taken from the tools this agent has already used successfully through the bridge (`registry.py:84-85`, `:290-304`; recorded by `remember_use`, `tool_exposure.py:151-181`).
- The set is chosen once per Run and frozen (`tool_exposure.py:89-128`).
- Budget: `EAGER_SCHEMA_BUDGET = 25700` characters of serialized schemas (`registry.py:83`). It is asserted by a test only (`tests/test_tool_discovery.py:165`); the constant is used nowhere else in `packages/` (two searches: `grep -rn EAGER_SCHEMA_BUDGET packages tests` finds the definition and the test), and `exposure` does not measure the eager set at run time (`registry.py:284-289`). So a tool that got an `eager` label would be offered to the model; what would fail is the test.

### d.2 Why `watch_create` is native and the others are not

- `watch_create` has `eager=eager_for("market")` (`packages/tools/src/lonora_tools/market_watch.py:243`). `watch_list`, `watch_cancel`, `watch_pause`, `watch_resume`, `watch_update` are declared without it (`market_watch.py:245-282`).
- `trade_execute` has `eager=eager_for("market")` (`packages/tools/src/lonora_tools/trade.py:767`); `trade_close_positions` does not (`trade.py:770-784`).
- No goal tool has it (`packages/tools/src/lonora_tools/trading_goal.py:484-541`: no `eager=`), nor `task_control`, `task_inspect`, `task_start` (`packages/tools/src/lonora_tools/tasks.py:105-125`), nor `agent_control` (`packages/tools/src/lonora_tools/supervision.py:609-623`).
- The budget is full. `runs/wl_exposure_budget.out`: the personal chat set (`core`, `market`, `coordination`) is 23 tools and **25,692 of 25,700 characters, 8 free**; the personal Task set is 22 tools, 25,686 characters, 14 free. `watch_create` alone is 4,612. The missing ones are small (`watch_list` 245, `watch_cancel` 272, `trade_close_positions` 734, `goal_list` 337) but none fits in 8 characters. So adding a label alone would break the budget test, although nothing at run time would stop the tool from being offered.

### d.3 The native list, reproduced

Personal agent, `role personal`, `scope_mode fixed_market`, `trading_account_id null`, `trading_symbol null` (SETUP in the output, same as trace Q6).

| Case | Native tools |
|---|---|
| D1: no mandate, default trading level (`effective_level: supervised`) | 22: the trace's 23 without `web_search` |
| D1b: trading level `analysis` | 21: also without `trade_execute` |
| D2: full mandate signed | 22: `trade_execute` back |
| C1: the Task's own Run | 22: no `agent_inspect`, no `peer_send`; `task_wait` and `task_step_update` added |
| D5: chat Run after successful bridge calls | 24: `watch_cancel` and `watch_list` promoted |

- The one-tool gap to the trace's 23 is `web_search`: the test environment has no research provider (`unavailable … 'web_search': 'research_provider_not_configured'`), production had one. `wl_exposure_budget.out` lists the 23 eager names; they are the trace's baseline exactly.
- **The mandate does not change the list; the agent's trading level does.** `trade_execute` and `trade_close_positions` are reported unavailable with `agent_analysis_only` when the effective level is `analysis` (`packages/tools/src/lonora_tools/trade.py:57-67`, `:768`, `:783`). That is the trace's list "U1" (09:05 to 09:37:55). Signing the full mandate lifts the level: an active authority makes the effective level `autonomous` whatever the saved level is (`packages/db/src/lonora_db/agent_permissions.py:150-158`; D2 after D1b; `agent_inspect` then shows `"trading_level": "autonomous"`), which is why `trade_execute` returns from 09:44:01 (the mandate message is seq 6, 09:43:24).
- UNSURE: why the production agent was at `analysis` before the mandate. In the reproduction a new Personal Agent starts at `effective_level: supervised` (D1) and the level was set to `analysis` by the script. In the trace the four failed Runs up to 08:56:01 show list U0 (no `agent_analysis_only`) and the Run at 09:05:37 shows U1, so the saved level changed to `analysis` between 08:56 and 09:05 UTC; what changed it is not in the export.
- Signed mandate or not, `watch_list`, `watch_cancel`, `trade_close_positions` and the goal tools are never native on a first use.

### d.4 What the model is told about the rest

Every Run carries a system message with the full inventory of names (`packages/tools/src/lonora_tools/registry.py:406-473`, built at `packages/agent-runtime/src/lonora_agent/tool_loop.py:492`). It opens (`registry.py:425-431`):

> «Current capability inventory from the permitted live registry. Your native tool list is this Run's working set, not the full set of abilities. Call a native tool by its own name. Call any other capability below with tool_call, using its exact name and arguments; inspect it with tool_environment first when you do not know its input schema, and before claiming an ability is absent. …»

`watch_cancel`, `watch_list` and `trade_close_positions` are named in it (see `runs/conv-C-discovery.out`, "capability inventory"). So in every Run of that day the model had the name `watch_cancel` in front of it; the name appears in its own replies [75] and [77].

### d.5 What `tool_environment` returns (D3)

| Query | Result |
|---|---|
| «حذف المتابعات» | `{"ok": true, "tools": [], "total": 0, …}`: nothing |
| `cancel watch` | 4 tools, `watch_cancel` first, with `"invoke": "tool_call"`, `"available": true` and its input schema (`watch_id`, required) |
| `watches` | the watch family: `watch_list`, `watch_pause`, `watch_cancel`, `watch_resume`, … |
| exact `tool_name: watch_cancel` | the full entry: purpose «Stop one of your own watches; its record stays, and watch_resume undoes it.», `"invoke": "tool_call"`, `"available": true` |
| exact `tool_name: trade_close_positions` | the full entry, `"invoke": "tool_call"`, `"available": true`, schema `account_id` required, `symbol` optional |

**What production actually sent (trace Part 4, Run 3fa683e6; corrected by the checker, the first draft assumed an Arabic query):** `tool_environment {"query": "watch cancel task routines goals"}`, an English query of five words, and the result was `{"ok": true, "tools": [], "total": 0, …}`. Reproduced on main (`scripts/wl_check_extra.py`, `runs/wl_check_extra.out`, part 1): the same query over the full catalog of 126 tools returns nothing. The cause is in the search itself (`packages/tools/src/lonora_tools/tool_discovery.py:62-73`):

- the query word that appears in the fewest tools becomes a gate that every result must contain (`tool_discovery.py:62`, `:70`). Here that word is `goals` (2 tools; `cancel` 4, `routines` 4, `watch` 10, `task` 11);
- with four or more known words, a result must also contain at least half of them, here 3 of 5 (`tool_discovery.py:63-64`, `:71`);
- no tool contains `goals` and two more of the five words. `watch_cancel` does not contain `goals` at all, so it was cut by the gate.

The same words asked separately succeed: `watch cancel` returns `watch_cancel` first; dropping `routines` (`watch cancel task goals`) returns one tool, `trade_execute`. So the more of its request the model put into one query, the less it got back. This fits [75] «ما في أداة حذف ظاهرة تحت هذا الاستعلام المبسّط».

The Arabic row of the table is a second, separate way to get an empty list (no Arabic word is in the catalog; `runs/conv-C-discovery.out` has the token frequencies). It did not happen in this conversation.

### d.6 What `tool_call` needs to invoke `watch_cancel` (D4)

- **No prior `tool_environment` call is needed.** `tool_call {"name": "watch_cancel", "arguments": {"watch_id": "<id>"}}` is unwrapped into the real call before anything else sees it (`packages/tools/src/lonora_tools/registry.py:180-208`) and runs. In D4 the Run's first tool call is `tool_call → watch_list`, then two `tool_call → watch_cancel`; all return `ok: true`, and the rows become `enabled=False`, `code=watch_cancelled`, `steered_by=agent`.
- Even calling `watch_cancel` **directly by its own name**, although it is not in the native list, works in the runtime (D4, call `cancel-3`): execution looks the name up in the whole registry (`registry.py:475-480`). Whether a given model provider lets the model emit a call to a tool it was not offered is outside this code. UNSURE for the production provider.
- The only argument is the watch id. The personal agent can cancel only its own watches (`packages/db/src/lonora_db/market_watches.py:115-125`); all four production watches are its own, and in D4 it cancels the Task's watch too (that row was already off through `task_terminal` from B3; the call still returns `ok: true` and takes it from version 2 to 3 with `code=watch_cancelled`).
- **The id is available without any tool call.** On every turn the routing frame gives the model `<live_agent_state>` with a `watches` list including `"id"` (`packages/agent-runtime/src/lonora_agent/context/team.py:82-91`; `packages/db/src/lonora_db/agent_state.py:36-53`, `:648`) and `<protected_operational_state>` with `active_watches[].watch_id` (`packages/db/src/lonora_db/operational_state.py:199-218`). E1b prints both from a real request. These two lists cover **enabled** watches only (`agent_state.py:347`, `operational_state.py:213`), and `<live_agent_state>` carries at most 6 of them (`agent_state.py:33`, `:648`) and at most 3 Tasks, none of them completed or cancelled (`agent_state.py:244-264`). On 2026-11-11 watches 1 to 3 were enabled until 12:29, so from 09:56:49 on all three ids were in every request of Runs e343c96a, 1638329a, fb1d4b5a, 3fa683e6 and e79b4bf2.
- `agent_inspect` with `section: "work"` returns the `id` of every watch, enabled or not (`packages/tools/src/lonora_tools/supervision.py:229-232`). The default section `overview` gives only a count (`supervision.py:154`). `watch_list` returns full rows with ids.
- After one successful bridge use the tool is native in later Runs (D5), so the first cancellation would also have ended the visibility problem for the watch tools.

So on 2026-11-11 nothing in the runtime stood between the model and `watch_cancel`: the name was in the inventory, the ids were in context, `tool_call` was native. The model never called it (trace: "No watch_cancel or any delete call anywhere") and called the one watch tool it had natively, `watch_create`, instead. One thing did push it the wrong way: the single search it ran (d.5) came back empty, and the result text carried no hint that a shorter query or the inventory would have found the tool.

---

## e. How `agent_inspect` lists watches and Tasks, and the «EURUSDm» answer in [59]

### e.1 What it returns

Tool: `packages/tools/src/lonora_tools/supervision.py:599-608`; it requires `agent_id` and takes `section` (default `overview`) and `page` (`packages/contracts/src/lonora_contracts/supervision.py:27-30`). The model's own id is in the routing frame («Your current identity: {"id": …», `packages/agent-runtime/src/lonora_agent/context/team.py:80-81`).

`overview` (`supervision.py:137-162`), from E1:

- `profile`: `role`, `template`, `focus` (null here), `trading_level`, `paused`, `paused_by`;
- `activity`: `state`, `phase`, `reason_code`, `pending_approvals`, `active_watches` (a number), `tasks`, `runtime_waits`, `health`. With the Task waiting it reads `"state": "action_required", "phase": "action_required", "reason_code": "task_attention_required"`, and each Task carries `id`, `title`, **`"status": "waiting"`, `"phase": "waiting"`, `"waiting_reason": "owner_attention"`**, `version`, `can_pause`, `can_resume`, `can_cancel`, `attempt`, `failure_code`, `recovery`, `retry_at` (`packages/db/src/lonora_db/agent_state.py:268-290`);
- `trading_readiness`, `supervised_by`, `more`.

`work` (`supervision.py:165-275`), from E1 and E2:

- `watches`: the 10 newest rows of the agent **whatever their state**, each with `id`, `kind`, `account_id`, `symbol`, `condition`, `level`, `indicator`, `timeframe`, `metric`, `expires_at`, `lifecycle`, `enabled` (`supervision.py:169-177`, `:229-232`; `agent_state.py:36-53`). No prompt, no owning Task, no creation time, no reason why a watch is off. `timeframe` is null for price watches (`agent_state.py:47-49`);
- `routines`: `id`, `enabled`, `cron`, `interval_seconds`, `timezone`, `next_run_at`, `last_run_at`, `prompt`;
- `tasks`: the 10 most recently updated tickets, terminal ones too, each with `id`, `title`, `status`, `phase`, `waiting_reason`, `version` (`supervision.py:187-197`, `:219-227`);
- `goals`: `id`, `title`, `status`, `current_step` (non-terminal only);
- `pauses_by_supervisors`, `more`.

All state values are the internal English codes. Nothing is put into the owner's language, and no field says what a state means. That is the source of the raw `waiting`, `owner_attention`, `routines` and `goals` in [59] and [65]. The same raw Task states also reach the model on every turn through `<live_agent_state>` (E1b), tool call or not.

A cancelled Task still reads `"status": "cancelled", "phase": "cancelled", "waiting_reason": "owner_attention"` in `work` (E2), because of the uncleared field in b.2.

### e.2 Why [59] said the running Task was on EURUSDm

At 09:56:12 (Run f51d1db6, one `agent_inspect` call) the agent's records were:

- one Task, «إدارة حساب التداول», `waiting` / `owner_attention`. It has **no symbol**: the agent has no `trading_symbol` (`focus: null`), the mandate covers the whole account (`"symbol_scope": "account"`, `"symbols": []` in E1), and the Task summary has no market field;
- one watch, created by that Task's Run: EURUSDm, below 1.11305.

`work` returns `watches` and `tasks` as two separate lists with nothing joining them: the watch entry does not carry its `task_id` although the row has it (`state.task_id`, b.1). The owner asked «و المهمة الشغالة على اي زوج ؟»; the only pair anywhere in the result was the watch's. The reply joined the two: «المهمة الشغالة الآن على EURUSDm … المراقبة النشطة: EURUSDm تحت مستوى 1.11305 … الحالة: waiting». The level and the pair are the watch's, and «waiting» is the Task's raw `status`. In fact the Task was not running at all (section c), and the open position was on XAUUSDm.

The watch's pair and level were also in `<live_agent_state>.watches` on that same turn, so the answer could have been produced from either source.
TRACE BODIES MUST CONFIRM: the `section` argument of the `agent_inspect` calls of Runs f51d1db6 and 049af207 and the returned bodies. (`overview` alone has no pair and no level, so for [59] either `work` was read or the per-turn state was used.)

### e.3 The list in [65]

[65] (Run 049af207) lists «3 متابعات سعرية على EURUSDm: تحت 1.11305، فوق 1.2، تحت 1.11305 مرة ثانية» and one Task «waiting بسبب owner_attention», «لا توجد routines», «لا توجد أهداف (goals)»: that is the shape of `work` read literally: three `watches`, one `tasks` entry, empty `routines`, empty `goals`.

Why two «تحت 1.11305» exist: watch 1 (the Task's, in the work thread, with a dedupe key and a long prompt) and watch 3 (chat thread, prompt «placeholder», no key). The automatic dedupe only matches a watch in the **same thread** with an **identical stored payload** and the same Task (`packages/tools/src/lonora_tools/market_watch.py:72-86`), and the keyed dedupe needs the same `dedupe_key` (`market_watch.py:41-52`). Neither applies, so a second watch on the same level was accepted.

---

## What the trace bodies must still confirm (collected)

Already settled by trace Part 4 (no longer open): the arguments and results of the `watch_create` calls of Runs ddae66ad and e79b4bf2 (a.4, a.5), and the `tool_environment` query and result of Run 3fa683e6 (d.5).

Still open (Part 4 covers seven Runs of thread 3c25305d and none of these):

1. Full `state` of watches 1 to 3 (`code`, `steered_by`, `steered_at` present or absent), the `market_watches.updated` events at 12:29:15 to 12:29:18, `ln_supervision_holds` for those ids, and the API access log for those three seconds: settles who switched them off and by which route (a.4).
2. Run 779e4761 (the Task's Run, thread ea0e47c6): tool calls, any `task_wait` result, `pending_input_request.reason`, and the assistant message left in that thread (c).
3. `agent_inspect` arguments and bodies in Runs f51d1db6 and 049af207 (e.2, e.3).
4. The agent's saved trading level and what changed it between 08:56 and 09:05 UTC (d.3).

---

## Verification log

Independent check of this file against the repository at 9f5b1da (read-only), `production-trace.md` (all four parts) and the reproduction scripts. `git -C /home/user/lonorabot status --short` was empty before and after.

**Reruns.**
- `scripts/wl_lifecycle.py` on database 8 after emptying its tables: exit 0, no stderr, output in `runs/wl_lifecycle.check.out`. Compared with `runs/wl_lifecycle.out` after masking ids and timestamps: the only differences are run-specific ids and state lengths that differ by one character (timestamp digits). Every section quoted in this file (A1 to A4, A1b, B0 to B3, C1, C2, D1 to D5, E1, E1b, E2) says the same thing in both runs.
- `scripts/wl_exposure_budget.py`: output identical to `runs/wl_exposure_budget.out` byte for byte.
- New, by the checker: `scripts/wl_check_extra.py`, output `runs/wl_check_extra.out` (no model turn): the production `tool_environment` query through the real search, and the generic resource update applied to a watch row.

**Citations.** Every `path:line` in sections a to e was opened (about 190 line references in some 40 files) and read against the sentence beside it. All but the ones listed under "Corrected" support their claim. The older builds were read with `git show <rev>:packages/market/src/lonora_market/watchers.py` for efb4911, 2477c22, cd2cc91 and f9fffe3: the four `enabled` checks are on the same lines in all of them. Verbatim strings checked against the source: the `CONTINUOUS_NUDGE` opening, the capability-inventory opening, the Arabic attention notice (both halves), the Task title, the `watch_cancel` purpose text, and the chat quotes [59], [65], [75], [77] (the file drops the markdown bold marks of the export; the words are the same).

**Corrected.**
1. a.4, "exactly one function sets `updated_at` and adds 1 to `version`": refuted. There are three paths; the generic `PUT /api/watches/{id}` (`packages/db/src/lonora_db/transactions.py:197-199`) and the keyed replacement in `watch_create` (`packages/tools/src/lonora_tools/market_watch.py:116-119`) were missed. The first leaves exactly the trace's picture (version 2, `enabled=false`, new `updated_at`, state still `active`) with no `code` and no `steered_by`, so the summary's "signature of a cancel or pause" was downgraded to "switched off outside the evaluator, route not settled". The central finding of section a (a disabled watch is not evaluated) stands and is now backed by trace Part 4 as well.
2. d.5, the `tool_environment` query: the file assumed an Arabic query and left the real one as "TRACE BODIES MUST CONFIRM". Trace Part 4 has it: `"watch cancel task routines goals"`, English, result empty. Reproduced on main; the cause is the rarest-word gate plus the half-coverage rule (`packages/tools/src/lonora_tools/tool_discovery.py:62-73`), not the language. Section rewritten.
3. b.2, "records the owner's hold" on a Task cancel: wrong. For a cancel `paused` is false and the function only releases a live hold (`packages/db/src/lonora_db/supervision.py:378-381`). Fixed in b.2 and in the summary row.
4. a.2, the default of `interval_seconds` was cited as contract line 32; it is line 31 (line 32 is `timeframe`).
5. a.3, the trigger test was cited as line 634 for the older builds; it spans 633-634. `f9fffe3` added to the list of builds checked.
6. c, step 3, "the only way to yield cleanly is `task_wait` on a watch the Task owns": too narrow. `task_wait` also accepts a broker recovery and a timer (`packages/db/src/lonora_db/task_wait.py:43`, `:70`).
7. d.1, d.2 and the summary, the budget "caps" the native set: downgraded. `EAGER_SCHEMA_BUDGET` is read by one test and by nothing at run time.
8. a.4, the hold shown as `"by": "owner"` was attributed to E1; it is in both E1 and E2 of the output.

**Moved from "must confirm" to confirmed (trace Part 4 was not used by the first draft).**
- Run ddae66ad: no `enabled` argument, both rows created `enabled: true`, third call identical to the second and answered with the same row.
- Run e79b4bf2: `enabled: false` with `dedupe_key: "cancel-test-1"`.
- Run 3fa683e6: the query and the empty result.

**Added.**
- a.2: paused agents, expired and quarantined watches are also left out of the selection.
- a.4: the full list of clients that call the watch control route (three more web call sites and the mobile one); the supervising-agent path; the three disable paths that do not write `updated_at`; the API access log as a way to settle 12:29.
- a.5: a watch can be switched off through the generic route with no record of who did it; a `dedupe_key` does not stop repeated disabled rows.
- b.2: the other callers of `control_task` and why the owner's route is the one that fits the trace; a second search showing nothing but the evaluator reads the watch-to-Task link.
- d.3: the code line that makes a signed mandate `autonomous`; UNSURE on what set the production agent to `analysis` between 08:56 and 09:05 UTC.
- d.6: the 6-watch and 3-Task limits of the per-turn state; which production Runs had the three watch ids in every request; the empty search as the one thing that pushed the model away from `watch_cancel`.

**Checked for a missed condition and found none.**
- "A disabled watch never reaches the wake code": the SQL filter, the early return, both re-reads under lock and `watch_can_trigger` were read; streamed quotes and candles go through the same `check_watches` and the same filter. No other caller of `check_watch` exists.
- "Nothing touches the watch when a Task ends": `control_task`, `finish_task`, `cancellation.py`, the Task route and the gateway steps were searched for the watch table and for `task_run_id` / `task_id` readers, with two different searches each.
- "No prior `tool_environment` call is needed" and "a non-native name still executes": `resolve_call` and `execute` read; D4 rerun shows all four calls `ok: true`.
- The stop-gate path to `owner_attention`: `request_task_attention` is the only writer of that `waiting_reason` (search for `OWNER_ATTENTION`), and its only caller is the executor.

**Not confirmed, left marked.** Who switched watches 1 to 3 off at 12:29 and by which route; what Run 779e4761 did before it stopped; the `section` argument of the two `agent_inspect` calls; whether the production model provider lets a model call a tool it was not offered; how `task.attention_required` reached the owner's screen.
