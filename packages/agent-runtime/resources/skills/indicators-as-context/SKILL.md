---
name: indicators-as-context
description: Use when reading moving averages, RSI, MACD, ATR, Bollinger width, tick volume, Fibonacci or VWAP as context for a decision, not as a trigger (المؤشرات كسياق)
---

# Indicators as Context

Follow the owner's current language in replies. This is judgment, never a condition;
a number appears only as a marked illustration.

## What you are deciding

What an indicator adds to a view built on structure: agreement, a warning, or a unit
for distance and volatility. An indicator alone is never a trigger and never a side.

## Ground rules

- Nearly every indicator is a transformation of price. Several momentum readings that
  agree are one piece of evidence, not several.
- Read closed bars on the timeframe you judge. Empty values at the start of a series
  are warm-up: not enough history yet, never zero.
- Parameters are your choice for your horizon; state them. Choosing them after seeing
  the chart is fitting the evidence to a wish.
- Compare a reading with its own history on this symbol, not with a level from a book.

## Moving averages

The slope shows direction and steadiness over the window. In a trend, price holds one
side of a rising or falling average and pullbacks find it; the distance from it,
measured in ATR, shows stretch. Crossovers lag and whipsaw in ranges, and a flat
average that price keeps crossing says range. Widely watched averages draw reactions
because many traders watch them.

## RSI

Momentum of closes. In a trend it tends to stay in its own half, upper in uptrends and
lower in downtrends, and a shift of that regime is evidence. An overbought reading in a
strong trend is strength, not a sell. Divergence (price makes a new extreme, RSI does
not) says momentum is fading, not that price will turn; it can persist through several
swings and matters at a level, ideally with a structure shift.

## MACD

The gap between two exponential averages and its signal line: momentum and its change.
A shrinking histogram says the push is tiring; zero-line crosses lag. Divergence reads
as with RSI. Here macd uses the classic fixed settings; the period you pass does not
change it.

## ATR and the volatility regime

ATR is the typical bar range, the unit for stops, buffers, reach and whether a move is
large for this symbol. market_snapshot gives its percentile against recent history and
a regime label (low, normal, high, or not enough history). Low volatility tends to
precede expansion without telling its direction; high volatility tends to cool. A stop
sized in a quiet stretch gets run in an expansion. ATR lags after a shock and is
inflated by a news spike. It never says which way.

## Bollinger width

Bands a fixed number of standard deviations around a simple average whose period you
choose. Width is volatility: a squeeze against its own history often comes before
expansion, direction unknown. Walking the band in a trend is strength; a close outside
the band inside a range is stretch.

## Tick volume

Broker candles here carry tick volume, a count of price changes: a proxy for activity,
not traded volume. Compare it only within this broker and symbol and at the same time
of day; it rises at every session open whatever the conviction. A break on rising
activity is cleaner than one in thin trade.

## Fibonacci areas

Retracement levels between a swing's start and end, drawn with chart_annotate from
confirmed pivots. They work as areas where they agree with structure, largely because
many traders watch them; a level alone is no reason.
Illustration: the most watched retracements are 38.2, 50 and 61.8 percent of the swing.

## VWAP and pivots

Neither is built in. Compute them in the workspace: market_candles_to_workspace, then
workspace_run. VWAP needs an anchor (a session open, a swing, an event) and on currency
and CFD candles weights by tick volume, so it approximates. Floor pivots come from the
prior day's high, low and close, so they follow the broker's day boundary. Both are
watched levels, not forecasts.

## What to check

1. chart_indicator (sma, ema, rsi, macd, atr, bollinger) or market_snapshot for ATR
   and RSI; state the name, period and timeframe you used.
2. Closed bars, with warm-up values behind you. market_candles and chart_indicator end
   with the forming bar, unmarked (forming while its open time plus one timeframe is
   still ahead): drop it, or read market_snapshot, which reports it apart.
3. The reading against its own history on this symbol.
4. Agreement with structure (market-structure): the indicator supports or warns, the
   level decides.
5. An indicator watch (watch_create) can wake you; on waking, read the structure again.

## Weak when

The indicator is the only reason, its parameters were chosen after the fact, the
regime has just changed, a news spike distorts ATR and the bands, or tick volume is
compared across brokers or hours.

## Saying it

"Price made a higher high at the range top while RSI made a lower one; momentum is
fading, so I plan the sell if 1h closes back inside the range." Or: "ATR is in its high
regime; I keep the stop at structure and reduce size rather than tighten the stop."
