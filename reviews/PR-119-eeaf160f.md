# PR #119 at eeaf160f — R-DOOR re-review (since d8515173)

- Verdict: **CLEAN** for the new commit + **rebase request**
- eeaf160f: catalog only — the two restriction activity labels become obsolete (`#~`) and line references move, in both locales together.

## Rebase request
`git merge-tree origin/main eeaf160f` (main 6cb4421d, batches 4-5) conflicts in apps/api/src/lonora_api/routes/owner_actions.py, docs/owner-actions.md, resources/system/lonora.md, manifest.json, lonora_agent/environment.py, contracts/src/owner-actions.ts, memory/guard.py, tools/agents.py. On rebase, re-chain `0086_end_trading_restrictions` onto main's current head (0176 now has two children on the merged tree), regenerate manifest.json, and rerun check_restriction_removal_migration and the core checks.
