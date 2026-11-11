# Conversation group A ([9]–[14]): symbol resolution and error handling

Scope: owner brief section 2 group A, and root causes 1–5 of section 3.
Code read at `main` HEAD `9f5b1da`. All paths are relative to the repository root.
Repository was not modified (`git status --short` is empty after the runs).

How the evidence was produced:

- Driver: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/conv_a_symbols.py`
  (database 9, emptied first with `scripts/reset_db9.sh`). Raw output:
  `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/conv-A-symbols.out`;
  every model request (messages and tool names) per run:
  `runs/conv-A-run9-requests.json`, `runs/conv-A-run11-requests.json`, `runs/conv-A-run13-requests.json`,
  `runs/conv-A-recovery-requests.json` in the same directory.
- Driver: `scripts/conv_a_discovery.py`, output `runs/conv-A-discovery.out` (registry search only).
- What is real in the runs: the Personal Agent row (`role = personal`), the API message route, the context builder,
  `model_turn`, the tool loop, the registry, `dispatch_call`, `environment.observe`, and a real `MetaApiBroker`
  object running its own `symbols`, `instrument`, `quote`, `candles`, `read_rpc`, `diagnose`, `provider_error`.
- What is fake, and labelled so in the output:
  - **SCRIPTED** model turns: which tools the model "chose" and the reply text (the owner's [10], [12], [14] texts
    were fed back as the scripted replies, to see whether anything on `main` changes or blocks them).
  - **FAKE SDK**: the MetaApi RPC connection behind the broker object. Catalog: `BTCUSDm, EURUSDm, USOILm,
    XAGUSDm, XAUUSDm`. An unknown symbol raises the SDK's own `NotFoundException` (HTTP status 404), which is what
    the SDK builds for a server `NotFoundError` (`.venv/lib/python3.12/site-packages/metaapi_cloud_sdk/clients/metaapi/metaapi_websocket_client.py:1758-1759`).
    The exception message text is my assumption; section 2.3 says where the text matters and where it does not.
  - The stored connection row says `provider: simulation` (shortcut to avoid a stored secret); the adapter object
    the tools reach is the `MetaApiBroker`.

No production trace was available. Every statement about what the production model actually called is marked
`TRACE MUST CONFIRM`.

---

## 0. Summary

| Message | Problem | On `main` (`9f5b1da`) |
| --- | --- | --- |
| [10] | Two raw codes, account identity, an offer instead of a search | **FAILS** |
| [12] | «ضع حرف m» answered with a clarification request and an offer | **FAILS** |
| [13] | Owner had to type the symbol himself | **FAILS** (consequence of [10] and [12]) |
| [14] | Contract specifications instead of the answer to [9], then another offer | **FAILS** |

Nothing that decides group A changed between the PR #42 merge (`aa50e8e`) and `9f5b1da`:
`git diff --name-only aa50e8e 9f5b1da` is empty for `packages/tools/src/lonora_tools/symbols.py`, `market.py`,
`market_analysis.py`, `account.py`, `tool_discovery.py`, `registry.py`, `packages/adapters/src/lonora_adapters/brokers/`,
`packages/market/src/lonora_market/instruments.py`, `packages/agent-runtime/src/lonora_agent/tool_dispatch.py`,
`environment.py`, `context/environment.py`, `skills/system_policy.py`, `packages/agent-runtime/resources/bootstrap/`,
`packages/contracts/src/lonora_contracts/tool_environment.py` and `packages/core/src/lonora_core/public_reply.py`.
PR #42 itself added only the uncertain-financial-outcome line (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:22`
lists `trade_execute`, `trade_close_positions`, `goal_step_execute`); it reads no market read results and no reply
wording. So group A behaves the same whichever of the two builds production served.

Root causes 1–5: all five **confirmed**, with two refinements (cause 2 is dead code; cause 5 adds one more
generic field). Details in section 5.

---

## 1. [9] «طيب شو وضع الذهب» → [10]

### 1.1 Tools exposed to the Personal Agent

Measured on model turn 1 of the run (`runs/conv-A-symbols.out`, block `run9: native tools offered on model turn 1`),
22 native tools:

`peer_send, memory_read, memory_write, session_search, skills_list, skill_view, market_instrument, market_quote,
market_candles, market_snapshot, market_sessions, watch_create, market_decision_record, market_decision_history,
chart_snapshot, list_accounts, account_read, trade_execute, wait_for_input, agent_inspect, tool_environment, tool_call`

