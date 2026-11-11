# Conversation group D: refusals despite a signed full delegation ([23]-[24], [30]-[35])

Scope: main at `9f5b1da`. Paths are relative to the repository root. Nothing under the repository was changed.

Evidence used:

- Code, read at `9f5b1da`.
- Scripted runs against the real runtime (`execute_run`, real registry, real guards), database 12, simulation broker. Driver: `scratchpad/audit/scripts/conv_d_delegation.py`; raw output: `scratchpad/audit/runs/conv-D-delegation.out`. A second driver isolates the ten-entries case: `scripts/conv_d_ten_debug.py`, output `runs/conv-D-ten-debug.out`. Every model turn in these runs is SCRIPTED (written by the driver); the evidence is what the runtime returned.
- The production export `scratchpad/audit/production-trace.md`. Parts 1-3 have tool names and ok/code per call, but no arguments and no result bodies (`production-trace.md`, Part 2, "IMPORTANT"). Part 4 adds the calls and results as the model saw them for seven runs, two of which are in this group: `00f7b6bc` ([24]) and `94d50998` ([35]). (Checker: the first version of this file overlooked Part 4; the sections below now use it.)
- Builds: [4] to about [55] ran on `2477c22`, which contains PR #42 (`TIMELINE_CORRECTION.md`). Between `2477c22` and `9f5b1da` nothing changed in `packages/agent-runtime/resources/system/lonora.md` or `packages/agent-runtime/resources/constitution/` (`git diff --stat 2477c22 9f5b1da -- packages/agent-runtime/resources` lists only three `prompts/genui_v2*.md` files), and `trade.py` changed by two lines about rejected cards (`packages/tools/src/lonora_tools/trade.py:160-161`). So the policy text and the trade tool that produced [24], [31], [33] and [35] are the ones on main. (Checker: other code did change between the two builds, but none of it touches these runs. `provisional_voice` now also makes a GenUI-tainted Run's trades into approval cards (`packages/trading/src/lonora_trading/account_authority.py:42-65`, `git diff 2477c22 9f5b1da`), and `context/history.py` / `context/builder.py` gained card-submission handling. Both apply only to `ui_submit` messages and card-started Runs, and `ui_submit` is empty on every row of this thread (`production-trace.md`, Part 3 header).)

## 0. Verdicts

| Message | Problem | On main | Why |
|---|---|---|---|
| [24] «ما أقدر أنفّذ صفقة شراء بدون **حجم الصفقة**» | Asked the owner for a lot size under a full delegation | **FAILS** | No default size exists anywhere; `volume` is required for an entry; no guard touches the reply (reproduced, section 2) |
| [31] «لا أستطيع فتح 10 صفقات…» | Refusal with no tool call | **FAILS** | No server limit on the number of trades under this grant; the refusal is the model's own and no guard touches it (reproduced, section 3). A separate mechanical trap exists: ten identical calls in one run open one position |
| [33] numbers asked in plain text | Should be one card with suggested numbers | **FAILS** | The card mechanism exists (`wait_for_input` with choices) but nothing makes the model use it; plain text passes (reproduced, section 4) |
| [35] plan narrowed to the current position, ended with an offer, no order change | Should be `modify_position` with TP/SL | **FAILS** | The tool does it under the grant with no card (reproduced, section 5); nothing holds the open request of [30] and nothing stops a reply that ends in an offer |

None of the four refusals is required by a money-safety rule (section 6).

## 1. What the «تفويض كامل» card in [7]-[8] grants

### 1.1 The record

The grant is one row of account authority whose signed envelope is `AccountAuthorityEnvelope` (`packages/contracts/src/lonora_contracts/account_authority.py:107-119`, fields inherited from `AccountAuthorityProposal`, `account_authority.py:52-66`). Full delegation is not a stored flag; it is recognised from the terms (`full_delegation`, `account_authority.py:37-49`):

- `management_mode == "full"`
- `symbol_scope == "account"` (every pair on that one account)
- every one of the ten actions (`ALL_AUTHORITY_ACTIONS`, `account_authority.py:12-26`)
- `valid_until is None`
- `allow_manual_positions is True`
- all six caps unset: `maximum_order_volume`, `maximum_symbol_volume`, `maximum_positions`, `maximum_pending_orders`, `maximum_actions`, `minimum_equity` (`AUTHORITY_CAPS`, `account_authority.py:27-34`)

The card's fixed Full terms are `FULL_TERMS` (`packages/contracts/src/lonora_contracts/owner_actions.py:252-257`). Every grant card signs `management_mode="full"` whatever the choice (`grant_proposal`, `packages/db/src/lonora_db/owner_actions.py:446-461`).

Reproduced (run output, section "0. FULL DELEGATION"): the signed envelope for the personal assistant was

`{"management_mode": "full", "symbol_scope": "account", "symbols": [], "actions": [all ten], "maximum_order_volume": null, "maximum_symbol_volume": null, "maximum_positions": null, "maximum_pending_orders": null, "maximum_actions": null, "minimum_equity": null, "valid_until": null, "allow_manual_positions": true, "execution_mode": "live", "schema_version": 2}`

The envelope has exactly these keys plus `owner_id`, `agent_id`, `account_id`, `thread_id`. There is no size, lot, risk-per-trade or stop field in it.

### 1.2 What signing also does

- It creates one continuous Task «إدارة حساب التداول» and its work Run (`packages/auth/src/lonora_auth/account_authority.py:131-173`). The Task description says: "choose your own justified direction, lot size, stops, targets and management plan within that scope. Do not ask for each order or ask the owner to choose routine trading parameters." (`account_authority.py:148-150`). This text is the prompt of that Task's own Run. It is not part of an ordinary chat Run such as the ones that answered [23]-[35]. The production ticket carries the same description (`production-trace.md`, Part 1, Q5). (Checker, two more routes checked: the context builder adds no Task section to a chat Run (`grep -n -i task packages/agent-runtime/src/lonora_agent/context/builder.py` finds only a comment at `:179`), and `agent_inspect`'s work page lists Tasks with only `id`, `title`, `status`, `phase`, `waiting_reason`, `version`, never the description (`packages/tools/src/lonora_tools/supervision.py:219-227`). So the chat Run cannot see this sentence even when it inspects the Task. The same instruction exists in only two other places: `lonora.md:337` (the `trading` chapter) and `skills/trade-management/SKILL.md:23-24` (section 2.4).)
- The permission frame of every model turn then shows level `autonomous`, the scope with `"full_delegation": true`, and the account's money limits (`packages/agent-runtime/src/lonora_agent/context/permissions.py:76-120`). Its behaviour text says: "Independently inspect fresh account/market facts, decide whether/when to trade, size and manage positions, and persist useful monitoring within the exact active signed scopes below. Matching actions need no repeated per-operation approval." (`permissions.py:140-142`).

