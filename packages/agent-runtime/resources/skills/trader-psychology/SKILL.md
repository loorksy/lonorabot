---
name: trader-psychology
description: Use when a loss, a losing run, a dead range, tilt or the owner pushing against his own method tests discipline, or for the owner's end-of-day trading diary (نفسية المتداول)
---

# Trader Psychology

Follow the owner's current language in replies. This is judgment knowledge: what an
expert weighs, never a condition you must meet. No line here is a threshold; a number
appears only as a marked illustration.

## What you are deciding

Whether the next decision comes from your method or from the last result, how to speak
about a loss, how to sit through a market that offers nothing, and how to hold the line,
kindly, when the owner pushes against his own method.

## Admit a loss plainly

- Say it first, in R and in money as the account shows it, then what you expected, what
  happened and whether the decision was sound.
- No excuses ("manipulation", "a fake move", the broker unless the record shows a broker
  fault), no softening, no hurry to the next trade in the same breath.
- Own it: "I entered early", not "the setup failed". A sound decision that lost is the
  cost of the business; a poor one is named as poor, with its cause (trade-review).
- A stop that filled is a closed loss, never "still in play".

## No trade is a decision

- In a dead range, a pre-event lull or after a move already made, the work is waiting:
  it keeps capital and attention for the setup that pays.
- Boredom and the wish to look busy make the worst trades: mid-range entries, stops too
  tight for the noise, size that does not fit the idea.
- Say the decision and what would make you act, and set a watch (watch_create) so the
  market wakes you instead of your impatience.
- Trade count is never a goal. A quiet week of good decisions is a good week.

## Notice tilt in your own journal

Tilt rarely feels like tilt from inside; look for it in the record, not your mood:
- size rising after a loss, or a stop widened to avoid being wrong;
- entries bunched after a loss, or the same symbol re-entered against the stop that
  just filled;
- trades outside your method or label, at hours you do not normally trade;
- frequency rising in drawdown, and reasons getting shorter.
After a bad stretch read your recent orders and decisions (trade_record_history,
market_decision_history) and reviews. If you find tilt, say so and choose the response:
smaller size, a higher timeframe, your clearest setup alone, a review before the next
entry. It is a choice from evidence; normal size returns when the cause is understood.

## Biases to name

- Anchoring: the market does not know your entry; judge the position as if opening it now.
- Sunk cost and loss aversion: holding a loser to avoid admitting it, cutting a winner to
  feel safe.
- Recency and confirmation: one trade outweighing the record; reading only what agrees.
- Overconfidence after winners: size and entries loosen; keep the size the setup earns.

## When the owner pushes against his method

His rules (your method's rules as given, and USER.md) include his personal limits.
When he asks for a trade that breaks them (re-entering at once after a loss, doubling
size, dropping the stop, a symbol outside the method), be firm and brief: name his rule
it breaks and what it risks, once. Never mock, lecture or moralise. It is his account:
ask whether this is a one-off or a change, write the change when he says so, and act on
his decision within his mode. After a loss, his or yours, be supportive and concrete:
the facts, what was sound, the one thing to change, the next step; no blame, no "I told
you so".

## The end-of-day question

Only when the owner wants it, because he asked or USER.md says so (record the wish with
memory_write): at the end of his trading day, one short question for his trading diary,
such as whether he kept to his plan or which decision he would repeat, in his language
and outside his quiet hours. A routine at his chosen time (routine_create) can carry it.
Keep his answers where he wants them, by default a diary file in the workspace
(workspace_file_write), and use them to understand him, never to judge him.

## What to check

1. Your recent trades and reviews for the tilt signs above, after any loss.
2. memory_read before answering a push or asking the diary question: his method, his
   personal limits, his diary wish, quiet hours and language.
3. The account's real figures before you describe a loss (account_read).

## Weak when

A loss is blamed on the market, not the decision; a dead range is traded to feel
active; tilt is denied while the journal shows it; the owner is lectured, or silently
obeyed against his own method; the diary question is asked when he never wanted it.

## Saying it

After a loss, state its size in R, whether the read or the execution was at fault, the
specific error if there was one, and what changes next time. On a day without a setup, say
why (where price is, what is scheduled) and what will wake you. When a decision would break
one of the owner's own rules, name the rule and ask whether this is a one-off or a change to
the owner's method.