Profiles recorded in the run checkpoint: `["core", "market", "coordination"]`
(`packages/agent-runtime/src/lonora_agent/tool_exposure.py:31-39`).

- `market_symbols` is **not native**. Its definition has no `eager=` argument
  (`packages/tools/src/lonora_tools/market.py:97-105`), while `market_instrument`, `market_quote`, `market_candles`
  have `eager=eager_for("market")` (`packages/tools/src/lonora_tools/market.py:112`, `:128`, `:136`) and
  `market_snapshot` too (`packages/tools/src/lonora_tools/market_analysis.py:370`).
- `market_symbols` is reachable in two ways only: through the bridge `tool_call`, or after discovery with
  `tool_environment`. Its name appears once in the capability inventory system message, in the line
  `market: economic_calendar_read, market_candles, …, market_symbols, watch_cancel, …`
  (`packages/tools/src/lonora_tools/registry.py:406-473`; preface text at `registry.py:425-431`:
  `Call any other capability below with tool_call, using its exact name and arguments`).
- Its description, which the model does not see unless it runs discovery, is the one that states the rule:
  `Discover exact broker symbol names … Use before guessing broker symbols or aliases; suffixes matter.`
  (`packages/tools/src/lonora_tools/market.py:99-101`).

### 1.2 Why `XAUUSD`: where the model gets a symbol

The first request of the run contains no symbol at all. String search over every message of model turn 1
(`runs/conv-A-symbols.out`, block `run9: what the first request contained`):

```
contains 'XAUUSDm' (catalog spelling): false
contains 'XAUUSD': false
contains 'market_symbols' (name): true
contains 'Use market_symbols to discover' (market chapter): false
contains account server 'Exness-MT5Trial16': false
```

- The account's symbol catalog is **not in context**. No context section lists symbols; the Personal Agent has no
  bound symbol, and its scope block only says `Read authorized owner accounts and exact broker symbols relevant to
  the current request.` (`packages/db/src/lonora_db/agent_binding.py:149-159`).
- So `XAUUSD` comes from the model's own general knowledge of the common gold ticker. Nothing in the runtime
  supplies it, and nothing maps «الذهب» to a symbol.
- The line that tells the model to discover first, `Use market_symbols to discover exact symbols before guessing
  aliases.` (`packages/agent-runtime/resources/system/lonora.md:212`), is in the `market` domain chapter. A chapter
  is added only after a tool of that chapter was already called in the last 16 messages
  (`packages/agent-runtime/src/lonora_agent/skills/system_policy.py:134-138`). It is absent on turn 1 and present
  from the turn after the first market call (measured: block `run9: model turn 3 (after the failures) contains`
  → both `Use market_symbols to discover` and `A truly unknown symbol is not a generic connection failure` are
  `true`; the latter is `lonora.md:239`).
- One prompt file teaches the guess directly: `Owner: "Alert me if gold rises above 2400". First call market_quote
  for XAUUSD, XAGUSD and EURUSD in one message` (`packages/agent-runtime/resources/prompts/genui_v2.md:17`). It is
  loaded only when the environment variable `LONORA_GENUI_V2` is on
  (`packages/agent-runtime/src/lonora_agent/skills/visual_policy.py:21-22`, `:77-78`). It was off in my run.
  TRACE MUST CONFIRM: the value of `LONORA_GENUI_V2` in production during the conversation.

### 1.3 The two codes: exact failing paths

Reproduced with one SCRIPTED model turn that called four native read tools with `symbol: "XAUUSD"`.
Adapter log lines from the run (first lines of `runs/conv-A-symbols.out`):

```
broker_rpc_failed code=broker_account_not_found type=NotFoundException message=Specification for symbol XAUUSD not found
broker_rpc_failed code=broker_account_not_found type=NotFoundException message=Price for symbol XAUUSD not found
broker_candles_failed code=symbol_not_found type=NotFoundException message=Symbol XAUUSD not found
```

