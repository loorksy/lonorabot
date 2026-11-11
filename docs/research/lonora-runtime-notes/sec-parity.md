## Parity inventory: what the owner can do from the interface versus what the agent can do

Main `9f5b1da`. Part A: trading, accounts, authority, watches, tasks, routines, goals, charts, attention, supervision (A1 to A64). Part B: everything else (R1 to R66). Overlaps counted once per part: A25/R5, A26/R3, A46/R12, A56/R63, A59/R64, A60/R8, A61/R9, A62/R10, A63/R11, A64/R4.

### Method

- Routes: Part A walked the trading, market, watch, task, routine, goal, chart, attention and supervision routers (`apps/api/src/lonora_api/app.py:126`); Part B every other mounted router: 276 routes (273 HTTP + 3 websocket). SCRIPTED: `scripts/parity_routes.py`.
- Client call sites: grep of `apps/web/src`, `apps/mobile/app`, `apps/mobile/lib`, `apps/mobile/components`, `packages/ui-web`, `packages/chat-ui` (Part A also `packages/core`) for path fragments; 375 hits for Part B. A route with no caller is not an owner action.
- Registry: 126 tools (`packages/tools/src/lonora_tools/loader.py:53`; SCRIPTED `scripts/parity_tools.py`). Native for the personal assistant: 23, the list every production run was offered (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:46`); `trade_execute` is withheld at level analysis (`packages/tools/src/lonora_tools/trade.py:768`), so a fresh analysis-level run was offered 22. Every other tool stays callable through `tool_call` (`packages/tools/src/lonora_tools/base.py:24`); a tool called once that way is promoted to native later, up to six (`packages/tools/src/lonora_tools/registry.py:292`); production made no `tool_call` call, so none was promoted.
- SCRIPTED runs: `scripts/parity_trading_probe.py` (real runtime; another agent T of the same owner holds a watch, routine, task) and `scripts/parity_discovery.py` (51 phrasings).
- Cards: "No tool can confirm a card" (`packages/tools/src/lonora_tools/owner_actions.py:5`). Card kinds an agent raises: `resume_trading`, `lift_restriction`, `resolve_operation`, `set_account_limits`, `grant_authority`, `trust_source`, `connect_credential` (`packages/contracts/src/lonora_contracts/owner_actions.py:20`), `create_agent`, `supervise`, `agent_model`. None exists for agent edit or delete, notification rules, groups, chats, provider key, default routing, Telegram, removing a feed, MCP server or trusted source, files (`packages/db/src/lonora_db/capability_cards.py:38`). Many tools act directly only on the owner's typed message, else card or refusal (`packages/tools/src/lonora_tools/restrictions.py:103`): a safety rule.

### Totals

CARD: the agent can raise a card, or the action is the owner's own tap. OWN = TOOL-BUT-OWN-AGENT-ONLY. TOOL-BUT-NOT-EXPOSED is 0: every tool is callable through `tool_call`; the cost is discovery.

| | Part A | Part B | Both |
|---|---|---|---|
| Owner actions | 64 | 66 | 130 |
| Covered by a tool (B includes 4 COVERED+CARD) | 27 | 23 | 50 |
| Covered by a card | 8 (A10, A23: owner tap or passkey only) | 4 | 12 |
| NO-TOOL | 17 | 28 | 45 |
| TOOL-BUT-OWN-AGENT-ONLY | 7 | 6 | 13 |
| READ-ONLY-GAP | 5 | 5 | 10 |
| TOOL-BUT-NOT-EXPOSED | 0 | 0 | 0 |
| Gaps | 29 | 39 | 68 |

27+8+29 = 64; 23+4+39 = 66; 50+12+68 = 130. Part B leaves out 8 owner-only-by-nature actions (login, passkey enrolment, deciding a card, calls, marking read, first-time setup, opening a chat) and `POST /api/threads` (no tool; 67 with it). Of Part B's 27 covered, 19 depend on a tool_call-only tool. Production had one agent (production trace Part 1 Q6): other-agent gaps are latent.

### Table of all owner actions

Part B paths are under `/api`. Exp: N native, N* native but withheld at analysis level, T through `tool_call` only. Status: C covered, CARD, NT NO-TOOL, OWN, RO READ-ONLY-GAP, C+CARD (acts on the owner's message, else raises a card). Handlers are under `apps/api/src/lonora_api/routes/` (cited for Part A gap rows only), tools under `packages/tools/src/lonora_tools/` (plain COVERED rows name the tool without a line).

| id | owner action | route | agent tool or card | scope | exp | status |
|---|---|---|---|---|---|---|
| A1 | List broker accounts | GET /trading/connections | list_accounts | all | N | C |
| A2 | Read balance, positions, orders | GET /trading/accounts/{id} | account_read | all | N | C |
| A3 | Connect a broker account | POST /trading/connections | card connect_credential | owner | T | CARD |
| A4 | Test a connection | POST /trading/connections/test `apps/api/src/lonora_api/routes/connection_tests.py:86` | none | - | - | NT |
| A5 | Disconnect a broker account | DELETE /trading/connections/{id} `apps/api/src/lonora_api/routes/trading.py:80` | none | - | - | NT |
| A6 | Load a simulation snapshot | POST /trading/connections/{id}/simulation `apps/api/src/lonora_api/routes/trading.py:106` | none | - | - | NT |
| A7 | Place an order | POST /trading/execute | trade_execute | all owned | N* | C |
| A8 | Close a position | as A7 | trade_execute; trade_close_positions | all owned | N / T | C |
| A9 | Cancel a pending order | as A7 | trade_execute | all owned | N* | C |
| A10 | Approve or reject a trade approval | POST /trading/approvals/{id}/decision | none by design: "spoken or typed agreement is not approval" | owner | - | CARD (owner tap) |
| A11 | Ask again on an expired approval | POST /trading/approvals/{id}/renew | trade_execute again | all owned | N* | C |
| A12 | Read the trade journal | GET /trading/journal | trade_record_history | all | T | C |
| A13 | Settle an uncertain operation | POST /trading/journal/{id}/resolve | card resolve_operation | owner | T | CARD |
| A14 | Stop all new trades (global brake) | PUT /trading/controls `apps/api/src/lonora_api/routes/trading.py:48` | none. Nearest trade_restriction_create all_agents, valid_until within 31 days `packages/tools/src/lonora_tools/restrictions.py:179`; on itself no valid_until `packages/tools/src/lonora_tools/restrictions.py:161` | - | - | NT |
| A15 | Resume trading | as A14 | as A14 | owner | T | CARD |
| A16 | See whether trading is stopped | GET /trading/controls | runtime_status | global | T | C |
| A17 | Suspend new trades for one agent | POST /trading/restrictions | trade_restriction_create | any agent (another agent: grant or owner message, valid_until) | T | C |
| A18 | Lift a restriction | POST /trading/restrictions/{id}/revoke | card lift_restriction | owner | T | CARD |
| A19 | Read the money limits | GET /trading/accounts/{id}/execution-policy | trade_restriction_list | named accounts | T | C |
| A20 | Set, lower or raise money limits | PUT .../execution-policy | card set_account_limits | owner | T | CARD |
| A21 | See an agent's level and grants | GET /agents/{id}/permissions | agent_inspect overview | self + supervised | N | C |
| A22 | Prepare a grant | POST /agents/{id}/account-authorities/draft | card grant_authority | any agent | T | CARD |
| A23 | Sign a grant (passkey) | POST /account-authorities/{id}/challenge | none by design | owner | - | CARD (owner passkey) |
| A24 | Revoke a grant | POST /account-authorities/{id}/revoke `apps/api/src/lonora_api/routes/account_authority.py:143` | none; no card kind | - | - | NT |
| A25 | Change the trading level | PUT /agents/{id}/permissions `apps/api/src/lonora_api/routes/agent_permissions.py:19` | none | - | - | NT |
| A26 | Change an agent's market | PATCH /agents/{id} `apps/api/src/lonora_api/routes/agents.py:141` | none | - | - | NT |
| A27 | List watches | GET /watches | watch_list; agent_inspect work | own + supervised | T / N | C |
| A28 | Create a watch for a chosen agent | POST /watches | watch_create `packages/tools/src/lonora_tools/market_watch.py:238` | own only | N | OWN |
| A29 | Pause or resume a watch | POST /watches/{id}/control | watch_pause; others: agent_control | own + supervised | T | C |
| A30 | Cancel a watch | POST /watches/{id}/control (as A29) | watch_cancel `packages/tools/src/lonora_tools/market_watch.py:254` | own only | T | OWN |
| A31 | Extend a watch | POST /watches/{id}/control (as A29) | watch_update `packages/tools/src/lonora_tools/market_watch.py:276` | own only | T | OWN |
| A32 | Delete a watch record | DELETE /watches/{id} `apps/api/src/lonora_api/routes/watches.py:13` | none | - | - | NT |
| A33 | List tasks | GET /tasks | task_inspect; agent_inspect work | own + supervised | T / N | C |
| A34 | Open one task | GET /tasks/{id} | task_inspect with task_id | own only | T | RO |
| A35 | Create a task for a chosen agent | POST /tasks | task_start `packages/tools/src/lonora_tools/tasks.py:106` | own only | T | OWN |
| A36 | Pause or resume a task | POST /tasks/control | task_control; others: agent_control | own + supervised | T | C |
| A37 | Cancel a task | POST /tasks/control (as A36) | task_control cancel `packages/contracts/src/lonora_contracts/tasks.py:90` | own only | T | OWN |
| A38 | Mark a task completed | POST /tasks/{id}/complete `apps/api/src/lonora_api/routes/tasks.py:62` | none: "Agents have no route here." `packages/db/src/lonora_db/tasks.py:571` | - | - | NT |
| A39 | Delete a task | DELETE /tickets/{id} `apps/api/src/lonora_api/routes/tickets.py:11` | none | - | - | NT |
| A40 | List routines | GET /routines | routine_list; agent_inspect work | own + supervised | T / N | C |
| A41 | Create a routine for a chosen agent | POST /routines/{agent_id} | routine_create `packages/tools/src/lonora_tools/routine.py:108` | own only | T | OWN |
| A42 | Switch a routine on or off | PUT /routines/{id} | routine_toggle | own + supervised | T | C |
| A43 | Edit a routine | PUT /routines/{id} `apps/api/src/lonora_api/routes/routines.py:43` | none | - | - | NT |
| A44 | Delete a routine | DELETE /routines/{id} `apps/api/src/lonora_api/routes/routines.py:59` | none | - | - | NT |
| A45 | See a routine's run history | GET /routines/{id}/history | none specific; agent_inspect runs is unfiltered, 10 a page `packages/tools/src/lonora_tools/supervision.py:281` | - | - | RO (weak) |
| A46 | List, add, edit an agent's goals | /agent-goals `apps/api/src/lonora_api/routes/agent_goals.py:9` | none | - | - | NT |
| A47 | List an agent's trading goals | GET /trading/goals | goal_list; agent_inspect work | own + supervised | T / N | C |
| A48 | Pause, resume, cancel a trading goal | POST /trading/goals/{id}/control | goal_control `packages/tools/src/lonora_tools/trading_goal.py:541` | own agent, same conversation | T | OWN |
| A49 | Wake a goal step now | POST /trading/goals/{id}/wake `apps/api/src/lonora_api/routes/trading_goals.py:83` | none; indirect: agent_control message, peer_send `packages/tools/src/lonora_tools/supervision.py:431` | - | - | NT (weak) |
| A50 | Read a goal's decisions | GET /trading/goals/{id}/decisions | goal_decisions `packages/tools/src/lonora_tools/trading_goal.py:506` | own only | T | RO |
| A51 | Create a chart | /charts | chart_open | all | T | C |
| A52 | Edit a chart | /charts | chart_set_symbol and four more | all | T | C |
| A53 | List charts, read a scene | /charts | chart_list, chart_inspect | all | T | C |
| A54 | Read symbols, quote, candles | GET /market/quote and siblings | market_quote, market_candles, market_instrument; market_symbols | all owned | N / T | C |
| A55 | Read the economic calendar | GET /market/calendar | economic_calendar_read | owner sources | T | C |
| A56 | Read open notifications (all agents) | GET /attention | owner_attention_list `packages/tools/src/lonora_tools/incoming_call.py:121` | this agent and conversation only | T | RO |
| A57 | Read notification history | GET /attention/history | none | - | - | RO |
| A58 | Mark notifications seen | POST /attention/seen `apps/api/src/lonora_api/routes/attention.py:63` | none | - | - | NT |
| A59 | Notification policy | PUT /attention/policy `apps/api/src/lonora_api/routes/attention.py:84` | none | - | - | NT |
| A60 | Per-agent notification rules | PUT /agents/{id}/notifications `apps/api/src/lonora_api/routes/agent_delivery.py:29` | none | - | - | NT |
| A61 | See who supervises an agent | GET /supervision | agent_inspect overview; list_agents | self + supervised | N / T | C |
| A62 | Let one agent supervise another | POST /supervision | supervision_change grant | all owned | T | C |
| A63 | End a supervision | POST /supervision/{id}/revoke | supervision_change revoke | all owned | T | C |
| A64 | Pause or resume a whole agent | PATCH /agents/{id} | agent_control target agent; money standing: owner message only | supervised | T | C |
| R1 | List agents, open one | GET /agents | list_agents; agent_inspect | all | T / N | C |
| R2 | Create an agent from a template | POST /agents/create | agent_create `packages/tools/src/lonora_tools/agents.py:371`; card create_agent without owner message | all; not for a delegated agent | T | C+CARD |
| R3 | Edit an agent (name, instructions, avatar, market) | PATCH /agents/{id} | none; agent_control "never ... edits its memory or instructions" `packages/tools/src/lonora_tools/supervision.py:618` | - | - | NT |
| R4 | Pause / resume an agent | as A64 | as A64 | supervised, or any on owner message | T | C |
| R5 | Set trading level Analysis / Ask me | as A25 | as A25 | - | - | NT |
| R6 | Read an agent's model | GET /agents/{id}/model | model_list | any owned | T | C |
| R7 | Set an agent's model | PUT /agents/{id}/model | model_request `packages/tools/src/lonora_tools/models.py:376`; card agent_model | other agents: personal agent only | T | C+CARD |
| R8 | Per-agent notification rules | as A60 | as A60 | - | - | NT |
| R9 | See who supervises whom | as A61 | as A61 | self + supervised | N | C |
| R10 | Grant supervision | as A62 | as A62 | all owned | T | C+CARD |
| R11 | Revoke supervision | as A63 | as A63 | all owned | T | C |
| R12 | Light goals of an agent | as A46 | as A46 | - | - | NT |
| R13 | Knowledge notes of an agent | POST /agents/{id}/knowledge/notes | none | - | - | NT |
| R14 | Knowledge links of an agent | /knowledge-links | none | - | - | NT |
| R15 | Semantic memory on/off and model | PUT /memory/semantic/config | none | - | - | NT |
| R16 | Read an agent's memory | GET /agents/{id}/memory | memory_read; agent_inspect memory | own; supervised read-only | N | C |
| R17 | Edit an agent's memory | PUT /agents/{id}/memory `apps/api/src/lonora_api/routes/memory.py:71` | memory_write `packages/tools/src/lonora_tools/memory.py:276` | caller only `packages/tools/src/lonora_tools/memory.py:115` | N | OWN |
| R18 | Memory and profile revision history | GET /agents/{id}/memory/revisions | none | - | - | RO |
| R19 | Undo a memory or profile change | POST /memory/revisions/{id}/revert | none | - | - | NT |
| R20 | Read the owner profile | GET /owner/profile | memory_read | all | N | C |
| R21 | Edit the owner profile text | PUT /owner/profile | memory_write USER.md, owner message | all | N | C |
| R22 | Preferences: language, reach me, quiet hours, time zone | PUT /owner/preferences | owner_preferences_update, owner message required; language ar, en, auto | all | T | C |
| R23 | Owner name and form of address | PUT /owner/preferences | none; not in the tool input `packages/tools/src/lonora_tools/memory.py:156` | - | - | NT |
| R24 | Message an agent | POST /threads/{id}/messages | peer_send | any owned | N | C (peer request) |
| R25 | Read a conversation | GET /threads/{id}/messages | session_search | own + supervised | N | C |
| R26 | React to a message | PUT .../reactions | message_react | own thread | T | C |
| R27 | Stop a run | POST /runs/{id}/cancel | none | - | - | NT |
| R28 | Retry / resume a run | POST /runs/{id}/retry | none | - | - | NT |
| R29 | Pin, mute, archive, mark unread a chat | PATCH /threads/{id}/prefs | none | - | - | NT |
| R30 | Clear a chat | POST /threads/{id}/clear | none | - | - | NT |
| R31 | Chat lists | /chat-lists | none | - | - | NT |
| R32 | "Keep archived" setting | PUT /threads/settings | none | - | - | NT |
| R33 | Web search on for one chat | PUT /threads/{id}/options | none | - | - | NT (low value) |
| R34 | Search everything | GET /search | search_internal `packages/tools/src/lonora_tools/search.py:316`; session_search; no files, skills, tasks | own + supervised | T / N | RO (partial) |
| R35 | Create a group chat | POST /groups/create | none | - | - | NT |
| R36 | Edit a group | PUT /groups/{id} | none | - | - | NT |
| R37 | See a collaboration's state | GET /threads/{id}/collaboration | collaboration_inspect | owner session | T | C |
| R38 | See an agent's skills | GET /agents/{id}/skills/catalog | skills_list; capabilities_list | own; all via capabilities_list | N / T | C |
| R39 | Create or edit a skill | POST /skills `apps/api/src/lonora_api/routes/agent_skills.py:122` | skill_package_create `packages/tools/src/lonora_tools/skills.py:123` | caller only | T | OWN |
| R40 | Enable, disable, delete a skill | PUT/DELETE /skills/{id} `apps/api/src/lonora_api/routes/agent_skills.py:122` | skill_package_control `packages/tools/src/lonora_tools/skills.py:145` | caller only | T | OWN |
| R41 | Skill versions; go back | POST /skills/{id}/restore `apps/api/src/lonora_api/routes/agent_skills.py:135` | skill_package_control rollback | caller only | T | OWN |
| R42 | Block a skill version | POST /agents/{id}/skills/revocations | none | - | - | NT |
| R43 | See what is connected | GET /capabilities | capabilities_list | all | T | C |
| R44 | Add an MCP server | POST /mcp | card connect_credential `packages/tools/src/lonora_tools/owner_actions.py:291` | all | T | CARD |
| R45 | List MCP servers; test one | GET /mcp | mcp_connections | all | T | C (unsaved dry run owner-only) |
| R46 | Trust an MCP server's tools | POST /trusted-sources/mcp/{id} | card trust_source | all | T | CARD |
| R47 | Add a trusted source | POST /trusted-sources | card trust_source; GitHub owner and repository have no other path: the page posts only feed_domain `apps/web/src/shell/settings/IntegrationsPage.tsx:205` | all | T | CARD |
| R48 | Revoke or restore a trusted source | POST /trusted-sources/{id}/revoke | none | - | - | NT |
| R49 | Subscribe a news feed | POST /integrations | news_feed_subscribe `packages/tools/src/lonora_tools/feeds.py:178`; trust card | all | T | C+CARD |
| R50 | Remove a news feed | DELETE /api/integrations/{id} (as R49) | none | - | - | NT |
| R51 | Connect Telegram | POST /integrations (as R49) | none; not a credential target `packages/db/src/lonora_db/capability_cards.py:38` | - | - | NT |
| R52 | Disconnect Telegram | DELETE /api/integrations/{id} (as R49) | none | - | - | NT |
| R53 | Save a model provider key | PUT /providers/{provider}/credential | none | - | - | NT |
| R54 | See providers and catalogs; test | GET /providers | model_list | all | T | C (read) |
| R55 | Set default model routing | PUT /settings/models | none | - | - | NT |
| R56 | Allow more models | PUT /settings/models/allowed | card agent_model, confirming adds to the allowed list | all | T | CARD |
| R57 | List files | GET /artifacts | none | - | - | RO |
| R58 | Open a file | GET /artifacts/{id}/file | artifact_read | any artifact | T | C |
| R59 | Attach a file to a chat | POST /artifacts/upload | artifact_create | current thread | T | C |
| R60 | Edit a text file | PUT /artifacts/{id}/text | none | - | - | NT |
| R61 | Delete a file | DELETE /artifacts/{id} | none | - | - | NT |
| R62 | Agent scratchpad notes | /scratchpad `apps/api/src/lonora_api/routes/scratchpad.py:5` | scratchpad_read `packages/tools/src/lonora_tools/scratchpad.py:42`, scratchpad_write | caller only | T | OWN |
| R63 | Read the alerts inbox and history | as A56 | as A56 | caller and thread only | T | OWN (read) |
| R64 | Alert filter | as A59 | as A59 | - | - | NT |
| R65 | Usage and cost, CSV |  | none | - | - | RO |
| R66 | Activity log of all agents | GET /activity | none owner-wide; agent_inspect runs: one supervised agent | - | N | RO (partial) |
### Gaps by class

[OWNER-ONLY]: stays the owner's act for security (at most a card). [LATENT]: other agents only. [weak]: a related path exists.

**NO-TOOL (45):** 1 A4 test connection. 2 A5 disconnect broker account. 3 A6 simulation snapshot. 4 A14 stop all new trades (a card resumes, none stops). 5 A24 revoke grant. 6 A25 change trading level (raising [OWNER-ONLY]). 7 A26 change agent market. 8 A32 delete watch record. 9 A38 complete task. 10 A39 delete task. 11 A43 edit routine. 12 A44 delete routine. 13 A46 agent goals. 14 A49 wake goal step [weak]. 15 A58 mark notifications seen. 16 A59 notification policy. 17 A60 per-agent notification rules. 18 R3 edit agent. 19 R5 trading level Analysis / Ask me (raising a card). 20 R8 per-agent notification rules. 21 R12 light goals. 22 R13 knowledge notes. 23 R14 knowledge links. 24 R15 semantic memory setting. 25 R19 undo memory or profile change (`owner_preferences_update` returns `"revertible": True`, `packages/tools/src/lonora_tools/memory.py:256`). 26 R23 owner name, address. 27 R27 stop a run. 28 R28 retry or resume a run. 29 R29 pin, mute, archive. 30 R30 clear chat. 31 R31 chat lists. 32 R32 "keep archived". 33 R33 per-chat web search. 34 R35 create group. 35 R36 edit group. 36 R42 block skill version. 37 R48 revoke or restore trusted source. 38 R50 remove news feed. 39 R51 connect Telegram [OWNER-ONLY] for the token. 40 R52 disconnect Telegram. 41 R53 provider API key [OWNER-ONLY]. 42 R55 default model routing: message [2] («النموذج غير متاح») was `model_not_configured` in all five failed runs; routing was set by the owner at 2026-11-11 09:37:25 UTC (production trace Part 1, Q7). 43 R60 edit text file. 44 R61 delete file. 45 R64 alert filter.

**OWN (13), all [LATENT]:** 46 A28 watch for another agent. 47 A30 cancel its watch (SCRIPTED `market_watches_not_found`, `scripts/parity_trading_probe.py`). 48 A31 extend its watch (same). 49 A35 its task, create. 50 A37 its task, cancel. 51 A41 its routine, create. 52 A48 its trading goal. 53 R17 its memory. 54 R39 its skill, create or edit. 55 R40 its skill, enable, disable, remove. 56 R41 its skill, roll back. 57 R62 its scratchpad. 58 R63 its alerts, read. SCRIPTED (`scripts/parity_trading_probe.py`): with T holding a watch, routine, task, `watch_list`, `routine_list`, `task_inspect`, `goal_list` return empty lists; `routine_toggle`, `agent_control` pause on T's rows succeed; `agent_control` cancel gives `tool_arguments_invalid`.

**READ-ONLY-GAP (10):** 59 A34 another agent's task detail [LATENT]. 60 A45 routine run history [weak]. 61 A50 another agent's goal decisions [LATENT]. 62 A56 notifications of other agents [LATENT]. 63 A57 notification history. 64 R18 memory and profile revisions. 65 R34 owner-wide search (partial). 66 R57 list files. 67 R65 usage and cost. 68 R66 owner-wide activity log (partial).

**CARD (12, not gaps):** A3, A10, A13, A15, A18, A20, A22, A23, R44, R46, R47, R56.

### Discovery makes covered actions unreachable

T tools include `watch_cancel`, `watch_list`, `task_control`, `routine_toggle`, `goal_control`, `trade_close_positions`, `agent_control`; native exceptions `agent_inspect`, `watch_create`. Every card is raised by a T tool.

Production: the one `tool_environment` call of the conversation (run 3fa683e6, 10:53:57 UTC, «شوف ادواتك») was `{"query":"watch cancel task routines goals"}` and returned `{"ok": true, "tools": [], "total": 0, ...}` (production trace Part 4) although `watch_cancel` and `task_control` exist. SCRIPTED on main (`scripts/check_parity_discovery.py`): same empty list; the rarest token, "goals", is in 2 tools, at least 3 of 5 tokens must be covered, and neither tool covers them (`packages/tools/src/lonora_tools/tool_discovery.py:62`, `packages/tools/src/lonora_tools/tool_discovery.py:71`). The empty list is the search gate, not a missing tool.

SCRIPTED Part A queries (`scripts/parity_trading_probe.py`): "stop all trading emergency brake", "edit routine schedule", "disconnect broker account", "mark notification seen" gave `[]`; "cancel task another agent" gave `subagent_spawn`, `trade_restriction_create`.

SCRIPTED Part B (`scripts/parity_discovery.py`; 51 queries, 9 Arabic, all `[]`). Found: `change model`, `reply language`, `quiet hours`, `subscribe feed`, `pause agent`; `trust source` and `supervise agent` 4th. Missed although the tool exists: `غيّر النموذج`, `لغة الرد`, `ساعات الهدوء`, `ثبّت مهارة`, `أوقف الوكيل مؤقتا` (`[]`); `install skill` gave `['skill_view']`; `add mcp server` gave `chart_add_indicator`, `memory_write`, `chart_annotate`, `trade_restriction_create`. Tool absent, `[]`: `rename agent`, `mute chat`, `edit file`, `connect telegram`, `usage cost` and 6 more. Tool absent, unrelated tools returned: `delete agent`, `delete chat`, `delete file` (`workspace_update`, `chart_annotate`); `create group` (`group_silence`); `change agent name` (seven tools); `clear chat history` (`trade_execute`, `watch_update`); `remove mcp server` (`mcp_execute`, `mcp_tools`, none removes).

The catalog is English only and the model cannot tell "no such tool" from "the search missed it". Exact names always work (`packages/tools/src/lonora_tools/registry.py:349`); the model sees all 126 names and is told to inspect "before claiming an ability is absent" (`packages/tools/src/lonora_tools/registry.py:429`); `owner_action_propose` is filed under `trading:` (`packages/tools/src/lonora_tools/loader.py:43`). In the conversation run ddae66ad (answer to [62] «ألغِ المهمة بالكامل») never called `tool_environment`; none of the 36 tool calls is `watch_cancel`, `watch_list`, `task_control` or `agent_control`. For [68] to [77] "delete" means either stop the watch (`watch_cancel`, T) or remove the record (A32); «ما عندي أداة حذف» is true only for the second.

### API-only findings

No client call site (negative grep; UNSURE for old clients). Part A: GET /trading/restrictions (`apps/api/src/lonora_api/routes/trading_restrictions.py:26`); risk-status and exposure (`apps/api/src/lonora_api/routes/execution_policy.py:146`); POST /trading/goals and PUT plan (`apps/api/src/lonora_api/routes/trading_goals.py:46`); opportunities (`apps/api/src/lonora_api/routes/opportunities.py:13`); decisions (`apps/api/src/lonora_api/routes/trading_decisions.py:13`); performance (`apps/api/src/lonora_api/routes/performance.py:14`). Part B: DELETE /api/agents/{id} (`apps/api/src/lonora_api/routes/agents.py:165`), reachable only through the Undo on the `agent_created` card, which deletes an unused agent and otherwise only pauses it (`packages/db/src/lonora_db/agent_creation.py:323`); DELETE /api/threads/{id} (`apps/api/src/lonora_api/routes/threads.py:98`); agent secrets (`apps/api/src/lonora_api/routes/agent_secrets.py:12`) and device list and delete (`apps/api/src/lonora_api/routes/device_authority.py:31`), both [OWNER-ONLY]. Skill install from GitHub exists only as the tool `skill_package_import` (`packages/tools/src/lonora_tools/skills.py:130`).

### Open items

- UNSURE: whether the personal agent's grant lets it close a position another agent opened (executor ownership checks not traced).
- UNSURE: who cancelled the task «إدارة حساب التداول» at 10:51:04 UTC (trace: "not in this thread (probably from the UI)"); no tool call did. Trace bodies must confirm: arguments and results of runs outside the seven in Part 4; `ln_agent_tool_usage`.
- UNSURE: which API call wrote `ln_settings.model_routing` at 09:37:25 UTC (`PUT /api/settings/models`, `apps/api/src/lonora_api/routes/model_router.py:20`).
- UNSURE: the `connect_credential` form fields per target (`apps/web/src/components/owner-actions/OwnerActionCard.tsx:177`); whether each cited web page is mounted and linked.
- UNSURE: whether a voice message's `origin` is `owner` (`packages/db/src/lonora_db/messages.py:67`; `owner_typed_message` does not exclude voice, `packages/db/src/lonora_db/owner_words.py:62`). The Turkish replies [50], [51] are not a missing tool.
- A14 to A16 rest on code reading (the scripted run did not change the global controls).
