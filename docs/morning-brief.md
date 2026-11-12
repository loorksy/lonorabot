# The morning brief

Lonora sends the owner one brief on every local date (VISION 11.1, 3.1.5). The gateway
step `morning_brief` (`lonora_trading/morning_brief.py`, every 30 s) keeps one record per
owner in `ln_morning_briefs`.

## When

- **Time zone:** `reach_me.timezone` when the owner stored one, else UTC. The step only
  reads reach-me.
- **Time:** 07:00 in that zone. VISION 11.1 keeps 07:00 until Lonora has seen the owner
  open the app on 3 days; app opens are not recorded yet, so the learned time is not
  built.
- **Once per local date.** The effect receipt `morning-brief:<owner>:<date>` claims a
  date's brief in the transaction that starts it, under the record's row lock. After
  downtime the step sends only today's brief: missed dates are not sent.

## Who writes it

- The step wakes Lonora in its own conversation with the trigger `morning_brief`. The
  wake is fixed server text followed by the facts as JSON inside `<brief_facts>` (`<`
  escaped). Text that agents wrote, such as names and symbols, is in the facts, so the
  wake is the run's request turn, not system text. Lonora composes the brief; there is
  no brief card.
- `morning_brief` is a conversational trigger. An empty turn gets the "no answer"
  notice, and the silence tool refuses.
- If the run has no brief message 30 minutes after the wake, the step cancels the run
  and posts a plain brief from the same facts as Lonora's message, in the conversation's
  language. It also posts it at once when Lonora is paused, or when the facts are too
  large for a wake. A pause never silences the brief.

## What it says

The facts come from the broker snapshots, the journal and the approval cards, never
from an agent's sentence:

- each enabled account's balance and equity, and their change since the last brief;
- each agent's journaled operations since the last brief. Each operation carries its
  broker-truth state: `confirmed` only when the broker confirmed it and its
  verification is not pending;
- open positions and pending orders, each with the agent whose journaled order opened
  it (else the owner);
- pending Trade Approval cards;
- what else waits for the owner, whatever its date: operations of unknown outcome, other
  pending owner cards, runs waiting for the owner's answer, and action-required alerts
  the owner has not seen;
- `nothing_else_needs_you`, true when none of these is waiting, no approval is pending
  and every account is connected.

Upcoming events are not in the facts. Lonora reads them with its calendar tool when the
owner configured one. The brief sends no push (11.4).