| Tool called with `XAUUSD` | Code returned | Path |
| --- | --- | --- |
| `market_snapshot` | `symbol_not_found` | `snapshot` calls `canonical_broker_symbol(broker, params.symbol, require_exists=True)` (`packages/tools/src/lonora_tools/market_analysis.py:140`) → `catalog_symbol` finds no exact and no case-only match and raises (`packages/tools/src/lonora_tools/symbols.py:9-15`) → re-raised because `require_exists` (`symbols.py:32-34`). The broker is not asked about the symbol at all; only `broker.symbols()` is read (`symbols.py:21`). |
| `market_instrument` | `broker_account_not_found` | `instrument` calls `canonical_broker_symbol` **without** `require_exists` (`packages/tools/src/lonora_tools/market.py:47`), so the miss is swallowed and `XAUUSD` is passed on (`symbols.py:32-35`) → `broker.instrument("XAUUSD")` (`market.py:48`) → `read_rpc("get_symbol_specification", symbol)` (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:465-469`) → SDK 404 → `raise self.diagnose(error, "rpc")` (`metaapi.py:434`) → `provider_error(error, "rpc")`: `if stage != "candles" or "account" in message and missing: return LonoraError("broker_account_not_found", 404)` (`metaapi.py:57-58`). |
| `market_quote` | `broker_account_not_found` | Same swallow (`market.py:58`) → `broker.quote` → `read_rpc("get_symbol_price", symbol)` (`metaapi.py:699`) → same `diagnose(error, "rpc")` (`metaapi.py:434`) → `metaapi.py:57-58`. |
| `market_candles` | `symbol_not_found` (with my fake message) | Same swallow (`market.py:65`) → `account.get_historical_candles` (`metaapi.py:711-713`) → `diagnose(error, "candles")` (`metaapi.py:725`) → because the stage is `candles`, the message is read: `if "symbol" in message and missing: return LonoraError("symbol_not_found", 404)` (`metaapi.py:59-60`), else `broker_candles_not_found` (`metaapi.py:61`). |

Reading [10] against this table: «محاولة الذهب على XAUUSD رجعت symbol_not_found» fits `market_snapshot` (or
`market_candles`), and «محاولة تفاصيل العقد رجعت broker_account_not_found» fits `market_instrument` exactly
("contract details" is that tool's subject: `Read specifications for ONE exact broker symbol`, `market.py:108`).
The account was fine: the same broker object answered `symbols()` and the account read in the same run.

TRACE MUST CONFIRM: the tool names and arguments of the run that produced [10] (expected: `list_accounts` or
`account_read`, then `market_snapshot` and/or `market_candles` with `XAUUSD`, and `market_instrument` with `XAUUSD`),
and that the stored `tool.completed` events carry `symbol_not_found` and `broker_account_not_found`.
UNSURE: the exact message text MetaApi sends for an unknown symbol. It does not matter for `market_instrument`
and `market_quote` (any 404 outside the `candles` stage becomes `broker_account_not_found`); it matters only for
`market_candles` (`metaapi.py:59-61`).

### 1.4 The literal tool results the model saw

From `runs/conv-A-symbols.out` (identical text in `runs/conv-A-run9-requests.json`, turn 3, role `tool`):

```json
{"ok": false, "code": "symbol_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}
```

```json
{"ok": false, "code": "broker_account_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}
```

- No symbol echoed back, no candidates, no hint, no tool name to call next. The two results differ only in `code`.
- `{"ok": False, "code": error.code}` is built at `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:113`;
  only argument-validation errors get more (`issues`, `retryable`, `tool_dispatch.py:114-116`).
- `recovery` is added afterwards by `observe` (`packages/agent-runtime/src/lonora_agent/environment.py:204-210`,
  called from `packages/agent-runtime/src/lonora_agent/tool_block.py:300`).

### 1.5 What `environment.classify` did with the errors

- Both codes end in `_not_found`, so both fall into the same branch:
  `elif code.endswith("_not_found"): category, action = "not_found", "inspect_existing_state"`
  (`packages/agent-runtime/src/lonora_agent/environment.py:80-81`).
- `safe_to_retry` is `bool(tool and tool.read_only and code in TRANSIENT_READ_CODES)` (`environment.py:92`);
  neither code is in `TRANSIENT_READ_CODES` (`packages/core/src/lonora_core/runtime_failure.py:10-21`), so `false`.
- The loop retries by itself only when `safe_to_retry` is true (`packages/agent-runtime/src/lonora_agent/tool_block.py:309`).
  For these two codes the runtime does nothing further: no automatic catalog read, no second attempt. The next
  step is left entirely to the model.
- `schema_tool: "tool_environment"` is a constant default of the contract
  (`packages/contracts/src/lonora_contracts/tool_environment.py:31`), not a per-error hint.
- The run's environment record kept one failure per call (`failures: 1`), so nothing was blocked either
  (blocking starts at 3 failures of the same call, `environment.py:129`).

So a wrong symbol and a (wrongly reported) missing account are indistinguishable to the model, and neither result
names `market_symbols`.

### 1.6 Why the broker name, account number and server appeared

- `list_accounts` returns them and tells the model to show them. Result in the run:
  `"broker_identity": {"broker": "Exness Technologies Ltd", "login": "00000000", "server": "Exness-MT5Trial16", …}`
  with the guidance string `Present accounts to the user using broker_identity broker/login/server, never transport
  IDs as account numbers.` (`packages/tools/src/lonora_tools/account.py:54-56`, `:63-65`). The identity is cached on
  the connection row by `BrokerManager.account` (`packages/adapters/src/lonora_adapters/brokers/base.py:67-84`).
- `list_accounts` is native for the Personal Agent (`account.py:126`) and is the only way to get the
  `account_id` every market tool requires (`packages/tools/src/lonora_tools/market.py:15-18`), so it is called before
  any gold read. `account_read` returns the same identity fields.
- The mandatory policy supports showing it: `Broker ticket numbers, exact symbols, prices, account login when
  relevant, and factual financial outcomes are useful owner information.`
  (`packages/agent-runtime/resources/system/lonora.md:48`).
- With a result that says the *account* was not found, listing the connected account is the model trying to
  reconcile `broker_account_not_found` with an account it had just read. The false code (root cause 3) is what
  made the identity "relevant".

TRACE MUST CONFIRM: that the [10] run called `list_accounts` (or `account_read`) and that the identity in the
reply matches that result.

### 1.7 Why it offered instead of searching

Facts from code and runs, in order of weight:

1. **The search tool is discovery-only** (section 1.1). Using it costs an extra indirection (`tool_call`) that the
   model must think of from a bare name in a list.
2. **The error result does not point to it** (sections 1.4, 1.5).
3. **Discovery fails for natural queries.** `scripts/conv_a_discovery.py` over the live registry
   (`runs/conv-A-discovery.out`):

   | `tool_environment` query | Result |
   | --- | --- |
   | `gold symbol name` | 0 tools |
   | `gold`, `find gold`, `XAUUSD`, `الذهب`, `رمز الذهب` | 0 tools |
   | `symbol search` | 7 tools: `session_search, web_search, search_internal, memory_read, list_agents, web_browse, owner_action_propose` — `market_symbols` absent |
   | `search symbol name` | 7 tools, `market_symbols` absent |
   | `symbol` | `market_symbols` is 6th of 12 |
   | `symbols`, `broker symbols`, `market symbols`, `list symbols` | `market_symbols` is 2nd |
   | `discover symbol` | `market_symbols` is 1st |

   The zero results come from the gate at `packages/tools/src/lonora_tools/tool_discovery.py:62`
   (`gate = min(query_tokens, key=lambda token: (frequencies[token], token))`): a query word that is in no tool
   text (`gold`) becomes the gate and every tool is skipped at `tool_discovery.py:69-73`. This is root cause 6,
   outside my group, but it applies here: even a model that tried to find a "gold symbol" tool would get nothing.
4. **The policy the model had at the moment of writing asks for exactly this shape of reply.** Mandatory core:
   `Report the practical failure and one concrete next step` (`lonora.md:163`); `Give at most one specific useful
   next suggestion when a suggestion is warranted.` (`lonora.md:33`); `Do not hide a failure … to make a reply sound
   smooth.` (`lonora.md:54`). The opposing lines exist but nothing enforces them: `For an ordinary safe read
   failure, make a bounded meaningful correction or use a genuinely supported alternative source.` (`lonora.md:160`),
   `Continue authorized work without asking whether to begin` (`lonora.md:35`), and, once the market chapter is
   loaded, `Use market_symbols to discover exact symbols before guessing aliases.` (`lonora.md:212`).
5. **No server-side check on the reply.** The SCRIPTED [10] text, with both codes, the identity line and the
   «إذا أردت» offer, was committed unchanged on `main` (`runs/conv-A-symbols.out`, `run9: run outcome`,
   `committed_reply`; and the stored thread rows at the end of the file). The only output filter removes
   credentials, server paths and resource ids (`packages/core/src/lonora_core/public_reply.py:10-25`); its own
   header says `Presentation is owned by the model's instructions, not a keyword veto on replies.`
   (`public_reply.py:3-4`).

The recovery was one call away. In the `recovery` run, both the bridge call and the direct call returned
(`runs/conv-A-symbols.out`, `recovery: TOOL RESULT ['market_symbols', …]`):

```json
{"ok": true, "symbols": ["BTCUSDm", "EURUSDm", "USOILm", "XAGUSDm", "XAUUSDm"]}
```

A suffix-aware matcher already exists in the code base but is used only when an agent is created:
`symbol_candidates` (`packages/tools/src/lonora_tools/agents.py:72-91`, callers `agents.py:120` via `resolve_market`
at `agents.py:257` and `apps/api/src/lonora_api/routes/agents.py:98`). The market read tools do not use it.

TRACE MUST CONFIRM: that the [10] run made no `tool_environment`, `tool_call` or `market_symbols` call after the
failures, and how many model turns it used.

### 1.8 Classification of [10]: FAILS

The same owner message on `main` reaches the same tools with the same model-chosen symbol and gets byte-identical
results; the reply text of [10] passes unchanged. No mechanism on `main` prevents any part of it.

---

## 2. [11] «ضع حرف m» → [12]

### 2.1 What context the model had

Measured on the first model request of the next run (`runs/conv-A-symbols.out`, block
`run11: context of the NEXT run after the failed gold read`; full request in `runs/conv-A-run11-requests.json`):

```
roles: system, system, system, system, user (context data), user, assistant, user
any role=tool message replayed: false
any assistant tool_calls replayed: false
contains previous reply prose ('symbol_not_found' text): true
contains 'XAUUSD': true
contains 'XAUUSDm': false
contains operational_observations: true
contains earlier-run tool evidence note: true
```

- **Tool calls and tool results of earlier runs are not replayed.** History is loaded from message rows with
  `MessageRow.role.in_(["user", "assistant"])` (`packages/agent-runtime/src/lonora_agent/context/history.py:117`),
  that is, the owner's text and the agent's published prose only.
- **Failed reads are dropped from the cross-run evidence.** `recent_tool_evidence` keeps the last 4 runs and
  12 entries (`packages/agent-runtime/src/lonora_agent/context/run_evidence.py:25-26`) and skips failures:
  `if result.get("ok") is not True and not effect: continue` (`run_evidence.py:158-160`). In the run, the only
  entry carried over was the successful `list_accounts` result (block `run11: earlier-run evidence block`), which
  again carries broker, login and server.
- **The failures come back only as tool name plus code, without arguments.** Block
  `run11: operational_observations block`:
  `{"tool": "market_candles", "code": "symbol_not_found", …}, {"tool": "market_quote", "code": "broker_account_not_found", …},
  {"tool": "market_instrument", "code": "broker_account_not_found", …}, {"tool": "market_snapshot", "code": "symbol_not_found", …}`
  (`packages/agent-runtime/src/lonora_agent/context/environment.py:48-55`, at most 5 facts `:75`). The symbol that
  failed is not in these facts. This block also re-shows the false `broker_account_not_found` to the next run.
- **The catalog is still not in context** (`XAUUSDm`: false).

So the only place the next run could read "XAUUSD failed" was the agent's own previous sentence
«محاولة الذهب على `XAUUSD` رجعت **symbol_not_found**», in history. That sentence plus «ضع حرف m» is enough for a
reader to form `XAUUSDm`, and [12] shows the model half-saw it («إذا تقصد الرمز الحالي للذهب…»). What was missing is
structured state: no record of the failed call's arguments, no open request ("gold status is still unanswered"),
no pending offer ("I offered to search for the gold name").

### 2.2 Why it asked and offered instead of acting

- UNSURE: why the model judged the instruction ambiguous. That is model behaviour; code cannot settle it.
- Policy that licenses the question, always loaded: `Stay friendly and curious — I'd rather ask a good question
  than guess wrong.` (`packages/agent-runtime/resources/bootstrap/SOUL.md:10`). The stricter line
  `Ask one focused clarification only when missing information prevents meaningful progress.` (`lonora.md:205`)
  sits in the `voice` chapter (`<!-- policy:voice -->` at `lonora.md:177`), not in the always-loaded core
  (`<!-- policy:core -->` at `lonora.md:9`), so a text chat run does not receive it.
- Even the literal reading needed no question: trying `XAUUSDm` is one read call (`market_instrument` or
  `market_snapshot`), and a wrong guess costs one more `symbol_not_found`.
- «أبحث عن التسمية الصحيحة فورًا» is a second offer of the same search as in [10]. Nothing on `main` stores the
  first offer or detects that a reply ends with an offer of a read the agent could run itself: the SCRIPTED [12]
  text was committed unchanged (`runs/conv-A-symbols.out`, `run11: run outcome`). The stop gates file is about
  Task runs and saved monitoring (`packages/agent-runtime/src/lonora_agent/stop_gates.py:1-6`, imports at `:36-39`).
- The native tool list of this run was the same 22 tools; `market_symbols` still not native
  (`run11: native tools offered on model turn 1`).

TRACE MUST CONFIRM: that the [12] run made zero tool calls; and the content of the `operational_observations`
block in that run's first request (expected: the two codes of [10], no symbol).

### 2.3 Classification of [12]: FAILS

Same context assembly, same exposure, no guard on a clarification or an offer. Nothing on `main` changes it.

---

## 3. [13] «يعني XAUUSDM» → [14]

### 3.1 [13]: the owner types the symbol

[13] is a consequence of [10] and [12]; classification **FAILS** with them. One part of the code does work here:
the owner typed `XAUUSDM` (capital M) and got `XAUUSDm`, because `catalog_symbol` accepts a single case-only
match (`packages/tools/src/lonora_tools/symbols.py:11-14`; test `tests/check_metaapi_adapter.py:317`). The same
function refuses `XAUUSD` (`tests/check_metaapi_adapter.py:318` asserts that `XAUUSD` stays `XAUUSD`).

### 3.2 [14]: which tool was called

The five numbers in [14] are the fields of `market_instrument`. Result in the run for `symbol: "XAUUSDM"`
(`runs/conv-A-symbols.out`, `run13: TOOL RESULT ['market_instrument', …]`):

```json
{"ok": true, "symbol": "XAUUSDm", "description": "Gold vs US Dollar", "digits": 3, "tick_size": "0.001",
 "volume_min": "0.01", "volume_max": "200", "volume_step": "0.01", "stops_level": 0, "point_size": "0.001",
 "contract_size": "100", "base_currency": "XAU", "profit_currency": "USD"}
```

| [14] line | Field (`packages/adapters/src/lonora_adapters/brokers/normalize.py:39-53`) |
| --- | --- |
| «الذهب مقابل الدولار» | `description` |
| «أقل حجم: 0.01» | `volume_min` |
| «أكبر حجم: 200» | `volume_max` |
| «خطوة الحجم: 0.01» | `volume_step` |
| «أقل مسافة وقف: 0» | `stops_level` |
| «الخانة السعرية: 3» | `digits` |

The corrected spelling `XAUUSDm` in the reply is the `symbol` field of the same result (`market.py:47-48`).
[14] contains no price and no trend, so `market_quote` and `market_snapshot` were most likely not called in that
run; they appear only in [16] after «ياريت».

TRACE MUST CONFIRM: the [14] run called `market_instrument` (with `XAUUSDM` or `XAUUSDm`) and neither
`market_quote` nor `market_snapshot`.

### 3.3 Why specifications instead of the answer

- The model treated [13] as the whole request ("confirm this symbol") and not as the missing piece of [9]
  ("how is gold"). Nothing in the runtime ties the two: the run prompt is the latest owner message, [9] is plain
  history, and there is no open-request state (section 2.1).
- The tool it picked is the one whose description says it is the first step for one symbol:
  `Read specifications for ONE exact broker symbol from market_symbols. Prefer this to loading every instrument
  for a single-symbol analysis.` (`packages/tools/src/lonora_tools/market.py:108`). `market_snapshot`, the tool that
  answers "how is gold" in one call, describes itself as `One compact multi-timeframe summary for an exact broker
  symbol: bid/ask/spread and freshness; per timeframe closed-bar trend slope…`
  (`packages/tools/src/lonora_tools/market_analysis.py:359-364`); it was native in the same run.
- Policy lines about answering the asked question exist only as general wording, and none is enforced:
  `Start with the result, the actual finding, or the single fact preventing completion.` (`lonora.md:30`);
  `An acknowledgment is not completion; finish the actual work or state its precise remaining obstacle.`
  (`lonora.md:36`); `Before final delivery, check: requested outcome, evidence, language, truthful status…`
  (`lonora.md:164`). No line says that a status question about an instrument means price, trend per timeframe,
  levels and a conclusion, or that specifications are given only on request (brief principle 13). Searched:
  `grep -n "symbol\|suffix\|alias" packages/agent-runtime/resources/system/lonora.md packages/agent-runtime/resources/constitution/*.md packages/agent-runtime/resources/bootstrap/*.md`
  and the lines listed in section 1.7.
- The closing «إذا تريد، أجيب لك الآن السعر الحالي والاتجاه» offers two read-only calls that were native and
  needed no permission. The SCRIPTED [14] text was committed unchanged (`run13: run outcome`).
- Nothing durable records `XAUUSD → XAUUSDm` for this account after [14]. The successful `market_instrument`
  result is carried only as cross-run evidence for the next 4 runs of the same thread (`run_evidence.py:25`,
  `:210-221`); a later thread or a later day starts from the guess again (brief principle 14).

### 3.4 Classification of [14]: FAILS

On `main` the same message leads to the same tool choice being available and attractive, the same result, and no
check that the open question of [9] was answered.

---

## 4. Timeline note

`git show --stat aa50e8e` (PR #42, merged 2026-11-11T07:08:03+00:00) touches `uncertain_outcome.py`,
`loop_outcomes.py`, `loop_restore.py`, `tool_loop.py`, two constitution files, `memory.py`, `models.py`,
`runtime_control.py` and one test. None of it is on the path of [9]–[14]. Between `aa50e8e` and `9f5b1da` the
files on that path are unchanged (section 0). PR #42 did add one sentence that touches this group, `Reach a tool outside your native list with tool_call.`
(`packages/agent-runtime/resources/constitution/trading-policy.md:7`, in the paragraph that PR added). If that build
was live, the sentence did not make the model use `market_symbols` in [10] or [12].
TRACE MUST CONFIRM: which commit production served between 07:37 and 07:45 UTC.

---

## 5. Root causes 1–5 of the brief

### Cause 1 — `catalog_symbol` matches exactly or by letter case only: CONFIRMED

`packages/tools/src/lonora_tools/symbols.py:9-15`:

```python
    if symbol in catalog:
        return symbol
    folded = symbol.casefold()
    matches = [name for name in catalog if name.casefold() == folded]
    if len(matches) == 1:
        return matches[0]
    raise LonoraError("symbol_ambiguous" if matches else "symbol_not_found", 404)
```

`XAUUSD` against `XAUUSDm`: not equal, not equal after `casefold()`, so `symbol_not_found`. Reproduced
(`market_snapshot` row in section 1.3).

Refinement: the wrapper `canonical_broker_symbol` has two modes, and most read tools use the lenient one.

- With `require_exists=True` the miss is raised: `market_snapshot` (`market_analysis.py:140`), broker hours in
  `market_sessions` (`market_analysis.py:215`), `market_candles_to_workspace` (`market_analysis.py:305`),
  `market_structure` (`market.py:78`), owner action proposals (`packages/tools/src/lonora_tools/owner_actions.py:85`).
- Without it the miss is swallowed and the unknown symbol goes to the broker (`symbols.py:32-35`):
  `market_instrument` (`market.py:47`), `market_quote` (`market.py:58`), `market_candles` (`market.py:65`),
  `chart_indicator` (`packages/tools/src/lonora_tools/chart_indicator.py:20`), `trade_execute`
  (`packages/tools/src/lonora_tools/trade.py:634`).

That split is why one wrong symbol produced two different codes in one reply: the strict tools answer from the
catalog, the lenient tools let the broker's 404 through to cause 3.

### Cause 2 — `resolve_instrument` matches exactly only: CONFIRMED, but it is dead code

`packages/market/src/lonora_market/instruments.py:5-9`:

```python
def resolve_instrument(instruments: list[Instrument], symbol: str) -> Instrument:
    matches = [item for item in instruments if item.symbol == symbol]
    if len(matches) != 1:
        raise LonoraError("broker_symbol_not_found", 404)
    return matches[0]
```

Exact `==` only. But nothing calls it: `grep -rn "resolve_instrument" --include=*.py .` (excluding `.venv`) returns
only the definition line. It played no part in [10]. It also uses a third code for the same condition
(`broker_symbol_not_found`, beside `symbol_not_found`).

### Cause 3 — every 404 outside the candles stage becomes `broker_account_not_found`: CONFIRMED

`packages/adapters/src/lonora_adapters/brokers/metaapi.py:52-61`:

```python
    if status == 404:
        message = str(error).split("Request URL:", 1)[0].casefold()
        missing = any(
            term in message for term in ("not found", "unknown", "does not exist", "not exist")
        )
        if stage != "candles" or "account" in message and missing:
            return LonoraError("broker_account_not_found", 404)
        if "symbol" in message and missing:
            return LonoraError("symbol_not_found", 404)
        return LonoraError("broker_candles_not_found", 404)
```

- `and` binds tighter than `or`, so the condition is `stage != "candles" or ("account" in message and missing)`.
  For any stage other than `candles` the message is never examined.
- Every RPC read fails through `raise self.diagnose(error, "rpc")` (`metaapi.py:434`), so the stage for an unknown
  symbol in `get_symbol_specification` or `get_symbol_price` is always `rpc`. The outer handlers
  (`metaapi.py:474`, `:701`) do not change it, because `diagnose` returns an already diagnosed error as is
  (`metaapi.py:237-238`).
- Reproduced: the SDK error text was `Specification for symbol XAUUSD not found`, the code returned was
  `broker_account_not_found` (log line in section 1.3). This is the second code in [10].
- The same false code is then stored and shown again to the next run (section 2.1).

### Cause 4 — a tool error is `{ok:false, code}` only: CONFIRMED

`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:110-117`:

```python
    except LonoraError as error:
        if error.code in {"stale_lease", "skill_continuation_unavailable"}:
            raise
        error_result: dict[str, Any] = {"ok": False, "code": error.code}
        if isinstance(error, ToolArgumentsError):
            error_result["issues"] = error.issues
            error_result["retryable"] = True
        result = error_result
```

No `hint`, no `candidates`, no echo of the rejected value. `LonoraError` raised by `catalog_symbol` carries only a
code and a status (`symbols.py:15`), so there is nothing more to forward even if dispatch wanted to.
Refinement: the model does see one more object, `recovery`, added by `observe` after dispatch (cause 5); it is
generic.

### Cause 5 — `classify` maps every `*_not_found` to `inspect_existing_state` with no candidates: CONFIRMED

`packages/agent-runtime/src/lonora_agent/environment.py:80-81`:

```python
    elif code.endswith("_not_found"):
        category, action = "not_found", "inspect_existing_state"
```

and the returned object is only `category`, `next_action`, `safe_to_retry` (`environment.py:89-93`), plus the
constant `schema_tool` (`packages/contracts/src/lonora_contracts/tool_environment.py:31`) and `attempt` /
`retry_exhausted` (`environment.py:205-209`). `classify(code, tool)` receives neither the call arguments nor any
catalog, so it cannot name candidates or the tool to inspect with. Measured result in section 1.4:
`symbol_not_found` and `broker_account_not_found` produce the same `recovery` object.

---

## 6. What the production trace must confirm (collected)

1. Which commit production served at 07:44–07:45 UTC, and the value of `LONORA_GENUI_V2`.
2. [10] run: tool calls with arguments, in order. Expected: an account read (`list_accounts` or `account_read`),
   then `XAUUSD` passed to `market_snapshot` and/or `market_candles` (→ `symbol_not_found`) and to
   `market_instrument` (→ `broker_account_not_found`). No `market_symbols`, `tool_call` or `tool_environment` call.
3. [10] run: the stored tool result contents equal the two JSON objects of section 1.4, and the adapter log has
   `broker_rpc_failed code=broker_account_not_found type=NotFoundException` with a message about the symbol, not
   the account. The real MetaApi message text for an unknown symbol.
4. [10] run: the native tool names stored in `execution_state.tool_exposure.native` (expected: no `market_symbols`).
5. [10] run: number of model turns, and whether the `market` chapter was in the request that produced the reply.
6. [12] run: zero tool calls; its first request contains the `operational_observations` block with the two codes
   and no role `tool` messages from the [10] run.
7. [14] run: `market_instrument` called with `XAUUSDM` or `XAUUSDm`; no `market_quote`, no `market_snapshot`.
8. Whether any memory entry or remembered tool existed from before [9] that mentions a gold symbol
   (the reproduction started from an empty database).

## 7. Limits of this report

- The model turns are scripted. The reproduction proves what the runtime returns and lets through; it does not
  prove what the production model chose.
- The stored connection in the reproduction is a simulation row with a MetaApi adapter object swapped in. The
  `provider` field of `list_accounts` therefore says `simulation`; in production it says `metaapi`.
- The SDK exception text is assumed. It affects only the `market_candles` row of section 1.3.
