# Conversation group C, part 2: the cancel / delete chain [58]–[81], root causes 6 and 7

Repository `/home/user/lonorabot`, `main` HEAD `9f5b1da`, read-only. Paths are relative to the repo root.
Scripted reproductions ran against the real runtime on audit database 11; every model turn in them is
SCRIPTED (the "model" is a fixed list of tool calls and texts), and the evidence is what the runtime
returned.

| Script | Raw output |
|---|---|
| `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/conv_c_discovery.py` | `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/conv-C-discovery.out` |
| `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/conv_c_watches.py` | `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/conv-C-watches.out` |
| `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/conv_c_task.py` | `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/conv-C-task.out` |

(`conv_c_reset_db11.sh` in the same scripts folder empties database 11 before a run.)

## 0. Which code produced these replies

Per the lead's timeline correction (`TIMELINE_CORRECTION.md` in the audit folder): [56]–[71] ran on build
`cd2cc91`, [72]–[81] on `9f5b1da` (today's `main`). `git diff --stat cd2cc91 9f5b1da -- packages apps/api apps/worker`
is empty: the whole backend that served [58]–[71] is byte-identical to `main`. The files this report
relies on (`market_watch.py`, `tool_discovery.py`, `supervision.py`, `trading-policy.md`) are also identical
in `aa50e8e`, `2477c22`, `cd2cc91` and HEAD (checked by hash; the only change to `market_watch.py` after
`aa50e8e` is three `taint_row_from` lines). So every failure in this range is a failure of `main` **by
observation**, subject only to model variance. PR #42 was live throughout.

## 1. Headline conclusions

1. **Root cause 6 is confirmed and reproduced** (section 4). `"حذف المتابعات"`, `"امسح المهام"` return nothing;
   `"delete watch"` and `"remove watch"` return unrelated tools and not `watch_cancel`.
2. **Root cause 7 is confirmed as code, but it is probably not what blocked this conversation** (section 2).
   - Code: cancel, pause, resume and update are restricted to the caller's own watches; another agent's
     watch answers `market_watches_not_found`. Reproduced.
   - But the Personal Agent cannot even *see* another agent's watches with `watch_list` (it returned
     `[]`). The listing in [65] has exactly the shape and order of `agent_inspect(section="work")` on
     **the Personal Agent itself**, and the Task «إدارة حساب التداول» in the same listing is created for
     the agent that signed the full mandate, which is the Personal Agent. The most likely owner of all
     three EURUSDm watches is therefore **the Personal Agent itself, through its own management Task
     run**. If so, `watch_cancel` through `tool_call` would have succeeded for every one of them
     (reproduced: a chat run cancels a Task-owned watch of the same agent, `ok: true`).
   - TRACE MUST CONFIRM: `agent_id`, `thread_id` and `state.task_id` of each EURUSDm watch row.
3. **The duplicate «تحت 1.11305» needs no second agent.** De-duplication compares the *whole stored payload,
   prompt text included*, within the same agent, the same thread and the same Task. A second
   `watch_create` with the same condition and a differently worded `prompt` creates a second watch.
   Reproduced five ways (section 2.4).
4. **No guard on `main` reads a chat reply for a false «تم», a promise, a denial of ability or an internal
   term.** The four replies [63], [69], [71] and a leak sample were committed byte-for-byte with one model
   turn and no runtime notice (section 3, 5).
5. **`watch_create` is native for the Personal Agent; `watch_list` and `watch_cancel` are not.** That
   asymmetry is what makes [77] likely: asked to «جرب», the only watch tool in the native list creates.
   `watch_create` accepts `enabled: false`, never de-duplicates a disabled watch, and nothing separates a
   "trial" call from a real one (section 4.4).
6. **There is no hard delete for an agent.** The owner said «امسح / احذف». `watch_cancel` only disables
   («its record stays»), and cancelled records keep appearing in `watch_list` and in
   `agent_inspect(section="work")`. The owner's UI has both Cancel and a real `DELETE /api/watches/{id}`.
7. **Nothing stores an unfinished owner request.** After [77] no state says "delete the watches" is still
   open, so [78]–[81] start clean.

## 2. Root cause 7 settled: `packages/tools/src/lonora_tools/market_watch.py`

### 2.1 Who owns a watch

- A watch row always has an agent: `MarketWatchRepository.create` raises `watch_agent_required` without
  one (`packages/db/src/lonora_db/market_watches.py:65-66`). The tool passes `agent_id=context.agent_id`
  (`packages/tools/src/lonora_tools/market_watch.py:129-136`).
- Thread: a Task run's watch is stored on the Task's own work thread; a chat or wake run's watch on the
  conversation (`market_watch.py:96-102`). A Task run also stamps `state.task_id` and
  `state.task_run_id` (`market_watch.py:137-142`).
