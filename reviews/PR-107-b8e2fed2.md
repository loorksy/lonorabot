# PR #107 re-review at b8e2fed2 (new own commit b303dbd0 since 5840a359; plus the #105/#106 merges)

Base reviewed: previous head; only the new own commits, plus the merge of the updated W-AUTH chain (wauth/3b-provenance 5ea33d05, R-DOOR's area). Reviewer: R-MONEY.
Verdict: **CLEAN** (one low note).

## Earlier findings
- **M1 (netting scale_in labels counted nowhere): fixed.** `netting_adds()` finds entry deals of closed netting trades whose order is not the position's opener, and the management query now counts those operations (`statistics.py:36-58, 99-107`).
- **M2 (unknown P&L shown as "0"): fixed.**
  - `_amount(None)` now returns None, and the TypeScript type is `string | null`.
  - The tool description and the `lonora.md` line now explain `unpriced` and a null net.
  - The manifest is regenerated.
- **L1 (`GENUI_PLAN.md:939`): open, low.** That line still says the tool "returns quality summaries".

## Note (not a finding)
`netting_adds` reads every closed trade of the owner, with its deals JSON, on each `market_performance_read`. That is unbounded over time. Bound it to the requested account and symbol, or move it into SQL, when the ledger grows.

## Checked
- `test_performance_summary`, `test_closed_trades`, `test_system_policy`: 19 passed.
- `check_trading`: passes.
- No `.venv` or `node_modules` entry in the tree.
