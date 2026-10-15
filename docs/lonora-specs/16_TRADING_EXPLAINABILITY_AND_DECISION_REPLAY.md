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


# 16 — Trading Explainability and Decision Replay

## Objective

Create a unified explainability and decision-replay layer so Lonora can reconstruct what it knew at the time of a recommendation, trade, thesis change, or WAIT decision.

The owner must be able to ask later:
- Why did you recommend this?
- What evidence did you have then?
- What changed afterward?
- Why did you change your mind?
- Why did you wait?
- Why did you exit early?

Answers must come from persisted historical evidence, not hindsight reconstruction.

## Inspect first

Reuse current:
- TradingJournal
- TradingGoal decisions
- watch transitions
- evidence structures
- recommendation contract
- thesis/opportunity history
- execution-quality records
- market snapshots
- event history
- collaboration evidence/provenance

Do not build a second trading journal.

## Decision record

For every meaningful trading decision preserve enough to identify:
- decision id
- owner
- Agent
- account
- exact symbol
- decision type
- observed_at
- market regime
- current thesis/opportunity id/version
- recommendation/action
- supporting evidence ids
- contradicting evidence ids
- unresolved conflicts
- data freshness/health
- account/exposure context when relevant
- risk/execution gate outcome
- strategy/detector versions where available

## Decision types

Support explainability for more than executed trades.

Examples:
- BUY recommendation
- SELL recommendation
- WAIT
- setup confirmed
- setup invalidated
- trade blocked
- trade cancelled before execution
- position managed
- early exit
- thesis expired
- Super Bot chose no opportunity

Use current contract conventions.

## Immutable historical view

Historical replay must preserve the state known at that time.

Do not answer a past-decision question using only today's market data.

Store references/snapshots/versioned evidence needed to reconstruct the original decision.

New later information may be shown separately as "what happened afterward."

## Timeline replay

Provide a deterministic event timeline such as:

Opportunity detected
→ evidence added
→ thesis created
→ setup confirmed
→ execution revalidated
→ order submitted/fill
→ thesis updated
→ exit/close
→ post-trade review

For WAIT:
Evidence gathered
→ contradiction/risk/data gap
→ WAIT
→ later evidence changed
→ new decision

## Explain "why"

Generate concise explanations from structured persisted facts:
- primary supporting evidence
- primary contradiction
- decisive rule/gate
- invalidation/expiry cause
- missing data if WAIT

Do not expose hidden chain-of-thought.
Explain using stored evidence, decisions, and runtime facts.

## "What changed?"

Compare two decision versions/timestamps.

Show only material deltas:
- regime changed
- level broke
- event passed
- spread deteriorated
- exposure increased
- correlation weakened
- confirmation expired
- new evidence arrived

Do not dump every unchanged field.

## Collaboration provenance

If a decision used other Agents:
- show contributing Agent identities
- evidence each contributed
- conflicts that remained
- final fusion result

Do not say Host invented participant evidence.

## Replay vs backtest

Decision Replay is not automatically a backtest.

Replay answers:
"What did Lonora know and do at that time?"

Historical strategy replay/backtesting may use later data separately.

Do not mix hindsight outcome into the original evidence set.

## Versioning

Preserve relevant version identifiers when available:
- strategy/playbook
- detector
- evidence schema
- recommendation logic version
- watch definition version

So historical decisions remain interpretable after code evolves.

## User experience

In chat, owner can ask naturally:
- "Why did you buy?"
- "Why did you change to WAIT?"
- "Show me what changed."

Provide concise answer plus optional "view timeline/details".

Detailed view may show:
- timeline
- evidence cards
- Agent contributors
- market snapshot/chart reference
- execution-quality record
- outcome

## Audit safety

Explainability records must not expose:
- secrets
- device credentials
- hidden model chain-of-thought
- unrelated private context

Use only user-visible/runtime evidence suitable for audit.

## Tests

Cover:
- recommendation can be reconstructed from stored evidence
- WAIT is explainable
- thesis change shows material evidence delta
- historical replay does not use future evidence as original evidence
- collaboration contributor provenance is retained
- execution block reason is replayable
- manual trade analysis replay is distinguishable from owner rationale
- version metadata retained
- restart does not lose decision history
- answer can be generated without hidden chain-of-thought
- later outcome displayed separately from original decision context

## Definition of done

Any important trading recommendation, WAIT, thesis change, execution block, management action, or exit can be replayed later from durable evidence with a clear timeline and provenance, without hindsight leakage or fabricated reasoning.
