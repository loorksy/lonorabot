# Persistent trading goals

Apply database migration `0015_trading_goals` with `bash scripts/migrate.sh` before starting the updated API and worker. The existing worker hosts market streams, chart state, routines, watches and goal recovery; a second process is unnecessary.

Ask an ordinary agent to create a goal with an exact broker symbol, account and ordered steps. `goal_create`, `goal_read`, `goal_decisions`, `goal_plan`, `goal_wait`, `goal_step_complete`, `goal_step_execute`, `goal_list` and `goal_control` participate in its existing tool loop. A planned trade may reference a previous entry step through `target_step_id`; the backend resolves the broker's actual position/order identity. Pending entries wait for an observed fill through durable scheduled reviews.

Open the agent profile → Goals to review the plan, volume/action limits and execution evidence. Background financial execution defaults to OFF. Only the authenticated owner can enable it or expand its limits. Changing the financial plan disables autonomy again. Global Trading ON/OFF and Emergency Stop apply to every execution, including goal steps and descendant runs.

Price/indicator/account watches and routines wake the same agent, thread and goal. Every financial step rebuilds fresh broker evidence and rechecks the condition before using the existing preflight and serialized execution journal. Operation identity stays fixed for a goal/step/attempt across worker retries. Uncertain results remain blocked until broker reconciliation; a restarted worker does not blindly submit the order again. Pausing or cancelling prevents new goal actions and never closes an existing broker position by itself.

The Goals panel reads saved progress and decision evidence from PostgreSQL. Cloud chart candle state and indicators also remain on the server when all clients disconnect. The Web and Expo clients render authenticated scene events; periodic reads provide reconnection fallback.

Regression checks use disposable PostgreSQL databases and explicit simulator or SDK transport fixtures. No test submits a live broker trade: `check_goals.py` includes a worker process crash after the simulated broker effect, lease recovery and reconciliation without resubmission; `check_pending_orders.py`, `check_chart_streaming.py` and the Web/Expo browser tests cover the connected surfaces.
