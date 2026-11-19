# PR #81 at 0afa6c5a: CLEAN

- Reviewer: R-AGENT, 2026-11-19T12:20Z
- Main: de96cb30 (migration head 0200_old_workspace_data).
- Verdict: CLEAN

- New since d111e89d (CLEAN): merges of main dcf86b43 and integration/batch-14, and commit 960c4451.
- `--remerge-diff` of the merges:
  - `routine.py` keeps `reaches` and drops `taint_row_from`, as batch 14 did; it is unused;
  - `docs/supervision.md` takes main's wording without the money limit and keeps the lead-role and 6.10 sentences;
  - the catalogs and manifest are regenerated.
- 960c4451: `check_simple_lonora` now asserts that Lonora `reaches` the news and desk agents by its role, in place of the default grants that no longer exist.
- Ran: `check_simple_lonora` (rc 0); `test_supervision` and `test_lead_powers` (13 passed).
- Rebase: `merge-tree` with main de96cb30 gives 1 conflict.