### 1.3 Limits that still bind

- The account's `ExecutionPolicy`: `max_positions`, `max_pending_orders`, `max_symbol_direction_volume`, spread and drift caps, and the money limits in `risk` (`packages/contracts/src/lonora_contracts/execution_quality.py:16-26`; `packages/contracts/src/lonora_contracts/risk_limits.py:22-36`). All default to unset, except the two freshness bounds `quote_max_age_seconds` and `account_max_age_seconds`, which default to 60 seconds (`execution_quality.py:17-18`). "Every limit is optional and unset means not enforced: no money amount is ever chosen for the owner." (`risk_limits.py:3-4`). Money limits are checked only when configured and only for requests that add risk (`packages/trading/src/lonora_trading/execution.py:357-360`).
- Stop new trading, the owner's pauses, restrictions (`docs/account-authority.md:32-34`).
- Under `management_mode == "bounded"` an entry needs a stop loss; under `full` it does not (`packages/trading/src/lonora_trading/account_authority.py:273-275`).

Reproduced: the account policy read back with every field `null`, and the permission frame showed `"monetary_risk_limits": [{"configured": false, ... "not_configured": ["max_trade_risk", "max_trade_risk_equity_percent", "max_daily_loss", "max_open_risk", "max_open_risk_equity_percent", "min_free_margin"]}]`. That matches [8] «لم يُضبط حد للخسارة اليومية».

### 1.4 Is there any default volume or risk-per-trade value (principle 6)?

**No.** Searched: `default_volume|default_lot|default_size|risk_per_trade|per_trade|minimum_volume|smallest` over `packages/**/*.py` returns no trading value. The documents say so on purpose:

- "No hardcoded lot or loss amount is chosen for the owner." (`docs/account-authority.md:127`)
- "There is no default instrument, currency, volume or stop." (`docs/broker-position-sizing.md:6-7`)
- "Never default authority, size limits or autonomy." (`packages/agent-runtime/resources/system/lonora.md:23`, always loaded)
- "Explicit full management lets you choose size, stops and targets without per-order approval or default volume/activity quotas" (`lonora.md:106`, always loaded)

The only server-held numbers that could bound a size today are:

1. the broker's `volume_min` / `volume_step` of the instrument (`packages/contracts/src/lonora_contracts/market.py:15-17`), 0.01 for XAUUSDm in [14];
2. `max_trade_risk` or `max_trade_risk_equity_percent`, when the owner has set one (`risk_limits.py:25-26`); not set in this conversation.

(Checker: one server-held money number does exist on the grant card, but it is not a size. A card with no daily-loss amount suggests 3% of equity: `SUGGESTED_DAILY_LOSS_PERCENT = Decimal(3)` (`packages/tools/src/lonora_tools/owner_actions.py:41`, used at `:131-135`). This is the recorded owner decision D1 (`docs/ui-reference/OWNER_DECISIONS.md:46`, Q18). It is a daily-loss line the owner sees and signs, never a per-trade volume, and Full sets none. It shows only that a server-suggested, owner-confirmed default has a precedent. No owner decision covers a trade size.)

So principle 6 ("the missing parameter takes a default from the delegation/risk policy") has nothing to read on main. The acceptance line for [23] («تنفيذ بالحجم الافتراضي للتفويض، مع ذكره») needs a value that does not exist yet, and three documents above state the opposite design. That conflict needs an owner decision recorded in `docs/ui-reference/OWNER_DECISIONS.md`; this file does not design it.

### 1.5 One inconsistency in the transcript

[7] shows the settled card with «تفويض كامل», and [8] says «كما اخترت، لم يُضبط حد للخسارة اليومية».

- The settled line shows «تفويض كامل» from the signed terms (`apps/web/src/components/owner-actions/OwnerActionCard.tsx:234-241`).
- «كما اخترت، لم يُضبط حد للخسارة اليومية» is the note `owner_action_grant_no_money_limit` (`packages/bus/src/lonora_bus/attention_messages.json:30`), added only when the stored result has `money_limit == "none"` (`packages/db/src/lonora_db/owner_actions.py:1862-1867`).
- A card whose stored choice is Full always stores `money_limit = "apply"` (`apps/api/src/lonora_api/routes/owner_actions.py:617`; the same line exists at `2477c22`) and adds the note `owner_action_grant_full` instead (`owner_actions.py:1857-1859`). Reproduced: I sent `money_limit: "none"` with a Full card; the result stored `"money_limit": "apply"` and the chat line was «…تفويض كامل: كل أزواج هذا الحساب وكل الإجراءات ومراكزك اليدوية أيضًا، حتى توقفه. لم تضع البطاقة حدًا للخسارة اليومية…», not the [8] wording.

The code supports this reading (checker). The settled line shows «تفويض كامل» for a Custom card too, when it signed exactly Full's terms: "a Custom card that signed exactly Full's terms says so too" (`packages/core/src/owner-actions.ts:920-924`). D1/Q18 make «التشغيل دون حد مالي» the server's `money_limit=none` choice (`docs/ui-reference/OWNER_DECISIONS.md:46`). The [8] text is confirmed verbatim in the database (`production-trace.md`, Part 3, seq 6). The likely history: the owner signed a card whose stored choice was Custom, with terms equal to Full's (all pairs, all actions, own positions, until stopped), and chose «التشغيل دون حد مالي». The executed authority is the same either way, because `grant_proposal` signs `management_mode="full"` for both choices.
TRACE MUST CONFIRM (not in the export): the `envelope` of the active row in `ln_account_authorities` for agent `0b9f0da6…`, and `payload.delegation` / `result.money_limit` of the grant row in `ln_owner_actions`. The card did not come from an agent proposal: no run in the thread called `owner_action_propose` (`production-trace.md`, Part 2 tool events; the only run before 09:43:24 with a tool call is `0afe5ea8`, `memory_read`). A seq-6 row without a run proves nothing by itself, because every confirmed card's acknowledgement is written as an assistant `MessageRow` with no run, whoever proposed the card (`packages/db/src/lonora_db/owner_actions.py:1999-2020`). So the card came from the owner's mandate sheet, which drafts a grant card through `POST /agents/{agent_id}/account-authorities/draft` (`apps/api/src/lonora_api/routes/account_authority.py:70-111`).

