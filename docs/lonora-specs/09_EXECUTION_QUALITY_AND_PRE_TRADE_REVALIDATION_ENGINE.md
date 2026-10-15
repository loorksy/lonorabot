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


# 09 — Execution Quality and Pre-Trade Revalidation Engine

## Objective
Add a server-side execution-quality layer that decides whether an otherwise valid setup is still executable at the exact moment of action.

A correct thesis is not enough if:
- spread widened
- price moved too far from the planned entry
- confirmation became stale
- execution conditions deteriorated
- new contradictory evidence appeared
- account state changed

This layer must sit before broker mutation and measure actual execution afterward.

## Inspect first
Reuse the current:
- trade preflight
- instrument metadata
- trading journal
- idempotency
- locking/serialization
- reconciliation
- approval/authority checks
- account/symbol binding
- quote/market tools

Do not create a second executor.

## Planned execution snapshot
When a recommendation becomes actionable, preserve:
- exact symbol
- direction
- planned entry/zone
- planned stop
- planned targets
- planned risk/size
- quote observed_at
- spread if available
- thesis id/version
- evidence version/snapshot
- confirmation timestamp/expiry

## Pre-trade revalidation
Immediately before broker submission refresh the authoritative values required to verify the opportunity:
- latest bid/ask/quote
- spread
- distance from planned entry/zone
- relevant candle/watch confirmation
- thesis invalidation state
- data freshness
- account state/exposure
- existing positions/orders
- Trading ON/OFF
- Emergency Stop
- risk limits

Never execute from a stale analysis snapshot alone.

## Entry deterioration
Detect when the current price has moved enough that the planned opportunity is no longer the same trade.

Use deterministic, strategy/volatility-aware tolerance from real inputs that exist, such as:
- ATR/volatility
- spread
- timeframe
- entry-zone width
- stop distance

Do not use one universal arbitrary pip threshold.

## Spread quality
Measure current spread against a valid configured/recent reference when one exists.

If no reliable baseline exists, return unknown instead of inventing "normal spread".

Allow server-side blocking when spread violates a configured safe limit.

## Liquidity/execution condition
Use only data the broker/feed actually supplies.

Do not claim centralized order-book liquidity for spot/CFD instruments when unavailable.

Possible evidence only when present:
- spread expansion
- quote gaps
- stale quotes
- abnormal update behavior
- broker-provided depth/volume

Unavailable means unavailable.

## Confirmation freshness
CONFIRMED is not permanent.

Before execution:
- valid/fresh → continue
- stale → re-confirm/reassess
- invalidated → block
- important new contradiction → reassess/WAIT

## Server-side result
Produce a machine-readable execution-quality result equivalent to:
- EXECUTABLE
- REVALIDATE
- BLOCKED
- EXPIRED
- INVALIDATED

Include structured reasons and observed values.

The LLM cannot override a blocked server-side result.

## Actual execution quality
After real execution record only what is actually observable:
- planned/requested price when meaningful
- submit/accepted time available to Lonora
- actual fill price
- fill time if supplied
- spread at submission if available
- measured slippage
- requested vs actual volume
- broker identifiers

Do not invent unobservable latency stages.

## Slippage
Calculate from known real values and handle BUY/SELL direction correctly.
Keep units explicit and use instrument metadata for conversions when supported.

## Bad/late fill
Record deterioration objectively.
Do not automatically label every negative slippage as broker failure.

Ambiguous broker result:
- use existing reconciliation
- never blind resend

## Opportunity cancellation
If execution quality degrades before submission:
- block/cancel the planned action
- persist the reason/current observations
- return to WAIT/reassessment when appropriate

Do not place an order merely because the recommendation was previously valid.

## Super Bot flow
Required order:

THESIS / SETUP CONFIRMED
→ PRE-TRADE REVALIDATION
→ EXECUTION QUALITY GATE
→ EXISTING FINANCIAL PREFLIGHT
→ BROKER EXECUTION

A blocked setup must not force a substitute trade.

## Tests
Cover:
- fresh valid setup passes
- stale confirmation does not execute
- invalidated thesis does not execute
- excessive price drift blocks/reassesses
- excessive spread blocks
- unavailable liquidity remains unknown
- no fake order-book metric
- Agent text cannot bypass the gate
- Trading OFF/Emergency Stop still dominate
- actual fill/slippage recorded from known fields
- ambiguous result reconciles rather than resends
- blocked opportunity persists reason
- journal/idempotency remain intact

## Definition of done
Every live trade is revalidated against fresh market/account state before submission, can be blocked when execution quality materially deteriorates, and records actual execution quality afterward without weakening existing safety.
