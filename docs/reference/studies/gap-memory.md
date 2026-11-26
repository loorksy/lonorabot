# Gap analysis: memory, context and skills (Lonora vs OpenMausBot and rakazo)

Audience: Lonora developers. Lonora read at `/home/user/wt-agent/fxmain` (main `d8193b98`), read-only.
Reference inputs: `ref/reports/openmausbot-memory.md`, `ref/reports/rakazo-memory.md` (two reference claims spot-checked
in the clones: OpenMausBot `server/memory-capture.ts` `statedInConversation`, rakazo
`packages/adapters/src/runtime/context/runtime-context.ts` `rebuildPaysOff`). Nothing was run and nothing in Lonora was edited.
Binding texts used: VISION 0.4, 3, 5, 6 (unchanged by any recommendation here), 8, 11, 12, 13, 14.1, Amendments 1-3,
`docs/cloud/DECISIONS.md` (D6, D41 BYOK).

## Ranked table

| # | Recommendation | Verdict | Pri | Source | Effort | Owner decision | VISION |
|---|---|---|---|---|---|---|---|
| 1 | Let every model call in a run reuse the provider cache: take the per-call timestamp out of the routing frame that sits before the transcript, add a rolling Anthropic breakpoint, send an OpenAI `prompt_cache_key`, record cache writes | adopt | P1 | both | M | no | 12.1, Am.3 §4, D6/D41, 5.8.7, 6 untouched |
| 2 | Volatile data after the transcript (account picture, routing frame, recall, memory snapshot, run evidence) so the history prefix also survives across turns | adapt | P2 | both | L | no | 5.4, 5.8.7, 6.3, 6.4, 6.10 |
| 3 | Stop re-sending MEMORY.md text through automatic recall (it is already loaded whole) | adopt | P2 | openmausbot | S | no | 5.4, P3 |
| 4 | Dated memory entries with an end (`until` date or "ends when <event>"), expired lines hidden and moved out by a system revision | adopt | P2 | both | M | no | 5.2, 8.4, 5.8.6 |
| 5 | "You said" profile lines need a quote of the owner's own words, checked against his message | adopt | P2 | openmausbot | S | no | 8.2, 8.4, 5.3.3 |
| 6 | An observation the owner removed from "What I know about you" is never re-learned | adopt | P2 | openmausbot | S | no | 8.2, 8.4 |
| 7 | `session_search` time windows (`since`/`until`, no query needed) and an honest miss text | adopt | P2 | openmausbot | S | no | 11.1, 3.1.5, 3.1.6, P6 |
| 8 | GIN index for the agent's whole-history full-text search, with the same Arabic folding as owner search | adopt | P2 | both | S | no | 3.1.6, P6, 13.1 |
| 9 | Weekly memory upkeep inside the existing weekly-report run (expired, duplicates, contradictions, promote summary facts, consolidate owner observations) | adapt | P2 | both | M | no | 5.5.4-6, 8.1, 8.3, 11.3, 11.5, P1 |
| 10 | Provenance label on memory/method revisions written by a run that read third-party content (label only, never a gate) | adapt | P2 | both | M | **yes** (reading of 6.10) | 6.10, 8.4 |
| 11 | Method and skill review with read-before-write, at most 3 changes, and a do-not-capture list, in the same weekly pass | adapt | P3 | openmausbot | M | no | 5.5.4, 5.5.5, 5.6 |
| 12 | Recent-work brief of team agents for Lonora's runs (SQL, no model) | adapt | P3 | openmausbot | S | no | 3.1.3, 3.1.5, 3.1.6, 11.1, 11.7 |
| 13 | Show budgets and omissions in the prompt (memory chars of limit, nearly-full hint, omitted skills/scratchpad counts) | adopt | P3 | rakazo | S | no | P3, 13.1 |
| 14 | Scratchpad item states (open, parked, done), titles always kept, fair shrinking, "this does not wake you" | adapt | P3 | rakazo | S | no | 5.2, 11.8 |
| A1 | Memory store: Postgres rows, attributed revisions with undo, locked content-addressed operations, receipts; never workspace files | already-better | - | both | - | no | 3.2.4, 5.5.5, 8.4 |
| A2 | Retrieval: hybrid lexical + embedding RRF, exact broker identifiers, Arabic diacritics, JSON evidence with authority labels | already-better | - | both | - | no | 6.10 |
| A3 | Compaction: persisted view, effect-preserving pruning ("read record, do not repeat"), structured summary with open operations, protected state re-read every turn | already-better | - | both | - | no | 6.2, 6.3, 6.4 |
| A4 | Skills: versions and restore, provenance labels, revocation, pinned immutable packages, validation, trusted sources, authority recheck on resume | already-better | - | both | - | no | 5.5.5, 5.6, 6.10 |
| A5 | Trading learning loop: close-wake self-review, judgment labels, per-label statistics, weekly report | already-better | - | both | - | no | 5.5 |
| A6 | Owner profile: said vs observed, owner-word protection, reach-me only on typed message, taint gate for observations | already-better | - | both | - | no | 8.2, 8.4 |
| S1 | External semantic memory providers (Supermemory, Honcho, ...) | skip | - | rakazo | - | no | P3, Am.3 §3 spirit |
| S2 | Cache keep-warm pings | skip | - | openmausbot | - | no | 12.1, P1 |
| S3 | Saved-steps replay, taught-skill demonstrations, skill burger | skip | - | both | - | no | 5.1, 6.1-6.3, P3 |
| S4 | Owner approval queue for background memory writes | skip | - | openmausbot | - | no | P1, P5, 8.2 |
| S5 | Shared team/Space memory writable by every agent | skip | - | both | - | no | 3.2.3, 3.2.4, 8.3 |
| S6 | Multiple context strategies and a cross-run projection map | skip | - | rakazo | - | no | P3 |
| S7 | Helper-model fallback chain for background jobs | skip | - | openmausbot | - | no | 12.3, P4 |

