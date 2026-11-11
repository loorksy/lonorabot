# Parity inventory, part 1: owner actions versus agent tools (trading scope)

Repository `/home/user/lonorabot`, main HEAD `9f5b1da`. Read-only audit. All paths are relative to the repository root.

Scope of part 1: trading, broker accounts and connections, account authority (grants, trading level, restrictions, brakes, limits), positions and orders, market bindings, charts, watches, tasks, routines, goals, attention and notifications, supervision.

Evidence used:

- Code, cited as `path:line`.
- The live tool registry, dumped by `scripts/parity_trading_registry.py` into `runs/parity_trading_registry.txt` (126 tools).
- A scripted run against the real runtime: `scripts/parity_trading_probe.py`, output `runs/parity_trading_probe.out`. Model turns are SCRIPTED; the evidence is the tool results and the owner-route responses.
- Another auditor's run `runs/conv-C-watches.out` (script `scripts/conv_c_watches.py`), which I read and reuse only for the watch results quoted below.

(The two `scripts/` and `runs/` folders are under `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/`.)

---

## 1. Result in short

- 64 owner actions in scope. 27 have an agent tool that works on any of the owner's resources. 8 are handled by a card (6 the agent can raise, 2 are the owner's own tap or passkey). 29 are gaps.
- Gaps by class: NO-TOOL 17, TOOL-BUT-OWN-AGENT-ONLY 7, READ-ONLY-GAP 5, TOOL-BUT-NOT-EXPOSED-TO-PERSONAL-ASSISTANT 0 (see section 2.3 for why it is 0 and what "discovery-only" costs).
- The personal assistant can pause and resume another agent's watch, task or routine, but it cannot cancel, extend, edit or delete any of them. The owner can do all of that from the interface.
- No agent tool and no card exists for: the global "stop new trades" brake, revoking a grant, lowering the trading level, disconnecting a broker account, deleting or editing a routine, deleting a watch or a task, marking a task completed, the agent goals list, and every notification setting.
- Every tool that cancels, pauses, lists or closes is "discovery-only" for the personal assistant: its schema is not in the native tool list; the model must call it through `tool_call`.

---

## 2. How exposure and ownership work (applies to the whole table)

### 2.1 Which tools the personal assistant gets natively

