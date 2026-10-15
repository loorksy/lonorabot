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


# 12 — Manual Trading Intelligence and Owner Intervention

## Objective
Make the Personal Agent the primary conversational owner of manual/external broker activity.

When the owner opens, modifies, or closes a trade outside Lonora, detect the authoritative broker change, identify it as not originating from a Lonora execution identity, analyze it through Personal Agent, optionally consult exact-symbol specialists, and never fight the owner's manual intervention.

## Inspect first
Reuse the current:
- broker position/order state
- trade journal
- operation identity
- account tools
- existing external broker ticket behavior/tests

The repo already has coverage for broker-native positions without a Lonora operation id.
Extend this distinction rather than creating a second broker ledger.

## External/manual identity
Use existing execution/journal identity to determine whether a position/order originated from Lonora.

If no matching Lonora execution identity exists, classify it as external/manual for Lonora purposes.

Do not guess origin from ticket formatting, comments, or display names unless an adapter contract explicitly guarantees it.

## Detect meaningful owner changes
Detect:
- external/manual position opened
- volume changed
- partial close
- full close
- SL changed
- TP changed
- manual pending order created
- pending order modified
- pending order cancelled
- other broker-state change outside the expected Lonora mutation path

Use broker-authoritative state.

## Event owner
Route account-level manual events primarily to Personal Agent.

Do not wake every specialist and send duplicate notifications.

Personal Agent may consult exact-symbol specialists through Collaboration Sessions.

## Manual-position analysis
For a newly detected manual position, build Lonora's current assessment using:
- exact symbol
- actual direction
- broker entry
- actual volume
- actual SL/TP
- current market evidence
- account exposure
- regime
- invalidation logic

Never pretend to know why the owner opened it unless the owner actually said why.

Distinguish:
"Lonora's current thesis"
from
"owner's original rationale".

## Observe vs manage
Keep separate server-side capabilities equivalent to:

`observe_manual_positions`
- detect
- analyze
- monitor
- advise
- create non-executing watches

`manage_manual_positions`
- may modify/close/manage only inside all existing financial safety/authorization rules

Observe permission never implies management permission.

## Owner intervention has priority
If owner manually changes a trade Lonora was monitoring/managing:
- broker state becomes authoritative
- update local thesis/state
- do not immediately restore previous SL/TP/volume
- re-evaluate before any new automated mutation

If owner manually closes:
- mark closed
- stop related management actions/watches as appropriate
- do not automatically reopen merely to restore the old plan

Any new trade requires a new valid decision and authority.

## Specialist consultation
Matching specialist exists:
- Personal Agent may invite it
- specialist contributes evidence
- Personal Agent remains the primary account-event communicator

No specialist:
- Personal Agent analyzes directly.

## Duplicate suppression and reconnect
Use durable state comparison/event identity so reconnect/polling does not repeatedly notify the same change.

On reconnect:
- reconcile current broker state first
- then emit only genuine new changes

## Super Bot interaction
If Super Bot is active and the owner intervenes manually:
- owner action is current authoritative broker state
- automated plan must revalidate
- do not instantly undo the change

If automated management remains authorized, any next mutation must be a new current-state decision under normal risk/permission controls.

## Manual pending orders
Apply the same principles:
- detect
- analyze
- monitor
- do not mutate without permission
- respect owner modification/cancellation

## Persistence
Persist enough to explain:
- first observed time
- broker state observed
- which changes were external/manual relative to Lonora
- which Agent analyzed them
- observe-only vs manage-enabled
- any later automated management action

Do not invent owner intent.

## UI
Keep the Personal Agent notification concise.
Allow access to:
- current analysis
- thesis
- relevant specialist chat
- observe/manage state

Do not duplicate the same manual-trade card across several Agent chats.

## Tests
Cover:
- external position without Lonora operation identity detected
- Personal Agent receives primary event
- specialist does not duplicate notification
- specialist consultation works
- no-specialist fallback works
- observe-only cannot mutate broker
- manage permission still passes all normal controls
- manual SL/TP change becomes authoritative
- Lonora does not immediately restore old values
- partial close updates state
- manual full close stops management and does not auto-reopen
- manual pending-order lifecycle detected
- duplicate observations do not spam
- reconnect reconciles before notification
- Super Bot revalidates after owner intervention
- stale automation cannot override owner's latest broker action

## Definition of done
Manual/external broker activity is first-class in Lonora: Personal Agent sees it, analyzes it, can consult specialists, avoids duplicate notifications, separates observation from management authority, and respects the owner's latest authoritative intervention.
