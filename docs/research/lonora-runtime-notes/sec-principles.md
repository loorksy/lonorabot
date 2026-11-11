## The sixteen binding principles: what exists, what is missing, where the change attaches

Code at main `9f5b1da`. OBSERVED = production trace (Part, run id). SCRIPTED = real runtime, scripted model; scripts in `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts` (`cp_*.py`, `p916_*.py`). Cost: S one file or function plus tests; M several files in a package; L several packages, new stored state or eval data. `[n]` = owner message.

**Path key.** `AR`=`packages/agent-runtime/src/lonora_agent`, `TL`=`packages/tools/src/lonora_tools`, `DB`=`packages/db/src/lonora_db`, `CT`=`packages/contracts/src/lonora_contracts`, `CO`=`packages/core/src/lonora_core`, `TR`=`packages/trading/src/lonora_trading`, `AD`=`packages/adapters/src/lonora_adapters`, `MK`=`packages/market/src/lonora_market`, `RES`=`packages/agent-runtime/resources`. A bare name is resolved in the order AR (including `context/`), TL, DB, CT, CO, TR; a name that exists in two places carries a prefix. RES/system: lonora.md. RES/constitution: trading-policy.md, tool-policy.md, identity.md. `OWNER_DECISIONS.md`=`docs/ui-reference/OWNER_DECISIONS.md`; `trading-safety.md`=`docs/trading-safety.md`.

### Summary

| # | Principle | Status | Exists today | Missing | Attaches at | Cost | Safe at once / owner |
|---|---|---|---|---|---|---|---|
| 1 | Resolution-first | FAILS | case-only match; suffix rule in `agent_create` only | shared resolver | registry.py:509-516; symbols.py:18-35 | M / L | reads safe; money owner |
| 2 | Error contract, recovery | PARTLY | `recovery` block, transient retry | `class`, `hint`, `candidates` | environment.py:134-216 | S to L | safe |
| 3 | Act, do not offer | FAILS | prompt text; Task-only gate | chat gate | loop_outcomes.py:155-184 | M | reads safe; detector owner |
| 4 | Short approval executes offer | FAILS | `suggested_reply` unused | link to offer | history.py:135-173 | S / M | safe; expiry owner |
| 5 | Condition becomes trigger | FAILS | watch, `modify_position` | mapping, helper | market_binding.py:97-141 | S/M/L | default route owner |
| 6 | Defaults, one-card plan | FAILS | lonora.md:106 | default size | permissions.py:61 | S/M | size owner |
| 7 | No inability claim | FAILS | inventory lists tools | any check | loop_outcomes.py:155 | S/M | structural safe |
| 8 | No promise/done without result | PARTLY | financial gates | other claims, trial calls | loop_outcomes.py:155; tool_guardrails.py:277 | S to L | placeholders safe |
| 9 | Open requests durable | PARTLY | checkpoints, Tasks | offer record | agent_state.py:222 | S/M/L | read block safe |
| 10 | Owner scope | FAILS cancel; PARTLY pause | `control_work` pause | owner-wide list, cancel | DB/supervision.py:629-749 | M | money Task owner |
| 11 | Live reads for status | PARTLY | live tools | gate | tool_dispatch.py:22 | S/M | safe |
| 12 | Reply guard | FAILS | redaction, `EFFECT_CLAIM` | codes/names check | loop_outcomes.py:155 | S/M | blocking owner (conflict) |
| 13 | Answer asked | PARTLY | levels in `market_snapshot` | shape text | RES/skills/market-analysis/SKILL.md:58-66 | S | safe |
| 14 | Remember learned | FAILS | nothing | map, write | symbols.py:18 | M | policy lines conflict |
| 15 | Owner's language | PARTLY | `reply_language`, empty | default, voice rule | context/memory.py:131 | S/M | confirm pin |
| 16 | Strength is not bypass | HOLDS | single executor | test | none | S | none |

### Shared facts

