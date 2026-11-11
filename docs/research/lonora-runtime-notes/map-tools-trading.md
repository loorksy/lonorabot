# Tool surface, group C (Part 1.3) and census (a): TRADING families

Repository `/home/user/lonorabot`, HEAD `9f5b1da`. Read-only audit. Every claim cites `path:line` (repo-relative). Nothing was executed; all findings come from reading code. Places I could not confirm are marked `UNSURE:`.

Families covered (`packages/tools/src/lonora_tools/`): `trade.py`, `trading_decision.py`, `trading_goal.py`, `restrictions.py`, `position_sizing.py`, `performance.py`, `opportunity.py`. Followed into `packages/trading`, `packages/security`, `packages/db`, `packages/adapters` (broker error mapping only), `packages/agent-runtime` (how a tool failure is shaped for the model only) and the listed docs.

Classes used: **RECOVERABLE-NOT-LED**, **OWNER-NEEDED**, **DEAD-END**, **BUG**. One extra marker, **LED-OK**, is used for outcomes where the result (or the tool description) already tells the model how to repair the call; LED-OK rows are not defects and are counted separately.

---

## 0. The twelve findings that matter most

1. **Every tool error reaches the model as a bare code.** A `LonoraError` raised by any handler becomes exactly `{"ok": False, "code": error.code}` (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:110-117`). `LonoraError` carries only `code`, `status` and two diagnostic fields (`packages/core/src/lonora_core/user_error.py:1-14`); there is no field for a hint, candidates or a next tool. The only addition is a generic `recovery` block chosen by code pattern (`packages/agent-runtime/src/lonora_agent/environment.py:35-93`): the default is `terminal_domain_failure` / `alternate_route` (`environment.py:36-37`), any `*_not_found` becomes `not_found` / `inspect_existing_state` (`environment.py:80-81`). It never names a tool. This is the root mechanism behind «رجعت **symbol_not_found**».
2. **BUG: an unknown symbol is reported as `broker_account_not_found`.** The MetaApi error mapper returns `broker_account_not_found` for any HTTP 404 outside the candles stage: `if stage != "candles" or "account" in message and missing: return LonoraError("broker_account_not_found", 404)` (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:57-58`). `instrument()` and `quote()` use stages `"instrument"` and `"quote"` (`metaapi.py:474`, `metaapi.py:701`), so a 404 for symbol `XAUUSD` on an account that lists `XAUUSDm` is reported as a missing account. That matches the owner's transcript («تفاصيل العقد رجعت **broker_account_not_found** على نفس الربط»). Inside this mapper `symbol_not_found` is only reachable at the candles stage (`metaapi.py:59-60`); the other source is the catalog check `catalog_symbol` (`packages/tools/src/lonora_tools/symbols.py:6-15`). UNSURE: I did not confirm what HTTP status MetaApi actually returns for an unknown symbol; the mapping is certain, the provider behaviour is not.
3. **BUG: a symbol spelling/case mismatch is reported as a connection outage.** `instrument()` raises `ValueError("broker_symbol_mismatch")` when the broker answers under another spelling (`metaapi.py:470-471`); the mapper has no case for it and falls through to `broker_connection_unavailable` (`metaapi.py:80-82`), which the runtime treats as transient (`packages/core/src/lonora_core/runtime_failure.py:10-21`, `environment.py:44-45`).
4. **No trading tool resolves a symbol.** `trade_execute` only repairs letter case and silently keeps an unknown symbol: `canonical_broker_symbol` returns the input unchanged when the catalog does not list it (`packages/tools/src/lonora_tools/symbols.py:30-35`, called at `trade.py:632-634`). `market_decision_record` states it on purpose: "Exact symbols are intentional. No hidden aliases or suffix stripping." (`trading_decision.py:79`). `catalog_symbol` raises `symbol_not_found` without candidates (`symbols.py:6-15`). The recovery tool exists (`market_symbols`: "Use before guessing broker symbols or aliases; suffixes matter." `packages/tools/src/lonora_tools/market.py:98-100`) but no error result points to it. This is why the owner had to type «ضع حرف m يعني XAUUSDM».
5. **The Personal Agent gets no defaults.** `prepare_market_arguments` fills `account_id`/`symbol` only when the agent has both bound (`packages/tools/src/lonora_tools/market_binding.py:89-90`). For an agent without a bound pair, `TradeRequest.account_id` and `symbol` are required (`packages/contracts/src/lonora_contracts/trading.py:16`, `trading.py:30`), as are `DecisionRequest.account_id/symbol/timeframe` (`packages/contracts/src/lonora_contracts/trading_decision.py:93-95`) and `PositionSizingRequest.account_id/symbol/currency` (`packages/contracts/src/lonora_contracts/position_sizing.py:14-18`). The model must supply the internal connection id and the exact broker spelling itself.
6. **BUG (UNSURE, not executed): an identical retry in the same Run replays a stale failure, even after a new owner approval.** `trade_execute` derives `operation_id` from the Run id and the argument hash only (`trade.py:635`). The executor answers any existing journal row for that id with its stored receipt (`packages/trading/src/lonora_trading/execution.py:162-168`). A not-sent failure recorded after the journal reservation (`execution.py:238-245`), such as a spread gate (`execution.py:337-343`), a risk limit (`execution.py:373-384`) or a broker rejection, is terminal `failed`. The approval layer deliberately asks again for a result that never reached the broker (`trade.py:145-147`, docstring `trade.py:117-119`), so the owner taps Approve on a new card and the executor returns the old failure without sending. Docs promise "A result that never reached the broker ... asks again" (`docs/account-authority.md:78-80`); the code asks again but cannot send again. Code wins.
7. **BUG (UNSURE whether intended for exits): a Run linked to a Goal cannot close a position with `trade_execute` / `trade_close_positions`.** `goal_create` writes `goal_id` into the Run metadata (`trading_goal.py:73-78`). The executor refuses any leased trade from such a Run that is not a Goal step: `raise LonoraError("goal_step_required", 409)` (`execution.py:121-126`), before any risk-reducing classification. The only test covers an entry ("Ordinary trade bypassed goal", `tests/check_goals.py:353-355`). This conflicts with "exits are always admissible".
8. **BUG: `goal_control` and `goal_plan` need a `version` no read tool returns.** `GoalToggle.version: int` is required (`trading_goal.py:58-60`), `GoalPlanUpdate.version` too (`packages/contracts/src/lonora_contracts/trading_goal.py:113`). The row version increases on every state change (`packages/db/src/lonora_db/trading_goals.py:50-52`). `goal_list` and `goal_read` return `plan_version` but not `version` (`trading_goal.py:102-114`, `trading_goal.py:132-148`). Only the mutating tools' outputs carry it (`goal_data` → `resource_data`, `packages/db/src/lonora_db/trading_goals.py:33-39`, `packages/db/src/lonora_db/transactions.py:21-31`). On a later wake the model can only guess, and gets `version_conflict` (`trading_goals.py:146`, `trading_goals.py:193`). UNSURE: I searched `packages/agent-runtime/src/lonora_agent/context/` for a goal version in a context frame and found none; I did not search every other context source.
9. **A single failed Goal step blocks the Goal until the owner acts outside the chat.** Any executor error before the journal exists marks the step and the Goal `blocked` (`packages/trading/src/lonora_trading/goals.py:538-549`). The tool's resume passes `owner_authorized=False` (`trading_goal.py:471-477`), so resume fails with `goal_owner_retry_required` (`trading_goals.py:174-176`). There is no owner-action card kind for a Goal (`packages/contracts/src/lonora_contracts/owner_actions.py:20-28`); the owner must use the Goals panel (`apps/web/src/components/goals/TradingGoals.tsx:145`). Blocking after uncertainty is needed for safety; blocking after a proved never-sent validation failure (for example `market_quote_stale`, `packages/trading/src/lonora_trading/preflight.py:84`) is friction beyond the money rules.
10. **BUG: `trade_close_positions` can answer "no positions" when positions exist.** It filters with an exact string compare, `p.symbol == args["symbol"]` (`trade.py:664`), and returns `{"results": [], "code": "no_positions"}` (`trade.py:666-667`) as a success (`ok: True` is added at `tool_dispatch.py:109`). Unlike `trade_execute` it does not even repair letter case. For a non-fixed agent, `XAUUSD` against open `XAUUSDm` positions yields a false "nothing to close". (A fixed-market agent is safe: its symbol is forced, `market_binding.py:120-121`.)
11. **`market_decision_record` never says "ready".** `ExecutionReadiness.state` is `Literal["BLOCKED", "REVALIDATION_REQUIRED"]` with `execution_authorized: Literal[False]` and five `remaining_checks` (`packages/contracts/src/lonora_contracts/trading_decision.py:68-82`); the best case is `REVALIDATION_REQUIRED` (`packages/trading/src/lonora_trading/decision_readiness.py:140`). Nothing in the result says the next step is simply `trade_execute`.
12. **Internal codes are allowed in owner-facing replies by design.** The reply guard blocks only credentials, private paths and UUIDs; its header says "Public capability names and ordinary diagnostic vocabulary are not credentials." (`packages/core/src/lonora_core/public_reply.py:3`, checks at `public_reply.py:37-51`). `docs/persistent-trading-teammate.md:58-62` describes a "lexical disclosure policy" with a rewrite of "private final narration"; the code does not filter error codes. Code wins. See section 9.

---

## 1. How a failure is shaped before the model sees it (applies to every tool below)

| Shape | Source | What the model sees | Hint / next step? |
|---|---|---|---|
| S1 handler raises `LonoraError` | `tool_dispatch.py:110-117` | `{"ok": False, "code": "<code>", "recovery": {"category", "next_action", "safe_to_retry", "attempt"}}` (`environment.py:203-210`) | Generic category only; never a tool name, value or candidate |
| S2 argument validation fails | `packages/tools/src/lonora_tools/schema.py:45-69`, `tool_dispatch.py:114-116` | `code: tool_arguments_invalid`, `issues: [{path, type, code?}]`, `retryable: True`; recovery `inspect_schema_and_repair` (`environment.py:38-39`) | Yes: field path and the validator's machine code. Submitted values are not echoed (`schema.py:46`, `schema.py:51`) |
| S3 financial result | `trade.py:464-468`, `trade.py:494-498` | `{"ok": True, "approval_id", "results": [...], "status": "failed", "code", "details"}`; counted as failed because `status in {"failed","rejected"}` (`environment.py:164-166`) | `details.send_state: "not_sent"` only when the failure happened after the journal reservation (`execution.py:53-60`); an executor error raised before it is rebuilt with the code only (`trade.py:464-467`) |
| S4 timeout or non-Lonora exception | `tool_dispatch.py:118-138` | read-only tool: `tool_read_timeout` / `tool_connection_failure` / `tool_internal_failure`; any other tool: `tool_execution_uncertain` | `tool_execution_uncertain` is classified ambiguous (`environment.py:17-19`, `environment.py:42-43`): `reconcile_before_any_resend` |
| S5 route blocked | `tool_dispatch.py:70-81`, `environment.py:127-131` | After 3 failures of the identical call: `tool_route_exhausted`. After an uncertain result: `broker_result_ambiguous` | `alternate_route_or_wait` / `reconcile_before_any_resend` |
| S6 result too large | `environment.py:234-245`, `packages/tools/src/lonora_tools/tool_results.py:46-55` | bounded summary with `result_ref` | Yes: `result_read_tool: artifact_read` |