No row weakens section 6, adds a Stop control (Amendment 1) or touches any venue other than MT5 (Amendment 2).

---

## 1. What Lonora does today

### 1.1 Stores and scopes

| Store | Where | Scope | Size | Loaded |
|---|---|---|---|---|
| Agent memory row: `# MEMORY.md` (knowledge, plus unsectioned legacy text) and `# OPERATING.md` (the agent's method) | `MemoryRow` via `packages/db/src/lonora_db/memory.py`; views in `packages/memory/src/lonora_memory/profile.py` | one agent (Lonora may read team agents', 3.1.6) | `MEMORY_CHAR_LIMIT = 30000` (`lonora_db/memory.py:112`) | whole, every run (`context/memory.py` `read_memory_context`) |
| Owner profile `USER.md` + structured preferences (reply language, reach-me, quiet hours, timezone, name, address) | `packages/db/src/lonora_db/owner_profile.py` | every agent of the owner | `OWNER_PROFILE_CHAR_LIMIT = 8000` | whole, every run, split into `profile` (he said) and `lonora_observations` |
| Owner signals (reads by day, closes outside Lonora) | `lonora_db/owner_signals.py` | Lonora only | bounded | Lonora's runs |
| Owner goals and links | `AgentGoalRow`, `KnowledgeLinkRow` (`context/memory.py` `owner_knowledge_section`) | one agent | 20 items, 400 chars each | every run |
| Knowledge notes (semantic) | `SemanticMemoryRow`, `packages/memory/src/lonora_memory/semantic.py` | one agent | 24,000 chars per note | recall only |
| Scratchpad | `ScratchpadRow`, `packages/tools/src/lonora_tools/scratchpad.py` | one agent | 12 newest, cut at 16,000 chars (`context/scratchpad.py`) | every run |
| Revisions | `ln_memory_revisions` (`lonora_db/memory_revisions.py`): author, `source_run_id`, `source_message_id`, `previous_content`, change kind | per document | pruned to a kept count | UI, `method_history`, undo |
| Conversation messages | `MessageRow` | per thread | - | last `HISTORY_WINDOW = 100` (`context/history.py`) after the summary cursor |
| Conversation summary | `ThreadRow.context_summary`, `summary_seq` (`context/compaction.py`, prompt `resources/prompts/consolidator_archive.md`) | per thread | 24,000 chars | every run |
| In-run compaction view | `state["context_compaction"]` (`lonora_agent/context_engine.py`) | per run | summary 16,000 chars | applied per request |
| Recent tool evidence | run checkpoints (`context/run_evidence.py`) | agent + thread | 4 runs, 12 entries, 8,000 + 4,000 chars | every run |

### 1.2 Writing memory

- One tool, `memory_write` (`packages/tools/src/lonora_tools/memory.py`): either a whole-document rewrite at `version`, or up to 20
  operations `add | patch | remove` on sections `USER.md | MEMORY.md | OPERATING.md`. The batch shape and overflow protocol
  are adapted from Hermes (`lonora_memory/edits.py` header): all or nothing, size checked on the final result only,
  `MemoryOverflow.result()` returns the exact `shortfall`, `closest_lines` hints on a no-match, exact-entry dedupe,
  heading protection.
