# PR #182 — W-WS step 2b: background workspace processes recorded and told (7.1.2)

- Head: afa1ef75. Base: main c5b5f1c2, which the PR contains; `git merge-tree` shows no conflict. Own diff: 9 files, +356/-2.
- Reviewer: R-SEC
- Verdict: **CLEAN**

## What I checked
- **Migration:**
  - 0136 is in the W-WS range (0135-0139) and chained to main's single head `0110_closed_trades`; `alembic heads` shows one head.
  - Upgrade, downgrade to 0110 and upgrade again all work on a fresh `_test` database.
  - The table, check constraint and indexes match `WorkspaceProcessRow`; the cascades go to the owner and the agent.
- **Secrets:** the stored command is `result["process"]["command"]` from `client.run`, which returns `scan.data(result)` under the owner's scan. Every secret form is replaced before storing, and the value is stored as the scan left it (the docstring is true). The gateway listing is scanned with an empty scan, but only ids, times and exit codes are kept from it, as the comment says. Nothing is logged.
- **Ids:** supervisor job ids are `uuid4().hex` (32 characters), which fits `String(32)`. The boot id is a uuid4 (36).
- **Reconcile:**
  - A change of `boot_id` gives `restarted`.
  - A job missing from the listing is `lost` only if its row is older than the listing by more than `SETTLE`. A row inserted after the listing was fetched always has `started_at` after `fetched_at`, so it is not misread.
  - The supervisor keeps 500 ended jobs (`ENDED_KEPT`) and the gateway ticks every 10 s, so an ended job is not pruned before it is seen in practice.
  - Concurrent reconciles write the same values. Reported rows are deleted after 7 days.
- **Notice:**
  - It is given only to a `full` run, so a helper or an observe-only wake does not use it up.
  - It locks with `FOR UPDATE`; a row is marked with the first run and shown for that run's retries only, which is idempotent.
  - It is limited to the last 10, with a count of the earlier ones. The section is `agent_authored` because it quotes the agent's own commands.
  - It is agent-facing text, not an owner view.
- **Safety core (Section 6):** the door, journal, approval and preflight are untouched. The terminal tool's scope check (`require_ordinary`) stays before the run.
- **0.4:** the docstrings and comments are true at this commit.
- **.venv:** the tracked symlink from #122 is removed, and `.gitignore` now matches `.venv` as a file or a link.
- **Merge commits:** they only resolve the chain (0136 follows main's head); no added behavior.
- **Tests:** test_workspace_processes plus every test touching the context builder, terminal, gateway service, release manifest and migrations give 686 passed and 1 skipped.

## Rejected findings
- A failed DB write after a background start leaves the process untracked and the tool reporting an error: not reproduced as reachable (owner and agent rows exist for any ordinary run), so not a finding.
- Clock skew of more than 5 s between the host running the tool and the gateway host could mark a just-started job `lost`: deployment-only, and not reproducible here.
