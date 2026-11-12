# PR #119 at 746c4a4c — R-DOOR: rebase request (main c5b5f1c2, batch 7)

- Batch 7 merged the Stop removal (#83), GenUI v2, workspace and push. `git merge-tree origin/main 746c4a4c` now reports 52 conflicting files. Rebase onto main, re-chain `0086_end_trading_restrictions` onto main's current head, regenerate manifest.json, and rerun check_restriction_removal_migration, check_risk_limits, check_owner_actions, check_agent_model_migration (it seeds a `lift_restriction` card) and the core checks. I review the rebased head in full.