- `atomic_edit` (`lonora_memory/commit.py`) commits own-document and owner-profile operations in one transaction under the run
  lease and one effect receipt; operations are content-addressed and applied to the row read under `with_for_update`.
- Gates in `memory.py` `write`: a team agent writes `USER.md` only in a run answering the owner's typed message
  (`owner_profile_requires_owner_message`); Lonora's observations are refused in a profile-tainted run
  (`tools/profile_taint.py`); a line whose origin is the owner's word changes only on his message (`OWNERS_WORD_PROTECTED`);
  `guard.py` refuses lines in `OPERATING.md` or the profile that tell agents to send memory, secrets or data elsewhere.
- Methods: `method_history` / `method_restore` (`lonora_memory/method.py`) version `OPERATING.md` (5.5.5).
- No entry carries its own date or an end; no expiry; no automatic capture. Facts in a conversation enter memory only if the
  model writes them. The conversation summary marks facts `[permanent]/[durable]/[ephemeral]` but "does not edit long-term memory".
- A closed trade wakes its owner agent for a self-review (`packages/trading/src/lonora_trading/close_wake.py`, 5.5.2);
  per-label statistics come from `market_performance_read` (`tools/performance.py`); weekly reports from
  `lonora_trading/weekly_report.py` (5.5.6).

### 1.3 Retrieval

- Automatic recall before each run: `retrieve_memory` (`lonora_memory/semantic.py`) -> `retrieve_evidence`
  (`lonora_memory/evidence.py`). Candidates: chunks of the agent's own MEMORY/OPERATING view (`document_chunks`), up to 128
  recent + 128 lexically matching knowledge notes, and messages of the same direct conversation that the summary already
  covers (`lonora_memory/conversation.py`, server-owned `ConversationRecallScope`). Ranking: reciprocal-rank fusion of a
  lexical score (`retrieval.py`: broker identifiers kept exact, Arabic diacritics removed) and cosine similarity when an
  embedding model is set (1.5 s timeout, then lexical only). Output: at most 8 items / 6,000 chars, rendered as JSON with
  `authority`, `freshness`, `status`, `reasons`.
- On demand: `session_search` (`tools/session_search.py`, `lonora_memory/sessions.py`): PostgreSQL `to_tsvector('simple')`
  ranked search over the whole scoped history, an any-word and identifier fallback over the newest 5,000 messages,
  `around_seq` / `after_seq` reading, browse of recent threads, and recorded trading decisions. Lonora's scope includes
  every team agent (3.1.6); a team agent sees only its own and its groups. The module docstring states:
  "There is no index yet, so the whole-history statement runs under a statement timeout and falls back to the recent window."
  The only GIN index on `ln_messages` is a trigram index on folded content for owner search (`migrations/versions/0045_chat_lists.py`).
- No time-window query (`since`/`until`).

### 1.4 Prompt assembly (exact order)

`build_context` (`packages/agent-runtime/src/lonora_agent/context/builder.py`) then `model_runtime.py` per model call:

1. System 1: constitution and operating policy (`load_constitution`), agent instructions, `binding_context`, skill catalog
   (`<skill_runtime>`, cut at 6,000 chars), `wake_context(run)`, group prompt, suggested-reply prompt, web-search-on, slash-command
   context, subagent prompt, voice note.
2. Per model call, inserted at index 1: capability inventory (`model_runtime.py`).
3. System: account picture (`context/picture.py`), mandatory.
4. System: recorded decisions and operational observations (sheddable).
5. System: routing frame (`context/team.py`), **replaced before every model call** by `refresh_routing_context`. It contains
   `live_agent_state`, whose `observed_at=utcnow()` (`lonora_db/agent_state.py:614`) is not excluded, the
   protected operational state, the team directory, group context and the permission frame.
6. User role, one labelled context-data message (`adapter-kit/.../context_sections.py`), placed "directly after the system
   messages, before the transcript": responsibility, owner preferences, owner signals, owner goals/links, operating notes,
   memory, active skill bodies, conversation summary, history gap, workspace processes, recent tool evidence, account symbols,
   external evidence, **recalled evidence**, scratchpad, quoted reply, attachments, wake/webhook sections. Each section has
   source, trust and priority; admission sheds lowest priority first with an omission notice.
7. Transcript (from `summary_seq + 1`, at most 100 messages), then the run prompt.
8. Per call, appended at the end: visual observation catalog and the visual-capabilities block ("after the cached prefix").

### 1.5 Prompt caching

