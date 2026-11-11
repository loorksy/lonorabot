# Completeness critique of the audit (maps, journeys, and the second team's conv/trace/sec files)

Repository `/home/user/lonorabot`. The checked-out HEAD is `0a03960`, not `9f5b1da`. `git diff --name-only 9f5b1da HEAD` lists 31 files, all under `docs/research/` (draft notes). No code changed, so line numbers taken at `9f5b1da` still hold. Read-only: nothing under the repository was changed.

Ground truth read first: `OWNER_BRIEF.md`, `TIMELINE_CORRECTION.md`, `production-trace.md` (headers and the parts the maps cite), `lonora-chat.md` (only as cited by the maps). The coverage checks below use grep over every `map-*.md`, `journey-*.md`, `conv-*.md`, `trace-*.md` and `sec-*.md` in the audit folder. Where a check says "never cited", it means that no file in that folder names the path.

---

## 1. Tool families (packages/tools/src/lonora_tools, 53 .py files)

Every file is either covered by a census table or defines no tool:

| Family file(s) | Census in | Note |
|---|---|---|
| `market.py`, `market_analysis.py`, `symbols.py`, `market_watch.py`, `market_binding.py`, `chart.py`, `chart_state.py`, `chart_indicator.py`, `chart_snapshot.py` | `map-tools-market.md` §3.1-3.3 | |
| `trade.py`, `trading_decision.py`, `trading_goal.py`, `restrictions.py`, `position_sizing.py`, `performance.py`, `opportunity.py` | `map-tools-trading.md` §3-7 | |
| `memory.py`, `message.py`, `tasks.py`, `routine.py`, `subagent.py`, `agents.py`, `consult.py`, `collaboration.py`, `relationships.py`, `runtime_control.py`, `session_search.py`, `incoming_call.py`, `owner_actions.py`, `supervision.py`, `account.py`, `tool_discovery.py`, `tool_results.py` | `map-tools-agentic.md` §4 | `context.py` and `tool_results.py` define no tool (stated there, line 79). |
| `workspace.py`, `workspace_access.py`, `browser.py`, `browser_service.py`, `search.py`, `feeds.py`, `mcp.py`, `skills.py`, `skill_access.py`, `artifacts.py`, `scratchpad.py`, `models.py`, `capabilities.py` | `map-tools-world.md` §3.1-3.9 | This map uses the `T/` prefix, which is why a plain grep for `lonora_tools/skill_access.py` finds nothing. Its scope line names `skills`/`skill_access`. |
| `registry.py`, `base.py`, `loader.py`, `schema.py`, `environment.py`, `__init__.py` | shared mechanics in `map-tools-world.md` §1 and `map-errors.md` §1 | |

**No tool family is missing.**

## 2. Agent runtime (packages/agent-runtime/src/lonora_agent, all subfolders)

Modules no audit file cites, with their size in lines:

- `context/attachments.py` (54): the owner's attachment path, and so the vision input. **Gap 3.**
- `genui_capabilities.py` (38): a per-turn system block that states delivery channels and language. **Gap 5.**
- `context/reply.py` (15) and `context/governance.py` (20): re-exports and a quote helper. No refusal or notice. Not a gap.
- `context/group.py`, `collaboration/groups.py`, `collaboration/mentions.py`, `collaboration/participation.py` (52 in all): group-thread context. The owner's complaint concerns a personal thread, so this is low priority.
- `skills/snapshot.py`, `skills/runtime.py`: not cited by path, but their codes (`skill_snapshot_invalid`, `skill_snapshot_budget_exceeded`, rejection codes) are covered through `skills/access.py` in `map-extension.md` lines 532-535. Not a gap.

All the guard, gate, repair and notice modules are cited at least once: `stop_gates.py`, `tool_guardrails.py`, `runtime_notices.py`, `uncertain_outcome.py`, `model_recovery.py`, `recovery.py`, `suggested_reply.py`, `continuation.py`, `loop_restore.py`, `loop_outcomes.py`, `tool_intent.py`, `tool_block.py`. `trace-guards.md` and `sec-guards.md` cover the PR #42 reply guards and why they recorded nothing.

## 3. Docs read and compared with code

