---
name: sessions-and-time
description: Use when timing matters, such as Asia, London and New York sessions, opens, rollover, Friday close, weekend gaps, holidays or time as an exit reason (الجلسات والتوقيت)
---

# Sessions and Time

Follow the owner's current language in replies. Everything here is a tendency that
varies by instrument and by day, never a schedule price obeys; a number appears only
as a marked illustration.

## What you are deciding

Whether this hour suits the idea, what the next session is likely to bring to an open
position or a resting order, and whether the clock itself has become a reason to act.

## How the sessions tend to behave

- Asia (Tokyo, with Sydney before it): often a narrower range for European and dollar
  pairs, more active for the yen, the Australian and New Zealand dollars and Asian
  indices. Its high and low become liquidity for London.
- London open: liquidity arrives and often takes one side of the Asian range first,
  sometimes as the day's false move, sometimes as the start of its trend. Acceptance
  beyond the Asian extreme, or a sweep back inside, tells you which (market-structure).
- New York: major US data and the US equity cash open land in its morning. The
  London and New York overlap has the deepest liquidity for most pairs and metals;
  moves made there hold more often than moves in thin hours.
- London close, late in London's afternoon: positions are squared, so the European
  move often pauses or partly reverses.
- Late New York into the Asian open: the thinnest stretch. Moves there carry little
  information, and spreads widen.
The first hours of London and of New York, which some traders call kill zones, are
where session sweeps and the day's expansion most often start.

## Opens and prior extremes

Each session open tends to probe the previous session's high or low, and the daily open
probes the prior day's (market_snapshot). A probe that closes back inside is a sweep; one
that holds is acceptance. Index CFDs trade most of the day, but the exchange's cash open
brings the real volume: the opening drive or a reversal of the overnight move often
starts there (family-indices).

## Rollover, swap and the week

- Around the broker's daily rollover, commonly near the New York close, spreads widen
  sharply and books thin. A stop close to price can be filled by spread alone.
- Swap is charged on positions held through rollover; most brokers charge several days
  of it on one weekday. The terms belong to the broker's contract; if your tools do not
  show them, say you do not know them.
- The wholesale week runs from the Sunday open to the Friday close in New York
  (market_sessions). Before the weekend, weigh what you hold against the gap risk: a
  stop does not protect against a gap, it fills at the first price after it. Weekend
  news (elections, conflicts, producer meetings) raises that risk. The Sunday open is
  thin and its first prices are unreliable.
- Some instruments pause every day (metals, energy and indices on many brokers); read
  the broker's hours rather than assuming the currency clock.

## Holidays, fixes and month-end

market_sessions ignores holidays. A bank holiday in a major centre thins liquidity:
ranges often compress, or a thin book lets a move run further than it should. Check the
calendar (economic_calendar_read) or web_search, and check the broker's hours; if you cannot
confirm, say so. Benchmark fixes (the London afternoon fix) and month-end or
quarter-end rebalancing can move price hard with no news behind it; the calendar tells
you when, not which way.

## Time as a reason to act

An idea built for a session move that has not moved by the session's end has lost part
of its reason. A momentum trade that stalls is a candidate for a time exit. A position
about to cross the Friday close, a rollover or a major release can be reduced or
closed by choice (exits-and-management). Ask: would I open this now, knowing what the
clock brings next?

## What to check

1. market_sessions with account_id and symbol: active sessions, overlaps, next open and
   close, and the broker's own hours when reported. Never work out session hours by
   hand; daylight saving changes on different dates in the US and Europe.
2. market_sessions with at set to the time your order could fill or your trade would
   still be open.
3. market_snapshot for the prior day and week extremes; the Asian range from
   market_candles.
4. economic_calendar_read for the session's scheduled events; configured false, or a
   reason saying no source could be read, is no evidence, not a quiet day.
5. market_quote for the spread now, against earlier quotes at comparable hours (no tool
   keeps a spread history).

## Weak when

The idea rests on a session tendency alone, a holiday or event changes the normal day,
or the instrument's active hours differ from the currency sessions.

## Saying it

"London took the Asian low and closed back inside; I favour the long toward the Asian
high while the sweep low holds, and a close below it ends the idea." Or: "It is late
Friday and the position is up; I am reducing it because a weekend gap can jump the
stop."
