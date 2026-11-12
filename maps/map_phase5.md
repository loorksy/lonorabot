# Phase 5 map: "The agent's mind" (mandate §5, 14.2.8, 14.3.9 label, 14.3.12, §17)

Baseline: `/home/user/wt-agent/mandate` at `a776adf` (mandate adopted as `VISION.md`; phases 2-8 not started). Every line number below is from that commit; Phases 3 and 4 will move code before Phase 5 starts, so re-anchor by symbol name.
Path shorthands: `AR` = `packages/agent-runtime/src/lonora_agent`, `RES` = `packages/agent-runtime/resources`, `TOOLS` = `packages/tools/src/lonora_tools`, `TRD` = `packages/trading/src/lonora_trading`, `DB` = `packages/db/src/lonora_db`, `MKT` = `packages/market/src/lonora_market`.

---

## 1. The system prompt today

### 1.1 What reaches the model, in order

| # | Block | Source | Role | Refreshed |
|---|---|---|---|---|
| 1 | `<lonora_operating_policy>` = `SOUL.md` + `AGENTS.md` + chapter `core` | `AR/skills/system_policy.py:98-109` | system | every model turn, also in resumed checkpoints (`system_policy.py:152-165`) |
| 2 | visual policy (v1 `native_visual_response.md`, or `genui_v2.md` when `LONORA_GENUI_V2` is on) | `AR/skills/visual_policy.py:76-83`, joined at `AR/skills/loader.py:40` | system | every turn (`visual_policy.py:86-98`) |
| 3 | six constitution files: identity, tool-policy, memory-policy, security-policy, collaboration-policy, trading-policy | `AR/skills/loader.py:27-46` (names at 29-36) | system | **only at `build_context`**; frozen in a checkpoint |
| 4 | `agent.instructions` (when the owner wrote it), `binding_context`, skill catalog, `wake_context`, goal core | `AR/context/builder.py:107-116` | system | build only (skill catalog also refreshed, `AR/context/skills.py:263-298`) |
| 5 | optional prompts: `group_behavior`, `suggested_reply`, `web_search_on`, `subagent_system`, voice observation | `builder.py:128-145` | system | build only |
| 6 | goal details, recorded decisions + active theses, operational observations | `builder.py:119-127, 160-163` | system, `runtime_context` (sheddable) | build only |
| 7 | routing frame: identity, `live_agent_state`, `protected_operational_state`, agent directory, group, **permission frame** | `AR/context/team.py:59-111` | system | **every model turn** (`AR/model_runtime.py:65`, `team.py:114-130`) |
| 8 | up to 3 domain chapters `<lonora_domain_guidance>` | `system_policy.py:121-186` | system, `runtime_context` | every turn |
| 9 | capability inventory; visual observation catalog; GenUI capabilities | `model_runtime.py:68-92` | system, `runtime_context` | every turn |
| 10 | `<lonora_context_data>`: responsibility, owner profile, owner goals/links, OPERATING.md, MEMORY.md, skill bodies, summary, tool evidence, symbols, recall, scratchpad, quote, attachments | `builder.py:219-287` | user (labelled data) | build only |

Consequence that matters for 5.4 and 5.8: `build_context` runs only when a checkpoint has no transcript (`AR/loop_restore.py:53-55`). A continuous Task (the 4.5 account-management task) wakes through `consume_wake`, which appends `<runtime_wake>` to the old transcript (`loop_restore.py:91-114`). So blocks 3-6 and 10 keep the text they had when the Task started; only blocks 1, 2, 7, 8, 9 follow a deploy or a new wake.

### 1.2 `RES/system/lonora.md` (650 lines, 59,555 chars)

| Chapter | Lines | Chars | What it is |
|---|---|---|---|
| preamble | 1-7 | | "Documentation never grants account access, financial permission" (5) |
| `core` | 9-168 | 14,892 | Identity (10-25), Public voice (27-39), Language/privacy (41-55), Formatting (57-73), Truth and evidence (75-94), **Financial authority is mandatory (96-116)**, Work rhythm and questions (118-149), Security and recovery (151-167) |
| `voice_surface` | 170-178 | 561 bytes | realtime voice short policy; used by `packages/voice/src/lonora_voice/context.py:196` |
| `voice` | 180-210 | 2,919 | voice behavior + `owner_notify` / call rules (209) |
| `market` | 212-252 | 4,336 | market reads, symbols, sizing helper, watches |
| `charts` | 254-296 | 3,376 | chart tools |
| `account` | 298-327 | 2,189 | account identity, owner intervention |
| `trading` | 329-373 | 4,565 | proposal, confirmation, verification |
| `goals` | 375-409 | 2,903 | trading goals (deleted with goals, 14.2.4) |
| `tasks` | 411-447 | 2,984 | tasks, routines, watches |
| `memory` | 449-490 | 4,655 | USER/MEMORY/OPERATING, skills lifecycle |
| `collaboration` | 492-538 | 4,652 | agents, templates, supervision, groups |
| `research` | 540-577 | 3,585 | web, MCP, trust cards, credentials |
| `files` | 579-617 | 3,025 | workspace, artifacts |
| `intelligence` | 619-650 | 3,799 | decisions, opportunities, performance, backtesting ban, model switch |

Governance text to delete or rewrite under 5.8.2 (grants, limits, restrictions, goals, supervision), by line:
- core: 19-25 (binding, "Never default authority, size limits or autonomy", "analysis is not permission to trade"), 98-109 and 112-113 (ladder, AccountAuthority, delegation, goal step), 139-140 and 143 (financial limits, loss range, "never grant financial consent").
- voice_surface 176; voice 194-195 (spoken yes, standing authorization).
- market 226 and 229 (binding, "grants and restrictions"), 241, 250; charts 264; account 320-322, 325-326.
- trading 342, 344, 358 (keep the risk-reducing definition, drop "within permission"), 360 (restrictions and monetary limits), 367-370.
- goals 375-409 whole chapter; tasks 415, 435; memory 454 (USER.md "write only what the owner said", replaced by 8.2 in Phase 6), 456-457, 474, 478-485.
- collaboration 501-514 (templates, creation card, "no money authority", supervision, `trade_restriction_create` pause), 523, 533, 537.
- research 563-566 (trust and credential cards, 10.3.2), 569; intelligence 623-624, 647 (model-change card), 648.
- Identity line 16 today: "You are not Grok, Claude, ChatGPT, a coding assistant, or an unrestricted desktop operator." 5.8.3 keeps the first three names only.
- Rules that forbid the section 7 environment (5.8.3): 127, 160-161, 291-292, 478, 482, 485, 549-553, 567, 571-572, 586-587, 614.
- Correctness text that must survive (section 6): 75-94 (truth and evidence), 105, 110-111, 113, 346-357, 359, 361-366, 372.

### 1.3 `RES/system/manifest.json` (138 lines)

