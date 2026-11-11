# Map: tool errors, recovery, and leaks (Part 1.4 + census d)

Repository `/home/user/lonorabot`, HEAD `9f5b1da`. Read-only audit. Every claim cites `path:line` taken from `grep -n` / the Read tool. Counts produced by regex over `packages/` and `apps/` are marked "regex count" and are approximate by construction.

Checked by an independent reviewer against the code and against `production-trace.md` (ground truth). The working tree at check time is commit `3f09572`, which adds only files under `docs/research/` on top of `9f5b1da` (`git diff --stat 9f5b1da HEAD`), so every code line cited here is the code of `9f5b1da`. Corrections are made in place; the list of changes is in "Verification log" at the end.

## 0. Short answers

| Question | Answer |
| --- | --- |
| What does the model see when a tool fails? | `{"ok": false, "code": "<snake_case>", "recovery": {category, next_action, safe_to_retry, schema_tool, attempt, retry_exhausted}}`. No message, no candidates, no tool-specific hint. |
| Is there a central registry of error codes? | No. Codes are ad-hoc string literals at about 1,300 `LonoraError(...)` sites; 723 distinct literal codes with a line-based regex, 728 when calls that put the code on the next line are counted (regex count), plus about 27 sites that build the code at runtime. |
| Is there ONE place that turns internal codes into owner language? | No. On the server there is none for chat replies: the model is the only translator, guided by prose policy. The clients have two parallel mappers (Web, Mobile) that share five tables; they cover REST errors and failed-Run cards, not chat text. |
| Is there a filter that stops a code from appearing in a reply? | No. The only deterministic reply filter removes credentials, UUIDs and private paths (`packages/core/src/lonora_core/public_reply.py:10-25`). `symbol_not_found` passes untouched. |
| Does a failed call tell the model what to do next? | Only as one of 13 generic `next_action` words chosen by `classify` (a free string field, `packages/contracts/src/lonora_contracts/tool_environment.py:29`, not tied to any tool). 634 of 728 literal codes (87%; 631 of 723 with the line-based count) fall into the default `terminal_domain_failure` / `alternate_route`. |
| Who retries? | The runtime retries read-only tools automatically, twice, only for 8 transient codes. Everything else is left to the model, bounded by guardrails. |
| The owner's gold transcript | Confirmed by the production trace (run `1ae9a14c`, `production-trace.md:93-95`, `:243-248`): `list_accounts` ok, then `market_snapshot` with `XAUUSD` → `symbol_not_found`, then `market_instrument` with `XAUUSD` → `broker_account_not_found`; both results carried only `code` + the generic `not_found` / `inspect_existing_state` recovery. The second code is a mis-classification: any broker 404 outside the candles stage is mapped to it, including an unknown symbol (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:57-58`). `symbol_not_found` from `market_snapshot` means the handler had already fetched the account's full symbol list and discarded it (`packages/tools/src/lonora_tools/symbols.py:20-35`). The symbol-discovery tool `market_symbols` is not in the native tool set (`packages/tools/src/lonora_tools/market.py:97-105`), but it is named in the capability inventory sent every round and in `market_instrument`'s own description (4.3). No result carries name candidates. |

---

## 1. How an exception becomes a tool result

### 1.1 The error type