Shared defects in this shaping:

- **BUG (S5):** the blocked-route code for an uncertain non-financial tool is `broker_result_ambiguous` (`tool_dispatch.py:71-75`). A `market_decision_record`, `goal_plan`, `market_opportunity_update` or `trade_restriction_create` call that timed out (90 s, `packages/tools/src/lonora_tools/base.py:16`, `base.py:99-104`) is afterwards answered with a broker-ambiguity code although no broker effect exists. Only tools that are both `financial` and `replay_safe` are let through to reconcile (`tool_dispatch.py:55-69`). `trade_restriction_create` is `replay_safe` but not financial (`restrictions.py:305-307`), so its own crash-replay path (`restrictions.py:133-134`) cannot be reached through an identical retry.
- **RECOVERABLE-NOT-LED (S3):** `trade_approval_expired` is returned with `status: "expired"` (`trade.py:397`). That status is not in the failed set (`environment.py:164-166`), so the result gets no `recovery` block at all.
- **Evidence dropped (S3):** an owner restriction raises `AdmissionBlocked` with the restriction data (`packages/trading/src/lonora_trading/restrictions.py:112-116`). When it is raised at the executor's early check (`execution.py:231-237`) or at the tool's pre-card check (`trade.py:261-263`), only the code survives (`trade.py:464-467`, `tool_dispatch.py:113`). The model learns "a restriction is active" but not which, by whom or until when.
- Expired reads: an exhausted read route is forgotten at real owner input (`environment.py:104-124`); a non-read route is not. UNSURE: whether `execution_state.environment` carries across Runs was not traced.

---

## 2. Tool inventory: what each tool can do, who may call it, limits

Common rules:

- **Scopes** (`base.py:39-49`, `base.py:92-97`): `full` may call everything; `observe_only` may call every non-financial tool; `helper` (a subagent) may call only `read_only` tools. A financial tool outside `full` is refused with `observe_only_execution_forbidden` (`packages/tools/src/lonora_tools/registry.py:481-482`, `registry.py:489-490`). Needed for safety.
- **Financial identity** (`market_binding.py:108-112`): every `trade_*` tool except the four in `NONFINANCIAL_TRADE_TOOLS` (`market_binding.py:21-28`), and every `goal_*` tool except `goal_read`, `goal_list`, `goal_decisions`, requires `require_financial_agent` (`packages/db/src/lonora_db/agent_binding.py:108-130`). A delegated research agent gets `delegated_financial_authority_forbidden` (`agent_binding.py:122-125`). Needed for safety.
- **Fixed-market binding** (`market_binding.py:113-141`): for a fixed-market agent every non-read tool whose name starts with `market_`, `chart_`, `watch_`, `trade_`, `goal_`, `account_` (`market_binding.py:18`) must stay on its account and symbol (`agent_binding.py:81-84`). Reads are open (`market_binding.py:118-119`).
- **Exposure** (`base.py:18-25`, `packages/agent-runtime/src/lonora_agent/tool_exposure.py:43-44`): the `market` profile (agents bound to a broker account, and the Personal Agent) receives eager tools as native schemas. Every other registered tool is "discovery-only": listed by name in the capability inventory (`registry.py:406-473`) and callable through `tool_call` (`registry.py:167-178`). Up to 6 remembered tools can be promoted (`registry.py:84-85`).
- **Timeouts** (`base.py:15-16`, `base.py:99-104`): read-only 45 s, other non-financial 90 s, financial tools never wrapped ("cancelling one after send would manufacture ambiguity", `base.py:13-14`).
- **Result size**: 120000 characters (`packages/tools/src/lonora_tools/environment.py:42`).
- **Toolset / policy chapter** (`packages/tools/src/lonora_tools/loader.py:8-50`): `trade`, `restrictions`, `position_sizing` → `trading`; `trading_goal` → `goals`; `trading_decision`, `opportunity`, `performance` → `intelligence`. The chapter texts themselves are outside this file's scope.

| Tool | Registered at | Real effect | read_only / financial | Exposure | Specific limits |
|---|---|---|---|---|---|
| `trade_record_history` | `trade.py:737-743` | Lists journal rows by account/symbol | read-only | discovery-only | `limit` 1-10, default 5 (`trade.py:678`) |
| `trade_record_read` | `trade.py:744-751` | Reads one journal row with evidence | read-only, poller | discovery-only | owner-scoped (`trade.py:684-686`) |
| `trade_execute` | `trade.py:752-769` | Sends one broker order through the single executor, under a signed grant or after an approval card | financial, replay-safe | eager for `market` (`trade.py:767`); availability shows `agent_analysis_only` for a No-trading agent (`trade.py:57-67`, `trade.py:768`) | No dispatch timeout. Approval card lifetime 45 min default, 30-60 min range (`packages/db/src/lonora_db/trade_approvals.py:19-21`) |
| `trade_close_positions` | `trade.py:770-784` | Closes all open positions of one account, or one exact symbol | financial, replay-safe | discovery-only (no `eager`) | `account_id` required (`trade.py:52-54`) |
| `market_decision_read` | `trading_decision.py:275-281` | Reads one stored decision | read-only | discovery-only | positions/orders capped at 20 in the excerpt (`packages/db/src/lonora_db/trading_decisions.py:174-175`) |
| `market_decision_record` | `trading_decision.py:282-288` | Captures quote, 100 candles, account, positions, orders and stores an immutable decision | mutating, not financial | eager for `market` (`trading_decision.py:287`) | 35 s overall, 5 s per read, one retry of a transient read (`trading_decision.py:78-84`, `trading_decision.py:112-115`); 8 missing codes kept (`trading_decision.py:156`) |
| `market_decision_history` | `trading_decision.py:289-296` | Lists stored decisions | read-only | eager for `market` (`trading_decision.py:295`) | defaults to the bound pair (`trading_decision.py:233-239`) |
| `market_decision_compare` | `trading_decision.py:297-303` | Diffs two stored decisions | read-only | discovery-only | same scope and time order required (`trading_decisions.py:85-87`) |
| `goal_create` | `trading_goal.py:483-489` | Stores a plan (max 40 steps, `packages/contracts/src/lonora_contracts/trading_goal.py:71`) and links the Run to it (`trading_goal.py:73-78`) | mutating, replay-safe | discovery-only | financial identity required |
| `goal_list` | `trading_goal.py:490-496` | Lists this agent's goals in this chat | read-only | discovery-only | 30 rows (`trading_goal.py:97`, `trading_goal.py:115`) |
| `goal_read` | `trading_goal.py:497-504` | One step and plan headers | read-only, poller | discovery-only | same agent and thread only (`trading_goal.py:129-130`) |
| `goal_decisions` | `trading_goal.py:505-511` | Last 3 decisions of a step | read-only | discovery-only | 3 rows; positions/orders capped at 5 (`trading_goal.py:166`, `trading_goal.py:178-179`) |
| `goal_plan` | `trading_goal.py:512-517` | Replaces pending steps | mutating | discovery-only | needs `version` |
| `goal_step_complete` | `trading_goal.py:518-523` | Marks an analysis/watch/review step done | mutating | discovery-only | never a trade step (`trading_goal.py:244-245`) |
| `goal_wait` | `trading_goal.py:524-529` | Creates a watch or routine that wakes the agent | mutating | discovery-only | review interval 60 s to 1 year (`packages/contracts/src/lonora_contracts/trading_goal.py:53`) |
| `goal_step_execute` | `trading_goal.py:530-539` | Sends the declared trade of the current step through the same executor | financial, replay-safe | discovery-only; availability as `trade_execute` (`trading_goal.py:538`) | fixed step/attempt identity (`trading_goal.py:363-369`) |
| `goal_control` | `trading_goal.py:540-545` | Pause, resume or cancel a goal | mutating | discovery-only | needs `version`; resume after a failed attempt is owner-only |
| `trade_restriction_create` | `restrictions.py:285-308` | Records a narrowing restriction the executor enforces | mutating, replay-safe, no financial authority needed | discovery-only | other agents: `valid_until` required, at most 31 days (`restrictions.py:58`, `restrictions.py:179-184`) |
| `trade_restriction_list` | `restrictions.py:309-317` | Lists restrictions and money limits | read-only | discovery-only | restrictions relevant to the agent (`restrictions.py:246-256`) |
| `market_position_size` | `position_sizing.py:21-31` | Computes a lot size from a money risk budget and a stop | read-only | discovery-only | quote and account at most 60 s old (`packages/trading/src/lonora_trading/position_sizing.py:38-49`) |
| `market_performance_read` | `performance.py:32-38` | Counts execution-quality states over the agent's journal rows | read-only | discovery-only | scans the newest 1000 owner rows before filtering by agent (`packages/trading/src/lonora_trading/performance.py:82-84`, `performance.py:100`) |
| `market_opportunity_version` | `opportunity.py:151-157` | One historical thesis version | read-only | discovery-only | |
| `market_opportunity_create` | `opportunity.py:158-163` | Stores a thesis keyed by agent/account/symbol/timeframe/setup_key | mutating | discovery-only | idempotent per key (`packages/db/src/lonora_db/trading_opportunities.py:120-130`) |
| `market_opportunity_read` | `opportunity.py:164-171` | Reads and refreshes a thesis, last 10 history rows (`opportunity.py:74`) | registered read-only, poller | discovery-only | |
| `market_opportunity_update` | `opportunity.py:172-177` | Versioned status/definition change | mutating | discovery-only | |
| `market_opportunity_list` | `opportunity.py:178-184` | Lists the agent's theses | read-only | discovery-only | |