| Doc | Compared in |
|---|---|
| `docs/tool-execution-runtime.md` | `map-errors.md`, `map-loop.md` |
| `docs/agent-operating-policy.md` | `map-context.md`, `map-loop.md` |
| `docs/context-engine.md` | `map-context.md` |
| `docs/chat-runtime-repair.md` | `map-loop.md` |
| `docs/provider-resilience.md` | `map-providers.md` |
| `docs/proactive-wakes.md` | `map-background.md`, `journey-j4-background.md` |
| `docs/persistent-trading-teammate.md` | `map-tools-trading.md` |
| `docs/mcp-boundary.md` | `map-extension.md`, `map-tools-world.md` |
| `docs/lonora-specs/MANDATE_EXECUTION_PLAN.md` | `map-tools-trading.md` |
| `docs/agent-memory-and-recall.md` | cited only once, in `journey-j4-background.md` J4-07. It is **not compared** with `packages/memory`. **Gap 1.** |
| `docs/architecture/decisions/0001-agent-first-evolution.md` | **never cited.** **Gap 4.** |
| `docs/lonora-specs/NANOBOT_PARITY_AND_RELIABILITY_PLAN.md` | **never cited.** **Gap 4.** |
| `docs/lonora-specs/NANOBOT_ARCHITECTURE_STUDY.md` | **never cited.** **Gap 4.** |
| `docs/lonora-specs/AGENT_HARNESS_SOURCE_REVIEW.md` | **never cited.** **Gap 4.** |

## 4. Packages

| Package | Coverage | Verdict |
|---|---|---|
| `packages/memory` | Only `edits.py`, `commit.py`, `guard.py` and `sessions.py` are cited, through `memory_write` and `session_search` error codes. `retrieval.py`, `semantic.py`, `evidence.py`, `conversation.py`, `compaction.py`, `profile.py`, `store.py` and `markdown_memory.py` are never cited. J4-07 says outright that semantic recall was not examined. | **Gap 1** (Part 1.6 has no map). |
| `packages/voice` | Voice notes are well covered: `voice_notes.py`, `transcription.py` and `routing.py` in `map-providers.md` §10, `conv-conv-EFG`, `sec-dissect-3`. Incoming calls are covered through `incoming.py`. Live calls are never cited: `realtime.py` (585 lines), `handoff.py`, `context.py`, `sessions.py`, `synthesis.py`, `barge_in.py`. | **Gap 2.** |
| Vision | `map-providers.md` §10 covers the model side (`image_observations.py`, routing). Not covered: the owner-attachment path (`context/attachments.py`), any journey, and `tests/check_image_observations.py` (never run or cited). | **Gap 3.** |
| `packages/channels` | `map-harness.md` §9 and `journey-j3-world.md` J3-08 (Telegram mirroring versus the `owner_notify` note). | Covered. |
| `packages/session` | `map-harness.md` §4 and `trace-model-availability-updates.md` (idempotency). | Covered. |
| `packages/automation` | `runner.py` and `types.py` in `map-background.md`. Routines are covered from the database and tool side, and J4-01 covers scheduling. `scheduling.py`, `service.py` and `binding.py` are not cited, but they hold only one code (`routine_binding_mismatch`, `packages/automation/src/lonora_automation/binding.py:6`). | Acceptable. |

## 5. Capability comparison: can each row be answered?

| Capability | Answered by | Status |
|---|---|---|
| Files | `map-extension.md` §0 row 1, §1 | yes |
| Running code | `map-extension.md` row 2, §2; `journey-j3-world.md` J3-01/J3-04 | yes |
| Shell or computer | `map-extension.md` row 2 (sandbox `/bin/sh`, no host computer) | yes |
| Browser | `map-extension.md` row 3, §3; J3-02; J6-2 (live) | yes |
| Web research | `map-tools-world.md` §3.2; J3-03 | yes |
| Scheduling | `map-background.md`; J4-01; J6-3 (live) | yes |
| Notifying and messaging | `map-harness.md` §9; `map-tools-agentic.md` (`incoming_call.py`); J3-08 | yes |
| Subagents | `map-tools-agentic.md` (`subagent.py`); J4-05 | yes |
| MCP | `map-extension.md` §5; J3-05 | yes |
| Adding skills or tools by itself | `map-extension.md` rows 4 and 6; J3-06 | yes |
| Vision | `map-providers.md` §10 (model side only) | **partial: Gap 3** |
| Voice | voice notes yes. Live calls: no | **partial: Gap 2** |
| Acting on connected accounts | `map-extension.md` row 7; the trading maps; J5 | yes |

No single file holds this table. The lead can assemble it from the rows above. The nanobot and rakazo columns are Phase 1 work and are outside this audit.

