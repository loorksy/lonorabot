Superseded by VISION.md

# Proactive wakes that can act, and reading without walls

Agents react to events in their own
responsibilities and read all of the owner's data. Only money stays gated.

## Observe-only means no financial effects

A Run's tool scope comes from the Run row (`run_scope` in `lonora_tools/base.py`):

| Scope | Runs | Tools |
| --- | --- | --- |
| `full` | conversations, watches, routines, Tasks, a broker wake on the Agent's own positions, an opportunity wake | every registered tool |
| `observe_only` | wakes about events the Agent did not cause: the owner's manual broker activity (Personal Agent), the activation review; Tasks and tickets such a wake starts | every non-financial tool: memory writes, watches and routines, peer messages, owner alerts, artifacts, workspace, skills, narrowing restrictions |
| `helper` | temporary subagents (`trigger="subagent"`) | read-only tools plus `workspace_execute` and `artifact_create`; never memory writes, peer messages, new agents or financial tools |

The registry applies one rule (`Tool.permitted(scope)`) to exposure, the capability
inventory, discovery, skill eligibility (an observe-only wake loads no `financial`
skill; a helper loads `read_only` and `state_mutating` ones) and execution. A financial
tool outside a `full` Run fails with `observe_only_execution_forbidden` before any
work, and the registry re-checks the Run row for every financial call. The executor's
own check (`require_goal_lineage` in `lonora_trading/execution.py`) is unchanged: a
Run that is observe-only or a helper, or whose parent chain reaches one (its helpers,
peer runs and collaborations), can never send a broker mutation, through approvals
included. A Task or ticket started from an observe-only Run has no parent link, so it
inherits the narrowing instead (`inherited_authority` in `lonora_db/runs.py` stamps
`authority: observe_only` and `authority_run_id` on its Run): it keeps every
non-financial tool and its trades fail with `observe_only_execution_forbidden`. The
permission frame still shows such a Run as `analysis`.

Watches and routines an observe-only wake sets up are not narrowed: they are
the Agent's own later work (correction 25 keeps watch and routine changes for wakes),
and when they fire they run with the Agent's normal authority. Money still follows
the Agent's signed grant, the account limits, pauses and the manual-positions switch
at the executor.

Workspace writes follow the scope too (`scoped_run` in `workspace_access.py`): a
paused Agent writes nothing, a helper may only run `workspace_execute`.

## Broker events wake the Agent that owns the position

Reconciliation (`reconcile_broker_account`) compares broker snapshots and marks a
change `external` when no journaled Lonora operation explains it: a stop-loss or
take-profit hit, a manual close or edit. `attributed_agent` in
`lonora_trading/manual_activity.py` then reads the journal, newest first: the Agent
whose sent operation opened the ticket (by the broker id or the operation id the
ticket carries), else the latest Agent that managed it. The Agent comes from the
executor's own `details.execution.agent_id`, written from the fenced Run, never from
broker data. Each `BrokerActivity` carries that `agent_id` (None for the owner's
manual activity).

`wake_for_activity` in `broker_recovery.py` delivers each change once (effect receipt
`broker-activity:<id>`):

- An attributed change goes to its Agent: a `broker.external_activity` event in the
  Agent's conversation and one `broker_event` wake per revision in its work lane,
  **with its normal authority**. Its grant, the account limits and pauses still decide
  at the executor, and an uncertain operation is never resent. An "Ask me" Agent's
  trade becomes an approval card in its conversation.
