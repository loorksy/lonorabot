# Simple autonomous trading teammate

Owner clarification, 2026-10-23. This supplements [prompt 1.md](<prompt 1.md>)
and the existing specifications; it does not replace their unfinished requirements.
This document records the requested behavior, not completed implementation.

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

The owner reviews one clear account scope and risk budget, authenticates once,
and may subsequently pause or revoke it. The Agent chooses opportunities,
direction, size, stops, targets and management actions inside that scope without
asking for each trade. No predeclared full Goal workflow is needed to grant scope.
Risk or scope expansion requires a new authenticated review; ordinary analytical
decisions do not. Existing manually opened positions retain explicit management
scope and owner intervention takes precedence.

"Unrestricted based on intelligence" means broad analytical initiative and
discretion within the owner's financial mandate. It does not mean shell access
to broker secrets, unbounded losses, self-granted permission or disabling controls.
"Without the user's knowledge" means no need for advance interaction on each
authorized operation, including while offline; execution remains recorded,
visible and included in the owner's configured notifications. It must never mean
concealed trades. This specification does not activate production trading.

## Complete mapping of the 27 requested behaviors

| Owner item | Required behavior | Existing foundation / remaining acceptance |
| --- | --- | --- |
| 1 | Execute trades for the owner | Existing trade tools/executor; verify autonomous end-to-end behavior within the completed monetary envelope |
| 2 | Review the actual market | Existing market reads, detectors and decision evidence; broader source quality and model acceptance remain |
| 3 | Create work from observed market movement | Existing Tasks, Watches and Gateway wakes; verify meaningful event-to-task creation, deduplication and continuation |
| 4 | Recommend trades when justified | Existing separate market assessment/entry/execution readiness; verify recommendations use current evidence and clear invalidation |
| 5 | Follow multiple positions concurrently | Existing account/position reads and scoped work; test shared exposure, independent monitoring and serialized conflicting mutations |
| 6 | Discover a rule-based trading approach | Existing workspace, reusable procedures and bounded research; arbitrary strategy validation and promotion remain incomplete |
| 7 | Identify swing highs and lows | Reuse market evidence and chart anchors; verify declared swing definitions, timeframes and confirmation timing |
| 8 | Compare trend lines and evolving formations | Reuse chart drawings and analysis; preserve alternative hypotheses, supporting anchors and invalidation without inventing certainty |
| 9 | Draw on the live chart | Existing attributed drawings, chart state and artifacts; verify drawings against actual chart state and visual observation |
| 10 | Pursue a capital-growth goal | Existing durable Goals and Tasks; implement bounded risk-aware progress and adaptation, without promising target returns |
| 11 | Act with broad discretion | Model-selected tools and analytical workspace; discretion cannot enlarge the signed financial envelope |
| 12 | Choose stop loss from analysis | Existing trade parameters and instrument constraints; validate structural invalidation and monetary risk before submission |
| 13 | Choose profit taking from market movement | Existing management tools; verify dynamic management uses fresh evidence and respects authorized operations |
| 14 | Use multiple profit targets | Reuse durable plan steps and partial closure; honor broker volume steps/minimum remainder and reconcile each partial fill; do not assume native multi-TP support |
| 15 | Choose lot size independently | Existing broker-economics sizing estimate; authoritative signed monetary ceilings and account-wide risk enforcement remain |
| 16 | Avoid unsuitable entry times | Reuse calendar, market health and execution checks; verify spreads, events, session/holiday constraints and evidence quality |
| 17 | Know market session and ending time | Use timezone/DST-aware session definitions and actual broker hours; do not assume named regional sessions equal broker availability |
| 18 | Protect winning positions by moving stops | Existing modification path; verify risk-reducing changes, broker distances, owner intervention and actual confirmation; gaps/slippage prevent guaranteed locked profit |
| 19 | Consult fellow Agents | Existing bounded peers/subagents and outcome return; verify evidence consolidation, deadlines and cancellation without authority transfer |
| 20 | Create a discussion group with colleagues | Reuse existing groups/membership/collaboration; verify Agent-callable creation and discussion lifecycle rather than assuming a UI endpoint proves this behavior |
| 21 | React to reversal or sudden market change | Existing watches and position management; fresh reanalysis and authorized protective action, no stale automatic reversal or risk expansion |
| 22 | Recognize candle and chart formations | Extend tested, documented formation definitions; distinguish forming, confirmed and invalidated patterns; no claim of knowing every possible pattern |
| 23 | Decide not to trade | Existing readiness and health boundaries; verify evidence-backed abstention and useful next observation instead of reflexive WAIT |
| 24 | Decide when sufficient profit warrants exit | Existing full/partial close; verify thesis, costs, exposure and fresh state inform the decision |
| 25 | Avoid greed, revenge and emotional trading | Enforce measurable loss/exposure/frequency limits, cooldowns and evidence requirements; model personality alone is not protection |
| 26 | Trade after one owner approval | Existing signed persistent volume/activity scope; finish monetary limits, recovery and actual-device acceptance |
| 27 | Initiate trades while the owner is away | Existing resident Gateway and persistent state; bounded proactive execution with transparent journal/results, never hidden trades |

## Dependency-aware completion

1. Complete signed per-entry monetary risk and account-wide daily-loss accounting
   on the existing executor. Reuse current exact-account tick economics and fresh
   final preflight. Keep reductions, cancellation and emergency controls usable.
2. Validate one complete trading mission: observe -> form alternatives -> plan
   risk/size -> watch -> revalidate -> execute -> reconcile -> manage partial
   exits -> review. Restart, owner intervention and uncertain effects are part of
   the same acceptance, not separate trading engines.
3. Extend market/session/pattern evidence and strategy research using the existing
   workspace and Skills. Test rules, data provenance, out-of-sample behavior and
   shadow performance before allowing a researched strategy to use live scope.
4. Verify multi-position and peer/group collaboration using existing ownership,
   account serialization, shared risk and bounded result consolidation.
5. Complete native voice/background calling and real device/provider acceptance
   from prompt 1. Keep the owner interface to conversation, chart, account/risk,
   active work and clear pause controls.

Mandatory acceptance includes offline/paper testing of automatic sizing and
entries, multiple positions and targets, no-trade conditions, DST/holidays,
partial fills, source loss, duplicate wakes, revocation and restart. Verify that
the exact financial scope is enforced and that each claimed effect exists at the
broker. Simulation success does not establish production/provider readiness.

See [implementation matrix](IMPLEMENTATION_MATRIX.md) for the current scoped
evidence. Full 27-item acceptance is open. Existing MetaApi service billing and
undeployed accounts remain external production prerequisites, not evidence that
the analytical or execution features are complete.