Only three tools of these seven families are in the eager `market` set: `trade_execute`, `market_decision_record`, `market_decision_history`. Everything else, including `trade_close_positions`, `goal_step_execute`, `market_position_size` and both restriction tools, needs a `tool_call` hop.

---

## 3. Family `trade.py`

Rows apply to `trade_execute` and `trade_close_positions` unless a tool is named. "(sf)" = needed for safety.

| # | Tool | Error code / outcome | path:line | What the model sees (hint?) | Class | Recovery path |
|---|---|---|---|---|---|---|
| T1 | both | `tool_arguments_invalid` with issue codes `volume_required`, `price_required`, `position_required`, `order_required`, `modification_fields_required`, `conflicting_protection_edit`, ... | `packages/contracts/src/lonora_contracts/trading.py:40-94`; `schema.py:45-69` | S2, with path and code | LED-OK | repair arguments |
| T2 | both | `observe_only_execution_forbidden` (sf) | `registry.py:482`, `registry.py:490`; `execution.py:81-85`, `execution.py:105-109` | S1, bare code | OWNER-NEEDED | The wake was server-authored; only a Run the owner starts may trade |
| T3 | both | `delegated_financial_authority_forbidden` (sf) | `agent_binding.py:122-125` | S1 | DEAD-END (by design) | A delegated research agent never trades; its parent does |
| T4 | both | `agent_trading_account_mismatch`, `agent_trading_symbol_mismatch` (sf: fixed binding) | `agent_binding.py:81-84`; `market_binding.py:122`; `execution.py:88-92` | S1; `permission_denied` / `respect_scope` (`environment.py:56-69`) | RECOVERABLE-NOT-LED | Hand the request to the agent bound to that pair or to the Personal Agent |
| T5 | both | `agent_trading_binding_invalid`, `agent_ancestry_invalid`, `agent_not_found` | `agent_binding.py:75`, `agent_binding.py:80`, `agent_binding.py:120`, `agent_binding.py:130`, `agent_binding.py:104` | S1 | DEAD-END | Corrupt agent record; no tool repairs it |
| T6 | both | `broker_sessions_not_found` (wrong `account_id`, for example the external MetaApi id) | `packages/db/src/lonora_db/transactions.py:92` with `kind = "broker_sessions"` (`packages/db/src/lonora_db/broker_sessions.py:37`); reached at `trade.py:633`, `trade.py:651`, `execution.py:174` | S1; `not_found` / `inspect_existing_state` | RECOVERABLE-NOT-LED | `list_accounts` returns the `connection_id` (`packages/tools/src/lonora_tools/account.py:118-121`). `TradeRequest.account_id` has no description saying so (`trading.py:16`) |
| T7 | both | `broker_disabled` | `packages/adapters/src/lonora_adapters/brokers/base.py:36-37`; `execution.py:204-205`, `execution.py:414-415` | S1 or S3 | OWNER-NEEDED | Owner enables the connection |
| T8 | both | `broker_secret_required` | `packages/adapters/src/lonora_adapters/brokers/base.py:50-51` | S1 | OWNER-NEEDED | Owner supplies the broker token |
| T9 | both | `broker_credentials_rejected` | `metaapi.py:62-63` | S1 | OWNER-NEEDED | Owner renews the token |
| T10 | both | `broker_connection_timeout`, `broker_connection_unavailable`, `broker_rate_limited`, `broker_request_rejected` from pre-card reads (`trade.py:86-97`, `trade.py:185-191`) | `metaapi.py:64-82` | S1; transient codes get `temporary_unavailable` / `inspect_health` (`environment.py:44-45`), `safe_to_retry` false for a non-read tool (`environment.py:92`) | RECOVERABLE-NOT-LED | Retry later; nothing was sent |
| T11 | both | `broker_account_not_found` for an unknown symbol | `metaapi.py:57-58`; reached through `preflight.py:17` | S3 `failed` + code, no details | **BUG** | Misnamed: the recovery is `market_symbols` (`market.py:98`), but the code tells the model the account is missing |
| T12 | both | `broker_connection_unavailable` for a symbol spelling mismatch | `metaapi.py:470-474`, `metaapi.py:80-82` | S3; classified transient | **BUG** | Same as T11 |
| T13 | `trade_execute` | unknown symbol silently kept | `symbols.py:30-35`; `trade.py:632-634` | Later failure T11/T12; no candidate list | RECOVERABLE-NOT-LED | `market_symbols`, then retry with the broker's spelling |
| T14 | both | `shadow_execution_forbidden` (sf: no shadow trading) | `trade.py:309-311`; `execution.py:131-132` | S1 | DEAD-END (by design) | none; such a Run never trades |
| T15 | both | `agent_analysis_only` (sf: ladder) | `trade.py:315-317`; `packages/trading/src/lonora_trading/agent_permission.py:33-35` | S1 | OWNER-NEEDED | Owner raises the level; `owner_action_propose` can put a grant card (`packages/tools/src/lonora_tools/owner_actions.py:291-293`, kinds at `packages/contracts/src/lonora_contracts/owner_actions.py:20-28`). Result names neither |
| T16 | both | `trading_not_started` (sf) | `trade.py:226-238` | Card raised by the tool plus `recovery: "Say in one line that trading has not been started and that the owner's one tap on the card starts it; ask again after the tap."` | OWNER-NEEDED (well led; the model for other refusals) | Owner taps Start trading |
| T17 | both | `trading_disabled`, `emergency_stop` (sf: Stop new trading) | `packages/core/src/lonora_core/trading_control.py:15-18`; `trade.py:258-259`; `execution.py:180`, `execution.py:190`, `execution.py:356` | S1 bare code; `health_blocked` / `wait_for_authoritative_recovery` (`environment.py:82-88`) | OWNER-NEEDED | Owner taps Resume; `owner_action_propose` kind `resume_trading` exists but is not named. No card is raised here, unlike T16 |
| T18 | both | `trading_restriction_active` (sf: owner pause) | `packages/trading/src/lonora_trading/restrictions.py:112-116`; `trade.py:260-263`; `execution.py:231-237`, `execution.py:469-471` | Code only when raised before the reservation (evidence dropped, `trade.py:464-467`); `permission_denied` / `respect_scope` | OWNER-NEEDED | `trade_restriction_list` shows which pause; `owner_action_propose` kind `lift_restriction` puts the Lift card. Neither is named |
| T19 | both | pending approval (not a failure) | `trade.py:398-404` | `_runtime_wait` | LED-OK | Runtime waits on the card |
| T20 | both | `trade_approval_expired` | `trade.py:393-397` | `{status: "expired", code, approval_id}`, no `recovery` block (section 1) | OWNER-NEEDED | Owner taps «طلب جديد» (`trade.py:395-396`), which starts a new Run |
| T21 | both | `trade_approval_rejected` (sf: owner decided) | `trade.py:405-406`; repeated until the owner writes again (`trade.py:141-144`) | `status: "rejected"` + code | OWNER-NEEDED | Owner's next message |
| T22 | both | `trade_approval_unavailable` | `trade.py:413-414`, `trade.py:434-439`, `trade.py:478-479` | S1 / S3 | RECOVERABLE-NOT-LED | A fresh call raises a fresh card |
| T23 | both | `tool_call_superseded` (sf: the owner wrote while the trade was being sent) | `trade.py:446-447`, `trade.py:590-591` | S3 `failed` + code | OWNER-NEEDED | The owner's newer message decides |
| T24 | both | `trade_approval_broker_state_changed` (sf: "Never restore old SL/TP/volume merely because an old card was approved", `trade.py:448-449`) | `trade.py:450-453`; `packages/db/src/lonora_db/trade_approvals.py:229-230` | S3 | RECOVERABLE-NOT-LED | `account_read`, then a new request and a new card |
| T25 | both | `trade_approval_mismatch`, `trade_approval_request_changed`, `agent_run_mismatch`, `agent_thread_mismatch` | `trade.py:391-392`, `trade.py:420-423`, `trade.py:440-445`, `trade.py:355-356`, `trade.py:360-361` | S1 | DEAD-END | Internal invariants |
| T26 | both | `batch_halted_after_unconfirmed_result` (sf) | `trade.py:283-298` | per-request receipt with `send_state: not_sent`, `halted_after` | LED-OK | Unreachable today for these two tools: `trade_execute` sends one request (`docs/financial-execution-recovery.md:198`) and close-all is independent (`trade.py:266-280`) |
| T27 | both | `goal_step_required` | `execution.py:121-126`; set up by `trading_goal.py:73-78` | S3 `failed` + code | **BUG** (finding 7) | Plan trades: `goal_step_execute`. An unrelated close has no route in that Run |
| T28 | both | `goal_run_ancestry_invalid`, `goal_delegated_trade_forbidden` (sf) | `execution.py:100`, `execution.py:104`, `execution.py:118`, `execution.py:120` | S3 | DEAD-END (by design) | none in that Run |
| T29 | both | `task_execution_stopped`, `task_run_mismatch` (sf) | `execution.py:137-141` | S3 | OWNER-NEEDED | Owner resumes the Task |
| T30 | both | `idempotency_conflict`, `operation_reservation_released`, `operation_send_already_authorized` | `execution.py:167`, `execution.py:484`, `execution.py:322` | S3 | DEAD-END | Internal |
| T31 | both | `trade_approval_required` (approval vanished between card and send) | `agent_permission.py:38`, `agent_permission.py:62` | S3 | RECOVERABLE-NOT-LED | Call again; a card is raised |
| T32 | both | `broker_connection_changed` | `execution.py:201-202`, `execution.py:416-417` | S3 | RECOVERABLE-NOT-LED | Retry |
| T33 | both | `broker_account_mismatch`, `broker_trading_not_allowed` | `preflight.py:20-23` | S3 | OWNER-NEEDED | Connection points at another account, or it is a read-only (investor) login |
| T34 | both | `position_not_found`, `order_not_found` | `preflight.py:30-35`, `preflight.py:52-56` | S3; `not_found` / `inspect_existing_state` | RECOVERABLE-NOT-LED | `account_read` (`account.py:129-130`). Note `preflight.py:31` also requires the request's `symbol` to equal the position's symbol, so a right ticket with a wrong spelling is "not found" |
| T35 | both | `position_volume_exceeded`, `position_remaining_volume_invalid` | `preflight.py:36-49` | S3, no numbers | RECOVERABLE-NOT-LED | `account_read` for the volume, `market_instrument` for min/step (`market.py:107-108`) |
| T36 | `trade_execute` | `volume_out_of_range`, `volume_step_mismatch`, `price_tick_mismatch`, `broker_symbol_mismatch` | `packages/security/src/lonora_security/financial.py:9-18`; `packages/core/src/lonora_core/trading_run_market.py:4-6` | S3, no min/max/step/tick values | RECOVERABLE-NOT-LED | `market_instrument`, or `market_position_size` for a valid volume |
| T37 | `trade_execute` | `stop_loss_wrong_side`, `take_profit_wrong_side`, `pending_price_wrong_side`, `pending_stops_level`, `stop_loss_stops_level`, `take_profit_stops_level`, `unsupported_pending_order` | `preflight.py:70`, `preflight.py:93`, `preflight.py:120-132` | S3, no current price or stops level | RECOVERABLE-NOT-LED | `market_quote` and `market_instrument` |
| T38 | `trade_execute` | `market_quote_stale` | `preflight.py:84` | S3 | RECOVERABLE-NOT-LED | Market closed or quiet; wait. The result does not say when it opens |
| T39 | both | grant term refused at send after the pre-check passed: `account_authority_*` (sf: "it fails closed, never wider", `docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:584`) | `packages/trading/src/lonora_trading/account_authority.py:237-327` | S3 | RECOVERABLE-NOT-LED | Call again: the pre-check (`trade.py:501-530`) now drops the grant and raises a card |
| T40 | both | grant revoked or changed: `account_authority_not_found`, `account_authority_scope_changed`, `account_authority_unavailable`, `account_authority_changed`, `agent_paused`, `device_authorization_required` (sf) | `packages/db/src/lonora_db/account_authority.py:80-97`, `account_authority.py:183-199` | S1 / S3 | OWNER-NEEDED | Owner re-signs. For ordinary Runs these are swallowed and the trade asks instead (`packages/trading/src/lonora_trading/account_authority.py:100-104`) |
| T41 | both | `broker_observation_unavailable` (sf) | `packages/trading/src/lonora_trading/admission.py:225-227` | S3 | RECOVERABLE-NOT-LED | Wait for the reconciliation loop; exits stay admitted (`admission.py:223-224`) |
| T42 | both | `broker_reconciliation_required` (sf: an earlier operation is unresolved) | `admission.py:228-230` | S3 | OWNER-NEEDED | Owner settles the earlier operation (`resolve_operation` card kind, `owner_actions.py:23`) or broker evidence settles it |
| T43 | `trade_execute` | owner portfolio limits `portfolio_position_limit`, `portfolio_pending_order_limit`, `portfolio_direction_volume_limit` (sf) | `packages/trading/src/lonora_trading/exposure.py:60-83`; raised at `execution.py:337-343` | S3 with `details.execution_quality` | OWNER-NEEDED | Owner policy |
| T44 | `trade_execute` | `execution_spread_limit`, `execution_entry_deteriorated`, `execution_drift_reference_unavailable`, `planned_symbol_mismatch`, health reason codes | `packages/trading/src/lonora_trading/execution_quality.py:42-76` | S3 with `details.execution_quality` | RECOVERABLE-NOT-LED | Retry later; but see T50 |
| T45 | `trade_execute` | `risk_trade_limit`, `risk_stop_loss_required` (sf: money limits) | `packages/trading/src/lonora_trading/risk_limits.py:522-524`; `execution.py:373-384` | S3 with `details.risk_assessment`; `risk_limit_blocked` / `inspect_risk_assessment` (`environment.py:70-73`) | LED-OK | Resize or add a stop; but see T50 (a changed argument gives a new operation id, so this one works) |
| T46 | `trade_execute` | `risk_open_limit`, `risk_open_unbounded`, `risk_daily_loss_limit`, `risk_free_margin_floor`, `risk_limit_currency_mismatch` (sf) | `risk_limits.py:480`, `risk_limits.py:527-544` | as T45 | OWNER-NEEDED | Owner limit; exits remain |
| T47 | `trade_execute` | `risk_economics_unavailable`, `risk_daily_history_unavailable`, `risk_daily_history_incomplete`, `risk_daily_history_invalid` (sf: fail closed) | `risk_limits.py:89`, `risk_limits.py:124`, `risk_limits.py:297-299`, `risk_limits.py:316-318`, `risk_limits.py:356-368` | S3 `not_sent`, no assessment | RECOVERABLE-NOT-LED | Retry when broker data returns |
| T48 | `trade_execute` | thesis gates when `thesis_id` is passed: `opportunity_not_found`, `thesis_execution_scope_mismatch`, `thesis_not_confirmed` or an evidence code, `thesis_already_acted_on`, `thesis_operation_unresolved`, `thesis_execution_direction_mismatch` | `packages/trading/src/lonora_trading/opportunities.py:201-220` | S3 | RECOVERABLE-NOT-LED | `thesis_id` is optional (`trading.py:15`); omit it or update the thesis first. Not a money rule |
| T49 | both | broker rejection: the broker's own `stringCode` (for example `TRADE_RETCODE_*`), `broker_request_rejected`, `broker_order_rejected` | `metaapi.py:894`, `metaapi.py:931`, `metaapi.py:949`, `metaapi.py:1069` | S3 with `details.description` (broker English text, `metaapi.py:906-911`) | RECOVERABLE-NOT-LED | Depends on the code; no mapping from broker codes to a next step exists |
| T50 | `trade_execute` | identical retry after a post-reservation failure replays the stored `failed` receipt | `trade.py:635`; `execution.py:162-168`; `trade.py:145-147` | the same `failed` result again, after a second owner approval | **BUG** (finding 6, UNSURE: not executed) | Only a changed argument or a new Run produces a new operation |
| T51 | both | `operation_interrupted_before_send`, `broker_unavailable_before_send` | `execution.py:530-535` | S3 `not_sent` | RECOVERABLE-NOT-LED | Safe to ask again, but T50 applies |
| T52 | both | uncertain outcome (sf: never resend): status `ambiguous` / `submitted`, codes `broker_result_ambiguous`, `broker_result_mismatch`, `operation_in_progress`, `execution_not_observed`, `mutation_evidence_required` | `execution.py:63-68`, `execution.py:524-529`, `execution.py:633-637`; `metaapi.py:1023`, `metaapi.py:1081` | `ambiguous_mutation` / `reconcile_before_any_resend` (`environment.py:42-43`) | OWNER-NEEDED | Reconciliation loop or the owner's resolve card; an identical call reconciles the same operation (`tool_dispatch.py:55-69`) |
| T53 | `trade_close_positions` | `no_positions` | `trade.py:664-667` | `{"ok": True, "results": [], "code": "no_positions"}` | **BUG** when caused by spelling/case (finding 10); otherwise a true answer | `account_read` shows the real symbols |
| T54 | `trade_record_read` | `operation_not_found` | `trade.py:684-686` | S1; `not_found` | RECOVERABLE-NOT-LED | `trade_record_history` lists ids (`trade.py:713-732`) |
| T55 | `trade_record_history` | empty list for a symbol that differs in spelling (exact compare) | `trade.py:704-705` | `records: []` | RECOVERABLE-NOT-LED | Call without `symbol`, or with the broker spelling |