## 6. Journeys

There are about 48 reproduced journeys in total: J1 has 10, J2 8, J3 about 10 (with sub-cases), J4 9, J5 6 families with sub-cases, and J6 5 (four of them live). That is well above twelve. **The gold journey is J1-01** (`journey-j1-gold.md` line 53). Its model turns are scripted and the MetaApi SDK is faked. Its "Reconciliation with the production trace" section matches the two codes and the recovery block of production run `1ae9a14c`. J6-1 adds a live reproduction. One trace point is explicitly not reproduced: the lead's "market_instrument took five seconds" (J1 line 32). It is correctly marked UNSURE.

No journey covers a voice call or an image the owner sends (Gaps 2 and 3).

## 7. Trace contradictions spotted

I found no remaining contradiction in the files I checked. `map-extension.md` lines 23-34 and `journey-j1-gold.md` lines 28-32 already apply the trace's corrections: availability of `workspace_execute` and `web_browse`, the 22 versus 23 native tools, and no discovery call in the gold run.

---

## 8. Gaps that matter most (six at most; none is covered by the conv/trace/sec files)

### Gap 1: memory-recall (Part 1.6 has no map)

**What is missing.** Nobody mapped how stored memory and recall feed a run, or whether they can bring back an earlier failure:

- Per-turn semantic and conversation recall is built from the newest user message (`packages/agent-runtime/src/lonora_agent/context/builder.py:187-213`) through `retrieve_memory` (`packages/memory/src/lonora_memory/semantic.py:55`). It is not examined anywhere, and J4-07 says so.
- Nobody checked whether recall or `recent_tool_evidence` re-injects old assistant replies that carry codes or «ما قدرت…» into later runs, which would make the refusal self-reinforcing.
- Provenance (`tests/check_memory_provenance.py`) and conversation recall (`tests/check_conversation_recall.py`) were never run.
- `docs/agent-memory-and-recall.md` was not compared with code. Two lines to check:
  - It says "Automatic per-turn recall still covers only the current thread" (`docs/agent-memory-and-recall.md:393-394`). If true, a symbol learned in another thread is never recalled, which matters for principle 14.
  - It says "Until the `owner_notify` tool (W15-7) lets an Agent raise an inbox alert…" (`:397-400`). The tool exists in code (`packages/tools/src/lonora_tools/incoming_call.py:129`), so the doc is stale and the code wins.

**Where to look.** All of `packages/memory/src/lonora_memory/`, `context/builder.py:150-270`, `context/run_evidence.py`, `context/memory.py`, `docs/agent-memory-and-recall.md`, and the two check scripts. `conv-principles-9-16.md` P14 covers only the symbol-map storage.

### Gap 2: voice-calls (live call path unexamined)

**What is missing.** Live voice calls hand owner speech to the Lonora agent and speak the result back. That path contains fixed English owner-facing strings and a raw code leak that no file examined:

- `"Backend status: " + run.status + ". " + (run.error_code or "")` (`packages/voice/src/lonora_voice/realtime.py:463`) is fed to the voice model as the result of a failed or cancelled run. That puts internal statuses and codes (for example `model_not_configured`) into speech.
- "Ask the user for the information the backend still needs." (`realtime.py:459`) is the fallback for `waiting_input`.
- "I couldn't pass that voice turn to Lonora, so I haven't started new work. …" (`realtime.py:41-44`, used at `:245`) and "The agent is paused or unavailable. No work was started." (`:424`) are both English.
- Two parts are needed for safety:
  - Speech and chat text are not approval: `APPROVAL_CARD`, `realtime.py:34-39`.
  - The rule never to create financial work from an incomplete utterance (`docs/architecture/decisions/0001-agent-first-evolution.md:19`).

**Where to look.** `packages/voice/src/lonora_voice/realtime.py`, `handoff.py`, `context.py`, `sessions.py`; `tests/check_voice_handoff_recovery.py`, `tests/check_voice_task_continuity.py`, `tests/voice/`. One journey is needed: a voice call asking «شو وضع الذهب» on the XAUUSDm account.

### Gap 3: vision-input (owner attachments)

**What is missing.** Nobody traced what happens when the owner sends a screenshot or file. Three behaviours to confirm:

- Images reach the model only when the type is png, jpeg, webp or gif and the file is at most 5 MiB (`packages/agent-runtime/src/lonora_agent/context/attachments.py:45-51`).
- Text and JSON are cut to 24,000 characters (`:52-53`). Any other type, such as a PDF, reaches the model only as the line "Artifact <id>: <name>" (`:41`). That can produce "I can't read the file" and leaks an id.
- An artifact the owner does not own is silently skipped (`:37-38`).

The images are then attached to the newest owner message (`context/builder.py:278-283`). The vision-routing failure (`model_not_configured` when no vision route exists) is in `map-providers.md` §10, but no journey exercises it, and `tests/check_image_observations.py` was never run.

**Where to look.** `context/attachments.py`, `context/builder.py:150-152` and `:278-283`, `context/image_observations.py`, `tests/check_image_observations.py`, `tests/test_image_observations.py`. One journey is needed: a chart screenshot plus «حلل هذا».

### Gap 4: spec-docs-unread (four of the fourteen required docs)

**What is missing.** Four docs were never read or compared with code. Each contains lines that bear directly on the complaint:

- `docs/lonora-specs/NANOBOT_PARITY_AND_RELIABILITY_PLAN.md`:
  - R06 says "Simple requests get direct execution" (`:126`).
  - It also says "Expose stable error codes and parameters through existing contracts" (`:132`), which can be read as licence to show codes.
  - And "Ask for clarification only when the missing information … cannot be inferred safely" (`:133`).
  - Each needs a "holds / fails on main" verdict.
- `docs/lonora-specs/NANOBOT_ARCHITECTURE_STUDY.md:60` already recorded, as a "Lonora baseline gap", that "ordinary errors lose recovery metadata" and that `advance_guard` aborts at repetition six. Check whether the code still has both, which would make this a known and unfixed gap. The error-contract fix belongs to another session, so state the cause only.
- `docs/lonora-specs/AGENT_HARNESS_SOURCE_REVIEW.md:15` states by design that "No English intent regex or claim such as 'I will monitor' proves a continuation". That is the documented reason the stop gates ignore «أراقبه» claims. Reconcile it with `trace-guards.md`.
- `docs/architecture/decisions/0001-agent-first-evolution.md:17-19` sets the rules of no second runtime and the voice handoff.

**Where to look.** The four docs, against `packages/agent-runtime/src/lonora_agent/tool_dispatch.py`, `tool_guardrails.py`, `stop_gates.py`, `packages/voice/src/lonora_voice/realtime.py`.

### Gap 5: ui-capabilities-block (genui_capabilities.py)

**What is missing.** When `LONORA_GENUI_V2` is on (`packages/agent-runtime/src/lonora_agent/skills/visual_policy.py:21-22`), every model request carries a system block (`packages/agent-runtime/src/lonora_agent/model_runtime.py:81-90`) with:

- `delivery: app` only (`packages/agent-runtime/src/lonora_agent/genui_capabilities.py:21`). This conflicts with the Telegram mirroring found in J3-08, and it is a source of "I can't message you outside the app".
- A language set to `ar` only when the owner's newest text contains Arabic letters, otherwise `en` (`packages/agent-runtime/src/lonora_agent/visual_response.py:601-603`). A voice note transcribed in Latin-script Turkish, as in production, would get `language: en`.

UNSURE: whether `LONORA_GENUI_V2` was on in production. Neither `production-trace.md` nor any file states it. Only causes are wanted here, because the voice-language fix belongs to another session.

**Where to look.** `genui_capabilities.py`, `visual_response.py:580-603`, `model_runtime.py:81-90`, and the production environment settings (ask the lead).

### Gap 6: none further worth an assignment

Group-thread modules and `packages/automation/scheduling.py` are uncited but low impact for this complaint.

---

## Verification log

Every citation above was re-opened in this pass:

- `attachments.py:37-53`, `builder.py:150-152`, `:186-213`, `:276-283`
- `semantic.py:55`
- `realtime.py:34-44`, `:245`, `:424`, `:459`, `:463`
- `genui_capabilities.py:21-24`, `visual_response.py:601-603`, `model_runtime.py:81-90`, `visual_policy.py:21-22`
- `incoming_call.py:129`, `binding.py:6`
- docs: `agent-memory-and-recall.md:393-400`; `NANOBOT_PARITY_AND_RELIABILITY_PLAN.md:126`, `:132`, `:133`; `NANOBOT_ARCHITECTURE_STUDY.md:60`; `AGENT_HARNESS_SOURCE_REVIEW.md:15`; `0001-agent-first-evolution.md:17`, `:19`
