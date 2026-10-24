# Simple autonomous trading teammate

Owner clarification, 2026-10-23. This supplements [prompt 1.md](<prompt 1.md>)
and the existing specifications; it does not replace their unfinished requirements.
This document records the requested behavior, not completed implementation.

## Latest clarification: model-owned judgment

The 2026-10-24 clarification makes the LLM the analysis and decision owner.
Algorithms provide data, calculations and wake observations; no predefined
pattern catalog may become a universal entry prerequisite. The Agent can judge
developing structures while describing their actual confirmation state honestly.
BUY/SELL and natural-language conditional entry are the ordinary planning choices.
WAIT remains readable for existing history and available for a justified
abstention. The expressed preference for rare abstention is not an implementation
quota or permission to fabricate an opportunity when data is unavailable.

Only the previously proposed consistency harness was accepted. Confidence
calibration, teaching examples, counterfactual comparison, additional reference
feeds, instrument lifecycle and beginner training are not added requirements.
Inspect and reuse actual Hermes/Nanobot code where it improves the existing loop;
remove unnecessary coupling rather than introduce a second Agent framework.

## Product and architecture

One continuing trading Agent observes, reasons, acts, verifies and resumes work.
Text, native Live voice, charts and background monitoring share its conversation,
memory, tools, durable tasks and account authority. Keep the existing Gateway,
broker adapters, executor, journal, workspace and Skill lifecycle.

Use nanobot's compact organization and capability discovery as the architectural
reference. Claude Code and Grok Bot illustrate capable tool-driven work and a
simple interaction surface; they are not additional runtimes or evidence that
Lonora supports arbitrary integrations. Prefer improving existing components over
introducing a service, manager or table for each item below.

The Agent has an isolated analytical terminal and persistent files. It can inspect
data, write and test analytical procedures, diagnose errors and reuse verified
procedures. Dependencies and external access remain reviewed capabilities.
Broker mutations always use the existing typed financial executor.

## One authorization, autonomous decisions

Latest owner clarification: do not impose default financial restrictions or make
the owner complete a risk-settings form. The owner connects/selects an account,
reviews a concise full-management authorization and authenticates once. The Agent
then chooses opportunities, direction, lot size, stops, targets and management
actions without per-trade approval. Existing positions must be visibly included
in the reviewed scope if management of them is granted. Pause/revocation remains
immediately accessible; owner intervention takes precedence.

Do not invent lot caps, trade-count quotas, daily-loss amounts, short grant
expirations or default market selections. Optional owner-imposed limits belong
in advanced settings and apply only when explicitly selected. No selected
monetary limit means no product-enforced monetary loss ceiling; disclose that
plainly during the initial review. Agent risk judgments remain decisions, not
guaranteed protection. The owner need not choose each entry or fill out a Goal.
Changing the actual account/action scope or removing an explicitly chosen limit
requires authenticated owner intent; routine trading decisions do not.

"Unrestricted based on intelligence" means broad analytical initiative and
discretion within the owner's financial mandate. It does not mean shell access
to broker secrets, self-granted permission or bypassing ownership, broker validity,
revocation, operation identity or uncertain-execution reconciliation. Those
technical correctness checks are not arbitrary trading quotas.
"Without the user's knowledge" means no need for advance interaction on each
authorized operation, including while offline; execution remains recorded,
visible and included in the owner's configured notifications. It must never mean
concealed trades. This specification does not activate production trading.

This supersedes mandatory numeric-budget setup in earlier planning text. The
explicit versioned full-management scope is implemented alongside existing bounded
grants; current evidence is recorded in the implementation matrix. Never
reinterpret a missing field in an old grant as unlimited permission, silently
upgrade an existing grant, or remove executor checks to simulate the new mode.

## Complete mapping of the 27 requested behaviors

