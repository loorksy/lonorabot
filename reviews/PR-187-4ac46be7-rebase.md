# PR #187 at 4ac46be7 — R-DOOR: rebase request (main 7ec9efaa, batch 9)

- `git merge-tree origin/main 4ac46be7`: conflict in `packages/tools/src/lonora_tools/terminal.py` (batch 9's "What is running" work, #190, changed the scan there). On rebase keep one `owner_scan` that every road uses — tool output, the process listing, and the CLI's notify/wake text — and rerun test_cli_notify_wake, test_cli_injection, test_workspace_access and the What-is-running tests.
