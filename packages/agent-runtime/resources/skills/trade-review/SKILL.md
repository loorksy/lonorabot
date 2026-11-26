---
name: trade-review
description: Use when a trade has closed or a weekly review runs, to grade the decision apart from the outcome, name a cause, read your results and draw the lesson (مراجعة الصفقة والتعلم)
---

# Trade Review

Follow the owner's current language in replies. This is judgment knowledge: what an
expert weighs, never a condition you must meet. No line here is a threshold; a number
appears only as a marked illustration.

## What you are deciding

What this closed trade teaches: whether the decision was good apart from its result,
what caused the outcome, and whether your method should change now, after more trades,
or not at all.

## What to check: the facts first

1. The close facts in the wake: symbol, side, volume, label, realized P&L, times.
2. The opening request and its initial stop: trade_record_history, then
   trade_record_read.
3. Every deal, with partial exits, adds, commission and swap: account_history.
4. What you decided and knew then: market_decision_history, market_decision_read, and
   market_opportunity_read for a saved thesis.
5. The path: market_candles over the holding time, closed bars only.
6. Your earlier reviews of this symbol and label, winners and losers alike.
Never rebuild a past decision from today's price.

## Measure in R

- Price R: side-signed exit minus entry, divided by the distance from entry to the
  initial stop, never to a stop moved later. With partials or adds, use volume-weighted
  entry and exit.
- Money R: realized P&L divided by the money at risk at the initial stop; it carries
  commission and swap.
- The best and worst excursion in R, from the candles.
- No initial stop: R is unknown. Say so; never estimate it.
Illustration: a long from 100 with its first stop at 98, closed at 103, made 1.5R; if
it first dipped to 98.5, its worst excursion was -0.75R.

## Grade the parts apart

Analysis (was the read right?), entry (location and timing for that read), management
(the plan followed, every change with a reason), execution (fill against intent,
slippage, spread, rejections) and discipline (your method, your chosen size, the owner's
rules). A right read can carry a poor entry. A winner outside your method is a
discipline fault; a loser taken well inside it is the cost of the business.

## Name one cause

Read, entry, management, execution, event or variance. Variance is an honest answer: a
sound decision that lost teaches nothing about the setup, and a lesson drawn from noise
damages the method. A poor decision that won is a warning, not a validation.

## Write the review

Add one entry per trade to MEMORY.md with memory_write, always in one shape: date,
symbol, side, label, R (or unknown and why), cause, what you expected, what happened,
the lesson in one or two sentences, when it applies and when it does not. Reuse the
labels you already trade with; a new label per trade makes your statistics useless.
Before a lesson informs a new decision, search your reviews on both sides (memory_read,
search_internal for the symbol or label), so evidence never becomes justification.

## Reading your results

market_performance_read gives, per opening label, the count and net realized P&L per
account currency (unpriced closes add nothing), and a count per management label. Read:
- wins of n, never a bare percentage;
- mean R and the spread of outcomes from your reviews: one large winner can carry a label;
- sample humility: a handful of trades says little, and a changed regime can make old
  results irrelevant;
- the counter-cases: the trades of this label that went the other way, and why.
Illustration: four wins of six is six trades, not a win rate.
Calibrate yourself: compare the conviction you stated with what happened, and look in
your journal for tilt (size jumps after losses, trades outside your method, entries
bunched after a loss, frequency rising in drawdown; trader-psychology).

## When a lesson changes the method

A lesson is ready when several independent trades point the same way, the ledger agrees,
the counter-cases are understood, and the condition can be stated precisely. Change one
thing at a time. Write it in OPERATING.md under the method's "Refinements from results":
the change, its evidence (which reviews, how many trades, mean R, the window) and the
date. Strike a refinement that later results contradict; do not delete it. The owner's
"Rules as given" stay in his words. method_history and method_restore bring back any
version. In the weekly report, list each change with its evidence, or say that nothing
changed and why.

## Weak when

The lesson rests on one trade; the cause is "the market was wrong"; the grade follows
P&L alone; R uses a moved stop; lessons come only from losers or only from winners; the
review restates facts without a decision.

## Saying it

Result in R, cause and lesson, in one line: "Minus one R on the breakout buy: the read
was right, the entry chased the second candle; cause entry; lesson: after a news spike
on this pair, the first pullback that holds is the entry; not in quiet sessions."
Illustration of a weekly line: "Six trades under the London method, three wins; no
change: the losers share no cause."
