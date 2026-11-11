# Binding principles 9 to 16: what exists, what is missing, where the change attaches

Repository `/home/user/lonorabot`, code at main `9f5b1da` (the working tree is HEAD `3f09572`, which adds
documentation only: `git diff --stat 9f5b1da HEAD -- packages apps scripts tests` is empty). All
`path:line` citations are relative to the repository root and were re-opened before this file was finished
(see "Verification log" at the end). Read-only audit: nothing under the repository was written; `git status
--short` stayed clean.

Sources used: the owner brief (sections 2, 3, 5 to 8), the owner's conversation (message numbers are `[n]`),
`TIMELINE_CORRECTION.md`, and `production-trace.md` (cited as "trace Part N, run id"; all times UTC). Leads
read and re-checked where reused: `trace-guards.md`, `trace-model-availability-updates.md`. Nothing here
designs the Phase 0 fixes or the model-default / watch-lifecycle fixes; it describes causes and attachment points.

Evidence labels:
- **CODE** = read in the repository at the cited line.
- **TRACE** = in `production-trace.md` (the trace wins over any other reading).
- **SCRIPTED** = my driver `scripts/p916_principles.py` (database 13). Every model turn in it is SCRIPTED (written by
  me); the evidence is what the real runtime produced (tool results, committed replies, context blocks, stored
  rows). Raw output: `runs/p9-16-principles.out`; two extra read-only probes: `runs/p9-16-locale-probe.out` (script `scripts/p916_locale_probe.py`) and
  `runs/p9-16-language-line.out` (script `scripts/p916_language_line.py`; it shows the shared test owner's profile language is `ar`, unlike production). All under
  `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/`. The shared test owner and its Personal Agent belong to another session; I created only agents named `p916-…` and left that profile untouched.

Path key. Where a citation gives only a file name (after the first full path in the same item), it means this unique file
(each name occurs once in `git ls-files`): `agent_binding.py` packages/db/src/lonora_db/agent_binding.py; `builder.py`
packages/agent-runtime/src/lonora_agent/context/builder.py; `conversation_locale.py` packages/db/src/lonora_db/conversation_locale.py;
`execution.py` packages/trading/src/lonora_trading/execution.py; `lonora.md` packages/agent-runtime/resources/system/lonora.md;
`loop_outcomes.py`, `loop_restore.py`, `model_runtime.py`, `public_stream.py`, `runtime_notices.py`, `stop_gates.py`, `tool_exposure.py`,
`tool_loop.py`, `uncertain_outcome.py` packages/agent-runtime/src/lonora_agent/ (same name); `team.py` and `run_evidence.py`
packages/agent-runtime/src/lonora_agent/context/; `market_analysis.py`, `symbols.py`, `trade.py` packages/tools/src/lonora_tools/;
`market_watches.py`, `run_retry.py`, `task_wait_settlement.py` packages/db/src/lonora_db/; `metaapi.py`
packages/adapters/src/lonora_adapters/brokers/metaapi.py; `stt.py` packages/adapters/src/lonora_adapters/voice/stt.py; `public_reply.py`
packages/core/src/lonora_core/public_reply.py; `score.py` scripts/genui_eval/score.py; `OWNER_DECISIONS.md` docs/ui-reference/OWNER_DECISIONS.md;
`trading_context.md`, `run_context_summary.md`, `genui_v2_teaching_p.md` packages/agent-runtime/resources/prompts/.

## 0. One-page summary

| # | Principle | Status on main | Cost | Needs the owner first? |
|---|---|---|---|---|
| 9 | open requests are durable | PARTLY: Tasks, pending question cards and crash recovery are durable; a prose offer or an unfinished chat request has no record | S read-only context line / M durable item / L auto-resume | Only for auto-retry of failed turns and item lifetime |
| 10 | owner scope | FAILS for cancel/update/list across agents; PARTLY for pause/resume and reads (supervision grants) | M | No for owner-message cancel (narrowing); yes for cancelling a money-bearing Task |
| 11 | live reads for status | PARTLY: the tools read live and stamp times; nothing makes a status answer use them | S markers / M structural gate | No |
| 12 | server-side reply guard | FAILS (observed on main: [73], [75], [77] ran on 9f5b1da): no check that can block or rewrite a reply looks for codes, tool names or states; the only text scans (privacy redaction, the streaming `EFFECT_CLAIM` hold) never block; the tool-name plumbing exists but is switched off | M | Yes: design tension with two written rules (section P12 (v)) |
| 13 | answer the question asked | PARTLY: the data is in `market_snapshot`; no loaded policy names the shape of a status answer | S | No |
| 14 | remember what was learned | FAILS: no stored symbol map, nothing written in the conversation | M | Policy text conflict to settle in the same change (live lines `lonora.md:60`, `:224`) |
| 15 | owner's language always | PARTLY: profile field exists; empty in production; voice path sends no hint; a Turkish transcript counts as the owner's language everywhere | S (M for a script guard) | Confirm the pin |
| 16 | strength is not bypass | HOLDS: enforcement is server-side at one executor; none of my attachment points changes a check | S (tests only) | No |

## 1. Facts from the trace that apply to several principles

- One agent, Lonora, role `personal`, `trading_account_id` null (trace Part 1, Q6). All four watches and the
  one Task are its own (trace Part 1, Q4/Q5). So in this conversation ownership across agents blocked nothing.
- The 23 native tools offered every run (trace Part 1, "BASELINE native tools") include `agent_inspect`,
  `peer_send`, `trade_execute`, `wait_for_input`, `watch_create`; not `watch_cancel`, `watch_list`,
  `routine_*`, `task_*`, `trade_close_positions`, `market_symbols`, `agent_control`.
- 36 tool calls; none of them `watch_cancel`, `watch_list`, `memory_write`, `market_symbols`, `task_*`
  (trace Part 2, "TOOL EVENTS").
- The reply guards of PR #42 were live for the whole conversation and recorded nothing (TIMELINE_CORRECTION
  point 12); they only read financial results, never reply text (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:3`).
- (Checker addition) The code that produced [4]-[71] is the code of main for every file this section relies on:
  `git diff --stat 2477c22 9f5b1da` is empty for `loop_outcomes.py`, `stop_gates.py`, `run_evidence.py`, `context/memory.py`,
  `runtime_notices.py`, `conversation_locale.py`, `voice_notes.py`, `public_reply.py`, `symbols.py`, `tool_exposure.py`, `lonora.md`,
  the market-analysis `SKILL.md` and `trading_context.md`; `market_watch.py`, `supervision.py` (db) and `model_runtime.py` changed only by
  taint bookkeeping and a GenUI capabilities block (`git diff 2477c22 9f5b1da` on those three files). So "fails on main" holds for the
  whole conversation by code, and for [72]-[81] also by observation.

---

## P9. Open requests are durable

An unfinished request stays an open item and is resumed or mentioned in the next turn.

### Trace
- [69]/[71]: run `e343c96a` promised «سأحذف…», called only `wait_for_input`, and completed 2 seconds after the
  owner's answer (trace Part 2, run lifecycle; Part 4 finding 5). The next owner message «؟» ([70]) got a new
  run `1638329a` that said it had no deletion tool; the deletion was never picked up again, not at 10:53
  (`fb1d4b5a`, `3fa683e6`, `e79b4bf2`) and not at 11:20 (`1bcddcee`, `38b259bb`, which listed deletion as
  possible "إذا كانت الأداة متاحة" while the watches still existed, trace Part 1 Q4) (trace Part 1 digest, Part 3, Part 4).
- [9] «شو وضع الذهب» was an open request when the owner typed «ضع حرف m» ([11]) and «يعني XAUUSDM» ([13]). Runs
  `e09ad476` (no tools; asked what «ضع حرف m» meant) and `10171b1c` (`market_instrument` only; answered with the symbol and its
  specifications) did not resume the analysis that [9] asked for. The analysis
  came in run `6f8ff964` at 09:46:36, 2 min 35 s after the question and after two «ياريت» (trace Part 1 digest).
- [1] was never answered; [3] was answered only at 09:37:46 UTC the next day, by the third retry `d5b850bc` (reply [4], trace Part 1 digest
  and Part 3 "the retry at 09:37:44 answered seq 2 only"). A failed reply whose error is not transient is retried only when the owner asks
  (`model_not_configured` is not in `TRANSIENT_CODES`, `packages/providers/src/lonora_providers/resilience.py:119`, `:130-134`). The only
  caller of `retry_run` is the owner API route `apps/api/src/lonora_api/routes/runs.py:73`; the four retry runs of the trace carry
  `retry_of` and ids derived by `retry_run` (`packages/db/src/lonora_db/run_retry.py:87`, `:132`), so each was an owner request. Message [1]'s
  chain stopped after one failed retry (`e2bc2eae`, trace Part 1 digest) and nothing started it again (trace Part 1 key findings; the lead's
  `trace-model-availability-updates.md` reaches the same reading).

### (i) What exists today
| Mechanism | Where | What it keeps |
|---|---|---|
| Run checkpoint (messages, pending tool calls, round counter, environment) | persisted by `persist` `packages/agent-runtime/src/lonora_agent/tool_loop.py:117`; restored by `restore_checkpoint` `packages/agent-runtime/src/lonora_agent/loop_restore.py:31` | An interrupted run resumes after a restart. Trace: `57dcaeb0` waited 8 s across the 09:54:57 update and completed (trace Part 2). |
| Pending question card | wait path `packages/agent-runtime/src/lonora_agent/executor.py:142-254`; answer merged into the same run `packages/db/src/lonora_db/messages.py:526-553`; a new owner message supersedes an unpublished question `packages/agent-runtime/src/lonora_agent/tool_loop.py:377-379` | A question stays `waiting_input` until answered. After the answer the same run continued (trace: `ddae66ad` 5 rounds, `e343c96a` 2 rounds) and still did not act. |
| Task (durable responsibility) | `TicketRow` `packages/db/src/lonora_db/schema.py:750`; stop gates `packages/agent-runtime/src/lonora_agent/stop_gates.py:86-129`; compute slices `packages/agent-runtime/src/lonora_agent/continuation.py:20-93`; owner-attention handoff `packages/agent-runtime/src/lonora_agent/loop_outcomes.py:109-152` | Work with `task_id` cannot end on a text answer. The gate does nothing for a chat run: `task_progress` returns `None` without a `task_id` (`stop_gates.py:153-155`) and `task_stop_gate` then returns "do not continue" (`stop_gates.py:180-181`). |
| Live agent frame in every turn | `agent_live_state` `packages/db/src/lonora_db/agent_state.py:222`, rendered by `routing_frame` `packages/agent-runtime/src/lonora_agent/context/team.py:59-91` | The agent's own active Tasks (limit 3; id, title, status, phase, waiting_reason, version, can_* flags, failure: the comment says it "deliberately omit[s] plan descriptions", `packages/db/src/lonora_db/agent_state.py:267-290`), up to 6 active runs, the count and up to 6 summaries of its own **enabled** watches (`packages/db/src/lonora_db/agent_state.py:339-354`, `:648`; fields `packages/contracts/src/lonora_contracts/agent_state.py:38-44`), pending approval/authorization counts. `current_work` is excluded from the model's copy (`team.py:88`). |
| Compaction summary | prompt `packages/agent-runtime/resources/prompts/run_context_summary.md:27-33` ("Open operations and commitments … promise to the owner that is unresolved") | Model-written, only when context overflows. No `context_compacted` event occurred in this conversation (trace Part 2). |
| Earlier tool observations | `recent_tool_evidence` `packages/agent-runtime/src/lonora_agent/context/run_evidence.py:207` | Observations, never intents. |
| Manual retry of a failed reply | `retry_run` `packages/db/src/lonora_db/run_retry.py:87` (id derived from the failed run), refusal rules `:93-115` | One retry per failed run, started only by the owner's button. |
| Automatic retry of a transient model failure (checker addition) | `plan_failure` `packages/agent-runtime/src/lonora_agent/model_recovery.py:155-200` (non-transient → `raise`, `:174-175`); backoff scheduled in `tool_loop.py:528-552`; `run.retry_scheduled` event `packages/agent-runtime/src/lonora_agent/executor.py:292-304` | The same run retries itself later for `model_provider_unavailable`/`model_rate_limited` only (`resilience.py:119`). `model_not_configured` fails the run at once, which is what happened to all five failed runs (trace Part 1). |
| Money-only tracking | `append_uncertain_line` `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:134` | Only uncertain financial operations. |
| Thread state | `ThreadPrefsRow` `packages/db/src/lonora_db/schema.py:293` (read cursor, mute, archive, pin, hidden cursor); `ThreadRow.options` `packages/db/src/lonora_db/schema.py:239` (per-chat options; today `web_search`); `MessageRow.suggested_reply` `packages/db/src/lonora_db/schema.py:266` | UI state and a 60-character display suggestion. No open-item content. |

### (ii) What is missing, and how I searched
No record of an offer, a promise or an unfinished owner request that survives the run. Searches:
`grep -rniE "open_request|open_item|pending_offer|pending_proposal|offer_state|open_loop|promis|commitment|owner_request"
packages apps scripts` found no store (restricted to `.py`/`.md`; the unrestricted grep is dominated by JavaScript `Promise`). The relevant hits are
prompt text only: `stop_gates.py:51` (a nudge), `run_context_summary.md:27-28` and `packages/agent-runtime/resources/prompts/consolidator_archive.md:22`
("follow-ups or reports promised to the owner": both are compaction/archive prompts that keep promises only inside a model-written summary),
`packages/agent-runtime/resources/system/lonora.md:127` ("Use actual watches, schedules or task waits for future work; do not promise to remain awake by thinking continuously."),
plus `uncertain_outcome.py:20` (a message index) and `task_wait_settlement.py:33` (a comment). Second search: the table list in `packages/db/src/lonora_db/schema.py`
(`grep -n "class .*Row"`) has no offer/request/open-item table.
SCRIPTED run B (`runs/p9-16-principles.out`, section 11.3): the model's next-turn context held the system blocks,
the routing frame with `live_agent_state` (`tasks: []`, `watch_count: 0`), the history and the historical-evidence
section, and none of the words "open request", "pending offer" or "unfinished request" (reproduced by the checker on database 13,
`chk916/principles.out` section 11.3). Also missing: any automatic retry of a failed owner turn whose error is not transient (the
transient case is retried, table above), and any rule that a "yes" answers the last offer (principle 4, not mine).

### (iii) Where the change attaches (no rewrite)
1. **Read side, smallest step.** `agent_live_state` (`packages/db/src/lonora_db/agent_state.py:222`) is already serialised into every turn and
   refreshed by `refresh_routing_context` (`team.py:114`). Add an `open_items` list there (open question cards:
   `input_requests` of the thread's waiting run; the agent's active Tasks including those whose description holds a
   standing instruction; pending approval/owner cards). Current behaviour: it lists tasks as title/status and counts
   watches. Correction (checker): it lists tasks with id/title/status/phase/waiting_reason and carries up to six summaries of
   enabled watches, not only a count (`packages/db/src/lonora_db/agent_state.py:339-354`, `:648`). Extension: item kind, one-line text, age, id. Today the standing Task «إدارة حساب التداول», whose description says «Do not ask for each order»
   (trace Part 1, Q5), reaches a conversation run only as title and status; its description is left out on purpose (`packages/db/src/lonora_db/agent_state.py:267`).
2. **Write side.** `final_answer` (`loop_outcomes.py:155-184`) is the single place where an owner-started chat run
   ends; `record_request_start` (`uncertain_outcome.py:40-48`) already stores `owner_started` and the index where the
   owner's request begins in the run state, so "this reply ended request #N" is derivable there. A durable item needs
   a store: a new small table keyed by thread (not `ThreadRow.options`, which holds owner options and would mix
   runtime data into them). The item should be declared by the model in structure, not found by keyword: the reply path already
   splits a trailing `<suggested_reply>` tag out of the text (`packages/agent-runtime/src/lonora_agent/model_runtime.py:195-201`,
   `packages/agent-runtime/src/lonora_agent/suggested_reply.py:31-43`); a sibling structured tag or a small tool would follow the
   same pattern and respects the written rule against keyword routers (`docs/ui-reference/OWNER_DECISIONS.md:12`).
3. **Context side.** `build_context` (`packages/agent-runtime/src/lonora_agent/context/builder.py:55-302`) assembles optional
   server-derived blocks with `server_records` (`builder.py:50-52`, used at `:118-126` for decisions) and labelled sections
   (`builder.py:218-267`). An `open_items` block fits either; it is first-party data, never authority.
4. **Close/resume.** An item closes on a successful tool result that names it (the call ids are in the run state) or on the owner's
   cancel. A new owner message while the run is `waiting_input` already merges into the same run
   (`packages/db/src/lonora_db/messages.py:526-553`); otherwise a new run starts (`packages/db/src/lonora_db/messages.py:576-584`), whose context would carry the item.
5. **Failed turns.** `retry_run` (`run_retry.py:87-115`) is manual. Auto-resume after the model route is fixed would be a
   gateway step reusing `retry_run`'s own refusals (it refuses runs with any financial effect, `run_retry.py:93-103`).

### (iv) Cost
S for the read-only `open_items` block (Tasks, question cards, cards derive from rows that exist). M for a durable
offer/request record with writer, close rules and context. L for auto-resume without an owner message.

### (v) Conflicts / flags
- No conflict with the money rules if an item is never an instruction that can be executed: a resumed item still goes
  through the signed grant or an approval card at the one executor.
- `docs/ui-reference/OWNER_DECISIONS.md:12` (no keyword router, no separate classifier call): detect offers by
  model-declared structure, not by matching «إذا تريد».
- The item store is runtime state, not a journal: it must not be confused with the append-only trading journal (`TradingJournalRow`,
  `packages/db/src/lonora_db/schema.py:676`). A fresh table is allowed (`OWNER_DECISIONS.md:17`: no migration of legacy data needed).

### (vi) Safe now vs decision
Safe now: the read-only `open_items` block. Needs the owner: (a) whether a failed owner turn is retried automatically once
the cause is fixed (today only the button; a retry replays model cost and is refused after a financial effect); (b) how long
an unresolved item lives before it is dropped.

---

## P10. Owner scope

The personal assistant acts on all the owner's resources (watches and Tasks of any agent) via delegation or owner authority,
within server permissions.

### Trace
Not exercised: one agent only (trace Part 1, Q6). It stays a real limit once a second agent exists (below). The lead's
point 10 (Task cancelled at 10:51:04 from the interface while watch `3789e892` still points at it and is polled) is a lifecycle
defect outside this principle.

### (i) What exists today
**What "personal assistant" means in code**
- `AgentRow.role == "personal"` (`packages/db/src/lonora_db/schema.py:160`; checks at `:165-197`: exactly one per owner via
  `ln_one_personal_agent`, never bound to an account or symbol). `ensure_personal_agent` `packages/db/src/lonora_db/personal_agent.py:16`
  (also seeds default supervision, `:40`), `discover_specialists` `:46`, `account_event_agent` `:68`.
- Account-wide visibility: `account_wide_scope` `packages/db/src/lonora_db/agent_binding.py:39`; the prompt scope text states
  "Owner-wide visibility is NOT autonomous execution authority" (`agent_binding.py:147-158`).
- Native tool profile `market` + `coordination` (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:43-45`). That is why `agent_inspect` and
  `peer_send` are native (trace Part 1) while `agent_control` is not (its `Tool(...)` has no `eager=` argument, `packages/tools/src/lonora_tools/supervision.py:609-623`,
  unlike `agent_inspect`'s `eager=eager_for("coordination")` at `:607`).
- Permission default `supervised` ("Ask me") (`packages/db/src/lonora_db/agent_permissions.py:43-44`).
- Spec: `docs/lonora-specs/05_PERSONAL_AGENT_AND_ACCOUNT_WIDE_TRADING_CONTEXT.md:20` ("not a manager hierarchy or second trading engine"),
  `:40` (visibility is not execution). Test: `tests/check_personal_agent.py:154` asserts the same.
- Flags in code: there is no "owner scope" flag; the only knobs are `role`, `scope_mode` and the supervision grants below.

**Delegation that already exists: supervision grants**
- The Personal Agent supervises every other agent by default: `grant_default` `packages/db/src/lonora_db/supervision.py:230` (called at
  `packages/db/src/lonora_db/agents.py:91`) and `seed_personal_grants` `packages/db/src/lonora_db/supervision.py:238`.
- `control_work` `packages/db/src/lonora_db/supervision.py:629`: a supervisor, or the Personal Agent on the owner's message (`packages/db/src/lonora_db/supervision.py:658-663`), can **pause or
  resume** another agent's whole agent, Task, routine or watch. `WorkAction = Literal["pause", "resume"]` (`packages/db/src/lonora_db/supervision.py:528`);
  the tool contract has no cancel (`packages/contracts/src/lonora_contracts/supervision.py:16`, `agent_control`'s description
  `packages/tools/src/lonora_tools/supervision.py:611-619`).
- Reads of another agent's work: `agent_inspect` section `work` (`packages/tools/src/lonora_tools/supervision.py:165-232`, ten items per page, per agent id).
- `routine_toggle` has a supervised branch (`packages/tools/src/lonora_tools/routine.py:58-60`, `:80-102`).
- The owner's own interface cancels anything: owner API `apps/api/src/lonora_api/routes/watches.py:41` and
  `apps/api/src/lonora_api/routes/tasks.py:59` call `control_watch(...)`/`control_task(...)` without an `agent_id`
  (the owner path, `packages/db/src/lonora_db/market_watches.py:163-167`, `packages/db/src/lonora_db/tasks.py:413`).

**Today's `agent_id == context.agent_id` filters that limit a tool to its own agent** (grep:
`grep -nE "agent_id *(==|!=) *context\.agent_id|agent_id=context\.agent_id" packages/tools/src/lonora_tools/*.py`, then each hit read):
| Tool surface | Line | Effect |
|---|---|---|
| `watch_list` | `packages/tools/src/lonora_tools/market_watch.py:153-155` (repository `list` filter `packages/db/src/lonora_db/transactions.py:71`) | lists only own watches |
| `watch_cancel` / `watch_pause` / `watch_resume` | `packages/tools/src/lonora_tools/market_watch.py:180` → `steered_watch` `packages/db/src/lonora_db/market_watches.py:123` | another agent's watch reads as `market_watches_not_found` |
| `watch_update` | `packages/tools/src/lonora_tools/market_watch.py:209`, `:215` | same |
| `watch_create` dedupe | `packages/tools/src/lonora_tools/market_watch.py:45`, `:77` | duplicates are per agent |
| `routine_list` | `packages/tools/src/lonora_tools/routine.py:46` | own only |
| `task_inspect` list / by id | `packages/tools/src/lonora_tools/tasks.py:51`, `:57-58` | `task_agent_mismatch` |
| `task_control` | `packages/tools/src/lonora_tools/tasks.py:69` → `packages/db/src/lonora_db/tasks.py:411-412` | `task_agent_mismatch` |
| `goal_list`, `goal_read`, goal step | `packages/tools/src/lonora_tools/trading_goal.py:93`, `:129`, `:158` | own agent and thread |
| `market_opportunity_list` | `packages/tools/src/lonora_tools/opportunity.py:108` | own |
| `owner_attention_list` | `packages/tools/src/lonora_tools/incoming_call.py:108` | own |
| collaboration host | `packages/tools/src/lonora_tools/collaboration.py:57`, `:91` | host agent |
| artifacts / tool receipts | `packages/tools/src/lonora_tools/artifacts.py:69`, `:139`, `:207`; `packages/tools/src/lonora_tools/chart_snapshot.py:77`; `packages/tools/src/lonora_tools/tool_results.py:84` | own and same thread |
| trade approvals | `packages/tools/src/lonora_tools/trade.py:126`, `:355-360` | approvals belong to the agent that proposed them (money; keep) |
| run identity checks (not resource scope) | `packages/tools/src/lonora_tools/agents.py:232`, `packages/tools/src/lonora_tools/models.py:239`, `packages/tools/src/lonora_tools/owner_actions.py:207` | `run.agent_id` must equal the caller |

