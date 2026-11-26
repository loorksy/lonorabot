---
name: candles-and-breakouts
description: Use when judging a breakout, a false break, a retest or a candle at a level, or describing a structure no pattern name fits (الشموع والاختراقات)
---

# Candles and Breakouts

Follow the owner's current language in replies. This is judgment, never a condition;
a number appears only as a marked illustration.

## What you are deciding

Whether a level broke, was swept or is holding; which way of entering a break fits
this market; whether the candle at the level adds evidence; and how to describe
structure that no name fits.

## Break, sweep, false break

- A break is a close beyond the level on the timeframe you judge; never call a wick a
  break. A wick through that closes back inside is a sweep (market-structure).
- A strong break closes well beyond the level for this instrument's normal range, with
  expansion and follow-through, often out of compression. One that arrives after a long
  run into higher-frame structure is late and fails more often; a close beyond by about
  the spread says little.
- A false break, a close beyond that is reclaimed quickly, is one of the strongest
  reversal signals: those who joined the break are trapped, and their exits drive the
  return. The idea is wrong beyond the false-break extreme.

## Five ways to take a break

Enter on the break close; enter early from a good location before it breaks; take part
now and add on a retest; wait for the retest as a conditional plan; or skip the retest
when momentum makes a deep pullback unlikely. None is the rule. Say why you chose
yours: a retest wait misses the strongest breaks; entering on the close fills for
sure, at a worse price, and is the most exposed to a false break.
A retest that holds on closes, with smaller bodies and rejection wicks, is constructive;
one that closes back deep inside the old range is turning into a false break.
A close-decided condition never pairs with a stop order at that level, which fills on a
touch (trade-planning); a watch on the close (watch_create, evaluation_mode
candle_close) wakes you to decide.

## Candles at levels

A candle marks a moment, not a trade: it matters at a level, little mid-range. Read
it against the instrument's normal range; where it closes within its range says more
than its colour.
- Hammer after a decline, hanging man after a rally: one shape, named by the move
  before it; likewise inverted hammer and shooting star with the long upper shadow.
- Pin bar: a long wick rejecting a level, where orders were absorbed. Engulfing: the
  new body swallows the last, strongest at a zone edge.
- Doji and spinning top: balance, meaningful at an extreme after a run. Inside bar (its
  range inside the last one's) and harami (its body inside the last body): momentum
  pausing, not yet reversing; the inside bar's break is a timing cue.
- Morning or evening star: impulse, pause, reversal. Marubozu: conviction. Three
  soldiers or crows: continuation, often late. Tweezers: matched extremes, a level
  defended.
A watch's candle detector can flag engulfings, dojis, inside bars and pins on the close;
a flag is a hint, not a decision.

## Hybrid and unclassified structures

An unnamed structure described honestly beats a named one described wrongly.
- Hybrid: two shapes overlap, such as a triangle whose top is also a double-top
  neckline, or a flag inside a wedge. Do not pick a name and force the rest to fit.
  Describe the boundaries, touches and direction of pressure, and say "hybrid".
- Unclassified: shapes with no name are normal and never a reason to withhold a view.
  Work from primitives: where the highs and lows are, which side is defended, where
  liquidity rests, where the last impulse started. Build entry, stop and target from
  those levels as for a named pattern, and say it is unclassified; the missing name says
  nothing about quality.
- Name zero or one pattern, two only when both are truly there (a hammer at a
  double-bottom neckline). Never stamp a favourite template on a chart that does not
  show it; "no clear pattern" is honest.

## What to check

1. The break candle is closed: market_candles and chart_indicator end with the forming
   bar, unmarked (forming while its open time plus one timeframe is still ahead); drop
   it, or read market_snapshot, which reports it apart.
2. The close beyond the level against the ATR (market_snapshot) and the spread
   (market_quote: only the current one), on the leading timeframe.
3. The hour and the calendar: thin hours and pending releases breed false breaks
   (sessions-and-time, news-and-macro).
4. How breaks of this level resolved before, on the chart and in your reviews
   (search_internal).

## Weak when

The break comes late into higher-frame structure, in thin hours or just before a
release; the candle sits mid-range; recent breaks here failed; or the structure fits a
template only if you squint.

## Saying it

"1h closed above the range high with a full body; I take part now and add on a retest
that holds; a close back inside the range ends it." Or: "Unclassified: sellers defend
the upper area while lows rise; I plan the buy on a close above it, stop under the last
higher low."
