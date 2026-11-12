# PR #192 at 31313c03 — R-DOOR: rebase request (main e67be56d, batch 11)

- #119 (its base) and #187 are now on main. `git merge-tree origin/main 31313c03`: 7 conflicts — ar/en messages.po, manifest.json, packages/tools/src/lonora_tools/base.py, tests/web/openui-chat-ux.spec.mjs, tests/web/safety-truth.spec.mjs, and docs/analytical-workspace.md (deleted on main by #194; drop it, don't re-add). Rebase onto main (0087 onto main's migration head), regenerate catalogs and manifest, rerun check_money_limits_migration, check_send_boundary and the core checks.
