---
name: trade-planning
description: Use when turning a view into a plan, with its type, entry, stop at invalidation, targets on structure, reward to risk after costs, or two conditional scenarios (تخطيط الصفقة)
---

# Trade Planning

Follow the owner's current language in replies. This is judgment, never a condition;
a number appears only as a marked illustration.

## What you are deciding

The plan for your view: side or no trade, how it fills, where it is wrong, where it
pays, whether it is worth the cost, and what wakes you.

## Three layers, kept apart

- View: bias and why.
- Plan type: immediate (at market now), anticipatory (in while a structure still forms:
  better price, less confirmation) or conditional (a stated trigger).
- Execution state: valid now, awaiting trigger, expired or invalidated.

## How it fills

Say it: at market, on a touch (a limit or stop order), at a confirming close, or on a
return into a band. A close-decided condition never pairs with a touch fill at the same
level: a stop order there fills on the wick before the close confirms, and a limit there
needs a return the condition never asked for. For a close trigger, a price watch with
evaluation mode candle_close wakes you to enter. A limit also fills on moves that keep
going through it; a stop order joins momentum and pays spread and slippage. Buys trigger
on the ask, sells on the bid; a pending price inside the broker's stops level is refused.

## Reach, stop and targets

- Reach: when price cannot plausibly get to the entry within the idea's life (its ATR,
  the session left), even a strong view is a watch: CONDITIONAL_ENTRY plus watch_create.
- Stop: at the structural invalidation plus room for this symbol's normal noise (recent
  wicks through similar levels, timing-frame ATR, spread at your hours), not on the
  obvious level where stops cluster. A stop squeezed to fit a size or a ratio is no
  longer at invalidation: when the right one is too wide, trade smaller or pass.
- Targets: on real structure and liquidity (next swing, prior day or week extremes, the
  range's far edge, equal highs or lows): the first where the move likely pauses, a later
  one where the larger structure points.
- Reward to risk after costs is a description to weigh against how likely the target
  is, never a gate.
Illustration: stop 10 away, spread 1, target 20 away: reward 19 against risk 11, about
1.7 to 1.

## Two conditional scenarios

Around a key level (a range top, a swept high) you may plan both outcomes:
- Breakout buy: a buy_stop beyond the level by more than its usual probes, stop back
  inside under the structure that launched the break, target the next liquidity above.
- Failed-break sell: a sell_stop under the level where a return inside shows the break
  failed, target the range middle or far edge. Its stop sits beyond the probe's extreme:
  placed in advance, near the buy trigger, and you may tighten it past the real probe
  once that prints (modify_order).
Both rest as pending orders; when one fills, cancel the other (trade_execute
cancel_order): nothing links them; the fill wakes you through broker activity.
Know beforehand:
- a fast market can fill both first: a netting account nets them, a hedging one keeps
  both;
- a deeper probe than usual fills the buy and then fails it; a sell after that is a new
  decision;
- the sell_stop also fills on a plain fall; to trade only the failed break, place it once
  a price watch shows the probe;
- both are touch fills, each sized as its own trade, and neither expires: set a timer
  for the end of the idea's life (routine_create with run_at, or task_wait in a task)
  that wakes you to cancel both.
Record each with market_decision_record as CONDITIONAL_ENTRY: direction, trigger,
invalidation, and which order it cancels.

## No trade

Not trading is a decision. Say what would change your mind: the level, the close, the
time. Record it when it matters (market_decision_record, WAIT).

## What to check

1. Fresh quote and spread (market_quote); tick size and stops level (market_instrument).
2. Closed bars for the trigger; name a forming bar as forming.
3. Events and session ends inside the idea's life (news-and-macro, sessions-and-time).
4. Positions and orders already on this symbol and correlated ones (account_read).
5. Your results and past decisions for this setup (market_performance_read,
   market_decision_history), losers as well as winners.
6. Size from the stop (risk-and-sizing), not the stop from the size.
Give every order its reason and a judgment label you reuse for this setup. Set the watch
or timer before you promise to monitor.

## Weak when

The target sits behind an obvious level; the stop sits where everyone's does; entry
needs a long trip before the session ends; the ratio needs a squeezed stop; a lower-frame
trigger fights the leading frame.

## Saying it

"Conditional: buy stop above the range high, stop under the breakout base, first target
the prior-day high; if price probes above and falls back inside, the sell stop takes
over and the buy is cancelled." Or: "No trade: the buy area is far and the session ends
soon; a 1h close back above the swept high makes it a plan."
