---
name: pre-trade-check
description: Use when about to send an order, to review the idea from the analysis side and the risk side (size, spread, exposure, news ahead), with a second model if useful (فحص ما قبل الصفقة)
---

# Pre-Trade Check

Follow the owner's current language in replies. This is judgment knowledge: what an
expert weighs, never a condition you must meet. No line here is a threshold; a number
appears only as a marked illustration.

## What you are deciding

Whether the order you are about to send is still the trade you planned, read once as
the analyst and once as the risk manager. This is a last look, not a gate: nothing here
blocks an order. Each finding is fixed (size, order type, timing), accepted and said, or
a reason to pass.

## The analysis side

- Is the thesis still true? Re-read market_snapshot or market_candles at the planned
  level, on closed bars, with no forming bar counted.
- Is price still where the plan was built? If it ran toward the target while you
  planned, the reward against the stop is no longer the one you planned (trade-planning).
- Does the leading timeframe still agree, or has a higher frame closed against you
  (multi-timeframe)?
- Invalidation: name in one line the close that proves you wrong, and see that the stop
  sits beyond it with room for this symbol's normal noise.
- The other side: state the strongest case against the trade. If you cannot, you have
  not looked; if it is stronger than yours, wait or pass.
- Your journal: reviews of this symbol and setup on both sides, and the label's
  results (market_performance_read).

## The risk side

- Size: the volume follows from the stop and the loss you chose (market_position_size in
  the exact account currency), within the volume limits and step (market_instrument),
  and the loss is the one you meant, not one fitted afterward (risk-and-sizing).
- Spread now against normal: market_quote gives it now, and no tool keeps a spread
  history. Judge normal from this symbol at comparable hours (your notes, earlier
  quotes) and from its share of the stop and of the timing frame's ATR. A spread far
  wider than usual means thin books, rollover or news: wait, take less size, or pass.
- Exposure: account_read shows every position and order on the account, manual and
  other agents' included (account_activity says whose); the wake picture groups the
  team by symbol and currency; other accounts need list_accounts, then account_read.
  Count positions on one currency or theme as one bet.
- News ahead: economic_calendar_read for the symbol's currencies over the hold; with
  configured false, or no source readable, there is no calendar evidence, so find the schedule publicly. A
  release inside the hold is a stance you choose (news-and-macro).
- The clock (rollover, the daily break, the Friday close, a cash open) inside the hold
  (market_sessions with at), and free margin after the order.
- The owner: his mode, and the personal rules he wrote in USER.md or your method. His
  rules apply as his words; the rest is your judgment.

## The order itself

The side and type match the plan: market, or a limit or stop on the correct side of the
quote. The stop and target are on the order and respect the stops level. A condition
decided on a close never pairs with a touch fill at the same level (trade-planning). The
label names the setup you will review it under, and the decision is recorded
(market_decision_record) with its invalidation.

## A second opinion

consult_model asks another available model for an independent critique. It earns its
cost when the size is above your usual, the trade runs against the higher frame, the
evidence conflicts, or you trade after losses. It has no tools and sees only the pack
you send: the draft decision, the facts with their times and sources, and a question
such as "what is the strongest reason this fails?". Send facts, not your conclusion
dressed as fact, and no credentials or private details of the owner. Its answer is
advice: weigh each point on its evidence, never count votes, and say what you changed.

## What to check

1. Fresh closed bars against the plan's level.
2. market_position_size, then the volume against the specification.
3. market_quote spread against normal and against the stop.
4. account_read for exposure; economic_calendar_read and market_sessions over the hold.
5. The decision recorded and the order's fields read back before sending.

## Weak when

The check is a ritual that never changes anything; a finding is noticed, left unsaid
and sent anyway; the trade is re-justified instead of challenged; a second model's
agreement is taken as proof; price moved and the plan was not redone.

## Saying it

"Checked before sending: the 1h higher low holds, the size is my reduced amount because
the spread is wide for this hour, the open euro long makes this one dollar bet, and
nothing is scheduled before the London close. Buying." Or: "Passing: price ran most of
the way to the target while I planned, so the trade is no longer worth its stop."
