# PR #105 — W-LEDGER 1: the closed-trade ledger from broker deal history (5.5.1)

- Head: 3ebcb06d (ledger/1-closed-trades)
- Base reviewed against: d6b4a41 merged with ledger/0-realized (585d75e); own commits 960a0e5, b6efd2f. The final merge 3ebcb06 adds only ledger/0's last commit 59e0c74, a docstring change.
- Reviewer: R-MONEY
- Verdict: **FINDINGS** (0 high, 1 medium, 1 low)
- Rebase request: conflicts with the current `wauth/3b-provenance` 8704653 in `packages/db/src/lonora_db/schema.py` and `packages/gateway/src/lonora_gateway/service.py`. `0110` chains from `0061`, so the W-AUTH chain has to land first.

## Findings

### M1. A netting reversal of a position the ledger never saw open loses the trade it closed (5.5.1)
- In `packages/trading/src/lonora_trading/closed_trades.py:155-168`, `trades()` cuts a closed trade at a reversal only when `len(current) > 1`.
- When the `INOUT` deal is the first deal kept for the position, it becomes the opening of the running trade (`Trade.__init__`, `:121-128`). The trade it took through zero is never recorded. This happens when the opening deal is older than the first read (30 days before connection), or was listed after the 15-minute overlap.
- This contradicts the PR's own rule: a plain `OUT` of such an old position does get a row with unknown P&L (the `old-1` test).
- The subagent's probe reproduced it: `anc-1` was 0.1 long, history held only `INOUT SELL 0.3`, and the broker then listed 0.2 short. `record_closed_trades` returned 0. After the close, only the sell trade had a row; the long trade had none. Confirmed by reading `trades()`.
- Fix:
  - In `trades()`, when the first ordered deal is `INOUT`, first append a closed `Trade` ending at that deal, with `opening=None` and `after_reversal=False`. This is the `write_trade` first-read case: owner by position id, P&L NULL, volume unknown.
  - Then start the running trade at the same deal, as today. The unique key `(owner, account, position, closing_deal)` keeps re-reads idempotent.
  - Add the case to `test_reversals_partial_reads_and_positions_older_than_the_ledger`.

### L1. Commission booked as separate deals is left out of P&L
- `closed_trades.py:86-106`: only `DEAL_TYPE_BUY`/`SELL` deals count, and a missing `commission` or `swap` counts as 0. On brokers that book commission as its own deal type, the trade's P&L reads too high instead of unknown.
- Unverified on a live broker (code reading only).
- Fix: count non-BUY/SELL deals carrying the trade's `positionId` through `deal_pnl`. Or state the limit in the module docstring.

## Rejected (one line each)
- An exit listed more than 15 minutes late can leave a trade unrecorded forever: not reproduced. Optional hardening: after N reads, record it on the broker's position read alone with NULL P&L.
- A trade after a netting reversal belongs to the reversing agent's order: the PR states this reading, and the door's `ticket_agent` agrees.
- Rows keep a deleted agent's id; there is no transfer to Lonora: 3.1.2's transfer is W-TEAM's, not on this base.
- Backfill on first deploy covers 30 days: noted for W-PICTURE's close wake (5.5.2), which must not wake on backfilled rows.

## What was checked
- **5.5.1 and 6.4.** A close needs an exit deal, exits that sum to the entries, and a position read taken after the history read. A partial close produces no row (probe `pf-1`). Every value comes from broker deals; the journal supplies ownership only, and only from confirmed rows.
- **3.3.4.** The opening order is matched by position or order id. A pending fill belongs to the journaled `buy_limit`'s agent (probe: gold's, P&L 3). A netting add never matches. Terminal and EA tickets belong to the owner.
- **Hedging and close-by.** Several positions per symbol and `OUT_BY` closes give one row each (probe: h-1 = 3, h-2 = -2).
- **Idempotency and restart.** The unique key is (owner, account, position, closing deal). One transaction covers the rows and the cursor. Duplicate deals collapse on the primary key.
- **Safety core.** Untouched, with no new `broker.execute` caller. Logs carry codes only. No owner text, screen, prompt or tool changes.
- **Migration `0110_closed_trades`.** It is in range, has a single head, and downgrades to 0061 and upgrades again.
- **Runs** (fresh databases): `test_closed_trades` and `test_realized` 7 passed; the five core `check_*.py` pass; the six core pytest files 101 passed; ruff clean.
