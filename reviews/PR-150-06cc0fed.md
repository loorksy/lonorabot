# PR #150 re-review at 06cc0fed (carried onto integration/batch-14 3f371259)

- Reviewer: R-MONEY.
- Base: re-review of the new commits on batch 14:
  - e05b06fe..2b68b532 re-apply the reviewed close-wake commits;
  - fc166d53 adapts the paused case;
  - d17d5d3d is the carry merge;
  - 06cc0fed passes the calendar's secret reader.
- Verdict: **FINDINGS** (0 high, 1 medium, 0 low).

## M1. While Lonora is paused, deleted agents' closes starve every other agent's wake (5.5.1)
**Where:** `packages/trading/src/lonora_trading/close_wake.py:166-184`.

**How it happens:**
1. The SQL filter leaves out only trades whose own `agent_id` names a paused agent.
2. A trade of a deleted agent still carries that agent's id. `ln_closed_trades.agent_id` has no foreign key, so the id stays, and the trade passes the filter.
3. In Python it is redirected to Lonora, and `if agent.paused: continue` skips it without a receipt.
4. So, with Lonora paused, those trades stay at the front of every pass (`order_by created_at`, `limit MAXIMUM_PER_PASS`).

The result: once there are 50 or more such trades within `WAKE_WINDOW` (2 days), no other agent's close is woken. The SQL filter was added precisely so that waiting trades never fill the pass.

**Reproduced** (probe `/home/user/wt/probes/pr150_paused_lonora.py`, run in the head's tests directory with run.sh):
- Setup: Lonora paused; 50 closes carrying ids of agents that do not exist; one close of a live, unpaused agent.
- Result: three passes of `wake_for_closes` each woke 0, and the live agent has 0 `broker_event` Runs.

**Fix:**
- Read Lonora's paused state first. While she is paused, also leave out, in SQL, the trades whose agent is missing or owned by someone else: `exists().where(AgentRow.id == ClosedTradeRow.agent_id, AgentRow.owner_id == owner_id)`.
- Apply the same in `_redirect_unread`.
- Add the probe's case to `check_close_wake.py`.

## Merge note for W-PAUSE and the lead (not a finding at this commit)
- **The interim behavior:** fc166d53 makes a paused agent's closed trade wait unwoken, and drops it if the pause outlasts the 2-day window. This is true at this commit, because batch 14 has no `runs_while_paused` and `create_run` refuses a paused agent.
- **Why it changes later:** W-PAUSE #99 makes a paused agent wake for its own tickets (4.7.1, 14.3.7).
- **What to do:** whichever of #150 and #99 merges second must restore the earlier behavior: wake the paused agent with the risk-reducing sentence (`PAUSED_SENTENCE`), and remove the SQL paused filter and the `continue` lines. Otherwise, after both merge, a paused agent never reviews its closes.

## 06cc0fed
- `cache_calendar` now takes `read_secret`, and the gateway passes `service.secrets.read`.
- `check_calendar_picture` failed without it and passes with it.
- No secret value is logged.

## Checks
- These pass (rc 0):
  - `check_close_wake`, `check_calendar_picture`, `check_account_picture`, `check_task_wake_context`;
  - the five core checks.
- pytest, the closed-trades, calendar and core files: 108 passed.
- Manifest `--check`: OK.