Counts, family `trade.py` (55 rows): RECOVERABLE-NOT-LED 22 (T4, T6, T10, T13, T22, T24, T31, T32, T34, T35, T36, T37, T38, T39, T41, T44, T47, T48, T49, T51, T54, T55); OWNER-NEEDED 18 (T2, T7, T8, T9, T15, T16, T17, T18, T20, T21, T23, T29, T33, T40, T42, T43, T46, T52); DEAD-END 6 (T3, T5, T14, T25, T28, T30); BUG 5 (T11, T12, T27, T50, T53); LED-OK 4 (T1, T19, T26, T45).

---

## 4. Family `trading_decision.py`

| # | Tool | Error code / outcome | path:line | What the model sees (hint?) | Class | Recovery path |
|---|---|---|---|---|---|---|
| D1 | record | `tool_arguments_invalid` incl. `conditional_entry_action_mismatch`, `conditional_entry_text_required` | `packages/contracts/src/lonora_contracts/trading_decision.py:31-36`, `trading_decision.py:116-120` (contract) | S2 | LED-OK | repair |
| D2 | record | `unsupported_timeframe` | `packages/core/src/lonora_core/chart_controller.py:29-31`; `trading_decision.py:61` | S1. The `timeframe` field has no description or enum (`packages/contracts/src/lonora_contracts/trading_decision.py:95`) | RECOVERABLE-NOT-LED | The accepted form is in another tool's schema: "e.g. 15m, 1h or 1mn; not M15/H1" (`market.py:26-28`) |
| D3 | record | `agent_trading_account_mismatch`, `agent_trading_symbol_mismatch` | `trading_decision.py:66`; `agent_binding.py:81-84` | S1 | RECOVERABLE-NOT-LED | Fixed agents record only their pair; route to the agent bound to the other pair |
| D4 | record | `broker_sessions_not_found` | `trading_decision.py:67-69`; `transactions.py:92` | S1 | RECOVERABLE-NOT-LED | `list_accounts` |
| D5 | record | `decision_intent_conflict` | `trading_decision.py:73-74`; `packages/db/src/lonora_db/trading_decisions.py:26` | S1 | DEAD-END | Internal (same call id, different arguments) |
| D6 | record | `relationship_not_found`, `relationship_scope_mismatch` | `packages/db/src/lonora_db/relationships.py:29`; `trading_decision.py:146-152` | S1, raised after up to 35 s of evidence capture; nothing is stored | RECOVERABLE-NOT-LED | Omit `relationship_ids` (optional, `packages/contracts/src/lonora_contracts/trading_decision.py:102`) or pass ids that match the pair |
| D7 | record | wrong symbol or failed reads do not fail the call: codes go to `evidence.missing_codes` and `gate_codes` and the record is stored | `trading_decision.py:110-121`, `trading_decision.py:156-159`, `trading_decision.py:179-202` | A stored decision whose gates read e.g. `broker_account_not_found` (finding 2) | RECOVERABLE-NOT-LED | `market_symbols`, then record again. The junk record stays (immutable ledger) |
| D8 | record | `execution_readiness.state` is never "ready" | `packages/contracts/src/lonora_contracts/trading_decision.py:68-82`; `packages/trading/src/lonora_trading/decision_readiness.py:115-143` | `BLOCKED` or `REVALIDATION_REQUIRED`, `execution_authorized: false` | RECOVERABLE-NOT-LED | The next step is `trade_execute`; no field says so |
| D9 | record | 90 s dispatch timeout → `tool_execution_uncertain`, then `broker_result_ambiguous` on retry | `base.py:16`; `tool_dispatch.py:118-128`, `tool_dispatch.py:71-75`; tool is not `replay_safe` (`trading_decision.py:282-288`) although the handler is idempotent (`trading_decision.py:71-75`) | misleading broker-ambiguity code | **BUG** (section 1) | none inside the Run with identical arguments |
| D10 | read, compare | `decision_not_found` | `trading_decisions.py:52-53` | S1; `not_found` | RECOVERABLE-NOT-LED | `market_decision_history` |
| D11 | compare | `decision_comparison_scope_mismatch` | `trading_decisions.py:79-85` | S1 | RECOVERABLE-NOT-LED | Pick two decisions of one account/symbol/timeframe from history |
| D12 | compare | `decision_comparison_order_invalid` | `trading_decisions.py:86-87` | S1 | RECOVERABLE-NOT-LED | Swap the two ids. The tool has both timestamps and could order them itself |
| D13 | history | empty list when the symbol filter differs in spelling | `trading_decision.py:230-241` | `decisions: []` | RECOVERABLE-NOT-LED | Call with the broker spelling or without `symbol` |

