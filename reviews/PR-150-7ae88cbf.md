# PR #150 re-review at 7ae88cbf

- Reviewer: R-MONEY.
- Base: re-review of new commit 7ae88cbf, on 06cc0fed.
- Verdict: **CLEAN**. M1 from PR-150-06cc0fed.md is fixed.

## The fix
- `wakeable(owner_id)` filters in SQL, before the limit, in both `wake_for_closes` and `_redirect_unread`:
  - a trade whose own agent is paused;
  - while Lonora (`role == "personal"`) is paused, a trade whose agent is missing or foreign.
- My probe (`/home/user/wt/probes/pr150_paused_lonora.py`) now wakes the live agent's close in the first pass, and the agent gets 1 `broker_event` Run.
- `check_close_wake` adds `lonora_paused`: 50 deleted agents' trades with Lonora paused, and the live close still wakes. When Lonora resumes, all 50 wake her.
- **Mutation:** with `wakeable` reduced to `~paused`, that check fails with an `AssertionError`. The test guards the fix.

## Merge note (carried)
Whichever of #150 and W-PAUSE #99 merges second must restore waking a paused agent for its own trade, with `PAUSED_SENTENCE` (4.7.1), and drop the paused filter.

## Checks
`check_close_wake`: all 10 PASS lines, rc 0.