- Anthropic: `cacheable_system` (`packages/adapters/src/lonora_adapters/models/anthropic.py`) puts one `cache_control` on the
  `<lonora_operating_policy>` (+ visual vocabulary) prefix. `anthropic_messages` hoists every system message, including the
  routing frame and the trailing per-call blocks, into the one `system` string. No breakpoint on messages.
- OpenAI-compatible (`openai_compatible.py`): system messages stay in place; no `prompt_cache_key`.
- Tools: "chosen once per Run and frozen in the checkpoint: the native tools array is identical on every model turn"
  (`loop_restore.py`). History start is anchored at the summary cursor, not a sliding window.
- Usage: `cached_tokens` recorded; `model_pricing.py`: "Not modelled: cache writes (the adapters do not record
  `cache_creation_input_tokens`)".

Consequence: because the routing frame changes bytes on every model call (`observed_at`) and sits before the context data and
the transcript, an OpenAI-compatible provider can reuse at most the system messages before it, and Anthropic only the policy
block. Every tool round of a run re-sends the whole transcript and context data at the uncached price. Across turns the
recalled evidence, account picture and memory snapshot also precede the transcript. The owner pays all of this on his own key
(D6, D41).

### 1.6 Context-window management

- Conversation level: `compact_history` (`context/compaction.py`) summarizes when 80/120 unsummarized messages or more than
  48,000 chars exist, keeping up to 60 messages verbatim; originals stay in `ln_messages` and remain reachable by recall and
  `session_search`. A `history_gap` notice reports unsummarized messages beyond the window.
- Run level: `compact_context` (`context_engine.py`, adapted from Hermes): phase 1 prunes old tool results outside a protected
  tail to placeholders that keep effect identities (`operation_id`, `broker_reference`, `approval_id`, ...) and say
  `read_record_do_not_repeat` for financial results; results over 1,500 chars are stored (`tools/tool_results.py`, redacted)
  for `artifact_read`. Phase 2 writes a structured summary (`prompts/run_context_summary.md`: Goal, Owner instructions,
  Progress, Decisions, **Open operations and commitments**, Key evidence, Unverified or failed), degrading to a deterministic
  summary. `LOW_WATER = 0.8` hysteresis. The view is persisted, canonical messages never rewritten.

### 1.7 Skills

- Catalog in the system role (`context/skills.py` `read_skill_context`), descriptions as discovery hints; bodies by `skill_view`;
  automatic selection by `skills/resolver.py` (explicit `[skill:name]`, durable triggers, market/chart signals, never owner keywords);
  selected bodies travel as context-data sections; a snapshot pins versions per run and `assert_skill_authority` rechecks them.
- Tools (`tools/skills.py`): `skill_save` (every save a version), `skill_history`, `skill_restore`, package create/import
  (immutable commit, trusted sources), validate (30 s, hash evidence), control, `skills_list`, `skill_view`,
  `skill_repository_inspect`. Provenance labels bundled/owner/agent_authored/external (`skills/provenance.py`).
- No usage counter or automatic skill review.

---

## 2. What the references do better or differently

| Topic | OpenMausBot | rakazo | Lonora today |
|---|---|---|---|
| Volatile data placement | Stable half cached; volatile half re-sent as a note; recall **in front of the user message, never in the system prompt** | System prompt stable-first; recall after history; live memory snapshot and `<current_time>` in the newest user turn | Volatile frame with a per-call timestamp **before** the transcript |
| In-run cache | Relies on Claude CLI; OpenRouter `cache_control` + `session_id` | Append-only transcript, `rebuildPaysOff`, `sessionId` as cache key, per-connection cache capabilities, cache tracker | Policy block only; no message breakpoint; no cache key |
| Memory expiry | `until` + hidden after date, archive before removal | `(saved D, ends D or when EVENT)`, archive before removal, archive never shown | none |
| Recall vs loaded memory | Auto-recall excludes `MEMORY.md` (already loaded) | Markdown memory injected, not retrieved | Recall chunks the already-loaded MEMORY view again |
| Automatic learning | capture (quote-checked), organize, dream (pattern in 2+ chats, quotes), tidy (expired, duplicates, contradictions), skill review | none locally; providers learn from turns | none; model writes only; close-wake self-review |
| Owner-fact honesty | `statedInConversation`: evidence quote must appear in the person's words | n/a | "you said" = agent write in a run answering any owner message |
| Forgetting | `forget` records the words so no bot relearns | n/a | removal is a revision; nothing stops re-adding an observation |
| History search | `since`/`until` with no query; scope enforced server-side | keyword search, "does not show it never happened", `searchBeforeSeq` | no time window; whole-history query unindexed |
| Lead awareness | recent-work brief: newest line per other conversation, 48 h, 10 lines | n/a | on demand only (`agent_inspect`, `session_search`) |
| Budgets shown | "only the first 200 lines shown" notice; skills omitted count | "N of 4096 bytes", nearly-full hint under 512 bytes | version attributes only; catalog `[:6000]` cut silently |
| Working memory | n/a | scratchpad open/parked/done, titles kept, fair shrink, "not a scheduler" | 12 newest notes, cut at 16,000 chars |

