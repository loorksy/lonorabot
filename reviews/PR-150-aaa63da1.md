# PR #150 re-review at aaa63da1 (new own commit aaa63da1 since c49f1ce8; plus merges of #149 and the current pause/2-paused-agent accdcced)

Reviewer: R-MONEY. Only the new own commits plus what they touch.
Verdict: **CLEAN** (one low left).

## Earlier findings
- **H1 (wake starvation): fixed.** Woken trades are excluded in SQL (`~exists` on the `close-wake:` receipt key) before the limit, which is now `MAXIMUM_PER_PASS`. The case "woken trades never crowd out a new close" passes.
- **M1 (11.5): fixed.**
  - A Run with `closed_trade_id` skips the `no_answer` nudge (`tool_loop.py:597-602`), so it may end empty, and `outcome_return` posts nothing for an empty result.
  - The wake text now says to reply only if something needs the owner.
- **M2 (deleted agent): fixed.** Lonora is woken through `ensure_personal_agent` with "you answer for its tickets", both in `wake_for_closes` and in `_redirect_unread`, with no permanent skip. The case "a deleted agent's closed trade wakes Lonora" passes.
- **Rebase:** the current `pause/2-paused-agent` is merged, and the manifest is regenerated.

## Open
### L1. `_redirect_unread` still limits before it filters
- It reads 200 unconsumed notices, oldest first, and only afterwards drops those whose Run is still executing (`close_wake.py`, `_redirect_unread`).
- With more than 200 notices waiting on executing Runs, a stopped Run's notice waits until those are consumed. The delay is only temporary: executing Runs consume their notices, and Lonora is single-owner (17).
- Fix: filter on the owner (a join to `ClosedTradeRow`) and on non-executing Runs in SQL, before the limit.

## Checked
- `check_close_wake` passes.
- `test_tool_loop_execution`: 26 passed.
- `check_trading` passes.