**Reply path.** `model_turn` cuts `<suggested_reply>` (model_runtime.py:195), runs financial-truth gates on `FINANCIAL_CALLS` only (`:218-238`), then redaction (`:246`); `:239-241`: "Style is model guidance, never a second generation or a failed user request." `final_answer` (tool_loop.py:595-611) asks `task_stop_gate` (loop_outcomes.py:170), which without a Task returns at once (stop_gates.py:153-155,180-181), then adds the uncertain line (loop_outcomes.py:179-183). `finish_turn` (tool_loop.py:223-322, call `:299`) and the silent final (tool_block.py:394-412) bypass it.

**PR #42 (`aa50e8e`): why the guards recorded nothing.** Its only runtime check is the uncertain-outcome line: "Structured results only: no wording of the owner or the model is read." (uncertain_outcome.py:3), three tool names (`:23`), "The reply and its card are never replaced" (`:9`); it also added trading-policy.md:7, which names `watch_cancel`. For `ddae66ad`, `e343c96a`, `fb1d4b5a` no check in stop_gates.py or the PR #42 files was in scope: `task_stop_gate` needs a Task (stop_gates.py:153-155) and is structural even then (`:99-104`); nothing reads reply text (SCRIPTED replay, `cp_guards.py`: nine production replies committed unchanged). «لا أقدر أدّعي الإلغاء بدون رد أداة ناجح» in `fb1d4b5a` was the model reciting trading-policy.md:7.

**Builds and tools.** All builds of the conversation contain PR #42; [72]-[81] ran on `9f5b1da`; since `aa50e8e` tool_dispatch.py, environment.py, stop_gates.py, loop_outcomes.py, symbols.py are unchanged. The model was offered the same 23 native tools in every run; `watch_list`, `watch_cancel`, `watch_pause`, `watch_update`, `trade_close_positions`, `market_symbols` are registered but not among them (SCRIPTED `cp_principles.py`). 36 calls, 34 ok.

**Constraints.** Money: the executor re-reads grant, trading switch, restrictions, limits and unresolved operations at send (trading-safety.md:7-9); exits stay allowed (`:18`); "spoken or typed agreement is not approval" (trade.py:753-757). OWNER_DECISIONS.md:12 (no keyword router, no separate classifier call), public_reply.py:4 ("not a keyword veto on replies").

**Shared primitive (3, 5, 7, 8, 11).** "What this request did" exists only for three money tools: `record_request_start` stores `owner_started`/`owner_request_start` (uncertain_outcome.py:40-48; loop_restore.py:58) and `uncertain_operations` pairs calls with results (`:78-112`) over `FINANCIAL_EFFECTS` (`:23`); effect class is known per tool (`Tool.read_only/financial/poller`, TL/base.py:72-82). A per-request walker for all tools does not exist.

**Server updates.** Three (09:54, 10:23, 10:38 UTC) recreated the containers. Checkpoints are saved each step (tool_loop.py:117-126); OBSERVED run `57dcaeb0` waited eight seconds, nothing else lost (Part 2). No pending offer exists to lose; new state must live in the database or checkpoint, not memory.

---

### P1. Resolution-first: FAILS

