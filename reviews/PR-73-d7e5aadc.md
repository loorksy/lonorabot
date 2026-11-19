# PR #73 at d7e5aadc (re-check); also #74 at c69ff14c and #75 at 4aeb93ce

- #73 head d7e5aadc. New since 68d5bd2d: one tests-only commit to tests/test_mandate_card.py.
- #74 head c69ff14c and #75 head 4aeb93ce: merges carrying it down. Both have an empty
  `git show --remerge-diff` (no conflicts to resolve).
- Verdict: **CLEAN** for all three.

## Verified
- test_lonoras_card_for_a_deleted_agent_ends_with_it now marks the Run it leased as
  completed in its finally block. Before, that Run stayed working in Lonora's shared
  conversation, so later owner turns there were taken as steering (admit_runs). No
  product code changed, and no assertion changed.
- Reproduction (fresh *_test DBs) of test_mandate_card plus test_owner_model:
  - at 68d5bd2d, 2 failed and 10 passed (test_owner_model's
    what_i_know_lists_origins... among them);
  - at 4aeb93ce, 12 passed.
