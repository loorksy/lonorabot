# LLM-owned trading: source review and integration

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
