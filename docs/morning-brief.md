# The morning brief

Lonora sends the owner one brief on every local date (VISION 11.1, 3.1.5). The gateway
step `morning_brief` (`lonora_trading/morning_brief.py`, every 30 s) keeps one record per
owner in `ln_morning_briefs`.

## When

- **Time zone:** `reach_me.timezone` when the owner stored it, else the latest device
  zone from the app-open record, else UTC. The step only reads reach-me.
- **Time:** 07:00 until the owner has opened the app on at least 3 days. After that it
  is the median of the owner's first open per day over the last recorded days (at most
  14), 15 minutes earlier. The time moves at most one hour per local date.
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
- the number of operations of unknown outcome waiting for the owner;
- `nothing_else_needs_you`, true when no approval or unsettled operation is waiting and
  every account is connected.

Upcoming events are not in the facts. Lonora reads them with its calendar tool when the
owner configured one. The brief sends no push (11.4).

## The weekly report

Each agent posts a weekly report in its own conversation (VISION 5.5.6, 11.3). The
gateway step `weekly_reports` (`lonora_trading/weekly_report.py`, every 30 s) finds the
latest closed FX week, which closes Friday 17:00 New York.

- **One wake per agent per week.** For each agent that existed at the close, the step
  claims the effect receipt `weekly-report:<agent>:<close date>`. It then wakes the agent
  with the trigger `weekly_report` in its own conversation. After downtime, only the
  latest close is woken.
- **What the wake holds.** Fixed server text asks for the week's results, what the agent
  learned and what it changed in its method. An agent that closed no trade posts one
  line. The agent's own journaled operations of the week follow as data in
  `<week_facts>`, each with its broker-truth state. `weekly_report` is a conversational
  trigger, so an empty reply is not accepted.
- **Paused agents.** A paused agent is not woken (4.7.1), and the brief says it is
  paused.
- **The first brief after the close** carries `weekly_reports` as data. Each entry is the
  agent's posted report (at most 1,500 characters), or `not_ready`, or `paused`. Lonora
  summarizes the reports in that brief. The record marks the week `summarized`, so no
  later brief carries it again.