| Owner item | Required behavior | Existing foundation / remaining acceptance |
| --- | --- | --- |
| 1 | Execute trades for the owner | Existing trade tools/executor; verify autonomous end-to-end behavior within the explicitly selected account-management scope |
| 2 | Review the actual market | Existing market reads, detectors and decision evidence; broader source quality and model acceptance remain |
| 3 | Create work from observed market movement | Existing Tasks, Watches and Gateway wakes; verify meaningful event-to-task creation, deduplication and continuation |
| 4 | Recommend trades when justified | Existing separate market assessment/entry/execution readiness; verify recommendations use current evidence and clear invalidation |
| 5 | Follow multiple positions concurrently | Existing account/position reads and scoped work; test shared exposure, independent monitoring and serialized conflicting mutations |
| 6 | Discover a rule-based trading approach | Existing workspace, reusable procedures and bounded research; arbitrary strategy validation and promotion remain incomplete |
| 7 | Identify swing highs and lows | Strict confirmed closed-bar swings implemented with explicit windows/tie policy and availability times; all21 timeframes/four asset classes verified (M-D3) |
| 8 | Compare trend lines and evolving formations | Alternative same-side pivot lines, anchors, touches and closed-price breaks verified through existing chart drawings; wider evolving formations remain open |
| 9 | Draw on the live chart | Existing attributed drawings, chart state and artifacts; verify drawings against actual chart state and visual observation |
| 10 | Pursue a capital-growth goal | Existing durable Goals and Tasks; implement bounded risk-aware progress and adaptation, without promising target returns |
| 11 | Act with broad discretion | Model-selected tools and analytical workspace; discretion cannot enlarge the signed financial envelope |
| 12 | Choose stop loss from analysis | Existing trade parameters and instrument constraints; validate structural invalidation and monetary risk before submission |
| 13 | Choose profit taking from market movement | Existing management tools; verify dynamic management uses fresh evidence and respects authorized operations |
| 14 | Use multiple profit targets | Reuse durable plan steps and partial closure; honor broker volume steps/minimum remainder and reconcile each partial fill; do not assume native multi-TP support |
| 15 | Choose lot size independently | Existing broker-economics sizing estimate; explicit full-management scope and optional owner-set monetary ceilings remain |
| 16 | Avoid unsuitable entry times | Reuse calendar, market health and execution checks; verify spreads, events, session/holiday constraints and evidence quality |
| 17 | Know market session and ending time | Use timezone/DST-aware session definitions and actual broker hours; do not assume named regional sessions equal broker availability |
| 18 | Protect winning positions by moving stops | Existing modification path; verify risk-reducing changes, broker distances, owner intervention and actual confirmation; gaps/slippage prevent guaranteed locked profit |
| 19 | Consult fellow Agents | Existing bounded peers/subagents and outcome return; verify evidence consolidation, deadlines and cancellation without authority transfer |
| 20 | Create a discussion group with colleagues | Reuse existing groups/membership/collaboration; verify Agent-callable creation and discussion lifecycle rather than assuming a UI endpoint proves this behavior |
| 21 | React to reversal or sudden market change | Existing watches and position management; fresh reanalysis and authorized protective action, no stale automatic reversal or risk expansion |
| 22 | Recognize candle and chart formations | Six existing candle definitions have62 positive/negative/boundary/lifecycle cases; broader formations remain open; no claim of knowing every possible pattern |
| 23 | Decide not to trade | Existing readiness and health boundaries; verify evidence-backed abstention and useful next observation instead of reflexive WAIT |
| 24 | Decide when sufficient profit warrants exit | Existing full/partial close; verify thesis, costs, exposure and fresh state inform the decision |
| 25 | Avoid greed, revenge and emotional trading | Evaluate losses, exposure, trading frequency and evidence before acting; enforce any owner-selected limits; model personality alone is not protection |
| 26 | Trade after one owner approval | Existing signed persistent volume/activity scope; implement explicit full-management scope, optional limits, recovery and actual-device acceptance |
| 27 | Initiate trades while the owner is away | Existing resident Gateway and persistent state; bounded proactive execution with transparent journal/results, never hidden trades |

## Current focus: one complete trading teammate

The owner's latest clarification prioritizes a comprehensible, capable product
over further feature expansion. Preserve the requirements above and in prompt 1;
sequence them around one complete trading mission. This is a priority decision,
not a claim that all requested behavior already works.

Read-only source comparison used nanobot revision
`df63526ddfb3674619231f0daf4d25ba3c8b7e54` (2026-10-22) and Lonora
`1e5406f`. Nanobot already has substantial session/channel/runtime infrastructure.
Adopt its small operating contract: compact identity and memory, discoverable
procedures, one action/observation loop and background work returning to that
same Agent. Do not import a second engine, scheduler or state store.

