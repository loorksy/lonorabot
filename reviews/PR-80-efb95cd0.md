# PR #80 — W-TASK: Full mode runs one continuous account-management task per agent (4.5, 14.3.3)

- Head: efb95cd0. Own commits: 47ad2acd, c8967a38, 5da5a9e0, 1fe0e6da, 3604c46b, efb95cd0. Base: wauth/3b-provenance.
- Reviewer: R-MONEY. This is the check the lead asked for once the head moved past 3604c46b.
- Verdict: **FINDINGS** (0 high, 2 medium, 1 low).

## The lead's four issues
- **Failed but resumable Task: fixed.** Probe with the real retry shape: Task `waiting`/`retry_wait` with `failure.next_retry_at`, Run `failed`.
  - The Task counts as live, and a second Full tap leaves exactly one open Task.
  - Ask cancels it and clears `next_retry_at`; `retry_due_tasks` then resumes nothing.
  - A Task that failed for good is closed before a new one starts.
- **Timers: fixed.** A Run suspended on its `task_wait` timer becomes a one-shot routine at the same `due_at`. Watches move to the conversation. The agent's other routines are untouched (4.5.3).
- **Lock cycle: fixed** for pause, `update_agent`, `control_work`, the creation Undo and the owner's delete (efb95cd0). **Not fixed for Ask** (M1 below).
- **Cards: fixed.**
  - Pause and Ask leave cards pending, because the waiting Run is detached; 10.3.1.3 lists no pause withdrawal.
  - Delete withdraws them in `prepare_delete` (3.1.2).
  - Full withdraws them through `withdraw_pending`.

## Findings

### M1. Switching to Ask can deadlock against the task's own Run (6.7 lock order)
- **Where:** `packages/db/src/lonora_db/trading_mode.py:42-66`. `set_trading_mode` takes `authority_lock`, writes the agent row (`agent.trading_mode = mode` and `flush`), and only then calls `end_management_task`, which locks the task's Runs.
- **The other side:** a tool transaction of the task's Run locks the Run first and the agent row second. `atomic_commit` in `lonora_memory/commit.py` does this: `require_lease(lock=True)`, then `owned_agent(lock=True)`.
- **Effect:** PostgreSQL aborts one side. Either the owner's tap to Ask, or the agent's own `trading_mode_ask`, or the memory write fails.
- **Reproduced:** by the subagent's contended probe (`DBAPIError: deadlock detected` on the Ask transaction; the same contention against `pause_agent` completes). I confirmed the order by reading `trading_mode.py:42-66`.
- **Fix:** right after `authority_lock`, `if mode == "ask": await end_management_task(session, owner_id, agent_id)`, before `_agent(...)`; then drop the `else` branch at `:65-66`. In `check_management_task`, add a contended Ask case whose tool transaction locks the agent FOR UPDATE (the current case uses `key_share=True`, which never conflicts with the row write).

### M2. After a pause, the task's in-flight Run can still open new risk (4.7.1)
- **Where:** `management_task.py:207-222` (`detach`).
  - On a pause, `close_task` removes `task_id` from the running Run, so `require_task_authority` no longer stops it.
  - At this head the door has no paused-agent check (grep of `execution.py` and `agent_permission.py`).
- **Reproduced:** by the subagent's probe. A Full agent's kickoff Run was running with a lease. After `pause_agent`, `ExecutionService.execute` of a new `buy` on that lease returned `confirmed`, with one send.
- **Context:** this gap exists for ordinary Runs of a paused agent in the base. The PR extends it to the task's Runs, which a cancelled task would otherwise have refused at the door. W-PAUSE's #99 (`require_pause_allows`, under the authority lock) closes it for every Run.
- **Fix, either:**
  - merge #80 together with or after #99; or
  - until then, refuse non-reducing requests at the door when the Run's agent is paused, in `require_operation_permission`, which already receives `reducing`.
  
  Add a case: after the pause, a buy is refused and a close is sent.

### L1. The creation Undo now always pauses an agent the owner tapped Full on, instead of deleting it
- **Where:** `agent_creation.py:323-338` (`undo_plan`). Any Ticket or Run counts as "has done something", and that includes the mode Task and its never-started kickoff Run.
- **Reproduced:** by the subagent's probe. The plan is "delete" before the Full tap and "pause" after it, with nothing else done. W-TEAM 4.3.3 will make created agents in Full common.
- **Fix:** in `undo_plan`, ignore Tickets with `payload.account_management_agent`, and the never-started Runs that belong to them.

## Out of scope
- An inline comment on `trade.py:746` (tolerance not rechecked at send) concerns W-AUTH's base code; it is not this PR's diff.

## What was checked
- **Concurrency:** two Full taps serialize on `authority_lock`.
- **Restart:** `resume_ready_waits` resumes the same Run.
- **Lock order:** consistent against `resume_failure` and `wake_waiting_run`, and against the trade tool and the door.
- **Door:** `require_task_authority` passes detached Runs, and 6.1-6.9 are unchanged apart from the two correct `account_management_id` guards.
- **Other:** no migration, and the Arabic task title exists.
- **Runs** (fresh databases):
  - `check_management_task` (13), `check_trading_mode`, `check_task_recovery`, `check_continuous_task_runtime`, `check_trade_approvals`, and the five core `check_*.py`: all pass;
  - `test_trading_mode`, `test_trading_mode_tools` and the six core pytest files: 120 passed.