**Exists.** No shared resolver. Account: exact connection id (AD/brokers/base.py:25-33); the Personal Agent has no bound account or symbol (Part 1 Q6; market_binding.py:44-79,89-90). Symbol: `market_instrument/quote/candles` case-only, raw name passed on (symbols.py:18-35); `market_snapshot`, `market_sessions` strict, `symbol_not_found` (market_analysis.py:140,215; OBSERVED `1ae9a14c`). Suffix matching and candidates exist only in `agent_create` (agents.py:72-135); SCRIPTED (`cp_principles.py`): `symbol_candidates("XAUUSD")` finds `XAUUSDm` while `catalog_symbol` raises; a fake `position_id` in `watch_create` is accepted (market_binding.py:133-140). Cause: the model sent `XAUUSD`; a non-candles 404 becomes `broker_account_not_found` (AD/brokers/metaapi.py:52-58).
**Missing.** Name-to-symbol, account lookup by login, default account, candidates in errors (`LonoraError` has only `code`, `status`, diagnostics, CO/user_error.py:1-14).
**Attaches (design is another session's).** `ToolRegistry.dispatch` runs `prepare_market_arguments`, `validate_arguments`, `guard_market_tool`, handler (registry.py:509-516); `prepare_market_arguments` is chosen by name prefix (market_binding.py:18,40-41,82-94); `canonical_broker_symbol`. **Cost** M reads, L all kinds.
**Conflicts.** "Exact broker symbols and owner/account scope are immutable server boundaries" (trading-policy.md:1); lonora.md:60,224; "Exact symbols are intentional. No hidden aliases or suffix stripping." (trading_decision.py:79). A wrong silent match on a money call moves money. **Safe/owner.** Reads and position check safe; money calls owner.

### P2. Unified error contract, bounded recovery: PARTLY

**Exists.** `observe` stamps failed results with `recovery` (environment.py:203-210) from `classify` (`:35-93`) (CT/tool_environment.py:27-33). **`classify()` categories, verbatim** (CT/tool_environment.py:9-24): `invalid_tool_arguments`, `result_too_large`, `temporary_unavailable`, `version_conflict`, `stale_state`, `authorization_required`, `permission_denied`, `not_configured`, `not_found`, `health_blocked`, `risk_limit_blocked`, `ambiguous_mutation`, `terminal_domain_failure`. SCRIPTED (`cp_classify.py`): every `*_not_found` code gives `not_found`; only `TRANSIENT_READ_CODES` (CO/runtime_failure.py:10-21) are retryable. OBSERVED (`1ae9a14c`): both failures reached the model with no candidates.
**Missing.** `class`, `hint`, `candidates`, `next_actions`; resolution-error recovery.
**Attaches (contract design is another session's).** `observe`; `dispatch_call` `except LonoraError` (tool_dispatch.py:110-117); category names are pinned by `tests/test_agent_environment.py:40-62,86`, so `class` is a second field. **Cost** S; M candidates; M to L resolution recovery (needs P1). **Conflicts.** Hints must never route around restrictions or risk limits (environment.py:62-63,70-73); financial calls are never retried (tool_dispatch.py:43-69). **Safe.** Yes.

### P3. Act, do not offer: FAILS

**Exists.** Prompt text only (tool-policy.md:3; lonora.md:120,135). A bounded continue mechanism exists for Task runs only: `StopGateVerdict`, two nudges per epoch, checkpointed counters (stop_gates.py:41-43,57-69,86-129); `final_answer` turns a verdict into a notice and returns `None` (loop_outcomes.py:170-174). SCRIPTED (`cp_count_offers.py`): 21 of 37 replies match an offer pattern (19 offers, 2 parameter questions).
**Missing.** An offer detector and a conversation gate (no offer wording in `packages/agent-runtime/src` or `packages/core/src`; only `EFFECT_CLAIM`, public_stream.py:11-19).
**Attaches.** `final_answer` (loop_outcomes.py:155-184): a second gate beside `task_stop_gate` (`:170`) for `is_conversational` runs (CO/run_state.py:33-34), checkpointed counter beside `_STATE_KEY`, reset by `reset_stop_gate` (stop_gates.py:66-69); `exhausted` must deliver the reply, not `request_owner_attention` (loop_outcomes.py:175-178). **Cost** M; L with corpus and eval.
**Conflicts.** Exclude `financial` steps (TL/base.py:73). Wording tension with public_reply.py:4 and OWNER_DECISIONS.md:12. **Safe/owner.** Read-only gate safe. Owner: which own-state steps are inside the delegation; a wording detector.

### P4. Short approval executes the pending offer: FAILS

**Exists.** `suggested_reply` (`RES/prompts/suggested_reply.md:2`, 60 characters), stored (DB/runs.py:336-387); question answers in the checkpoint (messages.py:528-552), shown in history as `<question_choices>` (history.py:135-173).
**Missing.** Nothing links a short reply to the offer (SCRIPTED S4: the model gets plain history only; no code for `pending_offer|open_request`). OBSERVED: read offers ran from plain history ([14]→[16]); own-state offers did not: [35] «أضع لك **أمر إغلاق مشروط** أو أتابعه لحظة بلحظة على هذا المستوى» → «طيب» → reads only; [75]→«جرب»→`watch_create`, not `watch_cancel`. UNSURE if the thumbs-up at [41], [43] reached the run.
**Attaches.** History loop (history.py:135-173); `restore_checkpoint` (loop_restore.py:31-65) plus `append_notice`; durable record at thread or message level. **Cost** S; M durable. **Conflicts.** Typed agreement is not approval (trade.py:753-757). **Safe/owner.** Reads and own-state safe. Owner: offer lifetime, thumbs-up, assent inside a grant.

### P5. Condition becomes a durable trigger: FAILS

**Exists.** `watch_create` supports `kind="position"`, `metric="profit"`, `condition="above"`, `level` (CT/market_watch.py:15,24,27-28,36-37,74,84-88); `modify_position` takes `stop_loss`/`take_profit` (CT/trading.py:18-29,54-66); OBSERVED [35]: both null, nothing set.
**Missing.** Nothing maps "close at +X" to either (no hit for `modify_position|kind=position|position_id` under `RES`). No money-to-price helper: `profit_tick_value` is parsed and declared (AD/brokers/normalize.py:57,65; CT/market.py:33), used by no code. No check that "I am watching" has a watch (OBSERVED `8114abdd`, `6e4aa88f`, `7e7da121`: no XAUUSDm watch existed; SCRIPTED `cp_guards.py`). `watch_create` accepts any prompt (market_watch.py:28).
**Attaches.** English guidance in text every chat run has: tool descriptions (market_watch.py:239; trade.py:753-769), tool-policy.md, core lonora.md:9-165; a pure helper; `guard_market_tool` position check; claim check = P8. **Cost** S text and check; M helper and claim check.
**Conflicts.** An order-sending watch would be a second money path (trading-safety.md:7-9). **Safe/owner.** Text, check, helper safe. Owner: default for "close at +$X".

### P6. Defaults, one-card plan inside the delegation: FAILS

**Exists.** Full delegation has no caps (CT/account_authority.py:27-34,37-49). Every chat run sees lonora.md:106 and "size and manage positions ... Matching actions need no repeated per-operation approval." (permissions.py:140-142). The explicit "do not ask for routine parameters already delegated" is only in `RES/skills/trade-management/SKILL.md:23-24` (skills are description-first, context/skills.py:198-200,239) and the Task prompt (`packages/auth/src/lonora_auth/account_authority.py:150`; chat context has no Task text, context/builder.py:100-175); lonora.md:136 ("Ask for owner preferences or missing financial limits; ...") reads as licence to ask. OBSERVED [24]: balance, quote and minimum 0.01 in hand, no trade call, size asked.
**Missing.** Any default size (no hit for `default_volume|default lot`); a check of a reply asking for a delegated parameter.
**Attaches.** `permission_guidance` (permissions.py:61), one English sentence; a default as data in `market_instrument` or `account_read`; the P3 gate; one card via `wait_for_input` (TL/runtime_control.py:22). **Cost** S; M default; M plan card plus eval.
**Conflict (flag).** Documents say no default is chosen for the owner: lonora.md:106 ("without ... default volume/activity quotas"), Q17/Q18 OWNER_DECISIONS.md:45-46 ("money_limit none"), unset limit "is not enforced" (permissions.py:165). A default size is a number the owner never chose and, with no limit, the only protection (must not enlarge scope, permissions.py:143-144). **Safe/owner.** Making the rule visible is safe. Owner: the size (suggest the instrument minimum).

### P7. No inability claim without evidence: FAILS

**Exists.** `tool_environment` (registry.py:155-166,336-397). The inventory in every request lists all 126 names (registry.py:406-473); the constitution names `watch_cancel` and `tool_call` (trading-policy.md:7); lonora.md:434 sits in a chapter added only after a `tasks` tool in the last 16 messages (AR/skills/system_policy.py:133-141).
**Missing.** Any check of an inability claim. OBSERVED: [71] zero calls; [75] «ما في أداة حذف ظاهرة» after one `tool_environment` query "watch cancel task routines goals" returning `{"tools":[],"total":0}` (Part 4 #76-77); [81] zero calls. Cause of the empty result (discovery session's): the lowest-frequency query token gates and drops every tool lacking it (tool_discovery.py:44-89, `:62,69-74`).
**Attaches.** `final_answer` with the request walk: any `tool_environment` call since `owner_request_start` and its `total`; stronger: non-empty result or full listing. **Cost** S; M with detector. **Conflicts.** None with money. **Safe/owner.** Structural safe; detector owner.

### P8. No promise or "done" without a tool result; no trial calls: PARTLY

**Exists.** Financial claims only: gates (model_runtime.py:218-238), uncertain line (uncertain_outcome.py:115-152). OBSERVED on main code: [63] three `watch_create` calls then «تم الإلغاء… أُزيلت»; [69] only `wait_for_input`, then «سأحذف…»; [77] trial `watch_create(enabled=false, prompt="cancel-test", ...)` created a watch (SCRIPTED `cp_guards.py`: replies unchanged, trial left a row).
**Missing.** Claim-versus-result comparison for non-financial effects (no reply pattern besides `EFFECT_CLAIM`, runtime_notices.py:84-93); request knowledge in `before_call` (tool_guardrails.py:277).
**Attaches.** `final_answer` with `uncertain_operations` (uncertain_outcome.py:78-112) widened from `:23` via `Tool.read_only/financial`; structural gate "option picked, no effect call since" from `input_requests` (messages.py:528-552); placeholder validation (market_watch.py:28). **Cost** M; L with promise detector; S placeholders. **Conflicts.** Never replace or suppress a reply after a financial effect (uncertain_outcome.py:9). **Safe/owner.** Placeholders and structural gate safe. Owner: wording detector.

### P9. Open requests durable: PARTLY

**Exists.** Checkpoint (tool_loop.py:117; loop_restore.py:31); question cards (messages.py:526-553); Tasks (schema.py:750); `agent_live_state` (agent_state.py:222): own Tasks and up to 6 enabled watches (`:339-354`); manual `retry_run` (run_retry.py:87-115); automatic retry only for transient model errors. OBSERVED: [69] promised «سأحذف…», never picked up again.
**Missing.** A record of an offer, promise or unfinished request surviving the run (grep for `open_request|pending_offer|commitment`: prompt text only).
**Attaches.** Read: `open_items` in `agent_live_state` or `build_context` (context/builder.py:55-302). Write: `final_answer` with `record_request_start`; a table keyed by thread (not `ThreadRow.options`, schema.py:239); items declared by the model in structure (model_runtime.py:195-201). Auto-resume would reuse `retry_run` (run_retry.py:93-103). **Cost** S read; M record; L auto-resume. **Conflicts.** An item is context, never authority; detect by structure (OWNER_DECISIONS.md:12). **Safe/owner.** Read block safe. Owner: auto-retry, lifetime.

### P10. Owner scope: FAILS (cancel/update across agents), PARTLY (pause, reads)

**Exists.** `control_work` pauses or resumes another agent's agent, Task, routine or watch, the Personal Agent on the owner's message (DB/supervision.py:629,658-663; `WorkAction = Literal["pause","resume"]` `:528`; no cancel, CT/supervision.py:16); the owner interface cancels anything with `agent_id=None` (`apps/api/src/lonora_api/routes/watches.py:41`, `apps/api/src/lonora_api/routes/tasks.py:59`). SCRIPTED (`p916_principles.py` 10.1-10.5): for another agent's objects lists are empty, cancel/update fail, pause works. One agent in production.
**`agent_id == context.agent_id` filters (READ; under `TL/` unless noted).**

| Tool | Line | Effect |
|---|---|---|
| `watch_list`, `watch_cancel/pause/resume`, `watch_update`, `watch_create` dedupe | market_watch.py:153-155; `:180` via market_watches.py:123; `:209,215`; `:45,77` | own only |
| `routine_list`; `task_inspect`, `task_control` | routine.py:46; tasks.py:51,57-58,69 | own; `task_agent_mismatch` |
| goals, opportunities, attention, artifacts, collaboration | trading_goal.py:93,129,158; opportunity.py:108; incoming_call.py:108; artifacts.py:69,139,207; collaboration.py:57,91 | own / host |
| trade approvals; run identity | trade.py:126,355-360; agents.py:232; models.py:239; owner_actions.py:207 | proposer's (money; keep); caller's run |

**Missing.** Owner-wide list; cancel/update across agents on the owner's message.
**Attaches.** `control_work` (DB/supervision.py:629-749): `cancel` in `WorkAction` (`:528`), `_apply` (`:590-626`), `AgentControlInput.action`; `control_watch` already says an agent "may still cancel it, which only narrows" (market_watches.py:155-157); route `watch_cancel`/`watch_update`/`task_control` through it as `routine_toggle` does (routine.py:58-60,80-102). **Cost** M.
**Conflicts.** `require_task_authority` refuses every trade of a run bound to a paused or cancelled Task (execution.py:129-141): cancelling a management Task removes its automatic exit. It does not revoke the grant: `stop_management_task` runs when a grant is replaced or revoked (`packages/auth/src/lonora_auth/account_authority.py:126`), not from `control_task` (DB/tasks.py:397); «ألغِ المهمة» must not read as revoking the mandate. **Safe/owner.** Owner-wide read and cancel on the owner's message safe. Owner: a Task holding money.

### P11. Live reads for status: PARTLY

**Exists.** Live: `account_read` (account.py:69-73), `market_quote` (stream price within 30 s, else RPC, AD/brokers/metaapi.py:676-701), `market_snapshot` (market_analysis.py:136-181). Quote, snapshot and evidence carry `observed_at`/`age_seconds` stamps (MK/snapshot.py:307,355; context/run_evidence.py:73-79,170-171). `live_agent_state` lists own enabled watches every turn, so «أراقب **XAUUSDm**» ([57]) contradicted it; [28] was answered with no tool call (OBSERVED).
**Missing.** A `live`/`cached` marker; a staleness limit; any check that a status reply followed a live read; 600-character result previews reach later runs (run_evidence.py:29,181).
**Attaches.** `dispatch_call` success merge (tool_dispatch.py:22,109): `as_of`, `source` from a flag beside `poller` (TL/base.py:80-82); `_entries` (run_evidence.py:120-191) drop value previews for live-only tools; bounded read-first round in `final_answer` (pattern loop_outcomes.py:170-174), "status answer" decided structurally (uncertain_outcome.py:3). **Cost** S markers; M gate. **Conflicts.** None. **Safe.** Yes; open: maximum age.

### P12. Server-side reply guard: FAILS (observed on main: [73], [75], [77])

**Exists.** Path: gates (model_runtime.py:225-238) → redaction `:246` (credentials, private paths, `<lonora_*>` tags, UUIDs only: public_reply.py:10-25) → `final_answer`. Name plumbing is switched off: `public_reply_violation(text, tool_names, …)` does `del tool_names`, "registry names are intentionally not private" (public_reply.py:37-42); `PublicStream` gets an empty set (model_runtime.py:109). `EFFECT_CLAIM` does not match «تم الإلغاء» or «سأحذف». Blocklist sources: tool names (registry.py:402) and run-local codes in `observe` (environment.py:134-201); there is no runtime registry of the 723 `LonoraError` codes. No server markdown normaliser (cause only).
**Missing.** Reply check against names, codes, states; a chat rephrase round.
**Attaches.** `final_answer` after the task gate, before `append_uncertain_line` (loop_outcomes.py:155,179); `finish_turn` (tool_loop.py:299); `append_notice` + `None` with a bounded counter (stop_gates.py:108-129). `PublicStream` admission (public_stream.py:47-51) would need the same blocklist; a published draft is replaced only by a new turn id (model_runtime.py:282-287). **Cost** S builders; M hook; M holding publication.
**Conflict (flag for the owner).** A guard that blocks and re-asks is a "second generation": it conflicts with public_reply.py:4, public_reply.py:40-41, model_runtime.py:239-241 and OWNER_DECISIONS.md:12; lonora.md:44 allows capability names when the owner asks, an exception that cannot be keyword-based. **Safe/owner.** Blocklist builders and eval check safe; a blocking guard is an owner decision.

### P13. Answer the question asked: PARTLY

**Exists.** `market_snapshot` returns quote, per-timeframe trend, structure, range, ATR, RSI, `levels` (previous day and week high-low with distance in price and ATR) and `limitations` (MK/snapshot.py:360-372). No verdict tool by design (lonora.md:78); `RES/skills/market-analysis/SKILL.md:60` asks for "one useful next action." OBSERVED «شو وضع الذهب»: error recitation [10], specification dump [14], full status only at [18].
**Missing.** No loaded text says what a market-status answer contains or that specifications are for sizing. `RES/prompts/trading_context.md:1` cannot be the cause of the dump: it is never loaded (`load_prompt` call sites: context/builder.py:128-136, context_engine.py:91, AR/context/compaction.py:20).
**Attaches.** SKILL.md "Output" (`:58-66`); the reliable place is the core manual (lonora.md:9-166). **Cost** S. **Conflicts.** None with money ("An owner request for analysis is not permission to trade", lonora.md:24). **Safe.** Yes; measure with an eval case «شو وضع الذهب».

### P14. Remember what was learned: FAILS

**Exists.** Case-only resolution (symbols.py:6-35); catalog not stored (AD/brokers/metaapi.py:443-459). OBSERVED: after «XAUUSDM» `XAUUSDm` was used in-thread, but nothing was written (Part 2: only `memory_read`). Candidate place: `BrokerSessionRow.state` (schema.py:767).
**Missing.** A stored map and a write on successful resolution (grep `symbol_map|symbol_alias|alias`: two policy mentions only).
**Attaches (storage and hooks; the resolver is another session's).** First step of `canonical_broker_symbol` (symbols.py:18), confirmed against the live catalog; write after a non-exact resolution (market.py:45-65; trade.py:621); key by connection and `connection_version`. **Cost** M.
**Conflict (flag).** "No hidden aliases" lines versus a symbol map: "Preserve broker symbols exactly, including case and suffix." (lonora.md:60), "Never strip suffixes, substitute an exchange feed or assume one broker's instrument exists at another." (lonora.md:224), comment trading_decision.py:79; the same change must rewrite them. A map supplies a candidate only: preflight (execution.py:182), restrictions (`:231`) and the operation id (trade.py:635) still apply. **Safe/owner.** Storage and hooks safe; policy lines change with the owner's brief.

### P15. Owner's language: PARTLY

**Exists.** lonora.md:58 ("Reply in the owner profile's reply_language, else the language of the owner's latest message, unless asked otherwise."); context `reply_language: preferences["reply_language"] or "latest_owner_message"` (context/memory.py:131); profile field `reply_language`, `ar`/`en`/null (schema.py:473-476). Two deciders: `prefers_arabic` (runtime_notices.py:84-93), `conversation_locale` (conversation_locale.py:13-35). SCRIPTED (`p916_principles.py` 15.1, `p916_locale_probe.py`): with an empty profile (production, Part 1 Q6; voice notes [48], [50] came out Turkish) both accept a Turkish transcript. The STT hint is the profile value only (`packages/voice/src/lonora_voice/voice_notes.py:55-58,72`).
**Missing.** A default pinning the language, a rule that transcripts do not decide it, one shared decider, a reply language check (cause only).
**Attaches.** `owner_preferences_section` (context/memory.py:119-151); `conversation_locale` skipping voice-part messages; `prefers_arabic` onto the same rule; script check in the P12 hook. **Cost** S default and hint; M script guard. **Conflicts.** None with money; the CHECK allows `ar`/`en` only while OWNER_DECISIONS.md:14 says cards follow the owner's language "whatever it is". **Safe/owner.** Safe; owner confirms the pin `reply_language = ar`.

### P16. Strength is not bypass: HOLDS

**Exists.** Tool layer: `trading_permission_available` → `agent_analysis_only` (trade.py:57-67, re-checked `:316-317`); `owner_action_propose` (owner_actions.py:291). Single executor `ExecutionService.execute` (execution.py:148): Task stop `:139-141`, global ON/OFF and Emergency Stop for new risk, never exits `:178-190`, preflight `:182`, account authority `:207-218`, restrictions `:231-236`. SCRIPTED (`p916_principles.py` 16.1-16.3): journal and approval rows stay 0.
**Missing.** Only a regression test. The attachments for 9-13 and 15 edit no executor check, approval or grant function. Closest: P14 changes the string entering the executor (trade.py:634-635); P10 Task cancel removes that Task's exits (execution.py:139-141). **Cost** S.


### genui_eval structure and where an agent eval attaches

Single-turn, offline-scorable. Cases: `tests/fixtures/genui_decision/cases.jsonl`. Tool answers: `tests/fixtures/genui_decision/tool_bank.json` via `scripts/genui_eval/bank.py:29` (all tools but `PASS_THROUGH` answered from data, `:35`). Runner `scripts/genui_eval/run.py`: disposable database, optional earlier turns (`seed_context` `:300`), real loop (`run_case` `:347`). Scorer `scripts/genui_eval/score.py`: `observe` `:374`, `judge` `:565`, `gate` `:782`, `called_tools` `:240`. Attachments: P9 two-turn case via `seed_context`; P10 bank answers for several agents, check `watch_cancel` per watch; P11 `observe` check "status case calls a live tool"; P12, P15 per-reply scan against `registry.names` and the owner's script; P13 content check. `scripts/agent_eval` is another session's.

### Reference parameters

65 of 126 tools take a reference, 134 fields. Tools per kind: `account_id` 32, `symbol` 24, `goal_id` 10, `agent_id` 8 (`agent_inspect`, `agent_control`, `peer_send`, `owner_action_propose`, ...), `chart_id` 8, `watch_id` 5, `position_id` 4 (`trade_execute`, `watch_create`, goals), `operation_id`, `thread_id`, `related_symbol` 4 each, `order_id`, `connection_id` 3 each, `task_id` 2.

### Open items

- UNSURE, trace bodies must confirm: `owner_started`/`owner_request_start` in the saved state of `fb1d4b5a`, `ddae66ad`, `e343c96a` (code predicts yes, loop_restore.py:58); `ln_messages.suggested_reply` of offer-ending replies (P3, P4); the grant envelope signed 09:43:24, expected all-null caps (P6); reactions at [41], [43] as run input (P4); request bodies (whether the `tasks` chapter lonora.md:434 or the inventory reached `ddae66ad`/`e343c96a`, P7); the third `watch_create` result of `ddae66ad`.
- UNSURE: `LONORA_GENUI_V2` in production (P13); admission shedding of the evidence section for `c22a6810` (P11); client display of a superseded streamed turn (P3, P12); grant path or card for `65e8b682` (P16); `web_search` source.
- Not ours to fix: nine `GET /api/agents/<the agent>/super-bot` requests answered 404 at 10:50-10:53 UTC, probably an old cached client.
