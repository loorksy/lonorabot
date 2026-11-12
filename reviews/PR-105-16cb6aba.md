# PR #105 re-review at 16cb6aba (new own commit 16cb6aba since 3ebcb06d)

Base reviewed: previous head; only the new own commits, plus the merge of the updated W-AUTH chain (wauth/3b-provenance 5ea33d05, R-DOOR's area). Reviewer: R-MONEY.
Verdict: **CLEAN**.

## Earlier findings
- **M1 (a reversal of an unseen position lost the trade it closed): fixed.**
  - `trades()` now closes a trade at every reversal; `unseen` is set when no earlier trading deal is kept.
  - The volume of such a trade is unknown: `ln_closed_trades.volume` becomes nullable in the unmerged `0110` and in `schema.py`.
  - The test covers the case.
- **L1 (commission booked as separate deals): fixed.** `position_deal` now keeps non-trade charge deals that carry the position, and `deal_pnl` counts them so they can only lower P&L. Balance, credit and bonus cash flows are excluded (`CASH_FLOW_DEALS`).

## Checked
- `test_closed_trades`: 5 passed.
- Nothing else reads `ClosedTradeRow.volume` at this head; the statistics (#107) do not use it.