- Fields: `version: 2` (2), `manual_sha256` (3), `bootstrap_sha256` for `AGENTS.md`, `MEMORY.md`, `SOUL.md`, `USER.md` (4-9), `tool_policies` tool name to chapter, 126 tools (10-137).
- Produced by `scripts/export_agent_tool_reference.py`: manual text = file up to the markers `## Behavioral examples` / `<!-- tool-reference:generated -->` (22-27); mapping = `tool.toolset` for every registered tool (29); fails when a toolset is not a chapter (30-33); hashes (38-42); `--check` compares both files byte for byte (58-62). `Tool.toolset` defaults per module in `TOOLS/loader.py:10-50` (for example `"trading_goal": "goals"` at 44, `"performance": "intelligence"` at 35).
- Checked at load by `system_policy._load` (`system_policy.py:40-85`): bootstrap hashes (50-53), manual hash and version (54-61), unique non-empty chapters (63-69), `core`, `voice`, `voice_surface` present (70-71), sizes (72-73, 77-82), every mapped chapter exists (74-76). Any failure raises `operating_policy_invalid` 500 (85): **no agent run can start**.
- `validate_system_policy` requires `set(tool_policies) == registered tools` (116-118); called from `AR/skills/registry.py:188-198` (`validate_resources`), which `scripts/build.sh:7` runs; `build.sh:8` runs the exporter `--check`; `build.sh:10` runs `scripts/check_policy_distribution.py` (wheel build, installed layout, `len(load_constitution()) == 7` at line 92).
- Data files are listed literally in `pyproject.toml:84-104` and `packages/agent-runtime/pyproject.toml:19-39` (constitution, each playbook, each skill; prompts use a glob at 93 / 28). 14.3.12 applies to every removal.

### 1.4 Constitution, bootstrap, prompts

- `RES/constitution/identity.md:1` (577 chars): ends with the code ban, "Never hand the owner code as a deliverable, trading code included (MQL5, Pine Script, expert advisors, scripts, websites, apps): decline in one line" (5.8.4).
- `RES/constitution/trading-policy.md` (3,181 chars): line 1 is the ladder (No trading / Ask me / On its own, signed AccountAuthority, goal plans), line 3 readiness, line 5 verification, line 7 "Owner controls are tools" (`trade_restriction_create`, risk limits, `owner_action_propose`). `loader.py:41-45` raises `policy_resource_missing` when the file is missing or empty, hence "rewritten, not deleted" (5.8.5).
- `RES/constitution/tool-policy.md` (4,056 chars): line 5 is goals and grants (`goal_list`, `grant_authority`); line 3 and 15 ask for "financial limits".
- `collaboration-policy.md:1`, `memory-policy.md:1-3`, `security-policy.md:1`: short; collaboration mentions "exact-symbol binding".
- `RES/bootstrap/SOUL.md` (11 lines) and `AGENTS.md` (13 lines) are in the core block (`system_policy.py:100-106`). `USER.md` and `MEMORY.md` are hashed (`system_policy.py:46-53`) but never sent to a model: no reader besides the hash check.
- `RES/prompts/*.md`, loaded: `run_context_summary` (`AR/context_engine.py:91`), `consolidator_archive` (`AR/context/compaction.py:20`), `group_behavior`, `suggested_reply`, `web_search_on`, `subagent_system` (`builder.py:129-137`), `native_visual_response` / `genui_v2` + `genui_v2_teaching_p|o` (`visual_policy.py:37-45, 79`). Never loaded: `identity.md`, `memory_policy.md`, `tool_contract.md`, `trading_context.md`, `untrusted_content.md` (no `load_prompt` caller; older copies of the constitution).
- `RES/prompts/genui_v2.md:5`: "Never an interface for: buying, selling ... grants, limits, the trading ladder ... supervision changes ... Never for out-of-scope work or code as a deliverable ... Never put a card in the same reply as an approval or owner-action card." (5.8.4, 10.2.4).

### 1.5 Chapter selection per turn (`system_policy.apply_operating_policy`, 121-186)

1. Look at the assistant tool calls in the last 16 messages, newest first (138-144); each permitted call adds its chapter.
2. Add the seeded chapters `market` and `trading` when a tool of that chapter is in the native tool list (`SEEDED_DOMAINS`, line 26; 145-146).
3. Keep the first 3, sorted by name (148). No owner-text matching and no extra model call (docstring 127-134).
4. The native tool list comes from `AR/tool_exposure.py:31-49`: profile `market` only for an agent bound to an account or the personal agent; others get `research`. So a research agent is not offered trading tools natively and reads no trading chapter first (contradicts 3.2.1; Phase 6 owns the fix, Phase 5 text must not assume it).

### 1.6 Size budgets and where they are enforced

| Budget | Value | Enforced at | Today |
|---|---|---|---|
| core block (SOUL + AGENTS + `core`) | 16,000 chars | `system_policy.py:21, 72, 107-108`; `tests/test_system_policy.py:120` | **15,942: 58 chars free** |
| `voice_surface` | 800 bytes | `system_policy.py:72`; `test_system_policy.py:216` | 561 |
| one domain chapter | 14,000 // 3 = 4,666 chars | `system_policy.py:22-23, 77-82` | memory 4,655, collaboration 4,652, trading 4,565 |
| domain message | 14,000 chars, 3 chapters | `system_policy.py:148-150` | |
| manual length | 300-700 lines | `tests/test_system_policy.py:54` | 650 |
| v1 visual policy | 6,500 chars | `visual_policy.py:14, 70` | 6,450 |
| GenUI v2 policy | 18,000 chars | `visual_policy.py:18, 49` | |
| first request total | < 17,000 + visual | `test_system_policy.py:131` | |
| eager tool schemas | 26,950 chars of serialized definitions per profile set | `TOOLS/registry.py:94`; `tests/test_tool_discovery.py:165-172` (also `EAGER + PROMOTED < 30000`) | |
| promoted schemas | 2,850 chars, 6 tools | `registry.py:95-96` | |
| skill catalog | 6,000 chars | `AR/context/skills.py:248` | |
| skill bodies | 16,000 chars total, per-skill `context_budget` | `AR/skills/resolver.py:29, 86, 94` | |
| agent directory | 12,000 chars | `AR/context/team.py:17` | |
| agent memory document | 30,000 chars | `DB/memory.py:97` | |
| voice context | 7,500 bytes | `packages/voice/src/lonora_voice/context.py:17` | |

---

## 2. Per-turn frames compared with 5.4

The routing frame (`team.py:59-111`) is the only state refreshed on every model turn. It holds: identity (70-72), `live_agent_state` without readiness (82-90; contract `packages/contracts/src/lonora_contracts/agent_state.py:31-56`: tasks, runs, waits, counts of approvals and watches, up to 6 watches, account authorities, health), `protected_operational_state` (94-105; `DB/operational_state.py:67-230`: unresolved, verifying and recently resolved operations, goal steps in flight, pending approvals, active watches), the agent directory (25-56; rows from `DB/agent_directory.py:24-41`: id, name, title, paused, role, scope, bound account and symbol, template, supervision flags), group, and the permission frame.

