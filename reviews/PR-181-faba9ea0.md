# PR #181 at faba9ea0 (re-check)

- Head: faba9ea0d89a0924cda14fd896d430be91b85c54 (merge of main e67be56d plus fixes)
- Base: main e67be56d. Reviewed the merge with `git show --remerge-diff` and the full diff against main.
- Verdict: **CLEAN**. My findings on 9f4ff02a (M1, L1) are fixed, and the rebase request is resolved.

## Verified
- M1 (the guard failed on main because of obsolete catalog entries): the ar and en web
  catalogs lose only `#~` (obsolete) Stop entries and their reference lines. No live
  `msgid` or `msgstr` is deleted (the diff has no removed non-`#~` msgid/msgstr
  line), and no msgstr is empty, so ar has 0 missing.
  tests/test_no_stop_control.py: 2 passed at this head.
- L1 (wrapped phrases): WORDS is now matched on whitespace-collapsed text, which catches
  the docs/incoming-attention.md:32-33 case, now reworded.
- Rebase: docs/operations.md takes main's line (no diff against main). The diff against
  main touches only the two catalogs, docs/incoming-attention.md and the new test.
  No 6.1-6.9 assertion touched, and none of main's protections lost.

## Rejected
- None.
