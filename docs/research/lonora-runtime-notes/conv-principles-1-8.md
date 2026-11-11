# Binding principles 1 to 8: what exists, what is missing, where each one attaches

Repository `/home/user/lonorabot`, main at `9f5b1da`, read-only audit. All `path:line` citations are
relative to the repository root and refer to `9f5b1da`. Production facts come from
`production-trace.md` (cited as "trace Part n, run id"; all times UTC) and from the corrected
timeline in `TIMELINE_CORRECTION.md`.

## 0. How to read this file

- **OBSERVED**: shown by the production trace (trace part and run id are cited).
- **REPRODUCED**: a scripted run on main. Every model turn is SCRIPTED (I wrote the tool calls and the
  reply text, copying the owner-visible replies from `lonora-chat.md`); the evidence is what the real
  runtime produced (tool results, recovery blocks, committed reply, exposed tool list, stored state).
  Scripts are in `scratchpad/audit/scripts/cp_*.py`, raw output in `scratchpad/audit/runs/cp-*.out` (section 12).
- **READ**: read from code only.
- **UNSURE**: not settled. "TRACE MUST CONFIRM" is kept only where tool arguments or result bodies still
  missing from the trace would settle it (section 11).
- Sizes: **S** = one file or function plus tests; **M** = several files in one package plus tests;
  **L** = several packages, new stored state, or new evaluation data.
- "Safe at once" = changes no authority, no money path, and no owner decision is needed.
  "Owner decision" = it changes what the agent may do on its own, or chooses a policy number.