## 2. [23] → [24] «ما أقدر أنفّذ صفقة شراء بدون حجم الصفقة»

### 2.1 What happened in production

Run `00f7b6bc` called `account_read`, `market_quote`, `market_instrument` in parallel, all ok, and then replied. It never called `trade_execute` (`production-trace.md`, Part 2, events #484-489; Part 1 run list). The refusal is the model's own text; no tool refused anything. The results the model had in hand (`production-trace.md`, Part 4, run `00f7b6bc` #27-#29): `account_read` with `"balance":"13944.57"`, `"positions":[]`; `market_quote` with `"profit_tick_value":"0.1","loss_tick_value":"0.1"`; `market_instrument` with `"volume_min":"0.01"`, `"volume_step":"0.01"`, `"contract_size":"100"`. The next run, `65e8b682`, executed 0.01 at once under the grant (`production-trace.md`, Part 2, #511/516 `trade_execute → ok code TRADE_RETCODE_DONE`). That run went from 09:48:25 to 09:48:31 with no waiting state (Part 2, run lifecycle), so no approval card was waited on. The card in [27] («أمر شراء 0.01 XAUUSDm: منفَّذ») is the settled result card, not an approval.

### 2.2 Is volume required?

- JSON schema shown to the model: `required` is `['account_id', 'action', 'symbol']`; `volume` is `{"anyOf": [number > 0, string, null], "default": null}` (run output 1a). So the schema does not mark it required.
- The validator requires it for the six entry actions: `raise ValueError("volume_required")` (`packages/contracts/src/lonora_contracts/trading.py:77-81`; field at `trading.py:31`).
- Reproduced (1a), SCRIPTED call `trade_execute {"action": "buy", "account_id": …, "symbol": "XAUUSDm"}` under the full delegation returned:

`{"ok": false, "code": "tool_arguments_invalid", "issues": [{"path": [], "type": "value_error", "code": "volume_required"}], "retryable": true, "recovery": {"category": "invalid_tool_arguments", "next_action": "inspect_schema_and_repair", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`

  Nothing was sent, no journal row, no card. The result is built at `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:113-116` and classified at `packages/agent-runtime/src/lonora_agent/environment.py:38-39`. It names no source for a size: no `volume_min`, no pointer to `market_instrument` or `market_position_size`.

### 2.3 Could the agent have sized the trade itself?

Yes, with what it already had.

- `market_instrument` returns `volume_min`, `volume_step`, `volume_max`, `contract_size` (`market.py:10-22`). Run `00f7b6bc` had just read it; [24] itself quotes `0.01`.
- `market_position_size` exists, read-only: "Estimate a broker-valid market volume from a risk budget and explicit stop loss using fresh exact-symbol broker tick values." (`packages/tools/src/lonora_tools/position_sizing.py:22-27`). It is not in the default native list; the model reaches it through `tool_call` (run output 1a: `'market_position_size': False` in the native list of 22 tools; the production native list of 23 does not have it either, `production-trace.md`, Part 1 "BASELINE"). (Checker: the native list is not fixed per agent. A long-tail tool that once succeeded is remembered and promoted into later Runs: "the agent's remembered long-tail tools are promoted within a bounded budget" (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:3-4`, recorded by `remember_use` at `:151-181`; `MAX_PROMOTED_TOOLS = 6`, `packages/tools/src/lonora_tools/registry.py:85`). On the checker's rerun against the same database 12, where 1c had already used `market_position_size`, the native list had 24 tools, including `market_position_size` and `market_symbols`. In production no long-tail tool succeeded before [23], so the 23-tool list matches.) It needs six inputs, all required: `account_id`, `symbol`, `side`, `risk_budget`, `currency`, `stop_loss` (`packages/contracts/src/lonora_contracts/position_sizing.py:13-19`). So it turns a money budget and a stop into a volume; it cannot produce a size from nothing.
- Reproduced (1c), SCRIPTED: `market_position_size` with budget 5 USD and stop 4045.819 returned `"volume": "0.01", "modeled_stop_loss": "5.000", "per_lot_stop_loss": "500.0"`; then `trade_execute buy 0.01` returned `"status": "confirmed"`, `"authorization": "account_authority"`, zero approval cards.

### 2.4 Which policy lines pull which way

Present in the first model request of the [23] run (checked by substring in the request the scripted model received, run output 1a):

Lines that tell the model to choose the size itself:

- "Explicit full management lets you choose size, stops and targets without per-order approval or default volume/activity quotas" (`lonora.md:106`)
- "The model owns interpretation, timing, sizing and management within current authority." (`packages/agent-runtime/resources/constitution/trading-policy.md:1`)
- "decide whether/when to trade, size and manage positions" (`permissions.py:140-141`)
- "derive technical entry, invalidation, size and target proposals from current broker evidence when the owner's limits allow it." (`lonora.md:136`, second half)
- "Solve by doing, not by describing what I would do." (`packages/agent-runtime/resources/bootstrap/SOUL.md:7`)

Lines that tell the model to ask:

- "Ask only for genuinely missing user intent, financial limits or business parameters" (`packages/agent-runtime/resources/constitution/tool-policy.md:3`). A lot size reads as a "business parameter".
- "Ask for owner preferences or missing financial limits" (`lonora.md:136`, first half)
- "Never default authority, size limits or autonomy." (`lonora.md:23`)
- "I'd rather ask a good question than guess wrong." (`SOUL.md:10`)
- "Do not invent a price threshold or trade parameters merely to fill a watch" (`tool-policy.md:5`)
- "An owner-provided loss range is a ceiling on permitted planning, not permission to choose its highest risk, fabricate sizing or bypass financial confirmation." (`lonora.md:137`)
- In the market chapter, which loads after `market_instrument` / `market_quote` calls: "Missing economics is unavailable, never a guessed lot size or guaranteed loss ceiling." (`lonora.md:230`). Reproduced (1b): after the three production reads, the second request contained this line.

The same market chapter also has a neutral line that points at the broker minimum: "Read min/max/step volume and stops constraints for financial preparation." (`lonora.md:228`; present in the 1b second request, rerun output).

The one line that settles the question directly is in the wrong place:

- "Under active signed full management, choose size, stops and targets from current analysis within broker constraints; do not ask the owner to choose routine trading parameters." (`lonora.md:337`). It sits in the `trading` chapter (`lonora.md:324-368`), and chapters are selected by the tool calls already made in the run (`packages/agent-runtime/src/lonora_agent/skills/system_policy.py:134-143`; `trade_execute` maps to `trading`, `market_instrument` and `market_quote` to `market`, `account_read` to `account` in `packages/agent-runtime/resources/system/manifest.json:52`, `:54`, `:97`, `:100`).
- Reproduced: the first request of the [23] run did not contain it; after the three reads of the production run it was still absent (1b); it appeared only after a `trade_execute` call had been made (1a, second request). In production the model decided to ask before ever calling `trade_execute`, so it never saw the line. Earlier runs' tool calls cannot load the chapter either. Selection reads only the tool calls of assistant messages in the request (`system_policy.py:134-140`), and the stored history replayed into a chat Run carries no tool calls (`grep -n tool_calls packages/agent-runtime/src/lonora_agent/context/history.py` finds nothing). So even after the trade in run `65e8b682`, the later runs `cc8399d7`, `1755d8d8` and `94d50998` started without the `trading` chapter.
- The same sentence is in the bundled skill `trade-management` ("do not ask for routine parameters already delegated", `packages/agent-runtime/resources/skills/trade-management/SKILL.md:23-24`), which the model reads only if it calls `skill_view`. Run `00f7b6bc` did not.

If the model must ask, the policy says to use the card: "call wait_for_input to publish one interactive question, rather than writing a numbered menu" (`lonora.md:131`), with "short options relevant to that particular question" (`lonora.md:132`). [24] asked in plain text instead. Nothing enforces either line.

### 2.5 Guards on main

Reproduced (1a and 1b): the scripted model returned the [24] text; the run committed it unchanged (`reply_outcome: answered`, no runtime notice, "did any guard change or hold the reply?: False").

- The stop gates act only on Task runs. `apply_stop_gates` returns `StopGateVerdict(continue_turn=False)` unless the run is a continuous Task or has unfinished declared steps (`packages/agent-runtime/src/lonora_agent/stop_gates.py:99-104`), and for a chat Run with no `task_id`, `task_stop_gate` returns that verdict before it ever reaches them (`stop_gates.py:178-181`).
- The PR #42 guard only appends a line when a financial result is uncertain (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:23-37`, `:134`).
- No code inspects a reply for a refusal or a parameter question.

### 2.6 Is a "smallest size" or "proposal card with suggested numbers" mechanism available?

- Smallest size: only as data (`volume_min` from `market_instrument`). No tool or policy line says to use it when the owner gave no size.
- A question card with suggested numbers: `wait_for_input` takes up to six choices of `{id, label}` (label up to 240 characters) plus free text (`packages/tools/src/lonora_tools/runtime_control.py:22-32`; `packages/contracts/src/lonora_contracts/input_request.py:8-10`). It is native. Reproduced in section 4.
- `owner_action_propose` cannot carry a trade or a size. Its kinds are `resume_trading`, `lift_restriction`, `resolve_operation`, `set_account_limits`, `grant_authority`, `trust_source`, `connect_credential` (`packages/contracts/src/lonora_contracts/owner_actions.py:19-28`). `set_account_limits` could set a `max_trade_risk`, which is a ceiling and not a size. It is not native.
- A trade approval card is raised by `trade_execute` only when no grant covers the request (`trade.py:334-341`). Under this grant the trade is sent directly, so there is no "propose this exact trade with these numbers" card for a covered trade.

### 2.7 Verdict for [24]: FAILS

The same owner message produces the same reply on main: no default size, the decisive policy line arrives only after the first trade call, the error for a missing volume names no source, and no guard holds the reply.

Settled by the trace and code (checker; this replaces an earlier "TRACE MUST CONFIRM"): `volume_min` 0.01 and `contract_size` 100 were in front of the model (`production-trace.md`, Part 4, `00f7b6bc` #29). The `trading` chapter could not have been in that run's requests. The run's only calls were `account_read`, `market_quote` and `market_instrument` (Part 2, #484-489; Part 4 #26), which map to `account` and `market` (`manifest.json:52`, `:54`, `:97`), and chapter selection uses only the run's own calls (above).

## 3. [30] → [31] «لا أستطيع فتح 10 صفقات…»

### 3.1 What happened in production

Run `cc8399d7` made no tool call and replied in three seconds (`production-trace.md`, Part 1 run list; Part 2 lifecycle). Pure model refusal.

### 3.2 Is there a server limit on the number of trades?

Under this grant and this account: none.

- Grant caps `maximum_positions` and `maximum_actions` apply only when set (`packages/trading/src/lonora_trading/account_authority.py:262-263`, `:282-286`); both are `null` in a full delegation (section 1.1).
- Account cap `max_positions` defaults to unset (`execution_quality.py:21`).
- Money limits unset (section 1.3).
- Per run: 24 tool rounds (`packages/agent-runtime/src/lonora_agent/runtime.py:8`; `packages/gateway/src/lonora_gateway/service.py:75`). Ten entries fit.

Reproduced (`runs/conv-D-ten-debug.out`): ten SCRIPTED `trade_execute` buys of 0.01 XAUUSDm, each with a slightly different SL/TP, one per model turn, in one run answering [30]. All ten returned `"status": "confirmed"` with `"authorization": "account_authority"`; the broker showed 10 positions; `approval_cards_in_this_run: 0`; run `completed`, `rounds: 11`.

(Note on the first driver: its section 2d shows 9 new positions for ten scripted steps. That is a driver artifact: the patched model also answered one in-run summary request, which consumed a scripted step. The debug run has one spare and shows all ten.)

Checker rerun (same database 12, now carrying the history of earlier runs; `runs/check/conv-D-ten-debug.rerun.out`): 9 of 10 executed, all `confirmed` under `account_authority`, with 0 approval cards. The missing entry (`var-8`) went to a side model request that has the same shape as the summary request above (turn 8, `messages=2`), and that request came earlier because the thread history is now larger (105 messages at turn 1 against 36). The same artifact explains 2d on the rerun (8 new positions). So the mechanism reproduces, but the "all ten" count reproduces only in the author's original run. No server limit stopped any entry in either run.

### 3.3 A real mechanical trap: ten identical entries in one run open one position

`trade_execute` derives the operation id from the run id and the arguments: `args["operation_id"] = stable_id(context.lease.run_id, "trade:" + request_hash(args))` (`trade.py:635`). The executor answers an existing id with its stored receipt and sends nothing (`packages/trading/src/lonora_trading/execution.py:162-168`). The guardrail then refuses the sixth identical effect (`IDENTICAL_EFFECT_BLOCK_AFTER = 5`, `packages/agent-runtime/src/lonora_agent/tool_guardrails.py:69`) and halts the run after two refused repeats (`tool_guardrails.py:71`, `:240-257`).

Reproduced (2b): eight SCRIPTED identical buys of 0.01, one per turn.

- Calls 1 to 5 each returned `ok: true, status: confirmed` with the same `operation_id` and the same `broker_id`: "distinct operation ids among the results: 1 of 7"; positions went from 1 to 2 (one new).
- Call 6: `{"ok": false, "code": "guardrail_blocked", "executed": false, "guardrail": {"action": "block", "code": "identical_effect_block", "tool": "trade_execute", "count": 5}, "message": "trade_execute was not executed: it already ran 5 times in a row with identical arguments in this run, and this call changed nothing. Use the earlier results, change the request, or report to the owner."}`
- Call 7: `"code": "identical_effect_halt"`; the run ended with `exit_reason: guardrail_halt` and the owner saw «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.»
- Reproduced (2c): three identical buys in one model turn also opened one position.

Consequences:

- A model that takes «خذ 10 صفقات» literally and repeats the same call sees five "confirmed" results for one position. Each result is true for that one operation, and nothing in it says "this is a replay of an earlier call": the executor returns the stored `TradeResult` unchanged (`receipt`, `packages/trading/src/lonora_trading/execution.py:63-68`). The model can then report several trades that do not exist. The only true signal is the identical `operation_id`.
- (Checker, added) Worse, the runtime tells the model the opposite. From the second identical call on, the guardrail attaches a `tool_guardrail` notice to the result (`tool_guardrails.py:370-373`, attached at `packages/agent-runtime/src/lonora_agent/tool_block.py:332-334`): "trade_execute has now run 2 times in a row with identical arguments. Each call is a separate effect, not a retry: check the earlier results and do not repeat it unless another identical effect is really intended." (text at `tool_guardrails.py:117-121`). For `trade_execute` inside one run this is false: the call was a replay of the same operation. Reproduced: in the stored state of the 2c run in database 12 (three identical buys in one turn, one position), results 2 and 3 carry this notice next to the same `operation_id` `ad7600a9-…` (`runs/check/conv-D-2c-state.json`).
- `TradeRequest` has one reference field, `thesis_id` (`trading.py:15`), and `trade_execute` keeps it in the hashed arguments when it is set (`packages/tools/src/lonora_tools/trade.py:624-625`). But it must name a real owned opportunity on the same account and symbol, and an entry needs that thesis `confirmed` and not already acted on (`packages/trading/src/lonora_trading/opportunities.py:201-214`). So it cannot serve as a free per-entry marker.
- The idempotency rule is a money-safety rule (operation identity, no double send after a lost response) and must stay. What is missing is a way to ask for N separate entries that the rule can tell apart, and a replay marker in the result. `TradeRequest` has no count field and no free client reference field (`trading.py:14-38`; on `thesis_id`, see above).
- This did not cause [31] (no call was made), but any fix that makes the model act on [30] meets it at once.

### 3.4 Which policy lines produce the refusal

No line forbids several trades. The lines that make a model stop on this message:

- "Missing current evidence is unavailable; never invent it or force a trading/waiting quota." (`trading-policy.md:1`). "Ten trades" reads as a quota.
- "A profit target is an objective, never a guarantee or reason to force a trade." (`permissions.py:180`)
- "Do not invent a price threshold or trade parameters merely to fill a watch" (`tool-policy.md:5`), for «ربح كويس».
- "Ask for owner preferences or missing financial limits" (`lonora.md:136`)
- "A watch is cancelled with watch_cancel … Say something was done only when a successful tool result in this request shows it." (`trading-policy.md:7`) covers claims, not this.

Lines that asked for the opposite, also in the request:

- "Preserve the objective and known answers. Reassess a requested side from current evidence; choose an immediate action, a concrete conditional plan, or explain a genuine obstacle without asking for known details again." (`lonora.md:138`)
- "Do not ask the owner whether to perform analysis, inspect a chart or build a plan they already requested: do that reversible work first." (`lonora.md:135`)
- "For necessary owner clarification use wait_for_input, with question-specific choices and free text, rather than plain numbered menus." (`tool-policy.md:15`)

The model wrote «لا أستطيع» for something no tool, limit or rule prevents. No text says "never state inability without checking the tools", and nothing checks it (principle 7 has no mechanism on main).

### 3.5 Guards on main

Reproduced (2a): the [31] text with no tool call was committed unchanged (`reply_outcome: answered`, no notice).

### 3.6 Verdict for [31]: FAILS

Settled by the trace: `cc8399d7` made zero tool calls (`production-trace.md`, Part 1 run list; no tool event for it in Part 2). Nothing is left for the database to confirm. (The provider's reasoning text, if any, would only be of interest.)

## 4. [32] → [33] numbers asked in plain text; plans

### 4.1 What happened in production

Run `1755d8d8`: no tool call; the reply asked «كم تريد ربحًا مستهدفًا، وكم حد الخسارة المقبول؟» in plain text (`production-trace.md`, Part 1). It also dropped "ten trades" from [30] without saying so.

### 4.2 The card mechanism exists and works

Reproduced (3b), SCRIPTED `wait_for_input` with three choices carrying numbers («هدف +2$ / وقف -1$ على الصفقة الحالية», «هدف +5$ / وقف -2.5$ على الصفقة الحالية», «10 صفقات 0.01، هدف +2$ ووقف -1$ لكل صفقة»):

- result `{"ok": true, "_runtime_wait": true, "question": "أي خطة تريدها للذهب؟", "choices": [...]}` (`runtime_control.py:100`);
- run status `waiting_input`; the question is stored as the assistant row and later shown to the model with its choices (`packages/agent-runtime/src/lonora_agent/context/history.py:173`).
- In production the same agent used this tool twice later, in runs `ddae66ad` and `e343c96a` (`production-trace.md`, Part 2, #919/920 and #1024/1025), so it was offered and usable at [33].

Limits of the card: at most six choices, each one text label, no structured numbers (`runtime_control.py:28-32`; `input_request.py:8-10`). An answer "cannot grant or transfer authority or approve trades" (`runtime_control.py:201`); under a grant the authority is the grant, so the trade that follows an answer is sent by `trade_execute` as in section 2.3. UNSURE: I did not run the answer-then-trade sequence end to end.

### 4.3 Guards on main

Reproduced (3a): the plain-text question of [33] was committed unchanged. `lonora.md:131` and `tool-policy.md:15` ask for the card; nothing enforces them.

### 4.4 Plan mechanisms

Three exist. The goal and task tools are not native for the personal assistant in a chat run, but `watch_create` is (run output 1a, native list; production BASELINE list, `production-trace.md`, Part 1).

- **Goals.** `goal_create`: "Persist a trading goal and ordered plan in this same agent/chat. Saving a plan grants no authority; live actions follow current Agent permission and exact signed account scope." (`packages/tools/src/lonora_tools/trading_goal.py:484-485`), with `goal_read` (`trading_goal.py:498`), `goal_plan` (`:513`) and `goal_step_execute` (`:531`). Reproduced (3c): `tool_environment {"query": "trading plan goal"}` returned `goal_create, goal_plan, goal_read, watch_create, task_control, task_step_update`; the Arabic query `{"query": "خطة"}` returned `"tools": [], "total": 0`. Policy says a separate Goal is not needed here: "Under active account management, continue its existing Task and account grant; an objective does not require creating a separate Goal or seeking another grant." (`lonora.md:374`). (Checker: that line is in the `goals` chapter (`lonora.md:370-404`), which loads only after a goal-tool call, so the [32]-[35] runs never saw it. The always-loaded constitution points the other way: "For a persistent objective, inspect goal_list and reuse a real existing Goal ID; create a bounded Goal with goal_create only when none fits." (`tool-policy.md:5`).) Known obstacles of the goal tools are listed in `map-tools-trading.md`, findings 7 to 9; I did not re-verify them.
- **Tasks.** `task_start` for durable work (`packages/tools/src/lonora_tools/tasks.py:106`; `tool-policy.md:9`).
- **Watches with an action.** `watch_create` (native, `packages/tools/src/lonora_tools/market_watch.py:238`) with `kind="position"` and `metric="profit"` (`packages/contracts/src/lonora_contracts/market_watch.py:15`, `:36`, `:84-85`). This covers «بس صار ربح كويس وقفهم» once a number exists. It belongs to group C.

For one open position with a money target and a money stop, no plan object is needed: TP and SL on the broker do it (section 5).

### 4.5 Nothing holds the open request

Searched `pending_offer|open_request|pending_request|last_offer` (case-insensitive) in `packages/agent-runtime/src`, `packages/db/src`, `packages/tools/src`: no match. (Checker, second search: `standing_request|owner_objective|current_objective|objective` over `packages/agent-runtime/src/lonora_agent/context/*.py` finds only saved-Goal objectives (`context/goals.py:48`) and the permission sentence at `permissions.py:180`. A saved Goal is the only durable carrier, and it needs `goal_create`.) The request of [30] (ten trades, sell them at a good profit) exists only as chat history. "A short reply continues the preceding request" (`lonora.md:130`) is the only carrier, and it is advice.

### 4.6 Verdict for [33]: FAILS

Settled by the trace: `1755d8d8` made zero tool calls (`production-trace.md`, Part 1 run list; no tool event in Part 2).

## 5. [34] → [35] the right action: `modify_position` with TP and SL

### 5.1 What happened in production

Run `94d50998` called `account_read`, `market_quote`, `market_instrument` (all ok) and wrote the plan in prose: «الخطة جاهزة على **المركز الحالي فقط**», then «إذا تريد، أضع لك **أمر إغلاق مشروط**…». No `trade_execute`, no `watch_create` (`production-trace.md`, Part 2, #603-612). [29] had already said «لا يوجد وقف خسارة أو هدف مضافين». The model's own read in this run showed it again: position `2217873130`, `"volume":"0.01"`, `"open_price":"4050.819"`, `"profit":"0.97"`, `"stop_loss":null`, `"take_profit":null` (`production-trace.md`, Part 4, `94d50998` #37).

Correction to the trace's own reading (checker): Part 4, finding 8 says the model "never set SL/TP (no trade-modify tool in the native list)". That is wrong. `trade_execute` was native in this run (BASELINE list, Part 1; U0) and accepts `action: "modify_position"` (section 5.2). The tool was there, and the model did not use it.

### 5.2 The tool supports it

- `action: "modify_position"` with `stop_loss` and/or `take_profit` as absolute prices and a `position_id` (`trading.py:18-38`); at least one field is required (`trading.py:54-66`), `volume` and `price` are refused for it (`trading.py:67-76`), `position_id` is required (`trading.py:92`).
- The grant covers it: `modify_position` is one of the ten actions; under `full` mode moving or adding a stop is not restricted (`account_authority.py:314-327` apply to `bounded` only).
- MetaApi implements it (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:871-874`).

### 5.3 Data needed, and where it comes from

| Needed | Source |
|---|---|
| `account_id`, `position_id`, open price, volume, side | `account_read` (native) |
| exact symbol | the position itself |
| money per price unit | `contract_size` from `market_instrument` (`market.py:20`), or `profit_tick_value` / `loss_tick_value` and `tick_size` from `market_quote` (`market.py:33-35`, `market.py:14`) |

Run `94d50998` had made exactly these three reads.

Arithmetic for the position of [26] (buy 0.01 at 4050.819, contract 100): 0.01 × 100 = 1 unit, so 1 USD per 1.000 of price. TP = 4050.819 + 2 = 4052.819; SL = 4050.819 − 1 = 4049.819. This matches the brief's «TP≈4052.82 وSL≈4049.82».

Settled by the trace (this replaces an earlier "TRACE MUST CONFIRM"). In run `94d50998`, `market_instrument` returned the same body as in `00f7b6bc`, with `"contract_size":"100"` and `"tick_size":"0.001"` (`production-trace.md`, Part 4, #41 → #29). The quote of this run is cut in the export (#39 shows only bid/ask), but three minutes earlier the same account's `market_quote` carried `"profit_tick_value":"0.1","loss_tick_value":"0.1"` (#28). The fields are normalised at `packages/adapters/src/lonora_adapters/brokers/normalize.py:50` and `:57-58`. Either route gives 1 USD per 1.000 of price for 0.01 lot (0.01 × 0.1 ÷ 0.001 = 1). The reported P/L agrees: (4051.792 − 4050.819) × 1 = 0.973 against `"profit":"0.97"`.

### 5.4 Reproduction on the simulation broker

Position: buy 0.01 XAUUSDm at 4050.819, opened under the delegation; quote moved to 4051.792 / 4052.032 as in [35].

- 4a, SCRIPTED: the three production reads, then the [35] text. `market_instrument` returned `"volume_min": "0.01", …, "contract_size": "100"`; `market_quote` returned `"profit_tick_value": "0.1", "loss_tick_value": "0.1"`. The reply was committed unchanged ("did any guard change or hold the reply?: False"); the position still had `stop_loss: None, take_profit: None`.
- 4b, SCRIPTED: `trade_execute {"action": "modify_position", "account_id": …, "symbol": "XAUUSDm", "position_id": …, "stop_loss": "4049.819", "take_profit": "4052.819"}` returned `"status": "confirmed"`; zero approval cards; position after: `'stop_loss': '4049.819', 'take_profit': '4052.819'`.

One detail for whoever relies on this under a brake: a `modify_position` that sets a new take profit is not classified as risk-reducing (`packages/trading/src/lonora_trading/admission.py:128-129`), so while Stop new trading or a pause is in force it is treated as new risk. Setting only a stop loss where there was none is risk-reducing (`admission.py:133-134`). With trading running, as in this conversation, both pass.

### 5.5 Why the plan was narrowed silently and nothing was done

- No state holds the request of [30] (section 4.5), so «10 صفقات» is simply gone by [35].
- Lines that favour describing over acting were in the request: "A profit target is an objective, never a guarantee or reason to force a trade." (`permissions.py:180`); "Informational replies never authorize financial execution." (`tool-policy.md:15`); "Do not turn an analysis/watch step into a trade step silently." (`lonora.md:108`).
- The `trading` chapter line "Under active signed full management, choose size, stops and targets…" (`lonora.md:337`) was again not loaded: the run made no trading-chapter call (section 2.4).
- No guard stops a reply that ends with «إذا تريد…» when the offered step is inside the grant (principle 3 has no mechanism; shown in 4a).

### 5.6 Verdict for [35]: FAILS

The same message on main gives prose and an offer; the tool that does the job works and needs no approval.

## 6. Which refusals money safety requires, and which it does not

Required, and working (keep):

- A trade is sent only under a matching signed grant or the owner's approval card, at the one executor (`trade.py:301-341`, `:577-618`; `execution.py:148-217`). Reproduced: every scripted trade went through `account_authority`; no shadow path.
- A trade outside the grant becomes an approval card, never a refusal (`trade.py:334-339`).
- The same request in the same run is never sent twice (`trade.py:635`; `execution.py:162-168`).
- Exits stay admissible. Reproduced (2e): eleven `close_position` calls under the delegation, all `confirmed`, no card (checker rerun: nine calls, because fewer extra positions were open, all `confirmed`, no card).
- Chat agreement is not financial confirmation (`lonora.md:101`; `runtime_control.py:201`).
- "Never silently increase lot size, remove a stop, or change account to make a trade pass." (`lonora.md:338`)
- A missing entry volume is refused before anything is sent (`trading.py:77-81`). The executor must never invent a size; choosing one is the agent's job, stated in the confirmation.

Not required by any money rule:

| Reply | Why it is not a safety refusal |
|---|---|
| [24] asking for a lot size | The grant covers the entry; the policy assigns sizing to the agent (`lonora.md:106`, `trading-policy.md:1`, `permissions.py:140-141`); a broker-valid minimum was in the tool result. Asking is allowed only when no safe value can be derived, and then as a card (`lonora.md:131`) |
| [31] «لا أستطيع فتح 10 صفقات» | No limit exists (section 3.2). The honest obstacle was «ربح كويس» having no number, which is a question with suggested numbers, not an inability |
| [33] plain-text question | The question is legitimate (a profit and loss amount is the owner's to give); the form is not: policy asks for the card |
| [35] prose plan and offer | `modify_position` is covered by the grant and was fully computable from the three reads just made |

One point where the brief and the repository disagree, to be decided by the owner and not here: a default size "from the delegation/risk policy" (principle 6) does not exist, and `docs/account-authority.md:127`, `docs/broker-position-sizing.md:6-7` and `lonora.md:23` state that none is chosen for the owner.

## 7. What the production database must still confirm

1. The signed envelope and the stored card choice (section 1.5): `ln_account_authorities.envelope`, and `ln_owner_actions.payload.delegation` / `result.money_limit` of the grant card.
2. (Settled, see 2.7: Part 4 #29 and code.)
3. (Settled, see 5.3: Part 4 #41 / #28.)
4. Run `65e8b682` ([26]): the trace already shows the resulting position as 0.01 with no SL/TP (Part 4, `94d50998` #37) and a run with no waiting state (Part 2 lifecycle). Still open: the `trade_execute` result body (`"authorization": "account_authority"`) and the absence of a `TradeApprovalRow`, plus one journal row for position `2217873130`. The `receipt_replay true` in Part 1 is the route record's copy of the tool's static `replay_safe` flag (`packages/agent-runtime/src/lonora_agent/environment.py:182-187`), not evidence of a second send.
5. Whether the management Task's own Run (`779e4761…`, in thread `ea0e47c6`) ever opened or sized a trade by itself. It is the only Run whose prompt says "choose your own … lot size" (section 1.2). The export covers only thread `3c25305d`. For the Task Run it shows just one product: the EURUSDm watch `3789e892`, created at 09:44:53 (Part 1, Q4 record 1).

## 8. State left in database 12

The drivers left one owner, the personal assistant with an active full delegation on two simulation accounts, open simulated positions and the chat history of the scripted runs. The other user of database 12 shares that owner and that personal-assistant thread. `git -C /home/user/lonorabot status --short` is clean.

## Verification log

Checker pass: an independent check of this file against the repository (`git -C /home/user/lonorabot` HEAD `3f09572`, which differs from `9f5b1da` only by notes under `docs/`, so every code line number equals main), `production-trace.md` (all four parts), `TIMELINE_CORRECTION.md` and `lonora-chat.md`.

### Citations opened

I opened every `path:line` citation of the original file (about 110 distinct citations over 40 files) and read the cited lines. Every verbatim English quote of policy, tool descriptions and guard messages was compared character by character, and matched: `lonora.md:23`, `:101`, `:106`, `:108`, `:130-138`, `:230`, `:337`, `:338`, `:374`; `tool-policy.md:3`, `:5`, `:15`; `trading-policy.md:1`, `:7`; `SOUL.md:7`, `:10`; `SKILL.md:23-24`; `permissions.py:140-142`, `:180`; `account_authority.py` (auth) `:148-150`; `position_sizing.py:22-27`; `risk_limits.py:3-4`; `trading_goal.py:485`; `runtime_control.py:201`; the guardrail block text; the docs quotes. The Arabic quotes of [24], [31], [33] and [35] match `lonora-chat.md` lines 196, 251, 263 and 275-290. The «لم يُضبط» line matches `attention_messages.json:30` and trace Part 3 seq 6.

Corrected citations:
- `trading_goal.py:531` was cited for `goal_plan`, `goal_read` and `goal_step_execute`; only the last is there. Now `:498` (`goal_read`), `:513` (`goal_plan`), `:531`.
- `metaapi.py:871-872` → `:871-874` (the call spans four lines).
- `normalize.py:58` for tick values → `:57-58` (profit at 57, loss at 58).
- `execution_quality.py:16-26` "All default to unset" was not exact: the quote and account age bounds default to 60 s (`:17-18`). Wording fixed.
- `stop_gates.py:99-104` "returns 'stop'": the function returns `StopGateVerdict(continue_turn=False)`; reworded and `:178-181` added.

### Reproductions rerun (database 12, `scripts/conv_d_delegation.py`, `scripts/conv_d_ten_debug.py`; outputs in `runs/check/`)

- 0 (signed envelope, task, permission frame, account policy): reproduced.
- 1a (`volume_required` result, no card, reply unchanged, chapter line absent from turn 1 and present after `trade_execute`): reproduced. The native list differed (24 tools rather than 22, with `market_position_size` and `market_symbols`) because the database already held the 1c use and long-tail tools are promoted (section 2.3 note). This is not a code difference.
- 1b, 1c, 2a, 2b (one position for five "confirmed", block at call 6, halt and the «توقفت…» line at call 7, "1 of 7" operation ids), 2c, 3a, 3b, 3c, 4a, 4b: reproduced with the same results.
- 2d: 8 new positions on the rerun (9 in the original). 2e: 9 closes (11 in the original). Ten-debug: 9 of 10 executed on the rerun (10 in the original). The cause is the driver artifact the author named: a side model request consumed a scripted step, earlier this time because the thread history was larger. Marked in section 3.2. The "all ten" count is NOT REPRODUCED on the rerun; the conclusion it supports (no server limit stops ten entries) stands.

### Claims refuted, downgraded or corrected

1. "no arguments and no result bodies" in the trace (Evidence used): refuted. Part 4 has results for `00f7b6bc` and `94d50998`. Two of the three "TRACE MUST CONFIRM" items in sections 2.7 and 5.3 are now settled by Part 4 #29, #41, #28 plus code. The [31]/[33] items are settled by Parts 1-2. Section 7 has been rewritten. One item is still open (1.5), and parts of two others (7.4, 7.5).
2. 1.5 "The message had no run, so the card came from the mandate sheet": the inference was invalid, because every confirmed card's acknowledgement is a run-less message (`packages/db/src/lonora_db/owner_actions.py:1999-2020`). The conclusion stands on different evidence (no `owner_action_propose` call in the thread; the mandate-sheet route exists at `apps/api/src/lonora_api/routes/account_authority.py:70-111`). The UNSURE reading of a Custom card with Full's terms and `money_limit=none` is now backed by code (`packages/core/src/owner-actions.ts:920-924`; `OWNER_DECISIONS.md:46`). It still needs the database row.
3. 4.4 "None is native": contradicted by its own bullet. `watch_create` is native. Fixed.
4. 4.4 `lonora.md:374` quoted as policy that applied: it is in the `goals` chapter (`lonora.md:370-404`) and was not loaded in these runs; `tool-policy.md:5` (always loaded) pushes toward `goal_create`. Added.
5. 3.3 "The only signal is the identical operation_id": kept, but the runtime's own guardrail notice tells the model the opposite ("Each call is a separate effect, not a retry"). Added with a reproduction.
6. 3.3 "`TradeRequest` has no … client reference field": narrowed. `thesis_id` exists and changes the operation id, but it must name a real confirmed opportunity (`opportunities.py:201-214`).

### Counter-evidence searched, nothing found (classifications kept)

- All four verdicts stay **FAILS** ([24], [31], [33], [35]). No mechanism on main changes any of these replies. I checked the reply pipeline in `trace-guards.md` section 1, re-verified here for the stop gate and `uncertain_outcome.py:23-37` (financial tool names only). I also checked the diff `2477c22..9f5b1da`: it adds GenUI handling only, which does not apply because `ui_submit` is empty on every row.
- No default size: two independent searches (`default_volume|default_lot|default_size|risk_per_trade|lot_size\s*=|DEFAULT_.*(VOLUME|LOT|RISK)` over `packages apps`; and a search for literal `"0.01"` volume defaults) found none. The only suggested money number is the 3% daily loss on the grant card (D1), added to 1.4.
- Task description visible to a chat Run: not through the context builder, and not through `agent_inspect` (`supervision.py:219-227`). Added to 1.2.
- Open-request state: a second search found only saved Goals. Added to 4.5.

### Claims added (with citations)

- Section 2.1: the production results in front of the model at [24] (Part 4 #27-#29); [27] is a result card, and the run had no waiting state.
- Section 2.3: per-agent promotion of long-tail tools into the native list (`tool_exposure.py:3-4`, `:151-181`; `registry.py:85`).
- Section 2.4: `lonora.md:228` ("Read min/max/step volume…"). The history replayed into a chat Run carries no tool calls, so an earlier run's `trade_execute` never loads the `trading` chapter for later runs.
- Section 3.3: the misleading `identical_effect_warning` text (`tool_guardrails.py:117-121`, `:370-373`; `tool_block.py:332-334`), reproduced in `runs/check/conv-D-2c-state.json`.
- Section 5.1: Part 4 #37 (SL/TP null in the model's own read). The trace's finding 8 ("no trade-modify tool in the native list") is incorrect, because `trade_execute` with `modify_position` was native.
- Section 5.3: a P/L cross-check of the contract arithmetic against production numbers.
- Timeline paragraph: the GenUI changes between builds, and why they do not apply.
- Section 7.4: the meaning of `receipt_replay` (`environment.py:182-187`).

Totals after this pass: 4 verdicts (4 FAILS, 0 PARTLY, 0 FIXED); 1 "TRACE MUST CONFIRM" left (section 1.5), plus two partly open items in section 7 (4, 5); 2 earlier "TRACE MUST CONFIRM" items turned into settled statements (2.7, 5.3) and 2 "nothing to confirm" notes made explicit (3.6, 4.6).
