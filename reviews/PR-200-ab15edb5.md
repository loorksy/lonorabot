# PR #200 — W-WS 6: the workspace not answering yet at start-up is not a failure

- Head: ab15edb5. Base: main batch 9 (7ec9efaa); own diff is the single commit ab15edb5 (3 files, +107/-2). `git merge-tree` against the current main shows no conflict.
- Reviewer: R-SEC
- Verdict: **CLEAN**

## What I checked
- **The guard is narrow:**
  - Only `workspace_unavailable` (connect refused or connect timeout, `client.py:164-165`; a non-dict answer, `:179`), and only before the supervisor has answered once since this Gateway started, is logged at INFO (`workspace_not_reached_yet`) and returns.
  - Any other code (`workspace_outcome_unknown`, a request error), or the same code after a first answer, still raises and is a step failure.
- **Order:** `workspace_reached` is set only after a successful listing, before reconcile and the What-is-running record. Nothing is skipped once the workspace answers.
- **Logs:** no secret and no listing content are logged.
- **Text (0.4):** `docs/operations.md` is true. `lonora` reports a workspace that never starts; the Gateway's INFO line is the only Gateway signal in that case, which the docs state.
- **Tests:** test_workspace_startup (new; both halves through the real step runner), test_workspace_running, test_workspace_processes and test_gateway_reliability give 36 passed on a fresh `_test` database. ruff is clean.

## Rejected findings
- A workspace that never starts shows no Gateway step failure. This is by design and documented: `lonora start` and `update` report it, and the agents' tools return `workspace_unavailable`.