### Findings to address in the existing owners

| Finding | Existing implementation | Next bounded work |
| --- | --- | --- |
| The persistent core already exists | `lonora_agent/runtime.py`, `tool_loop.py`, `context/builder.py`; existing memory and Skills | Fix measured continuity failures in this loop; retain one primary conversation |
| Management and Goal authority differ | `lonora_trading/account_authority.py` explicitly excludes Goal-linked Runs; full management starts an existing Task | Make the default management journey coherent; resolve Goal compatibility deliberately, preserving exact existing signed scopes and old-grant semantics |
| Waiting and resumption already exist | `lonora_tools/market_watch.py`, `lonora_market/watchers.py`, `lonora_db/task_wait.py` | Test one mission through deduplicated wake, restart and fresh reanalysis; do not add another monitoring loop |
| Skills are progressive but tool schemas are broad | `lonora_agent/context/skills.py`; `tool_loop.py` passes registry definitions, currently106 tools | Measure selection accuracy, input tokens and latency; use the existing registry for selective discovery only if the evaluation supports it |
| Each Agent already has persistent analytical files and isolated execution | `lonora_agent/workspace.py`, `workspace_client.py`, `workspace_host.py` | Use on-demand computation; defer a general desktop until an actual trading task demonstrates the need |
| Behavioral acceptance is narrower than infrastructure coverage | Existing scripted Agent, simulation and recovery checks; matrix M-B/M-F/M-T/M-J remain open | Evaluate the configured model's understanding and initiative separately from deterministic correctness checks |

Keep current financial verification, ownership, revocation, exact symbols,
serialization and reconciliation. These are execution correctness, not arbitrary
trading quotas. Any compatibility change needs explicit scope checks and regression
tests; this audit does not remove the existing Goal authority boundary.

### First completion checkpoint

One scenario follows the same Agent and management Task from a natural-language
objective through current account/market inspection, justified alternatives and
sizing, a saved watch, client closure, meaningful wake, revalidation, authorized
execution, independent broker verification, position management and a concise
owner update. Include a valid no-trade outcome and preserve the objective after
a temporary failure. A background wait must exist durably before it is promised.

Test this in the existing simulation and disposable-database infrastructure,
including duplicate wakes, restart, unknown execution results, owner intervention
and revocation. Then evaluate actual model behavior against the same controlled
market environment, without live-money mutation. A scripted model proves runtime
behavior; it does not prove the configured model understands the conversation.

The behavioral suite must include the owner's earlier failing conversation:
retain the chosen plan and risk answer across turns, interpret a short reply in
its conversational context, choose direction and size when the granted mandate
allows it, and request only genuinely missing information. When a question is
needed, use context-specific choices plus free text. Check language consistency,
evidence-backed claims, useful continuation, unnecessary questions, elapsed time
and model usage. Every claim of execution must trace to verified broker state.

### Computer and expansion policy

Private files, memory and isolation belong to each Agent; CPU/RAM can be allocated
only while computation runs. A future browser or desktop adapter would supply
observations and actions through the same runtime. Broker mutations remain in
the shared financial executor, including when several Agents collaborate.
Do not grant shell access to broker credentials to imitate a computer-using bot.

After the first checkpoint, expand session/formation evidence, validated strategy
research, multi-position/peer acceptance and native background behavior according
to measured failures and owner value. These requirements remain open. Broader
imports, additional integrations and a fleet of desktops are not prerequisites
for the first complete mission. No new runtime or mandatory user workflow is
introduced by this refocus.

Mandatory acceptance includes offline/paper testing of automatic sizing and
entries, multiple positions and targets, no-trade conditions, DST/holidays,
partial fills, source loss, duplicate wakes, revocation and restart. Verify that
the exact financial scope is enforced and that each claimed effect exists at the
broker. Simulation success does not establish production/provider readiness.

See [implementation matrix](IMPLEMENTATION_MATRIX.md) for the current scoped
evidence. Full 27-item acceptance is open. Existing MetaApi service billing and
undeployed accounts remain external production prerequisites, not evidence that
the analytical or execution features are complete.
