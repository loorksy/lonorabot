Superseded by VISION.md

# Persistent trading goals

Apply database migration `0015_trading_goals` with `bash scripts/migrate.sh` before starting the updated API and worker. The existing worker hosts market streams, chart state, routines, watches and goal recovery; a second process is unnecessary.

Ask an ordinary agent to create a goal with an exact broker symbol, account and ordered steps. `goal_create`, `goal_read`, `goal_decisions`, `goal_plan`, `goal_wait`, `goal_step_complete`, `goal_step_execute`, `goal_list` and `goal_control` participate in its existing tool loop. A planned trade may reference a previous entry step through `target_step_id`; the backend resolves the broker's actual position/order identity. Pending entries wait for an observed fill through durable scheduled reviews.

Open the agent profile → Goals to review the plan and its execution history. A goal is a plan under the agent's trading level and signed grant; it carries no authority of its own (W15-9, migration `0040_retire_super_bot_requests`). There is no per-goal autonomy switch, no Super Bot request and no owner limit knob on a goal: its owner controls are Pause, Resume, Review now and Cancel. A live step follows the agent's current level like any trade: No trading refuses it, Ask me waits for the owner's approval card, and On its own sends it inside a matching signed grant, while a step the grant does not cover becomes one approval card instead of a refusal. The owner's pauses and the account's money limits apply to every execution, including goal steps and descendant runs. A goal's `maximum_volume` and `max_trade_actions` are plan data, not limits: nothing enforces them, `goal_read` and the goal context frame show them as `planned_volume` and `planned_trade_actions` beside the account and symbol `scope`, and an owner's hard cap goes to a restriction or the account's money limits. The execution history shows the step and its status; the operation id, the decision evidence and the raw broker result sit behind "Technical details".

Price/indicator/account watches and routines wake the same agent, thread and goal. Every financial step rebuilds fresh broker evidence and rechecks the condition before using the existing preflight and serialized execution journal. Operation identity stays fixed for a goal/step/attempt across worker retries. Uncertain results remain blocked until broker reconciliation; a restarted worker does not blindly submit the order again. Pausing or cancelling prevents new goal actions and never closes an existing broker position by itself.

The Goals panel reads saved progress and decision evidence from PostgreSQL. Cloud chart candle state and indicators also remain on the server when all clients disconnect. The Web and Expo clients render authenticated scene events; periodic reads provide reconnection fallback.

Regression checks use disposable PostgreSQL databases and explicit simulator or SDK transport fixtures. No test submits a live broker trade: `check_goals.py` includes a worker process crash after the simulated broker effect, lease recovery and reconciliation without resubmission; `check_pending_orders.py`, `check_chart_streaming.py` and the Web/Expo browser tests cover the connected surfaces.

## Shadow goals (removed)

Shadow (virtual) trading is removed (owner decision Q57). Every Goal is a live plan under its agent's level and grant. Migration `0053_remove_shadow_trading` cancelled every unfinished Shadow goal with the code `shadow_trading_removed`; a finished one stays as history, and a Goal or Run still marked Shadow is refused (`goal_execution_mode_invalid`, `shadow_execution_forbidden`), never run live.