- A Task has a separate work thread: `create_task` makes one with `purpose="work"`
  (`packages/db/src/lonora_db/tasks.py:176-178`).
- The owner's UI may also create a watch for any agent (`apps/web/src/shell/domain/api.ts:75`).

### 2.2 Visibility

| Read path | Scope | Includes cancelled / disabled rows | Evidence |
|---|---|---|---|
| `watch_list` («Read this agent's durable market watches.») | caller's own only | yes, up to 200 | `market_watch.py:148-157`; `packages/db/src/lonora_db/transactions.py:63-80` (no `enabled` filter) |
| `agent_inspect(section="work")` | the caller itself, or an agent it supervises | yes (adds an `enabled` flag) | `packages/tools/src/lonora_tools/supervision.py:166-177`, `:229-232`, `:411-417` |
| `<live_agent_state>` in every run's context | caller's own, enabled and active, first 6 summaries with **full id and level** | no | `packages/agent-runtime/src/lonora_agent/context/team.py:74-91`; `packages/db/src/lonora_db/agent_state.py:339-352`, `:648`, `:33` |
| `<protected_operational_state>` `active_watches` | caller's own, enabled, 8, **no level** | no | `packages/db/src/lonora_db/operational_state.py:199-218`, `:55` |

Reproduction (`conv-C-watches.out`, run P1): agent T owns one EURUSDm below-1.11305 watch. The Personal
Agent P calls `watch_list` → `{"ok": true, "watches": []}`. P's first request context does not contain T's
watch id anywhere. P sees it only through `agent_inspect(agent_id=T, section="work")`, which carries
`"authority": "supervised_read"`.

Consequence for [65]: the three watches were either P's own, or P inspected one other agent. The same
listing names one Task, «إدارة حساب التداول», status `waiting`, reason `owner_attention`, plus "no routines"
and "no goals". `agent_inspect(section="work")` returns exactly these four lists for **one** agent
(`supervision.py:229-247`). The Task with that title is created when a full mandate is signed, for
`row.agent_id` of the grant and from the signing conversation (`packages/auth/src/lonora_auth/account_authority.py:136-142`;
the Arabic title is `packages/bus/src/lonora_bus/attention_messages.json:11`). The mandate was signed in the
Personal Agent's thread ([7]–[8]). Its task prompt tells the run to «persist meaningful market-triggered
follow-up» and to «persist a real wait on the relevant watch» (`account_authority.py:154-159`), and
`watch_create` is native in a Task run (section 4.3).

Reproduction of the shape (`conv-C-task.out`, runs K1 and C2): a continuous Task of P titled
«إدارة حساب التداول» arms three watches from its work thread; then a chat run calls
`agent_inspect(agent_id=P, section="work")`. Result: `watches` = below 1.11305, above 1.2, below 1.11305
(newest first, the order of [65]), `routines: []`, `goals: []`, and
`tasks: [{"title": "إدارة حساب التداول", "status": "waiting", "phase": "waiting", "waiting_reason": "owner_attention", ...}]`.
The same three watches, with ids and levels, and the same task line are also in the chat run's
`<live_agent_state>` block without any tool call (`"watch_count": 3`).

### 2.3 Cancel, pause, resume, update: own watches only

- `steer` passes `agent_id=context.agent_id` to `control_watch` (`market_watch.py:172-182`); `update`
  does the same (`market_watch.py:209-216`).
- `steered_watch` raises `market_watches_not_found` when `row.agent_id != agent_id`; the docstring says
  «Another agent's watch reads as not found, so an agent can neither steer nor probe it.»
  (`packages/db/src/lonora_db/market_watches.py:115-125`).
- The tool descriptions say it: `watch_cancel` «Stop one of your own watches; its record stays, and
  watch_resume undoes it.» (`market_watch.py:254-255`).

Every path by which the Personal Agent P could act on a watch that agent T created:

| Path | Result | Evidence |
|---|---|---|
| `watch_cancel`, `watch_pause`, `watch_update` on T's id | `{"ok": false, "code": "market_watches_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", ...}}` | reproduced, P1; `market_watches.py:123-124`; `packages/agent-runtime/src/lonora_agent/environment.py:80-81` |
| `agent_control(action="pause", target="watch")` (supervision) | `{"ok": true, "changed": true, "paused": true}`; `resume` undoes it. **Pause and resume only, no cancel** | reproduced, P1; `packages/contracts/src/lonora_contracts/supervision.py:16`; `packages/db/src/lonora_db/supervision.py:528`, `:610-614`. Tool is discovery-only (`supervision.py:609-623` has no `eager`) |
| `agent_control(action="message")` / `peer_send` | asks T's own model to cancel; indirect, not guaranteed | `packages/tools/src/lonora_tools/supervision.py:432-439` |
| `task_control` | own Tasks only: `task_agent_mismatch` otherwise | `packages/db/src/lonora_db/tasks.py:411-412`; `packages/tools/src/lonora_tools/tasks.py:57-58` |
| `owner_action_propose` | no card kind cancels a watch | kinds listed at `packages/tools/src/lonora_tools/owner_actions.py:290-300` |
| `runtime_control` tools (`runtime_status`, `wait_for_input`, …) | none steers a watch | `packages/tools/src/lonora_tools/runtime_control.py:180-214` |

What the owner can do from the UI, which no agent can:

- `POST /api/watches/{watch_id}/control` with `cancel | pause | resume | extend` on **any** of the owner's
  watches: `control_watch` is called with no `agent_id` (`apps/api/src/lonora_api/routes/watches.py:28-41`).
  Used by `apps/web/src/conversation/sheets/WatchesSheet.tsx:25`, `apps/web/src/shell/domain/SchedulesPages.tsx:258`,
  `apps/web/src/shell/agent/AgentPage.tsx:191`.
- `DELETE /api/watches/{id}` removes the row (`apps/api/src/lonora_api/routes/__init__.py:69-75`;
  `packages/db/src/lonora_db/transactions.py:211-222`); used by `apps/web/src/components/market/MarketWatch.tsx:328`.
- Reproduced at the end of `conv-C-watches.out`: owner cancel of T's watch → `enabled: false`,
  `state.code: "watch_cancelled"`, `steered_by: "owner"`; owner delete → `{"deleted": true}`.

Parity gap (brief §6, principle 10): no tool deletes a watch; no tool cancels another agent's watch; no tool
lists all of the owner's watches; there is no bulk cancel.

### 2.4 De-duplication on create

Two rules, both scoped to the calling agent:

1. With `dedupe_key`: one live watch per `(owner, agent, key)`; same stored payload → returned with
   `deduplicated: true`; different payload → the old one is disabled with `state.code = "watch_replaced"`
   and a new one is created (`market_watch.py:32-52`, `:108-128`).
2. Without `dedupe_key`: `identical_watch` returns an existing watch only if it is the same owner and
   agent, the **same thread**, `enabled` true, the **entire stored payload equal**, and the same
   `state.task_id` (`market_watch.py:55-87`, `:103-107`). The payload includes `prompt`, `level` as a
   string, `expires_at`, intervals and every default (`packages/contracts/src/lonora_contracts/market_watch.py:27-29`, `:43`).
3. A replay of the same tool call returns the same row by `resource_id` (`market_watch.py:93-95`).
4. No race for identical payloads on PostgreSQL: both paths take an advisory transaction lock keyed by
   agent and key or payload digest (`market_watch.py:36-40`, `:64-71`).

Reproduced results (`watch_create`, EURUSDm, `condition: "below"`):

| Case | Result | Run |
|---|---|---|
| T has the watch; P creates the same condition and prompt | **new watch** (duplicate across agents) | `conv-C-watches.out` P2, call 1 |
| P repeats the identical call in the same run | `deduplicated: true`, same id | P2, call 2 |
| P repeats it in a later run of the same conversation | `deduplicated: true`, same id | P2b |
| T repeats its own identical call in a later run | `deduplicated: true`, same id | T2 |
| Same condition and level, **different prompt wording** | **new watch** | P2, call 3 |
| `level: "1.113050"` instead of `"1.11305"` | **new watch** (stored string differs) | P2, call 4 |
| Same payload with `enabled: false` | **new disabled watch**, and again a second one on repeat | P2, calls 5 and 6 |
| Inside one Task run: same condition, different prompt | **new watch** in the Task's thread | `conv-C-task.out` K1, call 3 |
| Inside one Task run: identical payload | `deduplicated: true` | K1, call 4 |
| Chat run repeats the Task's exact payload | **new watch** (different thread, no `task_id`) | `conv-C-task.out` C3 |

Most likely origin of the duplicate in [65]: the management Task armed «below 1.11305» twice with two
prompt texts (a model rarely writes the same English prompt twice), or once in the Task and once in chat.
TRACE MUST CONFIRM: the `payload.prompt`, `thread_id`, `state.task_id`, `created_at` and
`payload.enabled` of the two «below 1.11305» rows.

### 2.5 Three further facts the trace reading depends on

- **A cancelled watch stays listed.** After P cancelled its own watch (`ok: true`, `undo: "watch_resume"`),
  `watch_list` still returned it with `payload.enabled: false`, `state.code: "watch_cancelled"`
  (`conv-C-watches.out`, P3). `agent_inspect(section="work")` lists it too. A model that counts rows
  reports the cancelled watch as existing. So [65] "three watches" is compatible both with "nothing was
  cancelled in [63]" and with "one was cancelled and still counted". Only `<live_agent_state>` filters them.
- **A successful long-tail tool becomes native in the agent's later runs.** After the successful
  `watch_cancel` in P3, the next run's native list contained `watch_cancel`
  (`"promoted": ["watch_list", "watch_cancel", "agent_control"]`, `conv-C-watches.out` P4;
  `packages/agent-runtime/src/lonora_agent/tool_exposure.py:167-177`; at most 6 within 4,100 schema
  characters, `packages/tools/src/lonora_tools/registry.py:84-85`). If [63] had made a successful
  `watch_cancel`, the tool would very likely have been native in [69]–[77]; [75] says no delete tool was
  visible. This points to "[63] cancelled nothing", but it is inference. TRACE MUST CONFIRM: the tool
  calls of the run that produced [63], and `tool_exposure.native` / `promoted` of the runs behind
  [69], [71], [75], [77].
- **Cancelling the Task does not stop its watches at once.** After `task_control(action="cancel")` returned
  `status: "cancelled"`, the two remaining Task-owned watches were still `enabled: true`
  (`conv-C-task.out`, "after C5"). The only code that disables a Task-owned watch for a finished Task runs
  when that watch next triggers (`packages/market/src/lonora_market/watchers.py:654-665`,
  `state.code = "task_terminal"`). UNSURE: whether any other cleanup runs later; I found no other writer of
  `task_terminal`. The constitution promises «Task-owned watches stop when that work terminates.»
  (`packages/agent-runtime/resources/constitution/tool-policy.md:11`).

## 3. (b) [62] → [63] «تم الإلغاء… أُزيلت», then [65] shows three watches

### 3.1 What could have been called

[60] «عدل المهمة» produced the question card [61]; it is `wait_for_input` (native, core;
`packages/tools/src/lonora_tools/runtime_control.py:199-205`). The four choices are written by the model
(`runtime_control.py:28-32`), so «ألغِ المهمة بالكامل» was the model's own option. The owner's tap [62]
answers the waiting run and the **same run** continues (`packages/db/src/lonora_db/messages.py:291-299`).

For "cancel the task entirely" the registry offers two different things, both discovery-only for the
Personal Agent's chat run (section 4.3):

| Tool | Effect | Needs |
|---|---|---|
| `task_control(action="cancel")` | cancels a Task of this agent | `task_id` and `expected_version` (`packages/db/src/lonora_db/tasks.py:426-427`); both are in `<live_agent_state>` |
| `watch_cancel` | disables one own watch | `watch_id`; in `<live_agent_state>` |

The owner's «المهمة» in [58] meant "the thing that is running"; [59] answered with a *watch* («المراقبة
النشطة: EURUSDm تحت 1.11305») and a *task status* («الحالة: waiting») in one bullet list, and [63] says
«المهمة/المتابعة». The model merged the Task and the watch. [65] then reports the Task still `waiting`, so
`task_control cancel` did not succeed in [63].

