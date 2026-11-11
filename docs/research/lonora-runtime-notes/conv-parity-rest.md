# Parity inventory, part 2: everything that is not trading, market, watch or task

Repository `/home/user/lonorabot`, main HEAD `9f5b1da`. Read-only audit; nothing under the repository was changed.
Owner brief section 6: every action the owner can take from the interface, against the tool that lets the agent do the same on any of the owner's resources, or the approval card that stands in for it.

## 0. Scope, method, what was run, what was skipped

**In scope:** agents (create, edit, delete, profile, permission level, model), threads, messages, groups, collaboration, memory and owner profile, skills, MCP servers and capabilities, model connections and provider settings, trusted sources and feeds, files (artifacts, scratchpad), channels (Telegram, webhook), voice and call settings, owner preferences (reply language, quiet hours), devices, sessions and security, usage, backups and ops.

**Skipped (another agent covers them):** every route under `/api/trading`, `/api/market`, `/api/watches`, `/api/tasks`, `/api/routines`, `/api/boards`, `/api/tickets`, `/api/charts`, `/api/account-authorities`, `/api/agents/{id}/account-authorities`, `/api/agents/{id}/performance`, and the trading card kinds (`resume_trading`, `lift_restriction`, `resolve_operation`, `set_account_limits`, `grant_authority`). They are named here only where a non-trading action ends in one of them.

**Method.**
1. Route list: walked every router the app mounts (`apps/api/src/lonora_api/app.py:124`, `apps/api/src/lonora_api/app.py:127`) and printed method, path and handler `path:line`. Script `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/parity_routes.py`, output `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/parity_routes.tsv`: 276 routes (273 HTTP + 3 websocket). The OpenAPI schema of the same app counts 275 HTTP operations; the difference of 2 is outside the `/api` routers walked here (the health router, `apps/api/src/lonora_api/app.py:123`, is one; not examined further).
2. Client call sites: grep of `apps/web/src`, `apps/mobile/app`, `apps/mobile/lib`, `apps/mobile/components`, `packages/ui-web`, `packages/chat-ui` for the path fragments; output `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/parity_client_calls.tsv` (375 hits outside the skipped areas). A route with no client call site is listed in section 6 and is not counted as an owner action.
3. Tool list: loaded the live registry (`packages/tools/src/lonora_tools/loader.py:53`): 126 tools. Script `scripts/parity_tools.py`, output `runs/parity_tools.tsv` (same audit directory).
4. Exposure of the Personal Agent: ran `registry.exposure(["core","market","coordination"])` (`packages/tools/src/lonora_tools/registry.py:270`), output `runs/parity_exposure.txt`: 23 native tools, the same 23 names the production trace reports for every run of the conversation.
5. Discovery: ran the ranking function that `tool_environment` uses (`packages/tools/src/lonora_tools/registry.py:362`) on 51 SCRIPTED owner phrasings; script `scripts/parity_discovery.py`, output `runs/parity_discovery.txt`. Section 7.

`git -C /home/user/lonorabot status --short` is empty after all runs.

## 1. How the Personal Agent reaches a tool (applies to every row)

- **Native** means the schema is in the model's tools array from the first turn. The Personal Agent gets profiles `core`, `market`, `coordination` (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:43`, `packages/agent-runtime/src/lonora_agent/tool_exposure.py:46`). Result: 23 native tools (`runs/parity_exposure.txt`). Of the tools in this document only these are native: `memory_read`, `memory_write`, `session_search`, `skills_list`, `skill_view`, `peer_send`, `agent_inspect`, `web_search`, `wait_for_input`, `tool_environment`, `tool_call`.
- **Discovery-only** means the tool has no eager profile for the Personal Agent. Its name is in the capability inventory text (bounded by `MAX_CAPABILITY_INVENTORY_CHARS = 8000`, `packages/tools/src/lonora_tools/registry.py:61`; the full inventory is 3056 characters today, `runs/parity_discovery.txt`), and it is callable only through `tool_call` after the model finds it. Up to six recently used tools are promoted per agent (`MAX_PROMOTED_TOOLS = 6`, `packages/tools/src/lonora_tools/registry.py:85`). No tool in this document is "not available": every registered tool stays callable through the bridge. The weak point is finding it (section 7).
- **Owner-message rule.** Several tools act directly only when the run answers the owner's own typed message and has read nothing that someone else wrote; otherwise they fall back to a card or a refusal (`packages/tools/src/lonora_tools/restrictions.py:97`, `packages/tools/src/lonora_tools/restrictions.py:114`). The doc comment lists them: "supervision, agent creation and control, the owner profile and reach-me, model switches". This is a safety rule and must stay; it is marked "owner message" in the table.
- **Supervision.** The Personal Agent is granted supervision over every other agent by default (`packages/db/src/lonora_db/supervision.py:230`), so the "agents you supervise" tools reach all of the owner's agents unless the owner revoked a grant.

## 2. Cards: exactly which owner actions an agent can propose

No tool can confirm a card ("No tool can confirm a card", `packages/tools/src/lonora_tools/owner_actions.py:5`). The owner decides at `POST /api/owner-actions/{card_id}/decision` (`apps/api/src/lonora_api/routes/owner_actions.py:177`), called from `apps/web/src/components/owner-actions/OwnerActionCard.tsx:153`.

| Tool that raises it | Card kinds | Owner action it stands in for | Citation |
|---|---|---|---|
| `owner_action_propose` (discovery-only) | `resume_trading`, `lift_restriction`, `resolve_operation`, `set_account_limits`, `grant_authority` | trading (skipped here) | kinds: `packages/contracts/src/lonora_contracts/owner_actions.py:20`; tool: `packages/tools/src/lonora_tools/owner_actions.py:291` |
| `owner_action_propose` | `trust_source` with `source_kind` `mcp_server`, `github_owner`, `github_repo`, `feed_domain` | add to the trusted list; for an MCP server, trust its tools | `packages/contracts/src/lonora_contracts/owner_actions.py:45`, `packages/db/src/lonora_db/capability_cards.py:37`, `packages/tools/src/lonora_tools/owner_actions.py:246` |
| `owner_action_propose` | `connect_credential` with `target` `mcp_server`, `news_feed`, `brave_search`, `economic_calendar`, `broker` | a secure form; "a secure form whose value goes straight to the server, never to you" | `packages/contracts/src/lonora_contracts/owner_actions.py:47`, `packages/db/src/lonora_db/capability_cards.py:38` |
| `agent_create` (discovery-only) | `create_agent` (proposal), `agent_created` (Undo after a direct creation) | create an agent; delete the one just created | `packages/tools/src/lonora_tools/agents.py:292`, `packages/tools/src/lonora_tools/agents.py:315`; decision: `apps/api/src/lonora_api/routes/owner_actions.py:410`, `apps/api/src/lonora_api/routes/owner_actions.py:413` |
| `supervision_change` (discovery-only) | `supervise` (proposal), `supervision_created` (Undo), `supervision_stopped` (Restore) | set or restore who supervises whom | `packages/tools/src/lonora_tools/supervision.py:547`; lifetimes list: `packages/db/src/lonora_db/owner_actions.py:76` |
| `agent_control` (discovery-only) | `supervision_paused` (who paused, with Resume) | resume work a supervisor paused | `packages/db/src/lonora_db/owner_actions.py:80` |
| `model_request` (discovery-only) | `agent_model` (proposal; confirming also adds the model to the allowed list), `agent_model_changed` (Undo) | set an agent's model; allow a model | `packages/contracts/src/lonora_contracts/owner_actions.py:31`, `packages/tools/src/lonora_tools/models.py:300` |
| `news_feed_subscribe`, `skill_package_import` (discovery-only) | `trust_source` (feed domain; GitHub repository) | trust the source, then subscribe / install | `packages/tools/src/lonora_tools/feeds.py:149`, `packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:235` |