---

## 3. Recommendations

### R1 (P1, adopt, M). Reuse the provider cache on every call of a run

Why: the single largest avoidable cost on the owner's key. A run with N tool rounds re-sends the transcript N times uncached.
The cause is narrow and fixable: the routing frame is rebuilt per call with `observed_at=utcnow()` and placed before the
transcript; Anthropic has no message breakpoint; OpenAI-compatible calls carry no cache key.

Change:
1. Exclude `observed_at` from the model-facing `live_agent_state` dump in `routing_frame` (`context/team.py`, the
   `exclude={...}` set), and give the model the current time in a trailing per-call note after the transcript, the same pattern
   `model_runtime.py` already uses for the visual-capabilities block. Keep the protected operational state and permission frame
   on every call (5.8.7, 6.3/6.4); only their position or a timestamp changes, never their presence.
2. Anthropic (`adapters/.../anthropic.py`): keep the policy breakpoint; add a second `cache_control` on the last content block of
   the request (rolling). System notes that the runtime appends after the transcript should be sent as a trailing user text
   block, not hoisted into `system`, or they invalidate everything after the first breakpoint.
3. OpenAI-compatible (`openai_compatible.py`): send `prompt_cache_key` = a hash of `agent_id:thread_id` on OpenAI;
   OpenRouter (`openrouter.py`): `cache_control` for `anthropic/*` models as OpenMausBot does.
