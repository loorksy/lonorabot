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


# 10 — Portfolio Exposure and Cross-Market Intelligence

## Objective
Make Lonora reason about the owner's trading account as one risk system instead of treating each Agent/position independently.

Also add evidence-based monitoring of changing cross-market relationships so Lonora does not apply a historical relationship blindly when it has weakened or changed.

## Account-wide exposure
Build exposure from authoritative broker state:
- open positions
- relevant pending orders
- exact symbols
- direction
- volume
- entry/current price
- instrument metadata
- equity/margin
- stop/risk information when actually available

Do not fabricate unavailable notional values, currency conversions, or stop-based risk.

## Exposure dimensions
Support reliable views such as:
- per symbol
- long vs short
- per account
- currency/base/quote exposure when instrument structure supports it
- correlated/clustered exposure
- total open stop-based risk when enough data exists

Mark each value as measured/derived/estimated/unavailable as appropriate.

## Duplicate directional risk
Detect when apparently separate trades express materially similar risk, for example:
- several trades with the same USD directional exposure
- multiple gold positions in the same direction
- several correlated instruments expressing one macro thesis

Do not use a permanent hardcoded correlation matrix as truth.

## Multi-Agent risk
Before any new financial action, the server-side risk path must see positions/orders created by every Agent on the account.

Prevent two specialized Agents from independently doubling the same risk because neither considered the other.

## Personal Agent
Personal Agent is the natural conversational owner of portfolio-wide context.
Specialists may request relevant exposure context.
Personal Agent does not steal ownership of a specialist's own watch/thesis.

## Cross-market relationship engine
Using real, time-aligned market observations available to Lonora, calculate relationship evidence for relevant markets.

Examples may include gold vs dollar measures, gold vs yields if available, related FX pairs, or indices.

Do not assume the relationship is always active.

## Relationship record
Preserve:
- instruments
- window/sample
- direction/sign
- strength metric
- observed_at
- stability/change state
- data quality
- available/unavailable

Possible high-level states may include:
STABLE / WEAKENING / BREAKING / INVERTED / UNRELIABLE / UNAVAILABLE.

Use codebase conventions rather than forcing these exact labels.

## Relationship change
Detect when current measured relationship differs materially from its recent baseline.

Do not convert correlation into a causal claim.
The system may say the relationship changed; it must not claim one market caused another without evidence.

## Multiple horizons
Support appropriate bounded time windows rather than one global period.
All numerical relationship calculations must be server/code generated from aligned real data, not invented by the LLM.

## Trading use
Cross-market evidence may:
- support a thesis
- contradict it
- reduce evidence quality
- trigger reassessment/WAIT

It must never be a one-signal BUY/SELL rule.

## Exposure gate
Integrate exposure into the existing risk/preflight path.

If a proposed trade violates configured portfolio/exposure limits:
- block server-side
- return a structured reason

Do not rely solely on model discretion.

## Audit/history
Persist enough to explain:
- account exposure at proposal time
- cross-market evidence used
- whether relationship later changed
- why a trade was blocked for correlated/duplicate exposure

Reuse existing market history stores rather than duplicating raw data.

## Tests
Cover:
- positions from several Agents combine into one exposure snapshot
- long/short exposure distinguished
- missing SL/risk is not fabricated
- two Agents cannot bypass global exposure limits
- Personal Agent can inspect account-wide exposure
- specialist can consume relevant portfolio context
- relationship calculation uses aligned real data
- relationship change detected
- unavailable data marked unavailable
- no causal claim from correlation
- cross-market evidence supports/contradicts but cannot force trade
- exposure block remains server authoritative

## Definition of done
Lonora has one account-wide risk view across Agents and positions, prevents unnoticed duplicated/correlated exposure, and uses measured changing cross-market relationships as evidence without treating correlation as a permanent law.
