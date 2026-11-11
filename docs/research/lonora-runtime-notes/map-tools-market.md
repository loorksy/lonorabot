# Tool surface map, group D: MARKET / CHART / BROKER families

Repository `/home/user/lonorabot`, HEAD `9f5b1da`. Read-only audit. All paths are relative to the repo root.
Line numbers were taken with `cat -n` / `awk` / `grep -n` and re-opened before finishing.

Scope: `packages/tools/src/lonora_tools/{market,market_analysis,market_binding,market_watch,symbols,chart,chart_indicator,chart_snapshot,chart_state}.py`, followed into `packages/market`, `packages/charts`, `packages/adapters/.../brokers`, `packages/adapters/.../market`, `apps/api/.../routes/{agents,account_authority}.py`, `docs/market-analysis.md`, `docs/market-structure.md`.

Class labels used in the census: **RECOVERABLE-NOT-LED**, **OWNER-NEEDED**, **DEAD-END**, **BUG** (the four requested). I add one label outside the four, **OK-LED**, for outcomes where the result or the runtime really does lead to recovery; those are not defects and are counted separately.

---

## 0. What the model sees for ANY failed tool call (applies to every row below)

- A `LonoraError` raised anywhere under a tool handler becomes exactly `{"ok": false, "code": "<code>"}`. Nothing else is copied from the error: `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:110-117` (`error_result: dict[str, Any] = {"ok": False, "code": error.code}` at `:113`). Only schema validation errors get more (`issues`, `retryable`) at `:114-116`.
- The loop then appends a generic `recovery` object chosen from the code string alone: `packages/agent-runtime/src/lonora_agent/environment.py:203-210`. The classifier is `classify()` at `environment.py:35-93`. For the codes of these families:
  - any code ending in `_not_found` -> `category: "not_found"`, `next_action: "inspect_existing_state"` (`environment.py:80-81`);
  - codes in `TRANSIENT_READ_CODES` -> `temporary_unavailable` / `inspect_health`, `safe_to_retry: true` for read-only tools (`environment.py:44-45`, `:92`; the set is `packages/core/src/lonora_core/runtime_failure.py:10-21`);
  - binding refusals -> `permission_denied` / `respect_scope` (`environment.py:56-69`);
  - everything else -> the default `terminal_domain_failure` / `alternate_route` (`environment.py:36-37`).
- I ran `classify()` against the live registry (no repo writes). Real output for the two codes of the gold incident:
  `symbol_not_found` -> `{"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 0, "retry_exhausted": false}`; `broker_account_not_found` -> the identical object. (`attempt` is then set to the failure count at `environment.py:205`.) The `ToolRecovery` contract has no field for a hint, a candidate list or a named next tool: `packages/contracts/src/lonora_contracts/tool_environment.py:27-33`.
