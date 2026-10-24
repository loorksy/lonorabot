# LLM-owned trading: source review and integration

## Continuous-work implementation after the structural audit

The first structural finding is now addressed in code: full-management activation
creates continuous work; an ordinary model answer cannot complete that Task.
Generic bounded Tasks retain finite completion by default. Legacy running
account-management work is recognized by its existing grant-bound Run metadata;
historical terminal work is neither revived nor granted new permission.

The typed `StopGateVerdict` and bounded structural protocol nudge adapt actual
Hermes `agent/turn_stop_gates.py`, at the pinned revision below. The complete MIT
notice ships in `lonora_agent/stop_gates.py`. Unlike the reference's unrelated
coding gates, Lonora checks its real persisted Task identity and requires actual
suspension. No English intent regex or claim such as "I will monitor" proves a
continuation. Two checkpointed nudges bound a review; exhaustion is an inspectable
plan-repair failure, not fake completion or endless self-polling.

Nanobot's sustained-goal and bounded-continuation separation informed the
existing slice contract and the distinction between finishing an answer and
finishing work. No new Nanobot engine or local session database was imported.
The existing PostgreSQL wait/wake path now publishes a concise originating
model update only after accepting its actual wait, with a stable receipt across
worker replacement. Owner controls and steering can supersede it. Unexecuted
siblings are explicitly cancelled before sleeping, including legacy checkpoints;
fresh market evidence must precede a new decision after waking.

This is one capability integrated into the same Agent. Board/Ticket coupling,
Task/Goal lifecycle convergence, approval ownership and reverse package imports
identified below remain separate restructuring work. Persistent checkpoint
history also needs periodic bounded consolidation for indefinite service life;
bounded model slices alone do not bound the stored history across every wake.

Review date: 2026-10-24. Lonora baseline: `825e794`, integration branch
`codex/agent-architecture-audit`. This review follows the owner's clarification:
the model analyzes and decides; the harness supplies context, capabilities,
persistence, observations and verified execution.

## Actual checkouts and provenance

Fresh shallow source checkouts were downloaded beside Lonora, not installed as
dependencies or copied wholesale into the product:

| Repository | Local checkout | Inspected revision | License |
| --- | --- | --- | --- |
| NousResearch/hermes-agent | `/workspace/hermes-agent` | `c78ca093aa4b6759c055c3ed2bfbe7f741cf0292` | MIT |
| HKUDS/nanobot | `/workspace/nanobot` | `3c022ada6ac60f3a378aec583056b24e11188134` | MIT |

The public GitHub metadata request reported 256,666 Hermes stars and 49,322
nanobot stars during this review; both satisfy the owner's preferred size.
Popularity is discovery metadata, not evidence of implementation quality.
OpenAI Codex metadata was also checked (130,754 stars, Apache-2.0); its source
was not audited in this wave. No upstream installation/test execution is claimed.

## Source comparison

| Actual reference code | Actual Lonora code | Decision |
| --- | --- | --- |
| Hermes `tools/tool_search_catalog.py`: tokenization, corpus statistics, BM25 scoring and bounded search; `tools/tool_search.py:assemble_tool_defs` | `lonora_tools/registry.py:definitions`, `lonora_agent/tool_loop.py:model_turn` currently expose the complete permitted schema set | Adapt the small scoring/discovery component with MIT attribution into the existing environment inspector; persist discovered exact schemas in the existing Run checkpoint |
| Hermes `agent/turn_tool_round.py`, `agent/turn_final_response.py` | Existing fenced ToolLoop, receipts and final-response handling | Retain effect durability. Do not import English-only intent regexes, reasoning-to-public-text fallback or provider-specific mutable orchestration |
| Hermes `agent/repetition_guard.py` | Existing model/provider response handling | Standalone copy candidate, not needed for the measured defects in this wave; not imported |
| Nanobot `nanobot/session/turn_continuation.py:maybe_continue_turn`, `nanobot/agent/runner.py` | ToolLoop round limit currently fails the Run with pending last-round calls | Adapt bounded slices through the same durable Task/Run and existing claimant; retain pending calls, receipts, original operation identities and owner steering |
| Nanobot `nanobot/agent/tools/registry.py` and `nanobot/agent/context.py` | Existing registry and progressive Skill context | Nanobot also sends all cached tool definitions. Its progressive Skills already have a Lonora equivalent; do not misattribute progressive tool schemas to Nanobot |

Hermes is not uniformly small: its `AIAgent` composes fourteen mixins, and the
inspected conversation loop, runtime helpers and auxiliary client contain
substantial compatibility machinery. Neither upstream is a reason to replace
working broker verification or owned PostgreSQL state with local sessions.
Source reuse is selected per component and tested against Lonora's semantics.

## Analysis boundary corrected in this wave

The audited `MarketViewRequest` required a predefined supporting detector.
`decision_readiness` changed a model's bias to insufficient evidence unless that
detector was confirmed. Separately, `market_decision_record` rewrote the requested
action to WAIT when unrelated account/order reads failed. These are distinct from
the actual financial executor and are unnecessary restrictions on interpretation.

