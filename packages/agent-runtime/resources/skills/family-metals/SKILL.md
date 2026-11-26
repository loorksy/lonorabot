---
name: family-metals
description: Use when trading gold, silver or another metal, with the dollar, real yields, the Fed's tone, safe-haven demand, the London and New York sessions and the London fixes (عائلة المعادن والذهب)
---

# Metals Family

Follow the owner's current language in replies. This is judgment knowledge: what an
expert weighs, never a condition you must meet. No line here is a threshold; a number
appears only as a marked illustration.

## What you are deciding

What drives the metal now (real yields, the dollar, fear, physical demand or
positioning), whether it is still pushing, and how the metal's wide ranges and this
broker's contract change the size and the stop.

## Start from the contract specification

Read market_instrument on the exact symbol: the broker category (path), base and profit
currencies (the metal's code against a currency, usually the dollar), digits, tick size,
contract size, volume step and stops level. The ounces in a lot differ by broker. Read
the tick value per lot (market_quote) and the hours and daily break (market_sessions
with account_id and symbol). Swap is not in the specification: past charges show in
account_history; otherwise say it is unknown.

## Gold's drivers, each read as evidence

- Real yields: gold pays nothing, so falling real yields (inflation-protected Treasury
  yields, read with web_search) tend to lift it and rising ones to weigh on it. The link
  broke for long stretches of heavy central-bank buying; check that it holds now.
- The dollar: gold tends to move against it. A dollar index where the broker offers one,
  or the dollar against the majors, is context, never a mandatory confirmation: in acute
  stress both can rise, and a gold move the dollar does not explain has another driver.
- The Fed's tone, from open news (news_feed_read, web_search; economic_calendar_read for
  the dates): statements, minutes, the press conference and speakers. A shift in the
  expected policy path moves real yields and so gold; judge the reaction on closed bars,
  not the adjectives.
- Safe-haven demand: war, sanctions, banking stress and contested elections can lift
  gold. A headline is evidence, never an automatic buy: price that rises and holds on
  closed bars shows the fear is being paid for; price that fades while the headline
  stays loud says it is priced or not believed. The first spike often retraces.
- Central-bank buying and fund flows explain trends over months, not entries; a
  crowded long unwinds fast on a hawkish surprise.

## Sessions and the London fixes

- Asia: physical demand from China and India; often a narrower range.
- London: the centre of the spot market; its open often takes one side of the Asian
  range first (sessions-and-time).
- New York: futures volume and US data land in its morning; the overlap with London
  holds the deepest liquidity and largest moves. Jobs, inflation and Fed days bring wide
  ranges and stop runs both ways before the direction shows.
- The London benchmark prices (the fixes) are set by auction at set London times; price
  can be drawn toward the auction, with a burst of volume. They are facts on the clock,
  not signals, and London time shifts with British summer time against the broker clock.
Illustration of the current schedule, to confirm with web_search: gold at 10:30 and
15:00 London time, silver at 12:00, platinum and palladium at 9:45 and 14:00.

## Silver, platinum and palladium

Silver adds industrial demand to gold's drivers, with a higher beta and thinner
liquidity: larger swings, sharper stop runs, wider spreads. The gold to silver ratio is
context, never a signal alone. Platinum and palladium, where offered, are thin markets
driven by car-catalyst demand and a few producers, with large spreads and gaps.

## What to check

1. The contract specification and tick value, on every new symbol or account.
2. economic_calendar_read for the dollar, and the profit currency if it is another; Fed
   days and US data first.
3. The dollar and yields now (market_snapshot on a dollar index or a major pair, real
   yields publicly); market_relationship_record for whether gold follows them now.
4. Spread now (market_quote) against normal (pre-trade-check); it widens before US data and around the
   daily break.
5. Your own and the team's metal and dollar exposure (account_read).

## Weak when

One driver is read as the whole story; a headline is bought before price confirms it;
the stop sits inside the normal range of a US release; size was carried from another
broker's contract; the relationship relied on was never measured in this window.

## Saying it

"Gold is following real yields lower while the dollar is flat, so this is a yields move;
I buy the London pullback while the 1h higher low holds, a close below it ends the idea,
and I hold reduced size into the jobs report." Or: "The conflict headline spiked gold
and closed 15m bars have given it all back; no trade: the market is not paying for the
fear."
