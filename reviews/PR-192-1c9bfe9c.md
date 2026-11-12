# PR #192 at 1c9bfe9c (re-check after the rebase request)

- Head: 1c9bfe9c0a7af15383f76e9fcea613447f9b78a5 (merge of main e67be56d into remove/money-limits)
- Base: main e67be56d. Reviewed the merge with `git show --remerge-diff`. The branch's own commits are unchanged since 31313c03 (CLEAN).
- Verdict: **CLEAN**. The rebase request (7 conflicts after batch 11) is resolved.

## Merge resolutions verified
- 0087_end_money_limits: down_revision is now 0138_skill_package_files, main's head
  (main's chain is 0139 -> 0086 -> 0137 -> 0138), so there is one head.
  check_money_limits_migration steps down to 0138 and PASSes: data steps, the
  recomputed grant-draft hash, the superseded duplicate card, the downgrade and the
  repeat upgrade.
- tools/base.py: takes batch 11's helper wording ("reads and reports, never workspace
  commands ...") without "and limits", which is true at this commit.
- #76's money-limit UI is gone: LimitsSheet.tsx is not in the tree, and no code
  references money_limits or execution-policy outside migrations. The
  openui-chat-ux M4 and safety-truth M11 Playwright steps for the limits are removed
  with the feature (14.1.3). Batch 10's menuitem changes are kept.
- Catalogs: every remaining LimitsSheet reference sits on an obsolete (#~) entry, with
  no live entry, and ar has no empty msgstr. docs/analytical-workspace.md stays deleted
  as on main. manifest.json was regenerated: test_system_policy checks manual_sha256
  and passes.

## Runs (fresh *_test DBs, this head's code)
- check_money_limits_migration: PASS. check_send_boundary: PASS (rc 0).
- pytest: 142 passed. That covers the six core files (broker effect verification,
  execution records, preflight identity, reconciliation history, tool execution core,
  financial admission), plus test_system_policy and test_capability_exposure.
- Web: `tsc --noEmit` clean.

## Rejected
- "LimitsSheet still in the catalogs": obsolete entries only, which never reach a screen.
