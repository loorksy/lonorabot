---
name: chart-patterns
description: Use when a chart pattern may be starting, forming, completing, confirmed or failing, and its stage has to become a plan type (أطلس النماذج الفنية)
---

# Chart Patterns

Follow the owner's current language in replies. Patterns are evidence you weigh, never
a gate; most good trades are not textbook shapes.

## What you are deciding

Whether a shape is really there, which stage it has reached, which plan that stage
suits, and where the idea is wrong.

## Read the shape yourself

Build it from closed candles (market_candles without its last, forming row) and
confirmed pivots (market_structure). No detector is required and none names it for
you: name the shape the chart shows, or say there is none. Context sets its worth: with
the higher-frame trend at a meaningful location (a range edge, a swept pool, a
higher-frame zone) a pattern counts far more than mid-range, and classic shapes alone
are weak evidence.

## Stages and the plan each suits

- Starting: few anchors. Context, not a trade; trade the level if anything.
- Forming: price between the boundaries. An anticipatory entry from a boundary on
  rejection, stop beyond it, said as the higher-risk choice.
- Near completion: pressing the completing level. Anticipatory from the boundary, or
  conditional on the break.
- Completed, unconfirmed: a close beyond, no follow-through yet. Immediate with tight
  invalidation, or conditional on a retest.
- Confirmed: break plus follow-through. Immediate, or a pullback plan if it ran far.
- Failed: broke the wrong way. The failure is itself a signal; often the other side
  is the trade, with the stop beyond the failure extreme.
The measured move (the height projected from the break) is a reference distance, not a
target; the next structure in the way usually comes first.

## The shapes

Breaks can be taken any way candles-and-breakouts lists; here is each shape's own read.
- Ascending or descending triangle: a flat side and a sloping side converging.
  Confirms on a close through the flat side, fails on a close through the sloping one;
  the anticipatory entry is a sloping-side rejection.
- Symmetrical triangle: both sides converge and the break decides; either boundary
  suits an anticipatory entry, stop just beyond. Triangles are weak with few clean
  touches or near the apex, where the range no longer pays for the spread.
- Rising or falling wedge: both sides slope one way and converge. A rising wedge tends
  to resolve down and a falling one up, often as exhaustion inside a trend. Enter toward
  that resolution at the boundary; a decisive close the other way fails it.
- Flag or pennant: a sharp impulse, then a shallow, orderly drift against it. Enter from
  the drift's far side; the break confirms it. A drift that retraces most of the impulse
  is not a flag.
- Double top or bottom: two rejections of one area, a neckline between. The second
  rejection is the anticipatory entry, stop beyond the extreme, first objective the
  neckline. A neckline close confirms it; a close beyond the extremes fails it, and that
  failure often runs.
- Triple top or bottom: a third touch, confirmed and failed the same way. Each touch
  spends the orders defending the area, so a third rejection that cannot push far away
  often precedes the break through it.
- Head and shoulders, or inverse: three swings, the middle one extreme, a neckline
  beneath. The right shoulder's rejection is the anticipatory entry, stop beyond it; a
  neckline close confirms, a close beyond the right shoulder fails. Weak with badly
  uneven shoulders or a steep neckline against the break.
- Rectangle: flat edges. Trade an edge on rejection; a sweep of one edge that closes
  back inside often beats the break.
- Channel: parallel sloping edges. Enter from the edge in its direction; the other edge
  offers a brief counter-move, and a close through it breaks the channel.
- Cup and handle: a rounded base, then a small drift. Enter from the handle low; a rim
  close confirms, a handle sinking deep into the cup fails. Weak when the cup is a V.
Hybrid, rounding, broadening and diamond shapes, and a range swept both ways before the
move (accumulation or distribution), are read from primitives (candles-and-breakouts).

## What to check

1. Closed bars for every anchor and the break, and touches that are real swings on the
   frame you judge, not lower-frame wicks.
2. The higher frame and the location in the dealing range (market-structure).
3. Room from entry to the next structure against the stop, after spread, and events
   that can run through the boundary (news-and-macro).
4. A conditional plan: market_decision_record, and a watch that wakes you on the close
   (watch_create, evaluation_mode candle_close).

## Weak when

The shape needs generosity to see, it sits mid-range against the higher frame, an
event lands before it can complete, or you found it after choosing the side.

## Saying it

One line: timeframe, pattern and its state, the entry, the stop beyond the breaking level,
the first objective, the close that ends it. No clear pattern: say so, name the plan's levels.
