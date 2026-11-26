---
name: exits-and-management
description: Use when managing an open trade, such as the thesis check, partials, break-even, trailing, time exits, extending targets, adding or holding through events (إدارة الصفقة والخروج)
---

# Exits and Management

Follow the owner's current language in replies. This is judgment knowledge: what an
expert weighs, never a condition you must meet. No line here is a threshold; a number
appears only as a marked illustration.

## What you are deciding

On each wake for an open trade: does its reason still hold, and which action serves it
now: hold, take part, protect, add, extend or exit. Every action costs something, and
doing nothing is also a choice.

## The thesis check on every wake

- Is the invalidation intact on closed bars of the leading frame?
- Is the trade doing what you expected, in the time you expected? A stall where it
  should have moved is information.
- What is new: an event ahead or just out, a shift against you on the timing frame, a
  related market turning.
If the reason is broken, an early exit is the professional answer, even with the stop
untouched. If it holds, noise is not a reason to act.

## Partials and break-even

- Take part at liquidity or structure where the move is likely to pause (first target,
  prior-day extreme, equal highs). It banks R and lowers variance; it also trims your
  best trades. Plan it before entry, not from fear on a pullback.
- A stop at entry turns ordinary pullbacks into scratches. Compare it with the normal
  pullback depth on your timing frame; move it when structure gives a new invalidation
  (a confirmed higher low after entry, for a long), not after an arbitrary distance.
  Secure-then-add uses break-even on purpose, to free risk for the next position.

## Trailing

- By structure: behind each new confirmed swing (market_structure pivots). It respects
  the market's own levels and lags in fast moves.
- By volatility: a distance in this symbol's ATR behind the extreme. It adapts to speed,
  and an ordinary pullback can tag it.
Trail tighter when the move is extended into higher-frame structure or momentum fades,
looser in a clean trend. Too tight turns trends into small wins.

## Time

An idea has a life. If the move has not started by the session or event you expected,
the edge has likely decayed: reduce or exit. Before the weekend and around rollover's
wide spread, decide what you hold through.

## Extending and adding

- Extend when momentum is strong (closes beyond the target, expanding ranges, structure
  breaking your way): move or remove the take profit and trail instead, unless an
  obvious higher-frame level sits just beyond.
- Add to a move that is working, at fresh structure (a retest that held, a new base),
  with the combined risk measured to the stop that now protects it all (risk-and-sizing).
- Adding to a loser raises risk on an idea the market disputes: an expert treats it as
  a new decision with its total risk chosen up front, not as a rescue.

## Events, restraint and the owner's hand

- Before a release decide: close, reduce, protect or hold as is (news-and-macro). A
  stop through a release slips.
- A change without new information costs spread or edge. A trade with its stop and
  target set needs watching, not tinkering.
- If the owner moved a stop or closed part, keep his change (position-management).

## Labels and wakes

Give each management order (modify_position, close_position with part of the volume, an
add) a judgment label in your own words and reuse it for that choice, so
market_performance_read counts how each kind of management works for you. Wake
yourself with watch_create: kind price at the level where you would add, tighten or exit
(evaluation mode candle_close for close-decided ones), kind position for the position,
kind calendar before an event.

## What to check

1. account_read: the actual volume, stop, target and floating result; account_activity
   for what changed and who changed it.
2. Fresh closed bars on the leading and timing frames since entry (market_snapshot,
   market_structure).
3. The original plan and its invalidation (market_decision_read).
4. Events before your next wake (economic_calendar_read).
5. Spread (market_quote) and the stops level before a stop moves close to price.

## Weak when

The stop moves away from invalidation; floating P&L drives the decision instead of
structure; break-even lands inside the normal pullback; a partial comes from fear; an add
skips the combined risk; the thesis broke and you wait for the stop anyway.

## Saying it

"Holding: 1h printed a higher low above my entry, so the stop goes under it; part
comes off at the prior-day high; a 1h close back below the breakout level ends it."
"Exiting early: the dollar reversed on the data and 1h shifted against me; the reason is
gone though the stop was not hit."