Permission frame (`AR/context/permissions.py`): `permission_guidance` (61-187) builds a JSON snapshot (101-120: `effective_level`, grant scopes with every envelope limit, `owner_restrictions`, `monetary_risk_limits`, `global_trading`) plus about 1,900 chars of fixed prose (151-187) on grants, restrictions, limits, Resume and Start-trading cards. `permission_context` (190-207) reads `permission_state`, observe-only scope, `provisional_voice`, restrictions and money limits (`trading_limits`, 210-232) and `global_trading` (`DB/trading_readiness.py:77-90`: `stopped` when `emergency_stop` or `not enabled`).

| 5.4 requires | Today | Where |
|---|---|---|
| own positions | not in any frame. Only through the `account_read` tool, a fresh broker read with no owner attribution (`TOOLS/account.py:69-73`, `TRD/accounts.py:7-17`), or as "historical" tool evidence of earlier runs (`builder.py:245-251`, `AR/context/run_evidence.py`) | missing |
| own pending orders | same. The frame shows journal rows not yet settled and approval rows, not broker orders | missing |
| own exposure | none. `account_exposure` groups a snapshot by symbol and direction but feeds only the cap checks (`TRD/exposure.py:21-50`) | missing, helper exists |
| floating P&L | `Position.profit` exists (`packages/contracts/src/lonora_contracts/account.py:30`), only inside `account_read` | missing |
| realized P&L | nowhere for the agent. `account_history` returns raw deals (`TOOLS/account.py:33-40`); daily realized P&L exists only inside money limits (`TRD/risk_limits.py:303-372`, deleted by 14.2.2) | missing |
| team positions and pending orders by symbol | none. `account_activity` lists external changes with `agent_id` (`TOOLS/account.py:80-97`); `agent_inspect` is for supervisors | missing |
| ... and by currency (each leg, quote currency) | none. `Instrument.base_currency` / `profit_currency` exist (`packages/contracts/src/lonora_contracts/market.py:23-24`, used at `MKT/instruments.py:117-119`) | missing, data exists |
| high-impact calendar, next 24 h, those currencies | none. Tool `economic_calendar_read` only (`TOOLS/market_analysis.py:241-281`), native for the `research` profile only (395), and only when the owner configured a source (234-238); every call fetches the URL live, 20 s timeout, no cache (`MKT/economic_calendar.py:63-117`); `CalendarEvent.impact` is a free string (`market.py:74`) | missing |
| whether Stop is in force | yes, every turn: `global_trading {state, since, changed_by}` (`permissions.py:117-119, 206`) | exists; Phase 3 changes its meaning (`enabled` removed) |
| current mode (5.8.7) | ladder level today (`permissions.py:101-108`) | Phase 3 replaces |
| "judging correlation is the agent's job" | text says the opposite in tone: `lonora.md:576, 631` | rewrite |

Data already on the server that a picture can be built from without a broker call: the reconciliation snapshot `BrokerSessionRow.state["broker_recovery"]` holds `account`, `positions`, `orders`, `observed_at` for every enabled account (`TRD/broker_recovery.py:95-112, 135`; contract `packages/contracts/src/lonora_contracts/broker_activity.py:33-45`), refreshed by the gateway step `account_recovery` every 10 s (`packages/gateway/src/lonora_gateway/service.py:50, 186-191`). Ticket attribution exists: `attributed_agent` (`TRD/manual_activity.py:108-138`), `journal_agent` (92-105), `lonora_opened` (`TRD/account_authority.py:110-144`, moved by 14.3.2).

---

## 3. Learning (5.5)

**How a close is seen today.** `reconcile_broker_account` (`TRD/broker_recovery.py:27-154`) reads account, positions and orders under the account send lock, then `detect_activity` (`TRD/manual_activity.py:141-208`) diffs them against the previous snapshot: a position missing from the new read is `closed` (173-174), a smaller volume is `partial_close` (177-178). `_known_change` (27-89) marks a change `lonora` when a confirmed journal operation explains it, else `external`.

**What wakes the agent.** Only `external` changes (`broker_recovery.py:94, 152-153`). `wake_for_activity` (157-243) wakes the attributed agent (not paused, not `delegated`; 179-186) with trigger `broker_event` and fixed text (213-219), or the personal agent with `authority: observe_only` (221-231). A close that the agent's own confirmed order caused wakes nobody and leaves no "closed trade" record. A position opened and closed between two reads never appears in a diff. Server-authored triggers are listed in `AR/context/routine.py:13-15`.

**Existing review or performance records.**
- Decisions and theses: `market_decision_record`, `market_opportunity_*`; last 3 decisions and 3 active theses are shown at build (`AR/context/decisions.py:11-63`). 14.2.5 removes the entry-thesis gate (`TRD/execution.py:472-474`, `TRD/opportunities.py:204-224`, one entry per thesis at 216-217) and keeps opportunities as memory.
- `market_performance_read` (`TOOLS/performance.py:33-34`, not eager): `TRD/performance.py:71-137` scans 1,000 journal rows; `monetary_pnl` is always `None` (57-58); groups are keyed by symbol only in practice (115-125); a `strategy_version` filter returns nothing (88-91); sample below 20 is `insufficient_data` (12, 53). Route `apps/api/src/lonora_api/routes/performance.py:14-37`. No per-label or per-strategy money statistics exist anywhere.
- Self-review: none. No code writes a review; `MEMORY.md` is free text (`TOOLS/memory.py:42-46`).

**Where a judgment label can live.** `TradeRequest` (`packages/contracts/src/lonora_contracts/trading.py:14-38`) is `extra="forbid"` (`domain.py:16-17`) and is hashed whole by `trade_fingerprint` (`TRD/idempotency.py:5-12`); the tool derives the operation id from a hash of all arguments (`TOOLS/trade.py:765`). The journal row keeps a server-written record beside the request at `result.details.execution` (`TRD/execution.py:265-287`: run, agent, provider, grant, goal ids). Approval rows keep `requests` as a list of `TradeRequest` payloads (`DB/schema.py:880`).

**Weekly market close.** `MKT/sessions.py:28-29` (`FX_WEEK_ZONE = "America/New_York"`, 17:00), `fx_week` (93-102), surfaced by `market_sessions`. No scheduler uses it.

**Reports.** No weekly report and no morning brief exist (`grep` for weekly/brief finds nothing outside market bars). Routines run through `packages/automation/src/lonora_automation/runner.py:6-20` and `DB/routines.py:195` (trigger `routine`).

---

## 4. Methods and skills (5.5.5, 5.6)

