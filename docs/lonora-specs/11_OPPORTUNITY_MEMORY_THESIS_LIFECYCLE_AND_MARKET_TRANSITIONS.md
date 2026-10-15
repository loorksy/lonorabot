PROJECT: Lonora (`loorksy/lonorabot`)

IMPORTANT:
- Implement, do not stop at an architecture report.
- Inspect the current repository before changing code. Do not assume conceptual names in this prompt already exist.
- Reuse existing Lonora primitives. Do not build a parallel runtime, event bus, broker ledger, or trading executor.
- Preserve Trading ON/OFF, Emergency Stop, ownership checks, authorization, risk controls, exact broker symbols, idempotency, journal, locking, and reconciliation.
- Never fabricate unavailable market, account, order-flow, execution, correlation, or performance data. Mark unavailable data as unavailable.
- Keep existing global model routing; do not introduce per-Agent provider/model selection.
- Keep Arabic-first/RTL compatibility.
- Do not mention paid API/token/key requirements.
- Work on a dedicated branch and add focused tests.


# 11 — Opportunity Memory, Thesis Lifecycle, and Market Transition Intelligence

## Objective
Make Lonora remember how a trading opportunity evolves over time instead of rebuilding the same setup from zero on every wake.

Add a durable thesis lifecycle including expiry/decay/invalidation, and detect market phase transitions instead of only assigning a static regime label.

## Inspect first
Reuse current:
- MarketWatch persistence/runtime
- TradingGoal state/decisions
- market snapshots/candles
- chart/indicator evidence
- event/wake flow
- recommendation/evidence structures created by the Super Bot work

Do not build a second watch runtime.

## Opportunity identity
A live opportunity needs a durable identity tied to:
- owner
- Agent
- account when relevant
- exact symbol
- timeframe/context
- setup/thesis
- originating watch/evidence
- creation time

Do not create a new opportunity on every wake when it is still the same setup.

## Opportunity memory
Persist meaningful evolution:
- first detected
- forming
- evidence added
- evidence contradicted
- confirmed
- degraded
- invalidated
- expired
- acted on
- completed/closed

Store transition evidence and timestamps.

## No analysis reset
On wake:
- load current opportunity/thesis
- load new evidence since last evaluation
- revalidate assumptions
- update the same opportunity when appropriate

Do not force the model to reconstruct history from chat.

Memory is context, not authority. Fresh data always wins for action.

## Thesis lifecycle
Preserve:
- bias/direction
- rationale
- supporting evidence
- contradicting evidence
- entry condition
- invalidation condition
- target logic
- created_at
- last_validated_at
- status
- expiry/decay policy
- version/history

Use existing thesis terminology if Prompt 03 already added it.

## Thesis expiry
A thesis can expire without stop-loss being hit.

Valid reasons may include:
- expected move did not occur within its defined horizon
- regime changed
- structure changed
- key event passed
- confirmation aged out
- new contradictory evidence invalidated the assumptions

Expiry must be explicit and evidence/rule driven.
Do not let the LLM arbitrarily expire a thesis without a recorded reason.

## Thesis decay
Where useful, represent decreasing relevance separately from hard invalidation.

Do not invent one global decay formula.

A setup may define deterministic expiry by:
- elapsed time
- number of candles
- session boundary
- event boundary
- other versioned strategy condition

## Reason-for-change history
Persist why Lonora changed state/opinion:
- BUY bias → WAIT
- WAIT → BUY
- BUY thesis → INVALIDATED
- CONFIRMED → EXPIRED

The owner must be able to ask why the view changed and receive a stored evidence-based answer.

## Market transition intelligence
Detect transition candidates and confirmations, not only current regime.

Examples:
- accumulation → expansion/markup
- trend → distribution
- distribution → markdown
- range → breakout
- breakout → failed breakout/re-entry
- trend → range
- high volatility → normalization

These examples are not universal truths.
Use deterministic evidence from actual structure/volatility/price-action engines.

## Transition record
Track:
- previous regime
- candidate next regime
- transition evidence
- evidence quality
- first observed
- confirmed/invalidated
- observed_at

Candidate transition != confirmed transition.

## Watch integration
Dynamic Watches may monitor:
- thesis invalidation
- thesis expiry
- regime transition
- opportunity confirmation
- opportunity degradation

Use event-driven wake.
No LLM on every tick.

## Quality after confirmation
Confirmed opportunities remain monitored until execution/expiry.

If:
- spread deteriorates
- price drifts too far
- structure changes
- new contradiction appears
- confirmation becomes stale

mark degraded/revalidate rather than blindly execute.

Prompt 09 should consume this state.

## Context budget
Load only the active/relevant opportunity and enough recent transition history to explain/update it.
Do not inject all historical setups every turn.

## Tests
Cover:
- same setup keeps one identity across wakes
- FORMING → CONFIRMED → INVALIDATED history persists
- restart restores active thesis/opportunity
- fresh data can override remembered thesis
- explicit expiry works without SL hit
- reason for opinion change retrievable
- transition candidate differs from confirmed
- transition can invalidate
- watch wakes on meaningful transition
- no LLM-per-tick loop
- confirmed opportunity can degrade
- stale confirmation cannot remain actionable forever

## Definition of done
Lonora remembers each live opportunity as a durable evolving object, can explain why its thesis changed, can expire stale ideas without waiting for stop-loss, detects market-regime transitions, and reuses history on later wakes while still revalidating fresh data.