- Unattributed activity (the owner's own) goes to the Personal Agent, as before, with
  `authority: observe_only`.
- Activity of a paused, delegated or missing Agent falls back to the Personal Agent,
  observe-only.

Run identities are stable (`external:<revision>` for the Personal Agent,
`external:<revision>:<agent>` for an attributed one), so a repeated reconciliation
creates no second wake. The owner's attention item for an attributed change opens
the responsible Agent's conversation.

An opportunity transition (`wake_opportunity` in `opportunities.py`) is the Agent's own
work, so its wake also carries normal authority.

A wake's records belong to its Agent's conversation (`report_thread` in
`lonora_db/threads.py`): approval cards, watches it sets up (Task watches stay with
their Task) and owner alerts. Whatever its authority, a work-lane Run (a broker or
opportunity wake, the activation review, a Task) also reads the conversation it came
from (`origin_read_threads` in `lonora_db/threads.py`: the same Agent's conversation, or
a group it belongs to).

## No duplicate effects from repeated wakes

- Each broker change and each opportunity version wakes once (effect receipts and
  stable run ids).
- Tool calls keep their receipts across a crash replay.
- `watch_create` takes an optional `dedupe_key`: one live watch per Agent and key.
  Re-arming with the same condition returns the existing watch (`deduplicated: true`;
  the request is compared as it would be stored, with the server-filled focus symbol,
  `MarketWatchRepository.stored_payload`); a changed condition disables the old one
  (`state.code = "watch_replaced"`) and creates the new one. A per-Agent and key advisory lock serializes concurrent wakes.
- Without a `dedupe_key`, a request identical to a live watch of the same Agent, in the
  same conversation or Task (the same stored payload), returns that watch
  (`deduplicated: true`) instead of adding a second one: a model that asks again after
  a worker restart, or a later wake that re-arms what is armed, keeps one watch. A
  changed condition, or a watch that was cancelled or has fired, is a new watch. With
  or without a key, a watch that no longer watches (expired, or its confirmation
  expired) is never the one returned: the request gets a new watch.
- `owner_notify` keeps one alert per Agent and `dedupe_key`.

## Reading without walls

Every agent, including a fixed-market (legacy bound) agent, reads every owned account
and symbol: quotes, candles, accounts, full history and activity, trade records,
decision history, opportunities, performance reads, sizing and
relationships. The read guard is the registry's own effect metadata
(`guard_market_tool(..., read=tool.read_only)`). Mutations keep the binding:
`agent_trading_account_mismatch` and `agent_trading_symbol_mismatch` now come only
from charts, watches, decisions, opportunity and relationship records and
financial tools, and the executor asserts the binding of every leased
request. `in_execution_scope` on accounts, positions and orders shows what the agent
may execute. See
[market-analysis.md](market-analysis.md#readable-and-executable-scope-of-fixed-market-agents).

Trading decisions on owner accounts are shared operational records: decision history,
reads and comparisons carry `recorded_by` (`agent_id`, `name`, and `you` when the
reader recorded it). Agents' private memory stays private.

## Agents alert the owner

`owner_notify` creates an owner attention item under the reach-me rules (dedupe, a
rate limit, quiet hours, "activity only"), and `owner_call_request` can target it. An
agent-declared critical alert passes quiet hours and "activity only"; beyond
`CRITICAL_LIMIT_PER_HOUR` (6) critical alerts per owner and rolling hour, across every
agent, a critical alert counts as an important change.
Delivery is in-app only until Wave 3. See
[incoming-attention.md](incoming-attention.md#agent-alerts-owner_notify).

## Verification

- `tests/test_proactive_wakes.py`: scopes and permitted tools; journal attribution
  (opener, manager, the owner's own order, a reservation) and a stop-loss close
  attributed to its Agent; quiet-hours end in the owner's timezone; the notify input
  bounds. On PostgreSQL: an observe-only wake writes memory, sets and dedupes a watch,
  messages a colleague and is refused `trade_execute` and `trade_close_positions`; the
  Task and ticket it starts are observe-only too, at the registry and the executor;
  observe-only, attributed broker and opportunity wakes read their conversation; a
  stop-loss hit on a simulation position an Agent opened wakes that Agent with normal
  authority, the owner's manual position wakes the Personal Agent, a repeated
  reconciliation wakes nobody twice; a paused Agent's activity falls back to the
  Personal Agent once; a fixed-market Agent reads another account (its other-symbol
  records and decisions unfiltered) and is refused trading and watches there;
  `owner_notify` dedupe, quiet
  hours, critical bypass,
  activity only, the rate limit and a call request from the wake.
- `tests/test_tool_discovery.py`: the eager budget for every scope, helper and
  observe-only membership, and the financial refusal before any work.
- `tests/check_opportunity_runtime.py`: one opportunity wake with normal authority.
- `tests/check_bound_market.py`: the focus-pair policy text.
- `tests/check_workspace_runtime.py`, `tests/check_workspace_skill_creation.py`,
  `tests/check_skill_packages.py`, `tests/check_market_analysis.py`: observe-only
  writes allowed, helper writes refused.
- `tests/check_agent_binding.py`, `tests/check_position_sizing.py`,
  `tests/check_decision_replay.py`: open reads, labelled decisions, bound mutations.
- Web and Mobile Playwright `agent-alert.spec.mjs`: the alert label and summary in
  Arabic and English, with no ids or evidence references shown; on Mobile an Arabic
  and an English summary in the Arabic interface each read in their own direction
  (`textDirection` in `apps/mobile/lib/text-direction.ts`, first strong letter, like
  the web's `dir="auto"`; `tests/mobile/text-direction.test.ts`).

## Limits

- Attribution reads the newest 1000 live journal rows of the account; an older
  position whose opening operation fell out of that window is unattributed and wakes
  the Personal Agent observe-only.
- An attributed wake that finds its Agent paused falls back to the Personal Agent; the
  paused Agent is not woken when it resumes.
- Off-app delivery of Agent alerts (push, messaging channels) arrives in Wave 3.
- Supervision (W15-6, `docs/supervision.md`): the Personal Agent reads other Agents'
  runs and memory by its lead role, whatever its grant, on demand.
