# PR #157 — W-ENV: Secret card targets (re-review at eae13b0b)

- Head: eae13b0b. New commit only: the merge of main 6f3eebb7 (batches 7-10) into b12a06a7.
- Reviewer: R-SEC
- Verdict: **CLEAN** for the merge. The two lows of PR-157-b12a06a7 are untouched by it and stand.
- **Rebase request:** `git merge-tree` against the current main (e67be56d, batch 11) conflicts in `docs/owner-actions.md`, the system manifest, `lonora_contracts/owner_actions.py`, `owner-actions.ts`, `lonora_tools/capabilities.py` and `tests/test_trusted_sources.py`. Please merge main again.

## What I checked
- **`git show --remerge-diff`** (31 files): the resolution applies this PR's removal of `connect_credential` and the capability cards to the code main brought in. `capability_cards.py`, the old owner-action kinds and the labels go.
- **Main's new tests** (push sender, morning brief, trading readiness, GenUI taint) now build a `secret`-kind card with the full Secret card payload in place of `connect_credential` (14.1.3). No assertion is dropped, and nothing is added beyond resolving the conflicts.
- **Migration:** `0071_secret_card_kinds` now chains to main's head `0139_workspace_running`, with one head. Upgrade, downgrade -1 and upgrade work on a fresh `_test` database.
- **Tests:**
  - test_secret_card, test_trusted_sources, test_push_sender, test_morning_brief, test_trading_readiness, test_genui_taint, test_release_manifest, test_secret_redaction, test_broker_secret_boundary, test_capability_exposure, test_owner_actions and test_attention give 224 passed.
  - check_simple_lonora passes (exit 0, including "no credential value in transcripts, events, cards or 67 model requests" and "32 conversation lines carry no raw ids or JSON"), and check_trusted_sources passes. ruff is clean.
