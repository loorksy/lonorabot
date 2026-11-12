# PR #149 re-review at defa33cc (new: merges of #147's fix and ledger/3-statistics eecad684, and own commit defa33cc)

Reviewer: R-MONEY. Only the new own commits plus what they touch.
Verdict: **CLEAN**.

- **Rebase: done.** ledger/3-statistics is merged at eecad684, so `netting_adds` is bounded (60e402c7).
- **M1 (frame text): fixed.** The frame now says:
  - all trades the ledger recorded, starting 30 days before each connection;
  - per opening label and account currency, most used first, at most 20 rows;
  - net over priced trades, with `unpriced` counting the others and null when none is priced;
  - management labels, at most 20.
- **L1 (tests): fixed.** `check_account_picture` now covers a partly unpriced row, a second currency and the row bound. It passes.
