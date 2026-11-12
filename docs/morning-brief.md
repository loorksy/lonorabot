# The morning brief

Lonora sends the owner one brief on every local date (VISION 11.1, 3.1.5). The gateway
step `morning_brief` (`lonora_trading/morning_brief.py`, every 30 s) keeps one record per
owner in `ln_morning_briefs`.

## When

- **App opens.** Web (the shell, on mount and when the page becomes visible) and mobile
  (when the app becomes active) post the device's time zone to `POST /api/app-opens`, at
  most once per local date of the device. The server keeps the first open of each local
  date of the device in `ln_app_opens` (`lonora_db/app_opens.py`). Owner session only.
- **Time zone:** `reach_me.timezone` when the owner stored one, else the zone of the
  latest recorded app open, else UTC. The step only reads reach-me.
- **Time:** 07:00 until the owner has opened the app on 3 days (VISION 11.1). Then the
  median of the first opens of the last recorded days (at most 14), in the owner's zone,
  15 minutes earlier. The time is planned once per local date and moves at most one
  hour a day.
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
  the owner has not seen. Each is counted once: a Settle card is its operation, and an
  alert for an approval, an uncertain operation, a pending card (the Secret card's) or
  a broker health problem (an account shown disconnected) is not counted again;
- `nothing_else_needs_you`, true when none of these is waiting, no approval is pending
  and every account is connected.

Upcoming events are not in the facts. Lonora reads them with its calendar tool when the
owner configured one. The brief sends no push (11.4).

## The weekly report

Each agent posts a weekly report in its own conversation (VISION 5.5.6, 11.3). The week
is the FX week, which closes Friday 17:00 New York (`latest_close`).

- **Woken at the first brief after the close.** When that brief falls due, the brief
  step wakes each agent that existed at the close (`lonora_trading/weekly_report.py`),
  once: the effect receipt `weekly-report:<agent>:<close date>` claims the wake. After
  downtime only the latest close counts. No report is asked for a close that came before
  the first brief ever sent, or before the last brief.
- **What the wake holds.** Fixed server text asks for the week's results, what the agent
  learned and what it changed in its method; an agent that closed no trade posts one
  line. The agent's own journaled operations of the week follow as data in
  `<week_facts>`, each with its broker-truth state. `weekly_report` is a conversational
  trigger, so an empty reply is not accepted.
- **Paused agents** are not woken (4.7.1).
- **The brief waits** until every woken agent's run has ended, at most 30 minutes after
  the wake. It then carries each agent's report state in the facts: `posted`,
  `not_ready` (still writing), `no_report` (the run ended without a message),
  `not_woken` (the wake was refused) or `paused`. The posted reports follow in a separate
  `<agent_reports>` block as each agent's own words (at most 1,500 characters each): data,
  never broker evidence. Lonora summarizes them in that brief. The record marks the week
  `summarized`, so no later brief carries it again. The plain brief lists the states,
  not the reports.