The replacement contract keeps model intent, optional measured observations and
execution availability separate. BUY/SELL can express a sourced discretionary
judgment without a named pattern. CONDITIONAL_ENTRY records direction, a natural
language condition, invalidation and reassessment instruction. It is not an
executable order or proof that monitoring has started. Existing watch/Task waits
provide the real wake; the same model then inspects fresh evidence and decides.
Old WAIT records and durable operation fingerprints must remain readable.

The model may analyze a forming structure. It may not relabel the forming
observation as a closed-bar fact. A missing source is explicit unavailability,
not a generated price, automatic directional opinion or forced trade. No numeric
BUY/SELL/WAIT frequency quota is introduced.

## Harness integration boundaries

- Discovery searches only the caller's allowed catalog. The same registry,
  financial authority and exact broker scope execute native calls. Discovery
  never installs tools or grants permission.
- Schema selection survives checkpoint/restart. Public-output filtering still
  knows the complete first-party tool-name inventory.
- Slice continuation belongs to a genuine durable Task. Worker release does not
  create a new financial operation or erase total compute-budget accounting.
- Skills and compact guidance describe model-owned judgment and actual
  conditional review. No separate market thinker, Agent engine or scheduler is
  introduced.
- Existing Goal/account authority compatibility remains a separate unfinished
  issue; no signed grant is silently broadened by this integration.

## Verification boundary

Acceptance must exercise actual AgentRuntime, disposable PostgreSQL and a
simulation broker: discovery -> persisted schemas -> restart; Arabic/English and
contextual follow-ups; conditional plan -> durable wait -> fresh reassessment;
verified execution versus invalidated condition; duplicate wake, revoked scope,
stale lease and finite continuation. Scripted providers test harness behavior and
context, not the independent judgment quality of a deployed LLM.

Current test outcomes and remaining work belong in PROGRESS.md and the
implementation matrix. This source review alone does not mark the integrated
product or the upstream runtimes verified. Production financial mutations and
native application builds are outside this audit.

## Structural ownership review at b7f24cc — 2026-10-24

The owner explicitly challenges the existing tree/framework. Prior investment
and passing tests do not establish that the current decomposition is the best
product architecture. This follow-up inspected source and AST imports; it did
not modify runtime behavior or reproduce these findings against production.

The26 package directories are not26 services: pyproject.toml builds one Python
distribution. An AST pass over548 first-party Python files found package-level
dependency cycles in contracts/core, db/session/bus, adapters/market/charts/trading
and Agent/tools/voice. The pass includes local and TYPE_CHECKING imports; it
identifies architectural dependencies, not necessarily import-time failures.
Folder count and line count are not themselves defects.

| Evidence in actual code | Structural consequence | Target ownership |
| --- | --- | --- |
| `lonora_auth/account_authority.py` starts management with an empty-step Task; ToolLoop accepts final prose; `lonora_db/runs.py:complete_run` checks declared steps; `lonora_agent/collaboration/outcome_return.py` maps completed Run to completed Task | A response/turn can structurally finish supposedly ongoing management, including when no durable monitor was established | Separate response/attempt completion from persistent work completion; continuous management ends on its defined terminal condition or owner stop |
| `lonora_db/tasks.py:create_task` creates BoardRow, work ThreadRow, TicketRow and RunRow; legacy ticket startup has its own entry path | Background work depends on board presentation and competing start/control mechanisms | One logical task lifecycle; boards/tickets display work rather than define its execution |
| Goal wait creates its own watch/routine and updates Goal state; Task wait retains its checkpoint; market watcher branches between new-Run and resumed-Run paths | Different continuation/recovery semantics depend on how the same objective was started | One persistent work owner for wait/wake/control; retain trading plans and signed Goal envelopes as domain data during an explicit migration |
| `lonora_agent/tool_loop.py:139` mutates TradeApprovalRow and interprets `_runtime_*` dictionaries; tools reverse-import Agent implementations | The generic loop, trading internals and tools depend on each other through implicit control messages | Typed tool/control outcomes and one narrow injected Agent-actions boundary; trading owns financial cancellation |
| `lonora_db/tasks.py` accepts financial step evidence with status confirmed; `lonora_agent/context/financial_result.py` also requires independent verification | Different layers can disagree about what constitutes financial completion | One typed verified execution outcome, consumed by task state and public presentation |
| API imports shared OwnerServices from Gateway; Worker and migration setup import settings from `lonora_api.env` | Composition/configuration are physically owned by application entry points that do not own their behavior | One shared application bootstrap; API and Worker remain entry points |

Keep distinct responsibilities that reflect real facts: Agent identity, bounded
execution attempts, durable work, source observations, broker operations and
their execution journal. Simplification must not merge these into an ambiguous
status field or delete historical identity/receipts. Existing SkillAccess and
WorkspaceAccess demonstrate useful injected boundaries already in the code.

The provisional logical shape is Agent/harness, durable runtime, trading
environment, interfaces and infrastructure. This is an ownership direction,
not a completed file move or a new mandatory framework. Define the response/work
completion contract first, migrate one full management mission through it, then
remove obsolete lifecycle paths and consolidate files where that clarifies the
actual responsibilities. Original requirement coverage remains tracked.