- So for every failure in this document the model receives: a snake_case code, a 3-word generic `next_action`, and `schema_tool: "tool_environment"` (the schema inspector, not a recovery tool). **No tool in these families returns a candidate list, a "did you mean", or the name of the tool that would fix the problem.**
- Runtime auto-retry exists only for read-only tools and only for `TRANSIENT_READ_CODES`: `packages/agent-runtime/src/lonora_agent/tool_block.py:309-328` (back-off `2**attempt` s, `environment.py:219-224`). After 3 failures of the same call (same name + same arguments) the route is refused without executing: `environment.py:127-131`, result `{"ok": false, "code": "tool_route_exhausted", "recovery": {"next_action": "alternate_route_or_wait"}}` at `tool_dispatch.py:70-81`. Read routes are forgotten only at real owner input or an external wake (`environment.py:104-124`).
- Non-`LonoraError` exceptions: `TimeoutError`/`ConnectionError` -> `tool_read_timeout` / `tool_connection_failure` for read tools, `tool_execution_uncertain` for mutating tools (`tool_dispatch.py:118-128`); any other exception -> `tool_internal_failure` (read) or `tool_execution_uncertain` (mutating) (`tool_dispatch.py:129-138`).
- Guardrail texts injected after repeated failures end with an explicit permission to stop: "correct the arguments, use a narrower request or a genuinely different source, or report the blocker." (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:82-86`).

---

## 1. FIRST WORKED EXAMPLE: the gold incident (XAUUSD vs XAUUSDm), traced from code

CHECKER CORRECTION (trace wins): this section was first written without a record of the calls. The production trace now gives them (`production-trace.md` Part 4, run 1ae9a14c): `list_accounts {}` -> ok; `market_snapshot {"account_id": <correct connection_id>, "symbol": "XAUUSD", ...}` -> `{"ok":false,"code":"symbol_not_found","recovery":{"category":"not_found","next_action":"inspect_existing_state","safe_to_retry":false,"schema_tool":"tool_environment","attempt":1,"retry_exhausted":false}}`; then `market_instrument {"symbol":"XAUUSD"}` -> `broker_account_not_found` with the same recovery block (about five seconds). No `market_symbols` call, no `tool_environment` call. The mechanism below matches this exactly; the earlier UNSURE about which tool was called is resolved.

### 1.1 Which tools can produce `symbol_not_found`, and where

There are exactly two raise sites reachable from the market/chart tools, plus one in agent creation:

| # | Raise site | Reached by | Condition |
|---|---|---|---|
| A | `packages/tools/src/lonora_tools/symbols.py:15` (`raise LonoraError("symbol_ambiguous" if matches else "symbol_not_found", 404)`) | Tools that call `canonical_broker_symbol(..., require_exists=True)`: `market_structure` (`market.py:78`), `market_snapshot` (`market_analysis.py:140`), `market_sessions` with a symbol (`market_analysis.py:215`, re-raised at `:219-221`), `market_candles_to_workspace` (`market_analysis.py:305`) | The requested name is not in `broker.symbols()` exactly and has no single case-only match (`symbols.py:9-14`). `XAUUSD` vs catalog `XAUUSDm` fails here: I ran `catalog_symbol(["EURUSDm","XAUUSDm","XAUEURm"], "XAUUSD")` and it raised `symbol_not_found`. |
| B | `packages/adapters/src/lonora_adapters/brokers/metaapi.py:59-60` | MetaApi candle history only (stage `"candles"`: `metaapi.py:725`, `:659`): `market_candles`, `chart_indicator`, `chart_snapshot` with explicit market fields, chart scene refresh | The provider answers HTTP 404 and the message contains "symbol" and one of "not found / unknown / does not exist / not exist" (`metaapi.py:52-60`). |
| C | `packages/tools/src/lonora_tools/agents.py:124` | `create_agent` market resolution (`agents.py:94-124`) | No catalog name matches exactly, by case, or by suffix. Not a read tool. |

`market_snapshot` is the tool a code comment next to its registration calls the one for "the first look at a market" (`market_analysis.py:368-370`; this is a source comment, not text the model sees) and is native for trading identities (see 1.3). The trace confirms site A through `market_snapshot` as the origin of the owner's "محاولة الذهب على `XAUUSD` رجعت **symbol_not_found**" (run 1ae9a14c, `production-trace.md` Part 4 #14-#15).

Important asymmetry: `market_quote`, `market_instrument`, `market_candles` and `chart_indicator` call `canonical_broker_symbol` WITHOUT `require_exists` (`market.py:47`, `:58`, `:65`; `chart_indicator.py:20`). In that mode the catalog miss is swallowed and the wrong name is passed on unchanged: `symbols.py:32-35` (`except LonoraError: if require_exists: raise; return symbol`). So the same wrong symbol produces different codes depending on which tool was called (see 1.5).

### 1.2 What the model sees in the result

For site A or B the complete tool result is:

```json
{"ok": false, "code": "symbol_not_found",
 "recovery": {"category": "not_found", "next_action": "inspect_existing_state",
              "safe_to_retry": false, "schema_tool": "tool_environment",
              "attempt": 1, "retry_exhausted": false}}
```

(construction: `tool_dispatch.py:113`, `environment.py:80-81`, `:203-210`). There is no hint, no candidate list and no next step naming `market_symbols`. This is despite the fact that at site A the handler had the full broker catalog in memory at the moment it failed: `canonical_broker_symbol` had just fetched `names = await broker.symbols()` (`symbols.py:21`) and `catalog_symbol` iterates it (`symbols.py:8-14`), then throws it away.

### 1.3 Does a symbol search/discovery tool exist, and was it visible?

- It exists: `market_symbols` (`market.py:97-105`), handler returns `{"symbols": [...]}` (`market.py:40-42`). Its description is the right instruction: "Discover exact broker symbol names without loading specifications for every instrument. Use before guessing broker symbols or aliases; suffixes matter." (`market.py:99-100`).
- It is **discovery-only**: the `Tool(...)` at `market.py:97-105` has no `eager=` argument, unlike `market_instrument` (`market.py:112`), `market_quote` (`:128`), `market_candles` (`:136`), `market_snapshot` (`market_analysis.py:370`), `market_sessions` (`market_analysis.py:383`). CHECKER CORRECTION: the Personal Agent's profiles are `core`+`market`+`coordination` (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:43-46`), not `core`+`market` only, so the 20-name list first written here was incomplete. `registry.eager_names(["core","market","coordination"])` on the loaded registry returns 23 names, exactly the 23 the trace shows were offered in every run: `account_read, agent_inspect, chart_snapshot, list_accounts, market_candles, market_decision_history, market_decision_record, market_instrument, market_quote, market_sessions, market_snapshot, memory_read, memory_write, peer_send, session_search, skill_view, skills_list, tool_call, tool_environment, trade_execute, wait_for_input, watch_create, web_search` (`production-trace.md` Part 1, BASELINE). `market_symbols` is not in it (confirmed by trace and registry). It is reachable only through the bridge `tool_call {"name": "market_symbols", "arguments": {...}}` (`packages/tools/src/lonora_tools/registry.py:167-178`), and appears to the model only as a bare name in the capability inventory line `market: ...` (`registry.py:414-473`), with no description or schema.
- The native tool descriptions point at it as if it were at hand: `market_instrument` says "Read specifications for ONE exact broker symbol from market_symbols." (`market.py:108`). `market_quote` says "for an exact broker symbol" (`market.py:123`) and `market_snapshot` "for an exact broker symbol" (`market_analysis.py:360`); neither says how to get the exact symbol.
- The policy line "Use market_symbols to discover exact symbols before guessing aliases." is `packages/agent-runtime/resources/system/lonora.md:212`, inside the `policy:market` chapter (`lonora.md:209-247`). Domain chapters are injected only after the model has already called a tool of that family: "Actual tool-call names select chapters." (`packages/agent-runtime/src/lonora_agent/skills/system_policy.py:126`; selection loop over previous assistant tool calls at `:134-140`). So on the first market call of a conversation the model has not been shown line 212; it sees it only after it has already guessed. CHECKER PRECISION: chapters are recomputed on every model request from the last 16 messages (`system_policy.py:134-140`). In run 1ae9a14c the first call was `list_accounts`, which selects the `account` chapter, not `market` (checked with `policy_bundle().tool_policies`); the `XAUUSD` guess in `market_snapshot` was therefore made without line 212. But from the next request on, the `market` chapter WAS in context: the model called `market_instrument("XAUUSD")` and wrote the final reply with "Use market_symbols to discover exact symbols before guessing aliases." (`lonora.md:212`) in front of it, and still neither called `market_symbols` nor `tool_environment`. The missing first-turn chapter explains the first guess, not the final offer.
- The one prompt that names the gold problem directly, "Gold may have broker suffixes or a different broker name; never guess or strip them." (`packages/agent-runtime/resources/prompts/trading_context.md:5`), is not loaded by any code at HEAD: `load_prompt` (`packages/agent-runtime/src/lonora_agent/skills/loader.py:20-24`) is called only with `consolidator_archive`, `group_behavior`, `run_context_summary`, `subagent_system`, `suggested_reply`, `web_search_on` (grep of `load_prompt(` over `packages` and `apps`), and `grep -rn trading_context` finds no Python reference. The file is dead text.
- ADDED BY CHECKER: the `schema_tool: "tool_environment"` route in the recovery block does not reach `market_symbols` with the words an owner or model would use for gold. `search_definitions` keeps a tool only if it contains the query's rarest token (the "gate", `packages/tools/src/lonora_tools/tool_discovery.py:60-73`), with no stemming or aliases (`tool_discovery.py:40-41`). Run against the loaded registry (read-only): `"gold"`, `"gold symbol"`, `"XAUUSD"`, `"الذهب"`, `"symbol suffix"` all return an empty list (the tokens `gold`, `xauusd`, `الذهب`, `suffix` occur in no tool name, description or parameter name); `"find symbol"` returns `trade_record_history, search_internal` without `market_symbols`. Only generic catalog words such as `"symbol names"` or `"exact broker symbol"` find it. So the one discovery path named in the failure needs the model to already think in the catalog's English vocabulary.
- The capability inventory does name `market_symbols` (checked: the rendered inventory's `market:` line lists it, 126 of 126 capabilities shown), and its prefix says to inspect with tool_environment "before claiming an ability is absent" (`registry.py:428-429`); that is a lead to the tool's existence, not to using it after a symbol miss.
- `market_symbols` takes only `account_id` (`AccountInput`, `market.py:15-18`). There is no query/filter argument, so even when called it returns the entire catalog and the model must find gold in it itself. An oversized result is replaced by a bounded summary (`tool_block.py:252-257`).

### 1.4 Does deterministic alias/suffix resolution exist?

Yes, twice, and neither is wired to the read tools:

- `symbol_candidates()` at `packages/tools/src/lonora_tools/agents.py:72-91`: exact, then case-only, then "every name that only adds a broker suffix to it" (separator in `".-_#!+"` or up to 4 lowercase letters: `agents.py:54-57`, `:87-90`). I ran `symbol_candidates(["EURUSDm","XAUUSDm","XAUEURm"], "XAUUSD")` -> `['XAUUSDm']`. Its only callers are `resolve_market` (`agents.py:120`), used by the `create_agent` tool (`agents.py:257`) and the HTTP route `apps/api/src/lonora_api/routes/agents.py:98`.
- `instrument_entry()` at `packages/contracts/src/lonora_contracts/instrument_names.py:36-54` maps a broker spelling back to a table entry with the same suffix rule, and the table already knows gold in Arabic: `InstrumentName("XAUUSD", "الذهب", "Gold", "ذهب")` (`instrument_names.py:21`). It is used only by GenUI naming (`packages/agent-runtime/src/lonora_agent/genui_vocabulary.py:9`, `packages/agent-runtime/src/lonora_agent/genui_compile.py:32`, `packages/contracts/src/lonora_contracts/genui_intents.py:17`).
- The read tools use only `catalog_symbol` (`symbols.py:6-15`): exact or single case-only match. The docstring says so: "exact, or the single case-only match" (`symbols.py:7`).
- Policy text actively discourages the model from doing the suffix step itself: "Never strip suffixes, substitute an exchange feed or assume one broker's instrument exists at another." (`lonora.md:224`); "Letter case is not a different symbol; never strip suffixes." (`packages/db/src/lonora_db/agent_binding.py:15-16`); `market_candles` description: "Read historical broker candles without symbol rewriting." (`market.py:132`); `packages/tools/src/lonora_tools/trading_decision.py:79` comment "Exact symbols are intentional. No hidden aliases or suffix stripping." Exactness is **needed for safety on execution paths** (a trade or grant on a guessed symbol would be money on the wrong contract). It is over-caution for read-only quotes/candles, where adding a suffix the catalog confirms is a lookup, not a guess.
- Other places that check a symbol with exact string equality only (no case, no suffix): `apps/api/src/lonora_api/routes/agents.py:34-35` (`if symbol not in await broker.symbols(): raise LonoraError("symbol_not_found", 404)`), `apps/api/src/lonora_api/routes/account_authority.py:54-56`. These are owner-UI routes; `packages/market/src/lonora_market/instruments.py:5-9` (`broker_symbol_not_found`) is exact too but has no caller (grep finds only its definition).

### 1.5 Why `broker_account_not_found` appears on a connection that just returned account info

It is not an account lookup at all. It is a mislabelled symbol 404:

1. "Contract details" is `market_instrument`. Its handler resolves the broker, then calls `canonical_broker_symbol(broker, args["symbol"])` without `require_exists` (`market.py:45-48`), so `XAUUSD` passes through unchanged (`symbols.py:32-35`).
2. `MetaApiBroker.instrument("XAUUSD")` finds no streamed specification and calls `self.read_rpc("get_symbol_specification", symbol)` (`metaapi.py:461-469`).
3. The MetaApi SDK turns the server's `NotFoundError` into `NotFoundException` (`.venv/lib/python3.12/site-packages/metaapi_cloud_sdk/clients/metaapi/metaapi_websocket_client.py:1758-1759`), whose `status_code` is 404 (`.venv/lib/python3.12/site-packages/metaapi_cloud_sdk/clients/error_handler.py:62-72`).
4. `read_rpc` wraps it with `self.diagnose(error, "rpc")` (`metaapi.py:434`); the outer `diagnose(error, "instrument")` at `:474` keeps the already-diagnosed error (`metaapi.py:237-238`).
5. `provider_error` (`metaapi.py:39-82`) for status 404 does: `if stage != "candles" or "account" in message and missing: return LonoraError("broker_account_not_found", 404)` (`metaapi.py:57-58`). Python parses this as `(stage != "candles") or (...)`, so **every 404 from any non-candle stage is reported as `broker_account_not_found`**, whatever the message says. The symbol branch at `:59-60` is reachable only when `stage == "candles"`.

I confirmed this by calling `provider_error(NotFoundException("Specified symbol not found"), stage)` with the repo's code: stages `rpc`, `quote`, `instrument`, `symbols` all return `broker_account_not_found`; stage `candles` returns `symbol_not_found`. UNSURE only about the exact wording MetaApi's server uses for an unknown symbol (no live account; `docs/market-analysis.md:192` says the same); the wording does not matter for non-candle stages because the message is not consulted. The checker re-ran the same call (stages `rpc`, `quote`, `instrument`, `symbols` -> `broker_account_not_found`; `candles` -> `symbol_not_found`), and production shows the effect: `market_instrument("XAUUSD")` on a connection that `list_accounts` had just returned returned `broker_account_not_found` (`production-trace.md` Part 4 #16-#17). UNSURE whether treating every non-candle 404 as an account 404 was a deliberate simplification; either way it contradicts `lonora.md:239` and misled the model in production.

Consequences:
- Account info worked because `account_read` goes through `read_rpc("get_account_information")` (`metaapi.py:781-783`) on the same, healthy connection. The connection id was never wrong.
- `market_quote("XAUUSD")` on MetaApi takes the same path (`metaapi.py:698-701`, RPC `get_symbol_price`) and would also say `broker_account_not_found`, not `symbol_not_found`. So for one wrong symbol the model can receive `symbol_not_found` (snapshot/structure/sessions/candles) or `broker_account_not_found` (quote/instrument) on the same account within seconds.
- The policy sentence "A truly unknown symbol is not a generic connection failure." (`lonora.md:239`) is contradicted by this adapter mapping. The existing test only covers the candle stage (`tests/check_broker_history.py:163-166`).
- The owner-facing translation of this code in the web client is "Broker account not found." (`apps/web/src/lib/user_error.ts:156-157`), which is false in this situation.

A second, genuine route to the same code exists: `resolve_account()` failing on `get_account` (`metaapi.py:264-276`), cached for 30 s (`ACCOUNT_METADATA_SECONDS`, `metaapi.py:36`, `:257-258`). That is a real provisioning problem and cannot be told apart from the mislabelled symbol case by the model, because both arrive as the same bare code.

### 1.6 Why the model offered instead of acting

Nothing in code forces it to stop; a combination of texts makes "report + offer" the compliant-looking answer:

- The result gives no next tool (1.2), and the discovery tool is not native (1.3).
- Core policy, always present: "Report the practical failure and one concrete next step, preserving the distinction between unavailable and uncertain." (`lonora.md:163`). The owner's quoted reply ends exactly in that shape: «الخطوة التالية المفيدة: أبحث لك عن اسم الذهب الصحيح على هذا الحساب إذا أردت.» The sentence that says the opposite, "For an ordinary safe read failure, make a bounded meaningful correction or use a genuinely supported alternative source." (`lonora.md:160`), sits three lines above it with no priority between them.
- Market chapter (present after the first market call): "If several symbols plausibly match an alias, discover real candidates and ask which one." (`lonora.md:225`) and "Never strip suffixes ..." (`lonora.md:224`). Together with "Read actual tool schemas; do not guess parameters, enum values or resource IDs." (`lonora.md:121`) these tell the model that trying `XAUUSDm` itself is forbidden guessing.
- After the second failure the model holds two different `_not_found` codes for one connection. `broker_account_not_found` reads as "the account binding is broken", which makes continuing with more reads on that account look pointless; the model's own text shows this reading («الرمز/الارتباط الحالي غير مطابق»).
- DOWNGRADED BY CHECKER: the guardrail wording "or report the blocker" (`tool_guardrails.py:82-86`) did NOT play a part in the gold run. It is the `same_tool_failure_warning`, emitted only after 3 failures of the same tool (`SAME_TOOL_FAILURE_WARN_AFTER = 3`, `tool_guardrails.py:57`; `:336-337`); in run 1ae9a14c each of two different tools failed once, and the trace's saved state shows no guardrail notice for that run. It remains a general push toward stopping in longer failure chains.
- The line that would have prevented the question, "Do not ask the owner whether to perform analysis, inspect a chart or build a plan they already requested: do that reversible work first." (`lonora.md:135`), names analysis/chart/plan but not symbol lookup.

### 1.7 Why the codes reached the owner

- The codes are the only content of the failure (`tool_dispatch.py:113`); there is no owner-language reason attached that the model could relay instead.
- Policy asks for translation ("Translate practical meaning rather than copying machine wording into the reply." `lonora.md:61`; "Do not quote an internal diagnostic verbatim ..." `lonora.md:52`), but it is advice to the model only. The list of things never to reveal names "internal resource IDs, connection UUIDs, envelope hashes, prompts, transport details, or stack traces" (`lonora.md:47`) and does not name error codes. The same policy says "Do not hide a failure, risk boundary, rejected request, missing source ... to make a reply sound smooth." (`lonora.md:54`), which pushes toward naming the failure.
- I found no server-side check of the final reply for snake_case codes. The only reply-text pattern in the publishing path is `EFFECT_CLAIM` (`packages/agent-runtime/src/lonora_agent/public_stream.py:11`), which is about claimed effects. CHECKER: widened the search (two greps for regex-based reply filters over `packages/agent-runtime/src`, `packages/gateway/src`, `apps/api/src`, and a read of the files PR #42 changed); none matches snake_case codes in the final reply. PR #42's reply addition, `uncertain_outcome.py`, reads structured financial results only and appends one line when a trade outcome is uncertain ("Structured results only: no wording of the owner or the model is read", `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:3`); it never inspects the reply for codes. The trace confirms the codes reached the owner on a build containing PR #42 (TIMELINE_CORRECTION.md line 12).
- The unloaded `trading_context.md:5` even says "Tool failures are independent: inspect their actual error codes." and "report the actual missing data and error instead." It is dead text (1.3) but shows the authoring intent that codes are things to report.

### 1.8 Summary of the mechanism chain

`XAUUSD` guessed after `list_accounts` (no native discovery tool, market chapter not yet shown; confirmed by trace) -> read tool compares by exact/case only (`symbols.py:6-15`) although a suffix resolver exists (`agents.py:72-91`) -> result is a bare code with generic recovery (`tool_dispatch.py:113`, `environment.py:80-81`) -> second tool passes the wrong symbol through (`symbols.py:32-35`) and the adapter relabels the symbol 404 as an account 404 (`metaapi.py:57-58`) -> policy says report failure + one next step (`lonora.md:163`) and forbids guessing/stripping (`lonora.md:121`, `:224`); `lonora.md:212` ("Use market_symbols ...") was in context by then but the model did not act on it, and the recovery's `tool_environment` path does not find `market_symbols` from words like "gold" or "XAUUSD" (1.3) -> reply contains both codes and an offer.

---

## 2. Tool inventory: what each tool does, who may call it, exposure, limits

Common rules (apply to every row):
- Registration and family: `packages/tools/src/lonora_tools/loader.py:10-50` (`market`, `market_analysis`, `market_watch` -> toolset `market`; `chart*` -> `charts`).
- Exposure: "native" = schema sent from the first turn for the profile; everything else is discovery-only through `tool_call` (`registry.py:260-304`, `packages/tools/src/lonora_tools/base.py:18-25`). Profile `market` is given to an agent bound to a broker account and to the Personal Agent; all other agents get `research` (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:43-44`).
- Scopes: `full` = everything; `observe_only` = everything non-financial; `helper` (subagent) = read-only tools plus `workspace_execute`/`artifact_create` (`packages/tools/src/lonora_tools/base.py:49-50`, `:92-97`). A tool outside scope fails with `tool_not_allowed` (`registry.py:483-484`). None of the tools in these families is `financial`.
- Dispatch deadline: 45 s for read-only, 90 s for mutating (`packages/tools/src/lonora_tools/base.py:15-16`, `:99-104`, applied at `registry.py:494-501`).
- Market binding: reads are open to every agent on every owned account and symbol (`market_binding.py:31-37`, `:118-119`). For a fixed-market agent, mutating tools whose names start with `market_`, `chart_`, `watch_`, `trade_`, `goal_`, `account_` (the full prefix list at `market_binding.py:18`) must stay on the bound pair (`market_binding.py:113-122`). The Personal Agent of this owner is not fixed-market: it has no `trading_account_id` (`production-trace.md` Q6; `fixed_market` at `packages/db/src/lonora_db/agent_binding.py:35-36`), so none of this binding applies to it. Missing `account_id`/`symbol` are filled from the binding (`market_binding.py:64-79`, `:82-94`); case-only differences are aligned (`market_binding.py:44-61`).
- Broker limits (MetaApi): SDK request/connect timeout 20 s, history 30 s, no SDK retries (`metaapi.py:204-207`); account metadata 25 s (`metaapi.py:265`); connect 25 s and synchronisation wait 15 s (`metaapi.py:391-404`); candle history 35 s and at most 1000 bars (`metaapi.py:710-713`); instrument catalogue capped at 2000 (`metaapi.py:511`, `:515-516`); market-data billing cooldown 300 s (`metaapi.py:35`, `:726-728`). Market runtime cache: quote 15 s (`packages/market/src/lonora_market/runtime.py:103`), candles 60 s (`packages/market/src/lonora_market/runtime.py:124`).

| Tool | What it really does | read_only / replay | Exposure | Limits | Definition |
|---|---|---|---|---|---|
| `market_symbols` | Returns the broker's full list of symbol names for one connection. MetaApi: free from synchronised stream, else paid RPC `get_symbols` (`metaapi.py:443-459`). | read | discovery-only | 45 s; no filter argument | `market.py:97-105`, handler `:40-42` |
| `market_instrument` | One contract specification. | read | native (`market`) | 45 s | `market.py:106-113`, handler `:45-48` |
| `market_instruments` | All specifications (up to 2000). | read | discovery-only | 45 s | `market.py:114-120`, handler `:51-53` |
| `market_quote` | Bid/ask + observation time; exempt from the no-progress guard (`poller=True`). | read | native (`market`) | 45 s; 15 s cache | `market.py:121-129`, handler `:56-60` |
| `market_candles` | Up to 1000 OHLC bars (`limit` 1..1000, default 300: `market.py:29`). | read | native (`market`) | 45 s | `market.py:130-137`, handler `:63-72` |
| `market_structure` | Swing pivots and candidate trendlines from closed bars. | read | discovery-only (comment `market.py:147-149`) | 45 s; windows 1..100, lines 1..24 (`market.py:32-37`) | `market.py:138-150`, handler `:75-92` |
| `market_snapshot` | Quote + up to 6 timeframes of trend/structure/ATR/RSI + day/week levels in one call. | read | native (`market`) | 45 s outer; 20 s per inner read (`market_analysis.py:29`, `:117`, `:128`); bars 50..1000 (`:48`) | `market_analysis.py:358-371`, handler `:136-181` |
| `market_sessions` | Session clock from IANA zones; optional broker trading hours. | read | native (`market`) | 45 s; 20 s broker part (`:213`); `at` within 31 days (`:188-189`) | `market_analysis.py:372-384`, handler `:184-200` |
| `economic_calendar_read` | Events from the owner's configured calendar integrations. | read | native (`research`), only when a source exists (`availability`, `:234-238`, `:396`) | 45 s; window back 0..168 h, ahead 0..336 h, limit 1..200 (`:84-86`) | `market_analysis.py:385-397`, handler `:241-279` |
| `market_candles_to_workspace` | Writes bars as CSV into the agent's analytical workspace. | mutating, `replay_safe` | discovery-only; needs workspace (`availability=workspace_available`, `:407`) | 90 s; 20 s broker read (`:309`); refused for helper runs (`docs/market-analysis.md:119-120`) | `market_analysis.py:398-408`, handler `:286-353` |
| `watch_create` | Persists a server-side watch that wakes the agent; never trades. | mutating, `replay_safe` | native (`market`) | 90 s; cooldown >= 30 s, interval >= 5 s (`packages/contracts/src/lonora_contracts/market_watch.py:30-31`) | `market_watch.py:237-244`, handler `:90-145` |
| `watch_list` | Lists this agent's watches. | read, poller | discovery-only | 45 s | `market_watch.py:245-252` |
| `watch_cancel` / `watch_pause` / `watch_resume` | Stop / pause / resume one of the agent's own watches. | mutating, `replay_safe` | discovery-only | 90 s | `market_watch.py:253-274`, `steer` `:172-188` |
| `watch_update` | Moves expiry or level of an own watch; raises an owner notice with Undo (`market_watch.py:221-231`). | mutating, `replay_safe` | discovery-only | 90 s | `market_watch.py:275-282`, handler `:203-232` |
| `chart_open` | Creates a persistent chart configuration; returns an acknowledgment, not a scene. | mutating, `replay_safe` | discovery-only | 90 s; <= 12 indicators, <= 100 annotations (`packages/contracts/src/lonora_contracts/chart.py:26-27`) | `chart.py:43-49`, handler `:11-38` |
| `chart_list` | Up to 200 chart ids/versions. | read | discovery-only | 45 s | `chart_state.py:385-391`, handler `:158-177` |
| `chart_inspect` | Chart config + bounded scene (tail default 60). | read | discovery-only | 45 s | `chart_state.py:392-398`, handler `:147-155` |
| `chart_set_symbol` / `chart_set_timeframe` | Change symbol / timeframe of an existing chart at an inspected version. | mutating, `replay_safe` | discovery-only | 90 s | `chart_state.py:399-412`, handlers `:216-235` |
| `chart_add_indicator` / `chart_remove_indicator` | Add / remove one indicator. | mutating, `replay_safe` | discovery-only | 90 s; indicators `sma, ema, rsi, macd, atr, bollinger`, period 2..500 (`packages/core/src/lonora_core/chart_indicator.py:3-8`) | `chart_state.py:413-426`, handlers `:238-269` |
| `chart_read_indicator` | Indicator values from the stored scene. | read | discovery-only | 45 s | `chart_state.py:427-433`, handler `:272-309` |
| `chart_annotate` | Add/update/delete drawings on the agent's own layer. | mutating, `replay_safe` | discovery-only | 90 s; 1..100 operations (`chart_state.py:320-321`) | `chart_state.py:434-440`, handler `:366-380` |
| `chart_indicator` | Computes an indicator from freshly fetched candles. | read | discovery-only | 45 s; period 2..500 (`chart_indicator.py:15`) | `chart_indicator.py:34-40`, handler `:18-29` |
| `chart_snapshot` | Renders and stores a chart image artifact (semantic SVG/PNG, or browser capture when configured). | mutating, `replay_safe` | native (`market`) | 90 s | `chart_snapshot.py:206-213`, handler `:68-201` |

`symbols.py` and `market_binding.py` define no tools; they are shared helpers (see census).

### 2.1 Description sentences that tell the model to stop, ask, or not do something

| Sentence (verbatim) | Where | Needed for safety or over-caution |
|---|---|---|
| "Use before guessing broker symbols or aliases; suffixes matter. When an immutable trading market is bound, omit account_id and do not ask the owner to repeat the symbol." | `market.py:100-101` | Good instruction, but attached to a tool the model does not see natively. |
| "Read specifications for ONE exact broker symbol from market_symbols." | `market.py:108` | Over-caution in effect: the native tool demands an input that only a non-native tool supplies, and fails with a misleading code otherwise (1.5). |
| "Read historical broker candles without symbol rewriting." | `market.py:132` | Over-caution for a read. Exactness is needed for trades, not for reading bars. |
| "Internal connection_id returned by list_accounts; not the external broker account ID." | `market.py:17` | Neutral; `list_accounts` is native, so this one leads. |
| "Exact supported broker timeframe, e.g. 15m, 1h or 1mn; not M15/H1." | `market.py:27` (also `market_analysis.py:46`) | Neutral; prevents a guess. But the failure code `unsupported_timeframe` carries no list of valid values (`packages/core/src/lonora_core/chart_controller.py:29-32`). |
| "... no trade signal or execution authority." | `market.py:143` | Needed for safety (reads never authorise money movement). |
| "Numbers and labels are evidence, not signals; no execution authority." | `market_analysis.py:363-364` | Needed for safety. |
| "Returns configured=false when no source exists; events are only what sources report." | `market_analysis.py:388-389` | Honest limit; the handler adds guidance "The owner can add one in Integrations." (`market_analysis.py:257-258`), which hands the task to the owner. |
| "It wakes this agent to reassess and never trades." | `market_watch.py:239` | Needed for safety (no shadow trading). |
| "(an expired one needs a later expiry first, through watch_update)" | `market_watch.py:269-270` | OK-LED: names the fixing tool. |
| "If an older chart lacks a creation receipt, list/inspect it rather than treating its current state as the original outcome." | `chart.py:45` | Neutral; names the next tools. |
| "The response confirms applied configuration only; use chart_inspect for current scene/evidence, which may still be initializing." | `chart_state.py:401`, `:408`, `:415`, `:422`, `:436` | Neutral; leads to `chart_inspect`. |
| "Only this Agent’s attributed layer can be changed. An annotation is visual evidence, not an order or trading approval." | `chart_state.py:436` | Needed for safety. |
| "Read the returned artifact with artifact_read(view_image=true) to inspect its actual pixels before claiming visual verification. Saved/delivered images do not prove the user rendered or saw them. ... No execution or trading approval is implied." | `chart_snapshot.py:208` | Honesty rule; the last sentence is needed for safety. ADDED BY CHECKER: same pattern as `market_instrument`: the native `chart_snapshot` tells the model to verify with `artifact_read`, which is eager only for the `research` profile (checked on the loaded registry) and so is not among the 23 native tools of the Personal Agent; it is reachable only through `tool_call`. |
| Capability inventory: "inspect it with tool_environment first when you do not know its input schema, and before claiming an ability is absent." | `registry.py:428-429` | Good; this is the only text that tells the model to look before saying "I can't". |

---

## 3. Refusal / failure census (a)

### 3.0 Shared layers (referenced by the per-family tables)

**Layer D (dispatch; every tool).**

| Outcome | path:line | What the model sees | Class | Recovery path |
|---|---|---|---|---|
| `tool_arguments_invalid` | `packages/tools/src/lonora_tools/schema.py:45-69`, raised `:72-76` | code + `issues` (path, pydantic type, validator code) + `retryable: true` (`tool_dispatch.py:114-116`) | OK-LED | Fix the fields and call again. |
| `tool_not_allowed` (helper/observe scope) | `registry.py:480`, `:483-484` | bare code; `permission_denied` / `respect_scope` | OWNER-NEEDED (needed for safety: a subagent may not mutate) | The parent run performs the mutation. |
| `tool_read_timeout` / `tool_connection_failure` | `tool_dispatch.py:118-128` | bare code, `safe_to_retry: true`; runtime retries (`tool_block.py:309-328`) | OK-LED | Automatic. |
| `tool_internal_failure` (read) | `tool_dispatch.py:129-138` | bare code, `alternate_route` | RECOVERABLE-NOT-LED | Another read tool for the same data; nothing names one. |
| `tool_execution_uncertain` (mutating tool timed out or threw) | `tool_dispatch.py:118-138` | bare code; treated as ambiguous: `reconcile_before_any_resend` (`environment.py:17-19`, `:42-43`). The route then stays blocked for the rest of the Run (`environment.py:127-131`; ambiguous routes are never expired, `environment.py:119-123`), and a later call with the same arguments and no stored receipt is answered `{"ok": false, "code": "broker_result_ambiguous", ...}` without running (`tool_dispatch.py:70-81`): a broker-trade code for a chart image or a watch | RECOVERABLE-NOT-LED for `chart_*`/`watch_*`/`market_candles_to_workspace`; the `broker_result_ambiguous` wording for a non-financial tool is a BUG-level mislabel | `chart_inspect` / `watch_list` shows whether the effect happened; not named. |
| `tool_route_exhausted` | `tool_dispatch.py:70-81` | code + `alternate_route_or_wait` | RECOVERABLE-NOT-LED | Change arguments or tool. |

**Layer A (connection lookup; every tool that calls `context.brokers.get` or `broker_market`).**

| Outcome | path:line | What the model sees | Class | Recovery path |
|---|---|---|---|---|
| `broker_sessions_not_found` (unknown connection id) | `packages/db/src/lonora_db/transactions.py:92` via `BrokerSessionRepository.kind` (`packages/db/src/lonora_db/broker_sessions.py:37`), called at `packages/adapters/src/lonora_adapters/brokers/base.py:33`; also `packages/market/src/lonora_market/runtime.py:67` | bare code, `inspect_existing_state` | RECOVERABLE-NOT-LED | `list_accounts` (native) gives the right `connection_id`. The input description names it (`market.py:17`), the failure does not. |
| `broker_disabled` | `packages/adapters/src/lonora_adapters/brokers/base.py:36-37`; `packages/market/src/lonora_market/runtime.py:68-69` | bare code, `alternate_route` | OWNER-NEEDED | The owner re-enables the connection. UNSURE whether an owner-action card for this exists; none is in these families. |
| `broker_secret_required` | `packages/adapters/src/lonora_adapters/brokers/base.py:50-51` | bare code | OWNER-NEEDED | Owner supplies the broker token through the connection form. |
| `broker_connection_unavailable` (manager closed) | `packages/adapters/src/lonora_adapters/brokers/base.py:27-28` | transient, auto-retry | OK-LED | Automatic. |

**Layer M (MetaApi adapter; every tool that reads the broker).** All from `provider_error`, `packages/adapters/src/lonora_adapters/brokers/metaapi.py:39-82`, unless stated.

| Outcome | path:line | What the model sees | Class | Recovery path |
|---|---|---|---|---|
| `broker_account_not_found` for a symbol 404 on stages `rpc`/`quote`/`instrument`/`symbols` | `metaapi.py:57-58` | bare code identical to a real missing account | **BUG**: the condition ignores the message for every non-candle stage (1.5) | `market_symbols` then retry with the catalog spelling; the code points away from that. |
| `broker_account_not_found` (provisioned account really missing) | `metaapi.py:57-58`, `:264-276` | same bare code | OWNER-NEEDED | Owner reconnects the broker account. |
| `symbol_not_found` (candle stage) | `metaapi.py:59-60` | bare code | RECOVERABLE-NOT-LED | `market_symbols`. |
| `broker_candles_not_found` | `metaapi.py:61` | bare code | RECOVERABLE-NOT-LED | `market_symbols` / another timeframe. |
| `broker_market_data_billing_required` | `metaapi.py:46-51` (5 min cooldown `:726-728`, `:741-746`) | bare code | OWNER-NEEDED | Owner tops up the data provider. Quotes still work (`lonora.md:240`). |
| `broker_credentials_rejected` | `metaapi.py:62-63` | bare code | OWNER-NEEDED | Owner renews the token. |
| `broker_rate_limited` | `metaapi.py:64-65` | bare code, `alternate_route`; not in `TRANSIENT_READ_CODES` (`runtime_failure.py:10-21`) so no auto-retry | RECOVERABLE-NOT-LED | Wait and retry. |
| `broker_connection_timeout` | `metaapi.py:66-72` | transient, auto-retry | OK-LED | Automatic. |
| `broker_candles_timeout` | `metaapi.py:70-72` | bare code, `alternate_route`; not in the transient set although its sibling `broker_candles_unavailable` is | RECOVERABLE-NOT-LED | Retry with a smaller `limit`. |
| `broker_candles_invalid` | `metaapi.py:73-74` | bare code | RECOVERABLE-NOT-LED | Retry / other timeframe. |
| `broker_candles_request_rejected` / `broker_request_rejected` | `metaapi.py:75-79` | bare code | RECOVERABLE-NOT-LED | Correct symbol/timeframe from `market_symbols`. |
| `broker_candles_unavailable` / `broker_connection_unavailable` (catch-all) | `metaapi.py:80-82` | transient, auto-retried (3 attempts in all: 2 automatic retries, then `retry_exhausted`; `environment.py:206-209`) | OK-LED when truly transient; **BUG** for deterministic causes that land here: `raise ValueError("broker_symbol_mismatch")` in `instrument`/`trading_hours` (`metaapi.py:470-471`, `:492-493`) and normaliser `ValueError`s become "connection unavailable" and are retried pointlessly | For the mismatch case: `market_symbols`. |
| `broker_account_undeployed` / `broker_account_not_ready` | `metaapi.py:370-379` | bare code | OWNER-NEEDED (code comment: "Do not silently redeploy an owner-stopped provider account." `:371`) | Owner redeploys; or wait if `not_ready`. |
| `broker_connection_closed` | `metaapi.py:348-349` | bare code | RECOVERABLE-NOT-LED | Retry (a new adapter is built on the next `get`, `packages/adapters/src/lonora_adapters/brokers/base.py:38-42`). |
| `broker_candles_mismatch` | `metaapi.py:714-719` | bare code | DEAD-END (broker returned other data than asked) | None. |
| `broker_symbol_mismatch` (provider wrapper) | `packages/core/src/lonora_core/trading_run_market.py:4-7` via `packages/market/src/lonora_market/provider.py:16`, `:23` | bare code | RECOVERABLE-NOT-LED | `market_symbols`. |

**Layer S (simulation broker).**

| Outcome | path:line | Class | Recovery path |
|---|---|---|---|
| `simulation_snapshot_required` | `packages/adapters/src/lonora_adapters/brokers/simulation.py:34-35` | OWNER-NEEDED (demo data must be imported) | Owner/operator imports a snapshot. |
| `broker_instrument_unavailable` | `simulation.py:41-45` | RECOVERABLE-NOT-LED | `market_symbols`. Note: third different code for "unknown symbol". |
| `quote_unavailable` | `simulation.py:62-65` | RECOVERABLE-NOT-LED | `market_symbols`. Fourth code for "unknown symbol". |
| empty candle list for an unknown symbol (no error) | `simulation.py:84-86` | RECOVERABLE-NOT-LED (silent) | `market_symbols`. |

Unknown-symbol codes across layers: `symbol_not_found`, `symbol_ambiguous`, `broker_account_not_found` (mislabel), `broker_candles_not_found`, `broker_instrument_unavailable`, `quote_unavailable`, `broker_symbol_mismatch`, `broker_symbol_not_found` (unused, `packages/market/src/lonora_market/instruments.py:8`). Unknown-connection codes: `broker_sessions_not_found` (`transactions.py:92`), `broker_connection_not_found` (`transactions.py:116`, `agents.py:108`), plus the mislabelled `broker_account_not_found`.

### 3.1 Family MARKET (`market.py`, `market_analysis.py`, `symbols.py`)

Every row also inherits layers D, A, M/S.

| Tool | Outcome | path:line | What the model sees (hint?) | Class | Recovery path |
|---|---|---|---|---|---|
| `market_symbols` | any provider 404 -> `broker_account_not_found` | `metaapi.py:452-459`, `:57-58` | bare code, no hint | OWNER-NEEDED (checker reclassified from BUG: `get_symbols` takes no symbol, `metaapi.py:457`, so a 404 there cannot be a symbol 404 and the account label is plausibly right) | Owner reconnects; `list_accounts`. |
| `market_symbols` | success with whole catalog, no filter | `market.py:40-42`, `:15-18` | list of names only | RECOVERABLE-NOT-LED (the model must match "gold" itself; no server match although `instrument_names.py:21` knows it) | Model scans list. |
| `market_instrument` | wrong symbol passed through, then `broker_account_not_found` | `market.py:47`, `symbols.py:32-35`, `metaapi.py:461-474`, `:57-58` | bare code, no hint | BUG | `market_symbols`. |
| `market_instrument` | case-mismatch spec -> `broker_connection_unavailable` + 2 automatic retries | `metaapi.py:470-474`, `:80-82` | transient-looking | BUG (layer M) | `market_symbols`. |
| `market_instruments` | provider failure | `metaapi.py:498-528` | bare code | per layer M | Prefer `market_symbols` + `market_instrument`. |
| `market_quote` | wrong symbol -> `broker_account_not_found` | `market.py:58`, `metaapi.py:698-701`, `:57-58` | bare code | BUG | `market_symbols`. |
| `market_quote` | `broker_symbol_mismatch` | `provider.py:15-17` | bare code | RECOVERABLE-NOT-LED | `market_symbols`. |
| `market_candles` | `unsupported_timeframe` | `provider.py:20`, `chart_controller.py:29-32` | bare code; valid list not returned (it is `chart_controller.py:4-26`) | RECOVERABLE-NOT-LED | Use `15m`/`1h` style from the schema description (`market.py:27`). |
| `market_candles` | `symbol_not_found` / `broker_candles_not_found` | `metaapi.py:59-61` | bare code | RECOVERABLE-NOT-LED | `market_symbols`. |
| `market_candles` | empty list, `ok: true` | `market.py:66-72` | `{"candles": []}` no reason | RECOVERABLE-NOT-LED | `market_symbols` / other timeframe. |
| `market_structure` | `symbol_not_found` / `symbol_ambiguous` | `market.py:78`, `symbols.py:15` | bare code; catalog was in hand | RECOVERABLE-NOT-LED | `market_symbols`. |
| `market_structure` | catalog unreadable: provider error re-raised, or `broker_symbols_unavailable` | `symbols.py:22-28` | bare code | RECOVERABLE-NOT-LED | Retry; `market_snapshot`. |
| `market_structure` | `unsupported_timeframe` | `market.py:76` | bare code | RECOVERABLE-NOT-LED | Fix timeframe. |
| `market_structure` | `market_candles_stale` / `market_candles_receive_stale` whenever the last bar is older than 2 x timeframe (closed market, weekend) | `packages/market/src/lonora_market/structure.py:244`, `packages/market/src/lonora_market/health.py:84-85`, `:203`, `:215-222`, `packages/contracts/src/lonora_contracts/market_health.py:25-26` | bare code, `alternate_route` (not in the stale set at `environment.py:48`) | RECOVERABLE-NOT-LED (intended per `docs/market-structure.md:28-29`, but the tool is unusable for intraday timeframes while the market is closed and nothing says so) | `market_snapshot` measures a stale series and marks it `freshness: stale` (`docs/market-analysis.md:31`). |
| `market_structure` | `market_candles_unavailable` (no bars) | `health.py:168-169` | transient code -> 2 automatic retries (3 attempts) | RECOVERABLE-NOT-LED (and wrongly treated as temporary: an unknown or empty series is auto-retried) | `market_symbols` / other timeframe. |
| `market_structure` | degraded series: `mixed_candle_series`, `market_candle_timestamp_invalid`, `duplicate_candle_timestamp`, `market_candle_out_of_order`, `market_candle_invalid`, `market_candle_timestamp_future` | `health.py:170-187`, `structure.py:245-246` | bare code | DEAD-END (broker data defect) | None. |
| `market_structure` | `market_structure_*_invalid`, `market_structure_candle_limit`, `market_structure_scope_invalid` | `structure.py:222-235`, `:277-287` | bare code | OK-LED in practice (schema bounds at `market.py:32-37` reject first with `issues`) | Fix arguments. |
| `market_snapshot` | `symbol_not_found` / `symbol_ambiguous` | `market_analysis.py:140`, `symbols.py:15` | bare code; catalog was in hand | RECOVERABLE-NOT-LED | `market_symbols`. |
| `market_snapshot` | instrument read fails -> whole snapshot fails | `market_analysis.py:141` (not wrapped) | bare code | RECOVERABLE-NOT-LED | `market_quote` + `market_candles` separately. |
| `market_snapshot` | per-part failure inside `ok: true`: `{"available": false, "reason": "<code>"}` incl. `market_history_timeout`, `market_quote_timeout`, `insufficient_closed_bars` | `market_analysis.py:119-122`, `:130-133`; `packages/market/src/lonora_market/snapshot.py:115-116`, `:125-136`, `:229-233`, `:287-288` | a code string as `reason`, no hint | RECOVERABLE-NOT-LED | Retry that timeframe with `market_candles`. |
| `market_snapshot` | `unsupported_timeframe`; `market_snapshot_timestamp_invalid` | `market_analysis.py:138`; `packages/market/src/lonora_market/snapshot.py:264-267` | bare code | RECOVERABLE-NOT-LED / internal | Fix timeframe. |
| `market_sessions` | `market_session_timestamp_invalid`, `market_session_symbol_requires_account` | `market_analysis.py:64-70` | via `issues` | OK-LED | Add `account_id` (from `list_accounts`). |
| `market_sessions` | `market_session_timestamp_out_of_range` | `market_analysis.py:188-189` | bare code | RECOVERABLE-NOT-LED | `at` within 31 days. |
| `market_sessions` | `symbol_not_found` / `symbol_ambiguous` fails the whole call (clock included) | `market_analysis.py:219-221` | bare code | RECOVERABLE-NOT-LED. Doc says this is "so the model can correct it" (`docs/market-analysis.md:81-83`); the code gives it nothing to correct with. | `market_symbols`; or call without symbol for the clock. |
| `market_sessions` | broker hours `state: "unknown"` with `reason` = `broker_hours_not_exposed`, `broker_hours_timeout`, `broker_connection_failure`, `broker_hours_failed`, any broker code, or `no_instrument_requested` | `market_analysis.py:192-196`, `:216-231` | `ok: true`, code as `reason` | DEAD-END for `broker_hours_not_exposed` (adapter lacks the capability); RECOVERABLE-NOT-LED for the rest (retry) | Session clock still usable. |
| `market_sessions` | `timezone_database_unavailable` | `packages/market/src/lonora_market/sessions.py:55` | bare code | DEAD-END (server install) | None. |
| `economic_calendar_read` | `configured: false`, `reason: economic_calendar_not_configured` + guidance "The owner can add one in Integrations." | `market_analysis.py:249-259` | English guidance string in result | OWNER-NEEDED today; DEAD-END from the agent side: "There is still no built-in calendar provider" (`docs/market-analysis.md:194-195`) | Web search for events (another family). |
| `economic_calendar_read` | `reason: calendar_source_unavailable`; per-source `unavailable` | `market_analysis.py:269-272` | `ok: true`, code as reason | RECOVERABLE-NOT-LED | Retry later / web search. |
| `market_candles_to_workspace` | `invalid_candle_range` | `market_analysis.py:103-109` | via `issues` | OK-LED | Fix range. |
| `market_candles_to_workspace` | `revision` required: "Current workspace revision from workspace_inspect." | `market_analysis.py:90` | schema field | OK-LED (names the tool) but a forced extra call | `workspace_inspect`. |
| `market_candles_to_workspace` | `symbol_not_found` / `symbol_ambiguous` | `market_analysis.py:305` | bare code | RECOVERABLE-NOT-LED | `market_symbols`. |
| `market_candles_to_workspace` | `market_history_timeout` | `market_analysis.py:311-312` | bare code | RECOVERABLE-NOT-LED | Smaller `limit`. |
| `market_candles_to_workspace` | health code when degraded/unavailable | `market_analysis.py:321-322` | bare code | per `market_structure` rows | |
| `market_candles_to_workspace` | `market_candles_window_empty` | `market_analysis.py:338-339` | bare code | RECOVERABLE-NOT-LED | Widen `start`/`end` or set `include_forming`. |
| `market_candles_to_workspace` | `workspace_unconfigured`, `workspace_revision_conflict`, `workspace_busy`, quotas | `packages/tools/src/lonora_tools/workspace.py:56`; `packages/agent-runtime/src/lonora_agent/workspace_access.py:121-131` | bare code | workspace family (not mapped here); `workspace_unconfigured` is DEAD-END for the agent | `workspace_inspect` for a fresh revision. |

`symbols.py` helper outcomes: `symbol_not_found` / `symbol_ambiguous` (`symbols.py:15`), `broker_symbols_unavailable` (`symbols.py:28`); already counted under the tools that surface them. `restriction_symbol` (`symbols.py:38-56`) raises the same two codes for trade restrictions when the catalog is readable; that refusal is **needed for safety** ("a restriction on a spelling the broker does not use would never match a trade", `docs/account-authority.md:215-216`).

### 3.2 Family WATCH (`market_watch.py`) and BINDING guard (`market_binding.py`)

Inherits layer D. `watch_create` does not touch the broker at creation unless a fixed agent passes `position_id` (`market_binding.py:133-140`).

| Tool | Outcome | path:line | What the model sees | Class | Recovery path |
|---|---|---|---|---|---|
| `watch_create` | validator codes: `watch_dynamic_detector_required`, `relationship_requires_distinct_symbols`, `watch_expiry_timezone_required`, `goal_and_step_required_together`, `invalid_watch_level`, `watch_account_required`, `watch_symbol_required`, `watch_price_required`, `watch_calendar_required`, `watch_position_required`, `watch_account_metric_invalid`, `watch_position_metric_invalid` | `packages/contracts/src/lonora_contracts/market_watch.py:45-89` | `issues[].code` | OK-LED | Fix fields. |
| `watch_create` | `broker_connection_not_found` (unknown `account_id`) | `packages/db/src/lonora_db/transactions.py:111-116` | bare code (a different code from the same mistake in read tools) | RECOVERABLE-NOT-LED | `list_accounts`. |
| `watch_create` | **wrong symbol accepted**: no catalog check anywhere on create | `market_watch.py:90-145`; `packages/db/src/lonora_db/market_watches.py:55-92`; only the account is checked (`transactions.py:111-116`) | `ok: true` with the stored watch | BUG (silent): a watch on `XAUUSD` for an `XAUUSDm` account is stored and can never fire; the failure is only recorded later in watch health (`packages/market/src/lonora_market/watchers.py:517-538`). UNSURE whether the agent is woken about an unavailable watch. | `market_symbols` before creating; `watch_list` to see health. |
| `watch_create` | `calendar_integration_not_found` | `market_watches.py:27-34` | bare code | RECOVERABLE-NOT-LED | `economic_calendar_read` returns `integration_id` (`docs/market-analysis.md:96-97`). |
| `watch_create` | `goal_run_mismatch`; goal not owned | `market_watches.py:68-71` | bare code | RECOVERABLE-NOT-LED | `goal_list` (another family). |
| `watch_create` (fixed agent) | `agent_trading_account_mismatch` / `agent_trading_symbol_mismatch` / `agent_trading_binding_invalid` | `market_binding.py:122`; `packages/db/src/lonora_db/agent_binding.py:79-84` | bare code, `respect_scope` | OWNER-NEEDED; **needed for safety** (mutations stay on the bound pair) | Owner uses an agent bound to that market. |
| `watch_create` (fixed agent, `position_id`) | `position_not_found` | `market_binding.py:133-139` | bare code | RECOVERABLE-NOT-LED | `account_read` (native) lists positions. |
| `watch_cancel` / `watch_pause` / `watch_resume` / `watch_update` | `market_watches_not_found` (also for another agent's watch) | `market_watches.py:115-125` | bare code | RECOVERABLE-NOT-LED; hiding other agents' watches is deliberate (`:118-120`) | `watch_list`. |
| `watch_resume` | `watch_expired` | `market_watches.py:182-184` | bare code; the tool description names the fix (`market_watch.py:269-270`) | OK-LED | `watch_update` with a later expiry. |
| `watch_resume` | `work_paused_by_owner` | `packages/db/src/lonora_db/supervision.py:440-441` | bare code | OWNER-NEEDED; **needed for safety** (an owner pause is lifted only by the owner) | Owner resumes. |
| `watch_resume` | `work_paused_by_supervisor` | `supervision.py:444-445` | bare code | OWNER-NEEDED (or the supervisor) | Ask supervisor/owner. |
| `watch_update` | `watch_expiry_in_past` | `market_watches.py:213-215` | bare code | RECOVERABLE-NOT-LED | Later `expires_at`. |
| `watch_update` | `watch_update_invalid` | `market_watches.py:219-222` | bare code; the pydantic reason is dropped | RECOVERABLE-NOT-LED | Fix `level`. |
| `watch_list` | none specific | `market_watch.py:148-157` | list incl. state/health codes | - | - |
| guard (any `chart_*`/`watch_*`/`goal_*` mutation by a fixed agent) | `cloud_charts_not_found`, `goal_not_found` | `market_binding.py:123-132` | bare code | RECOVERABLE-NOT-LED | `chart_list`, `goal_list`. |

ADDED BY CHECKER (watch family, matches the trace): `watch_create` with no `dedupe_key` and the same condition as a live watch of this agent returns that watch with `"deduplicated": true` instead of creating one (`packages/tools/src/lonora_tools/market_watch.py:103-107`, `identical_watch` at `:55-60`). This is why the third `watch_create` in run ddae66ad returned the same id 6050e419 and added no row (`production-trace.md` Part 4 #69-#70). With a `dedupe_key` whose condition changed, the old watch is disabled with `state.code: "watch_replaced"` and a new one is created (`market_watch.py:108-118`). Neither path is a cancel; `watch_cancel`, the tool that cancels, is discovery-only (section 2 table), and the trace shows it was never called. Cause only; the watch visibility fix belongs to another session.

### 3.3 Family CHART (`chart.py`, `chart_state.py`, `chart_indicator.py`, `chart_snapshot.py`)

Inherits layer D; broker layers apply where the scene or candles are read.

| Tool | Outcome | path:line | What the model sees | Class | Recovery path |
|---|---|---|---|---|---|
| `chart_open` | `invalid_chart_symbol`, annotation validators | `packages/contracts/src/lonora_contracts/chart.py:29-35` | `issues` | OK-LED | Fix fields. |
| `chart_open` | `unsupported_timeframe` | `packages/contracts/src/lonora_contracts/chart.py:31` via `chart_controller.py:29-32` | bare code | RECOVERABLE-NOT-LED | Fix timeframe. |
| `chart_open` | `broker_connection_not_found` | `transactions.py:111-116` | bare code | RECOVERABLE-NOT-LED | `list_accounts`. |
| `chart_open` | **wrong symbol accepted**: the command path stores the chart and returns an acknowledgment without reading the broker | `chart.py:11-38`; `packages/charts/src/lonora_charts/state.py:201-210` | `ok: true`, `requires_scene_inspection: true` (`state.py:97-102`) | RECOVERABLE-NOT-LED (checker reclassified from BUG: acknowledgment-only is the documented design, the result flags `requires_scene_inspection` and the description says to use `chart_inspect`, `chart.py:45`; what is not led is the symbol correction once `chart_inspect` shows the scene code) | `market_symbols` first; `chart_inspect` reveals it. |
| `chart_open` | `chart_command_scope_mismatch`, `chart_command_identity_conflict`, `chart_creation_receipt_missing` | `state.py:74`, `:82`, `:186`, `:199` | bare code | RECOVERABLE-NOT-LED (`chart_creation_receipt_missing` is explained in the description, `chart.py:45`) | `chart_list` / `chart_inspect`. |
| `chart_open` etc. (fixed agent) | `agent_trading_*_mismatch` | `market_binding.py:122`, `:126-127` | bare code | OWNER-NEEDED; **needed for safety** by current design (`docs/market-analysis.md:145-149`), though a chart moves no money | Agent bound to that market. |
| `chart_list` | none specific | `chart_state.py:158-177` | - | - | - |
| `chart_inspect` | `cloud_charts_not_found` | `transactions.py:92` via `packages/db/src/lonora_db/cloud_charts.py:14`, called at `state.py:155` | bare code | RECOVERABLE-NOT-LED | `chart_list`. |
| `chart_inspect` | scene failed: `ok: true`, `scene: null`, top-level `code` = `chart_initializing`, `chart_data_unavailable`, or whatever the refresh hit (`symbol_not_found`, `broker_account_not_found`, `broker_market_data_billing_required`, `chart_refresh_unavailable`, ...) | `state.py:136-161`; code recorded at `packages/charts/src/lonora_charts/runtime.py:100-108`, `:188`; `packages/charts/src/lonora_charts/controller.py:22-23` | a success-shaped result carrying a failure code; no hint | RECOVERABLE-NOT-LED | `market_symbols` + `chart_set_symbol`, or retry later. |
| `chart_set_symbol` / `chart_set_timeframe` / `chart_add_indicator` / `chart_remove_indicator` / `chart_annotate` | `version_conflict` | `chart_state.py:180-183`; `state.py:245-246` | bare code, `reload_authoritative_state` (`environment.py:46-47`) | OK-LED | `chart_inspect` for the version. |
| same | `cloud_charts_not_found` | `transactions.py:92` | bare code | RECOVERABLE-NOT-LED | `chart_list`. |
| `chart_set_symbol` | wrong symbol accepted, as `chart_open` | `chart_state.py:216-224`; `state.py:250-257` | `ok: true` acknowledgment | RECOVERABLE-NOT-LED (checker reclassified from BUG, same reason as `chart_open`; the description says to use `chart_inspect`, `chart_state.py:401`) | `market_symbols` first. |
| `chart_set_timeframe` | `unsupported_timeframe` | `packages/contracts/src/lonora_contracts/chart.py:31` | bare code | RECOVERABLE-NOT-LED | Fix timeframe. |
| `chart_add_indicator` | `unsupported_indicator` | `chart_state.py:246`; `packages/core/src/lonora_core/chart_indicator.py:6-8` | bare code; supported list (`packages/core/src/lonora_core/chart_indicator.py:3`) not returned and not in the tool description (`chart_state.py:415`) | RECOVERABLE-NOT-LED | Use sma/ema/rsi/macd/atr/bollinger. |
| `chart_add_indicator` | `chart_indicator_already_exists` | `chart_state.py:247-248` | bare code | OK-LED (the goal state already holds) | None needed. |
| `chart_remove_indicator` / `chart_read_indicator` | `chart_indicator_not_found` | `chart_state.py:266-267`, `:290-291` | bare code | RECOVERABLE-NOT-LED | `chart_inspect` lists indicators. |
| `chart_read_indicator` | `chart_scene_unavailable` | `chart_state.py:278-280` | bare code (the underlying scene code is dropped) | RECOVERABLE-NOT-LED | `chart_inspect` shows the real code; or `chart_indicator`. |
| `chart_annotate` | `provide_annotation_or_operations` | `chart_state.py:86-87` | `issues` | OK-LED | Fix. |
| `chart_annotate` | `invalid_chart_annotation` (6 raise sites, one code; checker corrected from 7) | `chart_state.py:321`, `:326`, `:339`, `:343`, `:347`; `packages/core/src/lonora_core/chart_annotations.py:153` | bare code; which rule failed is not said | RECOVERABLE-NOT-LED | Re-read schema via `tool_environment`. |
| `chart_annotate` | `chart_annotation_not_found`, `chart_annotation_already_exists`, `chart_annotation_scope_mismatch` | `chart_state.py:333`, `:349`, `:336` | bare code | RECOVERABLE-NOT-LED | `chart_inspect` for ids. |
| `chart_annotate` | `chart_annotation_forbidden` | `packages/core/src/lonora_core/chart_annotations.py:157-169` | bare code | OWNER-NEEDED by design (owner's or another agent's layer) | Add own drawing instead. |
| `chart_indicator` | wrong symbol passed through (no `require_exists`) | `chart_indicator.py:20` | per layer M (`symbol_not_found` / `broker_candles_not_found`) or empty series with `ok: true` | RECOVERABLE-NOT-LED | `market_symbols`. |
| `chart_indicator` | `unsupported_indicator`; `unsupported_timeframe` | `packages/charts/src/lonora_charts/indicators.py:49`; `provider.py:20` | bare code | RECOVERABLE-NOT-LED | Fix name/timeframe. |
| `chart_snapshot` | input validator texts "TradingView capture requires chart_id and PNG format", "Use chart_id or explicit market fields, not both", "Provide chart_id or account_id, symbol and timeframe" | `chart_snapshot.py:36`, `:39`, `:41` | **dropped**: these messages are sentences, and `ToolArgumentsError` keeps only messages matching a snake_case code (`schema.py:64-68`), so the model gets `type: value_error` with no reason | BUG (the helpful text is written but never delivered) | Guess from schema. |
| `chart_snapshot` | explicit-fields mode uses the symbol with no catalog or case handling at all | `chart_snapshot.py:177-178` | per layer M | RECOVERABLE-NOT-LED | `market_symbols`. |
| `chart_snapshot` | `chart_data_unavailable` (< 2 candles or empty scene) | `packages/charts/src/lonora_charts/snapshot.py:10-11`; `packages/charts/src/lonora_charts/scene_snapshot.py:14`; `chart_snapshot.py:126-128` | bare code | RECOVERABLE-NOT-LED | `market_symbols` / other timeframe. |
| `chart_snapshot` | any scene code re-raised as 409 (`chart_initializing`, `symbol_not_found`, ...) | `chart_snapshot.py:121-128` | bare code | RECOVERABLE-NOT-LED | `chart_inspect`, then retry. |
| `chart_snapshot` | `chart_visual_unconfigured`, `chart_visual_runtime_closed`, `chart_visual_busy`, `chart_visual_timeout`, `chart_visual_capture_failed`, `chart_visual_image_invalid`, `chart_visual_invalid_scene` | `chart_snapshot.py:131-132`; `packages/charts/src/lonora_charts/visual.py:125-146`, `:170-266`, `:319-322` | bare code | RECOVERABLE-NOT-LED: the default `renderer=semantic` works without the browser renderer, but the code does not say "retry without renderer=tradingview". `chart_visual_unconfigured` itself is DEAD-END for the TradingView path (operator setting). | Same call with semantic renderer. |
| `chart_snapshot` | `chart_snapshot_too_large`, `chart_snapshot_invalid` | `packages/charts/src/lonora_charts/snapshot.py:12-13`; `packages/charts/src/lonora_charts/snapshot_render.py:15`, `:27`, `:65` | bare code | DEAD-END (internal render) | None. |
| `chart_snapshot` | `artifacts_not_found`, `artifact_nonce_conflict`, `artifact_file_missing`, `artifact_integrity_failed` (replay of a stored artifact) | `chart_snapshot.py:79-100` | bare code | DEAD-END for that call id (replay integrity); a new call works | New call. |
| `chart_snapshot` | `broker_candles_mismatch` | `chart_snapshot.py:179-180` | bare code | DEAD-END | None. |

### 3.4 Counts per class per family

Counted mechanically from the tables above: one table row = one count, taken from the first class named in the row's class cell (a row listing several sibling codes counts once; where a row names a second class for a sub-case, that sub-case is not counted separately). Four rows carry no class and are not counted: `market_instruments` (defers to layer M), the `market_candles_to_workspace` health-code row (defers to the `market_structure` rows), `watch_list` and `chart_list` (no specific failure). CHECKER CORRECTION: the first version said five unclassed rows and counted 3 DEAD-END in 3.1; by the stated rule the `market_candles_to_workspace` workspace row names DEAD-END first, so 3.1 has 4 DEAD-END. The checker also reclassified three rows (market_symbols 404: BUG -> OWNER-NEEDED; `chart_open` and `chart_set_symbol` wrong symbol: BUG -> RECOVERABLE-NOT-LED; reasons in the rows). Recounted with a script over the table rows.

| Family / layer | RECOVERABLE-NOT-LED | OWNER-NEEDED | DEAD-END | BUG | OK-LED (outside the four) |
|---|---|---|---|---|---|
| Layer D (dispatch) | 3 | 1 | 0 | 0 | 2 |
| Layer A (connection) | 1 | 2 | 0 | 0 | 1 |
| Layer M (MetaApi) | 8 | 4 | 1 | 1 | 2 (one of them also holds a BUG sub-case) |
| Layer S (simulation) | 3 | 1 | 0 | 0 | 0 |
| MARKET tools (3.1) | 20 | 2 | 4 | 3 | 4 |
| WATCH + binding guard (3.2) | 8 | 3 | 0 | 1 | 2 |
| CHART tools (3.3) | 20 | 2 | 3 | 1 | 4 |
| **Total** | **63** | **15** | **8** | **6** | **15** |

The dominant class is RECOVERABLE-NOT-LED, and in most of those rows the recovery path is one of four reads the agent is always allowed to make: `market_symbols`, `list_accounts`, `chart_inspect`/`chart_list`, `watch_list`.

---

## 4. LEAKS (internal code / identifier / English string reaching the owner)

1. **Bare codes are the whole failure payload** for every tool here (`tool_dispatch.py:113`). Any owner-facing sentence about a failure must be invented by the model from a snake_case token; the gold reply shows the token copied instead. No reply filter for codes was found (1.7).
2. **Codes inside successful results**, which the model is even more likely to quote because the call "worked": `chart_inspect` top-level `code` (`state.py:160`); `market_snapshot` `reason` per timeframe/quote/levels (`packages/market/src/lonora_market/snapshot.py:116`, `:126`, `:230`, `:288`); `market_sessions` `broker_trading_hours.reason` (`market_analysis.py:192-196`, `:231`); `economic_calendar_read` `reason` and the English `guidance` string (`market_analysis.py:252-258`); watch rows carry `state.code` such as `watch_replaced`, `watch_cancelled`, `watch_paused` (`market_watch.py:117`; `market_watches.py:97`).
3. **Wrong owner text for a mislabelled code**: `broker_account_not_found` -> "Broker account not found." in the web client (`apps/web/src/lib/user_error.ts:156-157`); the same code is produced for an unknown symbol (`metaapi.py:57-58`). Chart scene failures publish their code in the event payload (`packages/charts/src/lonora_charts/runtime.py:190-203`, `"code": code` at `:201`), so the chart surface can show that sentence for a symbol typo.
4. **Internal identifiers the tools require or return**: `account_id` is the internal `connection_id` (`market.py:17`); `chart_id`, `version`, `scene_revision` (`chart_state.py:166-173`); `watch_id` (`market_watch.py:160-161`); `integration_id` (`packages/contracts/src/lonora_contracts/market_watch.py:38`). Policy forbids revealing "internal resource IDs, connection UUIDs" (`lonora.md:47`), but the model must handle them on every call, so they are one copy-paste from a reply.
5. **English catalog terms required for discovery**: `tool_environment` search asks for "concise English catalog terms" (`registry.py:157`; `packages/tools/src/lonora_tools/environment.py:16`). An Arabic owner request ("ابحث عن اسم الذهب") must be turned into English tool-name vocabulary by the model before it can even find `market_symbols`. CHECKER: confirmed on the loaded registry; `"الذهب"`, `"gold"` and `"XAUUSD"` return no tools at all because of the gate-token rule (`packages/tools/src/lonora_tools/tool_discovery.py:60-73`); see 1.3.
6. **Diagnostic text is kept out**: provider exception text goes only to logs with redaction (`metaapi.py:236-251`; `market_analysis.py:227-230`). No secret or exception text reaches the model from these families. This part is correct and needed for safety (never print secrets).

## 5. TECHNICAL QUESTIONS the contracts push toward the owner

1. **Exact broker symbol.** Every read tool requires it (`market.py:21-22`) and none resolves a common name or a suffix, although the server can (`agents.py:72-91`, `instrument_names.py:21`, `:36-54`). CHECKER CORRECTION (trace): the owner's hint came in two messages, and the agent asked a second question in between. Seq 9 «ضع حرف m» got «محتاج أوضح المقصود من "ضع حرف m"…» from run e09ad476, which called no tool; only after seq 11 «يعني XAUUSDM» did run 10171b1c call `market_instrument("XAUUSDm")` and succeed (`production-trace.md` Part 1 runs e09ad476, 10171b1c; Part 3 seq 9-12). The model could have looked the name up with `market_symbols`. DOWNGRADED from "nothing led it there": the failure result did not lead there (1.2) and the first guess was made without the market chapter, but `lonora.md:212` was in context when the reply was written and the inventory names the tool (1.3); the model did not follow those leads.
2. **Which of several matches.** "If several symbols plausibly match an alias, discover real candidates and ask which one." (`lonora.md:225`). For reads this is a technical question the agent could settle itself (for example by reading each candidate's `market_instrument` and choosing the tradable one for that account type); for a trade the question is needed for safety.
3. **Connection id.** `account_id` must be the internal id from `list_accounts` (`market.py:17`). `list_accounts` is native, so this is led; but three different not-found codes for a wrong id (3.0) make the failure look like three different problems.
4. **Timeframe spelling.** `15m`/`1h`/`1mn`, "not M15/H1" (`market.py:27`). The failure `unsupported_timeframe` returns no list. The server could accept `M15`/`H1` or return the valid set (`chart_controller.py:4-26`).
5. **Indicator names.** `chart_add_indicator` and `chart_indicator` take a free `name: str` (`chart_indicator.py:14`); the valid set is only in code (`packages/core/src/lonora_core/chart_indicator.py:3`) and in the `Watch` contract's `Literal` (`packages/contracts/src/lonora_contracts/market_watch.py:33`). A wrong name gives a bare `unsupported_indicator`.
6. **Chart version and workspace revision.** Every chart edit needs `version` from `chart_inspect` (`chart_state.py:180-183`); `market_candles_to_workspace` needs `revision` from `workspace_inspect` (`market_analysis.py:90`). Both are looked up by the agent, not the owner; they add a forced call but no owner question.
7. **Calendar.** With no calendar source the tool's own guidance is "The owner can add one in Integrations." (`market_analysis.py:257-258`), i.e. the agent is told to hand a setup task to the owner; there is no built-in provider (`docs/market-analysis.md:194-195`).
8. **Bound agents are protected from the symbol question**: "Never ask which pair, account, or symbol, and never ask the owner to repeat or retype it." (`agent_binding.py:14-15`), and the server fills the pair (`market_binding.py:64-79`). The Personal Agent has no binding, so it gets none of this help; it is also the agent the owner talks to most. Confirmed by trace: the only agent is role `personal` with `trading_account_id null, trading_symbol null` (`production-trace.md` Q6).

## 6. Doc vs code disagreements (code wins)

1. `docs/market-analysis.md:81-83`: "Only an unknown or ambiguous symbol (`symbol_not_found`, `symbol_ambiguous`) fails the call, so the model can correct it." Code: the call does fail with those codes (`market_analysis.py:219-221`), but the model receives only the code (`tool_dispatch.py:113`); nothing in the result lets it correct the symbol. The stated purpose is not implemented.
2. `docs/market-analysis.md:22-24`: "A timeframe that cannot be read is reported as `available: false` with its error code; the rest of the snapshot still returns." Code: true for quote and candle reads (`market_analysis.py:119-122`, `:130-133`), but the catalog check and the instrument read before them are not wrapped (`market_analysis.py:139-141`), so an unreadable catalog (`symbols.py:22-24`) or a failed specification read fails the entire snapshot.
3. `packages/agent-runtime/resources/system/lonora.md:239`: "A truly unknown symbol is not a generic connection failure." Code: on MetaApi an unknown symbol in `market_quote` / `market_instrument` is reported as `broker_account_not_found` (`metaapi.py:57-58`), and a case-mismatched specification as `broker_connection_unavailable` (`metaapi.py:470-474`, `:80-82`).
4. `market.py:108` ("ONE exact broker symbol from market_symbols") and `lonora.md:212` ("Use market_symbols to discover exact symbols before guessing aliases.") assume the model has `market_symbols`. Code: it is not in the native set (`market.py:97-105` has no `eager`; verified against the loaded registry) and the chapter holding `lonora.md:212` is shown only after a market tool was already called (`system_policy.py:126`, `:134-140`). (Checker precision: in the gold run that chapter was present from the second market call on, i.e. before the reply was written; see 1.3.)
5. `packages/agent-runtime/resources/prompts/trading_context.md:5` describes the gold-suffix procedure. Code: no loader references this file (`packages/agent-runtime/src/lonora_agent/skills/loader.py:20-24`; grep of `load_prompt(` callers), so it has no effect.
6. `docs/market-structure.md:28-29` ("A stale ... series fails explicitly") matches code (`structure.py:244`, `health.py:84-85`, `:220-222`). Noted because the consequence (the tool refuses intraday timeframes whenever the market is closed) is not stated in the doc or in the tool description (`market.py:140-143`).

## 7. Other stop mechanisms found in these families

- **Different behaviour for the same wrong symbol across sibling tools**: strict catalog check (`market.py:78`; `market_analysis.py:140`, `:215`, `:305`) vs pass-through (`market.py:47`, `:58`, `:65`; `chart_indicator.py:20`) vs no check at all (`chart_snapshot.py:177-178`; `chart.py:11-38`; `chart_state.py:216-224`; `market_watch.py:90-145`). The model cannot form one rule for "what happens when the symbol is wrong".
- **Catalog read on every call, result discarded**: `canonical_broker_symbol` calls `broker.symbols()` in every quote/instrument/candles/indicator call (`symbols.py:21`), yet on a miss returns nothing from it (`symbols.py:32-35`). The MetaApi comment notes that `get_symbols` costs "500" CPU credits when not served from the stream (`metaapi.py:444-445`).
- **Deterministic failures retried as transient**: `market_candles_unavailable` for an empty series (`health.py:168-169`, in `runtime_failure.py:10-21`) and `broker_connection_unavailable` from a `ValueError` (`metaapi.py:80-82`) trigger two delayed automatic retries, three attempts in all (`tool_block.py:309-328`; retry stops when `failures >= 3`, `environment.py:206-209`; the catalog advertises `"maximum_automatic_retries": 2`, `packages/tools/src/lonora_tools/environment.py:38`) before the model gets control back with `retry_exhausted`.
- **Route exhaustion**: three failures of an identical read block that exact call for the rest of the Run until owner input (`environment.py:127-131`, `:104-124`). After three `XAUUSD` attempts the model is refused locally; the refusal says `alternate_route_or_wait` (`tool_dispatch.py:76-80`) and names no alternate route.
- **A timed-out chart or watch call is treated like an ambiguous trade**: `chart_snapshot` (native, mutating, 90 s) that times out or throws returns `tool_execution_uncertain` (`tool_dispatch.py:118-138`), which is in `AMBIGUOUS` (`environment.py:17-19`). An identical later call is then refused with `broker_result_ambiguous` / `reconcile_before_any_resend` (`tool_dispatch.py:70-81`) unless a stored receipt exists (`tool_dispatch.py:42-54`), and that block does not expire at owner input (`environment.py:119-123`). The reconcile-before-resend rule is needed for safety on trades; applied to an image render it only stops the agent.
- **Possible deadline mismatch**: MetaApi candle history may take 25 s (`metaapi.py:265`) + 35 s (`metaapi.py:710`) while the read dispatch deadline is 45 s (`packages/tools/src/lonora_tools/base.py:15`). UNSURE how often this is hit; when it is, the model sees `tool_read_timeout` (`tool_dispatch.py:118-128`), not a broker code.
- **Unused adapters and resolver**: `resolve_instrument` (`packages/market/src/lonora_market/instruments.py:5-9`), `BrokerMarketAdapter` (`packages/adapters/src/lonora_adapters/market/broker_market.py:5`) and `RecordedMarketAdapter` (`packages/adapters/src/lonora_adapters/market/fake.py:5`) have no non-test callers (grep). They add two more unknown-symbol codes (`broker_symbol_not_found`, `quote_unavailable` at `fake.py:20`) that never reach the model today.

## 8. Refusals in these families that exist for the money-safety rules (keep)

- Mutations by a fixed-market agent stay on its bound account and symbol (`market_binding.py:113-122`; `agent_binding.py:79-84`): needed for safety. (Arguably broader than money safety for charts, but it is the current owner-approved design: `docs/market-analysis.md:145-153`.)
- Reads never grant execution: `execution_scope` note "Reading is open across every owned account and symbol; charts, watches, goals, decisions and trades stay on this bound account and symbol." (`market_binding.py:144-147`): needed for safety.
- A watch "never trades" (`market_watch.py:239`); an annotation "is visual evidence, not an order or trading approval" (`chart_state.py:436`): needed for safety (no shadow trading).
- Exact symbol on restriction creation (`symbols.py:38-56`): needed for safety.
- Agent may not resume work the owner paused (`supervision.py:440-441`): needed for safety.
- Provider exception text never returned to the model (`metaapi.py:236-251`): needed for safety (never print secrets).
- Not redeploying an owner-stopped provider account (`metaapi.py:370-379`): needed for safety.

None of the safety refusals above requires that a read-only symbol lookup return a bare code, that the discovery tool be non-native, or that a symbol 404 be labelled as a missing account.

## Verification log

Independent check of this file against the code at `9f5b1da` (the working branch adds only notes under `docs/research/`, no code change) and against `production-trace.md` / `TIMELINE_CORRECTION.md`. Every cited range was printed with `awk`/`cat -n` and compared with the claim; verbatim quotes were compared character by character; the author's runtime experiments (`classify`, `catalog_symbol`, `symbol_candidates`, `provider_error` per stage) were re-run read-only against the repository's own code and gave the same output.

- Citations opened: about 580 citation references (471 distinct `path:line` / `:line` tokens in the first version), all opened. Almost all support their claim.
- Citations / quotes corrected: 5 (native-set list attributed to the registry for the wrong profiles; `market_analysis.py:368-370` is a source comment, not a description shown to the model; `market_binding.py:18` prefix list is wider than stated; `chart_state.py:436` quote uses a curly apostrophe "Agent’s"; `invalid_chart_annotation` has 6 raise sites, not 7, one of them in `packages/core/src/lonora_core/chart_annotations.py:153`).
- Claims refuted or downgraded (12):
  1. 1.1 UNSURE "could equally be `market_candles`": resolved by the trace; it was `market_snapshot` (site A) and then `market_instrument` (mislabel), after `list_accounts`.
  2. 1.3 native set of 20 tools for `core`+`market`: wrong profile set; the Personal Agent gets `core`+`market`+`coordination`, 23 tools, identical to the trace.
  3. 1.6 "report the blocker" guardrail as a cause in the gold run: refuted; it needs 3 failures of one tool (`tool_guardrails.py:57`), the run had one failure each of two tools.
  4. 1.3/5.1 "nothing led it there" / "the model has not been shown line 212": downgraded; true for the first guess, but the `market` chapter (with `lonora.md:212`) was in context for the second call and the reply (`system_policy.py:134-140`), and the inventory names `market_symbols`.
  5. "auto-retried 3 times" / "up to three delayed retries" (four places): corrected to 2 automatic retries, 3 attempts in all (`environment.py:206-209`).
  6. `market_symbols` 404 -> `broker_account_not_found` as BUG: reclassified OWNER-NEEDED; `get_symbols` carries no symbol, so the account label is plausible there.
  7. `chart_open` wrong symbol accepted as BUG: reclassified RECOVERABLE-NOT-LED; acknowledgment-only is the design and the result flags `requires_scene_inspection` (`packages/charts/src/lonora_charts/state.py:101`).
  8. `chart_set_symbol` wrong symbol accepted as BUG: same reclassification.
  9. 3.4 counts: 3.1 DEAD-END is 4 (not 3) by the file's own rule; unclassed rows are 4 (not 5); totals after the checker's reclassifications are RECOVERABLE-NOT-LED 63, OWNER-NEEDED 15, DEAD-END 8, BUG 6, OK-LED 15 (first version: 61/14/7/9/15; even before reclassification the DEAD-END total was 8, not 7).
  10. 1.7 UNSURE about other reply filters: resolved; wider greps found none, and PR #42's `uncertain_outcome.py` reads structured financial results only (`uncertain_outcome.py:3`).
  11. 1.5 BUG on `metaapi.py:57-58`: kept, but marked UNSURE whether the precedence was deliberate; the effect is confirmed in production.
  12. Section 1 header "No transcript of the incident": superseded by the trace (kept the code mechanism, which matches).
- Absence claims re-checked with two independent searches each: `trading_context.md` is loaded by nothing (`grep load_prompt(` callers; grep of `"prompts"` path joins: only `loader.py:21` and `visual_policy.py:56`, `:79` for other files); `resolve_instrument`, `BrokerMarketAdapter`, `RecordedMarketAdapter` have no non-test callers; no snake_case reply filter exists.
- Added by the checker (also inserted in the body, 5):
  1. `tool_environment` cannot find `market_symbols` from "gold", "XAUUSD", "الذهب", "symbol suffix" or "gold symbol" (all empty), and "find symbol" misses it: the rarest query token must occur in the tool text (`packages/tools/src/lonora_tools/tool_discovery.py:60-73`). The recovery's `schema_tool` route is a dead end for the words the situation suggests (1.3, section 4 item 5).
  2. The owner's hint needed two messages: run e09ad476 answered «ضع حرف m» with a clarification question and no tool call (section 5 item 1).
  3. Native `chart_snapshot` tells the model to verify with `artifact_read`, which is not native for the Personal Agent (eager only for `research`) (2.1).
  4. `watch_create` dedupes an identical live watch and returns the same id (`market_watch.py:103-107`), which explains the third call in run ddae66ad; neither dedupe nor `dedupe_key` replacement is a cancel (3.2 note).
  5. The Personal Agent of this owner is not fixed-market (trace Q6; `agent_binding.py:35-36`), so the binding guards and `BINDING_POLICY` protections in this file do not apply to it (section 2 common rules, section 5 item 8).
