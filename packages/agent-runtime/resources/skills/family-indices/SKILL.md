---
name: family-indices
description: Use when trading a stock index or a stock CFD, with cash versus futures pricing, hours and gaps, the cash open, earnings reports, yields, dividends and the exchange clock (عائلة المؤشرات والأسهم)
---

# Indices Family

Follow the owner's current language in replies. This is judgment knowledge: what an
expert weighs, never a condition you must meet. No line here is a threshold; a number
appears only as a marked illustration. Stock CFDs are covered where the broker offers
them.

## What you are deciding

Whether the index or stock moves on its own story (earnings, a sector, a few mega-caps)
or on the macro tide (yields, the dollar, risk appetite), and how the exchange's hours,
its gaps and the broker's pricing change the entry, the stop and the hold.

## Start from the contract specification

Read market_instrument: the broker category (path) and the description tell an index
from a stock, and often a cash CFD from a futures-based one; then profit currency,
digits, tick size, contract size, volume step and stops level. Money per point per lot
varies widely: take it from the tick value (market_quote). Hours and daily breaks come
from market_sessions with account_id and symbol. Swap is not in the specification: past
charges show in account_history; otherwise say it is unknown.

## How the CFD is priced

- A cash CFD carries financing per night and dividend adjustments: on an ex-dividend
  date a long is debited, a short credited, and price drops by the dividend, which is
  not a move against your thesis.
- A futures-based CFD rolls at expiry: price jumps by the gap between contracts and
  positions may be adjusted. Find the roll date before a multi-day hold.

## The exchange's clock

- The cash open brings the real volume. The opening drive, or a reversal of the
  overnight move, often starts in its first part, and the opening range becomes the
  day's liquidity (sessions-and-time).
- Outside cash hours the CFD is thin or closed; overnight news opens as a gap, weekends
  as larger ones, and a stop fills at the first price after it.
- The exchange's time zone and holidays rule, not the currency sessions: a holiday or
  half day empties the market even while the broker quotes it.

## The macro tide

- Rising yields, real yields above all, tend to weigh on growth and technology-heavy
  indices more than on value-heavy ones.
- In risk-off, indices fall together and their correlation rises, so two index longs
  are mostly one bet (risk-and-sizing).
- A volatility index, where offered or read publicly, is context: when it rises, ranges
  widen and stops need room. It is not a timing signal.

## Earnings and stock CFDs

- In earnings season a few of the largest companies can move a cap-weighted index on
  their own; know their report dates.
- For a stock, the report is the event. Read it at the source (the company's release
  and filings with web_fetch, coverage with web_search): revenue and earnings against
  consensus, margins, and above all guidance. The reaction follows guidance and what was
  expected more than the headline beat; a beat with weak guidance often falls, and the
  call after the release can reverse the first move.
- Reports usually land outside cash hours, so the stock gaps through stops. Holding
  through one is a bet on the result: size it as one, or be flat.
- A stock moves with its sector and its index; read both before calling a move its own.
- Stock CFDs are often quoted in cash hours alone, with wider spreads at the open and
  close, financing on longs, and the broker's own terms for shorts and corporate actions
  (splits, mergers).

## What to check

1. The contract specification and the money per point on this broker.
2. market_sessions with at across the hold: cash open and close, breaks, weekend.
3. economic_calendar_read for the index's currency; earnings dates of the stock or the
   largest constituents from public sources, since the calendar may not list them.
4. Yields and the volatility index; market_relationship_record before treating two
   indices as separate trades.
5. Roll and ex-dividend dates inside the hold.

## Weak when

A report or the cash open inside the hold is ignored; a roll jump or dividend drop is
read as a signal; two indices are traded as independent; a stock is read without its
sector; the stop sits inside the normal opening range.

## Saying it

"The index is bid on falling yields, not on earnings; I buy the first pullback after the
cash open while the opening range low holds, a close back below it ends the idea, and I
am flat before the largest constituent reports tonight." For a stock: "Earnings beat but
guidance was cut and the gap up failed in the first hour; I am not buying it, and a close
back above the pre-report high would change my view."