- Build note (corrected by the checker): `git diff --stat 2477c22 9f5b1da` over the files cited below shows 20 changed
  files, not five: besides `context/history.py`, `context/skills.py` (one query filter), `model_runtime.py` (a GenUI v2
  request block), `market_watch.py` and `trade.py` (GenUI taint/origin lines), also `context/builder.py`, `db/messages.py`,
  `db/runs.py`, `db/schema.py` (message `origin`/`ui_submit` columns), `restrictions.py`, `owner_actions.py`,
  `runtime_control.py`, `trading_goal.py`, `contracts/domain.py`, `contracts/genui.py` (new) and
  `contracts/instrument_names.py` (new: added by commit `db668bc`, which is in `cd2cc91` but not in `2477c22`, and used
  only by the GenUI code). Those changes are GenUI v2 and message-origin work; none of them touches the mechanisms this
  file classifies. Since `aa50e8e` (PR #42) none of `tool_dispatch.py`, `environment.py`, `stop_gates.py`,
  `loop_outcomes.py`, `symbols.py`, `tool_discovery.py` changed (empty `git diff --stat aa50e8e 9f5b1da` over them), and
  `resources/system`, `resources/bootstrap` and `resources/constitution` are identical between `2477c22` and `9f5b1da`.
  So the runtime behaviour described here served every run of the 2026-11-11 conversation; runs [72] to [81]
  (`fb1d4b5a`, `3fa683e6`, `e79b4bf2`, `1bcddcee`, `38b259bb`) ran on exactly this code. `instrument_names.py` (cited in
  section 2) did not exist for runs [4] to [55].

Message-to-run map used below (export number, run id; trace Part 1 and Part 3): [10] `1ae9a14c`, [12] `e09ad476`,
[14] `10171b1c`, [16] `af5f00b3`, [18] `6f8ff964`, [24] `00f7b6bc`, [26] `65e8b682`, [29] `c22a6810`, [31] `cc8399d7`,
[35] `94d50998`, [37] `ac7e6426`, [41] `eb67419d`, [43] `8114abdd`, [47] `6e4aa88f`, [57] `7e7da121`, [59] `f51d1db6`,
[63] `ddae66ad`, [65] `049af207`, [69] `e343c96a`, [71] `1638329a`, [73] `fb1d4b5a`, [75] `3fa683e6`, [77] `e79b4bf2`,
[81] `38b259bb`.

### Status of each principle on main (one line each)

| # | Principle | Status on main | One-line reason |
|---|---|---|---|
| 1 | Resolution-first | FAILS | no shared resolver; suffix, alias and name matching exist in separate places and none is used by the read tools (section 2) |
| 2 | Unified error contract and bounded recovery | PARTLY | `recovery` block and bounded retry of transient reads exist; no `class`, `hint`, `candidates`, `next_actions`; no automatic recovery for resolution errors (section 3) |
| 3 | Act, do not offer | FAILS | the only end-of-turn "continue" gate is for Task runs; a conversation reply that ends with an offer is committed unchanged; the core-policy rules against it (`packages/agent-runtime/resources/system/lonora.md:120,135`) are prompt text only (section 4) |
| 4 | Short approval executes the offer | FAILS | no state links a short reply to the previous offer; the stored `suggested_reply` is never handed back to the model; only the core-policy sentence `packages/agent-runtime/resources/system/lonora.md:130` and plain history carry the offer. In production short approvals of read offers were executed ([16], [18], [22]) and of own-state offers were not ([37], [39], [43], [77]) (section 5) |
| 5 | Condition becomes a durable trigger | FAILS | the tools exist (`watch_create` on a position, `modify_position`); only general prompt text points at watches (`packages/agent-runtime/resources/system/lonora.md:127`, and `packages/agent-runtime/resources/system/lonora.md:433` in a domain chapter); nothing maps "close at +X" to them and nothing checks the claim (section 6) |
| 6 | Defaults and one-card plan inside the delegation | FAILS | the core policy in every run already says full management "lets you choose size, stops and targets" (`packages/agent-runtime/resources/system/lonora.md:106`) and the permission frame says "size and manage positions"; the explicit "do not ask for routine parameters" is only in a skill not loaded and in the Task's own prompt; the grant holds no default size; nothing enforces any of it (section 7) |
| 7 | No inability claim without evidence | FAILS | no runtime check of an inability claim; the search fails on the owner's words, and the model claimed absence although the mandatory constitution names `watch_cancel` (`packages/agent-runtime/resources/constitution/trading-policy.md:7`) and the inventory lists it (section 8) |
| 8 | No promise or "done" without a tool result; no trial calls | PARTLY | financial claims have gates; every non-financial claim and every trial call is unchecked (section 9) |

---

## 1. Facts shared by all eight principles

### 1.1 The path a final reply takes in a conversation run (READ, REPRODUCED)

1. The model turn returns a reply. Inside `model_turn`: the trailing `<suggested_reply>` tag is cut off
   (`packages/agent-runtime/src/lonora_agent/model_runtime.py:195`), then the financial-truth gates run
   (`packages/agent-runtime/src/lonora_agent/model_runtime.py:218-238`, keyed on the tool names in
   `FINANCIAL_CALLS` only), then privacy redaction (`packages/agent-runtime/src/lonora_agent/model_runtime.py:246`).
   Comment at `packages/agent-runtime/src/lonora_agent/model_runtime.py:239-241`: "Style is model guidance, never a
   second generation or a failed user request."
2. The assistant message is appended and checkpointed (`packages/agent-runtime/src/lonora_agent/tool_loop.py:580-589`).
   If it carries no tool call the loop calls `final_answer`
   (`packages/agent-runtime/src/lonora_agent/tool_loop.py:595-609`); a `None` return continues the turn
   (`packages/agent-runtime/src/lonora_agent/tool_loop.py:610-611`).
3. `final_answer` (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:155-184`) asks `task_stop_gate`
   (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:170`). For a run without a Task `task_progress` returns `None`
   (`packages/agent-runtime/src/lonora_agent/stop_gates.py:153-155`) and the gate answers `continue_turn=False`
   (`packages/agent-runtime/src/lonora_agent/stop_gates.py:180-181`). The only other thing it does is the PR #42
   uncertain-outcome line (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:179-183`). The text is returned as is
   (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:184`).
4. Exits that do not pass through that call and would each need the same check: the round-limit report
   `finish_turn` (`packages/agent-runtime/src/lonora_agent/tool_loop.py:223-322`; PR #42 had to add a second call at
   `packages/agent-runtime/src/lonora_agent/tool_loop.py:299`), the silent-final path
   (`packages/agent-runtime/src/lonora_agent/tool_block.py:394-412`), a question outcome
   (`packages/agent-runtime/src/lonora_agent/tool_block.py:392-393`) and an external wait
   (`packages/agent-runtime/src/lonora_agent/tool_block.py:389-391`).
5. Streaming: the reply text is published to the owner while it is generated
   (`packages/agent-runtime/src/lonora_agent/public_stream.py:11-19`, `packages/agent-runtime/src/lonora_agent/public_stream.py:47`). A check that runs after
   `final_answer` judges text the owner may already have read. The existing way to change published text is a new
   reply turn id (`packages/agent-runtime/src/lonora_agent/model_runtime.py:282-287`).

### 1.2 What PR #42 added (READ; `git show --stat aa50e8e`)

Ten files: `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py` (new), edits in `loop_outcomes.py`, `loop_restore.py`,
`tool_loop.py`, two constitution files (`identity.md`; `trading-policy.md` gained the whole paragraph now at
`packages/agent-runtime/resources/constitution/trading-policy.md:7`, which includes "A watch is cancelled with watch_cancel or changed with
watch_update" and "Say something was done only when a successful tool result in this request shows it."), one tool-description word
(`memory.py`: "limits") and two tool-result text fields (`models.py` "next", `runtime_control.py` "guidance"), and
`tests/test_uncertain_outcome.py` (`git diff aa50e8e^1 aa50e8e`).
The only runtime check is the uncertain-outcome line. Its own header states the scope: "Structured results only: no
wording of the owner or the model is read." (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:3`). It looks at three tool names
(`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:23`). So no reply guard of PR #42 reads what the reply says.
The trace agrees (trace Part 4 finding 9: for `ddae66ad`, `e343c96a` and `fb1d4b5a` the saved run state holds no
blocked reply, no rewrite and no repair round). Scripted reproduction of the same runs on main: every committed reply
is byte for byte the scripted text (`runs/cp-guards.out`, cases 1, 2, 3, 4a, 4b, 4c, 5a, 5b, 5c).

### 1.3 What the production model was offered and did (OBSERVED)

- 23 native tools in every run (trace Part 1): `account_read, agent_inspect, chart_snapshot, list_accounts,
  market_candles, market_decision_history, market_decision_record, market_instrument, market_quote, market_sessions,
  market_snapshot, memory_read, memory_write, peer_send, session_search, skill_view, skills_list, tool_call,
  tool_environment, trade_execute, wait_for_input, watch_create, web_search`. Clean reproduction on main (remembered-tool
  promotion switched off): 22 tools, the same list without `web_search`. `web_search` is added natively by the chat option
  (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:99,113-118`) or by remembered-tool promotion
  (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:95,102-104`); in the test database it is also unavailable
  (`research_provider_not_configured`). UNSURE which of the two put it in the production list. Registered but absent from the native list:
  `watch_list`, `watch_cancel`, `watch_pause`, `watch_update`, `trade_close_positions`, `market_symbols`,
  `market_position_size`, `task_control`, `goal_create`, `owner_action_propose`, `trade_restriction_create`
  (`runs/cp-principles.out`, section "P1b"). The eager set follows `run_profiles`
  (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:31-49`) and `Tool.eager`.
- 36 tool calls in the whole conversation, 34 ok. No `skill_view` call anywhere (trace Part 2 tool events), no
  `watch_cancel`, `watch_list`, `market_symbols` or close call.
- The runs were conversation runs with no Task: `trigger=user` on all 41 runs (trace Part 1 header).

### 1.4 Rules already written as prompt text, and what happened (READ + OBSERVED)

| Sentence (verbatim, short) | Where | What the production run did |
|---|---|---|
| "continue the already requested reversible work in the same turn" | `packages/agent-runtime/resources/constitution/tool-policy.md:3` | 19 of 37 replies end with an offer by reading, 21 match the offer pattern (section 4) |
| "For requested action, inspect the smallest relevant scope and continue the authorized work." / "Do not ask the owner whether to perform analysis, inspect a chart or build a plan they already requested: do that reversible work first." (core policy, every run) | `packages/agent-runtime/resources/system/lonora.md:120`, `packages/agent-runtime/resources/system/lonora.md:135` | same as above |
| "A short reply continues the preceding request; do not treat it as an isolated new task or forget a previously chosen side." (core policy, every run) | `packages/agent-runtime/resources/system/lonora.md:130` | read offers were executed after «ياريت» ([16], [18]) and «نعم 3 صور» ([22]); own-state offers were not after «طيب» ([37]), «تمام» ([39]), «تم» ([43]), «جرب» ([77]) |
| "Use actual watches, schedules or task waits for future work; do not promise to remain awake by thinking continuously." (core policy, every run) | `packages/agent-runtime/resources/system/lonora.md:127` | [43], [47], [57] claimed monitoring with no watch |
| "Explicit full management lets you choose size, stops and targets without per-order approval or default volume/activity quotas" (core policy, every run) | `packages/agent-runtime/resources/system/lonora.md:106` | [24] asked for the size |
| "inspect it with tool_environment first when you do not know its input schema, and before claiming an ability is absent" | `packages/tools/src/lonora_tools/registry.py:428-429` (capability inventory; on main it lists all 126 names, `watch_cancel`, `watch_list`, `market_symbols` and `trade_close_positions` included: `chk/p18/inventory.out`) | [71] claimed no tool with zero calls |
| "A watch is cancelled with watch_cancel or changed with watch_update ... Reach a tool outside your native list with tool_call." (constitution, every run; added by PR #42) | `packages/agent-runtime/resources/constitution/trading-policy.md:7`; loaded for every run by `packages/agent-runtime/src/lonora_agent/skills/loader.py:27-46` | [71], [75], [81] said no delete tool; [77] called `watch_create` instead |
| "Steer your own watches with watch_cancel, watch_pause, watch_resume and watch_update (expiry, level); confirm in one line, and watch_resume undoes a cancel." | `packages/agent-runtime/resources/system/lonora.md:434` (the `tasks` chapter, lines 406-442, added to a request only when a `tasks` tool such as `wait_for_input` was called in the last 16 messages: `packages/agent-runtime/src/lonora_agent/skills/system_policy.py:133-141`, `packages/agent-runtime/resources/system/manifest.json:119`) | `ddae66ad` and `e343c96a` called `wait_for_input` and then did not cancel. UNSURE whether the chapter was in those production requests (request bodies are not in the trace, section 11) |
| "Say something was done only when a successful tool result in this request shows it." | `packages/agent-runtime/resources/constitution/trading-policy.md:7` | [63] "تم الإلغاء" after three `watch_create`; [73] recited this sentence to the owner |
| "Under signed full management choose justified direction, lot size, stops and targets yourself; do not ask for routine parameters already delegated." | `packages/agent-runtime/resources/skills/trade-management/SKILL.md:23-24` | not in context: skills are description-first (`packages/agent-runtime/src/lonora_agent/context/skills.py:198-200`, `packages/agent-runtime/src/lonora_agent/context/skills.py:239`); `trade-management` activates only on the intent "trade" (`packages/agent-runtime/resources/skills/trade-management/skill.json:9-13`) and the chat run passes no intents (`packages/agent-runtime/src/lonora_agent/skills/resolver.py:106-110`); the model never called `skill_view`; [24] asked for the size |
| "A trigger wakes analysis, never execution directly." | `packages/agent-runtime/resources/skills/market-watch/SKILL.md:18` | n/a, never viewed |
| "Do not ask for each order or ask the owner to choose routine trading parameters." | `packages/auth/src/lonora_auth/account_authority.py:150` | this is the prompt of the Task created at signing, not of a chat run (`packages/auth/src/lonora_auth/account_authority.py:131-173`; the chat context builder has no Task text: `packages/agent-runtime/src/lonora_agent/context/builder.py:100-175`) |

Conclusion for all principles: prompt text has been tried for each of them and did not hold. The enforcement points
below are the ones that exist in code.

### 1.5 Constraints every change inherits

Money safety (`docs/trading-safety.md:7-9` "The single executor ... still re-reads the grant, global trading,
restrictions, money limits and unresolved operations at the moment of sending"; `docs/trading-safety.md:18` "Exits stay
allowed"; `packages/tools/src/lonora_tools/trade.py:753-757` "spoken or typed agreement is not approval").
Owner decisions: `docs/ui-reference/OWNER_DECISIONS.md:12` ("No keyword router, no forced interface, no separate
classifier call" for the shape of an answer), `docs/ui-reference/OWNER_DECISIONS.md:13` (prompts and skills in English;
"server-side matching data (instrument names, owner-text checks)" stays Arabic and is allowed),
`docs/ui-reference/OWNER_DECISIONS.md:10` ("The agent has access to every tool"),
`docs/ui-reference/OWNER_DECISIONS.md:17` (fresh start: no migrations of old data), `docs/ui-reference/OWNER_DECISIONS.md:51`
(Q23: the agent may add a suggested reply of at most 60 characters to conversational answers only).
The code comment `packages/core/src/lonora_core/public_reply.py:4` says presentation is "not a keyword veto on replies".
Any gate on reply wording (principles 3, 7, 8) is in tension with those two lines; section 10 lists it as a decision.

### 1.6 The one primitive principles 3, 5, 7 and 8 share

"What this request actually did" is already computed once, for three money tools:
`record_request_start` stores `owner_started` and `owner_request_start`
(`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:40-48`, called at
`packages/agent-runtime/src/lonora_agent/loop_restore.py:58`), and `uncertain_operations` pairs each tool call with its
result since that index (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:78-112`). The tool set there is the constant
`FINANCIAL_EFFECTS` (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:23`). The effect class of every tool is already
known to the runtime: `Tool.read_only`, `Tool.financial`, `Tool.poller`
(`packages/tools/src/lonora_tools/base.py:72-82`) and the "financial" / "read" / "change" label
(`packages/agent-runtime/src/lonora_agent/tool_block.py:148-156`). A walker that returns "for this request: each
(tool, arguments, result, effect class)" is the shared input of the checks in sections 4, 6, 8 and 9. It does not exist today.
UNSURE only about production: whether `owner_started` and `owner_request_start` are present in the saved run state
(trace Part 4 finding 9 lists the keys it saw and does not name them; section 11).

### 1.7 What a server update does (stated as the brief asks; OBSERVED + READ)

Three updates ran during the conversation (09:54:57, 10:23:46, 10:38:12 UTC); each stops the API and the gateway and recreates the containers
(`TIMELINE_CORRECTION.md`). A run in flight: its checkpoint is written at every step (`packages/agent-runtime/src/lonora_agent/tool_loop.py:117-126`) and a
scheduled retry stores its deadline in the checkpoint (`packages/agent-runtime/src/lonora_agent/environment.py:219-224`); the only visible effect in the trace is
run `57dcaeb0` waiting eight seconds between queued and leased (trace Part 2). Pending offers: none exist today (section 5), so none can be lost, and the pending
question of a card lives in the run checkpoint. Anything held in memory is lost on an update: for example the broker adapter cache
(`packages/adapters/src/lonora_adapters/brokers/base.py:23`), rebuilt on the next call. Consequence for every principle: any new state (a pending offer, a recovery counter, a gate counter) must be
stored in the database or the checkpoint, never in process memory.

---

## 2. Principle 1: resolution-first (one shared resolver for symbol, account, agent, watch, position)

### (i) What exists today

The reference parameters (registry introspection of all 126 tools, `runs/cp-reference-params.tsv`): 65 tools take at
least one reference, 134 fields. By kind: `account_id` in 32 tools, `symbol` in 24, `goal_id` 10, `agent_id` 8,
`chart_id` 8, `watch_id` 5, `position_id` 4, `order_id` 3, `operation_id` 4, `connection_id` 3, `task_id` 2,
`routine_id` 1, `ticket_id` 1, `thread_id` 4, `restriction_id` 1, plus nested `related_symbol` (4) and `symbols` lists.

How each kind resolves today (READ unless marked):

| Reference | Tools | Resolution today | Error when it fails |
|---|---|---|---|
| Account (`account_id`, a connection id) | all `market_*`, `account_*`, `chart_*`, `trade_*`, `goal_*`, `watch_create`, `list_accounts` output | exact id: `BrokerManager.get` -> `connect` -> `BrokerSessionRepository().get` (`packages/adapters/src/lonora_adapters/brokers/base.py:25-33`). The model must call `list_accounts` first and copy the id. A broker name, login or server ("Exness-MT5Trial16") does not resolve | `broker_sessions_not_found` (REPRODUCED, `runs/cp-contract.out` S1: `account_id: "Exness-MT5Trial16"`) |
| Account default | agents bound to an account | `fill_bound_fields` and `align_payload` fill or case-fix `account_id` and `symbol` from the agent's binding (`packages/tools/src/lonora_tools/market_binding.py:44-79`), but `prepare_market_arguments` returns the arguments untouched when the agent has no bound account and symbol (`packages/tools/src/lonora_tools/market_binding.py:89-90`). The Personal Agent has neither (trace Part 1 Q6: `trading_account_id` null, `trading_symbol` null). So it has no default account even with one connection | model must pass `account_id` |
| Symbol, read tools | `market_instrument`, `market_quote`, `market_candles` | `canonical_broker_symbol(..., require_exists=False)`: case-only match, and if the catalog read fails or the name is absent the raw symbol is passed on (`packages/tools/src/lonora_tools/symbols.py:18-35`, callers `packages/tools/src/lonora_tools/market.py:47,58,65`). The broker then answers | production run `1ae9a14c`: `market_instrument("XAUUSD")` -> `broker_account_not_found`; cause in `packages/adapters/src/lonora_adapters/brokers/metaapi.py:52-58` (any 404 outside the candles stage becomes `broker_account_not_found`) |
| Symbol, strict read tools | `market_snapshot` (line 140), `market_sessions` (through `_broker_hours`, line 215), `market_candles_to_workspace` (line 305), `market_structure` | `canonical_broker_symbol(..., require_exists=True)` (`packages/tools/src/lonora_tools/market_analysis.py:140,215,305`, `packages/tools/src/lonora_tools/market.py:78`) -> `catalog_symbol`: exact, or a single case-only match (`packages/tools/src/lonora_tools/symbols.py:6-15`) | `symbol_not_found` (OBSERVED, `1ae9a14c`, `market_snapshot("XAUUSD")`; trace Part 4 #15) |
| Symbol, trades | `trade_execute` | same lenient function, before the operation id is hashed (`packages/tools/src/lonora_tools/trade.py:632-635`), so a resolved symbol would enter the immutable request | falls through to broker preflight |
| Symbol, restrictions and owner actions | `trade_restriction_create`, `owner_action_propose` | strict when the catalog is readable (`packages/tools/src/lonora_tools/symbols.py:38-56`, `packages/tools/src/lonora_tools/restrictions.py:148`, `packages/tools/src/lonora_tools/owner_actions.py:85`) | `symbol_not_found` / `symbol_ambiguous` |
| Symbol, decisions | `market_decision_record` | exact on purpose: "Exact symbols are intentional. No hidden aliases or suffix stripping." (`packages/tools/src/lonora_tools/trading_decision.py:79`) | broker error |
| Symbol, agent creation | `agent_create` | the only place with suffix matching and candidates: `symbol_candidates` (`packages/tools/src/lonora_tools/agents.py:72-91`) and `resolve_market`, which returns `"resolved": False` and a `candidates` list for a card (`packages/tools/src/lonora_tools/agents.py:94-135`, `"resolved": False` at line 127) | `symbol_not_found` or the candidates |
| Position (`position_id`) | `trade_execute`, `watch_create`, `goal_create`, `goal_plan` | `trade_execute`: `management_targets` reads broker positions and returns `None` for an unknown ticket (`packages/tools/src/lonora_tools/trade.py:78-95`); the refusal `position_not_found` is in preflight and also requires the exact symbol spelling (`packages/trading/src/lonora_trading/preflight.py:29-37`). `watch_create`: existence is checked only for agents with a bound account (`packages/tools/src/lonora_tools/market_binding.py:133-140`, reached only when `fixed_market(agent)` is true: `packages/db/src/lonora_db/agent_binding.py:35-36`) | REPRODUCED: for the Personal Agent `watch_create(kind="position", position_id="9999999999")` returns `ok: true` (`runs/cp-principles.out`, P5 section); `trade_execute modify_position` on an unknown ticket raised a pending approval card (`runs/cp-contract.out` S5: "approval rows raised for this run: 1", status pending). UNSURE: when `packages/trading/src/lonora_trading/preflight.py:35-36` runs relative to the card |
| Watch (`watch_id`) | `watch_cancel`, `watch_pause`, `watch_resume`, `watch_update` | exact id; the row must belong to the calling agent (`packages/db/src/lonora_db/market_watches.py:115-125`: "Another agent's watch reads as not found"). `watch_list` lists only this agent's rows (`packages/tools/src/lonora_tools/market_watch.py:148-157`). Nothing selects a watch by symbol, level or description | `market_watches_not_found` (REPRODUCED S1 with a descriptive id) |
| Agent (`agent_id`) | `agent_inspect`, `agent_control`, `peer_send`, `model_list`, `model_request`, `trade_restriction_create`, `owner_action_propose` | exact id; `agent_inspect` accepts the own id or a supervised agent (`packages/tools/src/lonora_tools/supervision.py:408-417`). Name lookup exists only in `list_agents(name=...)` (`packages/tools/src/lonora_tools/agents.py:60-67`) | `agent_not_found` (REPRODUCED S1) |
| Chart, goal | `chart_*`, `goal_*` | exact id from the database (`packages/tools/src/lonora_tools/market_binding.py:123-132` for the fixed-market check) | `cloud_charts_not_found`, `goal_not_found` |
| Task, routine, ticket, operation, thread, connection, restriction | `task_*`, `routine_toggle`, `ticket_start`, `trade_record_read`, `mcp_*`, ... | exact id; not opened one by one (UNSURE of each error code) | |

Pieces that already exist and are not connected to the read tools:

- `symbol_candidates` has the suffix rule the owner needs: exact, then case-only, then "every name that only adds a
  broker suffix" (separators `.-_#!+` or up to four lowercase letters; `packages/tools/src/lonora_tools/agents.py:55-56,72-91`;
  `packages/contracts/src/lonora_contracts/instrument_names.py:32-33` holds a second copy of the same two constants). REPRODUCED on a catalog
  `[XAUUSDm, XAGUSDm, EURUSDm, BTCUSDm, GOLD, XAUUSD.pro]`: `symbol_candidates("XAUUSD")` returns
  `['XAUUSDm', 'XAUUSD.pro']` while `catalog_symbol("XAUUSD")` raises `symbol_not_found` (`runs/cp-principles.out`, P1a).
- `INSTRUMENT_NAMES` holds Arabic, English and short names for nine instruments
  (`packages/contracts/src/lonora_contracts/instrument_names.py:20-30`; "الذهب", "ذهب", "Gold" for `XAUUSD`) and
  `instrument_entry` maps a broker spelling (suffixes included) to its entry
  (`packages/contracts/src/lonora_contracts/instrument_names.py:36-54`). It maps symbol to name only: `instrument_entry("GOLD")` is `None`
  and the name-to-symbol direction does not exist. This module was added after `2477c22` (commit `db668bc`) and is
  used only by the GenUI code (`packages/agent-runtime/src/lonora_agent/genui_vocabulary.py:9`,
  `packages/agent-runtime/src/lonora_agent/genui_compile.py:32`, `packages/contracts/src/lonora_contracts/genui_intents.py:17`).
- `resolve_instrument` (`packages/market/src/lonora_market/instruments.py:5-9`) is exact-only and has no caller: a grep of
  `*.py` outside `.venv` for `resolve_instrument` finds only its definition.

### (ii) What is missing (and how I searched)

- No shared resolver. Searched: callers of `catalog_symbol`, `canonical_broker_symbol`, `restriction_symbol`,
  `symbol_candidates`, `resolve_instrument`, `instrument_entry` across `packages` and `apps` (section (i) lists them);
  `grep -rln "candidates"` in `packages/tools/src`, `packages/agent-runtime/src`, `apps/api/src` finds symbol candidates
  only in `agent_create` (`agents.py`); the other hits (`consult.py`, `context_engine.py`, `skills/resolver.py`,
  `genui_compile.py`, `context/image_observations.py`) use the word for other things (checker re-ran the grep).
- No alias table in the direction name to symbol ("الذهب", "gold", "XAU"); no account lookup by broker, login or server;
  no watch or position lookup by description; no default account for the Personal Agent.
- No error carries a candidate list. `LonoraError` has only `code`, `status` and diagnostics
  (`packages/core/src/lonora_core/user_error.py:1-14`).
- Symbol discovery is not native for the Personal Agent: `market_symbols` is described as "Use before guessing broker
  symbols or aliases; suffixes matter." (`packages/tools/src/lonora_tools/market.py:99-101`) but is not in the 23-tool
  list. It was reachable: the capability inventory names it and the market chapter says "Use market_symbols to discover
  exact symbols before guessing aliases." (`packages/agent-runtime/resources/system/lonora.md:212`; that chapter is added
  only after a market tool was called, `packages/agent-runtime/src/lonora_agent/skills/system_policy.py:133-141`). The
  model guessed `XAUUSD` anyway (OBSERVED, `1ae9a14c`). The core policy also says "Preserve broker symbols exactly,
  including case and suffix." (`packages/agent-runtime/resources/system/lonora.md:60`).
- Existing text that declares the opposite design: `market_candles` description "without symbol rewriting"
  (`packages/tools/src/lonora_tools/market.py:132`) and the constitution line "Exact broker symbols and owner/account
  scope are immutable server boundaries" (`packages/agent-runtime/resources/constitution/trading-policy.md:1`), plus the
  operating manual: "Preserve broker symbols exactly, including case and suffix." (`packages/agent-runtime/resources/system/lonora.md:60`,
  core) and "Never strip suffixes, substitute an exchange feed or assume one broker's instrument exists at another."
  (`packages/agent-runtime/resources/system/lonora.md:224`, market chapter).

### (iii) Where the change attaches, without a rewrite

1. **`ToolRegistry.dispatch`** (`packages/tools/src/lonora_tools/registry.py:509-516`): every call, direct or bridged, runs
   `prepare_market_arguments` -> `validate_arguments` -> `guard_market_tool` -> handler. It is the single place before
   validation where arguments can be rewritten for all tools.
2. **`prepare_market_arguments(context, name, args, model)`** (`packages/tools/src/lonora_tools/market_binding.py:82-94`):
   returns the arguments after filling the agent's bound account and symbol. Today it is selected by the name prefixes
   in `MARKET_TOOLS` (`packages/tools/src/lonora_tools/market_binding.py:18,40-41`: `market_`, `chart_`, `watch_`, `trade_`, `goal_`,
   `account_`, `list_accounts`), so `agent_inspect`, `peer_send`, `task_*`, `routine_*` are not covered, and it returns early
   without a bound agent (line 89-90). The extension needs a per-parameter table (which field is an account, a symbol, a
   position, a watch, an agent) instead of the name prefix; the 134-row list in `runs/cp-reference-params.tsv` is that table.
   Inputs: `context.db`, `context.brokers`, `context.owner_id`, the agent row, the tool's effect class, the owner's
   language only for the alias table. Outputs: the arguments with the resolved value, or a `LonoraError` carrying the
   candidates (needs the small `LonoraError` extension in `packages/core/src/lonora_core/user_error.py`).
3. **`canonical_broker_symbol` / `catalog_symbol`** (`packages/tools/src/lonora_tools/symbols.py:6-35`): signature
   `(broker, symbol, *, require_exists=False) -> str`. These are the functions the read and trade tools already call, so
   the suffix rule (`symbol_candidates`, `packages/tools/src/lonora_tools/agents.py:72`) and the alias table
   (`packages/contracts/src/lonora_contracts/instrument_names.py:20`, name-to-symbol direction added) can be joined here without
   touching any tool handler. `packages/tools/src/lonora_tools/trade.py:632-635` already resolves before the operation id is hashed, so the exact
   broker spelling reaches the immutable request, the approval card and the journal.
4. **`guard_market_tool`** (`packages/tools/src/lonora_tools/market_binding.py:97-141`): the position existence check at
   lines 133-140 is the place to apply to non-bound agents (needs `context.brokers`, `args["position_id"]`, the account).
5. **`steered_watch`** (`packages/db/src/lonora_db/market_watches.py:115-125`) and `watch_list`
   (`packages/tools/src/lonora_tools/market_watch.py:148-157`): the lookup by exact id and by agent; a by-description lookup
   needs the owner's watch rows (owner scope is principle 10, not designed here).
6. The remaining per-kind lookups are in the handlers listed in the table.

### (iv) Cost

M for symbol and account on the read tools (join two existing functions, add the alias table, default account for a
single connection, tests); L for all five kinds with candidates through the error object and the by-description lookups.
S for the single step "let `catalog_symbol` use `symbol_candidates`'s suffix rule".

### (v) Conflicts

- With the written design "exact symbols are immutable server boundaries" (`packages/agent-runtime/resources/constitution/trading-policy.md:1`) and the two comments/descriptions
  quoted in (ii). The immutable boundary can stay if resolution happens before the operation is formed (as at
  `packages/tools/src/lonora_tools/trade.py:632-635`) and the confirmation shows the exact broker spelling; the model-visible
  descriptions and the constitution line must then be changed in English (`docs/ui-reference/OWNER_DECISIONS.md:13`).
- Money safety: for `trade_execute`, `trade_close_positions` and goal steps a wrong silent resolution moves real money.
  The brief section 4 already decides "one candidate is used silently, several give a card, none gives the nearest
  candidates". Keep that for reads. For money calls I recommend the same rule but the result and the confirmation line must
  name the broker's exact symbol (UNSURE if the owner wants money calls excluded; he did not say).
- Decisions journal (`market_decision_record`) is exact on purpose and append-only; resolve before recording, record the resolved
  name.

### (vi) Safe at once or owner decision

Safe at once: symbol and account resolution for read tools (no authority involved); existence check of `position_id` in
`watch_create`; making `market_symbols` visible (that exposure fix belongs to the sessions fixing visibility). Needs the owner:
nothing for reads. For money calls see (v).

---

## 3. Principle 2: unified error contract and bounded automatic recovery

### (i) What exists today

Where `{ok:false, code}` is built (all in `packages/agent-runtime/src/lonora_agent/tool_dispatch.py`):

| Case | Lines | Object returned |
|---|---|---|
| a `LonoraError` from a handler or validation | 110-117 | `{"ok": False, "code": error.code}`; for `ToolArgumentsError` also `issues` and `retryable: True` (115-116) |
| a route blocked after three failures or an ambiguous financial route | 70-81 | `code` `tool_route_exhausted` or `broker_result_ambiguous`, `recovery.next_action` |
| an interrupted non-read call | 82-95 | `tool_execution_uncertain` |
| timeout or connection error | 118-128 | `tool_read_timeout` / `tool_connection_failure` for reads, else `tool_execution_uncertain` |
| any other exception | 129-138 | `tool_internal_failure` for reads, else `tool_execution_uncertain` (type only is logged) |
| guardrail block | `packages/agent-runtime/src/lonora_agent/tool_guardrails.py:302-310` | `guardrail_blocked`, `executed: False`, `message` |

Then `observe` (`packages/agent-runtime/src/lonora_agent/environment.py:134-216`) stamps every failed result
(it is called for every result, `packages/agent-runtime/src/lonora_agent/tool_block.py:300`) with `result["recovery"]`
(`packages/agent-runtime/src/lonora_agent/environment.py:203-210`), built by `classify` (`packages/agent-runtime/src/lonora_agent/environment.py:35-93`) into the
`ToolRecovery` contract (`packages/contracts/src/lonora_contracts/tool_environment.py:27-33`): `category`, `next_action`, `safe_to_retry`,
`schema_tool` (always `"tool_environment"`), `attempt`, `retry_exhausted`.

**The classes `classify` returns today, verbatim** (`FailureCategory`, `packages/contracts/src/lonora_contracts/tool_environment.py:9-24`): `invalid_tool_arguments`,
`result_too_large`, `temporary_unavailable`, `version_conflict`, `stale_state`, `authorization_required`,
`permission_denied`, `not_configured`, `not_found`, `health_blocked`, `risk_limit_blocked`, `ambiguous_mutation`,
`terminal_domain_failure`. With the `next_action` of each branch (`packages/agent-runtime/src/lonora_agent/environment.py:35-93`):

| Condition | category | next_action |
|---|---|---|
| `tool_arguments_invalid` | invalid_tool_arguments | inspect_schema_and_repair |
| `tool_result_too_large` | result_too_large | narrow_query |
| `broker_result_ambiguous`, `operation_ambiguous`, `tool_execution_uncertain` | ambiguous_mutation | reconcile_before_any_resend |
| a code in `TRANSIENT_READ_CODES` | temporary_unavailable | inspect_health |
| `version_conflict`, `stale_state`, `workspace_revision_conflict` | version_conflict | reload_authoritative_state |
| `quote_stale`, `market_data_stale`, `market_evidence_stale`, `stale_evidence` | stale_state | refresh_evidence |
| `approval_required`, `device_registration_required`, `device_authorization_required` | authorization_required | request_owner_authorization |
| `tool_not_allowed`, the three `agent_*_mismatch` codes, `financial_authority_required`, `trading_restriction_active`, `restriction_all_mutations_requires_owner_message`, `supervision_personal_agent`, `supervision_revoke_own_oversight` | permission_denied | respect_scope |
| a code starting `risk_` | risk_limit_blocked | inspect_risk_assessment |
| a code ending `_unconfigured`, `model_not_configured`, `search_not_configured`, `research_provider_not_configured` | not_configured | inspect_authorized_alternative |
| a code ending `_not_found` | not_found | inspect_existing_state |
| `broker_reconciliation_pending`, `market_health_blocked`, `trading_disabled`, `emergency_stop` | health_blocked | wait_for_authoritative_recovery |
| anything else | terminal_domain_failure | alternate_route |

REPRODUCED with the real `classify` (`runs/cp-classify.out`): `symbol_not_found`, `broker_account_not_found`,
`market_watches_not_found`, `agent_not_found`, `position_not_found` all give `not_found` /
`inspect_existing_state`; `symbol_ambiguous` gives `terminal_domain_failure` / `alternate_route`; `volume_required` gives
`terminal_domain_failure`; `broker_rate_limited` and `broker_candles_timeout` give `terminal_domain_failure` with
`safe_to_retry=False`; only `TRANSIENT_READ_CODES`
(`packages/core/src/lonora_core/runtime_failure.py:10-21`) give `temporary_unavailable` with `safe_to_retry=True`.

What the model received in production (OBSERVED, trace Part 4 findings 3 and 6, run `1ae9a14c`):
`{"ok":false,"code":"symbol_not_found","recovery":{"category":"not_found","next_action":"inspect_existing_state",
"safe_to_retry":false,"schema_tool":"tool_environment","attempt":1,"retry_exhausted":false}}`, and the same block for
`broker_account_not_found`. No candidates, no sentence. The model ignored it and wrote to the owner.

Recovery that exists and is automatic:

- Transient reads: a failed read-only call with a transient code gets `safe_to_retry`
  (`packages/agent-runtime/src/lonora_agent/environment.py:92`); `run_and_record_segment` then schedules the retry with a backoff
  of `2**attempt` seconds and releases the worker (`packages/agent-runtime/src/lonora_agent/tool_block.py:309-328`,
  `packages/agent-runtime/src/lonora_agent/environment.py:219-231`); after three failures `safe_to_retry` is withdrawn and
  `retry_exhausted` set (`packages/agent-runtime/src/lonora_agent/environment.py:206-209`). The deadline is stored in the checkpoint, so a
  server update does not lose it.
- Repeats: the same failing call is refused after three failures (`packages/agent-runtime/src/lonora_agent/environment.py:127-131`,
  `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:70-81`); warnings at 2 and 3 failures, halt at 8
  (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:56-58`, `packages/agent-runtime/src/lonora_agent/tool_guardrails.py:329-337`). REPRODUCED
  (`runs/cp-contract.out` S1): four identical `market_snapshot("XAUUSD")` calls give `symbol_not_found` three
  times (the second and third carry the guardrail warning "market_snapshot has failed 2 [3] times with identical arguments")
  and then `tool_route_exhausted` (re-run by the checker: `chk/p18/contract.out`).
- Invalid arguments: `issues` and `retryable: true`, with the prompt rule at
  `packages/agent-runtime/resources/constitution/tool-policy.md:3` and `packages/agent-runtime/resources/constitution/tool-policy.md:7` ("follow typed recovery information").
- Round budget: 24 rounds per slice by default (`apps/api/src/lonora_api/env.py:97`), with a budget notice
  (`packages/agent-runtime/src/lonora_agent/tool_loop.py:471-488`).
- Per-tool error documentation: `recovery_metadata` lists `common_error_codes`
  (`packages/tools/src/lonora_tools/environment.py:34-57`).

### (ii) What is missing

- The fields `class`, `retryable` (except for argument errors), `hint`, `candidates`, `next_actions`. Searched:
  `grep -rn '"hint"'` over `packages` and `apps` (`*.py`) finds hints only in the card contract and its compiler
  (`packages/contracts/src/lonora_contracts/genui.py:271`, `packages/agent-runtime/src/lonora_agent/genui_compile.py:683,706`),
  none in tool errors.
- `next_action` is a bare token ("inspect_existing_state") with no instruction and no argument.
- Nothing recovers a resolution error automatically: the loop only hands the error back to the model, which
  decided to answer the owner (OBSERVED `1ae9a14c`).
- Transient set too narrow: `broker_rate_limited` (429, `packages/adapters/src/lonora_adapters/brokers/metaapi.py:64-65`) and
  `broker_candles_timeout` (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:70-72`) are not in `TRANSIENT_READ_CODES`, so they
  are not retried (REPRODUCED, `runs/cp-classify.out`).
- The loop has no counter for "recovery rounds" apart from the per-route failure count.

### (iii) Where the change attaches

1. **`observe`** (`packages/agent-runtime/src/lonora_agent/environment.py:134-216`): `observe(state, call, tool, result) -> record`
   mutates `result["recovery"]`. It already sees every result, including synthetic ones, so it is the single place to
   complete the contract (`class`, `retryable`, `hint`) without touching a tool. `classify` (35-93) returns the dict;
   extending its return value is additive. The category names are pinned by
   `tests/test_agent_environment.py:40-62` and `tests/test_agent_environment.py:86`, so the new `class` is a second field,
   not a rename. The brief's six classes do not map one to one onto the 13 categories (for example `risk_limit_blocked`,
   `ambiguous_mutation`, `stale_state`, `result_too_large` have no named home); that mapping is the first design question.