(Checker: the same grep returns about 70 lines; the ones not in the table set `agent_id=context.agent_id` when a row is written or routed (e.g. `packages/tools/src/lonora_tools/market_watch.py:133`, `:228`, `trade.py:221`, `chart_state.py:190`), or are the second own-agent check of `routine_toggle` after its supervised branch (`packages/tools/src/lonora_tools/routine.py:62`). None of them is a further read/cancel filter.)

**SCRIPTED reproduction** (agent T creates a watch, a routine and a continuous Task; the Personal Agent P then probes them with
bridged calls; `runs/p9-16-principles.out` sections 10.1 to 10.5):
- `watch_list`, `routine_list`, `task_inspect` return empty lists for P.
- `watch_cancel` and `watch_update` on T's watch: `{"ok":false,"code":"market_watches_not_found"}`.
- `task_inspect(task_id)` and `task_control(cancel)` on T's Task: `{"ok":false,"code":"task_agent_mismatch"}`.
- `routine_toggle(enabled=false)` on T's routine: `ok:true`, routine disabled (supervised branch).
- `agent_control` pause on T's watch and T's Task: `ok:true`; stored `watch.state.code = watch_paused`, `task.status = paused`.
- Owner API cancel of T's watch: `enabled:false`, code `watch_cancelled`.
So: pause works across agents, read works one agent at a time, **cancel and update do not exist across agents**, and
there is no owner-wide list for an agent.

