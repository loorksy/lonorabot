# J1: the gold journey and broker/market symbol failures

Repository `/home/user/lonorabot`, HEAD `9f5b1da` (PR #42 is an ancestor of HEAD; `git diff --name-only aa50e8e^1 aa50e8e -- packages` touches 9 files and none of them is a symbols, market, adapter, environment, discovery, dispatch, exposure or chart file, so no symbol failure below can be "fixed or caused by PR #42").
Database used: number 1 (`audit_j1_test`). Repo status after all runs: `git status --short` prints nothing.

## 0. How to read this file

What is REAL in every run (real code, not mocked):
the FastAPI app and PostgreSQL, the Personal Agent row (`role=personal`, `scope_mode=fixed_market`, `trading_account_id=null`, `trading_symbol=null`, matching production-trace.md), the message route, the context builder, the model turn, the tool loop, the registry, tool dispatch, `environment.classify`, the exposure/native-tool selection, the stream events, and a real `MetaApiBroker` object running its own `symbols`, `instrument`, `quote`, `candles`, `read_rpc`, `diagnose` and `provider_error` code.

What is FAKE:
- **SCRIPTED**: every model turn. The script only picks which tools are called and (in a few runs) a placeholder final text. A scripted final reply is never evidence of what a real model would say. The evidence is the tool result, the injected guard text, the stream event and the committed message.
- **FAKE SDK**: the MetaApi RPC connection under the real `MetaApiBroker` (no network). An unknown symbol raises the SDK's own `NotFoundException` (status 404). Its message text is an ASSUMPTION ("Symbol not found", the text `tests/test_market_data_billing.py:68` uses). The text only matters on the candles stage (see J1-07); on the quote/instrument/rpc stages the code does not read the text (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:57`).
- The stored connection row says `provider=simulation` (no secret stored); the object the tools reach is the MetaApiBroker above. Account facts (Exness, `Exness-MT5Trial16`, login `00000000`) are fixture values. The symbol catalog is `BTCUSDm, EURUSDm, USOILm, XAGUSDm, XAUUSDm`.
- The fixture's native tool list has 22 tools; production offered 23 (production-trace.md line 17). The only difference is `web_search`, which production had and the fixture (no research provider configured) leaves out (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:5`). Everything else is the same list: `account_read, agent_inspect, chart_snapshot, list_accounts, market_candles, market_decision_history, market_decision_record, market_instrument, market_quote, market_sessions, market_snapshot, memory_read, memory_write, peer_send, session_search, skill_view, skills_list, tool_call, tool_environment, trade_execute, wait_for_input, watch_create`.

Files (all outside the repo):
- harness: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/j1_lib.py`, journeys `.../scripts/j1_gold.py`, runner `.../scripts/j1_run.sh`, search matrix `.../scripts/j1_search.py`
- raw output of each run: `.../audit/runs/J1-01.txt` ... `J1-10.txt`
- Rerun any journey NN (01 to 09):
  `cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 1 && /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/j1_reset_db1.sh && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/j1_gold.py J1-NN`
  (shortcut that does the same and saves the output: `.../audit/scripts/j1_run.sh J1-NN`).
- Rerun J1-10 (no database needed):
  `cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 1 && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/j1_search.py`

Connection ids, run ids and times differ on every run. In the quotes below `<conn>` stands for the connection id the runtime printed.

### Reconciliation with the production trace (trace wins)

The production run `1ae9a14c` (09:44:01 UTC, production-trace.md lines 31, 93-95, 243-249) did: `list_accounts`, then `market_snapshot` for `XAUUSD` (timeframes 15m/1h/4h/1d) -> `symbol_not_found`, then `market_instrument` for `XAUUSD` -> `broker_account_not_found`, with recovery `{"category":"not_found","next_action":"inspect_existing_state","safe_to_retry":false,"schema_tool":"tool_environment","attempt":1,"retry_exhausted":false}`. J1-01a reproduces exactly these two codes and the same recovery block, on the same two tools, from the same cause (code paths below). Two statements in earlier notes/briefs are corrected by the trace and by my runs:
1. The model did not "ask" the owner a technical question first and then fail; it called no discovery tool at all (trace lines 238, 243-249). The native list never contained `market_symbols` (trace line 17; J1-01a prints the 22 names).
2. "market_instrument took five seconds" (lead's reading, point 3) is NOT reproduced: with a fake transport the failure is instant. I cannot say why production took five seconds (UNSURE: probably the real SDK's connection wait or one retry in `read_rpc`, `packages/adapters/src/lonora_adapters/brokers/metaapi.py:422-435`, which retries once after a closed connection; I did not confirm).

---

## Summary table

| id | owner asked | what the runtime returned | class |
|---|---|---|---|
| J1-01 | «طيب شو وضع الذهب» (gold on an account whose gold is XAUUSDm) | `broker_account_not_found` / `symbol_not_found`, no candidates, `market_symbols` not native; the owner's own bad reply is committed unchanged | recoverable-not-led, technical-question, leak |
| J1-02 | «كم سعر الذهب الآن؟» (the word "gold" used as the symbol) | five different tools, all `*_not_found`, none lists what exists | recoverable-not-led |
| J1-03 | «ارسم لي شارت الذهب على الساعة» | `symbol_not_found`; `chart_open` returns ok for a bad symbol and leaves a failed chart; lower-case spelling refused by the chart tool only; `H1` refused | bug, recoverable-not-led |
| J1-04 | «نبهني إذا الذهب طلع فوق 4100» | `watch_create` ok for a symbol the account does not have; the watch is dead on its first poll; nobody is told | bug, dead-end |
| J1-05 | «حلل لي الذهب الآن وارسم الدعم والمقاومة» with 50-hour-old data | quote and candles return ok with old data and no flag; `market_structure` refuses with `market_candles_stale`; the recovery class is wrong | bug, recoverable-not-led |
| J1-06 | «كم سعر الذهب على حساب 00000000؟» (broker login used as account_id) | `broker_sessions_not_found` (a table name) | technical-question, recoverable-not-led |
| J1-07 | «أعطني شموع الذهب» (candles 404 with another provider text) | `broker_candles_not_found`; `M15` -> `unsupported_timeframe` with no list of valid values | recoverable-not-led, bug |
| J1-08 | «كم سعر الذهب الآن؟» with no broker account connected | `accounts: []`, `broker_sessions_not_found`, `research_provider_not_configured` | owner-needed (but not led) |
| J1-09 | control | which tools tolerate a case-only difference and which do not | bug |
| J1-10 | tool search matrix | `gold`, `XAUUSD`, `الذهب`, `symbol suffix` find nothing | recoverable-not-led |

---

## J1-01: «طيب شو وضع الذهب» on an account whose gold symbol is XAUUSDm (THE GOLD JOURNEY)

**Owner request**: «طيب شو وضع الذهب» (production message [9], answered at [10] with the reply quoted in the task).

**Rerun**: `.../scripts/j1_run.sh J1-01` (output `.../runs/J1-01.txt`).

**Setup**: personal agent as above; one enabled connection; catalog `BTCUSDm, EURUSDm, USOILm, XAGUSDm, XAUUSDm` (gold exists only as `XAUUSDm`).

### 1a. The failing run

Native tools offered to the model on all five model turns of the run (printed by the harness; identical every turn):

```
peer_send, memory_read, memory_write, session_search, skills_list, skill_view, market_instrument, market_quote, market_candles, market_snapshot, market_sessions, watch_create, market_decision_record, market_decision_history, chart_snapshot, list_accounts, account_read, trade_execute, wait_for_input, agent_inspect, tool_environment, tool_call
market_symbols native: False | market_instruments native: False | tool_call native: True | tool_environment native: True
```

Exposure profiles: `["core","market","coordination"]`. So **no symbol search tool is visible**; `market_symbols` is reachable only as `tool_call {"name":"market_symbols", ...}` or after a `tool_environment` lookup.

SCRIPTED model turns and the literal RUNTIME tool results:

1. SCRIPTED: `list_accounts {}` -> RUNTIME: `{"ok": true, "accounts": [{"connection_id": "<conn>", "broker_identity": {"broker": "Exness Technologies Ltd", "login": "00000000", "server": "Exness-MT5Trial16", ...}, "provider": "simulation", "enabled": true, "credentials_configured": false}], "guidance": "Use connection_id as account_id in account, market and trading tools. ..."}`
2. SCRIPTED: `market_quote {"account_id":"<conn>","symbol":"XAUUSD"}` -> RUNTIME:
   `{"ok": false, "code": "broker_account_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`
3. SCRIPTED: `market_instrument {"account_id":"<conn>","symbol":"XAUUSD"}` -> RUNTIME: the same `broker_account_not_found` + same recovery block.
4. SCRIPTED (parallel): `market_snapshot {... "symbol":"XAUUSD"}` and `market_candles {... "symbol":"XAUUSD","timeframe":"15m","limit":50}` -> RUNTIME: both `{"ok": false, "code": "symbol_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`
5. SCRIPTED final reply: the owner's own example, verbatim, to see whether anything in the runtime changes it.

Server log lines printed during the run (not seen by the model or the owner):
```
broker_rpc_failed code=broker_account_not_found type=NotFoundException message=Symbol not found
broker_rpc_failed code=broker_account_not_found type=NotFoundException message=Symbol not found
broker_candles_failed code=symbol_not_found type=NotFoundException message=Symbol not found
```

What the runtime did with the scripted reply (stream events and run row): `run.reply_started` -> `run.reply_committed` -> `message.created` with content `ما قدرت أقرأ الذهب على هذا الحساب لأن الرمز/الارتباط الحالي غير مطابق في البيانات المتاحة.\n\n- محاولة الذهب على `XAUUSD` رجعت **symbol_not_found**\n- ومحاولة تفاصيل العقد رجعت **broker_account_not_found** ...` -> `run.completed`. The run's `result` is identical to the scripted text and `exit_reason` is null. **Nothing in the runtime rewrote, blocked or repaired a final reply that contains `symbol_not_found`, `broker_account_not_found`, backticks and `**` markers, and ends with an offer ("أبحث لك ... إذا أردت").** The only place the final text is rewritten in the model path is `packages/agent-runtime/src/lonora_agent/model_runtime.py:225-238`, which handles proposed financial calls, unverified financial results and `task_wait`; it does not look at error codes. `apply_stop_gates` returns "stop" for a conversation run with no continuous task and no declared steps (`packages/agent-runtime/src/lonora_agent/stop_gates.py:99-104`).
The public stream also carries the raw code: `tool.completed` events have `"ok": false, "code": "broker_account_not_found"` (and `symbol_not_found`) in their payload (`.../runs/J1-01.txt`, "RUNTIME stream events").

Injected policy text about symbols, and WHEN it appears (the harness diffed each model request):
- Request 1 (before any tool call) contains only the core line `Preserve broker symbols exactly, including case and suffix.` (`packages/agent-runtime/resources/system/lonora.md:60`) and the tool-set catalog line `market: economic_calendar_read, market_candles, ..., market_symbols, watch_cancel, watch_create, watch_list, ...`.
- Request 2 (after `list_accounts`): nothing new.
- Request 3 (after the first `market_quote` call): the market chapter arrives: `Use market_symbols to discover exact symbols before guessing aliases.` (`lonora.md:212`), `Never strip suffixes, substitute an exchange feed or assume one broker's instrument exists at another.` (`lonora.md:224`), `If several symbols plausibly match an alias, discover real candidates and ask which one.` (`lonora.md:225`), `A truly unknown symbol is not a generic connection failure.` (`lonora.md:239`).
  Cause: domain chapters are selected by tool names the assistant ALREADY called in the last 16 messages (`packages/agent-runtime/src/lonora_agent/skills/system_policy.py:1-5, 134-140`). The first market call is therefore made without the chapter.
- The long gold/suffix paragraph (`packages/agent-runtime/resources/prompts/trading_context.md:5`: "Gold may have broker suffixes or a different broker name; never guess or strip them. Letter case alone is not a different symbol ...") never appears in any of the five requests. A repo-wide grep for `trading_context` finds no code that loads it (only `lonora.egg-info/SOURCES.txt` and notes under `docs/research`): **the file is dead text**.

**What the owner sees** (scripted reply shown only to prove it is not changed): two raw error codes in bold with backticks, an apology, and an offer instead of an action. In production this is what message [10] looked like.

**Root cause chain (code wins over prompt)**
1. `market_instrument`/`market_quote`/`market_candles` call `canonical_broker_symbol(broker, args["symbol"])` WITHOUT `require_exists` (`packages/tools/src/lonora_tools/market.py:47, 58, 65`). `catalog_symbol` only accepts an exact or case-only match (`packages/tools/src/lonora_tools/symbols.py:9-15`); `XAUUSD` vs `XAUUSDm` raises `symbol_not_found`, which `canonical_broker_symbol` swallows and returns the symbol unchanged (`symbols.py:32-35`).
2. The unchanged `XAUUSD` goes to the broker. The SDK answers 404. `provider_error` maps every 404 outside the candles stage to `broker_account_not_found` (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:52, 57-58`: `if stage != "candles" or "account" in message and missing: return LonoraError("broker_account_not_found", 404)`). So an unknown symbol on a healthy account is reported as an unknown account. This contradicts the prompt line `A truly unknown symbol is not a generic connection failure.` (`lonora.md:239`); the code wins.
3. `market_snapshot` (and `market_structure`, `market_sessions`) use `require_exists=True` (`market_analysis.py:140`, `market.py:78`, `market_analysis.py:215`), so they raise the catalog's `symbol_not_found` (`symbols.py:15`) before any broker call. Same word problem, different code: that is why the owner got two different codes for one cause.
4. The tool result is only `{"ok": false, "code": ...}` plus `recovery` (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:113-117`). `classify` turns every `*_not_found` into `not_found` / `inspect_existing_state` (`packages/agent-runtime/src/lonora_agent/environment.py:80-81`). Neither contains the real catalog, a candidate, or the name of the tool that would list symbols. `schema_tool: "tool_environment"` only says which tool shows schemas.
5. `market_symbols` is a registered tool without `eager=` (`market.py:98-105`), while `market_instrument`, `market_quote` and `market_candles` have `eager=eager_for("market")` (`market.py:112, 128, 136`). Non-eager tools are native only after the agent has used them successfully (`tool_exposure.py:1-9, 151-181`; `packages/tools/src/lonora_tools/registry.py:267`). Lonora had never called it, so it was not native. Production confirms: it never called it and it is not in the 23 tools (production-trace.md line 17).
6. The fixed-market auto-fill that would put the right symbol in does nothing here: `prepare_market_arguments` returns the arguments untouched when the agent has no bound account and symbol (`packages/tools/src/lonora_tools/market_binding.py:89-90`), and Lonora's row has `trading_account_id=null`, `trading_symbol=null`.
7. A suffix-aware matcher already exists and would have answered this: `symbol_candidates` (`packages/tools/src/lonora_tools/agents.py:72-91`) returns `['XAUUSDm']` for `XAUUSD` (J1-01c below). It is used only to resolve the focus pair when an agent is created (`agents.py:94-124, 257`; `apps/api/src/lonora_api/routes/agents.py:98`), where it returns candidates and tells the model to ask one focused question (`agents.py:265`). The market read tools do not use it. `resolve_instrument` (`packages/market/src/lonora_market/instruments.py:5-9`, exact match only) has no caller anywhere in the repo (grep), so it plays no part in this failure.

**Class**: recoverable-not-led (a safe read-only next step existed and was not taken), technical-question/leak (codes and an offer reach the owner), and a code bug for the misleading 404 mapping.

### 1b. What a search would have returned, by each route the model has (SCRIPTED turns, RUNTIME results)

Second owner message: «ابحث عن اسم الذهب الصحيح». SCRIPTED turn 1 calls `tool_environment {"query":"gold symbol"}`, `tool_environment {"query":"symbols"}` and `market_symbols {...}` together.

- `tool_environment {"query":"gold symbol"}` -> `{"ok": true, "tools": [], "total": 0, "next_offset": null, "invocation": "Call a tool marked invoke=direct by its own name. Call any other tool with tool_call {...}", "execution_authorized": false}`. **Empty.** (Same shape as production's empty `tool_environment` result for «watch cancel task routines goals», production-trace.md lines 271-272.)
- `tool_environment {"query":"symbols"}` -> lists `market_instruments` and `market_symbols` (purpose: "Discover exact broker symbol names without loading specifications for every instrument. Use before guessing broker symbols or aliases; suffixes matter. ...").
- `market_symbols {"account_id":"<conn>"}` (called directly; see UNSURE 1) -> `{"ok": true, "symbols": ["BTCUSDm", "EURUSDm", "USOILm", "XAGUSDm", "XAUUSDm"]}`. The raw catalog, not a ranked answer.
- Through the bridge (SCRIPTED `tool_call {"name":"market_symbols",...}`) the same list returns, plus `"runtime_notice": [{"kind": "tool_guardrail", "source": "lonora_runtime", "message": "market_symbols returned the same result 2 times. Use the result already provided or change the request instead of repeating it unchanged."}]`.
- SCRIPTED `market_quote` / `market_instrument` with `symbol":"XAUUSDM"` (the owner's typed fix, upper-case M) -> both ok: `{"ok": true, "symbol": "XAUUSDm", "bid": "4049.73", "ask": "4049.97", ...}` and `{"ok": true, "symbol": "XAUUSDm", "description": "Gold vs US Dollar", "digits": 3, ... "volume_min": "0.01", ...}`. The case-only fold works (`symbols.py:11-14`).

### 1c. What the existing suffix matcher returns on the same catalog (REAL call, J1-01c)

`lonora_tools.agents.symbol_candidates(catalog, name)`: `XAUUSD -> ['XAUUSDm']`, `xauusd -> ['XAUUSDm']`, `XAUUSDM -> ['XAUUSDm']`, `EURUSD -> ['EURUSDm']`, `GOLD -> []`, `الذهب -> []`. And `instrument_entry` (`packages/contracts/src/lonora_contracts/instrument_names.py:36-54`) maps a broker spelling TO the Arabic name (`XAUUSDm -> الذهب`, `instrument_names.py:21`) but returns `None` for `الذهب` and `GOLD` (REAL call). The table is used only to display names; nothing maps the owner's word to a broker symbol.

---

## J1-02: «كم سعر الذهب الآن؟» with the owner's word used as the symbol

**Rerun**: `.../scripts/j1_run.sh J1-02` (`.../runs/J1-02.txt`).
**SCRIPTED turn**: one model turn issuing five parallel reads (what a model does after seeing "not found"): `market_quote symbol="الذهب"`, `market_snapshot symbol="GOLD"`, `market_snapshot symbol="gold"`, `market_sessions symbol="XAUUSD"`, `market_structure symbol="XAU/USD" timeframe="1h"`. Final text SCRIPTED placeholder.

RUNTIME results (all `recovery` blocks identical to J1-01):
- `market_quote` «الذهب» -> `{"ok": false, "code": "broker_account_not_found", ...}`
- `market_snapshot` `GOLD` -> `symbol_not_found`; `gold` -> `symbol_not_found`
- `market_sessions` `XAUUSD` -> `symbol_not_found`
- `market_structure` `XAU/USD` -> `symbol_not_found`

Five different tools, three spellings, and the model learns nothing it can act on: no result carries a candidate or the catalog. The owner's Arabic word "الذهب" reaches the broker verbatim and is reported as a missing ACCOUNT.

**Root cause**: same as J1-01 (`market.py:58`, `symbols.py:9-15`, `metaapi.py:57-58`); additionally no alias layer exists between an owner word and a broker symbol (J1-01c; `instrument_names.py:36-54` only goes symbol -> name). `market_sessions` deliberately turns the catalog's `symbol_not_found` into a hard error because "only a symbol the model can correct is an error" (`packages/tools/src/lonora_tools/market_analysis.py:206-221`, `SYMBOL_ARGUMENT_ERRORS` at `:32`), yet the error carries nothing to correct it with.
**Class**: recoverable-not-led.

---

## J1-03: «ارسم لي شارت الذهب على الساعة» (chart request for an alias)

**Rerun**: `.../scripts/j1_run.sh J1-03` (`.../runs/J1-03.txt`); control for the case rows in J1-09.
**SCRIPTED turns** and RUNTIME results:
1. `chart_snapshot {symbol:"XAUUSD", timeframe:"1h"}` -> `{"ok": false, "code": "symbol_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", ...}}`.
2. `chart_snapshot {symbol:"xauusdm", timeframe:"1h"}` (case-only different) -> `symbol_not_found` again. (J1-09 shows `market_quote`, `market_candles` and `market_snapshot` all accept `xauusdm`.)
3. `chart_snapshot {symbol:"XAUUSDm", timeframe:"H1"}` -> `{"ok": false, "code": "unsupported_timeframe", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", ...}, "runtime_notice": [{"kind": "tool_guardrail", "source": "lonora_runtime", "message": "chart_snapshot has failed 3 times in this run. Diagnose the latest error before another attempt: correct the arguments, use a narrower request or a genuinely different source, or report the blocker."}]}`.
4. `tool_call chart_open {symbol:"XAUUSD", timeframe:"1h"}` -> **`{"ok": true, "chart": {"id": "<chart>", "version": 1, "payload": {"account_id": "<conn>", "symbol": "XAUUSD", "timeframe": "1h", ...}}, "command": {"status": "applied", ...}, "requires_scene_inspection": true, "scene_summary": {"available": false, ...}}`** (the chart is created for a symbol that does not exist).
5. `chart_inspect {chart_id}` -> `{"ok": true, ... "state": {..., "scene_status": "failed", ..., "error_code": "symbol_not_found"}, ... "code": "symbol_not_found", "scene": null}` (an ok result that carries a failure code inside).
6. `chart_snapshot {chart_id}` -> `symbol_not_found`. 7. `chart_list` -> `{"ok": true, "charts": [{"chart_id": "<chart>", ..., "symbol": "XAUUSD", "timeframe": "1h", "status": "failed", ...}]}`.

Server log line: `chart_refresh_failed code=symbol_not_found error_type=NotFoundException message=Symbol not found`.

**What the owner sees**: whatever the model writes; a failed chart row now exists in his thread (UNSURE how the app renders a `failed` chart; I did not open the UI).

**Root cause**
- `chart_snapshot` passes the model's symbol straight to the provider (`packages/tools/src/lonora_tools/chart_snapshot.py:178`, and uses it for the image and file name at `:181, :188, :196`); unlike `market_candles` it never calls `canonical_broker_symbol`. So a case-only difference is refused here, although the prompt says "Letter case alone is not a different symbol" (`trading_context.md:5`, dead text, see J1-01) and the market tools accept it. `chart_indicator` does canonicalise (`packages/tools/src/lonora_tools/chart_indicator.py:20`).
- The candles stage reports `symbol_not_found` only because the fake exception text contains "symbol" and "not found" (`metaapi.py:59-60`); see J1-07 for the other branch.
- `chart_open` validates the shape of the state, not the symbol: `chart.py:11-38` builds `ChartState` and calls `create_chart`; the symbol is first tried by the background refresh, which logs `chart_refresh_failed` and stores `scene_status: failed` (`packages/charts/src/lonora_charts/runtime.py:100-108`).
- `H1` is refused by `validate_timeframe` (`packages/core/src/lonora_core/chart_controller.py:29-32`, `raise LonoraError("unsupported_timeframe")`); the error names no valid values, and `classify` files it as `terminal_domain_failure` / `alternate_route` (`environment.py:36-37`) instead of "fix the argument". The rule "Candles use timeframes such as 15m or 1h, not M15 or H1" exists only in the dead `trading_context.md:5`.
**Class**: bug (ok result for a bad symbol; case handling differs per tool) and recoverable-not-led.

---

## J1-04: «نبهني إذا الذهب طلع فوق 4100» (a watch on a symbol the account does not have)

**Rerun**: `.../scripts/j1_run.sh J1-04` (`.../runs/J1-04.txt`).
**SCRIPTED turn**: `watch_create {kind:"price", account_id:"<conn>", symbol:"XAUUSD", condition:"above", level:"4100", prompt:"Gold crossed above 4100: tell the owner."}` then a placeholder final reply. Then REAL calls: one `check_watches()` poll (`lonora_market.watchers`), a second poll with `next_check` forced into the past, and a second owner message «هل التنبيه شغال؟» with SCRIPTED `watch_list` through the bridge.

RUNTIME results:
- `watch_create` -> `{"ok": true, "id": "<watch>", ... "payload": {... "kind": "price", ..., "symbol": "XAUUSD", "condition": "above", "level": "4100", ..., "enabled": true, ...}, "state": {}, "version": 1, ...}`. No symbol check, no warning.
- After the first poll: `triggered: 0`; the stored watch is `enabled: true` with `state.health = {"state": "unavailable", "reason_code": "broker_account_not_found", ..., "symbol": "XAUUSD", "resource": "watch"}`, `evaluation_status: "suspended_health"`, `code: "broker_account_not_found"`.
- Events and owner-attention classification (REAL `classify_attention`): `market_watches.created` -> `{"importance": "silent", "code": "internal_update", ...}`; `watch.suspended_health` -> `{"importance": "silent", "code": "internal_update", ...}`.
- After the second poll: no further `watch.*` event (still one `watch.suspended_health`, cursor 916). Newest runs of the agent: none started by the watch (no wake).
- `watch_list` -> the same watch with `"health": {"state": "unavailable", "reason_code": "broker_account_not_found", ...}` and `"evaluation_status": "suspended_health"`.
- What the NEXT run's first request says about the watch before any tool call: `live_agent_state.watches = [{"id": "<watch>", "kind": "price", ..., "symbol": "XAUUSD", "condition": "above", "level": "4100", ..., "lifecycle": "pending"}]`, `live_agent_state.health = []`; the request text contains neither `suspended_health` nor `broker_account_not_found`.

**Root cause**
- `watch_create` stores whatever symbol is given (`packages/tools/src/lonora_tools/market_watch.py:90-135`; no catalog lookup, no `canonical_broker_symbol`).
- The first evaluation turns the broker's 404 into `broker_account_not_found` (`metaapi.py:57-58`) and the watch into `suspended_health` (`packages/market/src/lonora_market/watch_health.py:23`).
- `classify_attention` has no branch for `watch.suspended_health`: it falls through to the default `importance="silent", code="internal_update"` (`packages/core/src/lonora_core/attention.py:57-61` only sets the transition id).
- The agent's own status summary drops health: `watch_summary` copies kind/symbol/condition/level and `lifecycle` only (`packages/db/src/lonora_db/agent_state.py:36-53`).
So the owner is told "I will alert you" by a model that was handed `ok: true`, while the watch can never fire and nobody is woken. (This is the symbol-error face of the watch problems in production-trace.md; the lifecycle bugs themselves belong to the watch session.)
**Class**: bug / dead-end (silent).

---

## J1-05: «حلل لي الذهب الآن وارسم الدعم والمقاومة» when the data is old

**Rerun**: `.../scripts/j1_run.sh J1-05` (`.../runs/J1-05.txt`).
**Fixture**: the FAKE SDK returns a last price and bars that are 50 hours old (`age=timedelta(hours=50)`, i.e. 2026-11-09 13:22 UTC in this run). This is a stand-in for any stale/closed market; it is not a claim about real weekend data.
**SCRIPTED turns** (symbol is correct here, `XAUUSDm`): `market_quote` + `market_candles 1h limit 3`; `tool_call market_structure` twice; `market_snapshot timeframes ["1h"]`.

RUNTIME results:
- `market_quote` -> `{"ok": true, "symbol": "XAUUSDm", "bid": "4049.73", "ask": "4049.97", "observed_at": "2026-11-09T13:22:58.252381Z", "source": "metaapi", ...}`: ok, two days old, no freshness field.
- `market_candles` -> `{"ok": true, "candles": [{"symbol": "XAUUSDm", "timeframe": "1h", "time": "2026-11-09T10:22:00Z", ...}, ...]}`: ok, no freshness field.
- `market_structure` -> `{"ok": false, "code": "market_candles_stale", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`; the repeat adds `"runtime_notice": [{"kind": "tool_guardrail", ..., "message": "market_structure has failed 2 times with identical arguments. Inspect the error and change strategy instead of retrying it unchanged."}]`.
- `market_snapshot` -> `{"ok": true, "methodology": "closed_bar_market_snapshot_v1", ..., "data_freshness": "stale", "quote": {"available": true, "freshness": "stale", "reason": "market_quote_stale", ..., "age_seconds": 180000.6}, "reference_price": "4049.85", "reference_basis": "stale_quote_mid", ...}`: honest, with the full analysis.

**Root cause**
- Four tools, four stale behaviours: `market_quote` and `market_candles` return old data as plain success (`market.py:56-72` returns the provider objects dumped); `market_structure` and `chart`-style reads refuse with a health code (`health.py:220-222` `require_healthy`; `market_analysis.py:321-322`); `market_snapshot` returns data with `data_freshness`. A model that reads only `ok: true` can present a two-day-old price as current.
- `classify` knows `quote_stale`, `market_data_stale`, `market_evidence_stale`, `stale_evidence` as "stale_state / refresh_evidence" (`environment.py:48-49`), but the codes the code really emits are `market_candles_stale` (`health.py:203`, `"market_candles_" + reason`) and `market_quote_stale` (`packages/trading/src/lonora_trading/preflight.py:84`). They do not match, so they fall to the default `terminal_domain_failure` / `alternate_route` (`environment.py:36-37`), which says nothing about "wait for the market or use the snapshot".
**Class**: bug (inconsistent freshness; wrong recovery class) and recoverable-not-led. A closed market itself is not an owner problem; the correct owner-facing answer ("the market is closed, here is the last close") needs no question.

---

## J1-06: «كم سعر الذهب على حساب 00000000؟» (broker login used as account_id; missing argument)

**Rerun**: `.../scripts/j1_run.sh J1-06` (`.../runs/J1-06.txt`).
**SCRIPTED turn**: `market_quote {account_id:"00000000", symbol:"XAUUSDm"}`, `market_snapshot {...}`, `tool_call market_symbols {account_id:"00000000"}`, `market_quote {symbol:"XAUUSDm"}` (no account).
RUNTIME results:
- the first three -> `{"ok": false, "code": "broker_sessions_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", ...}}`.
- missing account -> `{"ok": false, "code": "tool_arguments_invalid", "issues": [{"path": ["account_id"], "type": "missing"}], "retryable": true, "recovery": {"category": "invalid_tool_arguments", "next_action": "inspect_schema_and_repair", ...}}`.

**Root cause**: a connection id that does not exist makes the repository raise `<kind>_not_found` where the kind is the table name `broker_sessions` (`packages/db/src/lonora_db/transactions.py:92`; the same code is raised by `packages/market/src/lonora_market/runtime.py:67`). The owner's vocabulary is "حساب"; `broker_sessions_not_found` is an internal table name. The only hint to the model is the tool description (`market.py:17`, "Internal connection_id returned by list_accounts; not the external broker account ID."). Nothing in the result says "call list_accounts". Note the argument-error result is the better contract: it names the missing field and says `retryable`.
**Class**: technical-question risk (code leaks) / recoverable-not-led.

---

## J1-07: «أعطني شموع الذهب» when the provider's 404 text lacks the word "symbol"

**Rerun**: `.../scripts/j1_run.sh J1-07` (`.../runs/J1-07.txt`). The FAKE SDK raises `NotFoundException("Not found")` on the candles stage only (assumption, see section 0: real MetaApi wording UNSURE).
**SCRIPTED turn**: `market_candles XAUUSD 15m`, `chart_snapshot XAUUSD 15m`, `market_candles XAUUSDm M15`.
RUNTIME results: `market_candles` and `chart_snapshot` -> `{"ok": false, "code": "broker_candles_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", ...}}`; `M15` -> `{"ok": false, "code": "unsupported_timeframe", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", ...}}`.
Log: `broker_candles_failed code=broker_candles_not_found type=NotFoundException message=Not found`.

**Root cause**: on the candles stage a 404 becomes `symbol_not_found` only if the provider's text contains both "symbol" and a "missing" word; otherwise `broker_candles_not_found` (`metaapi.py:59-61`). The same wrong-symbol request therefore yields three different codes across tools (`broker_account_not_found`, `symbol_not_found`, `broker_candles_not_found`), none with candidates. `unsupported_timeframe`: see J1-03 (`chart_controller.py:29-32`, `environment.py:36-37`).
**Class**: recoverable-not-led / bug (the third code name depends on provider wording).

---

## J1-08: «كم سعر الذهب الآن؟» with no broker account connected

**Rerun**: `.../scripts/j1_run.sh J1-08` (`.../runs/J1-08.txt`); no connection is created.
**SCRIPTED turns**: `list_accounts`; then `market_quote {account_id:"default", symbol:"XAUUSD"}`, `market_sessions {}`, `tool_call web_search {query:"gold price XAUUSD now"}`.
RUNTIME results:
- `list_accounts` -> `{"ok": true, "accounts": [], "guidance": "Use connection_id as account_id in account, market and trading tools. Present accounts to the user using broker_identity broker/login/server, never transport IDs as account numbers. ..."}` (guidance is about using ids; nothing for the empty case).
- `market_quote` with `"default"` -> `broker_sessions_not_found` (as J1-06).
- `market_sessions {}` -> ok (FX session clock, `"fx_market": {"state": "open", ...}`): the one thing that works with no account.
- `web_search` -> `{"ok": false, "code": "research_provider_not_configured", "recovery": {"category": "not_configured", "next_action": "inspect_authorized_alternative", ...}}` (fixture has no research provider; production's web_search was available, so this row is fixture-specific).

**Root cause / classification**: needing a broker account to read the broker's gold price is real and cannot be worked around; the failure is that the empty-list result gives the model no instruction for the owner ("connect an account in settings") and the model may probe with a made-up `account_id` ("default") and get an internal table name back (`transactions.py:92`).
**Class**: owner-needed (a connection) but not led.

---

## J1-09: control, which tools tolerate a different spelling

**Rerun**: `.../scripts/j1_run.sh J1-09` (`.../runs/J1-09.txt`). One SCRIPTED turn, seven calls, correct account, catalog as above.

| call | RUNTIME result |
|---|---|
| `market_quote symbol="xauusdm"` | ok, `symbol: "XAUUSDm"` (case folded, `symbols.py:11-14`) |
| `market_candles symbol="xauusdm" 1h` | ok, candles carry `XAUUSDm` |
| `market_snapshot symbol="xauusdm"` | ok, `data_freshness: "healthy"` |
| `chart_snapshot symbol="xauusdm" 1h` | `symbol_not_found` (no canonicalisation, `chart_snapshot.py:178`) |
| `chart_snapshot symbol="XAUUSDm" 1h` | ok, PNG artifact |
| `market_quote symbol="XAUUSD.m"` | `broker_account_not_found` |
| `market_quote symbol="XAUUSD "` (trailing space) | `broker_account_not_found` |

So the system already knows how to fold case for reads, but only for three of four read paths, and anything else (a dot, a space, a missing suffix, an Arabic word) goes to the broker verbatim.
**Class**: bug.

---

## J1-10: what `tool_environment` search finds for the words that matter

**Rerun**: the J1-10 command in section 0 (REAL `load_tools()` registry of 126 permitted tools and REAL `search_definitions`, the same call as `packages/tools/src/lonora_tools/registry.py:362-366`; the availability filter at `registry.py:368` is not applied, so a configured-off tool could still appear here). Raw output, `.../runs/J1-10.txt`:

```
'symbols'                    -> ['market_instruments', 'market_symbols', 'market_relationship_record', 'market_instrument', 'agent_create', 'trade_restriction_create', 'owner_action_propose'] (n=7)
'symbol'                     -> ['market_instrument', 'market_candles', 'market_quote', 'chart_set_symbol', 'trade_record_history', 'market_symbols', 'chart_indicator', 'market_sessions'] ... (n=12)
'gold symbol'                -> [] (n=0)
'find symbol name'           -> ['trade_record_history', 'search_internal'] (n=2)
'gold'                       -> [] (n=0)
'XAUUSD'                     -> [] (n=0)
'broker symbol names'        -> ['market_symbols', 'list_agents', 'model_request', 'search_internal'] (n=4)
'الذهب'                      -> [] (n=0)
'رمز الذهب'                  -> [] (n=0)
'search symbol suffix'       -> [] (n=0)
'market symbols'             -> ['market_instruments', 'market_symbols', 'market_instrument', ...] (n=7)
'market_symbols'             -> ['market_symbols', 'market_instruments', ...] (n=7)
'delete watch'               -> ['workspace_update', 'chart_annotate'] (n=2)
'cancel watch'               -> ['watch_cancel', 'task_control', 'goal_control', 'trade_execute'] (n=4)
'stop watch'                 -> ['watch_cancel', 'market_position_size', ...] (n=6)
'remove watch'               -> ['chart_remove_indicator', 'skill_package_control', ...] (n=5)
'حذف المتابعات'              -> [] (n=0)
```

**Root cause**: the gate is the query's rarest token, even if its frequency is zero (`packages/tools/src/lonora_tools/tool_discovery.py:62`: `gate = min(query_tokens, key=lambda token: (frequencies[token], token))`), and every non-exact tool whose text lacks the gate is skipped (`tool_discovery.py:69-73`). One word the catalog never uses ("gold", "XAUUSD", "suffix", any Arabic word) empties the whole result. The index is built from English tool names, descriptions and parameter names only (`tool_discovery.py:52-57`). `market_symbols` is found only by a query that already contains its words.
**Class**: recoverable-not-led. (The `watch` rows show the same mechanism that emptied production's query «watch cancel task routines goals»; `delete watch` does not return `watch_cancel` at all.)

---

## Mechanism index (every path found in this area)

| # | mechanism | where | effect on the owner | class |
|---|---|---|---|---|
| M1 | symbol match is exact or case-only | `packages/tools/src/lonora_tools/symbols.py:9-15` | `XAUUSD` is not `XAUUSDm` | recoverable-not-led |
| M2 | a failed catalog match is swallowed for non-strict tools and the raw symbol is sent to the broker | `symbols.py:32-35`, `market.py:47,58,65` | wrong code downstream | bug |
| M3 | every non-candles 404 becomes `broker_account_not_found` | `metaapi.py:52,57-58` | unknown symbol reported as unknown account; contradicts `lonora.md:239` | bug |
| M4 | candles 404 wording decides `symbol_not_found` vs `broker_candles_not_found` | `metaapi.py:59-61` | a third code for the same cause | bug |
| M5 | strict tools raise `symbol_not_found` with nothing else | `market.py:78`, `market_analysis.py:140,215,305`, `symbols.py:15` | model cannot correct it | recoverable-not-led |
| M6 | tool error result has only `code` (+ `issues`) | `tool_dispatch.py:113-117` | no candidates, no hint | recoverable-not-led |
| M7 | all `*_not_found` -> `not_found` / `inspect_existing_state` | `environment.py:80-81` | the same advice for a missing account, symbol, run, order | recoverable-not-led |
| M8 | stale codes not in the stale set; `unsupported_timeframe` filed as terminal | `environment.py:36-37,48-49`, `health.py:203`, `preflight.py:84`, `chart_controller.py:29-32` | wrong recovery class | bug |
| M9 | `market_symbols` is not eager, becomes native only after a successful call | `market.py:98-105`, `tool_exposure.py:1-9,151-181`, `registry.py:267` | the search tool is invisible to the model; the descriptions point to it (`market.py:108`) | recoverable-not-led |
| M10 | market policy chapter only after the first market call | `system_policy.py:1-5,134-140` | first market guess is made without it | recoverable-not-led |
| M11 | `trading_context.md` never loaded | no loader reference (grep) | the best gold/suffix/timeframe guidance is dead text | recoverable-not-led |
| M12 | suffix-aware matcher exists but only agent creation uses it | `agents.py:72-91,94-124,257,265` | design already exists, not applied to reads | recoverable-not-led |
| M13 | no alias layer owner word -> broker symbol | `instrument_names.py:36-54` is symbol -> name only | «الذهب» reaches the broker verbatim | recoverable-not-led |
| M14 | fixed-market auto-fill needs a bound account and symbol | `market_binding.py:89-90` | Lonora's personal agent has neither | recoverable-not-led |
| M15 | tool search gate on a zero-frequency token; English-only index | `tool_discovery.py:62,69-73,52-57` | searching "gold"/Arabic finds nothing | recoverable-not-led |
| M16 | `chart_snapshot` does not canonicalise the symbol; `chart_open` accepts any symbol | `chart_snapshot.py:178`, `chart.py:11-38`, `runtime.py:100-108` | failed chart rows, case refusal | bug |
| M17 | `watch_create` accepts any symbol; suspended-health is silent; status line omits health | `market_watch.py:90-135`, `attention.py:57-61`, `agent_state.py:36-53` | a dead watch that nobody reports | bug / dead-end |
| M18 | `market_quote`/`market_candles` return stale data as plain ok | `market.py:56-72` | old price can be called current | bug |
| M19 | missing connection -> `broker_sessions_not_found` (table name) | `transactions.py:92`, `runtime.py:67` | internal word in results | technical-question |
| M20 | no reply check on registered codes, backticks, `**`, or "if you want" offers | `model_runtime.py:225-238` is the only rewrite; `stop_gates.py:99-104` | J1-01a reply committed unchanged | leak |
| M21 | raw error code in the public stream payload | `tool.completed` event in `.../runs/J1-01.txt` | any UI that shows tool chips shows the code | leak |

### Refusals that exist FOR the money-safety rules (needed for safety; do not relax)

- Exactness of the symbol on money-moving calls. `trade_execute` canonicalises the symbol before it builds the request (`packages/tools/src/lonora_tools/trade.py:632-634`), and `lonora.md:224` ("Never strip suffixes, substitute an exchange feed or assume one broker's instrument exists at another") protects an order from landing on a different instrument. Resolving `XAUUSD` -> `XAUUSDm` for READS is harmless; for an order the resolved symbol must be shown to the owner or approved in the card, and an ambiguous alias must remain a question (`lonora.md:225`).
- Restriction symbols: `restriction_symbol` records a symbol only in the broker's spelling and fails on an unlisted one (`symbols.py:38-56`): needed for safety (a restriction on a name that never matches would not restrict).
- Fixed-market agents keep mutations on their bound account/symbol (`market_binding.py:31-36`): needed for safety.
- `broker_account_not_found` for a truly unknown ACCOUNT, `broker_disabled`, and the credentials/rate-limit codes (`metaapi.py:62-65`) are honest refusals; the defect is only that an unknown SYMBOL shares the account code.

## UNSURE (not confirmed)

1. In J1-01b the SCRIPTED model called `market_symbols` by its own name although it is not in the native list, and the runtime executed it. A real provider normally cannot emit a tool name that was not offered, so the supported route for a real model is `tool_call` (also shown) or a `tool_environment` lookup. I did not read the dispatch path that allows the direct call.
2. The real MetaApi error text for an unknown symbol on `get_symbol_price`, `get_symbol_specification` and `get_historical_candles`. The stages other than candles do not depend on it (`metaapi.py:57`); the candles stage does (J1-03, J1-07). Production shows `symbol_not_found` only for `market_snapshot`, which fails before any broker call (`symbols.py:15`), so production does not settle the candles wording.
3. The five-second duration of production's `market_instrument` call (see reconciliation above).
4. How the web and mobile apps render a failed chart row (J1-03) and the `tool.completed` code (M21). I read only the stream payloads.
5. Whether `resolve_instrument` is used from outside `*.py` code (grep found no caller in any Python file); I treat it as dead.

## Citation check

Every `path:line` above was read with `grep -n`/`sed -n` or the Read tool against HEAD `9f5b1da`, and each line was re-opened before this file was finished: `symbols.py:6-15,32-35,38-56`; `market.py:17,47,58,65,78,98-105,108,112,128,136`; `market_analysis.py:32,136-140,203-231,305`; `chart_snapshot.py:178,181`; `chart.py:11-38`; `chart_indicator.py:20`; `metaapi.py:39,52,57-61,422-435,474,701,725`; `environment.py:35-37,48-49,80-81`; `tool_dispatch.py:113-117`; `tool_discovery.py:52-57,62,69-73`; `registry.py:267,348,362-368`; `tool_exposure.py:1-9,151-181`; `system_policy.py:1-5,134-140`; `lonora.md:60,212,224,225,239`; `agents.py:72-124,257,265`; `instrument_names.py:21,36-54`; `market_binding.py:31-36,89-90`; `market_watch.py:90-135`; `attention.py:57-61`; `watch_health.py:23`; `agent_state.py:36-53`; `health.py:203,220-222`; `preflight.py:84`; `chart_controller.py:29-32`; `transactions.py:92`; `runtime.py:67`; `charts/runtime.py:100-108`; `model_runtime.py:225-238`; `stop_gates.py:99-104`; `trade.py:632-634`.
