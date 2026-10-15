PROJECT: Lonora (`loorksy/lonorabot`)

IMPORTANT:
- This is an implementation task. Do not stop at an architecture-only answer.
- Inspect the current repository before changing code. Do not assume conceptual names in this prompt already exist.
- Reuse existing Lonora primitives and contracts. Do not create parallel runtimes, duplicate event buses, duplicate broker ledgers, or duplicate chat state systems.
- Preserve exact broker symbols, owner/account/Agent scoping, Trading ON/OFF, Emergency Stop, authorization, risk controls, idempotency, journal, locking, and broker reconciliation.
- Never fabricate unavailable market, execution, account, notification, or replay evidence.
- Keep current global model routing; do not introduce per-Agent model/provider selectors.
- Keep Arabic-first/RTL compatibility across Web and Mobile.
- Do not mention paid API/token/key requirements.
- Work on a dedicated branch, add focused tests, and run relevant existing checks.


# 13 — Market Data Integrity and Trading Runtime Health

## Objective

Add a unified market-data integrity and trading-runtime health layer so Lonora knows whether the data and runtime it relies on are trustworthy enough for analysis, recommendations, watches, and execution.

When data/runtime health is degraded, Lonora must explicitly degrade behavior to WAIT / SUSPENDED / REVALIDATE rather than continuing as if nothing is wrong.

## Inspect first

Inspect the current:
- market runtime
- broker subscriptions/sessions
- quote/candle caches
- market snapshots
- MarketWatch runtime
- Gateway heartbeat/worker lifecycle
- chart streaming
- broker reconnect behavior
- existing health/heartbeat endpoints or events
- retry/backoff logic

Reuse what exists.

## Data-health dimensions

Track integrity for each relevant stream/resource where applicable:

- quote freshness
- candle freshness
- candle continuity
- timestamp monotonicity
- duplicate/out-of-order observations
- missing candles
- stale snapshots
- spread availability
- symbol availability
- broker connection state
- market subscription state
- watch evaluation freshness
- chart stream freshness
- account snapshot freshness

Do not create fake health metrics for unsupported data.

## Health states

Support a small typed health model equivalent to:

HEALTHY
DEGRADED
STALE
UNAVAILABLE
RECOVERING

Use existing conventions if the codebase already has status semantics.

Each state must include:
- reason code
- observed_at
- last_good_at when known
- affected resource/symbol/account
- evidence/measurements where relevant

## Freshness

Freshness must be explicit and deterministic.

A value is not "live" merely because it exists in cache.

Use:
- source timestamp
- receive timestamp
- expected update cadence where known
- timeframe-aware candle rules
- broker/session status

Do not hardcode one global freshness threshold for all symbols/timeframes.

## Missing / broken candle series

Detect issues such as:
- missing expected bars
- duplicated bars
- non-monotonic timestamps
- large unexplained gaps
- partial/incomplete current bar confusion
- corrected historical bars

Do not silently fill gaps with invented OHLC values.

If backfilling is supported by the current broker/runtime, reconcile using real source data.

## Quote integrity

Detect:
- stale bid/ask
- invalid bid/ask ordering
- impossible/invalid numeric values
- missing side
- repeated stale observation beyond expected cadence
- exact-symbol subscription loss

Do not allow an actionable recommendation to rely on an invalid/stale quote.

## Watch integrity

A Market Watch must know whether it is evaluating against healthy source data.

If required inputs become stale/unavailable:
- transition to SUSPENDED/health-blocked semantics
- record reason
- do not emit false CONFIRMED/INVALIDATED transitions from bad data
- wake/re-evaluate after data health recovers

## Trading integration

Before actionable recommendation or broker execution, verify required market/account inputs are healthy.

Examples:
- current quote healthy
- relevant candles healthy
- required indicator inputs complete
- account snapshot fresh enough
- watch confirmation based on healthy evidence

If not:
- WAIT
- SUSPEND
- REVALIDATE

Never force BUY/SELL from degraded data.

## Runtime health

Track health for core trading runtime components using existing process/heartbeat architecture:
- Gateway
- worker
- market runtime
- broker connection/session
- watch evaluator
- chart stream/render path when relevant
- event delivery path where observable

Do not introduce Kubernetes-style infrastructure or external orchestration.

## Stuck-work detection

Detect operational states such as:
- watch has not evaluated despite expected inputs
- worker lease/Run is stuck
- broker subscription should be active but is silent
- wake receipt created but no follow-up progress
- repeated retry loop
- stale chart/market stream

Use durable timestamps/state, not guesses.

## Recovery behavior

When a data source recovers:
- reconcile current state
- refresh source data
- rebuild/revalidate affected indicators/watches
- avoid replaying stale decisions as current
- emit one meaningful recovery event
- continue only after required integrity checks pass

## Health events

Normalize meaningful events such as:
- market_data.degraded
- market_data.stale
- market_data.recovered
- broker.connection_degraded
- broker.connection_recovered
- watch.suspended_health
- watch.resumed_health
- runtime.component_stalled
- runtime.component_recovered

Use existing Lonora event conventions.

Do not spam one event per tick.

## Agent behavior

The Agent should be able to answer:
- "Are your market data current?"
- "Why are you waiting?"
- "Is the broker feed healthy?"
- "Did the watch stop?"

Answers must come from real health state.

## UI

Expose health only when useful:
- compact warning
- affected symbol/account
- stale/recovering state
- last-good timestamp
- action such as retry/reconnect only where appropriate

Do not fill the main trading chat with low-level telemetry.

## Tests

Cover at least:
- stale quote detected
- missing candle detected
- out-of-order candle handled
- invalid quote cannot produce actionable recommendation
- stale watch input suspends watch instead of confirming
- recovery revalidates before resuming
- repeated stale observations do not spam notifications
- broker disconnect marks dependent data unhealthy
- account snapshot freshness is checked before execution
- runtime-stall detection is based on durable evidence
- no fabricated candle/quote used to repair gaps
- exact broker symbol preserved throughout recovery

## Definition of done

Lonora always knows whether its market/account inputs and trading runtime are healthy enough to trust, automatically degrades to safe WAIT/SUSPENDED behavior when they are not, and recovers through reconciliation and fresh-data revalidation rather than stale assumptions.