### (ii) What is missing
An owner-wide list for agents (all watches, routines, Tasks, goals of every agent in one call); a cancel/update across agents on the owner's
message; a per-agent id is needed even for reads. Searched: the filter grep above, the `WorkAction` literal, and the `agent_control`
contract. The owner's own path (`agent_id=None`) is the only owner-wide path and agents cannot call it.

### (iii) Where the change attaches
- `control_work` (`packages/db/src/lonora_db/supervision.py:629-749`) already checks supervision or "owner message through Lonora"
  (`:658-663`), hold rules, and writes an intervention record (`:736-748`). Extension: allow `cancel` for watch/routine/task in `WorkAction`
  (`:528`), `_apply` (`:590-626`) and `AgentControlInput.action` (`packages/contracts/src/lonora_contracts/supervision.py:16`), leaving the hold semantics as they are
  (`control_watch` already says the agent "may still cancel it, which only narrows", `packages/db/src/lonora_db/market_watches.py:155-157`).
- `watch_cancel`/`watch_update`/`task_control` (`packages/tools/src/lonora_tools/market_watch.py:172-232`, `packages/tools/src/lonora_tools/tasks.py:62-75`): when the watch/Task belongs to another agent, route through
  `control_work` the way `routine_toggle` already does (`packages/tools/src/lonora_tools/routine.py:58-60` → `supervised_toggle` `:80-102`). One shared helper, no new tool.
- An owner-wide read: `agent_inspect` (`packages/tools/src/lonora_tools/supervision.py:408-426`) takes one agent id; the same SQL (`_work`, `:165-232`) with `agent.id` replaced
  by the owner's agent ids gives the list. For the model's view, `agent_live_state` (`packages/db/src/lonora_db/agent_state.py:222`) counts only its own watches (`:346`).
- The "owner message" proof is `owner_message_id` (`packages/tools/src/lonora_tools/restrictions.py:97-116`): it is `None` once the run has read
  third-party content, which is the right condition for the sensitive branch.
- Tool visibility is a separate fix (other session): `agent_control` and `watch_cancel` are in no eager profile (registry check by the checker: `eager` is empty for `watch_list`, `watch_cancel`, `agent_control`, `task_inspect`, `routine_list`, `market_symbols`, `trade_close_positions`), so they are not native by default (trace Part 1). (Checker addition) A long-tail tool becomes native in this agent's later runs after one **successful** use: `remember_use` (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:151-181`) records it with `record_tool_use` (`packages/db/src/lonora_db/tool_usage.py:40`) and the next run's exposure promotes it. In the checker's rerun on database 13 (fresh personal agent), `watch_list`, `routine_list`, `routine_toggle`, `task_inspect`, `goal_list` and `agent_control` were absent from run 10.2's native list and present in the next runs (12.1, 11.2) after P used them successfully; `watch_cancel` (which failed) was not promoted (`chk916/principles.out`). In production no such tool was ever called, so nothing was promoted.

### (iv) Cost
M: one shared helper plus one new action, the owner-wide read, tests.

### (v) Conflicts / flags
- Money rules: cancel only narrows. A Task that is the only closer of an open position is the exception to flag: `require_task_authority`
  refuses every trade from a run bound to a paused or cancelled Task (`packages/trading/src/lonora_trading/execution.py:129-141`), so cancelling
  a management Task removes its automatic exit. The owner's manual close path has no lease and is not affected. Exits stay admissible for the
  owner and for other runs. The confirmation to the owner must say that no automatic close remains (money-safety rule "exits always admissible"
  is about admissibility, not about keeping a manager alive; still, a flag).
- Cancelling the account-management Task does not revoke the signed grant. The link runs the other way: `stop_management_task` is called when a grant is replaced or revoked
  (`packages/auth/src/lonora_auth/account_authority.py:126`, `packages/db/src/lonora_db/agent_permissions.py:229`, `packages/db/src/lonora_db/account_authority.py:210`,
  `apps/api/src/lonora_api/routes/device_authority.py:95`); I found no call from `control_task` (`packages/db/src/lonora_db/tasks.py:397`) to any revoke function
  (`grep -rn stop_management_task` over `packages` and `apps`). Chat «ألغِ المهمة» must not be read as revoking the mandate.
- An agent must keep using the agent path (`agent_id` set) so `refuse_held` still stops it resuming an owner's pause
  (`market_watches.py:168-171`); it must never call the owner path (`agent_id=None`).
- `docs/lonora-specs/05_PERSONAL_AGENT_AND_ACCOUNT_WIDE_TRADING_CONTEXT.md:20` says the Personal Agent is not a manager hierarchy; supervision already contradicts "no hierarchy" for pause/resume,
  so cancel on the owner's message is a small step inside an existing design.

### (vi) Safe now vs decision
Safe now: owner-wide read; cancel/update of another agent's watch or routine on the owner's own message. Needs the owner: cancelling a Task that holds
money standing (which exits remain), and whether Lonora may cancel without the owner's message (today pause needs a grant and no message; keep that).

---

## P11. Live reads for status questions

### Trace
- Run `c22a6810` ([28] «شو وضعه») made no tool call and answered from the earlier number «النتيجة وقت آخر تحقق كانت -0.24 USD»
  (trace Part 1 digest line "09:48:52").
- Runs `8114abdd`, `a8be01f0`, `7e7da121`, `57dcaeb0` answered "monitoring/at last check" with no tool call; `01c07781`, `eb67419d`, `6e4aa88f`,
  `691adb1f` did read `account_read` (+`market_quote`) first (trace Part 1 digest). The model sometimes reads live, nothing makes it.
- Code largely settles the earlier "TRACE MUST CONFIRM" on run `c22a6810`: `build_context` always calls `recent_tool_evidence` (`packages/agent-runtime/src/lonora_agent/context/builder.py:214-217`), which reads the last four finished runs of the thread (`run_evidence.py:25`, `:207-224`); before `c22a6810` these were `65e8b682` (`trade_execute`, an effect tool, always kept: `run_evidence.py:49`, `:156-159`), `00f7b6bc` (`account_read`, `market_quote`, `market_instrument`), `e7ca6fb6` and `9d557f9e` (`chart_snapshot`) (trace Part 1 digest), so the section was built non-empty. UNSURE: whether admission shed it (priority 55, `builder.py:244-250`) is not in the trace. The figure −0.24 USD was in any case also in the assistant message [26] in the history (trace Part 3 seq 24). Reproduced by the checker: SCRIPTED section 11.3 shows the section present for a second run of the same thread.