- Profiles for a run: `core`, plus `market` when the agent is bound to a broker account or its role is `personal`, plus `coordination` for the personal agent (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:43`, `packages/agent-runtime/src/lonora_agent/tool_exposure.py:44`, `packages/agent-runtime/src/lonora_agent/tool_exposure.py:46`).
- The registry dump gives 23 native tools for those three profiles: `account_read, list_accounts, chart_snapshot, agent_inspect, peer_send, tool_call, tool_environment, market_decision_history, market_decision_record, market_candles, market_instrument, market_quote, market_sessions, market_snapshot, watch_create, memory_read, memory_write, session_search, skill_view, skills_list, web_search, wait_for_input, trade_execute` (`runs/parity_trading_registry.txt`, lines marked `personal=NATIVE`). This is the same list of 23 the lead reports from the production runs (`TIMELINE_CORRECTION.md`, point 2).
- Every other registered tool is "discovery-only": its name is listed in the capability inventory text (`packages/tools/src/lonora_tools/registry.py:406`), and it is called through `tool_call` (`packages/tools/src/lonora_tools/registry.py:167`). I ran `capability_inventory()` on main: 3056 characters, "Listed 126 of 126 permitted capabilities", and it contains `watch_cancel`, `watch_list`, `trade_close_positions`, `task_control`, `routine_toggle`, `agent_control`, `owner_action_propose`.
- Exposure is presentation only. The comment in the code says so: "any registered tool stays reachable via tool_call" (`packages/tools/src/lonora_tools/base.py:24`).

### 2.2 Ownership rules found

| Resource | Agent tool filter | Owner route filter |
|---|---|---|
| Watch | Own agent only: `steered_watch` raises `market_watches_not_found` when `row.agent_id != agent_id` (`packages/db/src/lonora_db/market_watches.py:123`); the tools pass `agent_id=context.agent_id` (`packages/tools/src/lonora_tools/market_watch.py:180`, `packages/tools/src/lonora_tools/market_watch.py:209`); `watch_list` lists `context.agent_id` only (`packages/tools/src/lonora_tools/market_watch.py:154`) | Owner only: `control_watch(session, owner.id, watch_id, body.action)` with no agent (`apps/api/src/lonora_api/routes/watches.py:41`) |
| Task | Own agent only: `task_agent_mismatch` (`packages/db/src/lonora_db/tasks.py:411`); `task_inspect` refuses another agent's task (`packages/tools/src/lonora_tools/tasks.py:57`) | Owner only (`apps/api/src/lonora_api/routes/tasks.py:59`) |
| Routine | List and create: own agent (`packages/tools/src/lonora_tools/routine.py:46`, `packages/tools/src/lonora_tools/routine.py:32`). Toggle: own, or a supervised agent's through the supervision rules (`packages/tools/src/lonora_tools/routine.py:58`, `packages/tools/src/lonora_tools/routine.py:86`) | Owner only (`apps/api/src/lonora_api/routes/routines.py:52`, `apps/api/src/lonora_api/routes/routines.py:64`) |
| Trading goal | Own agent and the same conversation only: `goal_run_mismatch` (`packages/tools/src/lonora_tools/trading_goal.py:467`, `packages/tools/src/lonora_tools/trading_goal.py:129`, `packages/tools/src/lonora_tools/trading_goal.py:158`); list filter (`packages/tools/src/lonora_tools/trading_goal.py:93`) | Owner only (`apps/api/src/lonora_api/routes/trading_goals.py:69`) |
| Another agent's work through supervision | `agent_control`: `pause` or `resume` only, on target `agent`, `task`, `routine` or `watch` (`packages/contracts/src/lonora_contracts/supervision.py:16`, `packages/contracts/src/lonora_contracts/supervision.py:17`). Needs a supervision grant, or the owner's message when the caller is the personal agent (`packages/db/src/lonora_db/supervision.py:658`). The personal agent supervises every agent by default (`packages/contracts/src/lonora_contracts/supervision.py:5`) | not applicable |
| Broker account, account state, journal, charts | Owner-wide: `list_accounts` (`packages/tools/src/lonora_tools/account.py:49`), `account_read` (`packages/tools/src/lonora_tools/account.py:71`), journal (`packages/tools/src/lonora_tools/trade.py:701`, `packages/tools/src/lonora_tools/trade.py:685`), charts (`packages/tools/src/lonora_tools/chart_state.py:160`, `packages/tools/src/lonora_tools/chart_state.py:181`) | Owner only |
| Fixed-market binding | A fixed-market agent's mutations must stay on its pair (`packages/tools/src/lonora_tools/market_binding.py:122`). The personal agent has no bound account or symbol, and `assert_market_binding` returns without a check for role `personal` with an empty binding (`packages/db/src/lonora_db/agent_binding.py:73`). So the binding does not restrict the personal agent | not applicable |

Scripted confirmation (`runs/parity_trading_probe.out`; agent T is another agent of the same owner, its routine, task and watch were created through the owner routes):

- `watch_list`, `routine_list`, `task_inspect`, `goal_list`, `owner_attention_list` called by the personal agent all return empty lists while T holds one watch, one routine and one task.
- `agent_inspect` (T, section `work`) returns T's watch, routine and task with their ids.
- `task_inspect` with T's task id: `{"ok": false, "code": "task_agent_mismatch"}`.
- `task_control` cancel on T's task: `task_agent_mismatch`. `watch_cancel` and `watch_update` on T's watch: `market_watches_not_found`.
- `routine_toggle` on T's routine with `enabled=false`: ok, `"enabled": false`.
- `agent_control` `pause` on T's task and on T's watch: ok, `"changed": true, "paused": true`. `agent_control` with `action="cancel"`: `tool_arguments_invalid` (`"path": ["action"], "type": "literal_error"`).
- The owner routes on the same rows then succeed: `POST /tasks/control` cancel gives `"status": "cancelled"`; `PUT /routines/{id}` changes the interval; `DELETE /routines/{id}`, `DELETE /watches/{id}` and `DELETE /trading/connections/{id}` give `{"deleted": true}`.
- `runs/conv-C-watches.out` shows the same for watches: `watch_cancel`, `watch_pause`, `watch_update` on another agent's watch give `market_watches_not_found`; `agent_control` pause and resume on it succeed.

### 2.3 Why TOOL-BUT-NOT-EXPOSED-TO-PERSONAL-ASSISTANT is 0

No profile removes a tool from the personal agent; every registered tool is callable through `tool_call`. What exists instead is the discovery-only cost: the schema is absent, and the search that should find the tool is weak. In my run, `tool_environment` returned an empty list for the queries "stop all trading emergency brake", "edit routine schedule", "disconnect broker account" and "mark notification seen", returned `workspace_update` and `chart_annotate` for "delete routine", and `subagent_spawn` and `trade_restriction_create` for "cancel task another agent" (`runs/parity_trading_probe.out`, block "R5"). The search gate is the rarest query word (`packages/tools/src/lonora_tools/tool_discovery.py:62`). Other sessions are fixing discovery and the visibility of `watch_list`, `watch_cancel` and `trade_close_positions`; I only record the state.

A model that guesses a name for a missing tool gets `tool_call_target_unknown` (`packages/tools/src/lonora_tools/registry.py:222`); my run got it for `routine_delete`, `watch_delete`, `task_complete`, `trading_stop` and `broker_disconnect`.

In the table below, "D" marks a covered action whose tool is discovery-only for the personal assistant, "N" a native one.

---

## 3. Class definitions used

- NO-TOOL: no agent tool performs the action on any resource, and no card kind stands in for it.
- TOOL-BUT-OWN-AGENT-ONLY: a tool performs the action, but only on resources of the calling agent; another agent's resource is refused or reads as not found.
- TOOL-BUT-NOT-EXPOSED-TO-PERSONAL-ASSISTANT: a tool exists but the personal assistant cannot call it at all. None found (section 2.3).
- CARD-ONLY: the agent cannot perform the action; it can raise a card, or the action is the owner's tap on a card. Listed with the safety rule. Not counted as an open gap.
- READ-ONLY-GAP: the owner action is a read (a list, a detail view, a history) and the agent has no tool that reads the same data.

The owner-side card rule, quoted from the tool module: "Agents propose; only the owner acts." and "widening money authority (a grant, or raising a money limit) needs the owner's passkey there" (`packages/tools/src/lonora_tools/owner_actions.py:1`, `packages/tools/src/lonora_tools/owner_actions.py:6` to `packages/tools/src/lonora_tools/owner_actions.py:7`). Card kinds an agent can raise: `resume_trading`, `lift_restriction`, `resolve_operation`, `set_account_limits`, `grant_authority`, `trust_source`, `connect_credential` (`packages/contracts/src/lonora_contracts/owner_actions.py:20`).

---

## 4. Routes in scope

Routers are mounted under `/api` (`apps/api/src/lonora_api/app.py:126`). `resource_router` generates list, create, read, update and delete (`apps/api/src/lonora_api/routes/__init__.py:16`, `apps/api/src/lonora_api/routes/__init__.py:35`, `apps/api/src/lonora_api/routes/__init__.py:50`, `apps/api/src/lonora_api/routes/__init__.py:57`, `apps/api/src/lonora_api/routes/__init__.py:69`).

| Method and path | Handler | A client calls it? (one call site) |
|---|---|---|
| GET /trading/controls | `apps/api/src/lonora_api/routes/trading.py:41` | yes, `apps/web/src/lib/trading.ts:15` |
| PUT /trading/controls | `apps/api/src/lonora_api/routes/trading.py:48` | yes, `apps/web/src/lib/trading.ts:17` |
| GET /trading/connections | `apps/api/src/lonora_api/routes/trading.py:55` | yes, `apps/web/src/lib/trading.ts:11` |
| POST /trading/connections | `apps/api/src/lonora_api/routes/trading.py:65` | yes, `apps/web/src/lib/trading.ts:13` |
| DELETE /trading/connections/{id} | `apps/api/src/lonora_api/routes/trading.py:80` | yes, `apps/web/src/shell/settings/ConnectionPages.tsx:287` |
| GET /trading/accounts/{id} | `apps/api/src/lonora_api/routes/trading.py:96` | yes, `apps/web/src/lib/trading.ts:14` |
| POST /trading/connections/{id}/simulation | `apps/api/src/lonora_api/routes/trading.py:106` | yes, `apps/web/src/components/trading/BrokerConnection.tsx:35` |
| POST /trading/connections/test | `apps/api/src/lonora_api/routes/connection_tests.py:86` | yes, `apps/web/src/shell/settings/ConnectionPages.tsx:173` |
| POST /trading/execute | `apps/api/src/lonora_api/routes/trading.py:116` | yes, `apps/web/src/lib/trading.ts:29` |
| GET /trading/journal | `apps/api/src/lonora_api/routes/trading.py:123` | yes, `apps/web/src/conversation/Conversation.tsx:180` |
| POST /trading/journal/{id}/resolve | `apps/api/src/lonora_api/routes/trading.py:137` | yes, `apps/web/src/lib/trading.ts:32` |
| GET /trading/approvals | `apps/api/src/lonora_api/routes/trading.py:169` | yes, `apps/web/src/components/trading/TradeApprovals.tsx:57` |
| POST /trading/approvals/{id}/decision | `apps/api/src/lonora_api/routes/trading.py:228` | yes, `apps/web/src/components/trading/TradeApprovals.tsx:86` |
| POST /trading/approvals/{id}/renew | `apps/api/src/lonora_api/routes/trading.py:247` | yes, `apps/web/src/conversation/Conversation.tsx:808` |
| GET /trading/restrictions | `apps/api/src/lonora_api/routes/trading_restrictions.py:26` | no caller found |
| POST /trading/restrictions | `apps/api/src/lonora_api/routes/trading_restrictions.py:42` | yes, `apps/web/src/conversation/sheets/AgentSheet.tsx:515` |
| POST /trading/restrictions/{id}/revoke | `apps/api/src/lonora_api/routes/trading_restrictions.py:75` | yes, `apps/web/src/lib/trading.ts:24` |
| GET, PUT /trading/accounts/{id}/execution-policy | `apps/api/src/lonora_api/routes/execution_policy.py:64`, `apps/api/src/lonora_api/routes/execution_policy.py:74` | yes, `apps/web/src/conversation/sheets/LimitsSheet.tsx:145` |
| POST .../execution-policy/challenge, /verify | `apps/api/src/lonora_api/routes/execution_policy.py:93`, `apps/api/src/lonora_api/routes/execution_policy.py:116` | yes, `apps/web/src/conversation/sheets/LimitsSheet.tsx:149` |
| GET .../risk-status, GET .../exposure | `apps/api/src/lonora_api/routes/execution_policy.py:146`, `apps/api/src/lonora_api/routes/execution_policy.py:169` | no caller found |
| GET, POST /agents/{id}/account-authorities | `apps/api/src/lonora_api/routes/account_authority.py:25`, `apps/api/src/lonora_api/routes/account_authority.py:41` | yes, `apps/web/src/components/permissions/AgentPermissions.tsx:396` |
| POST /agents/{id}/account-authorities/draft | `apps/api/src/lonora_api/routes/account_authority.py:70` | yes, `apps/web/src/conversation/sheets/MandateSheet.tsx:112` |
| POST /account-authorities/{id}/challenge, /account-authorities/verify | `apps/api/src/lonora_api/routes/account_authority.py:115`, `apps/api/src/lonora_api/routes/account_authority.py:126` | yes, `packages/core/src/account-authority.ts:147` |
| POST /account-authorities/{id}/revoke | `apps/api/src/lonora_api/routes/account_authority.py:143` | yes, mobile only: `apps/mobile/components/agent-permissions.tsx:1306` |
| GET, PUT /agents/{id}/permissions; PUT .../customization | `apps/api/src/lonora_api/routes/agent_permissions.py:13`, `apps/api/src/lonora_api/routes/agent_permissions.py:19`, `apps/api/src/lonora_api/routes/agent_permissions.py:30` | yes, `apps/web/src/conversation/PermissionMenu.tsx:216` |
| PATCH /agents/{id} (pause, market binding) | `apps/api/src/lonora_api/routes/agents.py:141` | yes, `apps/web/src/shell/agent/AgentPage.tsx:179` |
| GET, POST /owner-actions..., /challenge, /decision, /renew | `apps/api/src/lonora_api/routes/owner_actions.py:139`, `apps/api/src/lonora_api/routes/owner_actions.py:151`, `apps/api/src/lonora_api/routes/owner_actions.py:177`, `apps/api/src/lonora_api/routes/owner_actions.py:196` | yes, `apps/web/src/components/owner-actions/OwnerActionCard.tsx:153` |
| /watches list, create, read, update, delete | `apps/api/src/lonora_api/routes/watches.py:13` | list `apps/web/src/shell/domain/SchedulesPages.tsx:277`; create `apps/web/src/shell/domain/api.ts:75`; delete `apps/web/src/components/market/MarketWatch.tsx:328`; update: no caller found |
| POST /watches/{id}/control | `apps/api/src/lonora_api/routes/watches.py:28` | yes, `apps/web/src/conversation/sheets/WatchesSheet.tsx:25` |
| GET, POST /tasks; GET /tasks/{id} | `apps/api/src/lonora_api/routes/tasks.py:16`, `apps/api/src/lonora_api/routes/tasks.py:32`, `apps/api/src/lonora_api/routes/tasks.py:46` | yes, `apps/web/src/shell/domain/api.ts:48` |
| POST /tasks/control | `apps/api/src/lonora_api/routes/tasks.py:54` | yes, `apps/web/src/shell/domain/api.ts:56` |
| POST /tasks/{id}/complete | `apps/api/src/lonora_api/routes/tasks.py:62` | yes, `apps/web/src/shell/domain/api.ts:63` |
| DELETE /tickets/{id} | `apps/api/src/lonora_api/routes/tickets.py:11` | yes, `apps/web/src/shell/domain/TasksPages.tsx:175` |
| GET /routines; POST /routines/{agent_id}; PUT, DELETE /routines/{id} | `apps/api/src/lonora_api/routes/routines.py:19`, `apps/api/src/lonora_api/routes/routines.py:33`, `apps/api/src/lonora_api/routes/routines.py:43`, `apps/api/src/lonora_api/routes/routines.py:59` | yes, `apps/web/src/shell/domain/api.ts:66` |
| GET /routines/{id}/history | `apps/api/src/lonora_api/routes/routines.py:68` | yes, mobile only: `apps/mobile/lib/routine.ts:19` |
| /agent-goals list, create, update | `apps/api/src/lonora_api/routes/agent_goals.py:9` | yes, `apps/web/src/shell/domain/api.ts:78` |
| GET /trading/goals | `apps/api/src/lonora_api/routes/trading_goals.py:23` | yes, `apps/web/src/components/goals/TradingGoals.tsx:115` |
| POST /trading/goals; GET /trading/goals/{id}; PUT .../plan | `apps/api/src/lonora_api/routes/trading_goals.py:46`, `apps/api/src/lonora_api/routes/trading_goals.py:54`, `apps/api/src/lonora_api/routes/trading_goals.py:72` | no caller found |
| POST /trading/goals/{id}/control | `apps/api/src/lonora_api/routes/trading_goals.py:63` | yes, `apps/web/src/components/goals/TradingGoals.tsx:145` |
| POST /trading/goals/{id}/wake | `apps/api/src/lonora_api/routes/trading_goals.py:83` | yes, `apps/web/src/components/goals/TradingGoals.tsx:159` |
| GET /trading/goals/{id}/decisions | `apps/api/src/lonora_api/routes/trading_goals.py:90` | yes, `apps/web/src/components/goals/TradingGoals.tsx:31` |
| GET /trading/opportunities, /{id} | `apps/api/src/lonora_api/routes/opportunities.py:13`, `apps/api/src/lonora_api/routes/opportunities.py:32` | no caller found |
| GET /trading/decisions, /{id} | `apps/api/src/lonora_api/routes/trading_decisions.py:13`, `apps/api/src/lonora_api/routes/trading_decisions.py:36` | no caller found |
| GET /agents/{id}/performance | `apps/api/src/lonora_api/routes/performance.py:14` | no caller found |
| /charts list, create, update; GET /charts/{id}/scene; POST /charts/{id}/refresh | `apps/api/src/lonora_api/routes/charts.py:12`, `apps/api/src/lonora_api/routes/charts.py:15`, `apps/api/src/lonora_api/routes/charts.py:24` | yes, `apps/web/src/hooks/useCharts.ts:190`, `apps/web/src/lib/charts.ts:28`, `apps/web/src/lib/charts.ts:30` |
| GET /market/instruments, /symbols, /instrument, /quote, /candles, /calendar | `apps/api/src/lonora_api/routes/market.py:12`, `apps/api/src/lonora_api/routes/market.py:22`, `apps/api/src/lonora_api/routes/market.py:31`, `apps/api/src/lonora_api/routes/market.py:39`, `apps/api/src/lonora_api/routes/market.py:49`, `apps/api/src/lonora_api/routes/market.py:66` | yes, `apps/web/src/lib/market.ts:3`, `apps/web/src/components/market/EconomicCalendar.tsx:20` |
| GET /attention; POST /attention/seen, /seen-all; GET /attention/history; GET, PUT /attention/policy | `apps/api/src/lonora_api/routes/attention.py:39`, `apps/api/src/lonora_api/routes/attention.py:63`, `apps/api/src/lonora_api/routes/attention.py:71`, `apps/api/src/lonora_api/routes/attention.py:27`, `apps/api/src/lonora_api/routes/attention.py:78`, `apps/api/src/lonora_api/routes/attention.py:84` | yes, `apps/web/src/providers/AttentionProvider.tsx:47` |
| GET /attention/audit | `apps/api/src/lonora_api/routes/attention.py:15` | no caller found |
| GET, PUT /agents/{id}/notifications; GET /agents/notifications | `apps/api/src/lonora_api/routes/agent_delivery.py:22`, `apps/api/src/lonora_api/routes/agent_delivery.py:29`, `apps/api/src/lonora_api/routes/agent_delivery.py:14` | yes, `apps/web/src/shell/settings/NotifyPages.tsx:324` |
| GET, POST /supervision; POST /supervision/{id}/revoke | `apps/api/src/lonora_api/routes/supervision.py:27`, `apps/api/src/lonora_api/routes/supervision.py:35`, `apps/api/src/lonora_api/routes/supervision.py:49` | yes, `apps/web/src/components/ai/SupervisionSettings.tsx:105` |

Routes with "no caller found" are not owner actions and are left out of the action table. The agent does have tools on some of that data (`market_opportunity_*`, `market_decision_*`, `market_performance_read`, `goal_create`, `goal_plan`).

---

## 5. The parity table

Columns: owner action; one interface call site; agent tool or card; ownership scope; exposure for the personal assistant (N native, D discovery-only); result.

### 5.1 Broker accounts and connections

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A1 | List broker accounts | `apps/web/src/lib/trading.ts:11` | `list_accounts` (`packages/tools/src/lonora_tools/account.py:118`) | all the owner's accounts (`packages/tools/src/lonora_tools/account.py:49`) | N | covered |
| A2 | Read balance, equity, positions, orders | `apps/web/src/lib/trading.ts:14` | `account_read` (`packages/tools/src/lonora_tools/account.py:129`) | any owned account (`packages/tools/src/lonora_tools/account.py:71`) | N | covered |
| A3 | Connect a broker account | `apps/web/src/lib/trading.ts:13` | card `owner_action_propose` kind `connect_credential`, target `broker` (`packages/tools/src/lonora_tools/owner_actions.py:314`); the card posts to the owner route (`packages/core/src/owner-actions.ts:1289`) | owner | D | card |
| A4 | Test a connection before saving | `apps/web/src/shell/settings/ConnectionPages.tsx:173` | none | - | - | GAP NO-TOOL |
| A5 | Disconnect (delete) a broker account | `apps/web/src/shell/settings/ConnectionPages.tsx:287` | none | - | - | GAP NO-TOOL |
| A6 | Load a simulation snapshot into an account | `apps/web/src/components/trading/BrokerConnection.tsx:35` | none | - | - | GAP NO-TOOL |

### 5.2 Orders, positions, journal

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A7 | Place a market or pending order | `apps/web/src/components/trading/TradeActionCard.tsx:38` | `trade_execute` (`packages/tools/src/lonora_tools/trade.py:753`): under a signed grant, or it raises an approval card | any owned account for the personal agent (section 2.2, binding row); financial identity required (`packages/tools/src/lonora_tools/market_binding.py:112`) | N | covered |
| A8 | Close a position | `apps/web/src/components/trading/Positions.tsx:69` | `trade_execute` (close a position, `packages/tools/src/lonora_tools/trade.py:754`) or `trade_close_positions` (`packages/tools/src/lonora_tools/trade.py:771`) | as A7 | N / D | covered |
| A9 | Cancel a pending order | `apps/web/src/components/trading/Orders.tsx:38` | `trade_execute` (cancel an order, `packages/tools/src/lonora_tools/trade.py:754`) | as A7 | N | covered |
| A10 | Approve or reject a trade approval | `apps/web/src/components/trading/TradeApprovals.tsx:86` | none by design: "spoken or typed agreement is not approval" (`packages/tools/src/lonora_tools/trade.py:756`) | owner | - | CARD-ONLY |
| A11 | Ask again on an expired approval | `apps/web/src/conversation/Conversation.tsx:808` | the agent calls `trade_execute` again; the route itself only starts a run of the agent (`apps/api/src/lonora_api/routes/trading.py:251`) | as A7 | N | covered |
| A12 | Read the trade journal | `apps/web/src/shell/agent/TradesPage.tsx:111` | `trade_record_history`, `trade_record_read` (`packages/tools/src/lonora_tools/trade.py:738`, `packages/tools/src/lonora_tools/trade.py:745`) | all the owner's rows (`packages/tools/src/lonora_tools/trade.py:701`) | D | covered |
| A13 | Settle an uncertain operation | `apps/web/src/components/trading/TradingJournal.tsx:24` | card kind `resolve_operation` (`packages/tools/src/lonora_tools/owner_actions.py:296`) | owner | D | card |

UNSURE: whether the personal agent's grant lets it close a position that another agent opened. I did not trace the executor's per-ticket ownership checks. TRACE MUST CONFIRM: not needed for the conversation (one agent only).

### 5.3 Brakes, restrictions, limits

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A14 | Stop all new trades (global brake) | `apps/web/src/components/trading/TradingStatus.tsx:55`, `apps/web/src/lib/trading.ts:19` | none. Nearest: `trade_restriction_create` with `all_agents`, which needs `valid_until` within 31 days (`packages/tools/src/lonora_tools/restrictions.py:179`, `packages/tools/src/lonora_tools/restrictions.py:181`) | - | - | GAP NO-TOOL |
| A15 | Resume trading | `apps/web/src/lib/trading.ts:21` | card kind `resume_trading` (`packages/tools/src/lonora_tools/owner_actions.py:293`) | owner | D | card |
| A16 | See whether trading is stopped | `apps/web/src/lib/trading.ts:15` | `runtime_status` (`packages/tools/src/lonora_tools/runtime_control.py:192`, reads the controls at `packages/tools/src/lonora_tools/runtime_control.py:57`) | global | D | covered |
| A17 | Suspend new trades for one agent | `apps/web/src/conversation/sheets/AgentSheet.tsx:515` | `trade_restriction_create` (`packages/tools/src/lonora_tools/restrictions.py:286`). For another agent: a supervision grant or the owner's message, and `valid_until` is required (`packages/tools/src/lonora_tools/restrictions.py:165`, `packages/tools/src/lonora_tools/restrictions.py:179`) | any agent, with those conditions | D | covered |
| A18 | Lift a restriction | `apps/web/src/lib/trading.ts:24` | card kind `lift_restriction` (`packages/tools/src/lonora_tools/owner_actions.py:295`). Tool text: "Only the owner can lift a restriction." (`packages/tools/src/lonora_tools/restrictions.py:304`) | owner | D | card |
| A19 | Read the account's money limits | `apps/web/src/conversation/sheets/MandateSheet.tsx:64` | `trade_restriction_list`, field `monetary_risk_limits` (`packages/tools/src/lonora_tools/restrictions.py:310`, `packages/tools/src/lonora_tools/restrictions.py:277`) | accounts named or in scope | D | covered |
| A20 | Set, lower or raise money limits | `apps/web/src/conversation/sheets/LimitsSheet.tsx:145` | card kind `set_account_limits` (`packages/tools/src/lonora_tools/owner_actions.py:298`) | owner | D | card |

### 5.4 Account authority and bindings

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A21 | See an agent's trading level and grants | `apps/web/src/conversation/PermissionMenu.tsx:215` | `agent_inspect` section `overview`, field `trading_readiness` (`packages/tools/src/lonora_tools/supervision.py:159`; grants built at `packages/db/src/lonora_db/trading_readiness.py:116`) | itself and supervised agents (`packages/tools/src/lonora_tools/supervision.py:415`) | N | covered |
| A22 | Prepare a grant (mandate sheet) | `apps/web/src/conversation/sheets/MandateSheet.tsx:112` | card kind `grant_authority` (`packages/tools/src/lonora_tools/owner_actions.py:300`); the personal agent may propose for any agent (`packages/tools/src/lonora_tools/owner_actions.py:50`) | any agent (personal) | D | card |
| A23 | Sign a grant with the passkey | `packages/core/src/account-authority.ts:147` | none by design | owner | - | CARD-ONLY |
| A24 | Revoke a grant | `apps/mobile/components/agent-permissions.tsx:1306`; on the web by lowering the level, which revokes it (`packages/db/src/lonora_db/agent_permissions.py:228`) | none; no card kind (`packages/contracts/src/lonora_contracts/owner_actions.py:20`) | - | - | GAP NO-TOOL |
| A25 | Change the trading level (analysis, ask me, on its own) | `apps/web/src/conversation/PermissionMenu.tsx:216` | none for the level itself; only the grant card of A22 | - | - | GAP NO-TOOL |
| A26 | Change an agent's market (account and symbol) | `apps/web/src/shell/agent/IdentityPage.tsx:112` | none (`agent_create` sets a market only at creation) | - | - | GAP NO-TOOL |

### 5.5 Watches

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A27 | List watches | `apps/web/src/shell/domain/SchedulesPages.tsx:277` | `watch_list` (own; `packages/tools/src/lonora_tools/market_watch.py:246`); other agents one at a time with `agent_inspect` section `work` (`packages/tools/src/lonora_tools/supervision.py:169`), 10 per page (`packages/tools/src/lonora_tools/supervision.py:77`) | own, plus supervised through `agent_inspect` | D / N | covered |
| A28 | Create a watch for a chosen agent | `apps/web/src/shell/domain/SchedulesPages.tsx:433` | `watch_create` (`packages/tools/src/lonora_tools/market_watch.py:238`) | own agent only (`packages/tools/src/lonora_tools/market_watch.py:133`) | N | GAP TOOL-BUT-OWN-AGENT-ONLY |
| A29 | Pause or resume a watch | `apps/web/src/shell/domain/SchedulesPages.tsx:294` | own: `watch_pause`, `watch_resume` (`packages/tools/src/lonora_tools/market_watch.py:261`, `packages/tools/src/lonora_tools/market_watch.py:268`); another agent's: `agent_control` (`packages/tools/src/lonora_tools/supervision.py:610`) | own, plus supervised | D | covered |
| A30 | Cancel a watch | `apps/web/src/shell/domain/SchedulesPages.tsx:258` | `watch_cancel` (`packages/tools/src/lonora_tools/market_watch.py:254`), description "Stop one of your own watches; its record stays, and watch_resume undoes it." | own agent only (`packages/db/src/lonora_db/market_watches.py:123`); `agent_control` has no cancel | D | GAP TOOL-BUT-OWN-AGENT-ONLY |
| A31 | Extend a watch («تمديد ساعتين») | `apps/web/src/conversation/sheets/WatchesSheet.tsx:78` | `watch_update` (`packages/tools/src/lonora_tools/market_watch.py:276`) | own agent only (`packages/tools/src/lonora_tools/market_watch.py:209`) | D | GAP TOOL-BUT-OWN-AGENT-ONLY |
| A32 | Delete a watch (remove the record) | `apps/web/src/components/market/MarketWatch.tsx:328` | none; `watch_cancel` keeps the record | - | - | GAP NO-TOOL |

### 5.6 Tasks

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A33 | List tasks | `apps/web/src/shell/domain/api.ts:48` | `task_inspect` (own; `packages/tools/src/lonora_tools/tasks.py:113`); other agents with `agent_inspect` section `work` (`packages/tools/src/lonora_tools/supervision.py:187`) | own, plus supervised through `agent_inspect` | D / N | covered |
| A34 | Open one task (steps, state) | `apps/web/src/shell/domain/api.ts:49` | `task_inspect` with `task_id` | own agent only (`packages/tools/src/lonora_tools/tasks.py:57`); `agent_inspect` gives only id, title, status, phase, waiting reason, version (`packages/tools/src/lonora_tools/supervision.py:225`) | D | GAP READ-ONLY-GAP |
| A35 | Create a task for a chosen agent | `apps/web/src/shell/domain/TasksPages.tsx:283` | `task_start` (`packages/tools/src/lonora_tools/tasks.py:106`) | own agent only (`packages/tools/src/lonora_tools/tasks.py:32`) | D | GAP TOOL-BUT-OWN-AGENT-ONLY |
| A36 | Pause or resume a task | `apps/web/src/shell/domain/TasksPages.tsx:218` | own: `task_control` (`packages/tools/src/lonora_tools/tasks.py:121`); another agent's: `agent_control` | own, plus supervised | D | covered |
| A37 | Cancel a task | `apps/web/src/shell/domain/api.ts:55`, `apps/web/src/conversation/sheets/AgentSheet.tsx:420` | `task_control` action `cancel` (`packages/contracts/src/lonora_contracts/tasks.py:90`) | own agent only (`packages/db/src/lonora_db/tasks.py:411`) | D | GAP TOOL-BUT-OWN-AGENT-ONLY |
| A38 | Mark a task completed («تحديد كمكتملة») | `apps/web/src/shell/domain/TasksPages.tsx:240` | none. The code says: "Agents have no route here." (`packages/db/src/lonora_db/tasks.py:571`) | - | - | GAP NO-TOOL |
| A39 | Delete a task | `apps/web/src/shell/domain/TasksPages.tsx:175` | none | - | - | GAP NO-TOOL |

### 5.7 Routines

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A40 | List routines | `apps/web/src/shell/domain/api.ts:66` | `routine_list` (own; `packages/tools/src/lonora_tools/routine.py:113`); other agents with `agent_inspect` section `work` (`packages/tools/src/lonora_tools/supervision.py:178`) | own, plus supervised through `agent_inspect` | D / N | covered |
| A41 | Create a routine for a chosen agent | `apps/web/src/shell/domain/SchedulesPages.tsx:452` | `routine_create`, description "Schedule this same agent ..." (`packages/tools/src/lonora_tools/routine.py:108`) | own agent only (`packages/tools/src/lonora_tools/routine.py:32`) | D | GAP TOOL-BUT-OWN-AGENT-ONLY |
| A42 | Switch a routine on or off | `apps/web/src/shell/domain/SchedulesPages.tsx:305` | `routine_toggle` (`packages/tools/src/lonora_tools/routine.py:115`) | own, plus supervised (`packages/tools/src/lonora_tools/routine.py:86`) | D | covered |
| A43 | Edit a routine (schedule, prompt, title, re-arm a one-shot) | `apps/web/src/shell/domain/SchedulesPages.tsx:168` | none | - | - | GAP NO-TOOL |
| A44 | Delete a routine | `apps/web/src/shell/domain/SchedulesPages.tsx:217` | none | - | - | GAP NO-TOOL |
| A45 | See a routine's run history | `apps/mobile/lib/routine.ts:19` | none specific. UNSURE whether `agent_inspect` section `runs` shows the same rows; I did not compare | - | - | GAP READ-ONLY-GAP |

### 5.8 Goals

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A46 | List, add, edit an agent's goals (the goals page) | `apps/web/src/shell/domain/api.ts:78`, `apps/web/src/shell/domain/api.ts:80`, `apps/web/src/shell/domain/api.ts:82` | none. The rows are only read into the agent's own context (`packages/agent-runtime/src/lonora_agent/context/memory.py:62`) | - | - | GAP NO-TOOL |
| A47 | List an agent's trading goals | `apps/web/src/components/goals/TradingGoals.tsx:115` | `goal_list` (own agent and its conversations; `packages/tools/src/lonora_tools/trading_goal.py:491`, `packages/tools/src/lonora_tools/trading_goal.py:93`); other agents with `agent_inspect` section `work` (`packages/tools/src/lonora_tools/supervision.py:198`) | own, plus supervised through `agent_inspect` | D / N | covered |
| A48 | Pause, resume or cancel a trading goal | `apps/web/src/components/goals/TradingGoals.tsx:145` | `goal_control` (`packages/tools/src/lonora_tools/trading_goal.py:541`) | own agent and the same conversation only (`packages/tools/src/lonora_tools/trading_goal.py:467`); `agent_control` has no goal target (`packages/contracts/src/lonora_contracts/supervision.py:17`) | D | GAP TOOL-BUT-OWN-AGENT-ONLY |
| A49 | Wake a goal step now | `apps/web/src/components/goals/TradingGoals.tsx:159` | none | - | - | GAP NO-TOOL |
| A50 | Read a goal's decisions | `apps/web/src/components/goals/TradingGoals.tsx:31` | `goal_decisions` (`packages/tools/src/lonora_tools/trading_goal.py:506`) | own agent and its conversations only (`packages/tools/src/lonora_tools/trading_goal.py:158`) | D | GAP READ-ONLY-GAP |

### 5.9 Charts and market data

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A51 | Create a chart | `apps/web/src/hooks/useCharts.ts:190` | `chart_open` (`packages/tools/src/lonora_tools/chart.py:44`) | owner-wide | D | covered |
| A52 | Edit a chart (symbol, timeframe, indicators, drawings) | `apps/web/src/hooks/useCharts.ts:205` | `chart_set_symbol`, `chart_set_timeframe`, `chart_add_indicator`, `chart_remove_indicator`, `chart_annotate` (`packages/tools/src/lonora_tools/chart_state.py:400`, `packages/tools/src/lonora_tools/chart_state.py:407`, `packages/tools/src/lonora_tools/chart_state.py:414`, `packages/tools/src/lonora_tools/chart_state.py:421`, `packages/tools/src/lonora_tools/chart_state.py:435`) | any owned chart (`packages/tools/src/lonora_tools/chart_state.py:181`) | D | covered |
| A53 | List charts, read and refresh a chart's scene | `apps/web/src/lib/charts.ts:28`, `apps/web/src/lib/charts.ts:30` | `chart_list`, `chart_inspect` (`packages/tools/src/lonora_tools/chart_state.py:386`, `packages/tools/src/lonora_tools/chart_state.py:393`); inspect prepares a scene that is still initializing (`packages/tools/src/lonora_tools/chart_state.py:149`) | any owned chart (`packages/tools/src/lonora_tools/chart_state.py:160`) | D | covered |
| A54 | Read symbols, instrument, quote, candles | `apps/web/src/lib/market.ts:3` | `market_quote`, `market_candles`, `market_instrument` native; `market_symbols`, `market_instruments` discovery-only (`packages/tools/src/lonora_tools/market.py:122`, `packages/tools/src/lonora_tools/market.py:131`, `packages/tools/src/lonora_tools/market.py:107`, `packages/tools/src/lonora_tools/market.py:98`, `packages/tools/src/lonora_tools/market.py:115`) | any owned account | N / D | covered |
| A55 | Read the economic calendar | `apps/web/src/components/market/EconomicCalendar.tsx:20` | `economic_calendar_read` (`packages/tools/src/lonora_tools/market_analysis.py:386`) | owner sources | D | covered |

### 5.10 Attention and notifications

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A56 | Read open notifications (all agents) | `apps/web/src/providers/AttentionProvider.tsx:47` | `owner_attention_list` (`packages/tools/src/lonora_tools/incoming_call.py:121`) | only this agent and this conversation, status `ready` (`packages/tools/src/lonora_tools/incoming_call.py:108`, `packages/tools/src/lonora_tools/incoming_call.py:110`) | D | GAP READ-ONLY-GAP |
| A57 | Read the notification history | `apps/web/src/shell/domain/UpdatesPages.tsx:148` | none | - | - | GAP READ-ONLY-GAP |
| A58 | Mark one or all notifications as seen | `apps/web/src/providers/AttentionProvider.tsx:67`, `apps/web/src/shell/domain/api.ts:139` | none | - | - | GAP NO-TOOL |
| A59 | Notification policy (opportunities, informational) | `apps/web/src/shell/settings/NotifyPages.tsx:154` | none. `owner_preferences_update` (`packages/tools/src/lonora_tools/memory.py:290`) sets the reach-me channel, reply language, quiet hours and timezone, a different record | - | - | GAP NO-TOOL |
| A60 | Per-agent notification rules (in-app, calls, daily limit) | `apps/web/src/shell/settings/NotifyPages.tsx:324` | none | - | - | GAP NO-TOOL |

### 5.11 Supervision

| # | Owner action | Call site | Agent tool or card | Scope | Exp. | Result |
|---|---|---|---|---|---|---|
| A61 | See who supervises an agent | `apps/web/src/components/ai/SupervisionSettings.tsx:23` | `agent_inspect` overview, field `supervised_by` (`packages/tools/src/lonora_tools/supervision.py:160`); `list_agents` (`packages/tools/src/lonora_tools/agents.py:362`) | itself and supervised agents | N / D | covered |
| A62 | Let one agent supervise another | `apps/web/src/components/ai/SupervisionSettings.tsx:105` | `supervision_change` action `grant` (`packages/tools/src/lonora_tools/supervision.py:625`): direct from the owner's message, otherwise a card (`packages/tools/src/lonora_tools/supervision.py:546`) | any owned agents | D | covered |
| A63 | End a supervision | `apps/web/src/components/ai/SupervisionSettings.tsx:67` | `supervision_change` action `revoke`: needs the owner's message, never the caller's own oversight (`packages/tools/src/lonora_tools/supervision.py:501`, `packages/tools/src/lonora_tools/supervision.py:497`) | any owned agents | D | covered |
| A64 | Pause or resume a whole agent | `apps/web/src/shell/agent/AgentPage.tsx:179` | `agent_control` target `agent`. Limits: never the personal agent itself (`packages/db/src/lonora_db/supervision.py:686`); a trading agent with money standing only on the owner's message (`packages/db/src/lonora_db/supervision.py:689`) | supervised agents | D | covered |

---

## 6. Numbered list of gaps

### NO-TOOL (17)

1. A4 Test a broker connection before saving. No tool and no card.
2. A5 Disconnect a broker account. Owner route only (`apps/api/src/lonora_api/routes/trading.py:80`). The route also revokes the account's grants first (`apps/api/src/lonora_api/routes/trading.py:86`).
3. A6 Load a simulation snapshot. Owner route only (`apps/api/src/lonora_api/routes/trading.py:106`).
4. A14 Stop all new trades. Owner route only (`apps/api/src/lonora_api/routes/trading.py:48`). There is a card to resume and none to stop. The tool text says "Stop is the owner's brake" (`packages/tools/src/lonora_tools/owner_actions.py:294`). Stopping only narrows; no money rule requires the owner's tap for it.
5. A24 Revoke a grant. Owner route only (`apps/api/src/lonora_api/routes/account_authority.py:143`). Revoking narrows.
6. A25 Change the trading level. Owner route only (`apps/api/src/lonora_api/routes/agent_permissions.py:19`). Raising widens, so by the money rules it must stay the owner's act; lowering narrows and has no agent path either.
7. A26 Change an agent's market binding. Owner route only (`apps/api/src/lonora_api/routes/agents.py:141`).
8. A32 Delete a watch record. Owner route only (`apps/api/src/lonora_api/routes/__init__.py:69` through `apps/api/src/lonora_api/routes/watches.py:13`).
9. A38 Mark a task completed (`apps/api/src/lonora_api/routes/tasks.py:62`).
10. A39 Delete a task (`apps/api/src/lonora_api/routes/tickets.py:11`).
11. A43 Edit a routine (`apps/api/src/lonora_api/routes/routines.py:43`). The agent can only switch it on or off.
12. A44 Delete a routine (`apps/api/src/lonora_api/routes/routines.py:59`).
13. A46 The agent goals list (`apps/api/src/lonora_api/routes/agent_goals.py:9`). No agent tool reads or writes it.
14. A49 Wake a goal step now (`apps/api/src/lonora_api/routes/trading_goals.py:83`).
15. A58 Mark notifications as seen (`apps/api/src/lonora_api/routes/attention.py:63`, `apps/api/src/lonora_api/routes/attention.py:71`).
16. A59 Notification policy (`apps/api/src/lonora_api/routes/attention.py:84`).
17. A60 Per-agent notification rules (`apps/api/src/lonora_api/routes/agent_delivery.py:29`).

### TOOL-BUT-OWN-AGENT-ONLY (7)

18. A28 Create a watch for another agent (`packages/tools/src/lonora_tools/market_watch.py:133`).
19. A30 Cancel another agent's watch (`packages/db/src/lonora_db/market_watches.py:123`). Scripted result: `market_watches_not_found`.
20. A31 Extend or move another agent's watch (`packages/tools/src/lonora_tools/market_watch.py:209`). Scripted result: `market_watches_not_found`.
21. A35 Create a task for another agent (`packages/tools/src/lonora_tools/tasks.py:32`).
22. A37 Cancel another agent's task (`packages/db/src/lonora_db/tasks.py:411`). Scripted result: `task_agent_mismatch`.
23. A41 Create a routine for another agent (`packages/tools/src/lonora_tools/routine.py:32`).
24. A48 Pause, resume or cancel another agent's trading goal, or the caller's own goal from another conversation (`packages/tools/src/lonora_tools/trading_goal.py:467`).

For 18, 21 and 23 the personal agent's only route today is to ask the other agent (`peer_send`, or `agent_control` with `action="message"`, `packages/tools/src/lonora_tools/supervision.py:431`). That starts a run of the other agent; the result then depends on that agent's model.

### READ-ONLY-GAP (5)

25. A34 Detail of another agent's task (`packages/tools/src/lonora_tools/tasks.py:57`). Scripted result: `task_agent_mismatch`.
26. A45 Routine run history (`apps/api/src/lonora_api/routes/routines.py:68`).
27. A50 Decisions of another agent's goal (`packages/tools/src/lonora_tools/trading_goal.py:158`).
28. A56 Open notifications of other agents and other conversations (`packages/tools/src/lonora_tools/incoming_call.py:108`).
29. A57 Notification history (`apps/api/src/lonora_api/routes/attention.py:27`).

### TOOL-BUT-NOT-EXPOSED-TO-PERSONAL-ASSISTANT (0)

None. See section 2.3. Covered actions that depend only on a discovery-only tool for the personal assistant: A12, A16, A17, A19, A29, A36, A42, A51, A52, A53, A55, A62, A63, A64, and every card of A3, A13, A15, A18, A20, A22 (`owner_action_propose` is discovery-only). Own-resource cancel and control tools are discovery-only too: `watch_cancel`, `watch_pause`, `watch_resume`, `watch_update`, `watch_list`, `task_control`, `task_inspect`, `routine_toggle`, `goal_control`, `trade_close_positions` (`runs/parity_trading_registry.txt`).

### CARD-ONLY (8, not counted as open gaps)

30. A3 Connect a broker account. Rule: never print or handle secrets; the tool text says the form's "value goes straight to the server, never to you" (`packages/tools/src/lonora_tools/owner_actions.py:316`).
31. A10 Approve or reject a trade. Rule: money moves only through a signed grant or an approval card at the single executor.
32. A13 Settle an uncertain operation. Rule: journal records are append-only and the owner attests; "it clears the block, never resends" (`apps/api/src/lonora_api/routes/trading.py:144`).
33. A15 Resume trading. Rule: lifting a brake widens what may trade; "Stop is the owner's brake" (`packages/tools/src/lonora_tools/owner_actions.py:294`).
34. A18 Lift a restriction. Rule: "Only the owner can lift a restriction." (`packages/tools/src/lonora_tools/restrictions.py:304`).
35. A20 Set account money limits. Rule: "Lowering or adding a limit is one tap; a grant, raising or removing a limit ... needs the owner's passkey." (`packages/tools/src/lonora_tools/owner_actions.py:317` to `packages/tools/src/lonora_tools/owner_actions.py:318`).
36. A22 Prepare a grant. Rule: a grant is signed by the owner; the card grants nothing until then.
37. A23 Sign a grant. Rule: money authority exists only through the owner's signed grant (passkey ceremony, `apps/api/src/lonora_api/routes/account_authority.py:115`, `apps/api/src/lonora_api/routes/account_authority.py:126`).

---

## 7. Totals

| | Count |
|---|---|
| Owner actions in scope | 64 |
| Covered by a tool on any of the owner's resources | 27 (A1, A2, A7, A8, A9, A11, A12, A16, A17, A19, A21, A27, A29, A33, A36, A40, A42, A47, A51, A52, A53, A54, A55, A61, A62, A63, A64) |
| Handled by a card (CARD-ONLY) | 8 (A3, A10, A13, A15, A18, A20, A22, A23) |
| Gap NO-TOOL | 17 |
| Gap TOOL-BUT-OWN-AGENT-ONLY | 7 |
| Gap READ-ONLY-GAP | 5 |
| Gap TOOL-BUT-NOT-EXPOSED-TO-PERSONAL-ASSISTANT | 0 |
| Open gaps in total | 29 |

Of the 27 covered actions, 6 are covered for other agents only through `agent_inspect` (A27, A33, A40, A47: lists, one agent and 10 rows per call) or only as pause and resume through `agent_control` (A29, A36).

---

## 8. What this means for the problem messages

Only the parity side of each message is judged here. Other files cover the guards, the offers and the symbol errors.

| Message | Parity finding on main | Class |
|---|---|---|
| [62]→[63] «ألغِ المهمة بالكامل» | Tools exist for the agent's own resources: `watch_cancel` and `task_control` cancel. Both are discovery-only. Nothing on main makes the run call them. | FAILS (behaviour); the tool is not missing |
| [65] list shows three EURUSDm watches | `watch_list` reads the agent's own watches (`packages/tools/src/lonora_tools/market_watch.py:154`); `agent_inspect` section `work` on itself also lists them (`packages/tools/src/lonora_tools/supervision.py:411`). A read path exists. | not a parity gap: a read path exists and existed during the conversation |
| [68]→[77] delete the watches | "Delete" has two meanings in the product. Stop the watch: `watch_cancel`, own agent only. Remove the record: owner route only (gap 8). The reply «ما عندي أداة حذف» is true only for the second meaning and false for the first. For another agent's watch the personal assistant cannot cancel at all (gap 19). | FAILS |
| [75] «ما في أداة حذف ظاهرة تحت هذا الاستعلام» | The discovery search gave an empty list in production. On main my queries for other missing or renamed actions also return empty or unrelated tools (section 2.3). | FAILS until the discovery fix lands |
| [40] «بس صار ربح 100 دولار سكره» | `watch_create` is native and accepts a position watch; `trade_execute` is native. No parity gap. | not a parity problem |
| [34] target and stop | `trade_execute` is native and covers modifying a position (`packages/tools/src/lonora_tools/trade.py:754`). No parity gap. | not a parity problem |

TRACE MUST CONFIRM:

- That all four watches and the task «إدارة حساب التداول» belong to the personal agent. The lead's note says there is one agent only (`TIMELINE_CORRECTION.md`, point 1); if so, gaps 18 to 24 did not block anything in this conversation and matter for principle 10 only.
- That no `watch_cancel`, `watch_list`, `task_control` or `agent_control` call was made in runs ddae66ad, e343c96a, e79b4bf2 (the lead's note, points 4 to 6).
- The exact `tool_environment` query and result at 10:53:57 UTC, to confirm the empty list came from the search gate and not from another cause.
- Whether the owner cancelled the task from the interface at 10:51:04 (the lead's note, point 10); that is action A37 done by the owner because the agent had not done it.

---

## 9. What I skipped

- Part 2 scope: agent creation, deletion, identity, model, skills, memory, knowledge, files, integrations, MCP, providers, voice and incoming calls, threads, messages, groups, device enrolment, runs (cancel, steer, retry, resume), the activity feed.
- Boards and tickets other than deleting a task: `apps/web/src/pages/Board.tsx` calls them, but I found no import of that page in `apps/web/src/shell/pages.tsx`. UNSURE whether the page is reachable; not counted.
- Routes with no client caller (section 4): risk status, exposure, opportunities, decisions, performance, creating a trading goal, editing a goal plan, the attention audit, listing restrictions.
- The owner's side of the cards (`/owner-actions/{id}/challenge`, `/decision`, `/renew`) is the card mechanism itself and is not listed as separate actions.
- Whether `apps/web/src/pages/Trading.tsx` (manual order, close, cancel, journal) is linked from the navigation. It is routed at `/app/trading` (`apps/web/src/shell/pages.tsx:271`); I did not check the menus.
- The executor's per-position ownership rules (the UNSURE under section 5.2).
- Mobile was searched for call sites but its screens were not walked; two actions have a mobile-only call site (A24 revoke, A45 history).
- The scripted run did not change the global trading controls, because the database is shared; the brake findings (A14 to A16) rest on code reading only.