2. **`dispatch_call`'s `except LonoraError`** (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:110-117`): builds the result from `error.code`.
   It needs to copy optional `candidates` and `next_actions` from the error. `LonoraError`
   (`packages/core/src/lonora_core/user_error.py:1-14`) needs optional attributes for them.
3. **Automatic recovery for transient errors** exists at `packages/agent-runtime/src/lonora_agent/tool_block.py:309-328`; widening it is a change to
   `TRANSIENT_READ_CODES` (`packages/core/src/lonora_core/runtime_failure.py:10-21`).
4. **Automatic recovery for resolution errors**: the cheapest attachment is inside the resolver of principle 1 (resolve before the
   handler, so there is nothing to retry). Where a corrected call must be re-dispatched, the same segment hook as the
   transient retry (`packages/agent-runtime/src/lonora_agent/tool_block.py:297-328`) can run it once; the bound can live in
   `environment_state(state)` (`packages/agent-runtime/src/lonora_agent/environment.py:96-101`) and reset where guardrails reset
   (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:218-223`). Inputs: the failed call, `recovery.next_actions`
   (a ready corrected call). Output: one more `dispatch_call` result in the same round.
5. `hint` text is model-facing, so English (`docs/ui-reference/OWNER_DECISIONS.md:13`); the owner never sees it
   (the brief's principle 12).

### (iv) Cost

S to add `class`, `retryable`, `hint` (additive, `observe` and `classify`, update the pinned tests); S to widen the transient set;
M to carry `candidates` and `next_actions` through `LonoraError` and `dispatch_call`; M to L for automatic recovery of resolution
errors (depends on principle 1).

### (v) Conflicts

- `hint` and `next_actions` must never suggest a route around an owner restriction or a risk limit: `classify` marks those as
  "never route around" (`packages/agent-runtime/src/lonora_agent/environment.py:62-63`, `packages/agent-runtime/src/lonora_agent/environment.py:70-73`;
  test `tests/test_agent_environment.py:86`).
- Automatic recovery must stay out of financial and ambiguous calls: financial tools are never retried unseen
  (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:43-69`, `packages/agent-runtime/src/lonora_agent/environment.py:42-43`); the registry rejects a financial
  read (`packages/tools/src/lonora_tools/registry.py:143-152`).

