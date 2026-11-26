---
name: risk-and-sizing
description: Use when choosing the loss a trade may cost, sizing it from the stop in R, or weighing correlation, concentration, costs, gaps and drawdown (المخاطرة وحجم العقد)
---

# Risk and Sizing

Follow the owner's current language in replies. This is judgment, never a condition;
a number appears only as a marked illustration.

## What you are deciding

How much this trade may lose if it is wrong, the volume that makes the stop cost that
much, and whether the whole book with it is still one you would hold.

## Think in R

R is the money lost if the planned stop fills at its price. Plan, manage and review in
R so trades of any symbol and size compare.

## Size from the stop

Invalidation gives the stop (trade-planning); you choose the loss; the volume follows.
market_position_size (side, stop_loss, risk_budget in the exact account currency)
returns a volume rounded down to the broker's step from live tick values, measured from
the current price; it counts spread but not gaps, slippage, commission or swap. For a pending entry, size from the planned distance: the loss
divided by (planned entry-to-stop distance over the tick size, times the loss tick value
from market_quote), rounded down to the volume step and checked against the minimum
(market_instrument). If the tool refuses a planned stop on the wrong side of today's
price or inside its stops level, that says nothing about the plan; never move the stop
to make it answer. When even the minimum volume costs more than you chose, the trade is
bigger than intended: take it knowingly or pass.

## Choosing the loss

Your judgment, weighed from:
- conviction and setup quality: an aligned setup at a clean level earns more than a
  probe against the trend;
- your results with this setup (market_performance_read for its label);
- the account: equity, current drawdown, free margin;
- the owner: his mode, and his words in USER.md or your method, applied as given;
- the hold: gap and event risk, the weekend, liquidity.
Vary it on purpose and say why. Size that jumps after a loss to win it back is tilt, not
judgment (trader-psychology).
Illustration: a trader may risk a quarter of his usual amount on a counter-trend probe
and his full amount on a setup aligned with the leading frame; the scale is his.

## Correlation and concentration

Risk adds up by currency leg and by theme: a euro long against the dollar, a gold long
and a short on the dollar against the yen are largely one bet on a weaker dollar. Count
such positions as one, with their combined R. Read yours, the team's and the owner's
(account_read, the wake picture), and measure a link
with market_relationship_record before treating two symbols as independent or as a
hedge. A hedge lowers net exposure but keeps both costs and both gap risks.

## Scaling in and the combined stop

When you add, the trade's risk is the loss of all its positions at the stops that now
protect them. Securing the first position at break-even or better before adding keeps
the combined risk near the new position's own; adding without moving anything stacks R
on one idea.

## Costs, gaps and margin

- Spread, commission and slippage are a larger share of a tight stop; a stop a few
  spreads wide is mostly cost.
- Swap accrues on holds past rollover; its terms are the broker's: if your tools do not
  show them, say so and weigh the hold as if it costs.
- Weekend, holiday and event gaps jump stops: size a hold through them for the gap.
- A large position on little free margin can be closed by the broker before your stop.

## Survival and drawdown

Every edge has losing runs. Size so a normal run does not change how you trade or the
account's ability to keep trading.
Illustration: at even odds, a run of six losses in a row comes in about four of five
stretches of two hundred trades; winning four in ten, a run of eight comes in about
three of four.
In drawdown the responses are choices: smaller size, a higher timeframe, fewer entries
kept to your clearest setups, and a review of the losers for a cause before the method
changes (trade-review). No count of losses or hours forces a pause; normal size
returns when the cause is understood.
A stop moved away from invalidation raises R on the trade that is proving you wrong:
hope, not a plan.

## What to check

1. account_read: equity, free margin, every position and order, manual ones too.
2. market_instrument: volume minimum, maximum and step, contract size, tick size.
3. The volume (market_position_size or your pending count) against the minimum.
4. Events and the weekend inside the hold (news-and-macro, sessions-and-time).
5. Your results by label (market_performance_read) and the open R across your book.

## Weak when

The size came first and the stop was fitted to it; several positions are one bet counted
as many; there is no stop, so the loss is unknown; a hold through a weekend or a release
is sized as if the stop were guaranteed; size rose to recover a loss.

## Saying it

"One R here is my reduced amount: the stop sits beyond the 4h swing and the volume is
what the sizing returned; with the open euro long this is one dollar bet, so I size the
two as one trade."
