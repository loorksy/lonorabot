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


# 17 — Broker Recovery and Degraded Mode

## Objective

Define one safe recovery/degraded-mode protocol for broker disconnects, stale account state, ambiguous order results, reconnects, missed events, and partial runtime failure.

Lonora must never continue financial automation from stale assumptions after broker uncertainty.

## Inspect first

Inspect current:
- broker manager/session lifecycle
- account/position/order reads
- trade journal
- idempotency
- reconciliation
- pending-order handling
- reconnect/subscription behavior
- market runtime retry/backoff
- Gateway/worker recovery
- demo-broker verification tests

Extend current mechanisms.

## Degraded broker state

Represent broker/account connectivity health with clear server-side state equivalent to:

CONNECTED
DEGRADED
DISCONNECTED
RECOVERING
RECONCILING

Use existing status conventions if present.

Include:
- account/integration id
- since
- last successful read
- reason
- last error code
- reconciliation state

## Financial behavior while degraded

When authoritative broker state is not trustworthy:
- block new autonomous entries
- block blind position modifications
- suspend management decisions that require unknown current state
- preserve Emergency Stop semantics
- allow safe read-only status where possible
- return explicit WAIT/DEGRADED state

Do not guess positions/orders.

## Ambiguous mutation

If an order/modify/close request may have reached the broker but response is uncertain:

DO NOT RESEND.

Use existing operation id/journal and broker reconciliation.

Classify result only after authoritative state indicates:
- confirmed applied
- confirmed not applied
- still ambiguous

## Reconnect protocol

On reconnect:

1. mark connection RECOVERING
2. refresh account snapshot
3. fetch/reconcile open positions
4. fetch/reconcile pending orders
5. reconcile in-flight/ambiguous journal operations
6. reconcile manual/external changes
7. refresh relevant subscriptions/market state
8. revalidate active theses/watches/management plans
9. only then return to normal autonomous action

Do not immediately resume queued financial mutations before this protocol completes.

## Missed owner changes

During disconnect the owner may trade manually elsewhere.

After reconnect, detect authoritative differences:
- new manual position
- closed position
- changed SL/TP
- partial close
- pending-order changes

Route these through Prompt 12 behavior.

Do not restore pre-disconnect state over owner changes.

## Active Super Bot

If Super Bot was active before disconnect:
- keep goal/persistent state
- enter degraded/waiting mode
- do not create new broker mutations
- after reconnect, reconcile and revalidate
- resume only if all required state is trustworthy and permissions still valid

Do not treat reconnect itself as a trade signal.

## Position protection

If the broker-side SL/TP already exists, it remains broker-authoritative during application outage.

After reconnect:
- confirm it still exists/current values
- do not assume local cached protection is accurate

If protection state is unknown, surface the uncertainty clearly.

## Market-data dependency

Broker recovery and market-data health interact.

Do not resume execution just because the account endpoint is back if:
- quote feed is still stale
- candles are stale
- required symbol subscription is unavailable

Prompt 13 health gates must pass.

## Duplicate-event prevention

Reconnect reconciliation may rediscover existing positions/orders.

Do not emit them as "new" unless state comparison proves they changed during the gap.

## Recovery events

Persist meaningful transitions:
- broker.degraded
- broker.disconnected
- broker.recovering
- broker.reconciliation_started
- broker.reconciliation_completed
- broker.recovered
- broker.reconciliation_failed

Use current event conventions.

## Agent/user behavior

Agent should be able to say:
- broker connection is degraded
- new trading is paused
- reconciliation is in progress
- account state has been restored
- manual changes were discovered

Do not say "everything is fine" before reconciliation completes.

## Tests

Cover:
- disconnect blocks new autonomous execution
- in-flight ambiguous order is not resent
- reconnect performs reconciliation before resume
- positions/orders changed while offline are detected
- owner manual close is not undone
- stale cached position is not treated as authoritative
- duplicate reconnect snapshot does not emit false new-position event
- Super Bot remains persistent but non-executing while degraded
- market health must recover before execution resumes
- reconciliation failure keeps system degraded
- journal/idempotency survive restart/reconnect
- exact symbols/tickets preserved

## Definition of done

Broker uncertainty puts Lonora into a safe degraded mode, prevents blind financial mutations, reconciles account/order/position state after reconnect, discovers owner changes made while offline, and resumes automation only after authoritative broker and market state are trustworthy again.