4. Record `cache_creation_input_tokens` and add write prices in `packages/core/src/lonora_core/model_pricing.py`, so the gain
   is measured; store per run the section names, sizes and shed list next to `skill_selection` in `run.model_metadata`
   (rakazo's `RuntimeContextDecision`), for evals.

Files: `packages/agent-runtime/src/lonora_agent/context/team.py`, `packages/agent-runtime/src/lonora_agent/model_runtime.py`,
`packages/adapters/src/lonora_adapters/models/anthropic.py`, `.../openai_compatible.py`, `.../openrouter.py`,
`packages/core/src/lonora_core/model_pricing.py`, `packages/llm-usage` (usage record).
VISION: 12.1 and Amendment 3 §4 / D6 / D41 (the owner pays model use; no limit is added, P1 intact), 5.8.7 (frame kept),
section 6 untouched. Tests: a golden test that two consecutive requests of one run share a byte-identical prefix through the
end of the previous transcript; the 14.1.2 core tests unchanged.

### R2 (P2, adapt, L). Volatile data after the transcript, across turns

Why: each run loads about 30,000 chars of memory, 8,000 of profile, up to 16,000 of scratchpad, 6,000 of recall and 12,000 of
run evidence before the history. Recall and the account picture change every run, so the history (up to 100 messages) is never
a reusable prefix between turns. Both references fixed this with a stable-head, volatile-tail layout and say so in comments.

Change: keep the head byte-stable (policy, agent instructions, skill catalog, tools, conversation summary); move the account
picture, routing frame, recalled evidence, recent tool evidence, memory/scratchpad snapshot and wake context into one trailing
"current turn data" context message directly before the newest input. Lonora's labels, escaping and priority shedding stay as
they are. Copy rakazo's habit of a comment at each placement explaining the cache reason.

Files: `context/builder.py`, `loop_restore.py` (`refresh_context_head`, `_leading_data`), `context_engine.py` (`_split`
assumes leading context data), `adapter-kit/src/lonora_adapter_kit/context_sections.py` (`replace_context_sections`,
`context_message`), `context/team.py`, `model_runtime.py`, plus tests of order and shedding.
VISION: 5.4 (full picture on every wake: unchanged content, new position), 5.8.7, 6.3/6.4 (protected state still re-read and
present every turn; at the tail it is closer to generation), 6.10 (labels unchanged). Risk: compaction indexes and admission
shedding assume a leading data message; do it after R1 and measure with R1's accounting first. Effort L.

### R3 (P2, adopt, S). Do not recall what is already loaded

`_retrieve_evidence` adds chunks of the agent's MEMORY/OPERATING view as candidates and `fuse_evidence` prefers them on ties,
while `read_memory_context` already loads the whole view. The 6,000-char recall budget can be spent repeating it.
OpenMausBot excludes `MEMORY.md` from auto-recall for exactly this reason. The memory section (priority 80) outlives recall
(priority 40) under shedding, so excluding it is safe. Add a flag to `retrieve_memory`/`retrieve_evidence` used only by the
builder. Files: `packages/memory/src/lonora_memory/evidence.py`, `semantic.py`, `context/builder.py`. VISION 5.4, P3.

### R4 (P2, adopt, M). Dated entries with an end

Trading memory goes stale by the date ("no new entries until NFP on Friday", "broker maintenance Sunday"). Lonora lines carry no
date and never end; only per-revision provenance exists. Adopt rakazo's stamp `(saved 2026-11-26, ends 2026-11-28 | ends when
<event>)` on `add`/`patch` with an optional `until` in `MemoryOperation`, hide ended lines when loading, and remove them with a
`change="expired"`, `author="system"` revision (Lonora's revisions already keep the prior text, so no separate archive file is
needed; rakazo's archive-before-delete order is satisfied by the revision being written in the same transaction). Event-style
ends are never expired automatically. Use the owner's timezone from `owner_preferences`; rakazo's "ends only after the last
timezone's day" rule is a good default.
Files: `packages/memory/src/lonora_memory/edits.py`, `commit.py`, `packages/tools/src/lonora_tools/memory.py`,
`packages/agent-runtime/src/lonora_agent/context/memory.py`, `packages/db/src/lonora_db/memory.py`, `memory_revisions.py`,
a gateway maintenance step, `resources/system/lonora.md` memory chapter and `manifest.json` regeneration (5.8.6).
VISION 5.2 (timing and events are judgment the agent records), 8.4 (the owner sees the end date), 5.8.6.

### R5 (P2, adopt, S). Quote-checked "you said" lines

`owner_knowledge._origin` labels a profile line "you_said" when an agent wrote it in a run that answers any owner message, even if
the line is a paraphrase or invention. It then becomes protected owner's word (`OWNERS_WORD_PROTECTED`). Adopt OpenMausBot's
`statedInConversation`: a `USER.md` add that is not `observed` must carry an `evidence` quote that appears (after Arabic folding)
in the owner's typed message the run answers, not inside a question or a hypothetical; without it the write is refused with a
recovery that says "save it as observed (Lonora) or in MEMORY.md (team agent)". Files: `tools/memory.py`, `lonora_memory/edits.py`,
`lonora_db/owner_knowledge.py`, `lonora_db/owner_words.py`. VISION 8.2, 8.4 ("read and correct everything Lonora has learned"
requires honest origins), 5.3.3.

### R6 (P2, adopt, S). Owner removals stick

An owner who deletes an observation in "What I know about you" today can see Lonora add it back at the next observation. Keep the
normalized identity of lines the owner removed (derivable from owner-authored revisions, or a small table) and refuse an
`observed` add of the same identity; the owner's own message can still add it. Files: `lonora_db/owner_profile.py` or
`owner_knowledge.py`, `tools/memory.py`. VISION 8.2, 8.4.

### R7 (P2, adopt, S). Time windows in `session_search`

"What happened since the London open" or "since the last brief" needs no keyword. Add `since` / `until` (ISO time or `24h`, `3d`)
to `SessionSearchInput`; with no query, list scoped messages in the window newest first, bounded like `read`. Copy rakazo's miss
text ("no message matched these words, which does not show it never happened"). Files: `tools/session_search.py`,
`lonora_memory/sessions.py`. VISION 11.1 (brief since the last brief), 3.1.5, 3.1.6, P6.

### R8 (P2, adopt, S). Index the agent's history search

`sessions.py` documents that the whole-history statement has no index and falls back to the newest 5,000 messages after a 4 s
timeout. An always-on agent accumulates months of messages, so search silently degrades. Add a migration with a GIN index on the
exact expression `full_text_statement` uses, and use the same Arabic folding expression (`folded_sql`, migration 0045) for the
agent's literal arm and for `conversation.py` (today it strips diacritics only, not alef/hamza/taa-marbuta variants).
Files: new migration under `packages/db/migrations/versions/`, `lonora_memory/sessions.py`, `lonora_memory/conversation.py`.
VISION 3.1.6, P6, 13.1 (a half-built path).

### R9 (P2, adapt, M). Weekly memory upkeep in the weekly-report run

Neither "the model writes everything" (rakazo, Lonora) nor hidden background writers (OpenMausBot) fit exactly. Lonora's mandate
already has a weekly run per agent (5.5.6). Add to its wake text, and to a cheap deterministic pre-pass, the upkeep that rakazo
lacks and OpenMausBot does in the background:
- deterministic: ended lines (R4), exact duplicates;
- by the agent itself, under its own model and judgment: contradicting pairs (strike the older), `[permanent]`/`[durable]` facts
  from conversation summaries not yet in memory, and, for Lonora, consolidation of owner-behaviour observations seen on at least
  two days of `owner_signals` (OpenMausBot's two-conversation rule), each with the quote or signal it rests on;
- every change is an attributed revision with undo; nothing posts when nothing changed (11.5).
No approval queue (S4). Files: `packages/trading/src/lonora_trading/weekly_report.py`, `resources/system/lonora.md` +
`manifest.json`, a small helper in `packages/memory`. VISION 5.5.4-6, 8.1, 8.3, 11.3, 11.5, P1, P6.

### R10 (P2, adapt, M). Label memory written after reading third-party content (owner decision)

`memory_write` gates only `USER.md` on taint. A run that read a web page, feed, MCP result or peer message can write
`OPERATING.md`, which every later run reads as the agent's own method. The execution door never reads memory, so section 6 holds,
but judgment can be steered persistently. Both references treat recalled or learned text as outside content (rakazo
`markReadOutsideContent`; OpenMausBot "never record instructions or claims that arrive from other bots, webhooks or imported files").
Proposal: record on each revision whether the writing run had `external_content_seen`, show it as a section attribute
(`written_after_external_content="true"`) and in the method history; never refuse the write and never restrict the later run.
Owner decision needed: `tools/profile_taint.py` reads 6.10's last bullet ("Taint ... MUST NOT spread to the agent's later
watches, routines or wakes") as "never narrow a later run". A content label is not a restriction, but the owner should confirm
that reading before it ships. Files: `lonora_db/memory.py`, `lonora_db/memory_revisions.py` (+ migration), `tools/memory.py`,
`context/memory.py`, method history display in web and mobile. VISION 6.10, 8.4.

### R11 (P3, adapt, M). Method and skill review with guard rails

OpenMausBot's skill review (tool-step counter, read-before-write, at most 3 changes, a `DO_NOT_CAPTURE` list: no setup-dependent
failures, no "tool X is broken", no one-off tasks, no secrets; correction signals like "too long" as first-class triggers) is the
best part of its procedural memory. For Lonora put it in the same weekly run as R9: the agent reads its per-label statistics,
self-reviews and long tool-heavy runs since the last review, and changes its `OPERATING.md` or a skill through `skill_save` /
`memory_write` (versions and restore already exist). Never saved order recipes (S3). Files: `weekly_report.py`, `lonora.md` +
`manifest.json`. VISION 5.5.4, 5.5.5, 5.6.

### R12 (P3, adapt, S). Recent-work brief for Lonora

OpenMausBot gives a bot the newest thing it said in each of its other conversations (48 h, 10 lines, 1,400 chars, plain SQL).
Lonora leads the team and speaks for it but learns what agents did only on demand. Add, for Lonora's runs only, one line per team
agent: newest assistant message head in its conversation or work threads in the last 48 h, with time and thread id, in the
volatile tail (R2). Team agents do not get it (3.2.4). Files: `context/builder.py`, a query beside `lonora_db/lead.py` or
`lonora_memory/sessions.py`. VISION 3.1.3, 3.1.5, 3.1.6, 11.1, 11.7.

### R13 (P3, adopt, S). Show budgets and omissions

Add `chars` and `limit` to the memory and profile section attributes and a "nearly full" hint near the cap (rakazo shows
"N of 4096 bytes" so the agent tidies before a save fails); replace the silent `[:6000]` cut of the skill catalog with whole lines
plus "N more: use skills_list"; end the scratchpad cut on an item boundary with an omitted count. Files: `context/memory.py`,
`context/skills.py`, `context/scratchpad.py`. VISION P3, 13.1 (catalog entries that never reach the model).

### R14 (P3, adapt, S). Scratchpad states

Give `ScratchpadItem` a `status` (open, parked, done) and let the agent close items; render open items first with titles always
kept and notes shrunk fairly (rakazo `scratchpad-context.ts`), parked items only counted, and one line "this list does not wake
you; use a watch or timer". Files: `packages/contracts/src/lonora_contracts/domain.py`, `tools/scratchpad.py`,
`context/scratchpad.py`, `lonora_db/scratchpad.py`. VISION 5.2 (self-scheduling is watches and timers), 11.8.

---

## 4. Where Lonora is ahead (keep; do not port the reference design)

- **A1 Memory store.** OpenMausBot keeps memory in workspace files and needs a journal outside the workspace plus turn-start/turn-end
  diff reconciliation because the bot can edit the files directly. Lonora stores rows, writes only through tools, and keeps
  attributed revisions with undo (`lonora_db/memory_revisions.py`), content-addressed operations under a row lock, and effect receipts
  for idempotent retries. VISION 3.2.4 already forbids memory in workspace files. Rakazo's revision table is comparable, without the
  owner-word protection.
- **A2 Retrieval.** Neither reference has in-house semantic retrieval (OpenMausBot FTS5 only; rakazo delegates to optional cloud
  providers and never searches its Markdown store). Lonora fuses lexical and embedding ranks, keeps broker symbols exact
  (`XAUUSDm`), folds Arabic diacritics, scopes conversation recall with server-owned cutoffs, and renders evidence as escaped JSON with
  authority, freshness and degradation status (`evidence.py`).
- **A3 Compaction.** OpenMausBot does no in-session pruning; rakazo ships an LLM summarizer that default deployments never run. Lonora
  prunes with effect identities and "read the record, do not repeat" for financial results, stores large results, writes a summary
  with a mandatory "Open operations and commitments" section, and re-reads protected operational state every turn, which directly
  supports 6.2-6.4. This is what rakazo's own report recommends Lonora do; it is done.
- **A4 Skills.** Versions and restore for every skill and method (5.5.5), provenance labels, revocation by version, pinned immutable
  packages with validation evidence, trusted sources, and an authority recheck when a run resumes (`context/skills.py`
  `assert_skill_authority`). Neither reference versions skills or rechecks them on resume.
- **A5 Learning loop.** Close-wake self-review, judgment labels, per-label broker-confirmed statistics and weekly reports
  (`close_wake.py`, `tools/performance.py`, `weekly_report.py`). Neither reference learns from outcomes.
- **A6 Owner profile.** One shared profile with "he said" and "Lonora observed" kept apart, owner-word protection, reach-me changes
  only on his typed message, and a taint gate for observations (`tools/memory.py`, `tools/profile_taint.py`). R5 and R6 tighten it;
  the structure is already better than OpenMausBot's JSON-quoted About-me list and rakazo's absence of a profile.

## 5. Skips

- **S1 External semantic memory providers (rakazo).** Lonora already has hybrid retrieval in Postgres. A provider would send every
  conversation and memory to another vendor, needs purge/settle machinery (rakazo's `conversation-memory.ts`, 586 lines), and adds a
  second source of truth. P3. An owner who wants one can still reach any API from the workspace.
- **S2 Keep-warm pings (OpenMausBot).** Built for subscription sign-ins with a 1 h cache; VISION 12 allows API keys only, and pinging
  spends the owner's money without a request.
- **S3 Saved-steps replay, taught playbooks, skill burger.** Replaying recorded actions bypasses the model's judgment (5.1) and, for
  orders, the per-send reasoning the door expects (6.1-6.3). Out of scope for an MT5 trading agent (P3).
- **S4 Approval queue for background memory writes.** It would make the owner administer memory (P1, P5). Lonora's attributed
  revisions, undo and the 8.4 view already let him correct anything.
- **S5 Shared team or Space memory.** VISION 3.2.4 keeps team memory private; the owner profile is the one shared document (8.3); the
  trading picture is server-derived (5.4); peers talk through messages (3.2.3).
- **S6 Multiple context strategies and a cross-run projection map (rakazo).** One policy is enough (P3). R1 and R2 take the part that
  matters: a stable prefix and append-only growth.
- **S7 Helper-model fallback chain (OpenMausBot).** Lonora's router already runs background jobs on the owner's assigned models
  (`Capability.BACKGROUND`, 12.3); a second-provider helper would move transcripts without the owner choosing it.

## 6. Not verified

- Whether OpenAI's automatic caching currently reuses Lonora's system head across runs (it depends on the capability inventory
  being byte-stable); measure with R1's accounting.
- The exact token cost of the context-data message per run; sizes above are the code's caps, not measurements.
- Web and mobile rendering of method history and "What I know about you" (R6, R10 touch them) was not read.
- `weekly_report.py` wake text was not read in full; R9 and R11 assume it can carry extra instructions without a new run kind.