| Thing | Stored | Versions | Revert today |
|---|---|---|---|
| Agent instructions | `AgentRow.instructions`, 16,000 chars (`packages/contracts/src/lonora_contracts/domain.py:36, 67`); in the system role when the owner wrote it, as labelled data when another agent wrote it (`builder.py:102-110, 219-226`; `DB/agent_creation.py:61-73`) | none (row `version` only) | none |
| Operating notes `# OPERATING.md` ("your own working method", `lonora.md:455`) | section of the agent's one memory row (`DB/schema.py:457-464`; views in `packages/memory/src/lonora_memory/profile.py:16-64`); sent as labelled data, priority 82 (`AR/context/memory.py:167-178`) | every commit writes a `MemoryRevisionRow` with previous and new text, author, run, message (`DB/memory.py:118-207`; `DB/schema.py:490-523`) | owner only, HTTP `POST /memory/revisions/{id}/revert` (`apps/api/src/lonora_api/routes/memory.py:168-179`); it **undoes one change** by a line-level undo and fails with `memory_revert_conflict` when later edits touch the same lines (`DB/owner_profile.py:412-441`). No "restore version N", no agent or Lonora path |
| `# MEMORY.md` | same row and revisions | same | same |
| Skills | `SkillRow` + `SkillVersionRow` for every create and update (`DB/skills.py:19-62`; `DB/schema.py:701-715`) | yes | owner: `GET /skills/{id}/versions`, `POST /skills/{id}/restore` saves version N as the next version (`apps/api/src/lonora_api/routes/agent_skills.py:125-152`). Agent: `skill_package_control` `rollback` to a retained package version, always disabled (`AR/skills/lifecycle.py:480-493`) |

- Agent-authored skills need the workspace: `skill_package_create` takes a directory at an exact workspace revision with an adaptation review (`lifecycle.py:332-385`), starts `disabled_pending_validation` (326), and needs `skill_package_validate` + `skill_package_control activate` (452-501). There is no one-call "save this text as my skill".
- Memory guard: `packages/memory/src/lonora_memory/guard.py:14-40` refuses OPERATING.md and USER.md writes that contain phrases such as "without approval", "authorized to trade", "full trading authority", "ignore the limits/rules" (applied at `packages/memory/src/lonora_memory/edits.py:305-338`; tests `tests/test_owner_profile.py:239-278, 502-548`). An owner strategy that says "add the second position without confirmation" cannot be saved as a method today. Agent creation refuses such a responsibility too (`AR/collaboration/agent_create.py:54-55`).
- A file from the owner: upload accepts any type up to 20 MB (`apps/api/src/lonora_api/routes/artifacts.py:29-62`). The run sees only "Artifact <id>: <name>" plus the text of `text/*` and JSON files, 24,000 chars (`AR/context/attachments.py:24-54`), and images. `artifact_read` returns text for `text/*` and JSON only (`TOOLS/artifacts.py:203-236`). No PDF text extraction exists (no PDF library in any `pyproject.toml`; PDF appears only as an inline preview type, `routes/artifacts.py:174`), and no tool copies an artifact into the workspace (`TOOLS/workspace.py:82-117`). **A PDF strategy cannot be read by an agent today.**

---

## 5. Trading code (5.7)