Not proposable by any tool (no card kind exists): editing an agent, deleting an agent, the trading level Analysis/Ask-me, per-agent notification rules, groups, chat organisation, a model provider key, the default model routing, Telegram, removing a feed, an MCP server or a trusted source, blocking a skill version, deleting or editing a file. `CREDENTIAL_TARGETS` has no model-provider and no Telegram entry (`packages/db/src/lonora_db/capability_cards.py:38`).

## 3. The table

Verdict values: **COVERED** (a tool does it directly), **COVERED+CARD** (tool acts on the owner's message, otherwise raises the card), **CARD-ONLY**, and the gap classes **NO-TOOL**, **OWN-AGENT-ONLY** (= TOOL-BUT-OWN-AGENT-ONLY), **READ-ONLY-GAP**. "PA" = the Personal Agent. Exposure is for a PA conversation run.

### 3.1 Agents

| # | Owner action | API route (handler) | Client call site | Agent tool or card | Ownership scope of the tool | PA exposure | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | List agents, open one | `GET /api/agents` `apps/api/src/lonora_api/routes/agents.py:49`; `GET /api/agents/{id}` `apps/api/src/lonora_api/routes/agents.py:123` | `apps/web/src/hooks/useAgents.ts:7` | `list_agents` `packages/tools/src/lonora_tools/agents.py:362`; `agent_inspect` (overview) `packages/tools/src/lonora_tools/supervision.py:600`; the directory is also injected into context `packages/agent-runtime/src/lonora_agent/context/team.py:44` | all of the owner's agents (`packages/tools/src/lonora_tools/agents.py:67`) | `list_agents` discovery-only; `agent_inspect` native | COVERED |
| 2 | Create an agent from a template | `POST /api/agents/create` `apps/api/src/lonora_api/routes/agents.py:79` | `apps/web/src/pages/shell/bot-panel.tsx:132` | `agent_create` `packages/tools/src/lonora_tools/agents.py:371`: same input and service as the route; card `create_agent` when no owner message (`packages/tools/src/lonora_tools/agents.py:292`) | owner-wide; refused for a delegated agent (`packages/tools/src/lonora_tools/agents.py:235`) | discovery-only | COVERED+CARD |
| 3 | Edit an agent: name, title, description, instructions, avatar, colour, focus market | `PATCH /api/agents/{id}` `apps/api/src/lonora_api/routes/agents.py:141`; fields `packages/contracts/src/lonora_contracts/domain.py:41` | `apps/web/src/shell/agent/IdentityPage.tsx:112`, `apps/web/src/shell/agent/AvatarSheet.tsx:163` | none. `agent_control` says it "never trades, grants, raises limits, lifts restrictions or edits its memory or instructions" (`packages/tools/src/lonora_tools/supervision.py:618`) | - | - | **NO-TOOL** |
| 4 | Pause / resume an agent | `PATCH /api/agents/{id}` with `paused` `apps/api/src/lonora_api/routes/agents.py:141` | `apps/web/src/shell/agent/AgentPage.tsx:179` | `agent_control` `packages/tools/src/lonora_tools/supervision.py:610` | an agent it supervises, or any agent when the PA acts on the owner's message (`packages/db/src/lonora_db/supervision.py:661`); never itself (`packages/db/src/lonora_db/supervision.py:657`), never the PA (`packages/db/src/lonora_db/supervision.py:688`); a whole trading agent only on the owner's message (`packages/db/src/lonora_db/supervision.py:692`) | discovery-only | COVERED (the limits are safety rules) |
| 5 | Set the trading level Analysis / Ask me; save the permission draft | `PUT /api/agents/{id}/permissions` `apps/api/src/lonora_api/routes/agent_permissions.py:19`; `PUT .../permissions/customization` `apps/api/src/lonora_api/routes/agent_permissions.py:30` | `apps/web/src/conversation/PermissionMenu.tsx:216`, `apps/web/src/components/permissions/AgentPermissions.tsx:305` | none for the level. (Autonomous is the `grant_authority` card, trading part.) | - | - | **NO-TOOL** |
| 6 | Read an agent's model | `GET /api/agents/{id}/model` `apps/api/src/lonora_api/routes/agent_models.py:31`; `.../model/summary` `apps/api/src/lonora_api/routes/agent_models.py:50` | `apps/web/src/components/models/AgentModelCard.tsx:30` | `model_list` `packages/tools/src/lonora_tools/models.py:390` with `agent_id` | any owned agent (`packages/tools/src/lonora_tools/models.py:167`) | discovery-only | COVERED |
| 7 | Set an agent's model | `PUT /api/agents/{id}/model` `apps/api/src/lonora_api/routes/agent_models.py:39` | `apps/web/src/components/models/AgentModelCard.tsx:54` | `model_request` `packages/tools/src/lonora_tools/models.py:376`; card `agent_model` unless the owner's message names the model (`packages/tools/src/lonora_tools/models.py:300`) | another agent's model: PA only (`packages/tools/src/lonora_tools/models.py:243`) | discovery-only | COVERED+CARD |
| 8 | Per-agent notification rules (in-app on/off, calls on/off, daily limit) | `GET/PUT /api/agents/{id}/notifications` `apps/api/src/lonora_api/routes/agent_delivery.py:22`, `apps/api/src/lonora_api/routes/agent_delivery.py:29` | `apps/web/src/shell/settings/NotifyPages.tsx:323` | none | - | - | **NO-TOOL** |
| 9 | See who supervises whom | `GET /api/supervision` `apps/api/src/lonora_api/routes/supervision.py:27` | `apps/web/src/components/ai/SupervisionSettings.tsx:23` | `agent_inspect` overview (`supervised_by`, `packages/tools/src/lonora_tools/supervision.py:160`); `list_agents` | supervised agents or itself (`packages/tools/src/lonora_tools/supervision.py:415`) | native | COVERED |
| 10 | Grant supervision | `POST /api/supervision` `apps/api/src/lonora_api/routes/supervision.py:35` | `apps/web/src/shell/agent/AgentPage.tsx:579` | `supervision_change` `packages/tools/src/lonora_tools/supervision.py:625`; card `supervise` without the owner's message (`packages/tools/src/lonora_tools/supervision.py:547`) | owner-wide | discovery-only | COVERED+CARD |
| 11 | Revoke supervision | `POST /api/supervision/{id}/revoke` `apps/api/src/lonora_api/routes/supervision.py:49` | `apps/web/src/shell/agent/AgentPage.tsx:487` | `supervision_change` action `revoke`: only on the owner's message (`packages/tools/src/lonora_tools/supervision.py:503`), never the agent's own oversight (`packages/tools/src/lonora_tools/supervision.py:500`) | owner-wide | discovery-only | COVERED (limits are safety rules) |
| 12 | Light goals of an agent (a note, schedules nothing): create, edit | resource routes `/api/agent-goals` `apps/api/src/lonora_api/routes/agent_goals.py:9` (`apps/api/src/lonora_api/routes/__init__.py:35`, `apps/api/src/lonora_api/routes/__init__.py:57`) | `apps/web/src/shell/domain/api.ts:80`, `apps/web/src/shell/domain/api.ts:82` | none (the `goal_*` tools are trading goals) | - | - | **NO-TOOL** |
| 13 | Knowledge notes of an agent: add, edit | `POST/PUT /api/agents/{id}/knowledge/notes` `apps/api/src/lonora_api/routes/knowledge.py:27`, `apps/api/src/lonora_api/routes/knowledge.py:45`; `POST /api/agents/{id}/memory/semantic` `apps/api/src/lonora_api/routes/memory.py:212` | `apps/web/src/shell/domain/api.ts:88`, `apps/web/src/shell/domain/api.ts:90`, `apps/web/src/pages/KnowledgeSection.tsx:195` | none | - | - | **NO-TOOL** |
| 14 | Knowledge links of an agent: add, edit | resource routes `/api/knowledge-links` `apps/api/src/lonora_api/routes/agent_goals.py:10` | `apps/web/src/shell/domain/api.ts:92`, `apps/web/src/shell/domain/api.ts:94` | none | - | - | **NO-TOOL** |
| 15 | Semantic memory on/off and its model | `PUT /api/memory/semantic/config` `apps/api/src/lonora_api/routes/memory.py:201` | `apps/web/src/pages/KnowledgeSection.tsx:153` | none | - | - | **NO-TOOL** |

### 3.2 Memory and owner profile

| # | Owner action | API route (handler) | Client call site | Agent tool or card | Ownership scope of the tool | PA exposure | Verdict |
|---|---|---|---|---|---|---|---|
| 16 | Read an agent's memory | `GET /api/agents/{id}/memory` `apps/api/src/lonora_api/routes/memory.py:61` | `apps/web/src/pages/KnowledgeSection.tsx:22` | `memory_read` `packages/tools/src/lonora_tools/memory.py:266` (own: `packages/tools/src/lonora_tools/memory.py:73`); `agent_inspect` section `memory`, "(read-only)" `packages/tools/src/lonora_tools/supervision.py:600` | own; supervised agents read-only | native | COVERED |
| 17 | Edit an agent's memory | `PUT /api/agents/{id}/memory` `apps/api/src/lonora_api/routes/memory.py:71` | `apps/web/src/pages/KnowledgeSection.tsx:62` | `memory_write` `packages/tools/src/lonora_tools/memory.py:276` | the calling agent only: the write passes `context.agent_id` (`packages/tools/src/lonora_tools/memory.py:115`, `packages/tools/src/lonora_tools/memory.py:128`) | native | **OWN-AGENT-ONLY** |
| 18 | Revision history of an agent's memory and of the owner profile | `GET /api/agents/{id}/memory/revisions` `apps/api/src/lonora_api/routes/memory.py:84`; `GET /api/owner/profile/revisions` `apps/api/src/lonora_api/routes/memory.py:146` | `apps/web/src/pages/KnowledgeSection.tsx:105`, `apps/web/src/shell/settings/OwnerPage.tsx:64` | none; `memory_read` returns the provenance of the current revision only (`packages/tools/src/lonora_tools/memory.py:82`) | - | - | **READ-ONLY-GAP** |
| 19 | Undo one memory or profile change | `POST /api/memory/revisions/{id}/revert` `apps/api/src/lonora_api/routes/memory.py:168` | `apps/web/src/pages/MemoryRevisions.tsx:116`, `apps/web/src/shell/settings/OwnerPage.tsx:145` | none | - | - | **NO-TOOL** |
| 20 | Read the owner profile | `GET /api/owner/profile` `apps/api/src/lonora_api/routes/memory.py:110` | `apps/web/src/shell/settings/OwnerPage.tsx:148` | `memory_read` | owner-wide (shared profile) | native | COVERED |
| 21 | Edit the owner profile text | `PUT /api/owner/profile` `apps/api/src/lonora_api/routes/memory.py:117` | `apps/web/src/shell/settings/OwnerPage.tsx:121` | `memory_write` on `USER.md`; owner message required (`packages/tools/src/lonora_tools/memory.py:123`) | owner-wide | native | COVERED |
| 22 | Preferences: reply language, how to reach me, quiet hours, time zone | `PUT /api/owner/preferences` `apps/api/src/lonora_api/routes/memory.py:128` | `apps/web/src/shell/settings/OwnerPage.tsx:126`, `apps/web/src/shell/settings/NotifyPages.tsx:65` | `owner_preferences_update` `packages/tools/src/lonora_tools/memory.py:290`; owner message required (`packages/tools/src/lonora_tools/memory.py:206`) | owner-wide ("Every Agent follows them from its next run") | discovery-only | COVERED |
| 23 | Preferences: the owner's name and form of address | same route; fields `name`, `address` `apps/api/src/lonora_api/routes/memory.py:44` | `apps/web/src/shell/settings/OwnerPage.tsx:126` | not in the tool's input (`packages/tools/src/lonora_tools/memory.py:156`). Free text in `USER.md` is possible but does not set the two fields | - | - | **NO-TOOL** |

### 3.3 Threads, messages, groups

| # | Owner action | API route (handler) | Client call site | Agent tool or card | Ownership scope of the tool | PA exposure | Verdict |
|---|---|---|---|---|---|---|---|
| 24 | Send a message to an agent | `POST /api/threads/{id}/messages` `apps/api/src/lonora_api/routes/messages.py:92` | `apps/web/src/hooks/useThreads.ts:195` | `peer_send` `packages/tools/src/lonora_tools/message.py:63`; `agent_control` action `message` | any owned agent (`packages/agent-runtime/src/lonora_agent/collaboration/peer_messages.py:44`) | native | COVERED |
| 25 | Read a conversation's history | `GET /api/threads/{id}/messages` `apps/api/src/lonora_api/routes/messages.py:21` | `apps/web/src/hooks/useThreads.ts:41` | `session_search` `packages/tools/src/lonora_tools/session_search.py:49` | own history and that of supervised agents (`packages/tools/src/lonora_tools/session_search.py:34`, `packages/memory/src/lonora_memory/sessions.py:154`) | native | COVERED |
| 26 | React to a message | `PUT/DELETE .../reactions` `apps/api/src/lonora_api/routes/messages.py:68`, `apps/api/src/lonora_api/routes/messages.py:81` | `apps/web/src/conversation/Conversation.tsx:340` | `message_react` `packages/tools/src/lonora_tools/message.py:70` (the agent reacts as itself, in its own thread) | own thread | discovery-only | COVERED |
| 27 | Stop a run that is answering | `POST /api/runs/{id}/cancel` `apps/api/src/lonora_api/routes/cancellation.py:16` | `apps/web/src/hooks/useThreads.ts:302` | none for a run. Nearest: `agent_control` pause of the agent or its Task | - | - | **NO-TOOL** |
| 28 | Retry / resume a run | `POST /api/runs/{id}/retry` `apps/api/src/lonora_api/routes/runs.py:63`; `.../resume` `apps/api/src/lonora_api/routes/runs.py:80` | `apps/web/src/conversation/Conversation.tsx:604`, `apps/web/src/hooks/useThreads.ts:306` | none. Nearest: `peer_send` the request again | - | - | **NO-TOOL** |
| 29 | Pin, mute, archive, favourite, mark unread a chat | `PATCH /api/threads/{id}/prefs` `apps/api/src/lonora_api/routes/threads.py:139`; `POST /api/threads/prefs` `apps/api/src/lonora_api/routes/threads.py:50`; fields `packages/contracts/src/lonora_contracts/thread_prefs.py:13` | `apps/web/src/shell/lists/api.ts:14` | none | - | - | **NO-TOOL** |
| 30 | Clear a chat's history | `POST /api/threads/{id}/clear` `apps/api/src/lonora_api/routes/threads.py:150` | `apps/web/src/shell/lists/api.ts:19` | none | - | - | **NO-TOOL** |
| 31 | Chat lists: create, rename, reorder, delete, set members | `apps/api/src/lonora_api/routes/chat_lists.py:27`, `apps/api/src/lonora_api/routes/chat_lists.py:35`, `apps/api/src/lonora_api/routes/chat_lists.py:46`, `apps/api/src/lonora_api/routes/chat_lists.py:55` | `apps/web/src/shell/lists/api.ts:21`, `apps/web/src/shell/lists/api.ts:26` | none | - | - | **NO-TOOL** |
| 32 | "Keep archived chats archived" setting | `PUT /api/threads/settings` `apps/api/src/lonora_api/routes/threads.py:66` | `apps/web/src/shell/lists/api.ts:20` | none | - | - | **NO-TOOL** |
| 33 | Switch web search on for one chat | `PUT /api/threads/{id}/options` `apps/api/src/lonora_api/routes/threads.py:116` | `apps/web/src/conversation/threadOptions.ts:27` | none to change the option. The PA already has `web_search` natively (`packages/tools/src/lonora_tools/search.py:342`) | - | - | **NO-TOOL** (low value for the PA) |
| 34 | Search everything (chats, messages, tasks, files, knowledge, skills) | `GET /api/search` `apps/api/src/lonora_api/routes/search.py:13`; categories `packages/contracts/src/lonora_contracts/search.py:9` | `apps/web/src/shell/lists/UnifiedSearch.tsx:43` | `search_internal` `packages/tools/src/lonora_tools/search.py:316`, `session_search`: agent names, own memory, own and supervised conversations (`packages/tools/src/lonora_tools/search.py:62`). No files, skills or tasks category | own + supervised | `search_internal` discovery-only; `session_search` native | **READ-ONLY-GAP** (partial) |
| 35 | Create a group chat | `POST /api/groups/create` `apps/api/src/lonora_api/routes/groups.py:17` | `apps/web/src/shell/agent/GroupPage.tsx:268` | none. `collaboration_start` invites agents into one discussion of the current conversation (`packages/tools/src/lonora_tools/collaboration.py:119`); it creates no group | - | - | **NO-TOOL** |
| 36 | Edit a group: name, purpose, members, lead | `PUT /api/groups/{id}` `apps/api/src/lonora_api/routes/groups.py:14` (`apps/api/src/lonora_api/routes/__init__.py:57`) | `apps/web/src/shell/agent/GroupPage.tsx:166` | none | - | - | **NO-TOOL** |
| 37 | See a collaboration's state | `GET /api/threads/{id}/collaboration` `apps/api/src/lonora_api/routes/collaboration.py:13` | `apps/web/src/conversation/Conversation.tsx:194` | `collaboration_inspect` `packages/tools/src/lonora_tools/collaboration.py:125` | owner-scoped session | discovery-only | COVERED |

### 3.4 Skills

| # | Owner action | API route (handler) | Client call site | Agent tool or card | Ownership scope of the tool | PA exposure | Verdict |
|---|---|---|---|---|---|---|---|
| 38 | See an agent's skills | `GET /api/agents/{id}/skills/catalog` `apps/api/src/lonora_api/routes/agent_skills.py:213`; `GET /api/skills` `apps/api/src/lonora_api/routes/agent_skills.py:122` | `apps/web/src/pages/SkillsSection.tsx:29`, `apps/web/src/shell/domain/api.ts:97` | `skills_list` `packages/tools/src/lonora_tools/skills.py:152`, `skill_view` `packages/tools/src/lonora_tools/skills.py:161` (own catalog); `capabilities_list` lists installed skills of every agent (`packages/tools/src/lonora_tools/capabilities.py:116`) | own; all agents through `capabilities_list` | native; `capabilities_list` discovery-only | COVERED |
| 39 | Create or edit an instruction skill for an agent | `POST /api/skills`, `PUT /api/skills/{id}` `apps/api/src/lonora_api/routes/agent_skills.py:122` | `apps/web/src/components/skills/CreateSkill.tsx:30`, `apps/web/src/components/skills/SkillEditor.tsx:42` | `skill_package_create` `packages/tools/src/lonora_tools/skills.py:123`: "from this Agent's exact current workspace revision" | the calling agent only (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:65`) | discovery-only | **OWN-AGENT-ONLY** |
| 40 | Enable, disable or delete a skill | `PUT/DELETE /api/skills/{id}` `apps/api/src/lonora_api/routes/agent_skills.py:122` | `apps/web/src/components/skills/SkillEditor.tsx:152` | `skill_package_control` `packages/tools/src/lonora_tools/skills.py:145`, actions `activate`, `disable`, `rollback`, `remove` (`packages/tools/src/lonora_tools/skills.py:71`) | the calling agent only (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:475`, lookup filter `packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:65`) | discovery-only | **OWN-AGENT-ONLY** |
| 41 | Skill version history; go back to a version | `GET /api/skills/{id}/versions` `apps/api/src/lonora_api/routes/agent_skills.py:125`; `POST /api/skills/{id}/restore` `apps/api/src/lonora_api/routes/agent_skills.py:135` | `apps/web/src/shell/domain/api.ts:104`, `apps/web/src/shell/domain/api.ts:107` | `skill_package_control` action `rollback` (own packages) | the calling agent only | discovery-only | **OWN-AGENT-ONLY** |
| 42 | Block one exact skill version for an agent | `POST /api/agents/{id}/skills/revocations` `apps/api/src/lonora_api/routes/agent_skills.py:254` | `apps/web/src/shell/settings/IntegrationsPage.tsx:666` | none | - | - | **NO-TOOL** |

Note: installing a skill from a GitHub repository has no owner route; it exists only as the agent tool `skill_package_import` (`packages/tools/src/lonora_tools/skills.py:130`), with a `trust_source` card for a repository outside the trusted list. Here the agent can do more than the interface.

### 3.5 Capabilities, MCP servers, trusted sources, feeds, channels

| # | Owner action | API route (handler) | Client call site | Agent tool or card | Ownership scope of the tool | PA exposure | Verdict |
|---|---|---|---|---|---|---|---|
| 43 | See what is connected | `GET /api/capabilities` `apps/api/src/lonora_api/routes/capabilities.py:17` | `apps/web/src/shell/settings/IntegrationsPage.tsx:48` | `capabilities_list` `packages/tools/src/lonora_tools/capabilities.py:311` | owner-wide | discovery-only | COVERED |
| 44 | Add an MCP server (address and token) | `POST /api/mcp` `apps/api/src/lonora_api/routes/mcp.py:37`; `POST /api/integrations/secrets` `apps/api/src/lonora_api/routes/integrations.py:80` | `apps/web/src/shell/settings/ConnectionPages.tsx:772`, `apps/web/src/shell/settings/ConnectionPages.tsx:767` | card `connect_credential` target `mcp_server` via `owner_action_propose` `packages/tools/src/lonora_tools/owner_actions.py:291` | owner-wide | discovery-only | CARD-ONLY (secrets rule: "Never ask for a secret in chat; credentials stay on the server", `packages/agent-runtime/resources/system/lonora.md:561`) |
| 45 | List MCP servers; test one | `GET /api/mcp` `apps/api/src/lonora_api/routes/mcp.py:37`; `POST /api/mcp/test` `apps/api/src/lonora_api/routes/connection_tests.py:62` | `apps/web/src/shell/settings/SettingsRoot.tsx:33`, `apps/web/src/shell/settings/ConnectionPages.tsx:838` | `mcp_connections` `packages/tools/src/lonora_tools/mcp.py:411`, `mcp_tools` `packages/tools/src/lonora_tools/mcp.py:421` (saved servers) | owner-wide (`packages/tools/src/lonora_tools/mcp.py:184`) | discovery-only | COVERED |
| 46 | Trust an MCP server's tools (read or write tier) | `POST /api/trusted-sources/mcp/{id}/preview` `apps/api/src/lonora_api/routes/trusted_sources.py:109`; `POST /api/trusted-sources/mcp/{id}` `apps/api/src/lonora_api/routes/trusted_sources.py:129` | `apps/web/src/shell/settings/IntegrationsPage.tsx:71`, `apps/web/src/shell/settings/IntegrationsPage.tsx:74` | card `trust_source` / `mcp_server` (`packages/tools/src/lonora_tools/owner_actions.py:246`) | owner-wide | discovery-only | CARD-ONLY (trust rule: an advertisement never grants authority; the owner reviews the tools) |
| 47 | Add a trusted source (feed site, GitHub owner or repository) | `POST /api/trusted-sources` `apps/api/src/lonora_api/routes/trusted_sources.py:56` | `apps/web/src/shell/settings/IntegrationsPage.tsx:205` | card `trust_source` with `github_owner`, `github_repo`, `feed_domain` (`packages/contracts/src/lonora_contracts/owner_actions.py:45`) | owner-wide | discovery-only | CARD-ONLY (trust rule) |
| 48 | Revoke or restore a trusted source | `POST /api/trusted-sources/{id}/revoke` `apps/api/src/lonora_api/routes/trusted_sources.py:67`; `.../restore` `apps/api/src/lonora_api/routes/trusted_sources.py:78` | `apps/web/src/shell/settings/IntegrationsPage.tsx:233`, `apps/web/src/shell/settings/IntegrationsPage.tsx:239` | none | - | - | **NO-TOOL** |
| 49 | Subscribe a news feed | `POST /api/integrations` `apps/api/src/lonora_api/routes/integrations.py:77` | `apps/web/src/shell/settings/IntegrationsPage.tsx:283` | `news_feed_subscribe` `packages/tools/src/lonora_tools/feeds.py:178`: direct inside a trusted domain, otherwise the trust card (`packages/tools/src/lonora_tools/feeds.py:149`) | owner-wide ("every agent then reads") | discovery-only | COVERED+CARD |
| 50 | Remove a news feed | `DELETE /api/integrations/{id}` `apps/api/src/lonora_api/routes/integrations.py:77` (`apps/api/src/lonora_api/routes/__init__.py:69`) | `apps/web/src/shell/settings/IntegrationsPage.tsx:321` | none; the subscribe result tells the model `"owner_sees": "Capabilities, with Remove"` (`packages/tools/src/lonora_tools/feeds.py:147`) | - | - | **NO-TOOL** |
| 51 | Connect a Telegram bot | `POST /api/integrations/secrets` + `POST /api/integrations` type `telegram` (`packages/contracts/src/lonora_contracts/integrations.py:15`) | `apps/web/src/shell/settings/IntegrationsPage.tsx:366`, `apps/web/src/shell/settings/IntegrationsPage.tsx:370` | none: `telegram` is not a `connect_credential` target (`packages/db/src/lonora_db/capability_cards.py:38`) | - | - | **NO-TOOL** |
| 52 | Disconnect Telegram | `DELETE /api/integrations/{id}` | `apps/web/src/shell/settings/IntegrationsPage.tsx:399` | none | - | - | **NO-TOOL** |

Brave Search and the economic calendar have no settings-page call site that I found; the owner reaches them through the `connect_credential` card form (`apps/web/src/components/owner-actions/OwnerActionCard.tsx:177`). They are therefore card-only by construction and are not a row.

### 3.6 Model connections and provider settings

| # | Owner action | API route (handler) | Client call site | Agent tool or card | Ownership scope of the tool | PA exposure | Verdict |
|---|---|---|---|---|---|---|---|
| 53 | Save a model provider's API key | `PUT /api/providers/{provider}/credential` `apps/api/src/lonora_api/routes/providers.py:27` | `apps/web/src/shell/settings/ConnectionPages.tsx:632` | none: no provider target among the credential cards (`packages/db/src/lonora_db/capability_cards.py:38`) | - | - | **NO-TOOL** |
| 54 | See connected providers and their model catalogs; test | `GET /api/providers` `apps/api/src/lonora_api/routes/providers.py:15`; `.../models` `apps/api/src/lonora_api/routes/providers.py:38`; `.../discover` `apps/api/src/lonora_api/routes/providers.py:47`; `.../test` `apps/api/src/lonora_api/routes/connection_tests.py:43` | `apps/web/src/shell/settings/ConnectionPages.tsx:563`, `apps/web/src/lib/model_catalog.ts:3`, `apps/web/src/lib/model_catalog.ts:5`, `apps/web/src/shell/settings/ConnectionPages.tsx:706` | `model_list` `packages/tools/src/lonora_tools/models.py:390` (connected providers, allowed models, catalog matches) | owner-wide | discovery-only | COVERED (read) |
| 55 | Set the default model routing | `PUT /api/settings/models` `apps/api/src/lonora_api/routes/model_router.py:20` | `apps/web/src/lib/model_routing.ts:13` | none. `model_request` without a model only returns one agent to "the owner's default model" (`packages/tools/src/lonora_tools/models.py:74`) | - | - | **NO-TOOL** |
| 56 | Allow more models for agents to choose | `PUT /api/settings/models/allowed` `apps/api/src/lonora_api/routes/model_router.py:75` | `apps/web/src/pages/AllowedModelsSettings.tsx:33` | card `agent_model`: confirming "adds the model to the allowed list" (`packages/tools/src/lonora_tools/models.py:299`). No way to remove one | owner-wide | discovery-only | CARD-ONLY (owner decides which paid models may be used) |

### 3.7 Files

| # | Owner action | API route (handler) | Client call site | Agent tool or card | Ownership scope of the tool | PA exposure | Verdict |
|---|---|---|---|---|---|---|---|
| 57 | List the files of an agent or a chat | `GET /api/artifacts` `apps/api/src/lonora_api/routes/artifacts.py:19` (`apps/api/src/lonora_api/routes/__init__.py:16`) | `apps/web/src/shell/domain/api.ts:114` | none: `artifact_read` needs an `artifact_id` | - | - | **READ-ONLY-GAP** |
| 58 | Open / download a file | `GET /api/artifacts/{id}/file` `apps/api/src/lonora_api/routes/artifacts.py:150` | `apps/web/src/shell/domain/api.ts:117` | `artifact_read` `packages/tools/src/lonora_tools/artifacts.py:248` | any artifact of the owner; only stored tool results are limited to the same agent and thread (`packages/tools/src/lonora_tools/artifacts.py:207`) | discovery-only for the PA (eager only for `research`, `packages/tools/src/lonora_tools/artifacts.py:253`) | COVERED |
| 59 | Attach a file to a chat | `POST /api/artifacts/upload` `apps/api/src/lonora_api/routes/artifacts.py:29` | `apps/web/src/lib/api.ts:135` | `artifact_create` `packages/tools/src/lonora_tools/artifacts.py:242` ("attached to this thread") | the calling agent's current thread (`packages/tools/src/lonora_tools/artifacts.py:68`) | discovery-only | COVERED |
| 60 | Edit a text file | `PUT /api/artifacts/{id}/text` `apps/api/src/lonora_api/routes/artifacts.py:94` | `apps/web/src/shell/domain/api.ts:130` | none (`workspace_update` edits the agent's private workspace, not artifacts) | - | - | **NO-TOOL** |
| 61 | Delete a file | `DELETE /api/artifacts/{id}` `apps/api/src/lonora_api/routes/artifacts.py:19` (`apps/api/src/lonora_api/routes/__init__.py:69`) | `apps/web/src/shell/domain/api.ts:135` | none | - | - | **NO-TOOL** |
| 62 | See and edit an agent's scratchpad notes | resource routes `/api/scratchpad` `apps/api/src/lonora_api/routes/scratchpad.py:5` | `apps/web/src/pages/ScratchpadSection.tsx:18` | `scratchpad_read` `packages/tools/src/lonora_tools/scratchpad.py:42`, `scratchpad_write` `packages/tools/src/lonora_tools/scratchpad.py:48` (adds a note; no edit or delete) | the calling agent only (`packages/tools/src/lonora_tools/scratchpad.py:19`, `packages/tools/src/lonora_tools/scratchpad.py:33`) | discovery-only | **OWN-AGENT-ONLY** |

### 3.8 Attention, usage, activity

| # | Owner action | API route (handler) | Client call site | Agent tool or card | Ownership scope of the tool | PA exposure | Verdict |
|---|---|---|---|---|---|---|---|
| 63 | Read the alerts inbox and its history | `GET /api/attention` `apps/api/src/lonora_api/routes/attention.py:39`; `.../history` `apps/api/src/lonora_api/routes/attention.py:27` | `apps/web/src/providers/AttentionProvider.tsx:47`, `apps/web/src/shell/domain/UpdatesPages.tsx:148` | `owner_attention_list` `packages/tools/src/lonora_tools/incoming_call.py:121` | the calling agent and its thread only (`packages/tools/src/lonora_tools/incoming_call.py:108`) | discovery-only | **OWN-AGENT-ONLY** (read) |
| 64 | Alert filter: show opportunities, show informational items | `PUT /api/attention/policy` `apps/api/src/lonora_api/routes/attention.py:84`; fields `packages/contracts/src/lonora_contracts/attention.py:40` | `apps/web/src/shell/settings/NotifyPages.tsx:154` | none | - | - | **NO-TOOL** |
| 65 | Usage and cost dashboard, CSV export | `apps/api/src/lonora_api/routes/usage.py:27`, `apps/api/src/lonora_api/routes/usage.py:94`, `apps/api/src/lonora_api/routes/usage.py:110`, `apps/api/src/lonora_api/routes/usage.py:125` | `apps/web/src/shell/settings/UsagePage.tsx:510`, `apps/web/src/shell/settings/UsagePage.tsx:512` | none | - | - | **READ-ONLY-GAP** |
| 66 | Activity log (owner-visible actions of all agents) | `GET /api/activity` `apps/api/src/lonora_api/routes/activity.py:14` | `apps/web/src/shell/domain/api.ts:138` | none owner-wide. `agent_inspect` sections `runs`, `operations` give one supervised agent at a time | supervised agents | native | **READ-ONLY-GAP** (partial) |

### 3.9 Owner-only by nature (not gaps, not counted)

| Owner action | API route (handler) | Client call site | Why it stays with the owner |
|---|---|---|---|
| Log in, log out, session | `apps/api/src/lonora_api/routes/auth.py:26`, `apps/api/src/lonora_api/routes/auth.py:68` | `apps/web/src/lib/auth.ts:9`, `apps/web/src/lib/auth.ts:13` | authentication |
| Enroll a passkey device | `apps/api/src/lonora_api/routes/device_authority.py:40`, `apps/api/src/lonora_api/routes/device_authority.py:49` | `apps/web/src/components/permissions/AgentPermissions.tsx:872` | device authorization; the tool side only tells the model to ask (`packages/tools/src/lonora_tools/memory.py:189`) |
| Decide a card, passkey challenge, renew | `apps/api/src/lonora_api/routes/owner_actions.py:151`, `apps/api/src/lonora_api/routes/owner_actions.py:177`, `apps/api/src/lonora_api/routes/owner_actions.py:196` | `apps/web/src/components/owner-actions/OwnerActionCard.tsx:153` | "No tool can confirm a card" (`packages/tools/src/lonora_tools/owner_actions.py:5`) |
| Answer or decline an incoming call | `apps/api/src/lonora_api/routes/incoming_calls.py:59` | `apps/web/src/shell/call/CallPages.tsx:552` | the owner's own response; the agent side is `owner_call_request` (`packages/tools/src/lonora_tools/incoming_call.py:139`) |
| Start, interrupt, end a voice call | `apps/api/src/lonora_api/routes/voice.py:24`, `apps/api/src/lonora_api/routes/voice.py:33` | `apps/web/src/lib/voice.ts:196`, `apps/web/src/lib/voice.ts:13` | the owner's own call |
| Mark a chat read, mark all read, mark alerts seen | `apps/api/src/lonora_api/routes/threads.py:128`, `apps/api/src/lonora_api/routes/threads.py:42`, `apps/api/src/lonora_api/routes/attention.py:63`, `apps/api/src/lonora_api/routes/attention.py:71` | `apps/web/src/shell/lists/api.ts:16`, `apps/web/src/shell/lists/api.ts:17` | the owner's own read state; an agent marking it would hide things from him |
| First-time setup | `apps/api/src/lonora_api/routes/onboarding.py:17` | `apps/web/src/lib/bootstrap.ts:4` | bootstrap token |
| Open a chat with an agent | `apps/api/src/lonora_api/routes/agents.py:133` | `apps/web/src/hooks/usePersistentThread.ts:18` | navigation; the agent side is `peer_send` |

## 4. Numbered gap list

"Keep owner-only" marks actions that must not become a direct tool for security; a card with a server-side form is the most an agent should get.

**NO-TOOL (28)**

1. Row 3. Edit an agent (name, title, description, instructions, avatar, colour, focus market). No tool and no card. An owner sentence such as "rename the gold agent" or "change its instructions" has no route for the PA.
2. Row 5. Trading level Analysis / Ask me, and the permission draft. No tool, no card. Lowering to Analysis narrows authority and could be direct; raising to Ask me should be a card.
3. Row 8. Per-agent notification rules. No tool. "Stop agent X from calling me" or "at most five alerts a day from X" cannot be done; `owner_preferences_update` changes only the owner-wide channel.
4. Row 12. Light agent goals. No tool.
5. Row 13. Knowledge notes of an agent. No tool.
6. Row 14. Knowledge links of an agent. No tool.
7. Row 15. Semantic memory setting. No tool.
8. Row 19. Undo a memory or profile change. No tool, although the tool results advertise `"revertible": True` to the model (`packages/tools/src/lonora_tools/memory.py:256`) and the description says "the owner can revert".
9. Row 23. Owner name and form of address. Not in `owner_preferences_update`.
10. Row 27. Stop a run of another agent.
11. Row 28. Retry or resume a failed run.
12. Row 29. Pin, mute, archive, favourite, mark unread.
13. Row 30. Clear a chat's history.
14. Row 31. Chat lists.
15. Row 32. "Keep archived" setting.
16. Row 33. Per-chat web search switch (low value: the PA has `web_search` natively).
17. Row 35. Create a group chat.
18. Row 36. Edit a group.
19. Row 42. Block an exact skill version.
20. Row 48. Revoke or restore a trusted source. Revoking narrows and could be direct; restoring widens and should be a card.
21. Row 50. Remove a news feed. The agent can add a feed but cannot remove the one it added.
22. Row 51. Connect Telegram. **Keep owner-only for the token**: needs a `connect_credential` target, never chat.
23. Row 52. Disconnect Telegram.
24. Row 53. Model provider API key. **Keep owner-only**: a credential. Today there is not even a card for it, so the PA can only describe the settings page.
25. Row 55. Default model routing. Linked to conversation message [2] («النموذج غير متاح»): the production trace gives the cause as `model_not_configured` on a new installation, fixed only when the owner set the routing in the interface. No agent tool or card exists for this setting, and an agent with no model cannot run at all, so this one needs a first-run default on the server, not a tool.
26. Row 60. Edit a text file.
27. Row 61. Delete a file.
28. Row 64. Alert filter (opportunities, informational).

**OWN-AGENT-ONLY (6)**

29. Row 17. Edit another agent's memory. `memory_write` always writes the caller's document. The PA can read a supervised agent's memory but cannot correct it; it would have to ask that agent with `peer_send`.
30. Row 39. Create or edit a skill for another agent.
31. Row 40. Enable, disable or remove another agent's skill.
32. Row 41. Roll back another agent's skill.
33. Row 62. Another agent's scratchpad notes (also: no edit or delete even for its own).
34. Row 63. Alerts raised by other agents or in other threads (read).

**READ-ONLY-GAP (5)**

35. Row 18. Revision history of memory and of the owner profile ("who changed this and when").
36. Row 34. Owner-wide search across files, skills and tasks (partial: conversations and memory are covered).
37. Row 57. List files.
38. Row 65. Usage and cost. "How much did the models cost me this week" cannot be answered by any tool.
39. Row 66. Owner-wide activity log (partial: per-agent runs and operations through `agent_inspect`).

**CARD-ONLY by a safety or security rule (5; correct as built, not gaps)**

40. Row 44. Add an MCP server: secrets rule (`packages/agent-runtime/resources/system/lonora.md:561`). Limit of the card: the agent cannot pre-fill the address; UNSURE which fields the form shows (client form code not read in full).
41. Row 46. Trust an MCP server's tools: trust rule; "tools that trade or move money never run" (`packages/tools/src/lonora_tools/mcp.py:437`).
42. Row 47. Add a trusted source: trust rule.
43. Row 56. Allow a model: the owner decides which models may be used. Removal from the list has no path.
44. Brave Search and economic calendar keys (no settings row): secrets rule.

**TOOL-BUT-NOT-EXPOSED-TO-PERSONAL-ASSISTANT**

No tool in scope is unavailable to the PA: every registered tool is callable through `tool_call`. The exposure problem is the weaker one. Of the 27 rows that have a tool or a card, 19 depend on a tool that is discovery-only for the PA:

- rows 2, 4, 6, 7, 10, 11: `agent_create`, `agent_control`, `model_list`, `model_request`, `supervision_change`;
- row 22: `owner_preferences_update`; row 26: `message_react`; row 37: `collaboration_inspect`;
- rows 43, 45, 49: `capabilities_list`, `mcp_connections`, `mcp_tools`, `news_feed_subscribe`;
- rows 44, 46, 47: `owner_action_propose`; row 56: `model_request`; row 54: `model_list`;
- rows 58, 59: `artifact_read`, `artifact_create`.

Every card in section 2 is raised by a discovery-only tool. Only rows 1, 9, 16, 20, 21, 24, 25, 38 work with native tools alone. Section 7 shows what discovery returns for these.

## 5. Totals

- Routes enumerated: 276 (all areas). Tools in the registry: 126. Native for the PA: 23.
- Owner actions in scope with a client call site: **66 rows** (section 3.1 to 3.8), plus 8 owner-only-by-nature actions (3.9) that are not counted.

Exact count by verdict (each row has one verdict):

| Verdict | Rows | Count |
|---|---|---|
| COVERED | 1, 4, 6, 9, 11, 16, 20, 21, 22, 24, 25, 26, 37, 38, 43, 45, 54, 58, 59 | 19 |
| COVERED+CARD | 2, 7, 10, 49 | 4 |
| CARD-ONLY | 44, 46, 47, 56 | 4 |
| NO-TOOL | 3, 5, 8, 12, 13, 14, 15, 19, 23, 27, 28, 29, 30, 31, 32, 33, 35, 36, 42, 48, 50, 51, 52, 53, 55, 60, 61, 64 | 28 |
| OWN-AGENT-ONLY | 17, 39, 40, 41, 62, 63 | 6 |
| READ-ONLY-GAP | 18, 34, 57, 65, 66 | 5 |
| **Total** | | **66** |

So 27 of 66 owner actions (41%) have a tool or a card; 39 (59%) are gaps: 28 NO-TOOL, 6 OWN-AGENT-ONLY, 5 READ-ONLY-GAP. Of the 27 that are covered, 19 need at least one discovery-only tool (rows 2, 4, 6, 7, 10, 11, 22, 26, 37, 43, 44, 45, 46, 47, 49, 54, 56, 58, 59) and 8 work with native tools alone (rows 1, 9, 16, 20, 21, 24, 25, 38). Two gap rows must stay owner-only for the secret itself (51 Telegram token, 53 provider key); they need a card form, not a tool.

## 6. Routes in scope with no client call site (API only; not owner actions today)

Found by grep of the client directories in section 0; a negative grep result, so UNSURE for clients outside those directories (for example an older cached web build).

| Route | Handler | Note |
|---|---|---|
| `DELETE /api/agents/{id}` | `apps/api/src/lonora_api/routes/agents.py:165` | The only interface path to delete an agent is the Undo on the `agent_created` card (`apps/api/src/lonora_api/routes/owner_actions.py:413`, `apps/api/src/lonora_api/routes/owner_actions.py:809`). No agent tool either. So neither the owner (after the Undo card expires, 7 days: `packages/db/src/lonora_db/owner_actions.py:73`) nor the PA can delete an agent from the product |
| `POST /api/agents` (non-template create) | `apps/api/src/lonora_api/routes/agents.py:59` | clients use `/agents/create` |
| `DELETE /api/threads/{id}` | `apps/api/src/lonora_api/routes/threads.py:98` | clients offer Clear, not Delete |
| `DELETE /api/groups/{id}` | `apps/api/src/lonora_api/routes/groups.py:14` | |
| `GET/POST /api/agents/{id}/secrets`, `DELETE /api/secrets/{id}` | `apps/api/src/lonora_api/routes/agent_secrets.py:12`, `apps/api/src/lonora_api/routes/agent_secrets.py:21`, `apps/api/src/lonora_api/routes/agent_secrets.py:38` | credentials: keep owner-only |
| `GET /api/auth/devices`, `DELETE /api/auth/devices/{id}` | `apps/api/src/lonora_api/routes/device_authority.py:31`, `apps/api/src/lonora_api/routes/device_authority.py:60` | the owner cannot list or revoke an enrolled device from the interface; device authorization: keep owner-only |
| `PUT /api/voice/incoming/policy` | `apps/api/src/lonora_api/routes/incoming_calls.py:30` | clients save reach-me through `/owner/preferences` (row 22) |
| `PUT /api/settings/models/backups`, `GET/PUT /api/settings/models/context` | `apps/api/src/lonora_api/routes/model_router.py:28`, `apps/api/src/lonora_api/routes/model_router.py:37`, `apps/api/src/lonora_api/routes/model_router.py:47` | model fallbacks and context policy have no screen and no tool |
| `DELETE /api/agents/{id}/knowledge/notes/{note_id}` | `apps/api/src/lonora_api/routes/knowledge.py:68` | |
| `PUT/DELETE /api/mcp/{id}` | `apps/api/src/lonora_api/routes/mcp.py:37` | no client call to remove or disable an MCP server was found; no tool |
| `GET /api/attention/audit` | `apps/api/src/lonora_api/routes/attention.py:15` | |
| `GET /api/collaboration/{session_id}` | `apps/api/src/lonora_api/routes/collaboration.py:23` | |
| `POST /api/runs/{id}/steer` | `apps/api/src/lonora_api/routes/steering.py:15` | |
| `POST /api/webhook` | `apps/api/src/lonora_api/routes/webhook.py:16` | inbound machine route, signed; not an owner action. The `webhook` integration type has no client screen |
| `GET /api/mobile/updates` | `apps/api/src/lonora_api/routes/mobile_updates.py:54` | app update channel, called by the native update client |

Backups: `scripts/backup.sh` and `scripts/restore.sh` are host scripts with a systemd timer (`infra/systemd/lonora-backup.timer`). There is no API route, no screen and no tool for them; nothing to compare.

## 7. Discovery reproduction (current main; another session is fixing tool discovery)

Run: `scripts/parity_discovery.py`, output `runs/parity_discovery.txt`. The queries are SCRIPTED by the auditor; the lists are what `search_definitions` returned on the live registry (`packages/tools/src/lonora_tools/tool_discovery.py:44`). The gate is the rarest query word even when it appears in no tool (`packages/tools/src/lonora_tools/tool_discovery.py:62`).

| SCRIPTED query | Returned | Correct tool |
|---|---|---|
| `غيّر النموذج` | `[]` | `model_request` |
| `change model` | `model_request`, `consult_model`, `model_list`, ... | found |
| `لغة الرد` / `ساعات الهدوء` | `[]` / `[]` | `owner_preferences_update` |
| `reply language` / `quiet hours` | `owner_preferences_update`, ... | found |
| `ثبّت مهارة` | `[]` | `skill_package_import` |
| `install skill` | `['skill_view']` | `skill_package_import` not returned |
| `add mcp server` | `chart_add_indicator`, `memory_write`, `chart_annotate`, `trade_restriction_create` | `owner_action_propose` not returned |
| `trust source` | `mcp_tools`, `skill_package_import`, `mcp_execute`, `owner_action_propose` | found (4th) |
| `subscribe feed` | `['news_feed_subscribe']` | found |
| `pause agent` | `agent_control`, ... | found |
| `أوقف الوكيل مؤقتا` | `[]` | `agent_control` |
| `supervise agent` | ..., `supervision_change`, ... | found (4th) |
| `rename agent`, `edit agent instructions`, `احذف الوكيل`, `mute chat`, `pin chat`, `archive chat`, `add agent to group`, `edit file`, `connect telegram`, `usage cost`, `notification settings` | `[]` each | none exists (gap rows 3, 29, 35, 36, 60, 51, 65, 8) |
| `delete agent`, `delete chat`, `delete file` | `workspace_update`, `chart_annotate` | none exists; the two returned tools are unrelated |
| `create group` | `['group_silence']` | none exists; the returned tool is unrelated |

Reading: all 9 Arabic queries returned an empty list (the catalog is English only). For a real gap an empty list is true, but the model cannot tell "no such tool" from "the search missed it", and for `delete ...` it is handed unrelated tools. This matches the production trace: the one `tool_environment` call of the conversation returned an empty list.

## 8. What this means for the conversation and the binding principles

- Principle 10 (owner scope) fails on main for memory, skills, scratchpad and alerts of other agents (gap entries 29 to 34): the tools filter on `context.agent_id` (`packages/tools/src/lonora_tools/memory.py:115`, `packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:65`, `packages/tools/src/lonora_tools/scratchpad.py:19`, `packages/tools/src/lonora_tools/incoming_call.py:108`). The supervision tools show the pattern that already works owner-wide: grant-based reach with the owner-message exception for the PA (`packages/db/src/lonora_db/supervision.py:661`).
- Brief section 1 ("can do everything the owner can from the interface ... or asks permission with a card") fails for 39 of 66 non-trading actions. For 28 of them the PA has neither a tool nor a card, so the only truthful reply is to send the owner to a settings screen.
- Messages [50]/[51] (reply in Turkish): the tool that sets the reply language exists (`owner_preferences_update`, row 22) but is discovery-only and needs the owner's typed message; a voice note is not a typed message. TRACE MUST CONFIRM: whether any run of the conversation called `owner_preferences_update` (the lead's summary says `reply_language` is empty in production, which suggests none did).
- Message [2] («النموذج غير متاح»): gap entry 25.

## 9. UNSURE and TRACE MUST CONFIRM

- UNSURE: the exact fields of the `connect_credential` card form per target (only the submit call was read, `apps/web/src/components/owner-actions/OwnerActionCard.tsx:177`).
- UNSURE: whether `apps/web/src/pages/*` components cited as call sites are all still mounted. `Knowledge` is (`apps/web/src/shell/pages.tsx:12`); `AllowedModelsSettings.tsx` and `ModelSettingsOverlay.tsx` were not traced to a route.
- UNSURE: section 6 is a negative grep; a client outside the searched directories could call those routes.
- TRACE MUST CONFIRM: which discovery-only tools, if any, were promoted for the production Personal Agent (table of remembered tools, read at `packages/agent-runtime/src/lonora_agent/tool_exposure.py:95`). The trace's 23 native tools equal the unpromoted set, which suggests none.
- TRACE MUST CONFIRM: that the owner set the model routing through `PUT /api/settings/models` at 2026-11-11 09:37:25 UTC (stated in the lead's summary of the production database, not visible in code).
- Not examined: mobile-only screens were used only as secondary call sites; where web and mobile differ in which actions they offer, the table follows web.
