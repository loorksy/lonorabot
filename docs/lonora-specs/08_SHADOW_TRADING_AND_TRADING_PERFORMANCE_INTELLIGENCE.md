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


# 08 — Shadow Trading and Trading Performance Intelligence

## Objective
Add Shadow Trading plus durable performance intelligence so Lonora can record what it would have done, follow the virtual result on real market data, evaluate decision quality, detect recurring weaknesses, and compare setup/strategy performance over time.

Do not silently rewrite safety rules from performance history.

## Shadow Trading
Shadow mode:
- uses real current market data
- runs the same analysis/recommendation logic
- records a virtual action when Lonora would have traded
- sends NO broker order
- follows the hypothetical position against later real prices
- records how the virtual trade would have progressed/ended

Use explicit server-side mode/state so it cannot be confused with live execution.

## No broker mutation
In Shadow mode:
- no market order
- no pending order
- no SL/TP modification
- no partial close
- no broker mutation

Block before broker submission; do not call live execution and "ignore" it later.

## Preserve decision inputs
Store the relevant decision snapshot:
- exact symbol
- observed_at
- quote/spread
- timeframes
- regime
- thesis
- supporting/contradicting evidence
- entry plan
- invalidation
- stop/targets
- planned risk/size if applicable
- freshness/data quality

## Virtual lifecycle
Represent virtual trade progression such as:
PROPOSED → VIRTUAL_ENTRY → ACTIVE → TARGET / STOP / INVALIDATED / EXPIRED / VIRTUAL_CLOSE.

Use current conventions rather than forcing exact strings.

Simulation must be deterministic and document the available data granularity.
Do not pretend candle-only data gives tick-accurate fills.

## Real vs shadow separation
Every result must clearly identify real vs shadow.
Never silently mix both in metrics.

## Post-trade quality decomposition
Evaluate separately:

### Analysis quality
Was the original thesis/evidence coherent with subsequent market behavior?

### Entry quality
Was entry timely/structurally appropriate relative to the plan?

### Management quality
Did SL/TP/trailing/partial/early-exit handling follow the thesis and help/hurt?

### Execution quality
For real trades, how did actual spread/slippage/fill compare with the plan?

Do not reduce quality to P/L.
A winner can be poor quality; a loser can be a valid, correctly invalidated trade.

## Repeated-error analysis
Detect recurring weaknesses from persisted evidence, for example:
- chasing extended moves
- repeated late confirmations
- poor results around event risk
- weak performance in a regime/session
- recurring thesis invalidation pattern

Examples are not universal hardcoded truths.
Require meaningful sample size.

## Strategy/setup performance
Track by available dimensions:
- strategy/playbook id
- setup/pattern id
- exact symbol
- session
- market regime
- timeframe
- real vs shadow

Metrics may include when valid:
- sample count
- outcomes
- expectancy/P&L
- achieved risk/reward
- invalidation rate
- execution-quality metrics

Never present tiny samples as certainty.

## Adaptive boundaries
Performance history may inform future opportunity ranking.
It must not:
- rewrite hard safety rules
- remove risk limits
- introduce martingale
- self-modify strategy code silently
- claim future win probability from insufficient evidence

## Shadow-to-live
Give owner a way to review Shadow history before broader authority.
Never auto-enable live autonomous execution from good Shadow results.
Super Bot activation remains separately authorized.

## Persistence
Must answer:
- what would Lonora have done?
- when?
- with what evidence?
- what virtual entry/SL/targets?
- which detector/strategy version?
- what happened afterward?
- how was quality scored?
- real or shadow?

## Tests
Cover:
- Shadow never submits broker mutation
- virtual decision preserves evidence/exact symbol
- active virtual trade updates from later real market data
- real/shadow remain separate
- four quality dimensions stored separately
- winner can score poorly and loser can score validly
- repeated-error detection uses persisted evidence/sample
- setup/session/regime aggregation reproducible
- performance cannot bypass risk
- Shadow cannot auto-enable live Super Bot
- restart restores active virtual trades
- replay records data granularity/version

## Definition of done
Lonora can trade in Shadow mode on real market data without broker execution, track the hypothetical result, evaluate analysis/entry/management/execution separately, detect repeated weaknesses, and build a strategy/setup performance history that informs future analysis without silently changing safety policy.