`LonoraError(code, status=400, *, diagnostic_message=None, diagnostic_type=None)` — the whole class is 14 lines (`packages/core/src/lonora_core/user_error.py:1-14`). It has no owner message, no hint field, no severity, no retryable flag. `diagnostic_message` is filled only by broker adapters for logs (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:241-243`) and is never copied into a tool result (see 1.2).

Subclasses: `ToolArgumentsError` (`packages/tools/src/lonora_tools/schema.py:45`), `ModelProviderError` (`packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:102`), `AdmissionBlocked` (`packages/trading/src/lonora_trading/restrictions.py:45`), `RunRetryTooEarly` (`packages/db/src/lonora_db/run_retry.py:29`), `MemoryEditError` / `MemoryOverflow` (`packages/memory/src/lonora_memory/edits.py:69`, `:81`).

### 1.2 The single conversion point

`dispatch_call` in `packages/agent-runtime/src/lonora_agent/tool_dispatch.py` is the one place where a handler outcome becomes a result dict:

| Case | Result | Line |
| --- | --- | --- |
| Handler returned a dict | `{"ok": True, **result}` (a handler's own `"ok": False` wins) | `tool_dispatch.py:109` |
| `LonoraError` | `{"ok": False, "code": error.code}` — nothing else | `tool_dispatch.py:113` |
| `ToolArgumentsError` | adds `issues` (field path + pydantic type + optional machine code) and `"retryable": True` | `tool_dispatch.py:114-116`, `packages/tools/src/lonora_tools/schema.py:54-69` |
| `TimeoutError` / `ConnectionError` on a read-only tool | `tool_read_timeout` / `tool_connection_failure` | `tool_dispatch.py:118-125` |
| Same on a mutating tool | `tool_execution_uncertain` (needed for safety: the effect may have happened) | `tool_dispatch.py:127` |
| Any other exception | `tool_internal_failure` (read) or `tool_execution_uncertain` (mutation); only the exception type is logged. Comment: "Exception content may contain credentials; only the type belongs in diagnostics." (needed for safety) | `tool_dispatch.py:129-138` |
| Route already failed 3 times or is ambiguous | handler not run: `{"ok": False, "code": "tool_route_exhausted" \| "broker_result_ambiguous", "recovery": {"next_action": "alternate_route_or_wait" \| "reconcile_before_any_resend"}}` | `tool_dispatch.py:70-81` |
| Call was in flight when the worker died and is not replay-safe | `{"ok": False, "code": "tool_execution_uncertain"}` (needed for safety) | `tool_dispatch.py:82-95` |
| `stale_lease`, `skill_continuation_unavailable` | re-raised, fail the Run | `tool_dispatch.py:111-112` |

Registry-level refusals raised before the handler: `tool_not_allowed`, `observe_only_execution_forbidden` (`packages/tools/src/lonora_tools/registry.py:480-490`); bridge errors `tool_call_target_invalid`, `tool_call_unresolved`, `tool_call_target_unknown` (`registry.py:217-222`). Dispatch deadline: 45 s for reads, 90 s for mutations, none for financial tools (`packages/tools/src/lonora_tools/base.py:15-16`, `base.py:99-104`; the "never wrapped" rule for financial tools is needed for safety).

### 1.3 The `recovery` block added afterwards

`observe()` runs on every result (`packages/agent-runtime/src/lonora_agent/tool_block.py:300`) and, for a failed one, writes `result["recovery"] = classify(code, tool)` plus `attempt` (`packages/agent-runtime/src/lonora_agent/environment.py:203-210`). `classify` (`environment.py:35-93`) maps a code to one of 13 categories (`packages/contracts/src/lonora_contracts/tool_environment.py:9-24`) and one of 13 `next_action` words:

| Trigger | category / next_action | Line |
| --- | --- | --- |
| `tool_arguments_invalid` | `invalid_tool_arguments` / `inspect_schema_and_repair` | `environment.py:38-39` |
| `tool_result_too_large` | `result_too_large` / `narrow_query` | `environment.py:40-41` |
| ambiguous codes | `ambiguous_mutation` / `reconcile_before_any_resend` (needed for safety) | `environment.py:42-43` |
| 8 transient read codes | `temporary_unavailable` / `inspect_health` | `environment.py:44-45` |
| 3 version codes | `version_conflict` / `reload_authoritative_state` | `environment.py:46-47` |
| 4 stale codes | `stale_state` / `refresh_evidence` | `environment.py:48-49` |
| 3 authorization codes | `authorization_required` / `request_owner_authorization` (needed for safety) | `environment.py:50-55` |
| 9 scope/restriction codes | `permission_denied` / `respect_scope` (needed for safety) | `environment.py:56-69` |
| `risk_*` | `risk_limit_blocked` / `inspect_risk_assessment` (needed for safety) | `environment.py:70-73` |
| `*_unconfigured` + 3 | `not_configured` / `inspect_authorized_alternative` | `environment.py:74-79` |
| `*_not_found` | `not_found` / `inspect_existing_state` | `environment.py:80-81` |
| 4 health codes | `health_blocked` / `wait_for_authoritative_recovery` (needed for safety) | `environment.py:82-88` |
| anything else | `terminal_domain_failure` / `alternate_route` (the default) | `environment.py:36-37` |

Running `classify` over the 728 distinct literal codes (regex count that also catches a code on the line after `LonoraError(`, see 2) gives: 634 default `terminal_domain_failure`/`alternate_route`, 65 `not_found`, 6 `permission_denied`, 6 `not_configured`, 6 `temporary_unavailable`, 5 `risk_limit_blocked`, 2 `authorization_required`, 2 `health_blocked`, 2 `version_conflict`. (The author's line-based count over 723 codes gave 631 default and 4 `temporary_unavailable`.) So 87% of codes tell the model only "alternate_route". Two further `next_action` words exist outside `classify`: `alternate_route_or_wait` (`environment.py:208`, `tool_dispatch.py:79`) and `read_stored_result` (`packages/tools/src/lonora_tools/tool_results.py:52`).

### 1.4 Literal shapes the model sees

Produced by calling the repository's own `observe` / `after_call` / `attach_notice` on a `market_quote` call (no repository file was written).

Success (the handler's dict with `ok` prepended, `tool_dispatch.py:109`):

```json
{"ok": true, "symbol": "XAUUSDm", "bid": 1.0}
```

First failure:

```json
{"ok": false, "code": "symbol_not_found",
 "recovery": {"category": "not_found", "next_action": "inspect_existing_state",
              "safe_to_retry": false, "schema_tool": "tool_environment",
              "attempt": 1, "retry_exhausted": false}}
```

Second identical failure (guardrail warning attached, `tool_block.py:332-334`):

```json
{"ok": false, "code": "symbol_not_found",
 "recovery": {"category": "not_found", "next_action": "inspect_existing_state",
              "safe_to_retry": false, "schema_tool": "tool_environment",
              "attempt": 2, "retry_exhausted": false},
 "runtime_notice": [{"kind": "tool_guardrail", "source": "lonora_runtime",
   "message": "market_quote has failed 2 times with identical arguments. Inspect the error and change strategy instead of retrying it unchanged."}]}
```

Invalid arguments: `{"ok": false, "code": "tool_arguments_invalid", "issues": [{"path": [...], "type": "..."}], "retryable": true, "recovery": {...}}` (`tool_dispatch.py:113-116`).

Guardrail block (handler not run): `{"ok": false, "code": "guardrail_blocked", "executed": false, "guardrail": {action, code, tool, count}, "message": "<English sentence>"}` (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:302-310`).

Oversized result (> 120,000 chars, `tool_block.py:255`): a bounded summary with `"context_notice": "tool_result_too_large"`, `"result_omitted": true`, and `recovery.next_action` `narrow_query` or `read_stored_result` (`environment.py:234-245`, `packages/tools/src/lonora_tools/tool_results.py:47-55`).

Unexecuted sibling call: `{"ok": false, "code": "tool_call_superseded" | "tool_call_not_executed", "reason": "..."}` (`packages/agent-runtime/src/lonora_agent/tool_intent.py:25-31`).

What is absent in every failure shape: a human sentence, the offending argument, a list of valid values, a named next tool. `symbol_not_found` does not say which symbol, on which account, or what names exist.

---

## 2. Inventory of error codes

There is no registry, enum or table of codes anywhere in Python. Codes are string literals at the raise site.

Regex count (`LonoraError\(\s*"[a-z0-9_]+"` over `packages/` and `apps/`, `*.py`):

- 1,311 literal occurrences, 723 distinct codes with a line-based grep; 1,317 occurrences and 728 distinct codes when the code may sit on the next line (checker's re-count with a multi-line regex); 1,347 `LonoraError(` occurrences in total.
- Distinct literal codes per package (multi-line count): db 210, agent-runtime 125, tools 117, trading 94, adapters 76 (71 line-based), apps/api 71, voice 24, market 24, core 21, security 17, auth 17, charts 16, memory 8, adapter-kit 5, gateway 4, providers 3, channels 3, session 2, automation 1.
- About 27 sites build the code at runtime (checker's count of `LonoraError(` whose first argument is not a string literal, excluding the class definition and literals on the next line), so the true set is larger and not enumerable from source: `raise LonoraError(key + "_not_found", 404)` (`packages/db/src/lonora_db/transactions.py:110`), `raise LonoraError(risk.reasons[0], 409)` (`packages/trading/src/lonora_trading/execution.py:384`), `raise LonoraError(quality.reasons[0], 409)` (`execution.py:343`), `raise LonoraError(health.reason_code, 409)` (`packages/tools/src/lonora_tools/market_analysis.py:322`), `raise LonoraError(checked["reason"], 502)` (`packages/tools/src/lonora_tools/feeds.py:138`), `raise LonoraError(str(error), 422)` (`packages/db/src/lonora_db/genui_submit.py:348`, `packages/db/src/lonora_db/trusted_sources.py:135`), `raise LonoraError(message.removeprefix("Value error, "), 422)` (`apps/api/src/lonora_api/routes/routines.py:56`).

Further code sources that are not `LonoraError`:

- Runtime-synthetic codes: `tool_route_exhausted`, `broker_result_ambiguous` (`tool_dispatch.py:73-75`), `tool_execution_uncertain` (`tool_dispatch.py:95`), `tool_read_timeout`, `tool_connection_failure` (`tool_dispatch.py:122-124`), `tool_internal_failure` (`tool_dispatch.py:135`), `guardrail_blocked` (`tool_guardrails.py:306`), `tool_call_superseded` (`tool_intent.py:26`), `tool_failed` as the fallback when a failed result has no code (`environment.py:145`), `runtime_error` for an unexpected Run crash (`packages/agent-runtime/src/lonora_agent/executor.py:315`).
- Handler-returned refusals: 15 `"ok": False` dict literals in `packages/tools/src` (regex count), e.g. `financial_consent_requires_trade_request` (`packages/tools/src/lonora_tools/runtime_control.py:65-67`), `model_not_in_catalog` (`packages/tools/src/lonora_tools/models.py:199-201`).
- Maintenance failures: `failure_code()` returns the `LonoraError` code, `"timeout"`, or `"unexpected_" + <exception class name in snake_case>` (`packages/db/src/lonora_db/item_failures.py:42-48`).
- Broker return codes passed through as the result code, e.g. `code=string_code` such as `TRADE_RETCODE_*` (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:949`).

The only shared code sets are small frozensets used for classification: `TRANSIENT_READ_CODES` (8 codes, `packages/core/src/lonora_core/runtime_failure.py:10-21`), `AMBIGUOUS` (3, `environment.py:17-19`), `QUOTA_CODES` / `RATE_CODES` / `MODEL_CODES` (`runtime_failure.py:27-36`), `SYMBOL_ARGUMENT_ERRORS` (2, `market_analysis.py:32`), `OWNER_ACTIONABLE_CODES` (2, `apps/api/src/lonora_api/errors.py:15`).

---

## 3. Retry behaviour

| Layer | Who | How many | Which codes | Line |
| --- | --- | --- | --- | --- |
| Broker RPC read | adapter | 1 extra attempt after a definitively closed connection; "Never use this helper for a financial mutation." (needed for safety) | closed-connection errors only | `packages/adapters/src/lonora_adapters/brokers/metaapi.py:422-435` |
| Tool read retry | runtime, automatic, model not consulted | 2 retries (delays `2**attempt` s = 2 s, 4 s); the 3rd failure sets `safe_to_retry: false`, `retry_exhausted: true`, `next_action: alternate_route_or_wait` | read-only tool AND code in `TRANSIENT_READ_CODES`: `broker_connection_timeout`, `broker_connection_unavailable`, `broker_candles_unavailable`, `market_quote_unavailable`, `market_candles_unavailable`, `tool_read_timeout`, `tool_connection_failure`, `provider_temporarily_unavailable` | `environment.py:92`, `environment.py:206-209`, `environment.py:219-224`, `tool_block.py:309-328`, `runtime_failure.py:10-21` |
| Mutations | nobody; never retried automatically (needed for safety) | 0 | — | `packages/tools/src/lonora_tools/environment.py:38` |
| Same call, same arguments | runtime refuses the 4th attempt without running it (`tool_route_exhausted`) | 3 failures | any failing code | `environment.py:127-131`, `tool_dispatch.py:70-81` |
| Model-driven retry | the model, after reading `code` + `recovery` | bounded by guardrails (section 5) and 24 model rounds per Run | any | `packages/gateway/src/lonora_gateway/service.py:75`, `packages/agent-runtime/src/lonora_agent/runtime.py:8` |
| Invalid arguments | the model; result carries `"retryable": True` and field issues | bounded as above | `tool_arguments_invalid` | `tool_dispatch.py:114-116` |
| Model provider outage | runtime; backoff profiles conversation 10 s→60 s escalate after 3, work 30 s→900 s after 6, continuous holds after 12 h | per profile | transient provider failures | `packages/agent-runtime/src/lonora_agent/model_recovery.py:58-63`, `model_recovery.py:174-202` |
| Context overflow | runtime compacts and retries, max 3 | 3 | provider context overflow | `model_recovery.py:41-43`, `model_recovery.py:166-173` |

Exhausted read routes are forgotten only at real owner input or an external wake (`environment.py:104-124`; `reset_guardrails` callers `packages/agent-runtime/src/lonora_agent/steering.py:48`, `packages/agent-runtime/src/lonora_agent/loop_restore.py:78`, `:104`).

Code-versus-code mismatch: the tool metadata shown by `tool_environment` says `"safe_automatic_retry": read_only` and `"maximum_automatic_retries": 2 if read_only else 0` for every read-only tool (`packages/tools/src/lonora_tools/environment.py:37-38`), but the runtime retries only when the code is one of the 8 transient codes (`environment.py:92`). A `symbol_not_found`, `tool_internal_failure` or `broker_candles_timeout` on a read is never retried automatically. `docs/tool-execution-runtime.md:236` ("route exhaustion (existing, 3 failures)") matches the code (`environment.py:129`).

---

## 4. Hints: which errors carry a next step

### 4.1 Exception path (the large majority)

A raised `LonoraError` that reaches dispatch yields only `code` plus the generic `recovery` block (1.3). No raise site can attach a hint, candidates or a next tool that survives dispatch, because the base class has no such field (`user_error.py:1-14`) and the conversion copies only `error.code` (`tool_dispatch.py:113`). At dispatch the single exception is `ToolArgumentsError.issues` (`schema.py:50-69`). Correction: subclasses can carry details, and one handler converts them itself before dispatch: `memory_write` catches `MemoryEditError` / `MemoryOverflow` and returns their `result()` with `operation_index` and details (`packages/tools/src/lonora_tools/memory.py:136-138`, `packages/memory/src/lonora_memory/edits.py:77-78`), and turns `version_conflict` into the current version and size (`memory.py:139-153`). The pattern (catch a typed error in the handler, return a dict with details) therefore exists in the codebase; the market tools do not use it.

`packages/tools/src` alone has 194 `raise LonoraError(` sites (regex count) against the hint-carrying returns listed below. Estimated share of tool failures that carry a tool-specific hint: roughly 10 of about 200 failure sites in the tools package, i.e. about 95% carry none; across all 1,300 raise sites the share with none is above 99%.

### 4.2 Every place that does carry a hint

All are dicts returned by handlers, not exceptions.

| Site | Field | Text (verbatim, shortened) | Line |
| --- | --- | --- | --- |
| `agent_create`, ambiguous market | `candidates` + `recovery` | "Ask the owner one focused question (wait_for_input) naming these choices, then call agent_create again with the chosen account_id and market." | `packages/tools/src/lonora_tools/agents.py:261-266` |
| `agent_create`, agent exists | `recovery` | "Use this agent (peer_send) instead of creating another one." | `agents.py:303` |
| `agent_create`, model not allowed (added by checker) | `configured_models` (no prose) | — | `agents.py:276-280` |
| `memory_write`, rejected edit / too large / version conflict (added by checker) | `operation_index` + details; `version`, `chars`, `profile_version` | — | `memory.py:136-153` |
| model change, unknown model | `closest`, `allowed_models`, `recovery` | "Nothing changed. Retry with the exact provider and model of one of these, or find others with model_list." | `packages/tools/src/lonora_tools/models.py:199-209` |
| model change, provider not connected | `recovery` | "Nothing changed. The owner adds this provider's key in Model settings; until then choose one of the allowed models." | `models.py:218-223` |
| `wait_for_input` used for trade consent | `next_tool`, `guidance` | "An order or close is trade_execute. …" (needed for safety) | `packages/tools/src/lonora_tools/runtime_control.py:65-72` |
| `wait_for_input` with private wording | `guidance` | "Ask naturally in the owner's language without private identifiers, credentials or filesystem paths. …" | `runtime_control.py:78-82` |
| trade while trading not started | `recovery` | "Say in one line that trading has not been started and that the owner's one tap on the card starts it; ask again after the tap." (needed for safety) | `packages/tools/src/lonora_tools/trade.py:228-237` |
| owner profile write without owner message | `recovery` | "Nothing was saved. …" | `packages/tools/src/lonora_tools/memory.py:94-99` |
| incoming call without device | `recovery` | "Nothing was changed. A call needs a device the owner enrolled with a passkey; ask the owner to enroll one, or reach the owner by message." | `memory.py:189-194` |
| reach-me channel | `recovery` | "The owner asked to be messaged instead of called: …" | `packages/tools/src/lonora_tools/incoming_call.py:19-26`, `:83` |
| consult budget | `recovery.next_action` | `decide_with_current_evidence` | `packages/tools/src/lonora_tools/consult.py:110-115` |
| success-side guidance | `guidance` | `list_accounts` (`packages/tools/src/lonora_tools/account.py:63-65`), capabilities (`packages/tools/src/lonora_tools/capabilities.py:302-304`), feeds (`packages/tools/src/lonora_tools/feeds.py:117-118`, `:159-160`), calendar (`market_analysis.py:257`), MCP (`packages/tools/src/lonora_tools/mcp.py:209`, `:264`) | — |

### 4.3 The symbol case specifically

- A suffix-aware candidate finder exists: `symbol_candidates(names, symbol)` returns "every name that only adds a broker suffix" (`agents.py:72-91`). It is used only by `resolve_market` for `agent_create` (`agents.py:94-129`). For input `XAUUSD` and a catalog containing `XAUUSDm` it would return `["XAUUSDm"]` (lower-case alphabetic suffix rule, `agents.py:87-90`).
- The same suffix rule exists a second time, with a server table that already names gold: `INSTRUMENT_NAMES` maps `XAUUSD` to «الذهب» / "Gold" and `instrument_entry` accepts a broker suffix such as `XAUUSDm` (`packages/contracts/src/lonora_contracts/instrument_names.py:20-21`, `:46-53`; its docstring names `XAUUSDm` at `:4-5`). It is used only for generated-UI labels (`packages/agent-runtime/src/lonora_agent/genui_compile.py:32`, `packages/contracts/src/lonora_contracts/genui_intents.py:17`), not by any market read tool. (Added by checker.)
- The market read tools do not use either. Their resolver `catalog_symbol` accepts only an exact or case-only match and otherwise raises `symbol_not_found` with nothing attached (`packages/tools/src/lonora_tools/symbols.py:6-15`).
- In the gold run this matters more than "no candidates": `market_snapshot` calls `canonical_broker_symbol(..., require_exists=True)` (`market_analysis.py:140`), which first fetches the whole catalog (`symbols.py:21`) and re-raises any fetch error (`symbols.py:22-24`). A `symbol_not_found` result therefore proves the list of every symbol on the account (which contains `XAUUSDm`, see run `10171b1c`, `production-trace.md:33`) was already in the handler's hands and was thrown away (`symbols.py:12-15`). (Added by checker.)
- `market_quote`, `market_instrument`, `market_candles` call `canonical_broker_symbol` without `require_exists`, so an unknown symbol is passed to the broker unchanged (`packages/tools/src/lonora_tools/market.py:47`, `:58`, `:65`; `symbols.py:32-35`). `market_snapshot`, `market_structure`, `market_sessions` use `require_exists=True` and fail with `symbol_not_found` (`market_analysis.py:140`, `market.py:78`, `market_analysis.py:215`).
- The broker adapter maps a 404: `if stage != "candles" or "account" in message and missing: return LonoraError("broker_account_not_found", 404)` (`metaapi.py:52-58`). Because of `stage != "candles"`, every 404 at stage `instrument` (`metaapi.py:474`, `:496`), `quote` (`metaapi.py:701`), `symbols` (`metaapi.py:459`) or `rpc` (`metaapi.py:434`) becomes `broker_account_not_found`, whatever the provider message says. The `symbol_not_found` branch on the next lines (`metaapi.py:59-60`) is reachable only at stage `candles`. For `market_instrument` the deciding stage is `rpc`: `read_rpc` diagnoses first (`metaapi.py:434`), and the outer `diagnose(..., "instrument")` returns that error unchanged because it already has a `diagnostic_message` (`metaapi.py:237-238`, `:474`). This is the mechanism behind "تفاصيل العقد رجعت **broker_account_not_found**": a contract-specification read for a symbol the broker does not list is reported as a missing account. It contradicts the policy line "A truly unknown symbol is not a generic connection failure." (`packages/agent-runtime/resources/system/lonora.md:239`).
- Trace (supersedes the author's UNSURE): the calls were `market_snapshot {"symbol":"XAUUSD"}` → `symbol_not_found`, then `market_instrument {"symbol":"XAUUSD"}` → `broker_account_not_found`, with the connection id returned by `list_accounts` (`production-trace.md:243-248`). `metaapi.py:58` is the only place in Python that produces `broker_account_not_found` (`grep -rn broker_account_not_found packages apps --include=*.py`), so the provider did answer HTTP 404 to the specification read. UNSURE: the 404 body text (container logs for 09:44 UTC are gone, `TIMELINE_CORRECTION.md:15`) and why the call took five seconds (`production-trace.md:95`).
- `market_symbols` ("Discover exact broker symbol names … Use before guessing broker symbols or aliases; suffixes matter.") has no `eager=` argument (`market.py:97-105`), while `market_instrument`, `market_quote`, `market_candles`, `market_snapshot` are eager for the `market` profile (`market.py:112`, `:128`, `:136`; `market_analysis.py:370`). Loading the registry confirms: 126 tools, 64 read-only, 3 financial; `market_symbols` has an empty eager set (re-run by checker). The trace confirms it was not among the 23 native tools offered in any run (`production-trace.md:17`). The model must reach it through the `tool_call` bridge. It is not hidden, though: every model round carries the capability inventory (`packages/agent-runtime/src/lonora_agent/tool_loop.py:492`, `:501`), which tells the model to "Call any other capability below with tool_call … and before claiming an ability is absent" (`packages/tools/src/lonora_tools/registry.py:424-431`); the checker rendered it from the live registry: 3,056 characters, under the 8,000 budget (`registry.py:61`), with `market_symbols` on its `market:` line. The native `market_instrument` description also says "Read specifications for ONE exact broker symbol from market_symbols." (`market.py:108`). UNSURE: the trace records the native tools offered, not the inventory text, so its presence in run `1ae9a14c` is inferred from code.
- The `recovery` for both codes is `not_found` / `inspect_existing_state` (1.4). It does not name `market_symbols`.

---

## 5. Guardrails after repeated failures

State lives in the Run checkpoint (`tool_guardrails.py:53`, `:159-168`). Thresholds: `tool_guardrails.py:56-71`. All messages are English and go to the model (attached as `runtime_notice` on the tool result, `tool_block.py:334`; `packages/agent-runtime/src/lonora_agent/runtime_notices.py:55-64`).

| Signal | Action | Message (verbatim) | Line |
| --- | --- | --- | --- |
| same tool + same args failed 2× | warn | "{tool} has failed {count} times with identical arguments. Inspect the error and change strategy instead of retrying it unchanged." | `tool_guardrails.py:78-81`, `:334-335` |
| same tool failed 3× (any args) | warn | "{tool} has failed {count} times in this run. Diagnose the latest error before another attempt: correct the arguments, use a narrower request or a genuinely different source, or report the blocker." | `tool_guardrails.py:82-86`, `:336-337` |
| same tool failed 8× | halt | "{tool} failed {count} times in this run. Stop retrying this failing path." | `tool_guardrails.py:87-89`, `:332-333` |
| identical read, identical result 2× | warn | "{tool} returned the same result {count} times. Use the result already provided or change the request instead of repeating it unchanged." | `tool_guardrails.py:90-93`, `:355-356` |
| …5× | block | "{tool} was not executed: the identical read already returned the same result {count} times. Use that result or change the request." | `tool_guardrails.py:94-97`, `:299` |
| …2 refused repeats | halt | "{tool} kept being requested unchanged after it was refused for making no progress." | `tool_guardrails.py:98-100`, `:295-298` |
| identical consecutive call 3× / 5× | warn / halt | "This is call {count} in a row to {tool} with identical arguments and an identical result. Do not repeat it; …" / "{tool} was called {count} times in a row …" | `tool_guardrails.py:101-108`, `:380-387` |
| identical A/B cycle 3 laps / 5 laps | warn / halt | "The last {count} rounds repeated the same cycle of {period} calls …" | `tool_guardrails.py:109-116`, `:388-397` |
| identical effect 2× / 6th / next | warn / block / halt (needed for safety: stops duplicate effects before the handler runs) | "{tool} has now run {count} times in a row with identical arguments. Each call is a separate effect, not a retry: …" / "{tool} was not executed: …" | `tool_guardrails.py:117-130`, `:240-257`, `:370-373` |

Note on the same-tool counter: it counts failures per tool name regardless of arguments (`tool_guardrails.py:330`), so trying `XAUUSD`, `XAUUSDm`, `GOLD`, `XAUUSD.` on `market_quote` earns the "report the blocker" warning at the third miss. A success on that tool resets it (`tool_guardrails.py:339-340`).

After a halt or the round limit the loop makes one tool-less model call with this notice (`packages/agent-runtime/src/lonora_agent/tool_loop.py:245-253`): "This run stopped a repeating tool loop: {halt message}. No tool call will execute any more. Write the final reply to the owner now, in the owner's language: report only results verified by tool observations in this run; name every operation whose outcome is unresolved or unverified without calling it successful; and give the concrete next steps. Do not invent progress." (`runtime_notices.py:117-129`). The halt message contains the tool name. If that model call fails, the deterministic fallback is used (`tool_loop.py:284`, text in 7.2).

Budget notices to the model: "This is the last model round in this run whose tool calls will execute." / "{n} model rounds whose tool calls will execute remain in this run, including this one. …" (`runtime_notices.py:102-114`, sent at `tool_loop.py:486-487`, threshold `tool_loop.py:114`). Empty answer: "No answer was provided for the selected request. Provide the substantive result or ask a necessary clarification with wait_for_input. Do not invent results." (`runtime_notices.py:96-99`, `tool_loop.py:577`).

---

## 6. What the instructions tell the model to do with a failure

The reply the owner quoted ("ما قدرت… رجعت **symbol_not_found**… الخطوة التالية المفيدة: أبحث لك… إذا أردت") follows the written policy closely. Relevant lines, all in `packages/agent-runtime/resources/`:

Pushing toward "report and offer":

- "Report the practical failure and one concrete next step, preserving the distinction between unavailable and uncertain." (`system/lonora.md:163`)
- "Give at most one specific useful next suggestion when a suggestion is warranted." (`system/lonora.md:33`)
- "Do not hide a failure, risk boundary, rejected request, missing source, or uncertain financial result to make a reply sound smooth." (`system/lonora.md:54`)
- "Stay friendly and curious — I'd rather ask a good question than guess wrong." (`bootstrap/SOUL.md:10`)
- "Never strip suffixes, substitute an exchange feed or assume one broker's instrument exists at another." (`system/lonora.md:224`)
- "If several symbols plausibly match an alias, discover real candidates and ask which one." (`system/lonora.md:225`)
- Third same-tool failure notice ends with "or report the blocker" (`tool_guardrails.py:85`).

Pushing toward "fix it yourself":

- "For an ordinary safe read failure, make a bounded meaningful correction or use a genuinely supported alternative source." (`system/lonora.md:160`)
- "Continue authorized work without asking whether to begin or making the owner repair internal arguments." (`system/lonora.md:35`)
- "Tool failures are operational observations, not completion of that objective. Use tool_environment to inspect the actual schema, scope and side-effect class; follow typed recovery information." (`constitution/tool-policy.md:7`)
- "Use market_symbols to discover exact symbols before guessing aliases." (`system/lonora.md:212`)
- (Added by checker) "Ask one focused clarification only when missing information prevents meaningful progress." (`system/lonora.md:205`), but this line sits in the `voice` chapter (`system/lonora.md:177`), which is sent only after a voice-mapped tool call such as `owner_notify` (`resources/system/manifest.json:132-134`), so it was most likely absent from the gold run; the inventory's "…inspect it with tool_environment first when you do not know its input schema, and before claiming an ability is absent." (`packages/tools/src/lonora_tools/registry.py:428-429`); `market_instrument`: "Read specifications for ONE exact broker symbol from market_symbols." (`market.py:108`).

Two structural facts weaken the second group:

1. Lines 212-244 belong to the `market` chapter (`system/lonora.md:209`). Chapters are added only for tools that appear as tool calls in the last 16 messages (`packages/agent-runtime/src/lonora_agent/skills/system_policy.py:134-142`). On the first market call of a conversation the chapter is not yet in the request. Checker's limit on this point: the selection is recomputed for every model request (`packages/agent-runtime/src/lonora_agent/model_runtime.py:65`), and `market_snapshot` / `market_instrument` map to `market` (`packages/agent-runtime/resources/system/manifest.json:52`, `:57`). In run `1ae9a14c` the reply was written after both market calls, so by that round the chapter, with "Use market_symbols to discover exact symbols before guessing aliases." (`system/lonora.md:212`), was in the request. Late arrival explains the first guess (`XAUUSD`), not the decision to stop and offer. UNSURE: inferred from code; the trace does not store the request text.
2. The one prompt that says "Gold may have broker suffixes or a different broker name; never guess or strip them. Letter case alone is not a different symbol: if market_symbols has one match ignoring case, use that exact spelling and do not ask the owner to retype it." is `prompts/trading_context.md:5`. No Python code loads it: the only `load_prompt(...)` calls are `run_context_summary`, `consolidator_archive`, `group_behavior`, `suggested_reply`, `web_search_on`, `subagent_system` (`packages/agent-runtime/src/lonora_agent/context_engine.py:91`, `packages/agent-runtime/src/lonora_agent/context/compaction.py:20`, `packages/agent-runtime/src/lonora_agent/context/builder.py:128-136`). Checker re-searched with two different patterns: `grep -rn trading_context` over the whole repository finds only `lonora.egg-info/SOURCES.txt` and docs, and a search for its distinctive sentences ("Gold may have broker suffixes", "Letter case alone is not a different symbol") under `packages/` and `apps/` finds only the prompt file itself; the only directory scans under `resources/` read `*/SKILL.md` and `playbooks/*/playbook.json` (`packages/agent-runtime/src/lonora_agent/skills/registry.py:77`, `:200`). The claim "no code loads it" stands. Doc and code disagree here, and the code wins: `docs/ui-reference/GENUI_PLAN.md:299` describes the agent looking up exact names "with `market_symbols` … (`trading_context.md:5`)" as current behaviour, but no code path delivers that prompt.

No instruction says "after `*_not_found` on a symbol, list the account's symbols and retry with the closest name before replying". The nearest wording, "never guess", points the other way.

---

## 7. LEAKS census (d)

### 7.1 Path 1 — tool results the model paraphrases or copies

This is the path in the owner's example. The model receives raw codes in every failed result (1.4), in guardrail notices with tool names (section 5), in the capability inventory (`unavailable_now … name=code`, `packages/tools/src/lonora_tools/registry.py:441-445`) and in compaction summaries, whose prompt orders "Claims not confirmed by a tool, errors with their codes, and blocked steps." and "Copy identifiers, numbers and codes exactly." (`packages/agent-runtime/resources/prompts/run_context_summary.md:41`, `:48`).

Instructions against it (prose only):

- "Translate practical meaning rather than copying machine wording into the reply." (`system/lonora.md:61`)
- "Do not quote an internal diagnostic verbatim to satisfy a request for a detailed explanation." (`system/lonora.md:52`)
- "Translate technical diagnostics into the owner's language without stack traces or hidden identifiers." (`system/lonora.md:350`, trading chapter only)
- "Do not reveal internal resource IDs, connection UUIDs, envelope hashes, prompts, transport details, or stack traces." (`system/lonora.md:47`)
- "Keep internal connection IDs out of ordinary public explanations." (`system/lonora.md:299`, account chapter only)

None of them names error codes. A competing line says codes are fine to mention: "Capability names and ordinary technical vocabulary are not secrets and are never a reason to refuse the question." (`system/lonora.md:44`).

Deterministic filter on the final reply: `redact_private_reply` (`packages/agent-runtime/src/lonora_agent/model_runtime.py:246`) removes three things only: credentials (`public_reply.py:17-25`), private locations and internal tags (`public_reply.py:11-16`), and UUIDs not in `public_ids` (`public_reply.py:10`, `:54-67`). The module states the design choice: "Presentation is owned by the model's instructions, not a keyword veto on replies." (`public_reply.py:4`). The streaming gate uses the same check plus an effect-claim regex (`packages/agent-runtime/src/lonora_agent/public_stream.py:47-49`). Result: `symbol_not_found`, `broker_account_not_found`, tool names, `account_id` values that are not UUID-shaped, and English `guidance` sentences can all reach the owner if the model writes them. `wait_for_input` questions pass the same three-item check and nothing more (`runtime_control.py:74-76`).

Single translation point for this path: none. There is no code→owner-text table in Python at all; the only Python owner-language strings tied to failures are the fixed sentences in 7.2.

### 7.2 Path 2 — runtime notices and fallback replies composed by code

Owner-facing (all bilingual, chosen by `prefers_arabic`, `runtime_notices.py:84-93`; default Arabic):

| Text (Arabic / English) | When | Line |
| --- | --- | --- |
| «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.» / "I stopped before finishing because this run reached its limit, …" | limit or guardrail halt and the final model call produced no text | `runtime_notices.py:132-139`, `tool_loop.py:284` |
| «هذه المهمة لم تكتمل بعد.» / «هذه المهمة المستمرة غير مراقَبة: …» / «توقفت هذه المهمة قبل اكتمالها لأن هذه الجولة بلغت حدّ العمل، …» / «توقفت هذه المهمة قبل اكتمالها لأن استدعاء أداة تكرر دون تقدّم، …» / «هذه المهمة معلّقة لأن كل النماذج المهيأة غير متاحة منذ مدة …» plus «أحتاج توجيهك قبل المتابعة: ردّ هنا، أو عدّل المهمة أو استأنفها أو أوقفها مؤقتًا أو ألغها.» and «آخر تقرير: » | Task handed to the owner | `runtime_notices.py:142-169`, `:190-203`, `packages/agent-runtime/src/lonora_agent/loop_outcomes.py:125-152` |
| «نتيجة العملية غير مؤكدة بعد؛ أتحقق منها ولن أعيد إرسالها.» / "The outcome is not confirmed yet; …" (needed for safety) | appended when a financial result is still uncertain | `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:36-37`, `:115-118` |
| «أقرّ الوسيط بالطلب، لكن التحقق المستقل من نتيجته لم يكتمل بعد. لن أكرر الإرسال.» (needed for safety) | replaces prose after an unverified confirmation | `packages/agent-runtime/src/lonora_agent/context/financial_result.py:121-125` |
| «تعذر تأكيد نتيجة الطلب؛ سأتحقق من حساب الوسيط قبل أي إعادة إرسال.», «لم تتأكد جميع نتائج طلبات التداول؛ …», «لم يُنفّذ الطلب» + reason, «نتيجة الطلب غير محسومة؛ …» (needed for safety) | wait prose after an unsettled financial result | `financial_result.py:151-155`, `:193-197`, `:202-206`, `:208-212` |
| «حجم التداول غير مقبول لدى الوسيط.», «السوق مغلق.», «مستويات وقف الخسارة أو جني الربح غير مقبولة.», «الرصيد المتاح غير كافٍ.» | the only code→Arabic table on the server: 6 broker return codes; comment "Only documented server/broker codes select these safe human descriptions." | `financial_result.py:217-239` |

The "title" of an unfinished step in «الخطوات غير المكتملة: …» is whatever the model saved as the step title (`loop_outcomes.py:127-129`, `runtime_notices.py:180-189`); language not enforced.

Model-facing only, English by design: every guardrail message (section 5), `NO_ANSWER`, `budget_warning`, `finish_instruction`, `resumed_notice` (`runtime_notices.py:96-129`, `:206-212`), handler `guidance` / `recovery` sentences (4.2), `INVOCATION` and the inventory header (`registry.py:89-93`, `:424-432`). They reach the owner only if the model copies them (path 1).

Also (added by checker): «تعذر عرض هذا الجزء التفاعلي.» when an interactive part cannot be shown, and «غير متاح» / "Unavailable" for a missing value (`packages/agent-runtime/src/lonora_agent/visual_response.py:595`, `:599`).

Single translation point for this path: no table; each sentence is an inline `if arabic … else …` (or an Arabic/English pair) written in four files (`runtime_notices.py`, `uncertain_outcome.py`, `context/financial_result.py`, `visual_response.py`) and used from others such as `loop_outcomes.py` and `tool_loop.py`. (The author said "five files"; `loop_outcomes.py` itself holds no Arabic text, it calls `attention_notice`, `loop_outcomes.py:127-129`.)

### 7.3 Path 3 — API error bodies shown by clients

Server: one handler set (`apps/api/src/lonora_api/errors.py:26-62`). Bodies contain a code and nothing human: `{"code": error.code, "request_id": …}` (`errors.py:29-32`); validation `{"code": …, "fields": [{"path": […], "code": <pydantic type>}]}` (`errors.py:38-47`); `{"code": "resource_conflict"}` (`errors.py:51`); `{"code": "endpoint_not_found" | "request_failed"}` (`errors.py:59-62`). No exception text, no stack trace.

Failed Run: `row.error_code = code` and event `run.failed` with `{"code": code, "failure": {family, retry_after_seconds}}` (`packages/db/src/lonora_db/runs.py:466-487`); unexpected crash is `runtime_error` (`executor.py:313-315`). Progress events carry `name`, `call_id`, `ok`, `code` for every tool (`tool_block.py:377-387`); retry events carry `reason_code` and `code` (`executor.py:295-303`); degraded Task events carry `reason` and `code` (`packages/db/src/lonora_db/tasks.py:822-836`).

Clients translate; there are two mappers:

- Web: `userError()` — five shared tables first, then a 108-case `switch`, default `t\`The request could not be completed. Try again.\`` (`apps/web/src/lib/user_error.ts:12-27`, `:227-228`); Arabic through the Lingui catalog (`apps/web/src/i18n/locales/ar/messages.po:7416-7417` «تعذر إكمال الطلب. أعد المحاولة.»). It has entries for the two codes in the owner's example: «هذا الرمز بالضبط غير متاح لدى وسيطك.» (`user_error.ts:150-151`, `messages.po:7625-7626`) and «لم يتم العثور على حساب الوسيط.» (`user_error.ts:156-157`, `messages.po:1209-1210`). These are used for REST errors and cards, never for chat replies.
- Mobile: `errorText()` — the same five shared tables, then a lookup of the code among its own label keys, else `t("request_failed")` (`apps/mobile/lib/session.tsx:160-179`) = «تعذر تنفيذ الطلب. حاول مرة أخرى.» (`apps/mobile/lib/i18n.ts:574`). No Mobile label exists for `symbol_not_found` or `broker_account_not_found` (text search in `apps/mobile/lib`), so Mobile shows the generic sentence where Web shows a specific one.
- Shared tables in `packages/core/src`: `agentPermissionError` (`agent-permission-errors.ts:56-59`), `financialBoundaryError` (`financial-boundary.ts:137`), `ownerActionError` (`owner-actions.ts:1831`), `ownerProfileError` (`owner-profile.ts:194`), `supervisionError` (`supervision.ts:118`).
- Coverage (regex count, approximate): Web switch + shared tables match about 153 of the 723 distinct server codes; Mobile's own labels match 38. Every other code shows the generic "could not be completed / try again" sentence, which tells the owner nothing about cause or next step.
- Failed-Run card: family titles such as "The agent could not reply" and `other: userError({ code: run.error_code })` (`apps/web/src/conversation/Cards.tsx:69-82`). Added by checker: the family is chosen on the server by prefix, and every `model_*` code, `model_not_configured` included, becomes family `model` (`packages/core/src/lonora_core/runtime_failure.py:50-51`, stored at `packages/db/src/lonora_db/runs.py:467-469`). The Web card for family `model` says "The model is not available right now" / "The model provider could not be reached. Try another model or retry shortly." (`Cards.tsx:73`, `:81`), in Arabic «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.» (`apps/web/src/i18n/locales/ar/messages.po:7336`). The trace shows the five failed runs were all `model_not_configured` (`TIMELINE_CORRECTION.md:27`), so the card told the owner something untrue about the cause; the specific code never reached `userError`. (Model routing default is being fixed in another session; this is the cause only.); Mobile `errorText(new ApiError(run.error_code, 0))` (`apps/mobile/app/thread.tsx:849`); activity list (`apps/web/src/pages/ActivityList.tsx:236`).

Raw code shown by a client: the live activity projection drops tool codes (`packages/core/src/turn-activity.ts:196-209`) and keeps only the Run code for mapping (`turn-activity.ts:88`). Raw values are rendered in three places: an unavailable skill prints `<code dir="ltr">{item.code}</code>` (`apps/web/src/components/skills/SkillCard.tsx:84`); `ToolActivityDisclosure` prints tool name and `event.payload.code` (`apps/web/src/components/ToolActivityDisclosure.tsx:20`, `:33-41`), but no file imports that component (text search under `apps/` and `packages/`), so it appears unused; and the "Technical details" disclosures in 7.4.

Single translation point for this path: two (Web and Mobile), partly shared, with different coverage.

### 7.4 Path 4 — cards and generated-UI payloads with raw fields

- Order card, collapsed "Technical details": operation id, broker ticket, `row.account_id` (the internal connection id) and "Broker return code" (`apps/web/src/conversation/Cards.tsx:440-469`).
- Trading journal, collapsed "Technical details": `e.operation_id` and `JSON.stringify(e.result, null, 2)` — the whole raw result (`apps/web/src/components/trading/TradingJournal.tsx:119-127`). That result can contain `details.description`, the broker's English message passed through `safe_exception_message` (`metaapi.py:906-912`, `:933-935`, `:952-954`; redaction rules `packages/core/src/lonora_core/error_logging.py:9-39`). The same `description` is in the trade result the model reads.
- Generated UI and visual responses: text fields pass the same three-item redaction as replies (`packages/agent-runtime/src/lonora_agent/genui_compile.py:459`, `:813-816`; `packages/agent-runtime/src/lonora_agent/visual_response.py:268-308`). Compile failures become codes kept in metadata (`visual_response.py:648`, `:670`), not card text. A snake_case code the model types into a card label is not filtered.
- Trade approval wait: the runtime's own question text is empty (`packages/tools/src/lonora_tools/trade.py:402`); the card is rendered by the client from structured fields.

Single translation point: none on the server; the client renders structured fields with its own labels and exposes raw values only behind "Technical details".

### 7.5 Path 5 — logs as messages

No path was found that copies a log line or exception text into a message, notification or event:

- Unknown tool exceptions log only the type (`tool_dispatch.py:132`); the Run crash handler logs only the type (`executor.py:314`).
- `diagnostic_message` is written to logs (`metaapi.py:244-250`) and to no payload; the tool result takes only `error.code` (`tool_dispatch.py:113`).
- Maintenance quarantine raises an attention item with `{"item_kind": …, "reason_code": code}` (`packages/db/src/lonora_db/item_failures.py:228`), where the code may be `unexpected_<exception class>` (`item_failures.py:48`); clients show a fixed sentence for the attention kind (`apps/web/src/components/ai/AttentionInbox.tsx:32`, `apps/mobile/components/attention-inbox.tsx:36`). UNSURE whether any client screen prints `reason_code` itself; none was found in the files read.
- The one place exception-derived English text is stored in an owner-reachable record is the trade `details.description` in 7.4.

### 7.6 Plain statement

There is not one place that turns internal codes into owner language. There are:

1. none on the server for chat replies — the model improvises from `code` + `next_action`, guided by prose, with no filter for codes;
2. one six-entry server table for broker return codes used only in financial wait prose (`financial_result.py:217-239`);
3. inline bilingual sentences for runtime stops in four server files (7.2);
4. two client mappers with unequal coverage (7.3), which never see chat text.

---

## 8. Mechanisms that produce "stops / leaks a code / asks instead of acting"

Ordered by how directly they explain the owner's example.

1. Failure results are code-only. `{"ok": False, "code": error.code}` (`tool_dispatch.py:113`) with a generic enum (`environment.py:35-93`); `LonoraError` cannot carry a hint (`user_error.py:1-14`). The model has a bare token and nothing else to put in a reply.
2. No symbol candidates on market reads. `catalog_symbol` raises `symbol_not_found` for anything but an exact or case-only match (`symbols.py:6-15`), although `symbol_candidates` with broker-suffix matching already exists for `agent_create` (`agents.py:72-91`).
3. Wrong code from the broker adapter. Every non-candles 404 becomes `broker_account_not_found` (`metaapi.py:57-58`), so an unknown symbol looks like a broken account link («الارتباط الحالي غير مطابق»).
4. Discovery tool not native. `market_symbols` is outside the eager set (`market.py:97-105`); the tools that fail on a wrong name are inside it (`market.py:112`, `:128`, `:136`). Checker's correction of weight: it costs one `tool_call` hop, but it is named every round in the capability inventory and in `market_instrument`'s description (4.3), so the model was not unaware of it; it chose not to use it.
5. Policy rewards "report + one suggestion". `system/lonora.md:163`, `:33`, `bootstrap/SOUL.md:10`; "never guess or strip" (`system/lonora.md:224`, `prompts/trading_context.md:5`). The self-correcting instruction for symbol spelling sits in a prompt file no code loads (section 6).
6. Market guidance arrives late. The `market` chapter is injected only after a market tool call is already in the last 16 messages (`system_policy.py:134-142`). Checker: in the gold run this explains only the first guess; the chapter was present when the reply was written (section 6, point 1).
7. Guardrail wording steers to stopping. "…or report the blocker" at the third failure of one tool, counted across different arguments (`tool_guardrails.py:82-86`, `:330`). Checker: did not fire in the gold run: two failures on two different tools stay below every failure threshold (`tool_guardrails.py:56-58`, `:329-337`).
8. No code filter on replies. Only credentials, UUIDs and private paths are removed (`public_reply.py:10-25`, `model_runtime.py:246`); design note at `public_reply.py:4`. Checker re-searched: no compiled pattern in `packages/agent-runtime/src/lonora_agent` and no check in `stop_gates.py` looks for snake_case codes; the only reply-side patterns are `EFFECT_CLAIM` (`public_stream.py:11`) and private keys / numbers in visual and generated UI (`visual_response.py:32`, `genui_compile.py:38`).
9. Compaction preserves codes verbatim (`prompts/run_context_summary.md:41`, `:48`), so they stay in front of the model for the rest of the Run. Checker: not a factor in the production conversation, which had no `context_compacted` events (`production-trace.md:90`).
10. Automatic retry is narrower than advertised. Metadata promises two automatic retries for every read-only tool (`packages/tools/src/lonora_tools/environment.py:37-38`); the runtime grants them for 8 codes only (`environment.py:92`).
11. Generic client fallback. About four fifths of server codes map to "The request could not be completed. Try again." on Web and more on Mobile (7.3).
12. (Added by checker) The handler holds the answer and discards it. `market_snapshot` fetched the account's full symbol list before raising `symbol_not_found` (`symbols.py:20-35`, `market_analysis.py:140`), and `market_instrument` also asks for the list but, on no match or on a fetch error, passes the name to the broker unchanged (`market.py:47`, `symbols.py:25-35`). The suffix matcher that would have found `XAUUSDm` exists twice (`agents.py:72-91`, `instrument_names.py:46-53`) and is used by neither. This is the most direct cause of the owner having to type «ضع حرف m».
13. (Added by checker) A wrong cause on the failed-Run card. All `model_*` codes share one family (`runtime_failure.py:50-51`) and one Web text, "The model provider could not be reached" (`Cards.tsx:81`); for `model_not_configured` that told the owner the provider was down when no model was set up (`TIMELINE_CORRECTION.md:27`).

## 9. Refusals in this area that exist for the money-safety rules (keep)

- `tool_execution_uncertain` / `broker_result_ambiguous` instead of a retry for any mutation that timed out, crashed or was interrupted (`tool_dispatch.py:70-95`, `:127`, `:137`; `tool_block.py:73-74`).
- No dispatch deadline and no automatic retry for financial tools (`base.py:99-101`; `packages/tools/src/lonora_tools/environment.py:38`).
- Identical-effect block before the handler runs (`tool_guardrails.py:240-257`).
- `permission_denied` / `respect_scope`, `risk_limit_blocked`, `authorization_required`, `health_blocked` categories (`environment.py:50-73`, `:82-88`).
- Exception text never copied to the model or the owner (`tool_dispatch.py:129-132`; `schema.py:64-66`).
- The uncertain-outcome line and the financial wait sentences (`uncertain_outcome.py:36-37`; `financial_result.py:121-125`, `:151-212`).
- `wait_for_input` refused as a trade-consent channel (`runtime_control.py:63-72`).

A change that adds candidates, a hint field or an automatic read-only follow-up (listing symbols, retrying a read with the single suffix match) touches none of these: all are read paths. Any change to how mutation failures are worded or retried does.

## 10. Items not confirmed

- RESOLVED by the trace: the tool sequence behind the owner's quoted reply (`production-trace.md:243-248`, see 4.3).
- RESOLVED for specification reads: the provider answered HTTP 404 (the only producer of `broker_account_not_found` is `metaapi.py:58`). UNSURE for price reads (`metaapi.py:701`), which did not fail in this conversation, and UNSURE what the 404 body said.
- RESOLVED (checker, two searches): `prompts/trading_context.md` is not loaded by any code path (section 6, point 2).
- UNSURE: exact size of the code set; 723 / 728 are regex counts of literal codes and exclude about 27 dynamically built sites and broker return codes.
- UNSURE: whether the capability inventory and the `market` chapter were in the request of run `1ae9a14c`; the code says yes (4.3, section 6), the trace does not store request text.
- UNSURE: client coverage figures (153 / 38) come from regex key extraction and are approximate.
- Not examined: the legacy `apps/web` screens beyond the files cited, voice-surface wording, and channel adapters (`packages/channels`).

## Verification log

Checker: independent pass that tried to refute this file. Method: every cited file was opened at the cited lines (`awk`/`sed -n` with line numbers, or the Read tool), every verbatim quote compared with the source line, every absence claim re-searched with at least two different searches, every count re-run (a Python regex over all `*.py` under `packages/` and `apps/`, plus loading the live tool registry from the repository's own virtualenv). Nothing under `/home/user/lonorabot` was changed.

- Citation tokens in the file before edits: about 330 (`path:line` and `:line` continuations). All cited files and line ranges were opened; for about 15 long multi-line ranges (client components, `metaapi.py:906-954`, `genui_compile.py:813-816`) the start and end lines and the quoted line were checked, not every line in between.
- Wrong line numbers found: 0. Wrong verbatim quotes found: 0 (policy lines `system/lonora.md:33,35,44,47,52,54,61,160,163,212,224,225,239,299,350`, `bootstrap/SOUL.md:10`, `constitution/tool-policy.md:7`, `prompts/trading_context.md:5`, `prompts/run_context_summary.md:41,48`, all guardrail messages, all Arabic runtime and financial sentences, the `market_symbols` description, all `recovery`/`guidance` strings and the Web/Mobile strings matched character for character).
- The constructed failure shape in 1.4 matches the production result for `market_snapshot` exactly (`production-trace.md:246`).

Claims refuted and corrected (5):
1. "10 scope/restriction codes" → 9 codes are listed at `environment.py:56-69`.
2. "723 distinct codes / 631 default / 4 temporary_unavailable / adapters 71" → these come from a line-based grep that misses `LonoraError(` with the code on the next line; with that included: 1,317 occurrences, 728 codes, 634 default, 6 `temporary_unavailable`, adapters 76. Percent (87%) unchanged. Both sets of numbers are now given.
3. "About 20 sites build the code at runtime" → about 27.
4. "The single exception is `ToolArgumentsError.issues`" → at dispatch yes, but `memory_write` converts `MemoryEditError` / `MemoryOverflow` / `version_conflict` into detailed results itself (`memory.py:136-153`); added to 4.1 and 4.2.
5. "inline sentences … in five files" → four files hold the Arabic/English text; `loop_outcomes.py` only calls `attention_notice`.

Claims downgraded (4):
6. Mechanism 4 ("discovery tool not native"): true, but `market_symbols` is named every round in the capability inventory (checker rendered it: 3,056 chars, under the 8,000 budget) and in `market_instrument`'s description (`market.py:108`); it is an extra hop, not an invisible tool.
7. Mechanism 6 ("market guidance arrives late"): the chapter is recomputed per request (`model_runtime.py:65`) and was present at the reply round of run `1ae9a14c`; it explains the first guess only.
8. Mechanism 7 (guardrail "report the blocker"): did not fire in the gold run (two failures on two different tools).
9. Mechanism 9 (compaction keeps codes): not a factor in production (no `context_compacted` events, `production-trace.md:90`).

UNSURE items resolved by the trace or by re-search (3): the tool sequence (`production-trace.md:243-248`); the 404 on the specification read (`metaapi.py:58` is the only producer of `broker_account_not_found`); `trading_context.md` not loaded (two searches, plus the directory scans at `skills/registry.py:77`, `:200`).

Absence claims re-checked and upheld: no central code registry; no snake_case code filter on replies (`public_reply.py:10-25`; compiled patterns in `lonora_agent` and `stop_gates.py` searched); `ToolActivityDisclosure` imported nowhere; no Mobile label for `symbol_not_found` / `broker_account_not_found`; `diagnostic_message` reaches logs and the trade `description` only.

Not re-verified: client coverage figures 153 / 38 (kept, marked approximate); the five-second duration of the `market_instrument` call.

Findings the author missed, now in the body (10):
- A second suffix matcher plus a gold→`XAUUSD` name table, `instrument_names.py:20-21`, `:46-53`, used only for generated UI (4.3).
- `market_snapshot`'s `symbol_not_found` proves the full symbol list was fetched and discarded (`symbols.py:20-35`) — new mechanism 12, the most direct cause of «ضع حرف m».
- Failed-Run card mislabels `model_not_configured` as "provider could not be reached" via `runtime_failure.py:50-51` and `Cards.tsx:81` — new mechanism 13 (cause of the untrue «تعذّر الوصول إلى مزوّد النموذج»).
- The capability inventory and `market_instrument`'s description both name `market_symbols` (4.3, section 6).
- The market chapter was present at the reply round (section 6, point 1).
- `memory_write` already uses the "catch a typed error, return details" pattern (4.1, 4.2).
- `agent_create` returns `configured_models` for a disallowed model (`agents.py:276-280`).
- Doc/code disagreement: `docs/ui-reference/GENUI_PLAN.md:299` presents `trading_context.md:5` as live behaviour; no code loads it (code wins).
- Two `next_action` words outside `classify`: `alternate_route_or_wait`, `read_stored_result` (1.3).
- `visual_response.py:595`, `:599` fallback sentences (7.2); and the note that `system/lonora.md:205` lives in the `voice` chapter, not the core.

Totals: citations checked ≈330; line numbers corrected 0; claims refuted 5; downgraded 4; UNSURE resolved 3; findings added 10.