- Bans: `RES/constitution/identity.md:1` (decline in one line), `RES/prompts/genui_v2.md:5`, `lonora.md:16` ("a coding assistant"), `lonora.md:586-587` ("An isolated command has no network, broker credentials or financial authority", "never ask analysis code to trade"), `lonora.md:160, 571`.
- What happens when an agent is asked for an Expert Advisor: the constitution tells it to decline and offer analysis, a watch or a skill. The GenUI decision evaluation scores a fenced code answer as a violation: `scripts/genui_eval/score.py:426-427`, cases `tests/fixtures/genui_decision/cases.jsonl:64` (H06, MQL5) and `:69` (H11, Pine Script), asserted in `tests/test_genui_decision_eval.py:253-254`, documented in `docs/genui-decision-eval.md:376`.
- Workspace today: `workspace_execute` is "networkless", no credentials (`TOOLS/workspace.py:114-117`); Phase 4 replaces it.
- Deployment records: none. No table, contract or tool (`grep -i deployment` finds only MetaApi and server settings). Broker history rows omit magic number and comment (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:763-776` keeps id, orderId, positionId, symbol, type, entryType, volume, price, profit, commission, swap, clientId), so trades of deployed code cannot yet be told apart in a report.
- Related text: backtesting is forbidden in three chapters (`lonora.md:224, 584, 643`) and pinned by `tests/test_backtesting_excluded.py:75-109`. Section 17 carries over only "no backtesting or simulation gate".

---

## 6. Voice (5.3) and rules on judgment (5.1, 5.2)

### 6.1 Disclaimers, hedging, refusals, reassurance

- `RES/bootstrap/SOUL.md:3` "I am Lonora, a persistent trading teammate" (sent to every agent, whatever its name); `:9` "never fake confidence"; `:10` "Stay friendly and curious - I'd rather ask a good question than guess wrong".
- `lonora.md`: 15 ("not through grand claims about ... profitability"), 24-25, 32 ("inflated certainty"), 107 ("Sizing estimates do not guarantee maximum loss"), 116 ("Never promise profits, safety from loss, guaranteed fills ..."), 139-140, 234 ("never ... a guaranteed loss ceiling"), 250 ("rather than giving unsupported BUY/SELL advice"), 371, 576, 631, 641-642, 644-645 ("A positive return does not prove correctness or future performance"), 648.
- `permissions.py:180` "A profit target is an objective, never a guarantee or reason to force a trade"; `permissions.py:125-131` ("You may not open, close, modify or cancel").
- `RES/constitution/trading-policy.md:1, 7`; `tool-policy.md:3, 15`.
- Skills: `RES/skills/trade-management/SKILL.md:54` "Never promise profit."; `market-analysis/SKILL.md:66` "guaranteed returns"; `lonora-design/SKILL.md:83` "Never promise returns."; `position-management/SKILL.md:15-16`.
- Tool descriptions: `TOOLS/position_sizing.py:25-29` ("not a maximum-loss guarantee and authorizes no execution"), `TOOLS/performance.py:34` ("small samples remain insufficient, returns are not profit/correctness"), goal_create ("Do not promise profits"), and 40 of the 126 tool descriptions state that the tool grants no authority or does not authorize execution (trade, market, chart, skills, tasks, collaboration modules; counted by matching "authorit|authoriz|grants no|never trades" on the live registry). 5.8.2 moves procedure into descriptions, so these suffixes are the budget to reuse.
- Context notes: `AR/context/memory.py:23-47`, `AR/context/decisions.py:31-35`, `AR/context/environment.py:80`, `packages/adapter-kit/src/lonora_adapter_kit/context_sections.py:21-26`, `RES/prompts/run_context_summary.md:16-18`.
- `RES/bootstrap/USER.md:29` "Risk preference: (context only; never execution permission)" (never sent).

### 6.2 Fixed rules on the agent's trading judgment

| Rule | Where | Owner phase |
|---|---|---|
| position, pending, volume, spread, drift, risk caps | `TRD/exposure.py:53+`, `ExecutionPolicy` | 3 (14.2.2) |
| money limits | `TRD/risk_limits.py` | 3 |
| one entry per confirmed thesis, direction must match | `TRD/opportunities.py:214-223` | 3 (14.2.5) |
| **identical arguments in one run are one operation**: a second identical buy returns the first receipt and sends nothing | `TOOLS/trade.py:765`, `TRD/execution.py:162-168`; pinned by `tests/check_simple_lonora.py:789`, `tests/check_trading_restrictions.py:574` | open (Q3) |
| the same effect call at most 5 times in a run, then halt | `AR/tool_guardrails.py:68-71, 240-257`; `tests/test_tool_loop_execution.py:807` | open (Q3) |
| "Never silently increase lot size, remove a stop" | `lonora.md:343` | 5 |
| "If a request is rejected, do not try another size or price without new intent/confirmation" | `lonora.md:367` | 5 |
| "A watch ... is not automatic permission to trade"; "Watch detection must reawaken analysis and revalidation before a financial action" | `lonora.md:241, 440`; `market-watch/SKILL.md:18` | 5 |
| "Do not immediately restore a previous stop, size or position after an owner change" | `lonora.md:313`; `position-management/SKILL.md:15` | 5 (ownership rules of 3.3.4 replace it) |
| "Do not alter safety rules or authorize higher risk based on a performance score" | `lonora.md:648` | 5 (contradicts 5.2 sizing and 5.5.4) |
| card-send taint follows watches, routines and tasks and turns trades into approval cards | `DB/genui_taint.py:1-17`, `MKT/watchers.py:666-672` | 2/3 (6.10) |

Nothing in the prompt, the skills or the tool descriptions teaches scaling in, secure-then-add, several concurrent positions, partial profit, trailing or early exit. `lonora.md:251` and `trading-policy.md:1` ("The model owns interpretation, timing, sizing and management within current authority") are the only positive statements.

### 6.3 Existing honesty guards (keep)

- "Never claims an execution the broker has not confirmed": a turn that proposes a financial call has its text emptied (`AR/model_runtime.py:228-231`); an unverified confirmed result replaces the text with a fixed sentence (232-235; `AR/context/financial_result.py:70-126`); wait prose is replaced by the known outcome (236-241; `financial_result.py:129-214`); streaming stops on an effect claim (`AR/public_stream.py:11-19, 47-51`); the uncertain-outcome line is appended (`AR/uncertain_outcome.py:37-38, 154-181`); only verified broker ids are public (`financial_result.py:12-67`). Tests: `tests/test_wait_update_financial_truth.py`, `tests/test_public_stream.py`, `tests/test_uncertain_outcome.py`, `tests/test_capability_exposure.py:161-250`.
- "Never states a profit the account does not show": only inside cards. v2 cards show market and account values through `@Fact` bound to a tool call of this turn (`genui_v2.md:9`; `AR/genui_compile.py:455-477`); v1 observed values need `fact` references (`native_visual_response.md:32`; `AR/visual_response.py:300-314`). **Plain text has no guard**; only the offline scorer checks "unbacked_claim" (`scripts/agent_eval/score.py:71-116, 317-331, 399`; `tests/test_agent_eval.py:135-150, 304`).

---

## 7. Built but switched off in this area (section 13)

| Item | Evidence | Suggested outcome |
|---|---|---|
| 6 playbooks | validated at build only (`AR/skills/registry.py:199-212`); never sent to a model; bodies are two generic lines each (`RES/playbooks/*/PLAYBOOK.md:3-4`) | `autonomous-trading-goal` is deleted by 14.2.4. For the other five: either load them as skills or delete as superseded by the skills that name the same work. Owner decision (Q11) |
| 5 prompts never loaded | section 1.4 | delete: the constitution files replaced them (13.2 allows it) |
| `RES/references/metaapi/operations.md` (2 lines) | shipped (`pyproject.toml:94`), no reader | fold into the Phase 8 broker text or delete |
| bootstrap `USER.md`, `MEMORY.md` | hashed, never sent (`system_policy.py:46-53, 100-106`) | use as the seed of a new agent's memory, or drop from the manifest |
| built-in skills with `activation.mode: automatic` + intents | the runtime passes `intents=frozenset()` (`AR/context/skills.py:200`), so intent selection (`AR/skills/resolver.py:108-109`) never fires. Only `market-watch` loads by itself (on a run with trigger `watch`); the other 8 (7 automatic, `lonora-design` explicit) load only when the model calls `skill_view` or the owner's text names `[skill:<id>]` (`AR/context/skills.py:177-189`) | decide per skill; fold the trading ones into the rewritten prompt and descriptions |
| `market_performance_read` money result | `monetary_pnl: None` always (`TRD/performance.py:57-58`); not eager | rebuilt on the closed-trade ledger (step 4) |
| economic calendar | off until the owner adds an integration; table `ln_economic_calendar` and `EconomicCalendarRepository` have no reader or writer (`DB/schema.py:799-800`, `DB/economic_calendar.py:5-9`) | use the table as the calendar cache (step 7) |
| `consult_model`, opportunities, relationships | registered, not eager, described only in `intelligence` | keep; mention in descriptions |
| GenUI v2 prompt and teaching variants | `visual_policy.py:21-29` | Phase 2 |

---

## 8. Tests in this area

| Test | Pins | Fate |
|---|---|---|
| `tests/test_system_policy.py:52-76` | 300-700 lines; chapter set including `goals` (65) | edit with each chapter removal |
| `:79-87` | exporter output equals the files | keep; regenerate |
| `:106-131` | core contains "Stop new trading", "Ambiguous", "typed approval", "exact-symbol", "Do not expose credentials", "free-text" (109-118); sizes | "typed approval" and "exact-symbol" pin governance wording: replace with the section 6 sentences that stay |
| `:158-192` | market and trading are seeded; 3-chapter rule | keep |
| `:214-224` | voice surface contains "Spoken agreement is not financial approval" (221) | rewrite for Full/Ask (6.10) |
| `:283-300` | resumed checkpoint gets the new core; phrases at 293-295 | keep the mechanism, update phrases |
| `tests/test_skill_runtime.py:39-52, 64-75` | intent selection incl. `trading-goal`; 6 playbooks; 7 constitution blocks; "Stop new trading" present; 9 skills | counts change (14.3.12) |
| `tests/test_teammate_runtime.py:98-110` | two SOUL sentences in the core; every skill has "## Steps" and "## Output" | update with SOUL and skill rewrites |
| `:267-268`, `tests/test_capability_exposure.py:932-942`, `tests/test_conversation_conveniences.py:211` | manifest equals registry | keep; regenerate |
| `tests/test_capability_exposure.py:945-974` | capability family to chapter (`"goal": "goals"`, 963) | Phase 3 |
| `tests/test_agent_permissions_enforcement.py:236-321` | ladder snapshot, "not your analytical freedom", "never a guarantee" (248-249), Resume-card wording (296-300) | **asserts removed behavior**; replaced with mode + Stop frame tests (Phase 3, wording in Phase 5) |
| `tests/test_trading_restrictions.py:477-483`, `tests/check_trading_restrictions.py:302, 546`, `tests/check_full_delegation.py` | restrictions and limits in the frame | removed with the features (Phase 3) |
| `tests/test_full_management_tool_guidance.py:9-39` | `trade_execute` description says "active signed account grant"; personal scope text | **asserts removed behavior** |
| `tests/test_backtesting_excluded.py:75-109` | the ban sentences in `intelligence`, `files`, `market` | text assertions go if Q10 is answered "no gate only"; engine-absence test (62-72) can stay |
| `tests/test_genui_decision_eval.py:253-254`; `cases.jsonl:64, 69`; `scripts/genui_eval/score.py:426-427` | code answer is a violation | **asserts removed behavior** (5.7.1); recordings under `tests/fixtures/genui_decision/recordings` carry a prompt hash and need re-recording |
| `tests/test_performance_summary.py:21-32` | `monetary_pnl is None`, "insufficient_data" | replaced with ledger statistics tests |
| `tests/test_owner_profile.py:239-278, 502-548`; `tests/test_owner_intent.py:144-165` | memory guard refusals | authority part changes (Q7); disclosure part stays |
| `tests/test_manual_activity.py:63-129`, `tests/test_proactive_wakes.py:108-165, 659-860` | close detection, attribution, wake of the opening agent, paused agent falls back to the personal agent | keep; extend for own closes; the paused case changes (4.7) |
| `tests/check_simple_lonora.py:789`, `tests/check_trading_restrictions.py:574`, `tests/test_tool_loop_execution.py:807` | identical order in a run is one operation; 5 identical effects | see Q3 |
| `tests/test_tool_discovery.py:165-172` | eager schema budget | keep; every new tool argument costs budget |
| `tests/test_wait_update_financial_truth.py`, `test_public_stream.py`, `test_uncertain_outcome.py`, `test_agent_eval.py` | honesty guards | keep unchanged |
| `scripts/check_policy_distribution.py:92` | 7 constitution blocks | keep unless a file is merged |
| `tests/check_skills_versioning.py`, `tests/check_memory_provenance.py` | skill versions, memory revisions | extend for restore-to-version |
| `docs/agent-operating-policy.md` (134 lines) | documents budgets and the exporter | rewrite in the prompt change (0.4) |

Core regression tests of 14.1.2 are not touched by any Phase 5 step except through `TradeRequest` handling in step 3; run them after every step.

---

## 9. Gap list per clause

| Clause | State | Notes and files |
|---|---|---|
| 5.1 the model decides | partly | Text agrees in places (`lonora.md:79, 251`; `trading-policy.md:1`), but caps, limits, thesis gate (Phase 3) and section 6.2 rules above still decide. Phase 5: prompt and description text; Q3 |
| 5.2 entry: enter, wait, skip | exists | `market_decision_record` (WAIT), `lonora.md:251` |
| 5.2 scaling in; several concurrent positions | missing | not taught; blocked by caps (Phase 3) and by the one-operation rule for identical arguments (`trade.py:765`) |
| 5.2 secure, then add; management | partly | tools exist (`trade_execute` modify, partial close; `tightened_stop` notice `TOOLS/trade.py:603-646`); not taught; `position-management` skill never auto-loads |
| 5.2 sizing | partly | `market_position_size` helper (`TOOLS/position_sizing.py:23-31`); agent never sees its own results in money |
| 5.2 portfolio awareness | missing | no picture (section 2) |
| 5.2 timing | exists | `market_sessions` (eager for market), calendar tool when configured |
| 5.2 self-scheduling | exists | `watch_create/update/cancel`, `task_wait`, `routine_create` (`lonora.md:438-442`); wording at 241, 440 discourages acting on the wake |
| 5.3.1-2 voice | missing | section 6.1; no evaluation condition for disclaimers or refusal of a view |
| 5.3.3 honesty | partly | execution claims guarded in code (6.3); profit claims in text unguarded |
| 5.4 full picture | missing, except Stop | section 2; must also reach Task wakes (`loop_restore.py:91-114`) |
| 5.5.1 closed trade | partly | snapshot diff, external causes only, misses fast open-close; no record |
| 5.5.2 self-review | missing | wake exists for external closes only; no review step |
| 5.5.3 judgment label | missing | storage slot defined by 14.3.9; none today |
| 5.5.4 statistics | missing | `performance.py` has no money and no labels |
| 5.5.5 versions | partly | memory revisions and skill versions exist; `agent.instructions` has none; revert is owner-only and (memory) undo-one-change |
| 5.5.6 weekly report | missing | depends on the Phase 7 brief |
| 5.6 owner methods | partly | messages and text files work; PDF and other binary files unreadable; guard refuses some strategies; heavy skill lifecycle |
| 5.7.1 writing code | missing (banned) | section 5 |
| 5.7.2 code runs through `lonora trade` | missing | Phase 4 |
| 5.7.3 deployment record, report, one-time notice | missing | nothing exists |
| 5.8.1-2 rewrite, delete governance | missing | section 1.2 |
| 5.8.3 identity line | missing | `lonora.md:16` |
| 5.8.4 code bans | missing | `identity.md:1`, `genui_v2.md:5` |
| 5.8.5 trading-policy.md | missing | section 1.4 |
| 5.8.6 manifest | exists (mechanism) | exporter and checks, section 1.3 |
| 5.8.7 mode + Stop every turn | partly | refresh mechanism exists (`team.py:114-130`); content is the ladder |
| 14.2.8 | missing | governance chapters and `permissions.py` |
| 14.3.9 label beside the request | missing | see Q2 |
| 14.3.12 | mechanism exists | two `pyproject.toml` lists, `test_skill_runtime.py`, `test_capability_exposure.py`, manifest |
| §17 | exists | no rule engine; Arabic first (`lonora.md:59`); no raw ids (41-55); status line `DB/trading_readiness.py` (rewritten by 14.3.17); durable runs. The backtest ban is stricter than §17 (Q10) |

---

## 10. Design questions the mandate leaves open

**Q1. What is "the method" (3.1.2, 5.5.5, 5.6, 14.3.18.4)?** (a) `AgentRow.instructions`; (b) the `# OPERATING.md` section; (c) a new document. Recommendation: (b). It is already described as the agent's own working method, already versioned and attributed, private to the agent, and lives in the memory store (3.2.4). Larger procedures become skills. Needed: a "restore version N of the method" operation (new revision whose OPERATING.md text equals that revision's, MEMORY.md untouched), available to the owner, Lonora and the agent; a higher context priority than memory; `agent.instructions` stays the owner's own short brief.

**Q2. Where is the label stored and what may it contain?** (a) a field on `TradeRequest`, excluded by hand from `trade_fingerprint` and from the id hash; (b) a separate "intent" object `{reason, tolerance, label}` beside the request: a nullable JSON column on `ln_trading_journal` and on approval rows, written at reservation. Recommendation: (b). `TradeRequest` and every stored payload stay unchanged, so fingerprints of unresolved rows cannot move (14.3.9 by construction). Phase 3 creates the object for reason and tolerance; Phase 5 adds `label`. The tool must strip the three fields before `request_hash(args)` (`trade.py:765`). Label format: optional slug `^[a-z0-9_]{1,40}$`, examples in the tool description, no fixed list (5.2 "never rules"). Missing label counts under `unlabelled`. A slug can safely appear in system-role frames; free text cannot (6.10).

**Q3. A second identical order in the same run.** Today it is the same operation and nothing is sent (section 6.2). With the label and reason excluded from the id, an agent cannot open two equal positions in one run. Options: (a) leave it; (b) derive the id from the tool call id (weakens the protection against re-issuing after an uncertain result); (c) add an optional agent-chosen `key` to `trade_execute`, with the CLI meaning of 7.3.5, and mark a replayed receipt `replayed: true` so the agent never reports two positions. Recommendation: (c), and raise or scope the 5-identical-effects halt for financial tools that carry different keys. Needs the owner, because it touches 6.2.

**Q4. Which P&L belongs to which label?** A position has an opening label and later management labels. Options: (a) the whole realized P&L of a closed position counts once under the label of the order that opened it; (b) each closing deal counts under the label of the order that closed it; (c) both views. Recommendation: (a) as the statistic of 5.5.4, plus a count per management label without money. Realized P&L = sum of profit, commission and swap of the broker deals of that position (`metaapi.py:758-785`; helper `deal_pnl`, `TRD/risk_limits.py:303-321`), per account currency, never summed across currencies.

**Q5. How is a close detected, and is the agent woken for its own close?** Detection options: (a) snapshot diff as today; (b) broker deal history since a stored cursor (an exit deal and no remaining volume). Recommendation: (b) for the ledger, keeping (a) for activity events; it survives restarts and fast trades. Wake options: (a) always start a `broker_event` run for the position's owner; (b) when the closing operation's own run is still active, give that run the same fixed server text instead of a second run. Recommendation: (b), with (a) for every other cause (stop, target, owner, Lonora, margin). Tickets owned by the owner (3.3.4) create a ledger row without label statistics and no agent review. The review is asked for by fixed server text naming ticket, label, P&L and duration, with one bounded reminder when the run ends without a memory write; a run is never failed for it.

**Q6. Where and when is the full picture built?** (a) live broker reads on every model turn; (b) once per wake from the stored reconciliation snapshot, with its `observed_at`; (c) per turn from the snapshot. Recommendation: (b) for positions, team and calendar, as one bounded message that is replaced on every wake, including `consume_wake`; mode and Stop stay in the per-turn routing frame (5.8.7). It must be mandatory (not `runtime_context`, which admission may shed, `packages/adapter-kit/src/lonora_adapter_kit/context.py:235-246`) and bounded (largest tickets first, a count for the rest). Symbols and event names are third-party strings: encode them as data (`team.py:20-22`).

**Q7. Memory guard and owner strategies.** Options: (a) keep; (b) drop the authority patterns, keep the disclosure patterns; (c) drop all. Recommendation: (b). The guard is "defence in depth, not enforcement" (`guard.py:8-9`); mode is enforced at the door.

**Q8. Calendar source.** The frame needs events on every wake, but a source exists only when the owner configured a URL in Lonora's own JSON shape, and impact is a free string. Options: (a) owner-configured source only, frame says "calendar not connected" otherwise; (b) ship a default public source; (c) the news agent maintains it from the workspace. Recommendation: (a) now, a gateway step that caches events in `ln_economic_calendar`, impact normalised to low/medium/high, and Lonora offering to connect a source (P6). Which default source to ship is an owner question.

**Q9. PDF to method.** (a) extract text on upload on the server; (b) pass the file to models that read documents; (c) the agent reads it in the workspace (Phase 4) through an artifact-to-workspace bridge. Recommendation: (c) as the general path (P3) plus (a) for a plain text layer, so that a wake without a workspace job still sees the strategy. Scanned PDFs go through page images and the existing image observation path.

**Q10. Backtesting text.** §17 says "no backtesting or simulation gate"; today's prompt forbids building or running one. With a free workspace the ban is a rule against section 7. Options: keep the ban; or keep only "Lonora never requires or offers a backtest as a gate". Recommendation: the second. Owner question, because it reverses an earlier explicit exclusion.

**Q11. Playbooks and unloaded prompts** (13.1 "on or completed" against 13.2 "deleted only when replaced"). Recommendation: unloaded prompts are replaced copies, delete; playbooks carry no instruction beyond their skills, delete with the owner's confirmation, else load them as skills.

**Q12. Weekly report trigger and silence.** "First morning brief after the weekly market close" needs Phase 7. Options: (a) a server trigger per agent, fired by the brief dispatcher after `fx_week` closed (Friday 17:00 New York for every instrument); (b) an agent routine. Recommendation: (a), with an interim fixed time (07:00 owner time, first day after the close) until the brief exists. An agent with no closed trade that week still posts one line (5.5.6 says "each agent"); confirm with the owner against 11.5.

**Q13. Deployment record.** Recommendation: a tool the agent calls after deploying (target name, account, file hash, magic number), accepted only in a run that carries the owner's message (`owner_message_id`), stored in a new table; the one-time notice is fixed server text keyed per deployment; the report filters broker history by magic number, which needs `magic` and `comment` added to the history fields (`metaapi.py:763-776`). Open: an account that is not connected to Lonora cannot be reported.

**Q14. Voice enforcement.** Prompt plus evaluation, or a runtime filter. Recommendation: no runtime rewriting of model text. Add scorer conditions (disclaimer, reassurance, refusal of a view, profit not shown by a tool result) to `scripts/agent_eval/score.py` and scenarios to its bank.

**Q15. Where the judgment kinds are taught.** Core (always), the seeded `trading` chapter, a skill, or tool descriptions. Recommendation: a short "trader's judgment" part in the core (about 1,200 chars, each kind one line, stated as options), mechanics in the `trade_execute` and `watch_create` descriptions, within the 26,950 schema budget.

---

## 11. Ordered steps (each one pull request)

Every step that edits `lonora.md` or a bootstrap file runs `scripts/export_agent_tool_reference.py`, updates `tests/test_system_policy.py`, and (when a file is removed) both `pyproject.toml` lists. Prompt lines for a feature land in the step that builds it (0.4).

| # | Step | Depends on | Done when |
|---|---|---|---|
| 0 | **Before Phase 3 deletes `risk_limits.py`**: move `deal_pnl` and the deal-type sets to a surviving module (`TRD/realized.py`). No behavior change | nothing; must precede 14.2.2 | core tests pass; `risk_limits` imports it |
| 1 | Prompt pass A, voice and judgment: rewrite `core` Identity and Public voice (line 16 per 5.8.3), delete the governance lines Phase 3 left, add the judgment part, rewrite `trading-policy.md`, `tool-policy.md:5`, `SOUL.md`, the trading skills' wording, tool-description suffixes; fix the chapter-freeze for checkpoints (refresh the constitution block like the core, or bump the checkpoint so old Tasks rebuild); add voice conditions to the agent evaluation | Phase 3 (mode, Stop, removed features), Phase 4 for any workspace sentence | no sentence in section 6.1 remains; manifest check passes; core below 16,000 with at least 1,500 chars free |
| 2 | Closed-trade ledger: table, detector from deal history, owner attribution, realized P&L | step 0; Phase 3 ownership (3.3.4) | every close of the test broker creates exactly one row, also after a restart and for a trade opened and closed between two reads |
| 3 | Judgment label: `label` in the intent object and in `trade_execute`; excluded from id and fingerprint; ledger row copies the opening label; Q3 key if approved | Phase 3 (reason and tolerance storage), Phase 4 (`--label`) | test: two sends that differ only in label are one operation; an `ambiguous` row from before the change reconciles without resend |
| 4 | Statistics: per label count and net realized P&L per currency from the ledger; `market_performance_read` rebuilt on it; statistics block for the wake | steps 2, 3 | numbers equal broker history in a fixture; no `insufficient_data` wording |
| 5 | Full picture, own part: `AR/context/picture.py` from the snapshot (own positions, orders, exposure by symbol, floating P&L, realized today and this week, statistics), injected at build and at every wake including `consume_wake`; trim the mode + Stop frame wording | Phase 3 (frame replacement, ownership), step 4 | a Task wake after a new position shows it; size bounded |
| 6 | Team picture: all agents' tickets grouped by symbol and by currency (base and profit currency of each instrument) | Phase 3 ownership; Phase 6 (flat team; Lonora's whole-account role) | two agents on EURUSD and XAUUSD appear under EUR, USD, XAU |
| 7 | Calendar in the picture: cache step, impact normalisation, next 24 h for the picture's currencies, "not connected" line | step 6; Q8 | fixture source: only high-impact events of held currencies appear |
| 8 | Close wake and self-review: wake the owner for every close (Q5), fixed text, bounded reminder, review section in memory | steps 2, 4; Phase 3 pause rules (4.7); Phase 6 (deleted agent's tickets go to Lonora) | stop-loss hit and the agent's own close both end with a new memory revision |
| 9 | Method versions: restore-to-version for owner (route), agent and Lonora (tool); skill restore for agents; one-call instruction-only skill; guard change (Q7); `MEMORY`/`OPERATING` wording | Phase 6 for Lonora's access to another agent's method | 5.5.5 test: write, write, restore version 1, text equals version 1, history has 3 versions |
| 10 | Owner methods from files: artifact-to-workspace bridge and PDF text (Q9); the agent turns an uploaded strategy into its method or a skill and says where it saved it | Phase 4, step 9 | acceptance step 3: PDF upload ends with a method version quoting the strategy's rules |
| 11 | Trading code: delete the bans (`identity.md:1`, the code clause of `genui_v2.md:5`, `lonora.md:586-587`), flip evaluation cases H06 and H11, deployment record tool, table, one-time notice, history fields | Phase 4 (workspace, `lonora trade`, SSH, secrets), Phase 2 (`genui_v2.md:5` is also rewritten there) | agent writes an EA on request; a deployment creates one record and one notice |
| 12 | Weekly report: trigger after the weekly close, per-agent run in its own conversation with ledger statistics and method versions of the week; Lonora's summary | steps 4, 9; Phase 7 (brief), Phase 6 (Lonora reads agents) | acceptance step 7 |
| 13 | Dormant resources: unloaded prompts, playbooks, reference file, bootstrap templates, skill intents (Q11) | step 1 | every file under `RES` has a reader or is gone; data-file lists and counts updated |
| 14 | Acceptance harness for section 16 steps 3, 4 (break-even, partial profit) and 7, and `docs/agent-operating-policy.md` | all | scenario passes on a demo account |

Steps 2-4 touch no prompt text beyond their own lines and can start as soon as Phase 3's ownership lands. Step 1 should come first within Phase 5, because the core has 58 chars free and later steps add lines.

---

## 12. Risks to the safety core (section 6)

1. **Operation identity (6.2, 6.3).** Adding reason, tolerance or label to `TradeRequest`, or forgetting to strip them before `request_hash(args)` (`trade.py:765`), changes fingerprints and ids: an unresolved row then meets `idempotency_conflict` (`execution.py:162-167`) or, worse, a retry becomes a new operation. Keep them outside the contract (Q2) and add the 14.3.9 test before the change.
2. **Q3 key.** Any way to open a second identical order is also a way to resend after an uncertain result. The door's block on new risk for a market with an unresolved operation (`require_operation_scope`, `execution.py:221-228, 421`) must stay, and a replayed receipt must be labelled so that 6.4 holds in the reply.
3. **Picture is not broker truth (6.4, 6.5, 6.6).** The frame comes from a snapshot up to seconds old. It must carry `observed_at`, must never feed preflight, the stale-target check or `expected_target` capture in `TOOLS/trade.py`, and the "position closed" wake text must come from broker deals, not from the frame.
4. **Run integrity (6.9).** The close wake for the position's owner has full scope; a wake about a ticket the agent does not own must keep `authority: observe_only` (`broker_recovery.py:221-231`; `TOOLS/base.py:53-58`). Do not reuse one code path that drops the flag.
5. **Provenance (6.10).** Labels, symbols, calendar names, review text, an uploaded strategy and another agent's method are data. Only slugs and server text may enter system-role frames; methods stay in labelled data (`builder.py:219-230`). Team pictures show other agents' tickets, never their memory.
6. **Deleting safety sentences with governance.** The rewrite removes chapters that also carry section 6 text (`lonora.md:110-111, 346-366`). The code gates of 6.3 above do not depend on the prompt, but the model still needs: never resend an uncertain order, nothing is filled without broker evidence, a pending order is placed not filled. Keep them in the core and pin them in `test_system_policy.py` in place of the governance phrases.
7. **Fail-closed load.** An oversized core, a chapter over 4,666 chars, a stale manifest or a tool whose toolset has no chapter stops every agent run (`system_policy.py:72-85`), including the runs that manage open positions. `scripts/build.sh:7-10` must gate every prompt change; never edit the manifest by hand.
8. **Frozen constitution in checkpoints.** A continuous Task started before the deploy keeps the old ladder and code-ban text (section 1.1). Until fixed, the model reads two contradicting policies; the door still decides, so this is a behavior risk, not an execution risk. Fix in step 1.
9. **Trading code outside the door (6.1).** Removing `lonora.md:586-587` before Phase 4's isolation (7.1.4) and `lonora trade` exist would invite code that reaches a broker another way. Order step 11 after Phase 4. Tickets opened by deployed code on a connected account have no journaled order and are the owner's (3.3.4); the ledger must not attribute them to the agent.
10. **Statistics from evidence only (6.4).** Count only broker deals. Operations settled by the owner's attestation (`resolved`, `packages/contracts/src/lonora_contracts/trading.py:107-110`) are not broker confirmation and must not create profit numbers.
11. **Guard relaxation.** Dropping the authority patterns is safe only because nothing in execution reads memory; keep that true (no code may read mode, standing instructions or limits from OPERATING.md). The 3.3.4 standing instruction is an agent setting, not memory text.
