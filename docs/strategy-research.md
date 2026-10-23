# Reproducible historical research and decision readiness

These additions extend the existing market tools, deterministic detectors,
decision ledger and artifact store. They do not create trading authority or
replace the executor's final checks.

## Bounded historical research

`market_strategy_research` obtains the actual broker instrument specification and
exact-symbol candle history through the current broker manager. It excludes
incomplete bars, validates OHLC, symbol/timeframe identity, timestamps, ordering
and overlaps, and either rejects or explicitly reports gaps. Supported input is
80–1,000 closed bars and up to twelve declared SMA-cross candidates.

The audited engine uses completed closes for signals and later bar opens for
fills. It models declared whole-bar latency, adversely rounded execution,
spread/slippage, per-side commission and elapsed-time carry. The caller must
explicitly supply monetary tick valuation, currency, price basis, volume and
cost assumptions. The current instrument contract does not provide verified
historical tick value, contract size, FX conversion or historical bid/ask costs.
No monetary convention is guessed from a symbol or broker suffix.

Expanding training ranks candidates; validation selects among the strongest
three training candidates; disjoint chronological test windows measure the
selected parameters afterward. Each evaluation period starts flat and may warm
up only from earlier bars. A separately labeled full-sample baseline uses the
first declared candidate and is not out-of-sample evidence.

Seeded Monte Carlo reshuffles closed out-of-sample trades and adds uniformly
distributed extra execution cost between zero and the modeled execution cost.
It reports scenario drawdown, terminal P&L and ruin fractions. These are declared
stress results, not predictive probabilities or complete parameter uncertainty.

The JSON report retains the exact dataset, specification, scenario, candidate
scores, folds, trade results, engine version and configuration/data/result
hashes. The existing artifact lifecycle attaches the actual report to the
conversation. Identical tool retries return its original integrity-checked
report without fetching a different market. `market_research_history` finds the
same Agent's saved reports by exact account and symbol.

The implemented engine is a typed SMA strategy subset. It does not claim
arbitrary imported-strategy equivalence, tick-level liquidity, partial fills,
session/margin/liquidation modeling, historical swaps, sub-bar latency or live
promotion. Paper/Shadow execution remains an independent existing capability;
research creates no paper or broker position automatically.

## Three distinct decision projections

`market_decision_record` preserves its existing immutable evidence and legacy
action/gate behavior while adding optional `readiness`:

- Market assessment is an explicitly labeled model interpretation: BULLISH,
  BEARISH, NEUTRAL or INSUFFICIENT_EVIDENCE. It needs matching fresh broker
  observations, a rationale and a supporting condition independently evaluated
  by the existing detector. Available prices or a requested BUY alone do not
  manufacture a directional assessment. Confidence is not calibrated.
- Entry readiness separately records whether the supplied concrete detector
  condition is confirmed, unconfirmed or lacks evidence. A forming candle
  pattern is not confirmed. A market bias alone creates no entry.
- Execution readiness is BLOCKED or REVALIDATION_REQUIRED, never executable
  permission. Controls, broker recovery, account state and evidence failures
  remain visible; the executor must recheck current authorization, instrument,
  exposure, risk, quality, idempotency and reconciliation immediately before any
  mutation.

An unrelated account/order read failure can block execution without erasing a
grounded market interpretation. Read-only transient observations have one
bounded retry through the shared broker manager. Financial mutations are never
retried by this recorder. Historical reads and comparisons use the recorded
readiness and evidence, not current prices. Old records without `readiness`
remain readable and retain their original operation identities.

## Verification

`tests/test_strategy_research.py` covers exact costs and volume/tick conversion,
next-bar fills, delayed signals, adverse rounding, chronological selection,
disjoint tests, reproducible seeds/hashes and invalid history. It includes forex,
metal, index and crypto symbols without hardcoded monetary interpretations.
`tests/check_strategy_research.py` exercises the real Agent loop, simulation
history/specification, PostgreSQL, attached report and authenticated file download,
including original-result replay, corruption and exact-symbol scope.

`tests/test_decision_readiness.py` covers independent opinion/entry/execution,
stale or missing observations, forming candles, controls and old records.
`tests/check_decision_readiness.py` exercises canonical tools over four symbol
classes and timeframes, bounded read recovery, immutable history, and an actual
owner-approved simulation request that still cannot bypass reconciliation.