### (vi) Safe at once or owner decision

Safe at once: all of (iii) 1 to 3. Recovery of resolution errors on reads: safe. No owner decision. Note for the designers: the
production symptom [9] to [14] came from an error the model could have recovered from with `market_symbols`
(not native) and an unhelpful block; the contract fix alone is not enough without principle 1 and the tool exposure fix.

---

## 4. Principle 3: act, do not offer

### (i) What exists today

- Prompt text only: `packages/agent-runtime/resources/constitution/tool-policy.md:3` ("continue the already requested
  reversible work in the same turn"); the core operating policy sent in every run (inserted by
  `packages/agent-runtime/src/lonora_agent/skills/system_policy.py:146-161` from the `core` section,
  `packages/agent-runtime/resources/system/lonora.md:9-165`): "For requested action, inspect the smallest relevant scope and continue
  the authorized work." (`packages/agent-runtime/resources/system/lonora.md:120`) and "Do not ask the owner whether to perform
  analysis, inspect a chart or build a plan they already requested: do that reversible work first."
  (`packages/agent-runtime/resources/system/lonora.md:135`); the permission frame for the autonomous level ("decide whether/when to trade, size
  and manage positions, and persist useful monitoring": `packages/agent-runtime/src/lonora_agent/context/permissions.py:139-148`).
- A bounded "continue instead of ending" mechanism, but for Task runs only: `apply_stop_gates`
  (`packages/agent-runtime/src/lonora_agent/stop_gates.py:86-129`) returns `StopGateVerdict(continue_turn, nudge, exhausted)`
  (`packages/agent-runtime/src/lonora_agent/stop_gates.py:57-63`) with at most two nudges per review epoch
  (`packages/agent-runtime/src/lonora_agent/stop_gates.py:41`), the counter kept in the checkpoint under `continuous_stop_gate` and
  `task_completion_gate` (`packages/agent-runtime/src/lonora_agent/stop_gates.py:42-43`), reset at real owner input
  (`packages/agent-runtime/src/lonora_agent/stop_gates.py:66-69`, callers `packages/agent-runtime/src/lonora_agent/steering.py:47`,
  `packages/agent-runtime/src/lonora_agent/loop_restore.py:77,103`). `final_answer` turns a `continue_turn` verdict into a runtime notice and
  returns `None` (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:170-174`), delivered by `append_notice`
  (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:67-81`, a user-role `tool_observation` message at lines 27-31).
  Test of the pattern: `tests/test_tool_loop_execution.py:575`.
- An empty conversational reply gets a nudge and another round (`packages/agent-runtime/src/lonora_agent/tool_loop.py:573-579`).
- The size of the problem (my count, `runs/cp-count-offers.out`, narrow Arabic pattern on the last two lines):
  21 of the 37 text replies match the pattern in their last two lines
  ([10], [14], [16], [18], [20], [22], [24], [26], [29], [35], [37], [41], [53], [55], [59], [63], [65], [71], [75], [77], [81]);
  the checker re-ran the script with the same result. Two of the 21 ([24], [55]) are questions for a parameter, not offers (see the
  breakdown below), so the pattern finds 19 offers. Three replies offer a step without the pattern ([12] "أبحث عن التسمية الصحيحة فورًا",
  [31] "أقدر أنفّذ إدارة للمركز الحالي أو أضع خطة", [73] "أقدر بدل ذلك أعمل **فحصًا مباشرًا**"; checker's reading), so about 22 of 37
  by reading; the brief says about 25. Of the 21 pattern matches, [75], [77] and [81] ran on main. By kind (my reading of each reply): a read or an analysis offered ([10], [14], [16], [18], [20], [22], [29], [59], [63]: price, trend, charts, a search for the
  symbol name); an own-state step offered ([37], [41], [53], [65], [71], [75], [77]: follow it, watch it, tidy or cancel the watches, try `watch_cancel`); an
  order-related step offered ([26], [35]: stop loss and target, a conditional close); a question for a missing parameter, not an offer ([24], [55]); a general offer ([81]).
- REPRODUCED on main (`runs/cp-contract.out` S3): the reply "وضعه الآن: المركز مفتوح. ... إذا تريد، أراجع لك **السعر الحالي**
  ..." with a trailing suggested reply is committed unchanged after one model turn; `stop-gate keys in execution_state` is empty.

### (ii) What is missing

No detector of a reply that ends with an offer, and no end-of-turn gate for conversation runs: `task_stop_gate` returns early
without a Task (`packages/agent-runtime/src/lonora_agent/stop_gates.py:153-155,180-181`). Searched: `grep -rn` for offer wording
("إذا تريد", "إذا أردت", "if you want", "would you like") in `packages/agent-runtime/src` and `packages/core/src` finds nothing;
the only reply-wording pattern in the runtime is `EFFECT_CLAIM` (executed-trade verbs, `packages/agent-runtime/src/lonora_agent/public_stream.py:11-19`).

Why the three runs named in the lead's reading of the trace (point 12) tripped nothing: for `ddae66ad`,
`e343c96a` and `fb1d4b5a` the nearest check is `task_stop_gate`; it fires only for a run with `task_id`
(`packages/agent-runtime/src/lonora_agent/stop_gates.py:153-155`). These are chat runs with no Task, so it returns at once. Even for a Task run it is
structural (`continuous`, `incomplete_steps`) and does not read the reply (`packages/agent-runtime/src/lonora_agent/stop_gates.py:99-104`). No check in
`stop_gates.py` or in the PR #42 files was "supposed" to fire for those replies; they are outside the scope of every existing check
(`runs/cp-guards.out`, cases 1, 2, 5c).

### (iii) Where the change attaches

1. **`final_answer`** (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:155-184`): `(context, state, messages, text, metadata, save, *, outcome_line) -> LoopOutcome | None`.
   `None` continues the turn. Add a second gate beside `task_stop_gate` (line 170) for conversational runs
   (`is_conversational`, `packages/core/src/lonora_core/run_state.py:33-34`), using the same verdict type, the same notice delivery and a new
   checkpointed counter next to `_STATE_KEY` (`packages/agent-runtime/src/lonora_agent/stop_gates.py:42-43`) reset by `reset_stop_gate`
   (`packages/agent-runtime/src/lonora_agent/stop_gates.py:66-69`). `apply_stop_gates` (`packages/agent-runtime/src/lonora_agent/stop_gates.py:86`) takes
   `(state, *, continuous, incomplete_steps)`; either add a third mode or a sibling function with the same counter rules.
2. Inputs the gate needs: the reply `text` (argument 4 of `final_answer`); the messages since `owner_request_start`
   (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:40-48`) so it can see whether a tool already ran in this request; the registry
   (effect class of the step the offer names: read-only or an own-state change); the run trigger. Output: a `StopGateVerdict`
   with an English nudge ("execute the step you offered; the owner asked for it"). For a conversation run `exhausted` must mean "deliver the
   reply", not `request_owner_attention` (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:175-178` is built for Task work).
3. The same check must be called from the other exits listed in 1.1 item 4 (`finish_turn`, silent final).
4. How "ends with an offer" is detected is the design choice. The code offers three signals and none is wording-free
   except the second: (a) a pattern list of Arabic and English offer phrases (matching data may stay Arabic,
   `docs/ui-reference/OWNER_DECISIONS.md:13`, but see (v)); (b) the model's own optional `<suggested_reply>` on the same reply
   (`packages/agent-runtime/src/lonora_agent/model_runtime.py:195`, stored at `packages/db/src/lonora_db/schema.py:266`): a conversational answer that carries a
   suggested assent such as "ياريت" is an offer by the model's own declaration. Whether production replies carry such
   suggestions is not in the trace (section 11); (c) a second model call, which `docs/ui-reference/OWNER_DECISIONS.md:12` disfavours for answer shape.

### (iv) Cost

M (gate, counter, three exits, tests on the pattern of `tests/test_tool_loop_execution.py:575`); L if a wording detector needs an
Arabic and English corpus and the planned `scripts/agent_eval` scenarios.

### (v) Conflicts

- Money: the nudge must never push the model toward a money step. Only reads and own-state steps (for example watch
  create or cancel) are "act now"; a financial step stays with the signed grant or the approval card, checked at the single
  executor (`docs/trading-safety.md:7-9`). The gate must exclude any offer whose step is a `financial` tool (flag on
  `Tool.financial`, `packages/tools/src/lonora_tools/base.py:73`).
- Reply-wording tension: `packages/core/src/lonora_core/public_reply.py:4` and `docs/ui-reference/OWNER_DECISIONS.md:12` (see 1.5).
- PR #42's design rule "The reply and its card are never replaced" (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:9`): a gate that
  continues the turn leaves the first assistant message in the transcript (`packages/agent-runtime/src/lonora_agent/tool_loop.py:580-587`). UNSURE what the
  clients show for text already streamed in a turn that is then continued (not tested).

### (vi) Safe at once or owner decision

Safe at once: the gate for read-only offers (zero authority). Owner decision: which own-state steps count as "inside the
delegation" for acting without asking (watch create and cancel are the cases in the conversation), and whether a wording
detector is acceptable given `docs/ui-reference/OWNER_DECISIONS.md:12`.

---

## 5. Principle 4: a short approval executes the pending offer

### (i) What exists today

- `suggested_reply`: the model may end a conversational answer with one tag (`packages/agent-runtime/resources/prompts/suggested_reply.md:2`: "what the
  owner would most likely say next ... at most 60 characters"), loaded for owner-started runs
  (`packages/agent-runtime/src/lonora_agent/context/builder.py:131`), split off in `model_turn`
  (`packages/agent-runtime/src/lonora_agent/model_runtime.py:195`), validated and stored on the message row
  (`packages/db/src/lonora_db/runs.py:336-387`, column `packages/db/src/lonora_db/schema.py:266`), sent to clients (`packages/db/src/lonora_db/messages.py:70`).
  REPRODUCED (`runs/cp-contract.out` S3): the offer reply stores `suggested_reply: "ياريت"`.
- Question cards: the pending question and the owner's chosen id live in the run checkpoint
  (`packages/db/src/lonora_db/messages.py:528-552`: `input_requests` item goes from `pending` to `answered` with
  `selected_choice_id`), and the model sees the earlier question's choices in history as `<question_choices>`
  (`packages/agent-runtime/src/lonora_agent/context/history.py:135-173`).
- Request start marker `owner_request_start` (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:40-48`).

### (ii) What is missing

- Nothing records "the agent offered X" and nothing links a short owner reply to it. REPRODUCED (`runs/cp-contract.out` S4): for
  «ياريت» after the offer the model receives only the plain history (user, assistant, user); the key check for
  `pending_offer`, `open_request`, and the suggested value in the request is false for all four.
- The stored suggestion is never given back to the model. Searched: `grep -rni "pending_offer|open_request"` over `packages`, `apps`, `docs`
  finds nothing in code (the only hits are the audit's own notes under `docs/research/lonora-runtime-notes/`, committed after `9f5b1da`); the per-thread state columns of `ThreadRow` are only `options` (`{"web_search": bool}`) and `context_summary` / `summary_seq`
  (`packages/db/src/lonora_db/schema.py:220-240`), and `thread_options` reads only the keys it knows
  (`packages/db/src/lonora_db/threads.py:13-16`, `packages/contracts/src/lonora_contracts/domain.py:147-151`).
- OBSERVED: [35] offered "أضع لك **أمر إغلاق مشروط** أو أتابعه لحظة بلحظة على هذا المستوى"; [36] «طيب»; run `ac7e6426` answered with a status read (`account_read` and
  `market_quote` only, trace Part 2) and no watch or order was created. The same happened after [37] → «تمام» → [39] (`01c07781`, reads only),
  after [41] → «تم» → [43] (`8114abdd`, no tool call, "مراقب") and on main after [75] → «جرب» → [77] (`e79b4bf2`, `watch_create` instead of
  `watch_cancel`). Read offers, by contrast, were executed from plain history: [14] → «ياريت» → [16] (`af5f00b3`, `market_quote` +
  `market_snapshot`), [16] → «ياريت» → [18] (`6f8ff964`, `market_snapshot`), [20] → «نعم 3 صور» → [22] (`e7ca6fb6`, three `chart_snapshot`)
  (trace Part 1 and Part 2). So the gap is own-state offers, not short replies as such.
- Prompt text that already asks for this, sent in every run: "A short reply continues the preceding request; do not treat it as an
  isolated new task or forget a previously chosen side." (`packages/agent-runtime/resources/system/lonora.md:130`, core section).
- UNSURE whether a 👍 reaction (visible in the export at [41] and [43]) reaches the agent as an acceptance (reactions: `docs/ui-reference/OWNER_DECISIONS.md:54`); not traced.

### (iii) Where the change attaches

1. **History building** (`packages/agent-runtime/src/lonora_agent/context/history.py:135-173`): it already decorates a past assistant
   message with a structured block (`<question_choices>`) taken from side state. The same loop can decorate the last assistant message with a
   `<pending_offer>` block from the stored `suggested_reply`. Input: the previous assistant row and its `suggested_reply`; output: a text block next to
   that message.
2. **Run start** (`restore_checkpoint`, `packages/agent-runtime/src/lonora_agent/loop_restore.py:31-65`, which already calls `record_request_start` at
   line 58): add a runtime notice via `append_notice` when the owner's message is a short assent to the last offer ("the owner accepted your
   previous offer: <text>; do it now"). Two ways to know it is a short assent: the message equals the stored `suggested_reply` (no wording), or an Arabic and
   English list of assent words (allowed as matching data, `docs/ui-reference/OWNER_DECISIONS.md:13`).
3. **Durable "open request"** (the brief's principle 9): a conversation run is created per owner message, so per-run `execution_state` does not carry an offer to the
   next run. The offer must be stored at thread or message level (a new column or table; `docs/ui-reference/OWNER_DECISIONS.md:17`: no
   backfill needed). State must be in the database, not in memory: each server update recreates the containers (`TIMELINE_CORRECTION.md`); a run
   in flight survives because its checkpoint is saved at every step (`packages/agent-runtime/src/lonora_agent/tool_loop.py:117-126`); OBSERVED: run `57dcaeb0` waited eight
   seconds across the 09:54:14-09:54:57 update (trace Part 2) and lost nothing. Today nothing is held in memory for offers, so an update loses no offer; any new
   state must keep that property.

### (iv) Cost

S for items 1 and 2 using the stored suggestion; M for a durable, expiring, superseding pending-offer record.

### (v) Conflicts

Money safety is the main one: typed agreement is not approval (`packages/tools/src/lonora_tools/trade.py:753-757`; the permission frame text "chat agreement ... grants no authority" at
`packages/agent-runtime/src/lonora_agent/context/permissions.py:171-172`; `packages/agent-runtime/resources/skills/trade-management/SKILL.md:30-33`, step 4). A short «طيب» may execute a read or an own-state offer; for a financial offer it may at most
let the model call `trade_execute`, and the grant or the real Approve control decides. It must never mark or create an approval. Q23 limits suggestions to 60
characters and conversational answers (`docs/ui-reference/OWNER_DECISIONS.md:51`); using it as the offer carrier keeps within that.

### (vi) Safe at once or owner decision

Safe at once: items 1 and 2 for reads and own-state offers. Owner decision: how long an offer stays pending, whether a 👍 reaction counts as acceptance,
and whether a short assent may trigger a financial call inside an active signed grant (I recommend yes only inside the grant; the executor still re-checks).

---

## 6. Principle 5: a condition becomes a durable trigger

### (i) What exists today

- `watch_create` supports the whole case: `kind="position"`, `position_id`, `metric="profit"`, `condition="above"`, `level`, `prompt`
  (`packages/contracts/src/lonora_contracts/market_watch.py:15,24,27-28,36-37,74,84-88`). REPRODUCED (checker re-ran it on database 12: `chk/p18/principles.out`): the Personal Agent created
  `watch_create(kind="position", position_id="2217873130", metric="profit", condition="above", level="100", dedupe_key=...)` with
  `ok: true` (`runs/cp-principles.out`, P5).
- A fired watch is a run with trigger `watch`, which is in `WORK_TRIGGERS` (`packages/contracts/src/lonora_contracts/runs.py:7-9`), and its scope is `full`
  unless the run is observe-only (`packages/tools/src/lonora_tools/base.py:53-58`), so the woken run can call `trade_execute` or `trade_close_positions` under the grant.
- Broker-side conditional: `trade_execute` with `action="modify_position"` and `stop_loss` / `take_profit`
  (`packages/contracts/src/lonora_contracts/trading.py:18-29,54-66`; description `packages/tools/src/lonora_tools/trade.py:753-757`). In production
  [35] `account_read` showed `stop_loss: null, take_profit: null` (trace Part 4 finding 8, run `94d50998`) and the model never set them.
- Goal plans with a watch step and a trade step (`packages/tools/src/lonora_tools/trading_goal.py:484-545`, step kinds `packages/contracts/src/lonora_contracts/trading_goal.py:50`); `goal_wait` "never
  places a trade directly." (`packages/tools/src/lonora_tools/trading_goal.py:526`).
- General prompt text toward watches: core policy "Use actual watches, schedules or task waits for future work; do not promise to remain awake by
  thinking continuously." (`packages/agent-runtime/resources/system/lonora.md:127`, every run) and, in the `tasks` chapter only, "Use watch_create/watch_list
  for supported market/account/position/calendar/composite conditions." (`packages/agent-runtime/resources/system/lonora.md:433`).
- Skill `market-watch` ("Only say this after persistence succeeds.") and the tool description "It wakes this agent to reassess and never trades."
  (`packages/tools/src/lonora_tools/market_watch.py:239`).
- The quote already carries `profit_tick_value`, `loss_tick_value`, `tick_value_basis`; the instrument carries `tick_size`, `contract_size` (trace Part 4 #28-29,
  run `00f7b6bc`).

### (ii) What is missing

- Nothing maps "when profit reaches X, close it" to a position watch or a take-profit (the general watch lines above do not). Searched:
  `grep -rn "modify_position\|kind=position\|position_id"` over `packages/agent-runtime/resources` (constitution, system manual, prompts, playbooks, skills) finds nothing;
  the checker's second search `grep -rniE "take.?profit|stop.?loss|kind.?position|position watch"` finds only unrelated lines (`packages/agent-runtime/resources/system/lonora.md:269,353,366`).
  The skills are not in chat context anyway (`packages/agent-runtime/src/lonora_agent/context/skills.py:198-200,239`; no `skill_view` in the conversation).
- No helper turns a money target into a price: `profit_tick_value` is parsed (`packages/adapters/src/lonora_adapters/brokers/normalize.py:57,65`) and declared
  (`packages/contracts/src/lonora_contracts/market.py:33`) and used by no code; `loss_tick_value` feeds risk limits and sizing
  (`packages/trading/src/lonora_trading/position_sizing.py:104`, `packages/trading/src/lonora_trading/risk_limits.py:10`). The brief's expected 4052.82 for +2 USD on 0.01 lot of the
  gold contract is `open_price + target / (volume * profit_tick_value / tick_size)` with the values the model had in hand (4050.819, 0.01, 0.1, 0.001). The
  trade-management skill even says "do not convert cent-account units or invent tick economics" (`packages/agent-runtime/resources/skills/trade-management/SKILL.md:20`), so a
  deterministic helper is the safe way, not the model's arithmetic.
- No existence check of `position_id` for the Personal Agent (REPRODUCED, a fake id was accepted: `runs/cp-principles.out`, P5; code `packages/tools/src/lonora_tools/market_binding.py:133-140` runs only for bound agents).
- No check that a "I am watching / مراقب / I will close it" reply has a saved watch or order. OBSERVED: `8114abdd` [43], `6e4aa88f` [47], `7e7da121` [57] claimed monitoring with no
  watch on XAUUSDm (trace Part 1 Q4 note; Part 2 shows no watch tool call in those runs); REPRODUCED all three (`runs/cp-guards.out` cases 4a, 4b, 4c, "no XAUUSDm watch exists").
  The continuous-work nudge ("only a successful saved wait can support a promise to follow up", `packages/agent-runtime/src/lonora_agent/stop_gates.py:45-54`) reaches Task runs only.
- `watch_create` accepts any prompt: the production placeholder watches carry the prompts "placeholder" and "cancel-test" (trace Part 1 Q4).
- No server-side "action" on a watch: a watch only wakes the agent (by design).

### (iii) Where the change attaches

1. Model-facing guidance must be in text the chat run always sees: the tool descriptions of `watch_create` (`packages/tools/src/lonora_tools/market_watch.py:239`) and `trade_execute`
   (`packages/tools/src/lonora_tools/trade.py:753-769`) or the constitution (`packages/agent-runtime/resources/constitution/tool-policy.md`) or the core section of the operating manual (`packages/agent-runtime/resources/system/lonora.md:9-165`), in English. The skills and the domain chapters are not.
2. Money-to-price helper: next to `packages/trading/src/lonora_trading/position_sizing.py` (pure function) and exposed either as a field of an existing read result
   (`market_position_size`, which is also not native: `packages/tools/src/lonora_tools/position_sizing.py:22`) or as a new read tool. Inputs: volume, side, open price, target amount, quote
   tick values, instrument `tick_size` and volume step. Output: a price. No broker call beyond the two reads the model already makes.
3. Existence check of `position_id`: `guard_market_tool` (`packages/tools/src/lonora_tools/market_binding.py:133-140`) extended beyond bound agents (see principle 1).
4. The claim check is the same gate as in principle 8 (a reply that says it is watching needs a successful `watch_create` or `modify_position` in this request).
5. Durable behaviour already exists server-side (watch rows polled every 30 s; trace Part 1 Q4 note shows `updated` at 12:29 for disabled rows, which is the lifecycle defect being fixed elsewhere).

### (iv) Cost

S for guidance text and the position existence check; M for the helper and its tool exposure; M to L for the claim check (shared with principle 8).

### (v) Conflicts

- Do not give a watch a server-side action that sends orders: that would be a second path to move money besides the single executor (`docs/trading-safety.md:7-9`) and "no shadow
  trading". Keep it as the existing design: broker take-profit / stop-loss through `trade_execute modify_position`, or a watch whose wake run closes through `trade_execute` /
  `trade_close_positions`.
- A wake run that must close at night needs a live signed grant or it raises an approval card nobody answers; a broker-side take-profit survives outages. Which one is the
  default is a product choice (the brief accepts either). Exits stay admissible when trading is stopped (`docs/trading-safety.md:18`); tightening a stop is risk-reducing, moving it
  away counts as new risk (`packages/tools/src/lonora_tools/trade.py:176-178`), so protection edits must keep the direction rule.

### (vi) Safe at once or owner decision

Safe at once: guidance text, position existence check, the pure helper. Owner decision: default for "close at +$X" (broker take-profit or watch plus wake), and that a stated condition
without a saved trigger is not to be promised.

---

## 7. Principle 6: defaults for missing parameters and a one-card plan, inside the signed delegation

### (i) What exists today

- The chat run's permission frame says what the autonomous level may do and shows the grant's scope data, including the caps
  (`packages/agent-runtime/src/lonora_agent/context/permissions.py:61-100`, the field list is inside that range, and "size and manage positions" at `packages/agent-runtime/src/lonora_agent/context/permissions.py:141`). Full delegation by definition has no caps:
  `maximum_order_volume`, `maximum_symbol_volume`, `maximum_positions`, ... are all `None` (`packages/contracts/src/lonora_contracts/account_authority.py:27-34,37-49`).
- The explicit rule "choose lot size yourself; do not ask for routine parameters" exists in two places the conversation run does not read: the trade-management skill
  (`packages/agent-runtime/resources/skills/trade-management/SKILL.md:23-24`) and the description of the Task created at signing
  (`packages/auth/src/lonora_auth/account_authority.py:145-150`), the prompt of the Task's own work run (the conversation run never sees the Task text: the chat
  context builder adds no Task description, `packages/agent-runtime/src/lonora_agent/context/builder.py:100-175`; no `skill_view` was called, trace Part 2).
- CORRECTION by the checker (lead point 13): the conversation run does see the permission to choose the size, in two places sent in every run.
  The core operating policy: "Explicit full management lets you choose size, stops and targets without per-order approval or default volume/activity quotas,
  until revoked or its optional expiry." (`packages/agent-runtime/resources/system/lonora.md:106`, core section 9-165, present in every build of the conversation),
  and the permission frame of the autonomous level: "decide whether/when to trade, size and manage positions ... Matching actions need no repeated
  per-operation approval." (`packages/agent-runtime/src/lonora_agent/context/permissions.py:140-142`). What the chat run lacks is only the explicit prohibition
  "Do not ask"; the core policy even says "Ask for owner preferences or missing financial limits; derive technical entry, invalidation, size and target proposals
  from current broker evidence when the owner's limits allow it." (`packages/agent-runtime/resources/system/lonora.md:136`), which a model can read as licence to ask.
  So [24] is a model failure against prompt text it had, with no runtime check behind it.
- `volume` is mandatory only when the model calls `trade_execute` for a buy or sell (`packages/contracts/src/lonora_contracts/trading.py:77-81`; REPRODUCED: `trade_execute(buy)` without volume returns
  `tool_arguments_invalid` with issue `volume_required`, `runs/cp-contract.out` S1).
- Sizing tools: `market_position_size` (risk budget and stop distance, `packages/tools/src/lonora_tools/position_sizing.py:22`, `packages/trading/src/lonora_trading/position_sizing.py`), not native.
- The question-card mechanism with choices exists (`wait_for_input`, used in `ddae66ad` and `e343c96a`, trace Part 4), so "one card with proposed numbers" has a vehicle.
- OBSERVED [24] (`00f7b6bc`): the model had `account_read` (balance 13944.57, no positions), `market_quote` and `market_instrument` (min 0.01) in hand, called no trade tool and wrote
  «ما أقدر أنفّذ صفقة شراء بدون حجم الصفقة» (trace Part 4 finding 7). [31] (`cc8399d7`): «لا أستطيع فتح 10 صفقات...» with zero tool calls.

### (ii) What is missing

- A source of a default size. The grant has no default (full delegation has no caps); the owner chose no daily loss limit (export [8]: «لم يُضبط حد للخسارة اليومية»), so no risk budget exists
  for `market_position_size`. Searched: `grep -rn "default_volume\|default lot"` over `packages/trading`, `packages/tools`, `packages/agent-runtime/src` finds nothing.
- Only the permissive wording above reaches the chat run (not the explicit "do not ask"), and nothing checks a reply that asks the owner for a delegated parameter.
- No "plan for a vague request" tool; the brief's [30] to [35] case (10 trades, close when profit is good) ended with the plan silently narrowed to the existing position ([35]).
- The permission frame does not know the instrument's volume limits (that needs a broker read), so it cannot state a default by itself.

### (iii) Where the change attaches

1. `permission_guidance` (`packages/agent-runtime/src/lonora_agent/context/permissions.py:61`): `(state, *, observe_only, provisional_approval_required, restrictions, risk_limits, trading) -> str`. It
   already says what the autonomous level may do and carries the grant's caps; add the delegated-parameter rule and the stated default in one English sentence (inputs: the active authorities and the
   account money limits, both already passed in; the instrument minimum is not available here).
2. A default value as data in a read result the model already calls (`market_instrument` or `account_read`), for example a suggested default volume derived from the instrument's `volume_min`,
   `volume_step`, the grant's `maximum_order_volume` and the account limits. Inputs: instrument spec, grant caps, risk limits. Output: one number with its source.
3. The stop gate of principle 3 for a reply that asks the owner for a parameter the delegation already covers.
4. One-card plan: `wait_for_input` (`packages/tools/src/lonora_tools/runtime_control.py:22` for the input model, the tool registered at `packages/tools/src/lonora_tools/runtime_control.py:200`) or a generated card; question and choices must be in the owner's language.
5. The confirmation line ("opened 0.01 lots, the instrument minimum") is the model's reply, covered by principle 8.

### (iv) Cost

S for item 1; M for item 2; M for the plan card including the evaluation scenarios.

### (v) Conflicts

- Money safety: a default must never exceed any cap or limit and never enlarge the scope ("never enlarge scope yourself", `packages/agent-runtime/src/lonora_agent/context/permissions.py:143-144`). The server
  stays the judge: `risk_*` codes block before sending (`packages/agent-runtime/src/lonora_agent/environment.py:70-73`) and the executor re-reads the grant and limits
  (`docs/trading-safety.md:7-9`). With no limit configured the unset limit "is not enforced" (`packages/agent-runtime/src/lonora_agent/context/permissions.py:165`), so the only protection of a default is the number chosen.
- Q17 and Q18 (`docs/ui-reference/OWNER_DECISIONS.md:45-46`): full delegation means no cap of its own; the owner chose "money_limit none" at signing.

### (vi) Safe at once or owner decision

Safe at once: making the existing rule visible to the chat run. Owner decision: the default size when no limit exists. I recommend the instrument minimum volume (here 0.01), stated in the
confirmation line; it is the smallest exposure. For "10 trades" a count and a total-size ceiling are also a policy choice for the owner.

---

## 8. Principle 7: no claim of inability without evidence

### (i) What exists today

- `tool_environment` (`packages/tools/src/lonora_tools/registry.py:155-166`; handler `inspect_environment`, `packages/tools/src/lonora_tools/registry.py:336-397`): input `EnvironmentInput`
  (`tool_name`, `query`, `offset`, `limit`; `packages/tools/src/lonora_tools/environment.py:10-19`); with a `tool_name` it returns one tool, with a `query` a ranked list of up to 12, with
  neither a paginated list of all permitted tools. Its description: "Discover capabilities by query using concise English catalog terms, list bounded metadata, or inspect an exact tool_name for its input schema and current
  availability. Call a discovered tool that is not in your native tool list through tool_call. Discovery grants no authority." (`packages/tools/src/lonora_tools/registry.py:157-161`). The `query` field says: "Use English
  terms for the first-party catalog" (`packages/tools/src/lonora_tools/environment.py:16`).
- `tool_call` bridges any registered name (`packages/tools/src/lonora_tools/registry.py:167-178`, `resolve_call` `packages/tools/src/lonora_tools/registry.py:180-208`); `proposed_names` reads every target a call proposes
  (`packages/tools/src/lonora_tools/registry.py:101-135`).
- The capability inventory block in every run lists all permitted names by family and says to inspect "before claiming an ability is absent"
  (`packages/tools/src/lonora_tools/registry.py:406-473`, sentence at 428-429; the list is cut at a character budget, but on main it shows "Listed 126 of 126 permitted capabilities"
  and names `watch_cancel`, `watch_list`, `watch_pause`, `watch_update`, `market_symbols` and `trade_close_positions`: checker's `chk/p18/inventory.py` → `chk/p18/inventory.out`;
  it is added to every request at `packages/agent-runtime/src/lonora_agent/model_runtime.py:66-74`, as optional guidance that request admission may shed: UNSURE whether it was shed in any production run). The owner decision: "The agent has access to every tool" (`docs/ui-reference/OWNER_DECISIONS.md:10`).
- Added by the checker: the mandatory constitution, sent in every run, names the exact tool: "A watch is cancelled with watch_cancel or changed with watch_update, ...
  Reach a tool outside your native list with tool_call." (`packages/agent-runtime/resources/constitution/trading-policy.md:7`; this paragraph was added by PR #42 itself and
  is present in `2477c22`). The core policy adds "Native tools are this Run's working set; call other inventory tools via tool_call {name, arguments}."
  (`packages/agent-runtime/resources/system/lonora.md:122`), and the `tasks` chapter "Steer your own watches with watch_cancel, watch_pause, watch_resume and watch_update"
  (`packages/agent-runtime/resources/system/lonora.md:434`, only when a `tasks` tool was called recently). So [71], [75] and [81] claimed the absence of a tool that the
  model's own instructions name, and in [75] the model even named `watch_cancel` and then, in [77], called `watch_create`. The empty discovery result is one cause; the
  model not acting on a named tool through `tool_call` is another, and no runtime check catches either.
- The runtime design keeps schemas out of the native array mid-run to protect the prompt cache (`docs/tool-execution-runtime.md:120-126`), so a discovered tool is used through `tool_call`, which any gate
  can rely on.

### (ii) What is missing

- No check of a reply that claims inability. OBSERVED: [71] `1638329a` "ما عندي أداة حذف مباشر" with zero tool calls; [75] `3fa683e6` "ما في أداة حذف ظاهرة" after one `tool_environment`
  call with the query "watch cancel task routines goals" whose result was `{"tools":[],"total":0}` (trace Part 4 #76-77); [81] `38b259bb` "أحذف أو أوقف متابعة إذا كانت الأداة متاحة" with zero calls.
  [73]/[75]/[81] ran on exactly main. REPRODUCED: zero-call claim committed unchanged (`runs/cp-contract.out` S2b).
- The discovery search itself fails on the owner's vocabulary (cause of the empty result; described, not designed):
  `search_definitions` (`packages/tools/src/lonora_tools/tool_discovery.py:44-89`) takes as gate the query token with the lowest catalog frequency (`packages/tools/src/lonora_tools/tool_discovery.py:62`) and drops every tool that does not contain it
  (`packages/tools/src/lonora_tools/tool_discovery.py:69-74`); a token that no tool contains (frequency 0) is still chosen as the gate and empties the result. The corpus is name, description and parameter names only
  (`packages/tools/src/lonora_tools/tool_discovery.py:52-54`), English. REPRODUCED through the real tool (`runs/cp-contract.out` S2):
  `"watch cancel task routines goals"` -> 0 tools; `"حذف المتابعات"` -> 0 tools; `"delete watch"` -> `workspace_update`, `chart_annotate` (wrong tools);
  `"cancel watch"` -> `watch_cancel`, `task_control`, `goal_control`, `trade_execute`; `"watch"` -> 10 tools. The description of `watch_cancel` is "Stop one of your own watches; its record stays, and watch_resume undoes it."
  (`packages/tools/src/lonora_tools/market_watch.py:255`). This belongs to the discovery fix; I only note that a principle 7 gate based on "tool_environment was called" would have
  accepted `3fa683e6`.
- No tool-level synonyms: searched `grep -rn "search_terms\|aliases\|synonym"` over `packages/tools`, `packages/adapter-kit`, `packages/agent-runtime/src` finds none (only two prose uses of "aliases").

### (iii) Where the change attaches

1. The final-reply gate of section 4 (`final_answer`, `packages/agent-runtime/src/lonora_agent/loop_outcomes.py:155-184`), with the request-scoped walk of section 1.6. Structural facts available
   without reading wording: whether any `tool_environment` call exists since `owner_request_start`, and what it returned (`total`, `tools`). Output: a nudge "run tool_environment with a query that names the
   action the owner asked for, list the full catalog if the query finds nothing, and use the tool you find through tool_call". The tool-level execution stays validated (`packages/tools/src/lonora_tools/registry.py:475-516`).
2. What the gate needs to recognise as an inability claim is the same detection question as principle 3 (patterns or the model's own declaration).
3. An evidence rule stronger than "tool_environment was called": the gate can require that the query result is non-empty or that a full listing (`offset` paging, `packages/tools/src/lonora_tools/registry.py:389-397`) was read.
4. Discovery quality (gate token, synonyms, Arabic) is the phase 0 item `tool_discovery.py`.

### (iv) Cost

S for "no `tool_environment` call in this request" on top of principle 3's gate; M with the wording detector and the evidence rule. Effectiveness depends on the discovery fix.

### (v) Conflicts

None with money rules. The brief says the guard is never explained to the owner: the nudge goes to the model as a runtime notice, not to the owner (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:27-31`).
The wording tension of 1.5 applies. A found tool can be financial: continuing with it still goes through `tool_call` validation, grant and approval (`packages/tools/src/lonora_tools/registry.py:89-93`).

### (vi) Safe at once or owner decision

Safe at once: the structural part. Wording detector: owner decision (1.5).

---

## 9. Principle 8: no promise and no "done" without a successful tool result in the same turn; no trial calls with side effects

### (i) What exists today

- Financial claims only: the financial-truth gates in `model_turn` (`packages/agent-runtime/src/lonora_agent/model_runtime.py:218-238`; helpers `packages/agent-runtime/src/lonora_agent/context/financial_result.py`, tool names at line 9) and the
  uncertain-outcome line (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:115-152`).
- Stream admission delays a reply that matches `EFFECT_CLAIM` (trade verbs) until the end (`packages/agent-runtime/src/lonora_agent/public_stream.py:47`); it does not block it.
- Prompt: "Say something was done only when a successful tool result in this request shows it." (`packages/agent-runtime/resources/constitution/trading-policy.md:7`) and the skill line "Only say this after persistence succeeds."
  (`packages/agent-runtime/resources/skills/market-watch/SKILL.md:31`, not loaded in chat runs). Also sent in every run: "Never invent prices, sources, credentials or successful actions."
  (`packages/agent-runtime/resources/constitution/identity.md:1`) and "Only claim the stage actually established by the returned result."
  (`packages/agent-runtime/resources/system/lonora.md:86`, core).
- Guardrails on repetition only (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:277-299,313-400`); they do not know the owner's request.
- OBSERVED false claims on main code: [63] (`ddae66ad`): three `watch_create` calls (a second one with a new level, a third identical to the second that returned the same id 6050e419, trace Part 4 finding 1: "idempotent upsert"), then "تم الإلغاء. المهمة/المتابعة على **EURUSDm** أُزيلت";
  [69] (`e343c96a`): only `wait_for_input`, then "سأحذف ..." (owner had answered with `tasks_only`); [43], [47], [57] watching claims; [77] (`e79b4bf2`): the trial call `watch_create(enabled=false, prompt="cancel-test", dedupe_key="cancel-test-1")` created
  watch `b9c1017a` (trace Part 4 #78-79). REPRODUCED: every one of these replies is committed byte for byte (`runs/cp-guards.out` cases 1, 2, 3, 4a, 4b, 4c); after case 3 "the trial call left a new row".

### (ii) What is missing

- Any comparison of reply claims with tool results for non-financial effects. Searched: `grep -rn "re.compile\|re.search"` over `packages/agent-runtime/src` shows no pattern over reply text except `EFFECT_CLAIM`, the
  `<suggested_reply>` tag, card fences and the Arabic-letter language test (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:84-93`).
- A promise check ("I will", "سأحذف", "مراقب").
- Knowledge of the owner's request inside the tool guardrails: `before_call(state, call, tool)` has no messages (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:277`) and `ToolRegistry.execute`
  (`packages/tools/src/lonora_tools/registry.py:475-507`) has only the context, so nothing can say "this create call is a test, not the owner's request". There is no dry-run mode on `watch_create`.
- Argument sanity: `prompt` must only have length 1 to 8000 (`packages/contracts/src/lonora_contracts/market_watch.py:28`).
- The answered question card is recorded (`input_requests`, `packages/db/src/lonora_db/messages.py:537-552`) but nothing afterwards requires a tool call that matches the chosen option.

### (iii) Where the change attaches

1. **Claim versus evidence**: the same `final_answer` gate and request-scoped walk (sections 1.1, 1.6), generalising `uncertain_operations`
   (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:78-112`) from the three financial names (line 23) to "each effect call and its result" using `Tool.read_only` / `Tool.financial`
   (`packages/tools/src/lonora_tools/base.py:72-73`). Input: reply text, tool results since `owner_request_start`, the registry. Output: a nudge naming the missing evidence ("no successful call of the kind that would make this true in this
   request"). Needs a way to say what a claim is about (the same detector question as principle 3).
2. **Gate on an answered question with no follow-up call**: `input_requests` (`packages/db/src/lonora_db/messages.py:528-552`) and `owner_request_start` give the structural fact "owner picked an option; no effect call since" without
   reading the reply.
3. **No trial calls**: pass the request context to `before_call` (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:277`; it is called from `execute_segment`, `packages/agent-runtime/src/lonora_agent/tool_block.py:174`) or to
   `ToolRegistry.dispatch` (`packages/tools/src/lonora_tools/registry.py:509-516`); validation of obvious placeholders in `Watch` (`packages/contracts/src/lonora_contracts/market_watch.py:28`). A heuristic on test-looking arguments is weak; the
   structural remedies are discoverability (principle 7) and an explicit rule in the tool description of creating tools.
4. **Never hide a real financial effect**: any rewrite must keep the pattern of the uncertain line (append or continue, never delete), `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:9`.

### (iv) Cost

M for non-financial claims against effect results; L with a promise detector and its evaluation; S for refusing placeholder watch prompts; M for passing the request context to `before_call`.

### (v) Conflicts

- Money and journals: a gate must not replace or suppress a reply after a financial effect, because the owner must always learn that a real order was sent (the PR #42 rule at `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:9`). Only add, continue or ask.
- Append-only journal and authority records are untouched: this gate reads results and writes only a runtime notice.
- Wording tension (1.5). English-only for the nudge text; owner text stays in the owner's language.

### (vi) Safe at once or owner decision

Safe at once: placeholder-prompt validation; the structural "owner picked an option, nothing done" gate; claim checks for own-state effects once a detector exists. Owner decision: the wording detector (1.5), and that a claim of an
effect without a matching successful tool result is held back.

---

## 10. Order, dependencies and decisions

Dependencies: 7 needs the discovery fix; 2 and 6 need 1; 3, 5, 7, 8 share one gate and one request-scoped walk (section 1.6) and one answer to the detection question. 4 needs the pending-offer carrier.

| Piece | Cost | Safe at once? |
|---|---|---|
| Resolver for read tools (suffix, alias, default account, `candidates` through `LonoraError`) | M | yes |
| `class`, `retryable`, `hint` in `observe` and `classify`; wider transient set | S | yes |
| Position existence check for non-bound agents | S | yes |
| Request-scoped evidence walk (generalised `uncertain_operations`) | S to M | yes (read-only) |
| Conversation stop gate: read-only offer, `tool_environment` precondition, "owner picked an option, nothing done" | M | yes |
| Gate that reads reply wording (offers, inability, promises, "done") | L | owner decision (1.5) |
| Pending offer from `suggested_reply` as history block and run-start notice | S | yes for reads and own-state |
| Durable pending-offer record | M | yes; expiry and the 👍 question are decisions |
| Money-to-price helper for take-profit and stop-loss | M | yes |
| Default order size | S to M | owner decision (the number) |
| Guidance text in descriptions (watch, trade) in English | S | yes |
| Placeholder-prompt validation for watches | S | yes |

Owner decisions collected: (a) whether reply-wording checks are acceptable (`docs/ui-reference/OWNER_DECISIONS.md:12-13` and the comment at `packages/core/src/lonora_core/public_reply.py:4`); (b) the default order size when no limit exists (recommendation: the instrument
minimum, stated in the confirmation); (c) default for "close at +$X": broker take-profit or watch plus wake; (d) whether money calls may take a single suffix match silently (brief section 4 already says yes for symbols;
the confirmation line must show the exact name); (e) how long an offer stays pending and whether a 👍 counts as acceptance; (f) which own-state steps count as inside the delegation for acting without asking.

Conflicts to keep visible: none of the eight changes needs a second path to move money, a change to the journal or authority records, or shadow trading. Principles 3, 4 and 8 would be unsafe if they let chat text act as approval
(`packages/tools/src/lonora_tools/trade.py:753-757`); principle 1 and 6 would be unsafe if a resolver or a default widened scope.

---

## 11. What the trace still has to confirm (kept only where argument or result bodies are missing)

1. Whether production `execution_state` holds `owner_started` and `owner_request_start` for `fb1d4b5a`, `ddae66ad`, `e343c96a` (trace Part 4 finding 9 lists keys and does not name them). If they are absent the PR #42 code
   path would not have been running; every build in the timeline contains PR #42 (`TIMELINE_CORRECTION.md`) and `restore_checkpoint` calls `record_request_start` on every run entry (`packages/agent-runtime/src/lonora_agent/loop_restore.py:58`, keys named at `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:19-20`), so presence is expected. Finding 9 is not an exhaustive key list (it also omits `messages`, `environment` and `tool_exposure`, which the trace itself uses elsewhere).
2. The `ln_messages.suggested_reply` values of the assistant replies that end with an offer (Part 3 shows `rich_content` null and says nothing about this column): decides whether the model's own suggestion can be the wording-free offer signal (sections 4 and 5).
3. The envelope of the grant signed at 09:43:24 (`ln_account_authorities.envelope`: `management_mode`, caps): confirms that no default volume or cap exists. By the definition of full delegation
   (`packages/contracts/src/lonora_contracts/account_authority.py:37-49`) and the owner's «تفويض كامل» it should be all-null.
4. Whether the 👍 reactions at [41] and [43] reached the run as input (message reaction rows and run input).
5. The request bodies of the production runs (constitution text and capability inventory actually sent). The tool-call bodies are in Part 4; requests are not. In particular: whether the `tasks` chapter with "Steer your own watches with watch_cancel ..." (`packages/agent-runtime/resources/system/lonora.md:434`) was in the requests of `ddae66ad` and `e343c96a` after their `wait_for_input` call, and whether request admission shed the capability inventory or a domain chapter in any run.
6. The tail of the third `watch_create` result of `ddae66ad` (cut at 1500 characters in Part 4: whether it carried a `deduplicated` flag and the guardrail warning that the main-branch replay shows, "watch_create has now run 2 times in a row with identical arguments", `chk/p18/guards.out` case 1).

Settled by the trace (no longer open): the 23 native tools of every run (Part 1); no `skill_view`, `watch_cancel`, `watch_list`, `market_symbols` or close call (Part 2); the `recovery` block the model received for both gold failures (Part 4
finding 6); the `tool_environment` query and its empty result (Part 4 #76-77); the three `watch_create` calls and the "cancel-test" trial (Part 4 #65-70, #78-79); no guard record for three runs (Part 4 finding 9); the Task
description text is in the ticket payload (Part 1 Q5; that the chat run never sees it is a code fact, section 7); `reply_language` empty (Part 1 Q6); the three server updates cost one run eight seconds (Part 2).

---

## 12. Files

- `scratchpad/audit/scripts/cp_contract.py` (copy of the earlier probe, run on database 12) -> `scratchpad/audit/runs/cp-contract.out` (S1 resolution errors and the recovery block, S2 discovery queries and an inability claim, S2b zero-call claim, S3 offer ending, S4 short approval and what the model receives, S5 unknown position). SCRIPTED model, real runtime, simulation broker.
- `scratchpad/audit/scripts/cp_guards.py` -> `scratchpad/audit/runs/cp-guards.out`: replay of the production replies [63], [69], [77], [43], [47], [57], [29], [71], [73] against the real runtime; all committed byte for byte.
- `scratchpad/audit/scripts/cp_principles.py` -> `scratchpad/audit/runs/cp-principles.out`: existing resolver pieces on a sample catalog (P1a), clean native tool list (P1b), `watch_create` on a position with a real and a fake id (P5).
- `scratchpad/audit/scripts/cp_classify.py` -> `scratchpad/audit/runs/cp-classify.out`: the real `classify` on 22 codes.
- `scratchpad/audit/runs/cp-reference-params.tsv`: the 134 reference fields of 65 tools (registry introspection).
- `scratchpad/audit/scripts/cp_count_offers.py` -> `scratchpad/audit/runs/cp-count-offers.out`: 21 of 37 replies match the offer pattern; 19 of those are offers (section 4).
- Leads used and verified before reuse: `trace-guards.md` (guard inventory; I re-ran its script on database 12 and re-opened the lines I cite) and the earlier probe `p18_contract.py`.
- Repository state: `git -C /home/user/lonorabot status --short` is empty after the work.

---

## Verification log (independent checker)

Repository at `9f5b1da` code (working tree HEAD is `3f09572`, a docs-only commit on top of `9f5b1da` that adds `docs/research/lonora-runtime-notes/`; no code differs). `git -C /home/user/lonorabot status --short` empty before and after. Tools: `chk/p18/cites.py` (extracts every `path:line` and prints the lines), outputs in `chk/p18/`.

**Citations opened.** 211 distinct `path:line` specs in the original file, every one printed and read (`chk/p18/dump.txt`); 243 in the corrected file, the 36 new ones read the same way (`chk/p18/dump2.txt`). No missing file, no out-of-range line. Verbatim quotes checked character by character for: tool-policy.md:3, trading-policy.md:1 and :7, uncertain_outcome.py:3 and :9, public_reply.py:4, suggested_reply.md:2, registry.py:157-161 and 428-429, environment.py:16, market.py:99-101 and 132, trading_decision.py:79, market_watch.py:239 and 255, SKILL.md (trade-management 20, 23-24; market-watch 18, 31), account_authority.py:150, permissions.py:140-148 and 171-172, OWNER_DECISIONS.md:10, 12, 13, 51, stop_gates.py:45-54, the Arabic reply quotes against `lonora-chat.md`.

**Line numbers / quotes corrected.**
- `docs/trading-safety.md:7-8` -> `7-9` (the quoted sentence ends on line 9; 4 places).
- `market_watch.py:16,36,85-88` -> `15,24,27-28,36-37,74,84-88` (line 16 is `detector`, not `kind`).
- Suffix rule: constants of `symbol_candidates` are `agents.py:55-56`, not `instrument_names.py:32-33` (a second copy).
- `context/skills.py:200` -> `198-200`, plus the activation evidence (`resolver.py:106-110`, `trade-management/skill.json:9-13`).
- Market-watch skill line "Only say this after persistence succeeds." located at `SKILL.md:31`.
- [35] quote made verbatim («أضع لك **أمر إغلاق مشروط** أو أتابعه لحظة بلحظة على هذا المستوى»).
- "deduplicated" for the third `watch_create` of `ddae66ad` replaced by the trace's own words (same id, "idempotent upsert").
- `goal_wait` quote given its citation `trading_goal.py:526`.

**Claims refuted or downgraded.**
1. Build note: "only history.py, skills.py plus a few lines" changed between `2477c22` and `9f5b1da` is false: 20 cited files changed (GenUI v2 and message-origin work), and `instrument_names.py` did not exist for runs [4] to [55]. The conclusion that the classified mechanisms were the same in every run holds (the six named runtime files have an empty diff since `aa50e8e`; constitution, system manual and bootstrap identical between `2477c22` and `9f5b1da`).
2. PR #42 "three tool-description words": one description word plus two result-text fields; and the trading-policy paragraph PR #42 added already names `watch_cancel`.
3. Principle 6 / lead point 13 ("the rule exists only in a skill and the Task prompt; the chat run never sees it"): refuted in part. The core operating policy sent in every run says "Explicit full management lets you choose size, stops and targets without per-order approval or default volume/activity quotas" (`lonora.md:106`), and the autonomous permission frame says "size and manage positions" (`permissions.py:140-142`). Only the explicit "do not ask" is absent; `lonora.md:136` ("Ask for owner preferences or missing financial limits ...") pulls the other way. Status FAILS kept; reason rewritten.
4. Principle 7: "discovery is prompt-only and the search fails" was incomplete. The mandatory constitution names `watch_cancel` and the `tool_call` route (`trading-policy.md:7`), the core policy repeats the `tool_call` route (`lonora.md:122`), the inventory lists `watch_cancel` on main (checker's `inventory.out`: 126 of 126 listed), and the `tasks` chapter names it (`lonora.md:434`). Status FAILS kept; reason extended.
5. Principle 5 "nothing steers the model to them": softened to "nothing maps the condition to them"; general watch guidance exists (`lonora.md:127` core, `lonora.md:433` tasks chapter).
6. Principle 4: FAILS kept, but the trace shows short approvals of read offers were executed from plain history ([16], [18], [22]); the failures are own-state offers ([37], [39], [43], [77]); and core policy `lonora.md:130` already asks for it. Added.
7. Principle 3 count: "21 of 37 end with an offer" contradicted the file's own breakdown (2 of the 21 are questions). Corrected to 21 pattern matches, 19 offers; about 22 by reading with [12], [31], [73].
8. `market_symbols` "not native, so the model guessed": causal link downgraded; the tool was listed in the inventory and named in the market chapter (`lonora.md:212`).
9. `web_search` "comes from the chat option": downgraded to UNSURE (chat option or remembered-tool promotion).
10. Grep results restated: "candidates" also appears in five other files with other meanings; `"hint"` also in `genui_compile.py:683,706`; `pending_offer` appears only in the audit's own notes committed after `9f5b1da`.
11. "Task description text exists only in the ticket (settled by trace)": the trace shows where it is, not that it is nowhere else; rephrased.

**Reproductions re-run (database 12, `source env.sh 12`).**
- `scripts/cp_principles.py` -> `chk/p18/principles.out`: P1a, P1b (22 native tools, same 11 registered-but-absent), P5 (real and fake `position_id` both `ok: true`) REPRODUCED.
- `scripts/cp_classify.py` -> `chk/p18/classify.out`: identical to `runs/cp-classify.out`.
- `scripts/cp_contract.py` -> `chk/p18/contract.out`: S1 to S5 REPRODUCED in substance (`symbol_not_found`, `broker_sessions_not_found`, `market_watches_not_found`, `agent_not_found`, `volume_required`, route exhausted on the 4th call; discovery results 0 / 0 / 2 wrong / 4 / 10; S3 `suggested_reply` "ياريت"; S4 all four key checks false; S5 one pending approval row, cancelled after the owner moved on). Differences only in `list_accounts` output, because the database was not empty.
- `scripts/cp_guards.py` -> `chk/p18/guards.out`: first attempt failed at login (HTTP 401: the script's default e-mail differs from the owner already in database 12); re-run with `LONORA_UI_TEST_EMAIL=ci@example.com`: 10 of 10 committed replies byte for byte the scripted text, same cases. REPRODUCED.
- `scripts/cp_count_offers.py`: identical output.
- `runs/cp-reference-params.tsv` recounted: 65 tools, 134 fields; per-kind tool counts (32 account_id, 24 symbol, 10 goal_id, 8 agent_id, 8 chart_id, 5 watch_id, 4 position_id, 3 order_id, 4 operation_id, 3 connection_id, 2 task_id, 1 routine_id, 1 ticket_id, 4 thread_id, 1 restriction_id, 4 related_symbol) match. Registry size 126 confirmed.

**Absence claims re-searched (two greps each where possible).** `resolve_instrument` (definition only); offer wording in `agent-runtime/src` and `core/src` (none); `pending_offer|open_request` (no code); `modify_position|kind=position|position_id` and `take.?profit|stop.?loss|kind.?position|position watch` in resources (nothing relevant); `default_volume|default lot` (none, resources added); `search_terms|aliases|synonym` (two prose uses only); `profit_tick_value` (parsed and declared only, `normalize.py:57,65,72`); `re.compile|re.search|re.sub|re.findall|re.match|re.fullmatch` in `agent-runtime/src` (no pattern over reply text besides those named; `genui_compile.py:203-204` has number/fact-tool patterns for cards: UNSURE whether they check card numbers against tool results, not opened). Position existence check: only under `fixed_market` (`market_binding.py:113-114`), confirmed.

**Classifications after checking.** P1 FAILS, P2 PARTLY, P3 FAILS, P4 FAILS, P5 FAILS, P6 FAILS, P7 FAILS, P8 PARTLY: all eight kept; the reasons of P3 to P7 were corrected as above.

**Claims added.** Core-policy and constitution prompt rows in 1.4 (`lonora.md:60,86,106,120,122,127,130,135,136,212,224,433,434`, `trading-policy.md:7`, `identity.md:1`); how the core section and domain chapters reach a request (`system_policy.py:133-141,146-161`, `loader.py:27-46`, `model_runtime.py:66-74`); the inventory on main lists every tool; short-approval outcomes per offer kind from the trace; section 11 item 5 now names the `tasks` chapter question.

**TRACE MUST CONFIRM items.** All six kept: none is settled by the trace parts (they need `ln_messages.suggested_reply`, the grant envelope, reaction rows, request bodies, and the untruncated third `watch_create` result). Item 1 is predicted by code (`loop_restore.py:58`) but its presence in production state is a database fact.
