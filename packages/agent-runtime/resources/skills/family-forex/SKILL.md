---
name: family-forex
description: Use when trading a currency pair, with its two currencies, dollar and yen legs, rate differentials, crosses, session liquidity, swap, pips versus points and per-leg exposure (عائلة العملات)
---

# Forex Family

Follow the owner's current language in replies. This is judgment knowledge: what an
expert weighs, never a condition you must meet. No line here is a threshold; a number
appears only as a marked illustration.

## What you are deciding

Which of the two currencies drives the pair now, whether your view is really one
currency against the field, and how the pair's units, hours and carry change the plan.

## Start from the contract specification

Read market_instrument for the exact broker symbol, suffix included (market_symbols
finds it): the broker category (path), base and profit currencies, digits, tick size,
contract size, volume step and stops level. The category and the two currency codes make
it a pair, not the name. Read the tick value per lot (market_quote) and the broker's
hours (market_sessions with account_id and symbol). Swap is not in the specification:
past charges show on deals in account_history; otherwise say it is unknown.

## Pips, points and scale

A point is the broker's smallest step; a pip is a convention. Derive both from digits
and tick size on every symbol.
Illustration: on a five-digit quote a pip is ten points, the fourth decimal; on a
three-digit yen quote it is the second.
Measure stops and targets in the pair's own ATR and spread, never in pips carried over
from another pair.

## Two stories in one price

- A move is the base strengthening, the quote weakening, or both; the same currency in
  other pairs tells you which. A euro up against everything is a euro story.
- The dollar sits on one side of most volume. A dollar index where offered, or the
  dollar against several majors, is context, never a condition.
- The yen and the Swiss franc tend to rise in risk-off and fall while carry is in
  favour; yen crosses drop hard when carry unwinds.
- The Canadian dollar leans on oil, the Australian on metals and China's data, the New
  Zealand on dairy and its neighbour: tendencies to measure, not assume.
- Rate differentials and central-bank divergence move pairs over weeks; the expected
  policy path matters more than today's rate (news-and-macro). Intervention, most often
  for the yen, gaps price on the headline.

## Crosses, hours and carry

- A cross is two non-dollar stories with a wider spread; its move combines two dollar
  pairs, so read both legs. Exotics add gaps, thin hours and policy risk.
- A currency is most liquid in its home session (sessions-and-time); a move in its off
  hours carries less information.
- Swap follows the rate differential: the higher-yielding side usually earns, the other
  pays, and the broker's markup can make both pay. Over a multi-day hold it is part of R.

## Exposure per currency

Split each position into its two legs and add them across your own, the team's and the
owner's positions (account_read, the wake picture): a euro long and a pound long against
the dollar are mostly one short-dollar bet (risk-and-sizing).

## What to check

1. The contract specification, on every new symbol or account.
2. economic_calendar_read for both currencies over the hold.
3. market_snapshot on the pair and on the same currency elsewhere.
4. market_relationship_record before treating two pairs as one bet or as a hedge.

## Weak when

The view ignores one currency; the move is in the currency's off hours; the other
currency has a release inside the hold; a cross's legs disagree; spread and swap eat a
large share of the expected move.

## Saying it

"This is a dollar story: the dollar is weak against every major after the jobs miss. I
buy the euro on the London pullback while the 1h higher low holds; a close below it ends
the idea, and with the pound long open I size the two as one short-dollar trade."