Counts, family `trading_decision.py` (13 rows): RECOVERABLE-NOT-LED 10 (D2, D3, D4, D6, D7, D8, D10, D11, D12, D13), OWNER-NEEDED 0, DEAD-END 1 (D5), BUG 1 (D9), LED-OK 1 (D1).

---

## 5. Family `trading_goal.py`

| # | Tool | Error code / outcome | path:line | What the model sees (hint?) | Class | Recovery path |
|---|---|---|---|---|---|---|
| G1 | create, plan | `tool_arguments_invalid` with `goal_trade_scope_mismatch`, `goal_watch_scope_mismatch`, `goal_watch_symbol_mismatch`, `goal_step_id_duplicate`, `goal_target_must_reference_prior_step`, `goal_trade_step_requires_declared_trade`, `goal_watch_condition_required`, `goal_deferred_target_invalid`, `goal_deferred_watch_invalid` | `packages/contracts/src/lonora_contracts/trading_goal.py:14-30`, `trading_goal.py:36-44`, `trading_goal.py:55-61`, `trading_goal.py:80-109` (contract) | S2 with code and path | LED-OK | repair. Friction: every step's `trade.account_id` and `trade.symbol` must repeat the goal's exactly (`trading_goal.py:93-96` contract); binding defaults fill only top-level fields (`market_binding.py:64-79`) |
| G2 | every mutating goal tool | `delegated_financial_authority_forbidden` (sf) | `market_binding.py:108-112`; `agent_binding.py:122-125` | S1 | DEAD-END (by design) | "You cannot ... create trading goals" for delegated agents (`agent_binding.py:141-143`) |
| G3 | create | `agent_trading_account_mismatch`, `agent_trading_symbol_mismatch` | `packages/db/src/lonora_db/trading_goals.py:94-96`; `market_binding.py:122` | S1 | RECOVERABLE-NOT-LED | Use the bound pair or another agent |
| G4 | create | `agent_thread_mismatch`, `goal_not_found` (id collision), `goal_execution_mode_invalid`, `execution_mode_changed` | `trading_goals.py:97-98`, `trading_goals.py:103-104`; `packages/db/src/lonora_db/goal_scope.py:14-20` | S1 | DEAD-END | Internal / removed Shadow mode |
| G5 | read, decisions, plan, complete, wait, execute, control | `goal_not_found` | `trading_goals.py:28-29`; `market_binding.py:128-131` | S1; `not_found` | RECOVERABLE-NOT-LED | `goal_list` |
| G6 | same | `goal_step_not_found` | `trading_goals.py:42-46` | S1 | RECOVERABLE-NOT-LED | `goal_read` returns the plan's step ids (`trading_goal.py:144-147`) |
| G7 | same | `goal_run_mismatch` (goal belongs to another chat or agent) | `trading_goal.py:129-130`, `trading_goal.py:158-159`, `trading_goal.py:195-196`, `trading_goal.py:230-231`, `trading_goal.py:282-283`, `trading_goal.py:467-468`; `packages/trading/src/lonora_trading/goals.py:375-376`, `goals.py:449-450` | S1 | OWNER-NEEDED | The goal lives in the conversation it was created in ("in this same agent/chat", `trading_goal.py:485`); the owner must speak there |
| G8 | plan, control | `version_conflict` | `trading_goals.py:145-146`, `trading_goals.py:192-193` | S1; `version_conflict` / `reload_authoritative_state` (`environment.py:46-47`) but no read tool returns the version | **BUG** (finding 8) | none that is read-only |
| G9 | plan, control | `goal_terminal` | `trading_goals.py:148-149`, `trading_goals.py:194-195` | S1 | DEAD-END (by design) | Create a new goal |
| G10 | plan | `goal_executed_step_immutable` (sf: executed steps are history) | `trading_goals.py:206-207` | S1 | RECOVERABLE-NOT-LED | Resend the plan with executed steps unchanged |
| G11 | complete, wait, execute | `goal_not_active` | `trading_goal.py:232-233`, `trading_goal.py:284-285`; `goals.py:464-465`, `goals.py:126-127`, `goals.py:575-579` | S1; the status is not in the result | RECOVERABLE-NOT-LED | `goal_read` shows the status; if `blocked`, see G20 |
| G12 | complete, execute | `goal_plan_changed` | `trading_goal.py:235-236`, `trading_goal.py:396-401`; `goals.py:130-135`, `goals.py:469-474` | S1 | RECOVERABLE-NOT-LED | `goal_read`, then call again |
| G13 | complete, execute | `goal_step_order` | `trading_goal.py:246-247`; `goals.py:451-452` | S1 | RECOVERABLE-NOT-LED | Act on `current_step` (omit `step_id`) |
| G14 | complete | `goal_trade_confirmation_required` (sf: "Cannot mark a trade completed; only actual broker confirmation can do that.", `trading_goal.py:520`) | `trading_goal.py:244-245` | S1 | RECOVERABLE-NOT-LED | `goal_step_execute` |
| G15 | complete, execute | `goal_watch_evidence_required` (sf: a watch step completes only in the Run its own watch woke) | `trading_goal.py:237-243`; `packages/trading/src/lonora_trading/goals_market.py:49-63`, `goals_market.py:82-83` | S1 | RECOVERABLE-NOT-LED | `goal_wait`, then act in the wake |
| G16 | complete, execute | `goal_condition_unmet`, `goal_condition_stale`, `goal_condition_unavailable`, `goal_calendar_requires_market_condition` | `goals_market.py:105`, `goals_market.py:126`, `goals_market.py:135`, `goals_market.py:154` | S1, the observed value is not returned | RECOVERABLE-NOT-LED | `goal_wait` |
| G17 | wait | `goal_step_unavailable` | `trading_goal.py:287-291` | S1 | RECOVERABLE-NOT-LED | `goal_read` |
| G18 | wait | `goal_wait_source_required` | `trading_goal.py:335-336` | S1 | RECOVERABLE-NOT-LED | `goal_plan` to add a condition or `review_interval_seconds` (needs G8's version) |
| G19 | wait, execute | `goal_target_confirmation_required`, `goal_target_ambiguous`; `goal_target_not_observed` becomes a waiting result with `code: goal_target_pending` | `packages/trading/src/lonora_trading/goals_targets.py:34-35`, `goals_targets.py:68-72`; `trading_goal.py:273-278`; `goals.py:610-615` | waiting result is self-explaining; the two errors are bare | RECOVERABLE-NOT-LED | Execute the entry step first; `goal_decisions` |
| G20 | execute, control | Goal `blocked` after any pre-journal executor error; resume refused with `goal_owner_retry_required` | `goals.py:532-551`; `trading_goal.py:471-477`; `trading_goals.py:162-176` | First call: the executor's bare code (re-raised, `goals.py:551`). Next execute: the stored failed result with `deduplicated: true` (`goals.py:381-388`). Resume: bare `goal_owner_retry_required` | OWNER-NEEDED (finding 9; safety for uncertain outcomes, over-caution for proved not-sent ones) | Owner presses resume in the Goals panel (`apps/web/src/components/goals/TradingGoals.tsx:145`); no chat card kind exists |
| G21 | control | `goal_reconciliation_required` (sf) | `trading_goals.py:150-160` | S1 | OWNER-NEEDED | Unresolved operation must be settled first |
| G22 | control | `goal_control_invalid` | `trading_goal.py:462-463`; `GoalToggle.action: str` has no enum (`trading_goal.py:58-60`) | S1 | RECOVERABLE-NOT-LED | Use pause / resume / cancel (named only in the description, `trading_goal.py:542`) |
| G23 | execute | `goal_trade_step_required` | `goals.py:389-390`, `goals.py:447-448` | S1 | RECOVERABLE-NOT-LED | `goal_step_complete` for non-trade steps |
| G24 | execute | `agent_analysis_only` (sf) | `goals.py:85-87` | S1 | OWNER-NEEDED | as T15 |
| G25 | execute | approval outcomes: wait, `trade_approval_expired`, `trade_approval_rejected` (sf) | `trading_goal.py:407-413`; `trade.py:393-406` | as T19-T21 | OWNER-NEEDED | Owner's card |
| G26 | execute | `agent_permission_changed`, `trade_approval_required`, `trade_approval_unavailable` (sf: level changed mid-flight) | `goals.py:466-468`, `goals.py:110-111`, `goals.py:427-428`, `goals.py:517-520` | S1 | RECOVERABLE-NOT-LED | Call again under the new level |
| G27 | execute | `operation_id_conflict`, `goal_decision_mismatch`, `goal_lease_required`, `trade_approval_mismatch` | `trading_goal.py:359-360`; `goals.py:122-123`, `goals.py:137-147`, `goals.py:498-501`; `trading_goal.py:424-429` | S1 | DEAD-END | Internal |
| G28 | execute | every executor outcome of section 3 (T7-T12, T17-T18, T27-T52) | `goals.py:522-531` | as section 3, then G20 | (counted in section 3) | |

Counts, family `trading_goal.py` (27 own rows, G28 excluded): RECOVERABLE-NOT-LED 16 (G3, G5, G6, G10, G11, G12, G13, G14, G15, G16, G17, G18, G19, G22, G23, G26), OWNER-NEEDED 5 (G7, G20, G21, G24, G25), DEAD-END 4 (G2, G4, G9, G27), BUG 1 (G8), LED-OK 1 (G1).

---

## 6. Family `restrictions.py`

| # | Tool | Error code / outcome | path:line | What the model sees (hint?) | Class | Recovery path |
|---|---|---|---|---|---|---|
| R1 | create | `tool_arguments_invalid` with `restriction_agent_scope_conflict`, `restriction_symbol_scope_conflict`, `restriction_window_invalid`; `reason` required | `packages/contracts/src/lonora_contracts/trading_restrictions.py:30-32`, `trading_restrictions.py:72-80` | S2 | LED-OK | repair |
| R2 | create | `restriction_account_required` | `restrictions.py:135-137` | S1 | RECOVERABLE-NOT-LED | `list_accounts`; an agent with no bound account must pass `account_id` even when the owner has one account |
| R3 | create | `agent_trading_symbol_mismatch` for `all_symbols` by a market-bound agent | `restrictions.py:138-140` | S1; `permission_denied` / `respect_scope` | RECOVERABLE-NOT-LED | Record it for the own market, or pass the request to the Personal Agent. The description says "(not for a market-bound agent)" (`restrictions.py:297-298`) |
| R4 | create | `symbol_not_found`, `symbol_ambiguous` | `symbols.py:6-15`, `symbols.py:38-56`; `restrictions.py:143-148` | S1, no candidates | RECOVERABLE-NOT-LED | `market_symbols`. Doc: "fails with `symbol_not_found` or `symbol_ambiguous` so the agent or owner corrects it" (`docs/account-authority.md:214-216`): the design expects the owner to correct a spelling |
| R5 | create | `restriction_all_mutations_requires_owner_message` (sf: "Freezing other agents also blocks their protective exits: the owner asks.", `restrictions.py:159`) | `restrictions.py:153-160` | S1; `permission_denied` | OWNER-NEEDED | The owner must ask in a Run that has read no external content: `owner_message_id` returns None once any web, feed, MCP or peer content was read (`restrictions.py:107-116`) |
| R6 | create | `restriction_supervision_required` (sf) | `restrictions.py:161-170` | S1 | OWNER-NEEDED | Owner's message or a supervision grant |
| R7 | create | `supervision_cycle` (sf) | `packages/db/src/lonora_db/supervision.py:499-503`; `restrictions.py:171-177` | S1 | OWNER-NEEDED | Owner's message |
| R8 | create | `restriction_valid_until_required`, `restriction_window_too_long` | `restrictions.py:179-184` | S1; the rule is in the description: "it is required, within 31 days, for another agent or all agents" (`restrictions.py:300-301`) | LED-OK (by description) | add / shorten `valid_until` |
| R9 | create | `restriction_window_invalid` (end not in the future) | `packages/db/src/lonora_db/trading_restrictions.py:161-164` | S1 | RECOVERABLE-NOT-LED | Needs the current time and the owner's timezone ("end of the owner's day, timezone-aware", `restrictions.py:299-300`). UNSURE: where the model gets the owner's timezone was not traced |
| R10 | create | `restriction_creator_invalid`, `restriction_owner_manual_owner_only`, `restriction_not_found`, `restriction_time_zone_required` | `trading_restrictions.py:141-157` | S1 | DEAD-END | Not reachable from the tool's inputs |
| R11 | create, list | lifting is owner-only (sf): output `"lift": "owner_only"` | `restrictions.py:238`, `restrictions.py:278` | A field, not an error; does not name the card | OWNER-NEEDED | `owner_action_propose` kind `lift_restriction` (`owner_actions.py:21-22` contract) puts the one-tap Lift card |

Counts, family `restrictions.py` (11 rows): RECOVERABLE-NOT-LED 4 (R2, R3, R4, R9), OWNER-NEEDED 4 (R5, R6, R7, R11), DEAD-END 1 (R10), BUG 0, LED-OK 2 (R1, R8).

---

## 7. Families `position_sizing.py`, `performance.py`, `opportunity.py`

### 7.1 `market_position_size` (read-only)

| # | Error code / outcome | path:line | What the model sees | Class | Recovery path |
|---|---|---|---|---|---|
| P1 | `tool_arguments_invalid` (all six fields required) | `packages/contracts/src/lonora_contracts/position_sizing.py:13-19` | S2 | LED-OK | repair |
| P2 | `broker_sessions_not_found` | `position_sizing.py:15`; `transactions.py:92` | S1 | RECOVERABLE-NOT-LED | `list_accounts` |
| P3 | unknown symbol → `broker_account_not_found`; case or spelling difference → `broker_connection_unavailable` | `packages/trading/src/lonora_trading/position_sizing.py:157-158`; `metaapi.py:57-58`, `metaapi.py:470-474`, `metaapi.py:80-82`. No case repair here, unlike `market_quote` (`market.py:56-58`) | S1, misleading code | **BUG** | `market_symbols` |
| P4 | `position_sizing_currency_mismatch` | `packages/trading/src/lonora_trading/position_sizing.py:34-35` | S1; the account's currency is not returned | RECOVERABLE-NOT-LED | `account_read`. The tool has just read the account and only compares; the model is made to supply a value the tool already holds |
| P5 | `position_sizing_account_mismatch` | `packages/trading/src/lonora_trading/position_sizing.py:32-33` | S1 | DEAD-END | Connection misconfigured |
| P6 | stale or missing quote/account: `market_quote_unavailable`, `receive_stale`, `timestamp_invalid`, `broker_account_unavailable`, ... | `packages/market/src/lonora_market/health.py:220-222`, `health.py:62-83`, `health.py:104`, `health.py:135`; 60 s maximum age (`packages/trading/src/lonora_trading/position_sizing.py:38-49`) | S1 | DEAD-END while the market is closed (over-caution: a read-only estimate refuses instead of answering with a stale label) | Wait for a live quote |
| P7 | `position_sizing_economics_unavailable`, `position_sizing_values_invalid`, `position_sizing_instrument_invalid`, `position_sizing_numeric_precision` | `packages/trading/src/lonora_trading/position_sizing.py:51-57`, `position_sizing.py:71-74`, `position_sizing.py:84-85` (trading package) | S1 | DEAD-END | Broker does not supply usable tick values |
| P8 | `stop_loss_wrong_side`, `stop_loss_stops_level` | `packages/trading/src/lonora_trading/position_sizing.py:90-98` | S1, no price returned | RECOVERABLE-NOT-LED | `market_quote`, `market_instrument` |
| P9 | `position_sizing_below_minimum` | `packages/trading/src/lonora_trading/position_sizing.py:105-106`, `position_sizing.py:118-119` (trading package) | S1; the per-lot loss and the minimum budget are computed (`position_sizing.py:104` trading package) but not returned | OWNER-NEEDED | A larger budget or a tighter stop is the owner's choice; the model cannot tell him the number he needs |

Counts (9 rows): RECOVERABLE-NOT-LED 3 (P2, P4, P8), OWNER-NEEDED 1 (P9), DEAD-END 3 (P5, P6, P7), BUG 1 (P3), LED-OK 1 (P1).

### 7.2 `market_performance_read` (read-only)

| # | Outcome | path:line | What the model sees | Class | Recovery path |
|---|---|---|---|---|---|
| F1 | `tool_arguments_invalid` (`minimum_sample` 5-1000) | `packages/contracts/src/lonora_contracts/execution_quality.py:77-83` | S2 | LED-OK | repair |
| F2 | any `strategy_version` filter returns zero records: `if params.strategy_version: continue` | `packages/trading/src/lonora_trading/performance.py:88-91` | `sample_count: 0`, `insufficient_data`, no reason | DEAD-END | none: no journal row carries a strategy identity |
| F3 | money result never available: `"monetary_pnl": None`, `"monetary_pnl_code": "contract_currency_valuation_unavailable"` | `performance.py:57-58` (trading package) | constant fields | DEAD-END (for this tool) | UNSURE: the account history tool (`account.py:112`) may answer profit questions; not traced |
| F4 | three of four promised dimensions are always `unavailable`: records carry only `quality.execution` | `performance.py:18-23`, `performance.py:104-113` (trading package) | `analysis`, `entry`, `management` → `{"unavailable": n}` | **BUG** | Description says "Separate analysis, entry, management and execution" (`packages/tools/src/lonora_tools/performance.py:34`); code wins |
| F5 | `minimum_sample` below 20 is silently raised to 20 | `performance.py:12`, `performance.py:39` (trading package) vs contract `ge=5` (`execution_quality.py:83`) | `minimum_sample: 20` | **BUG** (minor) | none |

Counts (5 rows): RECOVERABLE-NOT-LED 0, OWNER-NEEDED 0, DEAD-END 2 (F2, F3), BUG 2 (F4, F5), LED-OK 1 (F1).

### 7.3 `market_opportunity_*`

| # | Tool | Error code / outcome | path:line | What the model sees | Class | Recovery path |
|---|---|---|---|---|---|---|
| O1 | create, update | `tool_arguments_invalid` (`setup_key` pattern, `strategy_version` required, `thesis_timezone_required`, `thesis_decay_must_precede_expiry`, `reason_code` pattern) | `packages/contracts/src/lonora_contracts/opportunity.py:15-30`, `opportunity.py:34-41`, `opportunity.py:53-58` (contract) | S2 | LED-OK | repair |
| O2 | create | `unsupported_timeframe` | `packages/db/src/lonora_db/trading_opportunities.py:184`; `chart_controller.py:29-31` | S1 | RECOVERABLE-NOT-LED | as D2 |
| O3 | create, update | `decision_not_found`, `thesis_evidence_scope_mismatch` ("References must be real recorded decisions/watch", `opportunity.py:160`) | `trading_decisions.py:52-53`; `trading_opportunities.py:185-192`; `packages/trading/src/lonora_trading/opportunities.py:56-62` | S1 | RECOVERABLE-NOT-LED | `market_decision_history` for ids of the same pair and timeframe |
| O4 | create | `agent_trading_account_mismatch`, `agent_trading_symbol_mismatch` | `trading_opportunities.py:96` | S1 | RECOVERABLE-NOT-LED | bound pair |
| O5 | create | `agent_thread_mismatch`, `agent_not_group_member` | `trading_opportunities.py:98-107` | S1 | DEAD-END | Internal |
| O6 | create | `broker_sessions_not_found` | `trading_opportunities.py:108` | S1 | RECOVERABLE-NOT-LED | `list_accounts` |
| O7 | create | `opportunity_watch_scope_mismatch` | `trading_opportunities.py:109-119` | S1 | RECOVERABLE-NOT-LED | Omit `watch_id` or pass a matching watch |
| O8 | create | `thesis_expiry_invalid` | `trading_opportunities.py:131-132` | S1 | RECOVERABLE-NOT-LED | A future `expires_at` |
| O9 | read, update, version | `opportunity_not_found` | `trading_opportunities.py:33-34` | S1; `not_found` | RECOVERABLE-NOT-LED | `market_opportunity_list` |
| O10 | version | `thesis_version_not_found` | `opportunity.py:141-142` | S1 | RECOVERABLE-NOT-LED | `market_opportunity_read` lists versions in `history` (`opportunity.py:54-75`) |
| O11 | update | `version_conflict` | `opportunities.py:164-165` (trading package) | S1; `reload_authoritative_state` | RECOVERABLE-NOT-LED | `market_opportunity_read` returns `version` (`trading_opportunities.py:38-40`, `transactions.py:28`); the hint is generic but sufficient |
| O12 | update | `opportunity_intent_conflict`, `opportunity_agent_mismatch` | `opportunity.py:87-88`; `opportunities.py:162-163` (trading package) | S1 | DEAD-END | Another agent's thesis / internal |
| O13 | update | `thesis_terminal` | `opportunities.py:166-167` (trading package) | S1 | DEAD-END (by design: "Cannot ... revive an ended thesis", `opportunity.py:174`) | Create a thesis under a new `setup_key` |
| O14 | update | `thesis_execution_receipt_required` (sf-adjacent: "Cannot forge execution") | `opportunities.py:168-169` (trading package) | S1 | RECOVERABLE-NOT-LED | The status follows a real trade that carried `thesis_id` |
| O15 | update | `thesis_expired`, `thesis_extension_evidence_required`, `thesis_expiry_rule_not_met` | `opportunities.py:171-179`, `opportunities.py:192-193` (trading package) | S1 | RECOVERABLE-NOT-LED | Record a new decision and pass its id |
| O16 | update | confirm refused with the first evidence code: `thesis_evidence_required`, `thesis_decay_horizon`, `thesis_contradicting_evidence`, `thesis_direction_unconfirmed`, `relationship_evidence_unreliable`, `thesis_watch_*` | `opportunities.py:49-53`, `opportunities.py:73-76`, `opportunities.py:106-127`, `opportunities.py:189-191` (trading package) | S1, only the first code | RECOVERABLE-NOT-LED | `market_decision_record`, then update with that id |
| O17 | update | `thesis_invalidation_evidence_required` | `opportunities.py:194-195` (trading package) | S1 | RECOVERABLE-NOT-LED | The agent must first record a contradicting decision before it may mark its own thesis invalidated |

Counts (17 rows): RECOVERABLE-NOT-LED 13 (O2, O3, O4, O6, O7, O8, O9, O10, O11, O14, O15, O16, O17), OWNER-NEEDED 0, DEAD-END 3 (O5, O12, O13), BUG 0, LED-OK 1 (O1).

### 7.4 Totals

| Family | RECOVERABLE-NOT-LED | OWNER-NEEDED | DEAD-END | BUG | LED-OK | Rows |
|---|---|---|---|---|---|---|
| `trade.py` | 22 | 18 | 6 | 5 | 4 | 55 |
| `trading_decision.py` | 10 | 0 | 1 | 1 | 1 | 13 |
| `trading_goal.py` | 16 | 5 | 4 | 1 | 1 | 27 |
| `restrictions.py` | 4 | 4 | 1 | 0 | 2 | 11 |
| `position_sizing.py` | 3 | 1 | 3 | 1 | 1 | 9 |
| `performance.py` | 0 | 0 | 2 | 2 | 1 | 5 |
| `opportunity.py` | 13 | 0 | 3 | 0 | 1 | 17 |
| **Total** | **68** | **28** | **20** | **10** | **11** | **137** |

Rows group several codes that share one cause and one recovery path, so the row count is lower than the count of distinct codes. Shared runtime outcomes (section 1) are not in these counts.

---

## 8. Tool description sentences that tell the model to stop, ask, or not act

| Tool | Sentence (verbatim) | path:line | Verdict |
|---|---|---|---|
| `trade_execute` | "Otherwise propose the immutable operation using the real financial Approve and Reject controls in chat or voice and wait for confirmation; spoken or typed agreement is not approval." | `trade.py:755-756` | Needed for safety (approval card at the single executor) |
| `trade_execute` | "Reconcile ambiguous execution before retrying." | `trade.py:758` | Needed for safety |
| `trade_execute` | "When an immutable trading market is bound, omit account_id and symbol or pass that bound pair; never ask which pair or ask the owner to retype the symbol." | `trade.py:758-760` | Good, but it only covers bound agents. For the Personal Agent nothing says "resolve the symbol with `market_symbols`, do not ask" |
| `trade_execute` | "Read broker positions/orders first, including manually opened tickets." | `trade.py:760-761` | Reasonable; a read-only step |
| `trade_execute` | "Saved goals use goal_step_execute instead." | `trade.py:761` | Needed for the plan trades; over-broad in effect (finding 7) |
| `trade_close_positions` | "Never silently extend a reviewed operation to later positions. Reconcile an uncertain ticket before retrying it." | `trade.py:776-777` | Needed for safety |
| `trade_record_read` | "Never resubmit a trade from this record." | `trade.py:746` | Needed for safety |
| `trade_record_history` | "never reconstruct past decisions from current prices. This does not authorize execution." | `trade.py:739` | Honesty rule; harmless |
| `market_decision_record` | "create a durable Task watch/wait separately before claiming monitoring. Operational failures remain separate from your decision. This never authorizes or executes a trade." | `trading_decision.py:284` | True; combined with finding 11 it reads as a stop. Over-cautious wording: it never says what does execute |
| `goal_create` | "Saving a plan grants no authority; live actions follow current Agent permission and exact signed account scope. Do not promise profits." | `trading_goal.py:485` | Needed for safety |
| `goal_plan` | "executed steps are immutable and changed plans disable financial autonomy." | `trading_goal.py:514` | Stale. `update_plan` raises only `version_conflict`, `goal_terminal`, `goal_executed_step_immutable` and then resets the waiting step (`packages/db/src/lonora_db/trading_goals.py:187-226`); its own comment says "A changed plan restarts the step it waits on; its trades are checked when they run." (`trading_goals.py:218`). Nothing disables autonomy. Code wins; the sentence discourages re-planning for no reason |
| `goal_step_complete` | "Cannot mark a trade completed; only actual broker confirmation can do that." | `trading_goal.py:520` | Needed for safety |
| `goal_step_execute` | "No trading prohibits mutations, Ask me waits for the owner's approval card, On its own sends inside a matching signed grant and asks with an approval card outside it. Stop new trading and pauses still apply. ... ambiguity blocks retries." | `trading_goal.py:532` | Needed for safety. Omits that a proved not-sent failure also blocks retries (finding 9) |
| `goal_control` | "This tool cannot enable financial autonomy or expand financial limits." | `trading_goal.py:542` | Needed for safety. Omits that resume after a failed attempt is owner-only |
| `trade_restriction_create` | "all_mutations (no other broker changes; for another agent or all agents only when the owner's message asked)" | `restrictions.py:293-294` | Needed for safety |
| `trade_restriction_create` | "symbol (the broker must list it; ...)" | `restrictions.py:296` | Friction: it states the requirement without naming `market_symbols` |
| `trade_restriction_create` | "Only the owner can lift a restriction." | `restrictions.py:304` | Needed for safety; could name the Lift card tool |
| `market_position_size` | "Currency must exactly match the broker account currency, including cent units; no FX conversion. ... It is not a maximum-loss guarantee and authorizes no execution." | `position_sizing.py:24-27` | Second half needed (honesty). First half is over-caution: the tool reads the account itself and could fill the currency |
| `market_performance_read` | "small samples remain insufficient, returns are not profit/correctness, and no safety rules change." | `performance.py:34` | Honesty rule; together with F3 the tool can never answer a profit question |
| `market_opportunity_create` | "References must be real recorded decisions/watch; creating a thesis never authorizes trading." | `opportunity.py:160` | Fine |
| `market_opportunity_update` | "Cannot forge execution or revive an ended thesis." | `opportunity.py:174` | Fine |
| Identity frame for bound agents | "Never ask which pair, account, or symbol, and never ask the owner to repeat or retype it. Letter case is not a different symbol; never strip suffixes." | `agent_binding.py:14-16` | The right rule, but it is rendered only when the agent has both an account and a symbol bound (`agent_binding.py:177-190`). The Personal Agent's frame says only "Read authorized owner accounts and exact broker symbols" (`agent_binding.py:150-151`). "never strip suffixes" also tells the model not to try the neighbouring spelling |

---

## 9. LEAKS: internal codes, ids and English system text that can reach the owner

1. **Raw error codes in the reply text.** The model receives only codes (section 1) and the reply guard does not remove them (`public_reply.py:3`, `public_reply.py:37-51`). The owner's example, with `symbol_not_found` and `broker_account_not_found` in bold, is the direct result. Doc disagreement: `docs/persistent-trading-teammate.md:58-62` versus the code; code wins.
2. **Raw broker codes.** A broker rejection is returned with `code=str(response.get("stringCode") or "")` (`metaapi.py:894`) or `code=string_code` (`metaapi.py:949`): MetaTrader strings such as those listed in `packages/trading/src/lonora_trading/retcodes.py:120-141` go to the model unchanged.
3. **Broker English text on an owner card.** `details.description` is the broker's own message (`metaapi.py:906-911`, `metaapi.py:951-954`). The order card uses it as the reason when the shared table has no text: `financialBoundaryError(code, i18n.locale) ?? (typeof details.description === "string" && details.description ? details.description : null)` (`apps/web/src/conversation/Cards.tsx:334-336`). An Arabic owner then sees an English broker sentence.
4. **Codes with no owner text.** The shared table (`packages/core/src/financial-boundary.ts:21-131`) covers the brakes, `risk_*`, reconciliation and restriction codes. It has no entry for the preflight and validation codes of rows T33-T38, the `account_authority_*` codes, `goal_step_required`, the `thesis_*` codes or any broker `stringCode`; `financialBoundaryError` returns null for them (`financial-boundary.ts:137-143`). The card then shows the status with no reason, and the only explanation the owner gets is the model's reply built from the bare code. `docs/trading-safety.md:113-114` says of the safety sheet "No ids, codes or JSON are shown"; that holds for the sheet, not for the conversation.
5. **`broker_account_not_found` has an owner string that is wrong for the symbol case**: `t\`Broker account not found.\`` (`apps/web/src/lib/user_error.ts:156-157`). With finding 2 the owner is told his account is missing when the symbol was mistyped.
6. **Internal ids in tool results the model may quote.** `trade_execute` returns `approval_id` and `operation_id` (`trade.py:494-498`); `goal_step_execute` returns `decision_id`, `operation_id` (`goals.py:554-558`); `goal_decisions` returns `run_id` (`packages/db/src/lonora_db/trading_goals.py:258-272`); `market_decision_history` returns `recorded_by.agent_id` (`trading_decision.py:216-222`); `goal_wait` builds the routine prompt "Review saved goal {goal.id}, step {step.id}..." (`trading_goal.py:324`). These ids are UUIDs (`packages/session/src/lonora_session/idempotency.py:7-8`), which the reply guard redacts to `[REDACTED]` unless declared public (`public_reply.py:10`, `public_reply.py:65-67`): a leak becomes a visible `[REDACTED]` token instead. Step ids chosen by the model (`packages/contracts/src/lonora_contracts/trading_goal.py:48`) are not UUIDs and pass.
7. **English system strings inside results.** `evidence_note` ("Account and exact decision receipt retained; ... Full owner API history remains available.", `trading_goal.py:187`), `details_tool` (`trade.py:730`, `trading_goal.py:118`), `"lift": "owner_only"` (`restrictions.py:238`), `interpretation_code` and `monetary_pnl_code` (`packages/trading/src/lonora_trading/performance.py:58`, `performance.py:67`), the `start_trading_card` recovery sentence (`trade.py:236-237`). These are model-facing and fine as instructions; they become leaks only when echoed.
8. **Decision records store the error codes permanently.** `gate_codes` and `evidence.missing_codes` of a decision hold codes like `broker_account_not_found` (`trading_decision.py:156-159`, `trading_decision.py:194`); `market_decision_read` and `market_decision_history` replay them into later conversations.

No secret is printed by any of these tools: stored tool results pass `redact` (`tool_results.py:35`, `tool_results.py:46`), exception text is never copied to the model (`tool_dispatch.py:129-138`), and broker messages pass `safe_exception_message` with the adapter's redaction list (`metaapi.py:240-243`).

---

## 10. TECHNICAL QUESTIONS: where the contract pushes the model to ask the owner for something it could look up

| # | What the model must supply | Contract | Could be resolved by | Effect on the owner |
|---|---|---|---|---|
| Q1 | The exact broker symbol, suffix included | `trading.py:30`; `trading_decision.py:94` (contract); `position_sizing.py:15` (contract); `trading_goal.py:70` (contract); only letter case is repaired, and only in some tools (`symbols.py:18-35`, `trade.py:632-634`) | `market_symbols` on the same account (`market.py:98-100`); a not-found error could carry the closest catalog names | «ضع حرف m يعني XAUUSDM». The owner's quoted reply ends with an offer to search "if you want" instead of searching |
| Q2 | The internal `connection_id` as `account_id` | `trading.py:16` (no description); `trade.py:52-54`; `restrictions.py:135-137` | `list_accounts` (`account.py:118-121`); when the owner has one account the tool could default to it | "Which account?" |
| Q3 | `position_id` and the matching `symbol` to close or modify one position | `trading.py:91-92` (`position_required`); `preflight.py:30-35` | `account_read`; the symbol is implied by the ticket | A request like "close the gold trade" needs two exact identifiers |
| Q4 | Account `currency` for sizing | `position_sizing.py:18` (contract); compared only (`packages/trading/src/lonora_trading/position_sizing.py:34-35`) | The tool already holds `account.currency` | "What currency is your account in?" |
| Q5 | `risk_budget` as an absolute amount | `position_sizing.py:17` (contract) | `account_read` for equity, then a percentage | "How many dollars do you want to risk?" when the owner said a percentage |
| Q6 | Goal row `version` | `trading_goal.py:58-60`; contract `trading_goal.py:113`, `trading_goal.py:118` | Not readable (finding 8) | The agent cannot pause or cancel its own goal on a later day and may ask the owner to do it |
| Q7 | Timeframe in Lonora's spelling | `trading_decision.py:95` (contract); `chart_controller.py:29-31` | Normalising `H1`/`M15`, or an enum in the schema | A format question or a failed record |
| Q8 | `valid_until` as a timezone-aware instant for "today" | `restrictions.py:299-300`; `trading_restrictions.py:42-43` (contract) | A server-side "end of owner's day" option. UNSURE: whether the owner's timezone is in the model's context | "Until what time exactly?" |
| Q9 | Decision ids as evidence before a thesis may be confirmed or invalidated | `opportunities.py:52-53`, `opportunities.py:194-195` (trading package) | `market_decision_record` first | None directly; adds steps where the agent may stop |
| Q10 | `strategy_version` and `setup_key` for a thesis | `opportunity.py:21`, `opportunity.py:38` (contract) | The model can invent them; no meaning is enforced | Possible question about a "strategy version" the owner never defined |

---

## 11. Which refusals the money-safety rules require, and which go beyond them

**Needed for safety (keep):**

- Approval card or signed grant before any send: `trade.py:301-342`, `agent_permission.py:19-62`; monotonic ladder (a trade no grant covers asks instead of refusing, `trade.py:334-339`). This part already behaves as the owner wants: it asks with a card, never refuses.
- Brakes before cards for new risk only: `trade.py:241-263`. Exits are not refused there ("a close, cancel or tightening is still asked", `trade.py:250-252`) and the executor exempts risk-reducing requests from Stop (`trading_control.py:13-14`), from unresolved-operation blocks (`admission.py:223-224`), from agent-authored restrictions (`packages/trading/src/lonora_trading/restrictions.py:56-57`) and from money limits (`execution.py:357-360`).
- No resend after uncertainty: `execution.py:511-535`, `tool_dispatch.py:55-69`.
- Observe-only wakes, helpers and delegated agents never trade: `base.py:39-49`, `registry.py:481-490`, `agent_binding.py:108-130`.
- No shadow trading: `trade.py:309-311`, `execution.py:130-132`, `goal_scope.py:13-15`.
- Lifting a restriction is the owner's act: `restrictions.py:1-6`.
- Freezing other agents' exits needs the owner's own words: `restrictions.py:153-160`.

**Friction beyond the money rules (candidates to change without touching the rules above):**

- A read-only estimate that refuses on a stale quote or on a currency string (P4, P6).
- Symbol and account identifiers the tools could resolve (Q1-Q4), and the two misleading broker codes (T11, T12, P3).
- Bare codes with no next step for failures that never touched money: validation and preflight rows T34-T38, all of sections 4, 7.1 and 7.3.
- `trading_disabled` and `trading_restriction_active` return a bare code while `trading_not_started` raises the card itself and says what to tell the owner (`trade.py:206-238`). The same pattern would fit both. Note the two texts disagree on who offers the card: the code's docstring says "the agent offers the owner's Resume or Lift card" (`trade.py:248-250`), the doc says "the agent proposes the Resume or Lift card only when the owner asks" (`docs/trading-safety.md:46-47`). Neither is enforced in this tool; the handler only raises the code (`trade.py:258-263`).
- Goal blocked after a proved not-sent failure, with owner-only resume and no chat card (G20).
- Goal-linked Runs unable to close a position through the ordinary tools (T27).
- `goal_control` / `goal_plan` version that cannot be read (G8).
- Stale-receipt replay after a not-sent failure (T50).
- `trade_close_positions`, `goal_step_execute`, `market_position_size` and both restriction tools are not in the eager set (section 2); the model reaches them only through `tool_environment` and `tool_call`.

---

## 12. Doc versus code disagreements found (code wins)

| Doc says | Code does |
|---|---|
| A not-sent result "asks again" (`docs/account-authority.md:78-80`) | It asks again, but the executor replays the stored receipt for the same operation id (`trade.py:635`, `execution.py:162-168`). UNSURE: not executed |
| "lexical disclosure policy ... Private final narration gets at most one rewrite" (`docs/persistent-trading-teammate.md:58-62`) | The guard covers credentials, private paths and UUIDs only (`public_reply.py:37-51`); error codes pass |
| "the agent proposes the Resume or Lift card only when the owner asks" (`docs/trading-safety.md:46-47`) | Docstring: "the agent offers the owner's Resume or Lift card" (`trade.py:248-250`); the handler does neither |
| `market_performance_read`: "Separate analysis, entry, management and execution" (`packages/tools/src/lonora_tools/performance.py:34`) | Only `execution` is ever populated (`packages/trading/src/lonora_trading/performance.py:104-113`) |
| `goal_plan`: "changed plans disable financial autonomy" (`trading_goal.py:514`) | `update_plan` changes no permission or grant (`packages/db/src/lonora_db/trading_goals.py:187-226`) |
| "fails with `symbol_not_found` ... so the agent or owner corrects it" (`docs/account-authority.md:214-216`) | Matches the code (`symbols.py:6-15`); recorded here because the design itself assigns spelling correction to the owner |
| Market assessment "needs ... a supporting condition independently evaluated by the existing detector" (`docs/decision-readiness.md:13-15`) | The contract says supporting detector observations "are optional" (`packages/contracts/src/lonora_contracts/trading_decision.py:103-106`) and the tool description says "Optional detector observations assist your analysis" (`trading_decision.py:284`). In `decision_readiness.py:65-70` (trading package) a missing `market_view` adds `market_interpretation_not_supplied` and the supporting condition is inspected only when supplied. UNSURE: which bias results when no supporting condition is supplied was not traced |

---

## 13. What was not confirmed

- UNSURE: the HTTP status MetaApi returns for an unknown symbol on `get_symbol_specification` / `get_symbol_price` (finding 2 depends on it being 404).
- UNSURE: T50 and T27 were derived by reading; no test was run and no transcript exists.
- UNSURE: whether `execution_state.environment` (route failure counts) is carried from one Run to the next.
- UNSURE: whether any context frame outside `packages/agent-runtime/src/lonora_agent/context/` exposes a goal's row `version`.
- Not covered here (other groups): the operating-policy chapter texts for the `trading`, `goals` and `intelligence` toolsets, the simulation broker's error codes, and the Mobile card rendering.