### (i) What exists today
**Live (read at call time)**: `account_read` (`packages/tools/src/lonora_tools/account.py:69-73` → `packages/adapters/src/lonora_adapters/brokers/metaapi.py:781-783` and `:805-807`, broker RPC);
`market_quote` (`metaapi.py:676-701`: the synchronized stream price if its age is within 30 s or the market is quiet, else RPC; the comment at `:690` notes
RPC costs quota); `market_candles` (`metaapi.py:703-720`); `market_snapshot` (`packages/tools/src/lonora_tools/market_analysis.py:136-181`: quote plus bars);
`market_instrument`; `chart_snapshot` ("a fresh broker-backed snapshot", `packages/agent-runtime/resources/constitution/tool-policy.md:13`).
**Cached/durable**: `list_accounts` (database rows; "a saved connection is not proof of live broker connectivity", `packages/tools/src/lonora_tools/account.py:63-65`), `account_activity`
(stored events, `packages/tools/src/lonora_tools/account.py:80-97`), `trade_record_*` (journal), `watch_list`/`agent_inspect`/`task_inspect`/`runtime_status` (database rows; watch
summary `packages/db/src/lonora_db/agent_state.py:36`), `market_decision_*`, memory and session search.
**Staleness markers in results**: quote `observed_at` and `source` (SCRIPTED 11.4: keys `observed_at`, `source`); account `account.observed_at` (SCRIPTED 11.4);
`market_snapshot`: `data_freshness` (`packages/market/src/lonora_market/snapshot.py:355`), `quote.age_seconds` (`:307`), per-timeframe `freshness` (`:162`)
(SCRIPTED 11.6 shows `data_freshness` and `quote.age_seconds: 4.4`; `data_freshness` was `unavailable` there only because the simulation broker has no candles, the quote itself was `healthy`); `list_accounts.broker_identity.observed_at` (trace Part 4, `1ae9a14c` #13); watch health `observed_at`
and `last_value` (trace Part 4, `ddae66ad` #70); the historical-evidence section stamps `observed_at` and `time_basis` (`packages/agent-runtime/src/lonora_agent/context/run_evidence.py:170-171`)
under a note that says "not live market or broker truth … Re-read before acting or before claiming current state" (`run_evidence.py:73-79`);
`agent_inspect` carries "Broker and market state need fresh reads" (`packages/tools/src/lonora_tools/supervision.py:95-98`).
**Policy lines**: `packages/agent-runtime/resources/system/lonora.md:76-77` ("Current market or account claims require actual returned evidence, not memory…"; "Inspect the relevant
account, symbol, observation timestamp, timeframe, freshness and source"); `packages/agent-runtime/src/lonora_agent/context/team.py:91` ("Use task_inspect or runtime_status for fresh details before claiming current progress").
**A registry flag for status tools already exists**: `Tool.poller` ("status checks legitimately repeated while monitoring", `packages/tools/src/lonora_tools/base.py:80-82`), set on `account_read`, `market_quote`, `watch_list`,
`task_inspect`, `runtime_status`, `trade_record_read`, `account_activity` and others; today the runtime uses it only inside the guardrails (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:233`, `:237`, `:375-377`) and in a registry consistency check (`packages/tools/src/lonora_tools/registry.py:149`).
**(Checker addition) Server-derived state already in every turn**: the routing frame carries `live_agent_state` with up to six summaries of the agent's own enabled watches (symbol, condition, level; `packages/db/src/lonora_db/agent_state.py:36-53`, `:339-354`, `:648`). A claim such as «أراقب **XAUUSDm**» ([57], run `7e7da121`) could be checked against that list structurally: trace Part 1 Q4 shows no XAUUSDm watch ever existed. UNSURE: the exact frame content at 09:55 is not in the trace (execution_state cut). Note also that the frame's own advice names `task_inspect` and `runtime_status` (`team.py:91`), neither of which is among the 23 native tools of this conversation (trace Part 1 baseline).

### (ii) What is missing
No consistent `live`/`cached` marker; no staleness limit applied by the runtime; nothing checks that a reply about position, balance, price or watch state followed a live read in the same
run. The historical-evidence block carries result previews (up to 600 characters, `run_evidence.py:29`) of `account_read`/`market_quote` into later runs (`run_evidence.py:114-117`, `:181`), which is a number the model can quote. Searched:
`grep -rn "poller" packages` (only `base.py` and `tool_guardrails.py` consume it); `grep -rn "observed_at" packages/agent-runtime/src`: the runtime records each call's observation time in the run state (`tool_observed_at`, `packages/agent-runtime/src/lonora_agent/context_engine.py:74`, `:180-187`) and shows it only where a result is no longer fresh in the transcript: pruned results (`context_engine.py:324-325`), compaction transcripts (`:574`) and the evidence block (`run_evidence.py:170`). A fresh result reaches the model with the tool's own fields only. (Checker correction: the earlier text said "evidence block only".)

### (iii) Where the change attaches
- **Result markers**: `dispatch_call` (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:22`, success merge at `:109`) is the single place every result passes before the model; add `as_of`
  and a `source: live|stored` from a registry flag next to `poller` (`packages/tools/src/lonora_tools/base.py:82`). Current behaviour: success is `{"ok": True, **result}`. S.
- **Historical evidence**: `_entries` (`run_evidence.py:120-191`) builds the preview; for live-only tools (`account_read`, `market_quote`, position-bearing results) keep identity and time but drop the value
  preview, like `SKIPPED_TOOLS` does for discovery tools (`run_evidence.py:32-48`). Limitation: the number also sits in the earlier assistant message in the history, so this lowers the temptation only. S.
- **Structural gate**: `final_answer` (`loop_outcomes.py:155`) with the pieces PR #42 left: `owner_started` and the request-start index in the run state (`uncertain_outcome.py:40-48`) and the tool calls of this request. A bounded
  "read first" round (same pattern as the stop-gate nudge, `loop_outcomes.py:170-174`, counter pattern `stop_gates.py:108-129`) when the owner-started run ended with zero calls to live-read tools and
  the reply is a status answer. The difficulty is deciding "status answer" without reading words (`uncertain_outcome.py:3` is a design rule of PR #42; `OWNER_DECISIONS.md:12`): a model-declared flag or a
  tool-based rule (a position or watch exists in `agent_live_state`) are the structural options. M.
- **Eval**: `scripts/genui_eval/score.py:374` (`observe`) and `:565` (`judge`) score recorded replies against recorded tool calls (`called_tools` `:240`); a check "status case calls a live tool" is a new
  per-case check there, with a case in `tests/fixtures/genui_decision/cases.jsonl` and a bank answer in `scripts/genui_eval/bank.py`.

### (iv) Cost
S for markers and the evidence preview; M for the structural gate.

### (v) Conflicts / flags
No money-rule conflict (reads only). Cost flag: more broker RPC (`metaapi.py:690`); the stream path serves a price within 30 s without RPC. Design flag: `uncertain_outcome.py:3` "no wording … is read".

### (vi) Safe now vs decision
Safe now: markers and evidence preview. The gate is the brief's own principle; the only open choice is the maximum acceptable age (30 s is what the broker stream tolerates, `metaapi.py:687`).

---

## P12. Server-side reply guard

Blocks registered codes, tool names, internal states and broken markdown, and rephrases in the owner's language.

### Trace
Trace Part 4 finding 9: no guard or rewrite record on `ddae66ad`, `e343c96a`, `fb1d4b5a`. Replies that carried internal terms: [10] (`symbol_not_found`, `broker_account_not_found`), [59]/[65] (`waiting`, `owner_attention`, `routines`, `goals`),
[75]/[77] (`watch_cancel`). Why nothing fired: no check that can block or rewrite a reply looks for codes, tool names or internal states (section 1 and `trace-guards.md`, which I re-checked at the lines below). The reply text is scanned only by privacy redaction and by the streaming `EFFECT_CLAIM` hold, neither of which blocks (below). [73], [75] and [77] ran on 9f5b1da (TIMELINE_CORRECTION), so for those the failure on main is observed, not inferred.

### (i) What exists today
- **Final-reply path in order** (CODE): `model_turn` financial-truth gates `packages/agent-runtime/src/lonora_agent/model_runtime.py:225-238` → visual projector `:243` → privacy redaction `:246` (credentials, private paths, `<lonora_*>`/`<skill_runtime>` tags and UUIDs only:
  `packages/core/src/lonora_core/public_reply.py:10-25`) → published as deltas `model_runtime.py:288-291`; then in the loop `final_answer` `packages/agent-runtime/src/lonora_agent/loop_outcomes.py:155-184` (task stop gate `:170`, uncertain-outcome line `:179-183`) → stored.
- **Tool-name plumbing exists and is switched off.** `public_reply_violation(text, tool_names, …)` accepts a name set and deletes it: `del tool_names` with the comment "registry names are intentionally not private" (`public_reply.py:37-42`); `PublicStream`
  is built with an empty set (`packages/agent-runtime/src/lonora_agent/model_runtime.py:109`, `:163`). The stated reason: "Presentation is owned by the model's instructions, not a keyword veto on replies" (`public_reply.py:4`) and "Style is model guidance, never
  a second generation or a failed user request" (`model_runtime.py:239-241`).
- **Streaming stops on one pattern**: `EFFECT_CLAIM` (`packages/agent-runtime/src/lonora_agent/public_stream.py:11-19`, English and Arabic trading verbs such as «تم تنفيذ», «فتحت صفقة») stops incremental publication when a reply claims an effect; the full text is still published at the end. «تم الإلغاء» and «سأحذف» do not match it (`trace-guards.md` 6.3, checked against the regex).
- **A repair-round mechanism exists** for tasks (and, for empty chat replies only, `tool_loop.py:573-579`, see (iii)): a continuing verdict appends a `runtime_notice` and returns `None`, so the loop calls the model again (`loop_outcomes.py:170-174`, `append_notice` `packages/agent-runtime/src/lonora_agent/runtime_notices.py:67-81`), bounded by a counter in the run state
  (`stop_gates.py:41`, `:108-129`). A chat run never reaches it (`stop_gates.py:153-155`, `:180-181`).
- **Registries usable as blocklists**:
  - Tool names: `ToolRegistry.names(scope)` `packages/tools/src/lonora_tools/registry.py:402` (126 names at 9f5b1da, counted with `load_tools()`); the model's own inventory is built from it (`packages/tools/src/lonora_tools/registry.py:406`), and `tool_loop.py:493` already passes it to `model_turn` as `policy_tools`.
  - Error codes: **no runtime registry.** 723 distinct string literals `LonoraError("…")` by grep (`grep -rhoE 'LonoraError\(\s*"[a-z0-9_]+"' --include=*.py packages apps | sort -u | wc -l` = 723), plus codes made elsewhere
    (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:73`, `:95`, `:121-127`, `:134-137`; the sets in `packages/agent-runtime/src/lonora_agent/environment.py:38-88`; `packages/core/src/lonora_core/runtime_failure.py:10`). A run-local list is more exact: `environment.observe` already records each failed call's `code`
    in the run state (`packages/agent-runtime/src/lonora_agent/environment.py:134-179`, `routes` and `recent`; bounded: `routes` keeps 32 entries, `recent` the last 12, `:193-201`).
  - Internal states: Literal types and constants, e.g. `TaskStatus` `packages/contracts/src/lonora_contracts/tasks.py:10`, `OWNER_ATTENTION` `packages/db/src/lonora_db/tasks.py:20`, `waiting_reason` is a free string (`packages/contracts/src/lonora_contracts/tasks.py:71`), watch `evaluation_status` values
    (`packages/market/src/lonora_market/watch_health.py:23`). No single list.
- **Policy (prompt only)**: `packages/agent-runtime/resources/system/lonora.md:52` ("Do not quote an internal diagnostic verbatim…"), `:61` ("Translate practical meaning rather than copying machine wording into the reply."), `:44` (capability names are allowed when the owner asks about capabilities).
- **Markdown**: no normaliser anywhere on the server reply path (grep for `\*\*`/markdown handling in `packages/agent-runtime/src`, `packages/core/src`, `messages.py`, `runs.py`: none); the client renders with `react-markdown` + `remark-gfm` (`packages/chat-ui/src/markdown.web.tsx:3-4`, `:21`).
- **SCRIPTED** (`runs/p9-16-principles.out` §12.1-12.2): a reply containing `symbol_not_found`, `broker_account_not_found`, `waiting`, `owner_attention`, `routines`, `watch_cancel` and `** text**`-style bold is stored byte-for-byte identical; `model_turns: 1`; no `public_rewrite` or `privacy_redacted` key.

### (ii) What is missing
A check of reply text against names/codes/states; a rephrase round for chat runs; a per-run list of codes the model has seen; a script/language check; markdown normalisation. Searched by reading every step of the final-reply path above and `grep -rn "public_reply_violation\|redact_private_reply" packages`.

### (iii) Where the change attaches
- **Hook**: `final_answer` (`loop_outcomes.py:155`), after the task gate and before `append_uncertain_line` (`:179`). (Checker: a chat-run re-ask already exists one step earlier: an empty conversational reply gets the `no_answer` notice and the loop continues, `packages/agent-runtime/src/lonora_agent/tool_loop.py:573-579`, text `NO_ANSWER` `runtime_notices.py:96-99`; it is the closest precedent for a chat-run repair round, bounded only by the round budget.) It is also the owner-started final in `execute_tool_loop` (`tool_loop.py:595-611`). The limit report path needs the same call:
  `finish_turn` builds its text at `tool_loop.py:284` and appends the uncertain line at `:299`. Question and attention texts bypass `final_answer` (`question_outcome` `loop_outcomes.py:71-80`, `request_owner_attention` `:109-152`).
- **Pattern to reuse**: the stop-gate nudge: `append_notice(messages, kind, text)` (`runtime_notices.py:67`) + return `None` so the loop makes another model turn (`tool_loop.py:610-611` continues on `None`), with a bounded counter like `apply_stop_gates` (`stop_gates.py:108-129`).
  The notice text is English (policy: `OWNER_DECISIONS.md:13`); the owner never sees it. If the bound is spent, fall back to a server-composed owner-language line, as `limit_fallback`/`LINE_AR` do (`uncertain_outcome.py:36`).
- **Blocklist source**: `registry.names(scope)` (`packages/tools/src/lonora_tools/registry.py:402`) for tool names; run-local codes from the run state (`packages/agent-runtime/src/lonora_agent/environment.py:179`, `:201`); states from the Literal types above.
- **Streaming**: the draft is already published as `run.delta` before `final_answer` runs (`model_runtime.py:288-291`). To keep a leaked word from ever flashing, the same admission test that stops EFFECT_CLAIM (`public_stream.py:47-51`) must also hold publication when a blocklisted token appears
  (that is what the unused `names` argument was for). The replace-a-provisional-reply mechanism exists (`model_runtime.py:282-287`, new `turn_id`). UNSURE: how the web client shows a superseded turn when the loop continues; I did not run the client.
- **Money truth stays first**: the financial-truth gates (`model_runtime.py:225-238`) and the uncertain-outcome line (`loop_outcomes.py:179-183`) must run unchanged; the guard may only request a rewrite, never delete or replace them.
- **Eval**: a per-case check "reply has no registry token" in `scripts/genui_eval/score.py:374` (`observe`; uses the recorded reply and `registry.names`), which is deterministic.

### (iv) Cost
S for the blocklist builders; M for the `final_answer` hook with bounded repair round; M more for holding publication in `PublicStream`. Markdown normalisation is the other session's item.

### (v) Conflicts / flags
- Design tension with two written rules: `public_reply.py:4` and `:40-41` ("registry names are intentionally not private"; "not a keyword veto"), `model_runtime.py:239-241` ("never a second generation"), and `lonora.md:44` (capability names are fine when the owner asks). A guard must
  therefore pass names when the owner's latest typed message is about capabilities/technical subjects. That test cannot be keyword-based (`OWNER_DECISIONS.md:12` for UI shape; same spirit); a model-declared flag or "the owner asked" via the run's tool use are the structural options. **Flag for the owner.**
- The guard must never rewrite financial truth (see above). A server-side word substitution (replace the code by a translation) could change meaning; use a model rewrite round, not string replacement.
- No money path is touched: the guard sends nothing and calls no tool itself; a rewrite round is an ordinary model turn under the same gates.

### (vi) Safe now vs decision
Safe now: the blocklist builders and the eval check. Needs the owner: the tension above (a guard that blocks and re-asks is exactly a "second generation").

---

## P13. Answer the question asked

«شو وضع الذهب» = price, trend on each timeframe, the important levels, and the conclusion (buy / sell / wait); specifications only on request.

### Trace
Question at 09:44:01 (`1ae9a14c`). Answers: error recitation ([10]); a contract-spec dump ([14], run `10171b1c`, last tool `market_instrument` only); price and a trend summary at 09:46:09 (`af5f00b3`); the complete status with a verdict at 09:46:36 (`6f8ff964`)
after two «ياريت» (trace Part 1 digest). [18] omitted the key levels although the tool returns them.

### (i) What exists today
- `market_snapshot` (`packages/tools/src/lonora_tools/market_analysis.py:358-371`; function `:136-181`) returns in one call: quote with spread and freshness; per timeframe closed-bar trend, swing structure, range, ATR/volatility regime, RSI; **`levels`**: previous day and week
  high/low with distance in price and in daily ATR (`packages/market/src/lonora_market/snapshot.py:360-366`); `limitations`: "Labels describe measurements, not entry signals or forecasts." (`packages/market/src/lonora_market/snapshot.py:368-372`). SCRIPTED §11.6 confirms the top-level keys: `data_freshness`, `levels`, `quote`, `timeframes`, `limitations`.
- There is no verdict tool by design: "You own market interpretation and trading decisions" (`packages/agent-runtime/resources/system/lonora.md`, "Truth and evidence" section starts at `lonora.md:74`; the sentence is `lonora.md:78`); "Choose BUY, SELL or conditional entry from your analysis" (`packages/agent-runtime/resources/skills/market-analysis/SKILL.md:47`).
- Output policy lines: `packages/agent-runtime/resources/skills/market-analysis/SKILL.md:60` ("Give the finding, evidence time, decisive uncertainty and one useful next action."), `lonora.md:30` ("Start with the result…"), `:33-34` ("Give at most one specific useful next suggestion…"; "Do not end every answer with a question or a menu of possible follow-ups."), skill step 2
  ("Start with market_snapshot…", `packages/agent-runtime/resources/skills/market-analysis/SKILL.md:26`). (Checker correction) `packages/agent-runtime/resources/prompts/trading_context.md:1` ("Obtain instrument specifications and real data before analysis or execution") and `:5` are **never loaded**: `load_prompt` is called only with `group_behavior`, `suggested_reply`, `web_search_on`, `subagent_system` (`packages/agent-runtime/src/lonora_agent/context/builder.py:128-136`), `run_context_summary` (`packages/agent-runtime/src/lonora_agent/context_engine.py:91`) and `consolidator_archive` (`packages/agent-runtime/src/lonora_agent/context/compaction.py:20`); `grep -rn trading_context packages apps scripts tests` finds no reference in code; the only other readers of `resources/prompts` are `genui_v2.md`/`genui_v2_teaching_*.md` and `native_visual_response.md` (`packages/agent-runtime/src/lonora_agent/skills/visual_policy.py:37`, `:56`, `:79`). Lead `map-context.md` finding 3 says the same.
- `<lonora_answer_shape>` says a status is text (`packages/agent-runtime/resources/prompts/genui_v2_teaching_o.md:19`; `genui_v2_teaching_p.md:3`), but only when `LONORA_GENUI_V2` is set (`packages/agent-runtime/src/lonora_agent/skills/visual_policy.py:21-22`, `:76-77`; one variant at a time, default P, `:25-29`). UNSURE: whether production sets it.

### (ii) What is missing
No text says what a "status of a market" answer contains (price, per-timeframe lines, levels, verdict) or that specifications are only for sizing. (Checker correction) The earlier text blamed `trading_context.md:1` for the specification dump of `10171b1c`; that file is not loaded (above), so it cannot be the cause. Live text that points the same way: the `market_instrument` description names `market_symbols` and suffixes (`packages/tools/src/lonora_tools/market.py:100`); the run's only tool was `market_instrument` and its reply listed that tool's fields (trace Part 1 digest). UNSURE why the model stopped there; nothing in loaded policy asks for a status after a symbol is resolved.
`packages/agent-runtime/resources/skills/market-analysis/SKILL.md:60` asks for "one useful next action", which matches the offer endings. Searched: `grep -rniE "level|support|resistance|status|وضع" packages/agent-runtime/resources/skills packages/agent-runtime/resources/prompts` shows no answer-frame wording for a status question.

### (iii) Where the change attaches
`packages/agent-runtime/resources/skills/market-analysis/SKILL.md`, "Output" (`:58-66`): add the status frame in English, and say there that specifications are read when sizing or when the owner asks (not in `trading_context.md`, which is not loaded). No code change.
The manual `lonora.md` has a core part (`lonora.md:9-166`) that is always loaded and domain chapters, among them `policy:market` (`lonora.md:209`), that are chosen by recent tool calls
("selected by actual operations", `packages/agent-runtime/src/lonora_agent/skills/system_policy.py:1-5`): on the first turn of a new question only the core is certain to be present. Eval: a case «شو وضع الذهب» in `tests/fixtures/genui_decision/cases.jsonl` with a check in `score.py:374` that the reply states a price, a trend per
requested timeframe, a level and a verdict, and contains no specification fields. UNSURE: whether the market-analysis skill is in the context of a run that has not loaded it with `skill_view`; the reliable place is the core manual (`lonora.md:9-166`), which is always loaded.

### (iv) Cost
S.

### (v) Conflicts / flags
None with money rules ("An owner request for analysis is not permission to trade", `lonora.md:24`): the verdict is analysis; it must not read as an instruction that trades. Prompt text must be English (`OWNER_DECISIONS.md:13`).

### (vi) Safe now vs decision
Safe now. Measure with the eval before relying on it.

---

## P14. Remember what was learned

A per-account symbol map in durable storage (XAUUSD ⇒ XAUUSDm).

### Trace
Run `1ae9a14c` sent `XAUUSD` without a catalog read (`market_symbols` was not native; trace Part 1 baseline list); it failed twice. After the owner typed «XAUUSDM» the model used `XAUUSDm` correctly in the same thread (run `10171b1c`) but **no `memory_write` or any other write happened in the whole conversation** (trace Part 2: the only memory call is `memory_read` at 09:37:56). Later runs used `XAUUSDm` only because the transcript carried it. A new thread, a new agent or a context compaction would repeat the failure.

### (i) What exists today
- Resolution is case-only: `catalog_symbol` `packages/tools/src/lonora_tools/symbols.py:6-15`, `canonical_broker_symbol` `:18-35`. Callers: `packages/tools/src/lonora_tools/market.py:47`, `:58`, `:65`, `:78`; `market_analysis.py:140`; `packages/tools/src/lonora_tools/trade.py:632-635` (before the operation id is hashed);
  `restriction_symbol` `symbols.py:38-56`.
- The catalog is not stored: `broker.symbols()` comes from the synchronized terminal specifications or an RPC (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:443-459`).
- Written policy forbids silent alias handling. Live (loaded) lines: "Preserve broker symbols exactly, including case and suffix." (core, `packages/agent-runtime/resources/system/lonora.md:60`) and "Never strip suffixes, substitute an exchange feed or assume one broker's instrument exists at another." (market chapter, `lonora.md:224`). Not seen by the model: the code comment "Exact symbols are intentional. No hidden aliases or suffix stripping." (`packages/tools/src/lonora_tools/trading_decision.py:79`) and "Gold may have broker suffixes … never guess or strip them." (`packages/agent-runtime/resources/prompts/trading_context.md:5`, a file no code loads; see P13).
- **Durable places that could hold a map**:
  - `BrokerSessionRow.state` (`packages/db/src/lonora_db/schema.py:767`; the state JSON is on `ResourceRow`, `:663`): per-account facts are already kept there without bumping the connection version: `market_health` (`packages/market/src/lonora_market/health.py:250-259`) and `broker_identity` (`packages/adapters/src/lonora_adapters/brokers/base.py:84`).
    Version matters: the executor refuses a send if the connection version changed (`packages/trading/src/lonora_trading/execution.py:198-202`).
  - `MemoryRow` per agent (`packages/db/src/lonora_db/schema.py:457`): `MEMORY.md` via `memory_write` (`packages/tools/src/lonora_tools/memory.py:276-287`); the context labels it "untrusted … does not establish current broker state" (`packages/agent-runtime/src/lonora_agent/context/memory.py:23-26`). Free text, per agent, not machine-readable by the resolver.
  - `SemanticMemoryRow` (`packages/db/src/lonora_db/schema.py:811`): fuzzy retrieval; wrong tool for an exact map.
  - `SettingRow` (`packages/db/src/lonora_db/schema.py:548`): key to JSON, owner-level.
  - Precedent for a runtime-written durable memory: `AgentToolUsageRow` (`packages/db/src/lonora_db/schema.py:442`), `record_tool_use` (`packages/db/src/lonora_db/tool_usage.py:40`), called best-effort after a successful call (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:151-181`).
  - `MarketSnapshotRow` (`packages/db/src/lonora_db/schema.py:815`) is keyed by (owner, connection, symbol, timeframe) and stores `connection_version`: an analysis cache, not a map, but it shows the key shape.

### (ii) What is missing
A stored map and a write on successful resolution. Searched: `grep -rniE "symbol_map|symbol_alias|alias" --include=*.py packages apps scripts` restricted to symbol/instrument hits: only the two policy mentions (`packages/tools/src/lonora_tools/market.py:100`, `packages/tools/src/lonora_tools/trading_decision.py:79`).

### (iii) Where the change attaches (storage and hooks only; the resolver is another session's work)
- Read: the first step of `canonical_broker_symbol` (`symbols.py:18`) would consult the stored map for (connection, requested name) and then confirm the target is still in the live catalog (`broker.symbols()`); an entry whose target vanished is dropped and the resolver continues. That keeps a stale entry fail-closed.
- Write: after a successful resolution that was not an exact match, in the same helper or its callers, which have a `ToolContext` (`packages/tools/src/lonora_tools/market.py:45-65`, `market_analysis.py:136`, `trade.py:621`). Best-effort, never changes the call's outcome (as `remember_use` does).
- Storage choice: `BrokerSessionRow.state["symbol_aliases"]` follows the `market_health` precedent with no version bump; a small table (owner, connection, requested, broker_symbol, learned_at, connection_version) is the alternative if the map must be listed and edited by the owner. Keep `connection_version` so a reconnected or re-pointed account drops the map.
- The model's own `memory_write` stays for facts it learns (`MEMORY.md`), but the resolver must not depend on it.

### (iv) Cost
M.

### (v) Conflicts / flags
- Policy text above conflicts with any learned alias; the same change must rewrite the live lines `lonora.md:60` and `:224` (and, for consistency, the comment at `packages/tools/src/lonora_tools/trading_decision.py:79` and the dead `trading_context.md:5`). The owner's brief (section 4) already asks for the resolver and learned suffixes.
- Money: the resolved name is the one that enters `TradeRequest` (`trade.py:634`) and is hashed into the operation id (`:635`); the executor then preflights against the broker (`execution.py:182`) and checks the fixed-agent binding (`execution.py:88-92`, `packages/db/src/lonora_db/agent_binding.py:67`). A map only supplies a candidate name; it must never skip those checks.
  Owner restrictions match the stored symbol exactly (`symbols.py:38-56`); applying the same map when a restriction is created strengthens it (today an unknown spelling fails with `symbol_not_found`).
- Wrong map entry risk: an entry learned from one broker's catalog must not apply to another connection (key by connection).

### (vi) Safe now vs decision
Storage and the write/read hooks are safe. Updating the two policy lines is part of the same change and follows the owner's brief.

---

## P15. Always the owner's language

### Trace
`ln_owner_profile.reply_language` is empty (trace Part 1, Q6). Voice notes [48] and [50] were transcribed as Turkish («ımuz lazım birasta», «Bu korkuluklar nasıl hakkında») and run `11f8603e` answered in Turkish and offered to continue in Turkish (trace Part 3, Part 1 digest). Run `26cb3997` answered the first in Arabic («لم أفهم… اكتبها بالعربية»).

### (i) What exists today
- Model instruction: `packages/agent-runtime/resources/constitution/identity.md:1` ("Respond in the user language"); `packages/agent-runtime/resources/system/lonora.md:58` ("Reply in the owner profile's reply_language, else the language of the owner's latest message, unless asked otherwise.") and `:59` ("An English background instruction, machine result, technical symbol, or confirmation label does not change that language."; a voice transcript is not among the exceptions); the context line
  `"reply_language": preferences["reply_language"] or "latest_owner_message"` (`packages/agent-runtime/src/lonora_agent/context/memory.py:131`; note text `packages/agent-runtime/src/lonora_agent/context/memory.py:27-34`); cards: "in the language of the owner's latest message" (`packages/agent-runtime/resources/prompts/genui_v2.md:8`).
- Stored preference: `OwnerProfileRow.reply_language` (`packages/db/src/lonora_db/schema.py:483`), allowed values `ar`, `en` or null (`packages/db/src/lonora_db/schema.py:473-476`); set by the owner form (`apps/web/src/shell/settings/OwnerPage.tsx:130`, `apps/mobile/components/incoming-call-settings.tsx:71`) or by the `owner_preferences_update` tool (`packages/tools/src/lonora_tools/memory.py:158`, `:290`).
- Server-composed text uses two different deciders:
  - `prefers_arabic` (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:84-93`): scans owner messages from the newest; the first with an Arabic letter gives Arabic, the first with ≥ 8 Latin letters and a space gives not Arabic; default Arabic. Used by the uncertain-outcome line (`uncertain_outcome.py:118`), the attention notice (`loop_outcomes.py:125`) and the limit fallback (`tool_loop.py:284`).
  - `conversation_locale` (`packages/db/src/lonora_db/conversation_locale.py:13-35`): the profile value first, else the last 16 user messages from the newest (first Arabic letter gives `ar`, first message with ≥ 8 Latin letters and a space gives `en`), else a stored locale setting, else `ar`. Used when the mandate Task is created (`packages/auth/src/lonora_auth/account_authority.py:135-142`).
  - SCRIPTED §15.1: `prefers_arabic` returns **False** for both Turkish transcripts, also when an Arabic message precedes them. `runs/p9-16-locale-probe.out`: on the same thread with the profile row hidden (the shared test owner's profile is `ar`, set by another session, which is why §15.2 printed `ar`; that value comes from the profile branch `conversation_locale.py:19-20` and is not evidence about the scan),
    `conversation_locale` returns **`en`** because the newest transcript with Latin letters wins. So with an empty profile, as in production, both server-side deciders treat a Turkish transcript as the owner's language, and the model is told `latest_owner_message` (`packages/agent-runtime/src/lonora_agent/context/memory.py:131`).
- Voice notes: the transcription hint is the profile value and nothing else: `packages/voice/src/lonora_voice/voice_notes.py:55-58`, passed at `:72` to `OpenAISpeechToText.transcribe(... language=...)` (`packages/adapters/src/lonora_adapters/voice/stt.py:15`, sent only when set, `:26`). The module header says "Arabic language hint" (`packages/voice/src/lonora_voice/voice_notes.py:5`) but no code sends one. The transcript is stored as the message content (`packages/db/src/lonora_db/voice_notes.py:64`) and then read like typed text.

### (ii) What is missing
A default that pins the owner's language when the profile is empty; a rule that voice transcripts do not decide language; a hint from the owner's typed history; one shared implementation of the rule (`prefers_arabic` and `conversation_locale` are two copies with different fallbacks); any check that a reply is in the owner's language. Searched: `grep -rn "reply_language\|conversation_locale\|prefers_arabic" packages apps`. (Checker correction: not all hits are listed above. `conversation_locale` also decides the language of owner-action acknowledgments, which produced the run-less message [8] «وُقّع التفويض…» (`packages/db/src/lonora_db/owner_actions.py:2011`; its clauses are `owner_action_grant_authority`, `owner_action_grant_no_money_limit` and `owner_action_grant_resumed`, `packages/bus/src/lonora_bus/attention_messages.json:27`, `:30`, `:34`), the activation acknowledgment (`packages/db/src/lonora_db/activation_acknowledgment.py:29`), the activation review (`packages/db/src/lonora_db/activation_review.py:97`) and card submissions (`packages/db/src/lonora_db/genui_submit.py:359`); `reply_language` also feeds voice sessions (`packages/voice/src/lonora_voice/context.py:171`). With an empty profile each of them would follow a Turkish transcript the same way.)

### (iii) Where the change attaches
- `owner_preferences_section` (`packages/agent-runtime/src/lonora_agent/context/memory.py:119-151`): replace the fallback `"latest_owner_message"` (`:131`) with a server-derived value from typed messages only.
- `conversation_locale` (`conversation_locale.py:13`): skip user messages whose `rich_content` has a voice part, or messages whose transcript is not yet trusted; it already reads up to 16 messages (`:25`). Make `prefers_arabic` (`runtime_notices.py:84`) call the same rule.
- `transcribe_note` (`packages/voice/src/lonora_voice/voice_notes.py:43-75`): derive the hint from the message's thread (the message is loaded at `packages/voice/src/lonora_voice/voice_notes.py:52`) using `conversation_locale`; `transcribe` already takes `language` (`stt.py:15`). This is the Phase 0 voice item; I only name the attachment.
- Reply check: the P12 hook can compare the script of the reply with the owner's language (the same Arabic-letter regex as `conversation_locale.py:29`), a structural test with no word list.
- Eval: `score.py` already has an Arabic check for cards (`card_language_ok`, `scripts/genui_eval/score.py:229`) to extend to replies.

### (iv) Cost
S for the default and the hint; M for the reply-script guard.

### (v) Conflicts / flags
No money conflict. The `reply_language` CHECK allows only `ar` and `en` (`packages/db/src/lonora_db/schema.py:473-476`); `OWNER_DECISIONS.md:14` says cards follow the owner's language "whatever it is, Arabic, English or any other" (the owner's words: «حتى لو سرلنكية»). For this owner (Arabic) it does not bite. `lonora.md:58` ("else the language of the owner's latest message") is the current rule; principle 15 replaces it with "the owner's language".

### (vi) Safe now vs decision
Safe now: derive from typed messages; send the STT hint. Ask the owner once to confirm the pin (profile `reply_language = ar` in his settings), because the policy sentence at `lonora.md:58` otherwise lets a typed English phrase switch the language.

---

## P16. Strength is not bypass

Approvals, mandate and restrictions stay server-enforced; out-of-delegation goes to `owner_action_propose`.

### (i) What enforces money safety today (CODE)
**Tool layer (presentation + gating, never the last word)**
- Availability: `trading_permission_available` → `agent_analysis_only` (`packages/tools/src/lonora_tools/trade.py:57-67`); every financial handler re-checks (`trade.py:316-317`).
- Approval or grant: `approved_execution` `trade.py:301` (card), `covering_grants` `:501`, `account_authorized_execution` `:577-618` (standing grant, same executor).
- Not started: `start_trading_card` `trade.py:206-238` returns `trading_not_started` and a one-tap card.
- Out-of-delegation action: `owner_action_propose` (`packages/tools/src/lonora_tools/owner_actions.py:291`; "No tool can confirm a card: the owner's tap goes to an owner-session route", `:5-7`; widening money authority needs the owner's passkey, `:6-7`).

**The single executor** `ExecutionService.execute` `packages/trading/src/lonora_trading/execution.py:148`: goal/agent lineage and observe-only refusal (`:71-127`, `:81-85`), shadow refusal (`:129-132`), Task stop (`:139-141`), agent permission
(`:171`, `:195`), global ON/OFF and Emergency Stop for new risk, never for exits (`:178-190`), broker preflight (`:182`), connection version and enabled (`:201-205`), account authority (`:207-218`), operation scope (`:221-228`), owner restrictions (`:231-236`),
journal reservation (`:238-248`), then the send boundary. Journal and authority records are written there.

**SCRIPTED** (§16.1-16.3): an analysis-only agent calling `trade_execute` through the bridge gets `{"ok":false,"code":"agent_analysis_only"}`; an "Ask me" agent on an install where trading was never started gets `{"status":"failed","code":"trading_not_started","details":{"send_state":"not_sent"}}` plus a pending `resume_trading` card; journal and approval row counts stayed 0 before and after.
In production `trade_execute` → `TRADE_RETCODE_DONE` at 09:48:27 after the signed grant (trace Part 2, `65e8b682`); UNSURE whether it went through the standing-grant path (`account_authorized_execution`) or an approval card: the trace has no arguments or result body for this call (Part 2 header), and [27] shows an executed-order card either way; before the grant `trade_execute` was withheld with `agent_analysis_only` (trace Part 1, runs `7b86f6fb` to `0afe5ea8`).

### (ii) What is missing
Nothing in enforcement for this principle (searched by reading `ExecutionService.execute` and the tool-side gates top to bottom and by the SCRIPTED §16 runs). What the audit adds: a regression test that every new attachment below leaves each check in place.

### (iii) The attachments I propose for 9 to 15 against those checks
| Principle | Attachment point | Touches an executor check? |
|---|---|---|
| 9 open items | `agent_live_state`, `build_context`, `final_answer` | No (read context, new rows; never authority) |
| 10 owner scope | `control_work`, `control_watch`, `control_task`, `watch_*`/`task_control` routing | No. Watches never trade ("wakes this agent … never trades", `packages/tools/src/lonora_tools/market_watch.py:239`). One flag: cancelling a Task removes that Task's own automatic exits (`execution.py:139-141`); the owner's manual path is unaffected |
| 11 live reads | `dispatch_call` markers, `run_evidence`, `final_answer` | No (reads) |
| 12 reply guard | `final_answer`, `PublicStream` | No, provided the financial-truth gates (`model_runtime.py:225-238`) and the uncertain line run unchanged |
| 13 answer shape | skill / prompt text | No |
| 14 symbol map | `canonical_broker_symbol` (on the trade path: `trade.py:634`) | **Closest.** It changes the string that enters the executor, not any check: preflight (`execution.py:182`), fixed binding (`:88-92`), restrictions (`:231`) and the idempotency identity (`trade.py:635`) still see the resolved name. A stale or wrong entry fails at preflight |
| 15 language | context default, STT hint, locale deciders | No |
So none of principles 9 to 15, as I would attach them, calls or edits a function in the executor list above, the approval/grant functions in `trade.py`, or the owner-card route. (Principles 3, 4, 6 and 7, owned by other sessions, do sit in `trade_execute` and the stop gates; they are not assessed here.)

### (iv) Cost
S: tests only. Suggested: a deterministic test that each attachment's failure mode leaves `journal` and `approval` rows unchanged (the SCRIPTED §16 pattern).

### (v) Conflicts / flags
Two to keep visible: (a) P10's Task cancel versus automatic exits (P10 (v)); (b) P14's resolved symbol on the trade path (P14 (v)).

### (vi) Safe now vs decision
Nothing to decide. The one item for the owner is the Task-cancel notice wording (P10).

---

## Cross-cutting: one hook, five principles

`final_answer` (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:155-184`) is the existing end-of-reply seam. It is already used by the Task stop gate (`:170`) and the uncertain line (`:179`). Principles 9 (record or close open items), 11 (read-first round), 12 (reply guard) and 15 (script check)
all want the same shape: inspect structure, append a runtime notice, return `None`, bounded by a counter in the run state like `stop_gates.py:108-129`. One shared "end-of-turn checks" list in that function, each with its own counter key (like `_STATE_KEY`/`_COMPLETION_KEY`, `stop_gates.py:42-43`) and
reset at real owner input or an external wake (`reset_stop_gate`, `stop_gates.py:66`, called from `loop_restore.py:77` (owner resumed work held for attention), `:103` (external wake) and `packages/agent-runtime/src/lonora_agent/steering.py:47` (owner steering)), avoids a parallel system. The empty-reply `no_answer` re-ask (`tool_loop.py:573-579`) is the existing chat-run precedent. The limit-report path (`finish_turn`, `tool_loop.py:223-323`) must call the same list.

## Eval attachment (`scripts/genui_eval`, structure bank / run / score)

The existing evaluation is single-turn and offline-scorable: cases in `tests/fixtures/genui_decision/cases.jsonl` (owner message, language, expected shape, check text),
tool answers from `tests/fixtures/genui_decision/tool_bank.json` loaded by `scripts/genui_eval/bank.py:29` (every tool but `PASS_THROUGH` is answered from data, `bank.py:35`; anything missing
returns `eval_tool_not_executed`, `bank.py:30`), a runner that seeds a disposable database, optionally seeds earlier turns (`seed_context` `scripts/genui_eval/run.py:300`) and runs the real loop with a recording
adapter (`run_case` `run.py:347`), and a deterministic scorer (`observe` `scripts/genui_eval/score.py:374`, `judge` `:565`, thresholds `:94`, `gate` `:782`). Where each principle's check attaches:
P9 a two-turn case (`seed_context` supplies the first turn; the check is that the second run's reply resumes or names the open item); P10 bank answers for `watch_list`/`agent_inspect` of several agents and a check that `watch_cancel` is called for every watch;
P11 `observe` check "a status case calls a live tool" (it already has `called_tools`, `score.py:240`); P12 and P15 a per-reply scan against `registry.names` and the owner's script (`score.py:374`); P13 a check on the reply's content;
P14 a case whose bank answers a symbol catalog with `XAUUSDm` and a second case in a new thread; P16 no change (the bank never reaches a broker, `scripts/genui_eval/bank.py:1-6`). The new `scripts/agent_eval` is the other session's work; this only says where the same checks would land.

## Open items for the owner (consolidated)
1. P9: auto-retry of failed owner turns after the cause is fixed; lifetime of an unresolved item.
2. P10: cancelling a Task that is the only automatic closer of a position (what the owner is told).
3. P12: allow a guard that blocks and asks the model to rewrite, given `public_reply.py:4` and `model_runtime.py:239-241`; the exception when the owner asks about capabilities (`lonora.md:44`).
4. P14: confirm the live policy lines `lonora.md:60` and `:224` (plus the comment `packages/tools/src/lonora_tools/trading_decision.py:79` and the unloaded `trading_context.md:5`) are replaced by the resolver rules in the same change.
5. P15: pin the owner's reply language to Arabic in his profile.

## UNSURE and TRACE-MUST-CONFIRM (only what the trace could not settle)
- P11: whether admission shed the historical-evidence section of `c22a6810` (code shows it was built non-empty; the trace has no context sections).
- P12: how the web client displays a superseded streamed turn when a repair round follows a published draft (client not run).
- P13: whether the market-analysis skill text is in the run's context when not loaded with `skill_view` (the core manual is always loaded; the skill is selected).
- P15: settled by code plus trace (checker): the profile language is empty (trace Part 1 Q6), the hint is read only from it (`packages/voice/src/lonora_voice/voice_notes.py:55-58`; same code at 2477c22, `git diff --stat 2477c22 9f5b1da` empty for the file), and `stt.py:26` sends `language` only when set, so no language was sent. Still unknown: which transcription model answered (`packages/voice/src/lonora_voice/voice_notes.py:69-72` tries several).

## Verification log (author, before the independent check)

- Every `path:line` citation was extracted from this file and re-opened by script: 264 citations that carry a path, 0 unresolved, 0 out of range
  (`runs/p9-16-citation-check.txt` lists each cited line); the bare `:NNN` follow-ups were re-opened the same way against the file named just before them
  (`runs/p9-16-bare-citation-check.txt`, 230 lines). Each line was then compared with the claim by hand.
- Corrections made during that pass: `lonora.md:23` is `:24` ("An owner request for analysis is not permission to trade"); the `AgentRow` checks are `schema.py:165-197`;
  the message load in `transcribe_note` is `voice_notes.py:52`, not `:24`; `stop_management_task` is also called when a grant is revoked, so the Task/grant paragraph in P10 (v) was rewritten;
  two bare line numbers that a reader could attach to the wrong file now carry their file name.
- One finding was reversed by a probe: SCRIPTED §15.2 printed `ar` only because the shared test owner's profile language is `ar`; with the profile hidden (`runs/p9-16-locale-probe.out`)
  `conversation_locale` returns `en` for the Turkish transcripts, so P15 says both deciders accept the transcript (the first draft said they disagree).
- Quotes (policy lines, tool descriptions, Arabic strings) were copied from the cited lines, shortened only at the ends.
- Scripted runs: `python scripts/p916_principles.py` on database 13 (exit 0, run twice; the second run is the file `runs/p9-16-principles.out`); the probes `scripts/p916_locale_probe.py` and
  `scripts/p916_language_line.py` read only. No file under `/home/user/lonorabot` was created, changed or deleted; `git status --short` is empty.
- Not verified, stated as such above: the web client's display of a superseded streamed turn (P12), context sections of production run `c22a6810` (P11), the exact STT request body (P15),
  and whether a run that has not loaded the market-analysis skill sees its text (P13).

## Verification log

Independent check of this file against main (code identical to 9f5b1da; HEAD 3f09572 adds documents only) and against `production-trace.md`,
`TIMELINE_CORRECTION.md` and `lonora-chat.md`. Repository untouched: `git -C /home/user/lonorabot status --short` empty before and after.

**Citations opened.** A script (`chk916/dump.py`) extracted every `path:line` and bare `:N` follow-up and printed the cited lines:
402 citation instances before the edits, 476 after (`chk916/dump.txt`, `chk916/dump2.txt`); 0 missing files, 0 out of range. Each line was
compared with the claim by hand; ranges were read at start and end, and the passages a claim depends on were read in full
(`stop_gates.py:140-185`, `agent_state.py:222-470`, `team.py:55-120`, `run_evidence.py:25-235`, `model_runtime.py:95-300`,
`public_reply.py:1-70`, `public_stream.py:1-60`, `execution.py:60-200`, `market_watches.py:115-200`, `tasks.py:395-425`,
`messages.py:515-590`, `voice_notes.py:1-76`, `conversation_locale.py:10-36`, `runtime_notices.py:84-99`, `tool_loop.py:495-612`).
Quotes checked character by character: all English policy/tool quotes match; the Arabic quotes from the conversation match
`lonora-chat.md` (shortened at the ends only).

**Reproductions rerun** (database 13, `source env.sh 13`): `scripts/p916_principles.py` first failed with `POST /auth/login: HTTP 401`
because another session had recreated database 13 at 15:58 UTC with owner `conv-efg@example.com`; rerun with
`LONORA_UI_TEST_EMAIL=conv-efg@example.com` (the default password), exit 0, output `chk916/principles.out`. Reproduced: 10.2 (empty
`watch_list`/`routine_list`/`task_inspect`/`goal_list`; `market_watches_not_found` for `watch_cancel`/`watch_update`; `task_agent_mismatch`
for `task_inspect`/`task_control`; `routine_toggle` ok; both `agent_control` pauses ok), 10.3, 10.5, 11.3 (evidence block present, no
open-item words, `tasks: []`, `watch_count: 0`), 11.4, 11.6 (`data_freshness` `unavailable`, `quote.age_seconds` 4.4), 12.1-12.2 (stored reply
identical, one model turn), 15.1 (both transcripts `false`), 15.2 (`ar`, from the profile), 16.1-16.3 (`agent_analysis_only`;
`trading_not_started` + pending `resume_trading`; journal/approval counts 0 → 0). Differences, explained: 10.4 printed 1 instead of 3 (fresh
database); the native list of 10.2 lacked `watch_list`, `routine_list`, `routine_toggle`, `goal_list`, `task_inspect`, `agent_control`, which were
present in the author's run because the personal agent had used them before (usage promotion, now described in P10 (iii)); in this rerun
they appear in the later runs 12.1 and 11.2 after their first successful use. `scripts/p916_locale_probe.py` → `en` with the profile hidden,
`scripts/p916_language_line.py` → `reply_language: "ar"`: both reproduced.

**Recounts.** 36 tool calls (trace Part 2): recounted, 36. 23 native tools: recounted from the baseline list, 23. 126 registry tools:
`load_tools()` → 126. 723 distinct `LonoraError("…")` literals: same grep → 723. Retry runs with `retry_of`: 4. Poller tools: the registry
lists 12 (`account_activity`, `account_read`, `collaboration_inspect`, `goal_read`, `market_opportunity_read`, `market_quote`,
`owner_attention_list`, `runtime_status`, `subagent_inspect`, `task_inspect`, `trade_record_read`, `watch_list`); the file's examples are among them.

**Refuted and corrected.**
1. P13 and P14 relied on `packages/agent-runtime/resources/prompts/trading_context.md` as live policy (P13 named `trading_context.md:1` as the
   cause of the specification dump in `10171b1c` and as an attachment point). No code loads that file (two searches: the `load_prompt(`
   call sites, and `grep -rn trading_context` over packages, apps, scripts and tests; the only other readers of `resources/prompts` load the
   GenUI and native-visual files). The causal claim is withdrawn (UNSURE), the attachment moved to the skill/core manual, and P14's policy
   conflict now names the live lines `lonora.md:60` and `:224`.
2. P9 trace: "[1]/[3] were never answered" was wrong for [3]: the retry `d5b850bc` answered it at 09:37:46 (trace Part 1, Part 3). Only [1] was
   never answered.
3. P9: "Also missing: any automatic retry of a failed owner turn" was too broad: transient provider failures are retried automatically in
   the same run (`model_recovery.py:155-200`, `executor.py:292-304`); only non-transient failures such as `model_not_configured`
   (`resilience.py:119`) need the owner's button. Row added to P9 (i).
4. P15: "all hits are the ones above" for the language grep was false: `conversation_locale` also serves the owner-action acknowledgment
   that produced [8], the activation acknowledgment and review, and card submissions; `reply_language` also feeds voice sessions. Added.
5. P11: "`observed_at` … stamping in the evidence block only" was false: the run state stamps every call (`context_engine.py:74`,
   `:180-187`) and shows the time on pruned and compacted results too. "full result previews" corrected to "previews up to 600 characters".
6. P12: "no check reads reply text at all" overstated: privacy redaction and the streaming `EFFECT_CLAIM` hold do read it (the latter with
   Arabic patterns), but neither blocks or rewrites for codes/names/states. Reworded; the classification FAILS stands and is now marked as
   observed on main for [73], [75], [77].
7. P12/cross-cutting: "A chat run never reaches [a repair round]" is true of the task stop gate but missed the empty-reply re-ask that does run
   in chat (`tool_loop.py:573-579`); added as the nearest precedent. `reset_stop_gate` callers corrected (`loop_restore.py:103` is an external
   wake, not owner input; `steering.py:47` was missing).
8. P9 (i)/(iii): `agent_live_state` carries up to six enabled-watch summaries, phase and waiting_reason, not only "title/status" and a count.

**Downgraded to UNSURE.** P16 "the grant path ran" for `65e8b682` (the trace has no arguments or result body; card or grant path unknown).
P13 genui teaching lines are live only with `LONORA_GENUI_V2` set (production setting unknown). P11 `c22a6810`: only admission shedding remains
unknown (code shows the evidence section was built non-empty).

**Line and wording fixes.** `owner_actions.py:290` → `:291` (the tool name); `agent_control` "not eager" now cites the whole `Tool(...)`,
`supervision.py:609-623`; `voice_notes.py:49-72` → `:43-75` (`transcribe_note`); "even Sinhalese" was a paraphrase, replaced by the decision's
own words; ambiguous short paths (`context/memory.py`, `contracts/supervision.py`) given in full.

**Claims added (with citations in the body).** The cited code that produced [4]-[71] is unchanged on main (section 1). Usage promotion of
long-tail tools after one successful use (P10 (iii)). `live_agent_state` already gives the model its enabled watches every turn, so «أراقب
XAUUSDm» contradicted a server-derived list; and `team.py:91` points to two tools that were not native (P11 (i)). `lonora.md:59` (P15).
Prompt-only promise handling in `consolidator_archive.md:22` and `lonora.md:127` (P9 (ii)). The "STT request body" item is settled by code plus
the empty profile (UNSURE list).

**Checked and confirmed without change.** The P10 ownership table and its SCRIPTED results; `require_task_authority` refusing every trade of a
run bound to a stopped Task (`execution.py:129-141`, reached through `require_goal_lineage` `:86`, `:110`); `stop_management_task` has no
caller in `control_task` (`grep -rn stop_management_task`); the absence of a symbol map (two greps); the absence of a server-side markdown
normaliser (two greps; the web client only closes unterminated fences, `packages/chat-ui/src/markdown.web.tsx:34`); `prefers_arabic` and
`conversation_locale` logic; the voice hint path; every trace citation (run ids, times, seq numbers, Part numbers) against
`production-trace.md`.