Three explanations fit the code; the trace picks one:

1. No tool call at all after the card answer: the reply was a bare claim.
2. `watch_cancel` on one of the two «below 1.11305» watches succeeded; [65] then counted the cancelled
   record (section 2.5).
3. A call failed (for example `task_control` with a wrong version → `version_conflict`,
   `tasks.py:426-427`, or a bridge call with a wrong name → `tool_call_target_unknown`,
   `packages/tools/src/lonora_tools/registry.py:222`) and the model reported success anyway.

TRACE MUST CONFIRM: tool calls and results of the run that holds [60]–[63]; `payload.enabled` and
`state.code` of each EURUSDm watch at 09:56–09:58 UTC.

### 3.2 How a false «تم» passes on `main`

Every check a final chat reply meets, and why none applies:

| Mechanism | What it does | Why [63] passes |
|---|---|---|
| Constitution sentence (PR #42) | «Say something was done only when a successful tool result in this request shows it.» (`packages/agent-runtime/resources/constitution/trading-policy.md:7`) and «Validate the returned machine status before claiming success.» (`packages/agent-runtime/resources/constitution/tool-policy.md:1`) | prompt text only; nothing enforces it |
| `uncertain_outcome.py` (PR #42) | appends one fixed line when a **financial** call (`trade_execute`, `trade_close_positions`, `goal_step_execute`) is still uncertain (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:23`, `:36`, `:134-139`); its docstring: «no wording of the owner or the model is read» (`uncertain_outcome.py:3`) | not a financial call; it never blocks or replaces a reply |
| `stop_gates.py` | bounded nudges for **Task runs only**: `task_stop_gate` returns "do not continue" when the run has no Task (`packages/agent-runtime/src/lonora_agent/stop_gates.py:178-181`) | a chat run has no Task |
| Financial truth gate | replaces the text only when a financial result is unverified, or blanks it beside a proposed financial call (`packages/agent-runtime/src/lonora_agent/model_runtime.py:219-234`) | no financial call involved |
| `EFFECT_CLAIM` regex | only switches off incremental streaming for the turn (`packages/agent-runtime/src/lonora_agent/public_stream.py:47-51`); the Arabic branch lists «تنفيذ، فتح، إغلاق، إرسال، تفعيل، شراء، بيع، الموافقة» (`public_stream.py:16`) | «تم الإلغاء» does not match (checked: `False`); and a match would not block anyway |
| Privacy redaction | removes credentials, paths, private ids (`packages/core/src/lonora_core/public_reply.py:37-51`) | not about truth |
| `final_answer` | applies the Task stop gate, then the uncertain line, then returns (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:170-185`; called at `packages/agent-runtime/src/lonora_agent/tool_loop.py:595-609`) | nothing else runs |

Reproduction (`conv-C-watches.out`, P5): owner text «ألغِ المهمة بالكامل», SCRIPTED model returns the exact
text of [63] with **no tool call**. Outcome: `status: completed`, `model_turns: 1`, `runtime notices added: []`,
stored assistant message identical to the scripted text.

## 4. (c) The delete chain [66]–[81]

### 4.1 [68] → [69] «سأحذف» with no action

The owner's tap on the card [67] resumes the waiting run; the model's next turn was prose with no tool
call, so the loop took the final-answer path (`tool_loop.py:590-609`). Which gate should have caught a
promise that ends a turn:

- `stop_gates.py` does not: Task runs only (`stop_gates.py:178-181`). Its nudge text does contain the
  right rule, but it is injected only into continuous Task runs: «only a successful saved wait can support
  a promise to follow up» (`stop_gates.py:45-54`).
- `uncertain_outcome.py` does not: financial results only (section 3.2).
- Nothing else inspects the final text for intent.

Reproduction (P6): the exact text of [69] with no tool call is committed, one model turn, no notice.
The owner had to send «؟» [70] to get another turn.

### 4.2 [71] «ما عندي أداة حذف»: root cause 6 confirmed

`search_definitions` (`packages/tools/src/lonora_tools/tool_discovery.py:44-89`):

- Corpus per tool = name + description + top-level parameter names, tokenised by
  `[^\W_]+` after NFKC and casefold (`tool_discovery.py:40-41`, `:52-57`). All descriptions are English.
- `gate = min(query_tokens, key=lambda token: (frequencies[token], token))` (`tool_discovery.py:62`): the
  rarest query token, **including a token with frequency 0**.
- A tool is dropped unless it is an exact-name match or contains the gate token
  (`tool_discovery.py:67-73`). So one query word that appears in no tool empties the result, and one rare
  word that appears only in unrelated tools returns only those.
- The tool's own schema asks for English: «Use English terms for the first-party catalog»
  (`packages/tools/src/lonora_tools/environment.py:16`); the tool description says «using concise English
  catalog terms» (`packages/tools/src/lonora_tools/registry.py:155-158`).
- An empty search returns `{"tools": [], "total": 0}` with no hint (`registry.py:361-388`).

Reproduced over the full 126-tool catalog (`conv-C-discovery.out`; token → number of tools containing it):

| Query | Token frequencies | Gate | Results |
|---|---|---|---|
| `حذف المتابعات` | حذف 0, المتابعات 0 | المتابعات | none |
| `امسح المهام` | امسح 0, المهام 0 | المهام | none |
| `ألغِ المتابعة` | ألغ 0, المتابعة 0 | ألغ | none |
| `delete watch` | delete 2, watch 10 | delete | `workspace_update`, `chart_annotate` |
| `remove watch` | remove 5, watch 10 | remove | `chart_remove_indicator`, `skill_package_control`, `news_feed_subscribe`, `memory_write`, `owner_action_propose` |
| `delete watches` | delete 2, watches 9 | delete | `workspace_update`, `chart_annotate` |
| `watch cancel delete` | cancel 4, delete 2, watch 10 | delete | `workspace_update`, `chart_annotate` |
| `delete task` | delete 2, task 11 | delete | `workspace_update`, `chart_annotate` |
| `cancel watch` | cancel 4, watch 10 | cancel | **`watch_cancel`**, `task_control`, `goal_control`, `trade_execute` |
| `stop watch` | stop 6, watch 10 | stop | **`watch_cancel`** first of 6 |
| `watch` | watch 10 | watch | `watch_pause`, **`watch_cancel`**, `watch_resume`, `watch_update`, `watch_list`, … (10) |
| `watch_cancel` | cancel 4, watch 10 | cancel | **`watch_cancel`** first (exact name) |

The same results came back from the real `tool_environment` tool inside a run (`conv-C-watches.out`, P4):
`query: "حذف المتابعات"` → `"tools": [], "total": 0`; `query: "delete watch"` → `workspace_update` first.
`tool_environment(tool_name="watch_cancel")` returns the schema. A guessed name such as `watch_delete`
returns `tool_not_allowed` with `recovery.next_action: "respect_scope"` (`registry.py:351-353`), which reads as
a permission refusal, not "no such tool".

Why the model's «حذف» finds nothing even in English: the word the owner used is delete/remove/erase; the
catalog word is *Stop* («Stop one of your own watches; its record stays, and watch_resume undoes it.»,
`market_watch.py:255`) and the tool name says *cancel*. Neither "delete" nor "remove" appears in any watch
tool.

The statement in [71] is also literally true in one respect: no tool deletes (section 2.3). It is false as
an inability: the three watch ids were in the run's context and `watch_cancel` was one `tool_call` away.
Reproduction (P7): the text of [71] is committed with no tool call and no notice.

Texts already in context that the model ignored:

- «A watch is cancelled with watch_cancel or changed with watch_update … Reach a tool outside your native
  list with tool_call.» (`trading-policy.md:7`, constitution, loaded for every run:
  `packages/agent-runtime/src/lonora_agent/skills/loader.py:27-45`). Confirmed present in P's first request.
- The capability inventory lists `watch_cancel` by name under `market` and says to inspect with
  `tool_environment` «before claiming an ability is absent» (`registry.py:424-431`). Confirmed present.

### 4.3 Exposure: is `watch_cancel` visible by default?

Printed by `conv_c_discovery.py` and confirmed from real runs (native list sent on model turn 1):

| Tool | Personal Agent chat run (`core + market + coordination`) | Personal Agent Task run (`core + market + task`) |
|---|---|---|
| `watch_create` | **native** (`market_watch.py:243`) | **native** |
| `watch_list`, `watch_cancel`, `watch_pause`, `watch_resume`, `watch_update` | discovery-only | discovery-only |
| `agent_inspect` | native (`supervision.py:607`) | discovery-only |
| `agent_control`, `task_inspect`, `task_control`, `task_start`, `routine_list`, `goal_list` | discovery-only | discovery-only |
| `tool_environment`, `tool_call`, `wait_for_input` | native | native |

Profiles: `packages/agent-runtime/src/lonora_agent/tool_exposure.py:43-49`; eager sets:
`packages/tools/src/lonora_tools/base.py:18-25`. 23 of 126 tools are native in the chat run. A discovery-only
tool is called as `tool_call {"name": ..., "arguments": {...}}`; the bridge unwraps it to the real call
(`registry.py:180-209`). So the agent can *create* a watch with one native call but needs to know to use the
bridge to *list* or *stop* one.

### 4.4 [73] the guard explained to the owner

[73]: «ما أملك نتيجة تنفيذ مؤكدة لحذف المتابعات… ولا أقدر أدّعي الإلغاء بدون رد أداة ناجح».

- No repair prompt is injected into a chat run. `uncertain_outcome.py` has no prompt for the model at all;
  it only has the owner-facing line «نتيجة العملية غير مؤكدة بعد؛ أتحقق منها ولن أعيد إرسالها.»
  (`uncertain_outcome.py:36`). The `stop_gates.py` nudges go to Task runs only.
- The text the model paraphrased is the PR #42 constitution sentence, present in every run:
  **«Say something was done only when a successful tool result in this request shows it.»**
  (`trading-policy.md:7`). «رد أداة ناجح» = "a successful tool result"; «ما أملك نتيجة تنفيذ مؤكدة» also echoes
  «Validate the returned machine status before claiming success.» (`tool-policy.md:1`).
- So the model recited a rule of its own instructions to the owner as the reason it could not act. No
  server check stops a reply from quoting or paraphrasing policy text. Brief principle 7 («لا يُشرح الـguard
  للمالك أبدًا») has no enforcement on `main`.
- TRACE MUST CONFIRM: that the run behind [73] made no tool call (the reply is a pure explanation).

### 4.5 [74] → [75] «شوف ادواتك»

«ما في أداة حذف ظاهرة تحت هذا الاستعلام المبسّط» is the model describing an empty or irrelevant
`tool_environment` search result (section 4.2). It names `watch_cancel` itself (from `trading-policy.md:7` or
the inventory) and then *offers* to look it up instead of calling `tool_environment(tool_name="watch_cancel")`
or `tool_call`. TRACE MUST CONFIRM: the exact `query` string(s) sent to `tool_environment` in this run.

### 4.6 [76] → [77] a new disabled watch "to test"

- The call that does this is `watch_create` with `enabled: false`. `enabled` is an ordinary model-settable
  field of the `Watch` schema (`packages/contracts/src/lonora_contracts/market_watch.py:29`), and `create`
  stores the payload as given (`market_watch.py:129-136`).
- A disabled watch is never de-duplicated: both look-ups filter on `enabled` true (`market_watch.py:47`,
  `:79`). Reproduced: two identical `enabled: false` calls created two rows (P2, calls 5 and 6).
- `watch_create` is the only watch tool in the native list (section 4.3), which is the likely reason a
  model told «جرب» reached for it.
- Nothing prevents a side-effecting "trial" call. The loop has no dry-run mode and no rule that a mutating
  call must serve the owner's open request; `watch_create` is `replay_safe=True` and mutating
  (`market_watch.py:237-244`). `tool-policy.md:5` says «Do not invent a price threshold or trade parameters
  merely to fill a watch», which is prompt text only.
- The new row is disabled, so it never fires, but it is one more record in `watch_list` and
  `agent_inspect(section="work")`, and the owner's UI lists it.
- [77] then says the right tool is `watch_cancel` «على المعرفات الحالية» and stops again. The ids were in
  context.
- TRACE MUST CONFIRM: the `watch_create` arguments of this run (symbol, level, `enabled`), whether a fourth
  EURUSDm row exists, and whether any `tool_call`/`tool_environment` call for `watch_cancel` was made.

### 4.7 After [77]: nothing resumes the request

- [78] «مرحبا» and [80] start new runs. A new run's context is rebuilt from the thread: recent messages,
  `<live_agent_state>`, and a block of earlier tool results labelled historical
  (`packages/agent-runtime/src/lonora_agent/context/run_evidence.py:73-80`).
- There is no persistent "open owner request" record. A search of `packages` and `apps` for
  `open_request`, `pending_offer`, `open_items`, `unfinished_request` finds nothing. The only durable
  "unfinished" states are a run in `waiting_input` (a card), a Task, an approval and an owner action card.
  The delete request was none of these: every run in the chain ended `completed` with prose.
- So [79] «مرحباً.» and [81] are correct by the runtime's lights. [81] again hedges «أحذف أو أوقف متابعة إذا
  كانت الأداة متاحة».

## 5. (d) Leaked internal terms in [58]–[81]

| Term | Messages | Where the string comes from |
|---|---|---|
| `waiting` | [59], [65], [71] | Task status literal (`packages/contracts/src/lonora_contracts/tasks.py:10`), computed in `snapshot` (`packages/db/src/lonora_db/tasks.py:283-289`). Reaches the model in `<live_agent_state>.tasks[].status` (`team.py:82-91`; `packages/db/src/lonora_db/agent_state.py:635`), in `agent_inspect(section="work").tasks[].status` (`supervision.py:221-227`), in `task_inspect`. A watch's own state word is `lifecycle: "pending"` (`agent_state.py:52`), so «الحالة: waiting» in [59] is the Task's status attached to a watch line. |
| `owner_attention` | [65] | `OWNER_ATTENTION = "owner_attention"` (`packages/db/src/lonora_db/tasks.py:20`), the Task's `waiting_reason` in the same three places. It is set when a continuous Task run answers in prose three times without `task_wait` (`stop_gates.py:41`, `:126-129`; `loop_outcomes.py:109-152`), reason `task_wait_required`. Reproduced in `conv-C-task.out` K1. |
| `routines` | [65] | result key `"routines"` of `agent_inspect(section="work")` (`supervision.py:233`) or of `routine_list` (`packages/tools/src/lonora_tools/routine.py:50`) |
| `goals` | [65] | result key `"goals"` of `agent_inspect(section="work")` (`supervision.py:247`) or of `goal_list` (`packages/tools/src/lonora_tools/trading_goal.py:101`) |
| `watch_cancel`, `watch` | [75], [77] | tool name: `market_watch.py:254`; named in `trading-policy.md:7`, in `packages/agent-runtime/resources/system/lonora.md:434`, and in the capability inventory (`registry.py:424-433`) |

No reply check removes these. The privacy filter states that tool names are deliberately allowed:
«registry names are intentionally not private» (`packages/core/src/lonora_core/public_reply.py:40-41`).
Reproduction (P8): a reply containing `waiting`, `owner_attention`, `routines`, `watch_cancel` and the
spaced `**` pattern of [65] is stored unchanged.

Related observation, outside my range but explaining [65]: when the management Task was handed to the owner,
the runtime's own Arabic message is «هذه المهمة المستمرة غير مراقَبة: لم يُحفظ أي انتظار مراقبة أو مؤقت مراجعة…»
(`packages/agent-runtime/src/lonora_agent/runtime_notices.py:150`). In my reproduction that question stayed on
the Task's run; the chat thread received no message. TRACE MUST CONFIRM: whether the owner was ever shown
this question (it is not in the exported conversation), and the `waiting_reason` history of the Task.

## 6. Classification on latest `main`

"By observation" = the reply was produced by code identical to `main` (section 0).

| Message | Problem | On `main` | Evidence |
|---|---|---|---|
| [58]→[59] | Internal status `waiting`; says the running job is EURUSDm, contradicting [57]; mixes a Task status with a watch; ends with an offer | **FAILS** (by observation) | no reply guard for internal states (section 5, P8); the Task and watch facts come straight from `<live_agent_state>` |
| [60]→[61] | Question card for «عدل المهمة» | not a failure by itself: a real ambiguity. The option «ألغِ المهمة بالكامل» merges Task and watch | `runtime_control.py:199-205` |
| [62]→[63] | «تم الإلغاء… أُزيلت», yet [65] lists three watches | **FAILS** | no gate reads a chat reply for an unsupported "done" (section 3.2); P5 commits the same text with no tool call. Whether anything was cancelled: TRACE |
| [64]→[65] | Leaks `waiting`, `owner_attention`, `routines`, `goals`; duplicate «تحت 1.11305»; offers to tidy instead of doing it | **FAILS** | leak: section 5. Duplicate: de-duplication compares the full payload including the prompt, per agent, thread and Task (section 2.4). Cancelled rows are still listed (section 2.5) |
| [66]→[67] | Question card: watches only, or the management Task too | not a failure: stopping the management Task is a real owner decision | — |
| [68]→[69] | «سأحذف» and the turn ends | **FAILS** | stop gates are Task-only (`stop_gates.py:178-181`); P6 commits the same text |
| [70]→[71] | «ما عندي أداة حذف مباشر» | **FAILS**; **PARTLY** true: no delete tool exists for agents, only cancel | root cause 6 reproduced (section 4.2); `watch_cancel` discovery-only (section 4.3); ids were in context; P7 commits the text |
| [72]→[73] | Explains the "no claim without a tool result" rule to the owner | **FAILS** (by observation, ran on `9f5b1da`) | paraphrase of `trading-policy.md:7`; no check on policy talk (section 4.4) |
| [74]→[75] | «ما في أداة حذف ظاهرة تحت هذا الاستعلام»; names `watch_cancel`; offers to search | **FAILS** (by observation) | `tool_discovery.py:62`, `:67-73`; table in section 4.2 |
| [76]→[77] | Creates a new disabled EURUSDm watch "as a test"; names `watch_cancel`; stops | **FAILS** (by observation) | `watch_create` native, `enabled` settable, disabled watches never de-duplicated, no bar on trial effects (section 4.6) |
| [78]–[81] | The delete request is neither resumed nor mentioned; [81] «إذا كانت الأداة متاحة» | **FAILS** (by observation) | no open-request state anywhere (section 4.7) |
| Root cause 6 | discovery gate | **FAILS**, confirmed | section 4.2 |
| Root cause 7 | own-watch restriction; agent-scoped de-duplication | **FAILS** as a parity gap, confirmed; probably **not** the blocker in this conversation | sections 2.2–2.4 |

Nothing in this range is FIXED on `main`: no commit between `cd2cc91` and `9f5b1da` touches the backend.

## 7. What the production trace must confirm

1. TRACE MUST CONFIRM: for each EURUSDm watch row (three before [77], probably four after): `agent_id`
   (Personal Agent or another agent), `thread_id` (the chat thread or a Task work thread), `state.task_id`,
   `payload.prompt`, `payload.level`, `payload.enabled`, `state.code`, `created_at`, `updated_at`,
   `state.steered_by`. This settles ownership and the duplicate.
2. TRACE MUST CONFIRM: whether the Task «إدارة حساب التداول» belongs to the Personal Agent, its run's tool
   calls (which `watch_create` calls it made and with what prompts), and how it reached
   `waiting` / `owner_attention` (stop-gate exhaustion `task_wait_required`, or a model-failure escalation).
3. TRACE MUST CONFIRM: tool calls and results of the run [60]–[63] (did it call `watch_cancel`,
   `task_control`, a failed bridge call, or nothing).
4. TRACE MUST CONFIRM: for [59] and [65], whether the model called `agent_inspect`, `watch_list`,
   `task_inspect`, `routine_list`, `goal_list`, or answered from `<live_agent_state>` alone.
5. TRACE MUST CONFIRM: for [69], [71], [73]: that no tool call was made; for [75]: the `tool_environment`
   queries; for [77]: the `watch_create` arguments.
6. TRACE MUST CONFIRM: `execution_state.tool_exposure.native` and `.promoted` of the runs behind [69]–[77]
   (was `watch_cancel` native at any point), and the Personal Agent's `agent_tool_usage` rows.
7. TRACE MUST CONFIRM: whether the server updates at 09:54:57 and 10:38:12 UTC interrupted a run of this
   chain (the first falls between [55] and [56], the second between [71] and [72]).

## 8. Money-safety note

Nothing found here touches the executor, grants, approvals or the journal. Watches «never trade»
(`market_watch.py:239`). Any future widening of watch steering to the owner's scope must keep the existing
hold rules: an agent does not resume a watch the owner or a supervisor holds paused
(`packages/db/src/lonora_db/market_watches.py:168-171`), while cancel only narrows.
