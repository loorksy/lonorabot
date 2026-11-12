# Phase 6 map: Lonora as lead, the flat team, the owner model

Scope: mandate sections 3 and 8, P5, 12.3, 10.3.2 (supervision kinds, `trust_source`, `agent_model`), 14.2.6, 14.3.5, 14.3.6, 14.3.15, 14.3.16, 14.3.18.4, 14.3.18.6.

## 0. Baseline and how to read this map

- Code line numbers are as of commit `a776adf` (main). Commit `5112c25` landed while this map was written: it only prepends `Superseded by VISION.md` plus a blank line to 98 documents (doc line numbers +2), no code change (`git diff a776adf 5112c25 -- packages apps tests` touches only `apps/mobile/README.md`).
- Phases 2 to 5 are NOT in this checkout: `LONORA_GENUI_V2` is still read (`packages/agent-runtime/src/lonora_agent/skills/visual_policy.py`), grants, restrictions and goals exist (`packages/db/src/lonora_db/account_authority.py`, `packages/trading/src/lonora_trading/restrictions.py`, `goals.py`), there is no `lonora` CLI, no `ticket_not_owned`, and `TradingControl.enabled` still exists (`packages/contracts/src/lonora_contracts/trading.py:10`). Everything below describes today's code; section 12 names what phases 3, 4 and 5 must have delivered first.
- Path prefixes: `db/` = `packages/db/src/lonora_db/`, `tools/` = `packages/tools/src/lonora_tools/`, `rt/` = `packages/agent-runtime/src/lonora_agent/`, `res/` = `packages/agent-runtime/resources/`, `mem/` = `packages/memory/src/lonora_memory/`, `ct/` = `packages/contracts/src/lonora_contracts/`, `trd/` = `packages/trading/src/lonora_trading/`, `gw/` = `packages/gateway/src/lonora_gateway/`, `api/` = `apps/api/src/lonora_api/`, `web/` = `apps/web/src/`, `mob/` = `apps/mobile/`, `tsc/` = `packages/contracts/src/` (TypeScript), `tsk/` = `packages/core/src/` (TypeScript).

## 1. Agents today

### 1.1 The row, roles, templates, parents
- `AgentRow` (`db/schema.py:160-217`): `role` in `personal|general|specialist|delegated|legacy` (CHECK `:168`), `template` in `trading|general|research|supervisor` or NULL (`:172`), `scope_mode` `fixed_market|flexible` (`:170`), `parent_id` self-FK `SET NULL` (`:207`), `trading_account_id` / `trading_symbol` (`:208-209`), `instructions` (`:215`), `paused` (`:216`). Four more CHECKs tie role to scope (`:175-190`); one personal agent per owner (unique partial index `:191-197`).
- Lonora = role `personal`, name "Lonora", deterministic id, template NULL (`db/personal_agent.py:16-43`); created at API start (`api/app.py:89-94`), on every authenticated request (`api/middleware/auth.py:25`) and at owner setup (`packages/auth/src/lonora_auth/owner_policy.py:25`). It cannot be deleted (`db/agent_creation.py:356-357`), cannot change scope (`db/agents.py:117`) and is listed first (`db/agents.py:102`).
- Role is derived at creation (`db/agents.py:43-49`): `specialist` with a pair, `general` when flexible without one, else `legacy`. With a parent: `delegated` (parent delegated or unbound, `:52-57`) or `specialist` inheriting the parent's pair as `fixed_market` (`:58-70`). Template defaults from the pair (`:71-75`).
- Child agents: tool `child_agent_create` ("Compatibility only", `tools/subagent.py:66-72`) → `rt/collaboration/child_agents.py:11-23` → `create_agent(..., parent_id)`.
- Templates: `AgentTemplate` and `TEMPLATE_LEVEL` (trading → `supervised` "Ask me"; general, research, supervisor → `analysis` "No trading") in `ct/agent_creation.py:16-23`; applied by `initial_permission` (`db/agent_creation.py:245`); template notes written to OPERATING.md, three of them saying "do not trade" (`rt/collaboration/agent_create.py:41-49,132-134`). The supervisor template is hidden from both forms (`web/pages/shell/bot-panel.tsx:17`, `mob/app/new.tsx:21`) but accepted by the tool and the API.
- `report_to` (peer link, max 5) and `supervises` (max 10) are creation inputs (`ct/agent_creation.py:64-73`), checked in `check_creation` (`db/agent_creation.py:175-183`), stored in the origin record `agent-origin:<hash>` in `ln_settings` (`db/agent_creation.py:57-58,253-269`), turned into OPERATING.md lines on both agents (`rt/collaboration/agent_create.py:135-162`) and into supervision grants (`db/agent_creation.py:271-283`). `report_targets` (`db/agent_creation.py:468-471`) feeds the directory.
- Directory: `agent_directory` (`db/agent_directory.py:12-43`) returns role, scope, pair, template, `reports_to`, `you_supervise`, `supervises_you`; injected every turn by `team_context` (`rt/context/team.py:25-56`, budget 12,000 chars `:17,32-33`) and returned by `list_agents` (`tools/agents.py:64-69`).

### 1.2 Account and symbol binding (`db/agent_binding.py`) and every caller
- Definitions: `BINDING_POLICY` (`:12-23`), `flexible_scope` (`:26-32`), `fixed_market` (`:35-36`), `account_wide_scope` (`:39-40`), `scope_data` (`:43-58`), `assert_market_binding` (`:67-84`), `assert_payload_binding` (`:87-98`), `agent_binding` (`:101-105`), `require_financial_agent` with the delegated/child refusal and the ancestry walk (`:108-130`), `binding_context` prompt frames (`:133-190`).
- Execution door (phase 3 removes these, 6.9): `trd/execution.py:80,88-92,110-114` inside `require_goal_lineage` (`:71`).
- Financial tool paths: `tools/trade.py:375,423`; `tools/market_binding.py:213-217` (`guard_market_tool`); `tools/owner_actions.py:66`; `db/owner_actions.py:254-268,433`; `db/account_authority.py:89-99`; `db/agent_permissions.py:246-261`; `db/trading_goals.py:92-94,198`; `db/goal_scope.py:16`; `api/routes/account_authority.py:84`.
- Non-financial paths (left for phase 6): tool-argument alignment and fill `tools/market_binding.py:54-90,195-199` (`align_payload`, `fill_bound_fields`), mutation guard `:218-245`, result annotation `:259-275`; resource repository for charts/watches `db/transactions.py:131-144,187-194`; watcher evaluation `packages/market/src/lonora_market/watchers.py:213-215`; decisions `tools/trading_decision.py:65-66`; relationships `tools/relationships.py:34-41`; opportunities `db/trading_opportunities.py:95-96`; task wait on broker recovery `db/task_wait.py:44-51`; performance route `api/routes/performance.py:27`; creation of children `db/agents.py:61-63`.
- Plain `agent_binding` lookups (row fetch only): `rt/tool_exposure.py:94`, `rt/context/permissions.py:214`, `tools/agents.py:234`, `tools/trade.py:66,751,775,822,833`, `tools/restrictions.py:132,245`, `tools/opportunity.py:48,105,129`, `tools/owner_actions.py:49,198`, `tools/trading_decision.py:229`, `tools/supervision.py:515`, `tools/performance.py:15`, `tools/market_binding.py:182,212,266`.
- Prompt frames: `binding_context` in `rt/context/builder.py:110` and `packages/voice/src/lonora_voice/context.py:197`.
- Other readers of the columns: `default_account` (`tools/market_binding.py:92-112`), `default_level` (`db/agent_permissions.py:34-45`), `run_profiles` (`rt/tool_exposure.py:43`), `money_standing` (`db/supervision.py:536-537`), `discover_specialists` (`db/personal_agent.py:46-65`, no caller), status line `db/agent_state.py:370,388`, `db/trading_readiness.py:136,186,265`, restrictions `db/trading_restrictions.py:75`, `tools/restrictions.py:138`; clients `web/shell/agent/shared.tsx:39-45`, `web/shell/ChatHeader.tsx:71`, `web/shell/ChatMenu.tsx:88`, `web/shell/domain/hooks.ts:19`, `web/conversation/Composer.tsx:407`, `web/conversation/PermissionMenu.tsx:86`, `web/conversation/sheets/MandateSheet.tsx:86-98`, `web/pages/shell/bot-settings.tsx:24,145`, `mob/app/bot-settings.tsx:77,153-154,166`, `tsk/agent-scope.ts:10`, `tsk/agent-permission.ts:173`.

### 1.3 Caps on agents
- `MAXIMUM_ACTIVE_AGENTS = 20` (`db/agent_creation.py:50`), counted by `active_agents` (not paused, not delegated, `:93-104`), enforced in `check_creation` (`:173-174`, skipped for the owner's form `:223`) and again in the tool (`tools/agents.py:218-223,314,331`); stale reason for creation cards `db/owner_actions.py:589-590`; client text `tsk/owner-actions.ts:749`; error class `rt/environment.py:201`; docs `docs/agents-from-chat.md:82`.
- `MAXIMUM_CREATIONS_PER_RUN = 3` (`db/agent_creation.py:51`, `run_creations` `:107-127`, `tools/agents.py:220-221`): the only rate guard; it counts per run, not per minute.
- Other numeric limits near agents (none caps the total): supervised per change 10 (`db/supervision.py:68`), `report_to` 5 / `supervises` 10 (`ct/agent_creation.py:66,71`), group members 12 (`ct/groups.py:8`), direct-chat guests 2 (`db/messages.py:48,350`), collaboration participants 16 and rounds 8 (`db/collaboration.py:121,130`), live subagents per run 4 (`tools/context.py:32`, `rt/collaboration/subagents.py:46-47`), pending cards per agent 5 (`db/owner_actions.py:92`), peer depth 3 (`packages/security/src/lonora_security/collaboration.py:4-10`).

### 1.4 Capability limits by template, role or scope
- Starting ladder by template (`ct/agent_creation.py:18-23`) and by role (`db/agent_permissions.py:34-45`); a delegated agent can never leave `analysis` (`db/agent_permissions.py:211`).
- `require_financial_agent` refuses delegated agents and unbound children (`db/agent_binding.py:122-125`); `scope_data` reports `execution_authority="none"` for delegated (`:57`).
- Fixed-market agents: charts, watches, decisions, relationships, opportunities and trades stay on the pair (callers in 1.2).
- Tool exposure (`rt/tool_exposure.py:31-49`): `market` profile only for bound agents and Lonora, `research` for the rest; `coordination` (`agent_inspect`, `peer_send`) only for Lonora or a grant holder (`:45,96`). Exposure is eager schemas only; every tool stays callable through `tool_call` (`:1-10`). `ToolScope` (`tools/base.py:49-58,95-100`) narrows by run kind (subagent helper, observe-only wake), not by agent: it stays (6.9).
- Creation refusals by role: delegated cannot create agents (`tools/agents.py:235-236`), set supervision (`tools/supervision.py:516-517`) or be a supervisor (`db/supervision.py:172-174`) or a report target (`db/agent_creation.py:177-178`).
- UI: `hasDelegation` hides trading level for the research template (`web/shell/agent/shared.tsx:44-45`); `AgentPermissions` disables levels for delegated (`web/components/permissions/AgentPermissions.tsx:516`).

### 1.5 Creation paths
- Tool `agent_create` (`tools/agents.py:226-356`, definition `:370-383`): with the owner's typed message (`owner_message_id`, `:286`) it creates directly (`:327-356`), one per message/template/name (`creation_receipt` `:158-163`), then raises an `agent_created` Undo card (`:347-354`). Without it, or when the new agent would supervise Lonora (`:287-291`), it raises a `create_agent` card (`:292-326`). Model must be in the owner's configured list (`:273-280`).
- Service: `create_from_spec` (`rt/collaboration/agent_create.py:105-162`) → `create_root_agent` (`db/agent_creation.py:192-295`) → `create_agent` (`db/agents.py:36-92`); always `scope_mode="flexible"` (`db/agent_creation.py:232`). `check_responsibility` refuses authority claims (`rt/collaboration/agent_create.py:52-55`).
- Routes: `POST /api/agents` (form, `api/routes/agents.py:59-76`), `POST /api/agents/create` (template, `:79-120`), `PATCH /api/agents/{id}` (`:141-162`), `DELETE` (`:165-174`).
- Cards: `create_agent` confirm (`api/routes/owner_actions.py:410-412,720-734`), `agent_created` Undo (`:413-419,791-812`), first-task wake for the proposer (`db/agent_creation.py:392-453`, `api/routes/owner_actions.py:507`).
- Clients: `web/pages/shell/bot-panel.tsx` (`/app/new-agent`), `mob/app/new.tsx`, card rendering `web/components/owner-actions/OwnerActionCard.tsx:473-493`, `mob/components/owner-action-card.tsx`.

### 1.6 Deletion today
- Only the owner deletes: route (`api/routes/agents.py:165-174`) and Undo card. No agent tool deletes, cancels another agent's run (`cancel_run` is owner-route only, `api/routes/cancellation.py:21`) or edits another agent's instructions or memory.
- `delete_created_agent` (`rt/collaboration/agent_create.py:233-241`) removes report links and notes (`forget_links` `:181-230`), then `delete_agent` (`db/agent_creation.py:341-376`): `authority_lock` → row lock → `prepare_delete` → supersede its Undo card → delete skill controls and origin → `owner_holds_for` → `session.delete`.
- `prepare_delete` (`db/obligations.py:98-158`): refuses with `delete_blocked_unresolved_operation` while a journal row attributed to the agent is in progress or unresolved (`:112-115`; attribution by `details.execution.agent_id` or run id `:57-64`, written at reservation `trd/execution.py:253-266`); supersedes pending owner cards (`settle_for_delete`, `db/owner_actions.py:2167-2214`); sets pending and approved Trade Approval rows to `cancelled` (`db/obligations.py:120-124`); revokes grants (`:127-142`); settles goals (`:146-158`).
- Undo plan: delete only an agent with no runs, watches, routines, tickets, grants, approvals or children, else pause (`db/agent_creation.py:323-338`).
- What survives: journal rows (no agent FK, thread `SET NULL`, `db/schema.py:676-694`), Trade Approval rows (`:862-887`, migration `0036_durable_records.py`), owner-action rows including settlement cards (`:965-1021`), events (plain ids, `:434-436`), grants, goals, restrictions.
- What cascades away: threads and their messages (`db/schema.py:234,254-256`), runs (`:386`), memory and its revisions (`:460,509`), routines (`:535`), attention (`:568`), workspace (`:631,649`), every `ResourceRow` table (`:668`: watches, tickets/Tasks, scratchpad, artifacts, opportunities, peer messages, collaboration sessions, `ln_financial_receipts`), supervision grants (`:1059-1060`) and holds on it (`:1114`).
- Positions and pending orders: nothing happens at the broker and nothing is reassigned. Later broker activity on a ticket whose journal agent no longer exists wakes Lonora observe-only (`trd/broker_recovery.py:172,179-186`), which the door refuses to trade from (`trd/execution.py:81-85`).

## 2. Supervision today

### 2.1 `db/supervision.py`
- Grants (`ln_supervision_grants`, `db/schema.py:1023-1069`; migration `0041_supervision_grants.py`): `supervised_ids` (`:84-91`), `supervisor_ids` (`:94-100`), `supervises` (`:103-115`), `supervises_all` (`:118-125`), `require_supervision` (`:128-137`), `grant_supervision` (`:156-196`), `owned_grant` (`:199-207`), `revoke_supervision` (`:210-221`), `agent_names` (`:254-265`), `grant_data` (`:268-283`), `supervision_view` (`:286-315`), events `supervision.granted/revoked` (`:150-153`).
- Lonora's default power is a grant, not a role: `personal_agent_id` (`:224-227`), `grant_default` (`:230-235`, called from `db/agents.py:88-91`), `seed_personal_grants` (`:238-251`, called from `db/personal_agent.py:37-40`). The owner can revoke it in one tap.
- Holds (`ln_supervision_holds`, `SupervisionHoldRow` `db/schema.py:1072-1124`; migration `0043_owner_held_pauses.py`): `live_hold` (`:321-331`), `work_paused` (`:334-352`), `release_hold` (`:355-358`), `owner_takes_over` (`:361-399`), `owner_holds_for` (`:402-418`), `refuse_held` (`:421-446`), `holds_over` (`:449-486`, reads `TradingRestrictionRow`), `check_cycle` (`:489-503`), `record_intervention` (`:506-525`), `money_standing` (`:531-551`, reads the permission ladder), `control_work` (`:629-749`), `owner_resumes` (`:752-792`). Sources: `agent`, `owner_message`, `owner` (`:66`).
- `control_work` rules: needs a grant, or Lonora with the owner's message (`:658-663`); never pauses Lonora (`:686-688`); never pauses a whole agent with money standing without the owner's message (`:689-692`); cycle rule (`:693`); raises a `supervision_paused` card (`:708-710`); resume only by the holder, or with the owner's message, never an owner hold (`:714-722`); taint propagation on resume (`:728-735`).

### 2.2 Callers of each function (non-test)
| Function | Callers |
|---|---|
| `owner_takes_over` | `db/agents.py:136-143` (owner's pause switch), `db/agent_creation.py:381-385` (`pause_agent`, Undo), `db/tasks.py:409-422,584-589`, `db/market_watches.py:172-180`, `packages/automation/src/lonora_automation/service.py:45-56` |
| `refuse_held` | `db/tasks.py:426`, `db/market_watches.py:182-184`, `tools/routine.py:108-115` |
| `owner_resumes` | `api/routes/owner_actions.py:428-429` (the `supervision_paused` card) |
| `work_paused` | `db/owner_actions.py:560-565` (`_live_pause`); string match `work_paused*` in `rt/environment.py:140` |
| `live_hold`, `release_hold` | only inside `db/supervision.py` |
| `owner_holds_for` | `db/agent_creation.py:372-375` (delete) |
| `SupervisionHoldRow` | `tools/supervision.py:118-121,213-216`, `db/owner_actions.py:556-565,966,990,1651-1675` |
| `personal_agent_id` | `tools/agents.py:287`, `tools/supervision.py:574` |
| `grant_default` / `seed_personal_grants` | `db/agents.py:88-91` / `db/personal_agent.py:37-40` |
| `supervised_ids` | `rt/tool_exposure.py:96`, `tools/agents.py:192`, `tools/supervision.py:419`, `db/agent_directory.py:22`, `db/owner_actions.py:896-900`, `mem/sessions.py:139` |
| `supervisor_ids` | `tools/supervision.py:124`, `db/agent_directory.py:23` |
| `supervises` | `rt/collaboration/subagents.py:100`, `tools/routine.py:124`, `tools/restrictions.py:39`, `db/owner_actions.py:287-297,545-553` |
| `supervises_all`, `check_cycle`, `record_intervention` | `tools/restrictions.py:166,171,203` (deleted with restrictions in phase 3) |
| `require_supervision` | `tools/supervision.py:444` |
| `grant_supervision` | `tools/supervision.py:597`, `db/agent_creation.py:275`, `api/routes/owner_actions.py:747,768`, `api/routes/supervision.py:40` |
| `revoke_supervision` | `tools/supervision.py:549`, `api/routes/owner_actions.py:786`, `api/routes/supervision.py:54` |
| `control_work` | `tools/supervision.py:477`, `tools/routine.py:132` (`supervised_toggle` `:122-143`) |

### 2.3 Tools, routes, contracts, cards, screens
- Tools (`tools/supervision.py:631-669`): `agent_inspect` (`:436-456`; sections overview, work, runs, decisions, operations, memory `:400-407`; reads `TradingGoalRow` `:200-210` and `effective_permission` `:146`), `agent_control` (`:459-490`; pause, resume, message via `delegate_peer`), `supervision_change` (`:509-628`). `named_agent` resolves names only within reach (`:410-433`). Results are labelled `supervised_read` and untrusted (`:96-101`). `agent_inspect` is in the external-content tool list (`rt/context/run_evidence.py:66-69`), so calling it voids `owner_message_id` for the rest of the run (`tools/registry.py:555-559`).
- Other grant-based reads: `session_search` and `search_internal` through `HistoryScope.supervised` (`mem/sessions.py:107-130,134-175`; `tools/session_search.py:34`, `tools/search.py:62`), `subagent_inspect` (`rt/collaboration/subagents.py:92-110`).
- Route `api/routes/supervision.py:27-58` (GET view, POST grant, POST revoke); registered in `api/app.py:73`.
- Contracts: `ct/supervision.py:15-65`; TypeScript `tsc/supervision.ts`, helpers `tsk/supervision.ts`; card kinds `tsc/owner-actions.ts:18-21`; activity kinds `tsc/domain.ts:177-178`, `db/activity.py:28-29`.
- Cards: `supervise`, `supervision_created`, `supervision_stopped`, `supervision_paused` (lifetimes `db/owner_actions.py:76-80`; stale checks `:286-318`; facts `:923-1006`; raise functions `:1445-1475,1575-1675`; decisions `api/routes/owner_actions.py:420-429,470-480,740-788`; waiting-card list `db/agent_state.py:69-70`).
- Web: `web/components/ai/SupervisionSettings.tsx` (mounted in `web/pages/shell/bot-settings.tsx:97`), `SupervisionSection` and picker in `web/shell/agent/AgentPage.tsx:125-141,245-255,419-427,452-590`, creation toggle `web/pages/shell/bot-panel.tsx:34-35,101-113,140,239-262`, cards `web/components/owner-actions/OwnerActionCard.tsx:476,490-493`, activity labels `web/shell/domain/UpdatesPages.tsx:50-53`, errors `web/lib/user_error.ts:9,25-26`.
- Mobile: `mob/components/supervision-settings.tsx` (mounted in `mob/app/bot-settings.tsx:177`), errors `mob/lib/session.tsx:7,172-173`.
- Prompt: `res/system/lonora.md:506-514`; tool descriptions above; manifest chapter `collaboration` for all these tools (`res/system/manifest.json` `tool_policies`).

## 3. Peer messaging and collaboration
- `peer_send` (`tools/message.py:26-29,62-68`) → `delegate_peer` (`rt/collaboration/peer_messages.py:17-142`): cycle and depth checks (`:29-43`), writes the request as an `assistant`-role `MessageRow` authored by the sender in both conversations (`:71-93`), creates a `peer` run of the target in the target's own conversation with `parent_run_id` (`:94-111`), records `PeerMessageRow` (`:112-132`). Any agent may message any agent; no grant is needed.
- How it reaches the model: `history_context` renders any message by another agent as a **user-role** turn prefixed `[Peer <name>]` with no data marker (`rt/context/history.py:187,199-208`); the peer run gets no wake line (`rt/context/routine.py:19-20`) and no explicit prompt (`rt/context/builder.py:181-185`). The only statement that peer text is evidence is prose: `res/system/lonora.md:153`, `res/constitution/collaboration-policy.md:1`. A peer run has full tool scope including financial tools (`tools/base.py:53-58`).
- Outcome return: `rt/collaboration/outcome_return.py:29` onward posts the result back to the requester's thread.
- Provenance: a run whose thread holds another agent's message after the owner's message loses `owner_message_id` (`tools/restrictions.py:77-94,97-116`); peer runs never have one (trigger `peer` is not in `OWNER_TRIGGERS`, `:56`).
- Collaboration sessions: `collaboration_start/inspect/finish` (`tools/collaboration.py:118-138`), `invite` (`db/collaboration.py`), host-only inspect and finish (`tools/collaboration.py:58,92`).
- Owner addressing: one persistent conversation per agent (`conversation_thread`, `db/threads.py:66`; `POST /api/agents/{id}/conversation`, `api/routes/agents.py:133-138`). `@mention` in a direct chat invites up to 2 guests through a collaboration session (`db/messages.py:339-351`); in a group, explicit mentions, then `@name` text (`packages/core/src/lonora_core/group_mentions.py:4-9`), then the replied-to author, then the group lead (`db/messages.py:491-508`). Composer helpers `tsk/composer-mentions.ts:62-79`. A paused agent gets no run (`db/messages.py:514-515`, `db/runs.py:156-157`) and cannot be answered (`db/messages.py:302-303`).
- Subagents (`subagent_spawn`, `rt/collaboration/subagents.py:18-69`) are temporary runs of the same agent, not agents; 6.9 keeps their door refusal.

## 4. Memory privacy
- Per agent: `ln_memory` one row per agent (`db/schema.py:457-464`) holding MEMORY.md and OPERATING.md views (`mem/profile.py:17-63`); revisions `ln_memory_revisions` (`:490-520`); semantic notes per agent (`mem/semantic.py:79-135`); scratchpad, tickets, opportunities by `agent_id` (`db/schema.py:661-673`).
- Readers: the agent itself (`memory_read`, `tools/memory.py:71-91`; context `rt/context/memory.py:154-186`), the owner (`GET/PUT /api/agents/{id}/memory`, `api/routes/memory.py:61-94`), and any agent holding a grant (`agent_inspect` memory section `tools/supervision.py:379-397`, history `mem/sessions.py:123-130`). Without a grant another agent's threads and memory read as not found (`mem/sessions.py:178-183`, `rt/collaboration/subagents.py:109-110`).
- Writers: only the agent and the owner; a supervisor never edits (`tools/supervision.py:10-13`).
- Shared: the owner profile `ln_owner_profile` (`db/schema.py:467-487`) is read by every agent on every turn (`rt/context/memory.py:119-152`).
- Workspace versus store: memory is database rows, not files. The analytical workspace is per agent today (`ln_analytical_workspaces` keyed by agent, `db/schema.py:627-637`), so 3.2.4's "workspace files, which all agents share" only becomes true in phase 4. Skills created in the workspace are a separate store (`docs/workspace-created-skills.md`).

## 5. The owner model today
- Storage: USER.md is the one profile text (8,000 chars, `db/owner_profile.py:35`), versioned, each change attributed to owner or agent with the source message and revertible (`commit_owner_profile` `:90-160`); structured preferences are reply language, name, address and the reach-me record `IncomingCallPolicy` (channel, device, quiet hours to the minute, time zone; `ct/incoming_calls.py:17,41-56`; `db/owner_profile.py:163-182`).
- Gates in `tools/memory.py`: USER.md operations need `owner_message_id` else `owner_profile_requires_owner_message` (`:94-99,109,123-124`); `owner_preferences_update` needs it else `owner_preferences_require_owner_message` (`:204-206`). Any agent may write under that rule, not only Lonora. Tool text "only what the owner said" (`:278-279`), module docstring (`:3-5`), context note (`rt/context/memory.py:27-34`), prompt (`res/system/lonora.md:453-456`), template `res/bootstrap/USER.md`.
- Authority-claim guard on notes and profile: `mem/guard.py:63-75`.
- Behavioral signals already recorded: read cursor per thread, max-wins, with a `thread.read` event (`db/thread_prefs.py:94-113`; column `db/schema.py:314`); attention items marked seen (`db/attention.py:498-499`, `api/routes/attention.py:64-75`); broker changes not made by an agent's run as `broker.external_activity` events with journal attribution (`trd/manual_activity.py:108-141`, `trd/broker_recovery.py:156-196`), which is where a manual close of an agent's position shows. Quiet hours exist only as the owner's own setting. NOT recorded: app opens (`SessionRow` has only an expiry, `db/schema.py:40-47`), reactions to drawdowns, report-length preference.
- "What I know about you": web `/app/owner` (`web/shell/settings/OwnerPage.tsx`): owner form, "What your agents know about you" listing lines agents wrote with author and time, each removable (`:89,156-170,243-266`), and a change log with restore (`:279`); routes `api/routes/memory.py:110-179`. Mobile has no such screen: `/owner/profile` is read only by `mob/components/incoming-call-settings.tsx:52,70`. Agent memory editors are separate (`/app/memory` legacy `web/shell/pages.tsx:284`, `mob/app/bot-settings.tsx:58,90`).

## 6. Model assignment and `trust_source`

### 6.1 Model per agent
- Record `agent-model:<hash>` in `ln_settings` (`db/agent_models.py:42-59`): mode `automatic|fixed` plus preference. Allowed list = global routes + backups + owner additions `model_allowed` (`:79-110,118-126`).
- Tool `model_request` (`tools/models.py:212-372`): an Automatic agent switches itself within the allowed list (`:267-272`); a change applies at once when the owner's typed message names the model (`:266,276-282`, `_owner_named` `:129-145`); only Lonora changes another agent's model (`:241-245`); everything else raises an `agent_model` card (`:294-318`); every applied switch raises an `agent_model_changed` Undo card (`:349-357`); 3 switches per run (`:64,329`). `model_list` (`:163-190`).
- Cards: `db/model_cards.py:28-294`, lifetimes `db/owner_actions.py:69-70`, decision `api/routes/owner_actions.py:403,499-503`.
- New agent: no record, so Automatic on the owner's default route, unless the creation spec named a model (`db/agent_creation.py:246-252`). It does not take Lonora's current model.
- Owner API and screens: `api/routes/agent_models.py:31-53`; `web/components/models/AgentModelCard.tsx`, `web/pages/ModelSettingsOverlay.tsx`, `AllowedModelsSettings.tsx`, `ModelRoutingSettings.tsx`; `mob/components/agent-model-settings.tsx` (in `mob/app/bot-settings.tsx:176`), `mob/app/(settings)/models.tsx`.
- Subagent model must be in the allowed list (`rt/collaboration/subagents.py:29-37`).

### 6.2 `trust_source`
- Store `ln_trusted_sources` (`db/schema.py:1127-1160`, `db/trusted_sources.py`): `trust_source` (`:111-195`) is reached only from owner routes and the card decision; `added_via` is `default|operator|owner_ui|owner_card` (`:30`). github.com is trusted by default (`:44-76`). Checks: `github_trusted` (`:284`), `feed_trusted` (`:309`), `mcp_trust` (`:325`).
- Gates that raise the card today (kind `trust_source`, `ct/owner_actions.py:25,45`): feed subscribe outside the list (`tools/feeds.py:141-153`); skill import from an untrusted repository (`rt/skills/lifecycle.py:216-240,251`; `source_trusted` reported by `rt/skills/access.py:224-237`); MCP review (`tools/mcp.py:333-347`, reached from `owner_action_propose` `tools/owner_actions.py:267-271`); card builder `propose_capability_card` (`tools/owner_actions.py:241-262`), `db/capability_cards.py`, `db/owner_actions.py:1477-1572`.
- Decision: `api/routes/owner_actions.py:433` → `trust_from_card` (`:668-716`), MCP tier chosen on the card (`read` or `write_nonfinancial`); tools that can move money are never pinned and block the write tier (`db/trusted_sources.py:144-147`). MCP owner trust flag `mcp_owner_trust` default on (`api/env.py:47`, `tools/mcp.py:124,338`).
- Owner routes and screens: `api/routes/trusted_sources.py:62,151`, `api/routes/integrations.py:48-49`; `web/shell/settings/IntegrationsPage.tsx`, `mob/app/(settings)/integrations.tsx`.

## 7. Screens outside conversations, and P5
P5 allows six: (1) Stop control, (2) agent and conversation list, (3) "needs your attention", (4) "What I know about you", (5) "What is running", (6) sign-in.

### 7.1 Web (`web/shell/routes.ts:2-51`, `web/shell/pages.tsx:246-364`)
| Route | Component (`pages.tsx` line) | Purpose | P5 |
|---|---|---|---|
| sign-in / setup | `AuthFlow` (`web/App.tsx:68-81`) | onboarding, sign-in | 6 |
| `/app` | `ChatList`, `UnifiedSearch` (`:192-197`) | agents, groups, search | 2 |
| `/app/archived` | `ArchivedPage` (`:255`) | archived rows | 2 |
| `/app/agents` | `AgentsPage` (`:256`) | manage agents and groups | 2 |
| `/app/updates` | `UpdatesPage` (`:199`), heads-up `web/shell/lists/HeadsUp.tsx` | attention inbox | 3 (per agent today; unified in phase 7) |
| `/app/activity` | `ActivityPage` (`:300`) | activity log | none |
| `/app/owner` | `OwnerPage` (`:324`) | owner form, known facts, change log | 4 (partial) |
| `/app/tasks`, `/app/tasks/:id`, `/app/new-task` | `TasksPage`, `TaskPage`, `NewTaskPage` (`:200,294-295`) | Tasks and runs | none (5 is workspace processes, phase 4) |
| `/app/settings` | `SettingsRoot` (`:217`); legacy tabs models, voice, trading (`:67,209-215`) | settings hub; the trading tab holds Stop (`web/pages/TradingSettingsPanel.tsx:10`) | none |
| `/app/trading` | `Trading` (`:271`) | positions, orders, journal, Stop (`web/pages/Trading.tsx:27`, `web/components/trading/TradingStatus.tsx:13-65`) | 1 (only here and in the agent sheet `web/conversation/sheets/AgentSheet.tsx:475`; not always visible) |
| `/app/agent/:id`, `/app/identity/:id`, `/app/trades/:id` | `AgentPage`, `IdentityPage`, `TradesPage` (`:257-259`) | agent info, level, supervision, identity form, trades | none |
| `/app/group/:id`, `/app/new-group` | `GroupPage`, `NewGroupPage` (`:260,315`) | group settings | none |
| `/app/new-agent` | `AgentCreatePanel` (`:304`) | creation form | none |
| `/app/recovery` | `RecoveryPage` (`:261`) | broker outage | none (becomes Lonora's report, 9.4) |
| `/app/market` | `Market` (`:263`) | market view | none |
| `/app/routines`, `/app/new-schedule` | `SchedulesPage`, `NewSchedulePage` (`:279,293`) | routines and watches | none |
| `/app/knowledge`, `/app/knowledge-edit`, `/app/goals`, `/app/new-goal` | (`:280-281,291-292`) | agent goals and links | none |
| `/app/memory` | `Knowledge` legacy (`:284`) | agent memory editor, semantic memory switch | none |
| `/app/skills`, `/app/skills/:id`, `/app/new-skill` | (`:296-298`) | skills | none |
| `/app/artifacts`, `/app/artifacts/:id`, `/app/file-edit` | (`:246,248,299`) | files | none |
| `/app/call`, `/app/incoming/:callId` | `CallPage`, `IncomingPage` (`:301-302`) | voice call | conversation surface (see Q22) |
| `/app/accessibility`, `/app/chat-prefs`, `/app/notify-settings`, `/app/communication/:item`, `/app/integrations`, `/app/providers`, `/app/provider[/:item]`, `/app/mcp`, `/app/broker`, `/app/broker-account/:item`, `/app/usage`, `/app/usage-detail/:item`, `/app/storage`, `/app/privacy` | (`:325-353`) | settings pages | none |
| `/app/lab` | `Lab` (`:355`), dev only (`routes.ts:62`) | gallery | none |
Sheets outside the message list: agent sheet `safety` (`web/conversation/sheets/AgentSheet.tsx:674`), `mandate` (`MandateSheet.tsx:408`), `limits` (`LimitsSheet.tsx:301`), `watches` (`WatchesSheet.tsx:116`), `perm` (`web/shell/PermissionSheet.tsx:61`), supervision picker `sup` (`web/shell/agent/AgentPage.tsx:495`), `chat-menu`, `new-chat`, `shortcuts`, `avatar`, `chart`, `trade-edit`, `trade-close`, list sheets, integrations sheets `mcp|domains|rss|cred`, `sign-out`: none of the six.

### 7.2 Mobile (`mob/app/_layout.tsx:52-62`)
| Route file | Purpose | P5 |
|---|---|---|
| `sign-in.tsx`, `server.tsx` | sign-in, server address | 6 |
| `(tabs)/index.tsx`, `agents.tsx`, `archived.tsx` | chats list, manage agents, archived | 2 |
| `(tabs)/updates.tsx` (`AttentionInbox` `:46`) | attention inbox | 3 |
| `(tabs)/tasks.tsx` | agents' runs ("task pages arrive with phase 4") | none |
| `(tabs)/settings.tsx`, `(settings)/account.tsx`, `integrations.tsx`, `models.tsx`, `voice.tsx` | settings | none |
| `thread.tsx`, `group-thread.tsx` | conversation; Stop lives here as `SafetyPill` (`thread.tsx:750`, `mob/components/safety-pill.tsx:32-200`) | conversation; 1 only inside a thread |
| `bot-settings.tsx` | agent form: pair, instructions, pause, memory, grants, model, supervision (`:153-217`) | none |
| `new.tsx`, `new-group.tsx`, `group-settings.tsx` | creation and group forms | none |
| `charts.tsx`, `routine.tsx`, `skills.tsx`, `artifacts.tsx`, `artifact.tsx`, `image.tsx` | charts, routines, skills, files | none |
Overlays: `VoiceOverlay`, `IncomingCallOverlay` (`_layout.tsx:64-65`). Missing on mobile: any "What I know about you" view, any "What is running" view, a Stop control outside a thread.

## 8. Built but switched off in this area (section 13)
- Semantic memory: off by default (`SemanticConfig.enabled = False`, `api/routes/memory.py:182-184`), switched only on the legacy web memory page (`web/pages/KnowledgeSection.tsx:129-153`).
- `discover_specialists` and `account_event_agent` (`db/personal_agent.py:46-70`): no caller.
- `ln_financial_receipts` / `FinancialReceiptRepository` (`db/financial_receipts.py:5-9`): no caller; it also cascades with the agent (`db/schema.py:668,795`), which matters if phase 3 reuses it for Execution Receipts.
- Prompts never loaded: `res/prompts/memory_policy.md` (it still tells agents to keep user preferences in MEMORY.md), `tool_contract.md`, `trading_context.md` (no `load_prompt` reference; loader `rt/skills/loader.py:20-24`).
- `child_agent_create`: registered "compatibility only" (`tools/subagent.py:66-72`); removed by 3.3.3 rather than switched on.
- Supervisor template: accepted by server, offered by no client (1.1).
- Mobile gaps against web: owner profile page, agent page, task pages, knowledge, activity, recovery (7.2).
- `coordination` exposure is left out of a trading agent's Task runs (`rt/tool_exposure.py:45`), so Lonora in a Task run does not see its lead tools natively.

## 9. Tests in this area
Assert behavior the mandate removes (delete or rewrite in the same change as the feature, 14.1.3):
- `tests/test_supervision.py` (1,315 lines): grant reads `:183`, supervisor never pauses a trading agent or Lonora on its own `:507`, narrowing needs a grant and obeys the cycle `:872`, supervision from a sentence or card `:941`, default grant `:1080`, card lifetimes `:96`. Keep and move: owner-pause tests `:308` (owner wins part), `:638`, `:1110`, `:1228`.
- `tests/check_supervision.py`, `tests/web/supervision.test.ts`, `tests/web/supervision.spec.mjs`, `tests/mobile/supervision.spec.mjs`.
- `tests/test_agent_create.py`: templates never carry authority `:38`, trading template needs its market `:50`, responsibility never states authority `:68`, creation and Undo cards `:107`, first-task wake `:139`. `tests/check_agent_create.py`: per-run limit `:315`, 20-agent cap `:452`. `tests/web/agent-create.test.ts:220` (`agent_limit_reached`), `tests/web/agents-from-chat.spec.mjs`, `tests/mobile/agents-from-chat.spec.mjs`, `tests/test_agent_environment.py:257`.
- Binding and roles: `tests/check_agent_binding.py`, `check_bound_market.py`, `check_delegated_scope.py`, `check_flexible_agents.py`, `check_agent_market.py`, `tests/flexible-agent-ui.mjs`, `tests/web/agent-pages.spec.mjs`.
- Exposure: `tests/test_capability_exposure.py:611-615,658-668` (coordination by grant).
- Owner intent: `tests/test_owner_intent.py:86` (oversight is always the owner's tap), `:121` (only a supervisor or Lonora steers); keep `:44`, `:144`, `:182`.
- Owner profile: `tests/test_owner_profile.py:502` (profile writes need the owner) is rewritten for Lonora's observations; keep `:591` and `:982` (reach-me from the owner's message). `tests/check_owner_profile.py`.
- Memory privacy: `tests/test_memory_privacy.py:340` (agents cannot read each other) stays for team agents and gains "Lonora can"; `:469` loses the supervised branch.
- Models: `tests/check_agent_model_choice.py`, `tests/web/agent-model.test.ts` (cards, Undo, self-switch); `tests/check_agent_model_preference.py`.
- Trust: `tests/test_trusted_sources.py:244` (card lifetimes), `:1060` (skills ask once outside the list), `tests/check_trusted_sources.py`, `tests/web/capabilities.spec.mjs`, `tests/mobile/capabilities.spec.mjs`; keep `:65,131,177` (money tools never trustable) and `:736`.
- Named work: `tests/test_named_work.py:110` (an agent is read by name only within reach).
- Teams and peers: `tests/check_team.py` (directory fields), `check_collaboration_sessions.py`, `check_runtime_collaboration.py`, `check_group_replies.py`, `check_personal_agent.py` (uses `discover_specialists`).
- Journeys: `tests/check_simple_lonora.py`, `tests/test_card_journeys.py`, `tests/web/owner-actions.spec.mjs`, `tests/mobile/owner-actions.spec.mjs`, `tests/test_owner_actions.py` (kinds).
- Deletion: `tests/check_durable_records.py` (refusal while uncertain, records survive) stays whole.
Core regression tests (14.1.2) touching this area: `tests/check_account_recovery.py:105-106` asserts the broker-event agent has `role == "personal"`; `tests/check_trading.py:489-495` and `tests/check_execution_recovery.py:637,726` use the `supervised` permission level (phase 3). None asserts supervision, binding or the cap.

## 10. Gap list per clause
| Clause | State | Evidence and what is missing |
|---|---|---|
| 3.1 Lonora always exists | exists | `db/personal_agent.py:16-43`, `db/schema.py:191-197`, `db/agent_creation.py:356-357` |
| 3.1.1 trades under its own mode | partly | starts at "Ask me" (`db/agent_permissions.py:43-44`), account-wide (`db/agent_binding.py:39-40`); the mode itself is phase 3 |
| 3.1.2 creates on its own judgment | partly | tool exists but needs the owner's message or a card (`tools/agents.py:286-326`), requires a template, capped at 20; open to every non-delegated agent |
| 3.1.2 gives responsibilities and instructions | partly | responsibility at creation only (`db/agent_creation.py:236-237`), authority-claim refusal (`rt/collaboration/agent_create.py:52-55`), first task by `peer_send` |
| 3.1.2 edits methods | missing | no tool; owner routes only (`api/routes/agents.py:141`, `api/routes/memory.py:71`) |
| 3.1.2 pauses and resumes | partly | `control_work` needs a grant, refuses trading agents (`db/supervision.py:658-663,689-692`), raises a card (`:708-710`) |
| 3.1.2 cancels the current run | missing | `api/routes/cancellation.py:21` only |
| 3.1.2 deletes | missing | `api/routes/agents.py:165-174` only |
| 3.1.2 one line to the owner | partly | prose in prompt (`res/system/lonora.md:504,513`) and tool hints (`tools/agents.py:197-198`); cards do the telling today |
| 3.1.2 instruments are method text, door never binds | missing | columns plus door check (1.2) |
| 3.1.2 new agent uses Lonora's model | missing | default route or the spec's model (`db/agent_creation.py:246-252`) |
| 3.1.2 delete: tickets transfer to Lonora, Lonora woken | missing | nothing reassigned; later activity wakes Lonora observe-only (`trd/broker_recovery.py:179-186`) |
| 3.1.2 delete: approvals withdrawn | partly | set to `cancelled` (`db/obligations.py:120-124`) |
| 3.1.2 delete: journal, receipts, settlement kept | exists | 1.6; verify phase 3's receipt storage does not cascade |
| 3.1.3 whole-account picture, may act on any ticket | partly | Lonora reads every account (`db/agent_binding.py:147-160`), per-agent operations via `agent_inspect` (`tools/supervision.py:346-376`); no ownership record, no Ask exception (phase 3 plus this phase) |
| 3.1.4 maintains the shared owner model | partly | section 5; every agent writes, only from the owner's message |
| 3.1.5 speaks for the team | partly | account and system events default to Lonora (`gw/attention.py:130-131`, `db/attention.py:570-571`, `gw/owner_cards.py:40-45`); brief and unified view are phase 7 |
| 3.1.6 reads any team agent | partly | works through the revocable default grant (2.1); must become built in |
| 3.2.1 same capabilities | missing | 1.4 |
| 3.2.2 no leading | missing | `agent_create`, `supervision_change`, `child_agent_create`, `agent_control` are open to team agents |
| 3.2.3 peers, message is information | partly | `peer_send` works; delivered as a user turn without a data mark (`rt/context/history.py:199-208`) |
| 3.2.4 private memory, in the store | partly | private except to grant holders (section 4); other supervisors go away with grants |
| 3.2.5 direct access | partly | conversation per agent and @mention exist; a paused agent cannot be talked to (`db/messages.py:514-515`) |
| 3.3.1 two levels | missing | arbitrary grants, parents, report links |
| 3.3.2 no limit on agents | missing | 1.3 |
| 3.3.3 removed hierarchy | missing | all five items present (1.1, 2) |
| 3.3.4 positions | missing | phase 3; basis today `lonora_opened` (`trd/account_authority.py:110-143`), `attributed_agent` (`trd/manual_activity.py:108-138`) |
| 8.1 learning from behavior | missing | only read cursor, attention seen and external broker activity are recorded (section 5) |
| 8.2 replaced rules | missing | gates `tools/memory.py:123-124,204-206`, prompt `res/system/lonora.md:454` |
| 8.3 shared model drives reports | partly | profile reaches every agent (`rt/context/memory.py:119-152`); nothing learned feeds timing or length |
| 8.4 "What I know about you" | partly | web `/app/owner`; no mobile view; covers the profile only |
| P5 | missing | section 7: about 45 web routes and 20 mobile routes outside the six; Stop not always visible; views 4 (mobile) and 5 absent |
| 12.3 / 10.3.2 models | partly | owner-named assignment exists (`tools/models.py:276-282`); cards, self-switch and allowed list contradict "typed message, no card" |
| 10.3.2 `trust_source` | missing | card only; no typed-message path (6.2) |

## 11. Design questions the mandate leaves open
Each: options, then the recommendation. All are "how" questions for the owner (0.1).
1. **How Lonora is identified once roles go.** (a) keep `role='personal'` and collapse every other value to one team value; (b) a boolean; (c) the deterministic id. Recommend (a): 14.3.15 asks for a "built-in role check", and the core test `tests/check_account_recovery.py:106` asserts `personal`.
2. **Do templates survive as labels?** (a) remove the column, `TEMPLATE_LEVEL`, template notes and the tool input; (b) keep a non-limiting label. Recommend (a): 14.2.6 removes templates that limit capability and all four do; the acceptance scenario names agents by purpose only.
3. **`create_agent`, `agent_created` and `supervision_paused` cards are not in the 10.3.2 table.** (a) delete them (only five fixed cards exist; Lonora tells the owner in one line; undo is "delete it" in chat); (b) keep Undo as a sixth card. Recommend (a), confirmed by the owner because it removes one-tap Undo.
4. **A team agent that needs an agent (3.2.2).** (a) `agent_create` exists for all and refuses non-lead callers with a hint to message Lonora; (b) the tool is absent from team agents' inventory. Recommend (a) plus leaving it out of their eager set.
5. **The owner types "create a helper" to a team agent.** Refuse (3.2.2 is a MUST NOT with no owner exception) and hand the request to Lonora with `peer_send`.
6. **Whose pause is one Lonora makes because the owner asked in chat?** (a) the owner's (only the owner lifts it); (b) Lonora's. Recommend (a): store it as `source='owner'` with Lonora as holder for attribution, which is what `owner_takes_over` already produces (`db/supervision.py:397-399`).
7. **Migration 14.3.18.6: which holds end, and does the work resume?** Holds with `source='agent'` (including Lonora's own) end and their work resumes; `owner_message` holds: (a) end too, (b) become owner holds. Recommend (b), since ending them resumes work the owner asked to pause; Lonora posts one line listing what resumed. Resuming is safe only after 14.3.18.1 put every agent in Ask.
8. **Where 14.3.18.4 runs.** The mandate says the whole of 14.3.18 is one step before the permission code is deleted (phase 3), yet roles, parents and supervisor holds are phase 6 code. (a) phase 3's step runs all eight items and phase 6 only drops columns; (b) phase 6 runs 18.4 and 18.6. Recommend (a) with the two functions written so phase 6 can run them idempotently if phase 3 did not; check the Alembic history on arrival.
9. **What "method" is.** `AgentRow.instructions` (owner text, system role, unversioned), OPERATING.md (agent notes, versioned by `ln_memory_revisions`) or a phase 5 method store with versions (5.5.5). Recommend whatever phase 5 built; binding text from 18.4 and Lonora's edits go there, each as a version.
10. **Is Lonora's method text an instruction or data to the team agent?** Today text another agent wrote stays out of the system role (`db/agent_creation.py:65-73`, `rt/context/builder.py:102-108`). (a) keep it as a labelled method block the agent follows; (b) system role. Recommend (a): 3.1.2 needs the agent to follow it, 6.10 needs injected text never to become system policy.
11. **Position transfer mechanism at delete.** (a) rewrite an ownership row per ticket; (b) derive: owner = the journal agent if it still exists, else Lonora. Recommend the one that matches phase 3's ownership representation; (b) needs no write and cannot be half-done.
12. **The deleted agent's conversation.** (a) keep the cascade; (b) soft-delete so Lonora and the owner still read it (3.1.6) and receipts shown in it survive. Recommend (a) only if phase 3's Execution Receipt record is journal-derived; otherwise (b).
13. **Lonora woken with transferred tickets.** A new server-authored trigger (add to `SERVER_AUTHORED_TRIGGERS`, `rt/context/routine.py:13-15`) with fixed text listing account, ticket, symbol and volume, as an ordinary run (not observe-only), in Lonora's conversation.
14. **Can a paused agent answer the owner (3.2.5 versus 4.7.1)?** (a) the owner's direct message always starts a run, which under 4.7 may only reduce risk; (b) refused as today. Recommend (a).
15. **Lead tool surface.** (a) extend `agent_control` with `cancel_run`, `delete`, `set_ask`; method edit through phase 5's method tool with an `agent_id`; keep `agent_inspect`; (b) new tools. Recommend (a).
16. **How the one-line report is guaranteed.** (a) prompt only; (b) each lead tool result names it as an open step that the conversation gate holds (`rt/conversation_gate.py`); when the run is not in the owner's view, the line is posted in Lonora's conversation. Recommend (b).
17. **Which behavioral signals are stored (8.1).** (a) events only, Lonora reads them; (b) one append-only owner-signals record (app opened, thread read, manual close) plus a small summary on Lonora's wake. Recommend (b) minimal: 11.1.3 needs "opened the app on at least 3 days" as a server fact; reactions to drawdowns and report length stay Lonora's judgment written to the profile.
18. **Who writes observations.** Only Lonora without the owner's message (8.2, 14.3.5); team agents keep the typed-message rule and send observations to Lonora. The view marks each line "you said" or "observed" from the revision's `source_message_id`.
19. **Does anything in `owner_preferences_update` open up?** 8.2 names its gate as replaced but also keeps reach-me on the typed message. (a) the whole structured record (channel, device, quiet hours, time zone, reply language) stays typed-message only and learned quiet hours are profile text; (b) Lonora may set quiet hours and time zone from behavior. Recommend (a): the structured quiet hours gate real calls (`ct/incoming_calls.py:105-110`).
20. **Model assignment.** (a) every change needs the owner's typed message naming the model; self-switch, Fixed/Automatic and both cards go; "any available model" = any catalog model of a connected provider (`db/agent_models.py:233-266`), so the allowed list stops gating; (b) keep self-switch within the allowed list. Recommend (a). New agents store Lonora's model at creation (a snapshot, per 3.1.2 "current").
21. **Trust without a card.** `owner_message_id` is void once the run read external content, and the agent usually reads the feed, repository or MCP tool list first (`tools/feeds.py:136`, `tools/mcp.py:341-345`). (a) trust only in an untainted run; (b) the typed message must name the source (domain, owner/repository, server), as models already do (`tools/models.py:129-145`). Recommend (b). MCP write tier only when the owner's words ask for writing; the money-tool block stays. `added_via` gains `owner_message` (`db/trusted_sources.py:30`, CHECK `db/schema.py:1147-1150`).
22. **P5 edges.** Voice call pages and group conversations count as conversations; device preferences (theme, language, accessibility, app lock, sign-out, server address) have no place in the six. (a) literal: follow the device, sign-out next to sign-in; (b) one device sheet. Ask the owner; default (a).
23. **P5 ordering.** Screens whose chat replacement belongs to another phase (broker forms: phase 8; provider keys and secrets: phase 4; attention: phase 7) cannot be deleted here without breaking 14.1.1. Recommend deleting in phase 6 only screens whose chat path works, and handing the rest to their phase with a tracked list.
24. **"What is running".** 7.1.5 defines it as workspace processes. Tasks, routines and watches are then asked in chat. Recommend literal; the Tasks tab goes.
25. **Groups and collaboration hosts.** A group lead only decides who answers; a collaboration host only gathers evidence. Recommend keeping both as peer mechanics, renaming nothing, and confirming with the owner that neither is "leading" under 3.2.2.

## 12. Ordered steps (each one a reviewable pull request)
Preconditions to verify on arrival. From phase 3: a per-agent mode read under `authority_lock`; position ownership with `ticket_not_owned` and the Lonora exception; a paused agent still wakes for its own tickets and may reduce risk (4.7.1, 14.3.7); `require_task_authority` lets risk-reducing requests through; `assert_market_binding` and the delegated refusal are out of the door; provenance helpers live in a surviving module (14.3.5, today `tools/restrictions.py:56-116`); `supervises_all`, `check_cycle`, `record_intervention`, `holds_over` lost their restriction callers; whether 14.3.18.4 and .6 already ran. From phase 4: one workspace per owner, the CLI token per agent. From phase 5: the method store with versions, the full picture on wake, the rewritten prompt.

1. **Move the owner pause** (14.3.6; no behavior change). New `db/pauses.py` holding `live_hold`, `work_paused`, `release_hold`, `owner_takes_over`, `owner_holds_for`, `refuse_held`, `owner_resumes`; `SupervisionHoldRow` and its table stay as they are. Update the import sites in 2.2. Verify: the four owner-pause tests of `tests/test_supervision.py` pass from a new test file.
2. **Move `personal_agent_id` and add the lead check** (14.3.15). `db/personal_agent.py` gains `personal_agent_id` and `is_lead`. Read paths accept "grant or lead": `mem/sessions.py:134-150`, `tools/supervision.py:419,444`, `rt/collaboration/subagents.py:100`, `rt/tool_exposure.py:43-46,96`, `db/agent_directory.py:22-23`. Verify: a new test revokes Lonora's default grant and Lonora still reads; a team agent still cannot.
3. **Lead control without a grant or owner message** (3.1.2; depends on phase 3 pauses). `control_work` lets Lonora pause and resume any team agent and its work; the hold records Lonora as holder; no card; drop `money_standing`'s refusal for Lonora only once 4.7.1 holds. Add `cancel_run` and `set_ask`. Verify: Lonora pauses a trading agent with an open position, and the paused agent still closes it.
4. **Lonora edits methods** (3.1.2; depends on phase 5). The method tool accepts a team `agent_id` from Lonora; each write is a version and is delivered per Q10. Verify: version created, revert works, a team agent calling it for another agent is refused.
5. **Creation on Lonora's judgment, flat and uncapped** (3.1.2, 3.2.2, 3.3.2, 4.3.2-4.3.3). `agent_create` for Lonora creates directly with no owner message and no card, takes no template, `report_to` or `supervises`, writes instrument and account into the method, copies Lonora's mode (or Ask; a request for full authority raises the Mandate card), stores Lonora's model. Remove `MAXIMUM_ACTIVE_AGENTS` at its five sites (1.3) and keep the per-run guard. Team agents are refused. Same change: `tests/check_agent_create.py:452`, `tests/web/agent-create.test.ts:220`, client string `tsk/owner-actions.ts:749`. Verify: 25 agents exist; a fourth creation in one run is refused; a team agent's call is refused.
6. **Deletion by Lonora with transfer** (3.1.2, 14.3.16; depends on phase 3 ownership and 4.5, phase 4 token). `agent_control delete` reuses `delete_created_agent`; `prepare_delete` keeps its refusal; in the same transaction: tickets become Lonora's (Q11), pending Trade Approval rows are withdrawn, the continuous task ends, the CLI token is revoked, Lonora is woken (Q13). Verify: delete with an open position and a pending order, then Lonora closes the position through the door; delete with an ambiguous operation is refused; journal, approval and settlement rows are still there.
7. **Lonora on a ticket owned by an agent in Ask** (3.1.3). The door turns Lonora's risk-increasing request on such a ticket into a Trade Approval card even when Lonora is Full. Verify with both modes of the owning agent.
8. **Peer messages as data** (3.2.3, 6.10). `history_context` wraps other agents' messages in the same data frame as other third-party content; a peer run's wake states that the request is information. Verify: `tests/test_context_engine.py` gains the frame; `owner_message_id` results unchanged (`tests/test_owner_intent.py:44`).
9. **Owner model** (8.1-8.3). Record the signals (Q17); Lonora's USER.md writes no longer need `owner_message_id`, team agents and reach-me keep it (`tools/memory.py:123-124,204-206`); update `res/system/lonora.md:453-456`, the tool description and `rt/context/memory.py:27-34`, and regenerate the manifest (5.8.6). Verify: Lonora writes an observation in a routine run; a team agent's attempt returns `owner_profile_requires_owner_message`; reach-me from a non-owner run is refused.
10. **"What I know about you" on web and mobile** (8.4). One view over the profile lines with origin and correction; mobile gets it for the first time. Verify with one web and one mobile spec.
11. **Model assignment from the typed message** (12.3, 10.3.2). Apply Q20; remove `agent_model` and `agent_model_changed` cards with their clients and tests in the same change. Stored cards of those kinds are settled first (14.3.9).
12. **Trust from the typed message** (10.3.2, 14.3.8). Apply Q21 in `tools/feeds.py`, `rt/skills/lifecycle.py`, `tools/mcp.py`; remove the `trust_source` card after the three flows pass without it. Verify: `tests/test_trusted_sources.py:65,131,177,736` unchanged.
13. **Data migration** (14.3.18.4, .6; if phase 3 did not run it). One Alembic revision: write each bound pair into the agent's method, set every non-personal role to the team value, clear `parent_id` and `template`, revoke every grant, end supervisor holds per Q7. Data first, then CHECK constraints (`db/schema.py:167-190`).
14. **Delete binding** (3.1.2, 3.2.1). Remove the non-financial callers in 1.2, `BINDING_POLICY`, `binding_context`, the scope contract (`ct/agent_scope.py`), the columns `trading_account_id`, `trading_symbol`, `scope_mode`, `scope_revision`, `parent_id`, `template`, and the client readers in 1.2. See risk 4 before removing `fill_bound_fields`.
15. **Delete supervision** (3.3.3, 14.2.6). Grant functions, `ln_supervision_grants`, `grant_default`, `seed_personal_grants`, `supervision_change`, `child_agent_create`, `api/routes/supervision.py`, `ct/supervision.py` (keep the inspect and control inputs), the four card kinds, activity kinds, `report_to` and its notes, web and mobile screens (2.3), `docs/supervision.md`, prompt lines `res/system/lonora.md:501,505-514`, manifest, and the tests in section 9. `prepare_delete` keeps its refusal (14.3.16); only the subject filters of removed card kinds leave `settle_for_delete` (`db/owner_actions.py:2185-2194`).
16. **P5 shell** (P5). Stop always visible in the web shell and the mobile tab layout; the six surfaces; remove screens whose chat path works (Q23), web and mobile in the same change as any API they alone used (14.1.4).
After every step the eleven core tests of 14.1.2 run.

## 13. Risks to the safety core (section 6)
1. **Pausing before paused agents can exit.** Today a paused agent gets no run at all (`db/runs.py:156-157`), which is why supervisors may not pause trading agents (`db/supervision.py:27-32,689-692`). Step 3 before phase 3's 4.7.1 would leave positions unattended.
2. **Lonora's cross-agent actions must use the one door** (6.1, 6.6, 6.7). Acting on another agent's ticket needs the merged stale-target check and, for an Ask owner, the exact-approval card; no side path.
3. **Delete during a send.** Keep the lock order: owner-action lock, creation lock, `authority_lock`, agent row (`db/agent_creation.py:214-216,354-355`). `prepare_delete` sees reserved rows because attribution is written at reservation (`trd/execution.py:253-266`, `db/obligations.py:57-64`); do not weaken that query when grants and goals leave it. Runs cascade with the agent (`db/schema.py:386`), so a delete that slipped past would strand a journal row with no run to reconcile from.
4. **Operation identity when binding fill goes** (6.2, 6.3, 14.3.9). The operation id is `stable_id(run_id, "trade:" + request_hash(args))` (`tools/trade.py:765`) over arguments after `fill_bound_fields` and `align_payload` (`tools/registry.py:574-578`, `tools/market_binding.py:54-90,195-199`). A checkpointed run of a bound agent replayed after the fill is removed hashes different arguments and derives a NEW operation id: a second send, not an idempotency refusal. Remove the fill only when no bound agent has a journal row in `reserved`, `submitted` or `ambiguous` and no checkpointed pending trade call, and test it with the 14.3.9 ambiguous-row scenario.
5. **Transferred tickets and observe-only wakes** (6.9). Activity on a deleted agent's ticket wakes Lonora observe-only today (`trd/broker_recovery.py:179-186`), which the door refuses (`trd/execution.py:81-85`, `tools/registry.py:541-543`). After transfer Lonora owns the ticket and its wake must be ordinary; the observe-only refusal for tickets an agent does not own stays.
6. **Dropping `owner_message_id` from lead actions** (14.3.5, 6.10). A Lonora run that read a web page, a feed or a team agent's memory (`agent_inspect` is external content, `rt/context/run_evidence.py:66-69`) can then create, pause, delete and rewrite methods. The mandate accepts this; what must hold: third-party text stays framed as data, Full is still set only by the owner's tap, the per-run creation guard stays, and the four remaining gates (tickets not owned, reach-me, trust, model) keep `owner_message_id`.
7. **Peer framing must not change owner detection.** `owner_typed_message` (`db/owner_words.py:62`) and `external_content_seen` (`tools/restrictions.py:77-94`) decide the owner exception of 3.3.4 at the door; step 8 changes rendering only.
8. **Role flattening and broker wakes.** `wake_for_activity` tests `role != "delegated"` and `paused` (`trd/broker_recovery.py:180-185`) and `tests/check_account_recovery.py:106` asserts `personal`; flattening must keep Lonora's role value and keep attributed agents woken with normal authority.
9. **Hold lock order.** The owner's controls lock the agent, routine or watch row before the hold; a Task takes hold, run, Task (`db/supervision.py:559-562`). Moving the functions (step 1) and adding Lonora's path (step 3) must keep both orders, or pause and resume deadlock with message admission.
10. **Receipts and the cascade.** Anything phase 3 stores for Execution Receipts or settlement under a thread or agent foreign key with `CASCADE` (as `ln_financial_receipts` has today, `db/schema.py:668-669,795`) would be destroyed by a delete, against 3.1.2. Check before step 6.
