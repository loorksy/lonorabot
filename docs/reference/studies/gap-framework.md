# Gap analysis: the framework (processes, persistence, run lifecycle)

Audience: Lonora developers. Lonora was read at `d8193b98` (`/home/user/wt-agent/fxmain`, read-only). The reference
projects were read through their reports (`ref/reports/openmausbot-framework.md`, `ref/reports/rakazo-framework.md`)
and spot-checked read-only in the clones (OpenMausBot `140172d`, rakazo `10973b5`). Nothing was run from either clone.
All Lonora paths are repo-relative.

The binding texts used: `VISION.md` 0.4, section 6 (the safety core, never weakened), 14.1, section 17, Amendments 1-3,
and `docs/cloud/DECISIONS.md`. No recommendation below adds a Stop control, adds a venue other than MetaTrader 5, or
changes any clause of section 6. Two of them (R2, R8) make section 6 easier to keep, and none of them relaxes it.

## Ranked recommendations

| # | Recommendation | Verdict | Priority | Effort | Source | Owner decision |
|---|---|---|---|---|---|---|
| R1 | Detect a wedged or dead Gateway from outside the Gateway, and restart it | adapt | P1 | M | both | no |
| R2 | Drain at a step boundary, within one deadline that fits the stop grace | adapt | P2 | M | both | no |
| R3 | Alarm on owner and broker-event runs left queued (queue-age check) | adopt | P2 | S | rakazo | no |
| R4 | Claim by wake priority and run age, not by thread age; size the worker pool on its own | adapt | P2 | M | both | no |
| R5 | Tell a late routine that it is late, and count what was collapsed | adapt | P2 | S | both | no |
| R6 | One transition gate for every run status write, plus invariant tests | adopt | P2 | M | both | no |
| R7 | Expire streaming projection events of finished runs | adopt | P2 | M | both | no |
| R8 | One Gateway per installation, enforced by a Postgres lock, with immediate recovery at boot | adapt | P2 | M | both | no |
| R9 | Retry the final commit of a run on a transient database error | adopt | P3 | S | rakazo | no |
| R10 | Use `LISTEN/NOTIFY` as a wake-up latch for run claims and event streams (polling stays) | adapt | P3 | M | both | no |
| R11 | Framework counters for the Lonora Cloud host agent, with no trading data | adapt | P3 | M | rakazo | yes |
| A1 | The run row is the queue: claim, lease, fence, fenced writes | already-better | - | - | both | no |
| A2 | Restart rules for outward effects, per tool call | already-better | - | - | both | no |
| A3 | Supervised steps, per-item isolation, deterministic watchdog, quarantine that holds runs with unresolved trades | already-better | - | - | both | no |
| A4 | Agent-to-agent delivery as one transaction plus a normal run | already-better | - | - | rakazo | no |
| A5 | Update, rollback, held rollback and maintenance mode | already-better | - | - | both | no |
| A6 | Send serialization per account rather than a run-level lease on the MT5 account | already-better | - | - | rakazo | no |
| S1 | Spend caps and budget stop modes | skip | - | - | openmausbot | no (already decided) |
| S2 | A "reads and drafts only" fence on unattended runs | skip | - | - | openmausbot | no (already decided) |
| S3 | Expiry for approval waits (stuck-work expiry, per-action approval lifetimes) | skip | - | - | rakazo | no (already decided) |
| S4 | Multi-tenant row-level security, a separate job queue, memory-based admission, starting runs inside the API | skip | - | - | rakazo | no |

P1 means it can silently stop the always-on promise today. P2 means a concrete defect or gap with a contained fix.
P3 means an improvement worth doing when the area is touched.

---

## 1. What Lonora does today

### 1.1 Processes

| Process | Entry | Role |
|---|---|---|
| API | `apps/api/src/lonora_api/app.py` (`create_app`), command `api` in `entrypoint.sh` | FastAPI: every request from the apps, the event WebSocket `/ws/events` (`apps/api/src/lonora_api/websocket/events.py`) and SSE `/api/events/stream` (`apps/api/src/lonora_api/routes/events.py`), `/health` and `/ready` (`apps/api/src/lonora_api/health.py`), and the `lonora` CLI endpoint on a Unix socket. It runs no agent and opens no MetaApi connection. |
| Gateway (the worker) | `apps/worker/src/lonora_worker/main.py` → `lonora_gateway.service.Gateway.serve` (`packages/gateway/src/lonora_gateway/service.py`) | One asyncio process. It runs `maximum_subagents + 1` shared run workers plus one reserved `conversation` worker (`service.py:481-503`), and 35 supervised maintenance steps (`STEPS`, `service.py:48-103`): routines, task waits, retries, outcome returns, reconciliation, verification rechecks, account recovery, broker relay, provisioning, market, watches, approval drift, attention, push, channels, the workspace, the morning brief and the watchdog. |
| Database | `postgres:16-alpine` in `infra/compose/docker-compose.prod.yml` | The only shared state, queue and bus. |
| Migrate | the `migrate` service, run as its own step by `infra/compose/lonora` | Alembic (`packages/db/migrations`). |
| Workspace and `workspace-net` | `lonora_workspace.supervisor`, `lonora_workspace.netguard` | The owner's Linux workspace (VISION 7.1), reachable from the Gateway through a control socket. |
| SearXNG, research browser, Caddy | compose services | Tools and TLS. |

How they talk to each other:

- **API → Gateway, run work.** The API writes a `ln_runs` row (`create_run`, `packages/db/src/lonora_db/runs.py:149`). Each
  Gateway worker polls `claim_next` every `worker_poll_seconds` (0.5 s by default, `apps/api/src/lonora_api/env.py:89`).
  There is no `LISTEN/NOTIFY` anywhere in the code.
- **API → Gateway, broker access.** Broker reads and the owner's own orders go through the `ln_broker_relay` table
  (`packages/db/src/lonora_db/broker_relay.py`), served by the `broker_relay` step every 0.2 s
  (`packages/gateway/src/lonora_gateway/broker_relay.py`). Only the Gateway holds MetaApi connections
  (`docs/operations.md`, "Only the Gateway keeps MetaApi connections").
- **Gateway → clients.** Every state change is an `ln_events` row written in the same transaction (`emit`,
  `packages/db/src/lonora_db/events.py:104`). Clients stream by cursor. `stream_events`
  (`packages/bus/src/lonora_bus/durable_events.py:21`) polls every 0.1 s for 5 s after the last event, then every 0.5 s.
  Each poll runs `publish_committed` (`events.py:28-61`), which takes the global advisory lock `1524053101` and assigns
  commit-ordered public cursors, so a late commit cannot fall behind a client's cursor.
- **Agent to agent.** A transactional write plus a normal run (`delegate_peer`,
  `packages/agent-runtime/src/lonora_agent/collaboration/peer_messages.py`), with outcomes returned once by receipt
  (`outcome_receipt(run_id, fence)`, `collaboration/outcome_return.py:27`). See A4.

### 1.2 Persistence

Everything is Postgres through SQLAlchemy (`packages/db/src/lonora_db/schema.py`), with one owner per installation
(VISION 17 as replaced by Amendment 3.1). The tables that matter for this topic:

- `ln_runs` (`RunRow`, `schema.py:405`): `status` with a CHECK constraint on the eight values, `lease_owner`,
  `lease_fence`, `lease_expires_at`, `recovery_count`, `execution_state` (the fenced checkpoint: transcript, pending
  calls, environment, retry deadline), `model_metadata` and `trigger`.
- `ln_events` (`EventRow`, `schema.py:445`): one global autoincrement cursor per installation, with the public cursor in
  `payload._ln_public_cursor`. It is both the client projection log and a store of some domain facts that code reads back
  (`trading_decisions.py`, `trading_opportunities.py`, `agent_creation.py`, `memory.py`, `attention.py`,
  `context/environment.py`). Nothing deletes from it.
- `ln_gateways` (`GatewayRow`, `schema.py:701`): heartbeat plus a per-step liveness snapshot.
- `ln_item_failures` (`ItemFailureRow`, `schema.py:710`): per-item backoff and quarantine for maintenance steps.
- `ln_effect_receipts`, `ln_trading_journal` and the rest of the trading tables are owned by section 6 and are not
  changed by anything here.

### 1.3 The run lifecycle

The state table is a declared port of rakazo's `run-state.ts` (`packages/core/src/lonora_core/run_state.py:1-28`,
attribution in `THIRD_PARTY_NOTICES.md`), with one addition, `running → queued`:

```
queued → leased → running → completed | failed | cancelled
                  running → waiting_input | waiting_takeover → queued | leased
                  running → queued   (retry backoff, drain release)
failed → queued   (owner retry)
```

1. **Create.** `create_run` (`runs.py:149`) locks the thread, checks the agent's pause (VISION 4.7), strips server-only
   metadata keys and emits `run.queued`.
2. **Claim.** `claim_next` (`runs.py:239`) locks one eligible thread with `FOR UPDATE SKIP LOCKED`, then its oldest
   eligible run. Eligible means `queued`, or `leased`/`running` with an expired lease and `recovery_count < 5`, and past
   any retry deadline in `execution_state.environment.retry.not_before`. A thread with an active lease is skipped, so
   turns in one conversation never overlap. The claim increments `lease_fence` and sets a 120 s lease
   (`run_lease_seconds`, `env.py:90`).
3. **Run.** `execute_run` (`packages/agent-runtime/src/lonora_agent/executor.py:100`) renews the lease every 40 s and
   retries transient database errors until shortly before expiry (`keep_lease`, `executor.py:45-74`). Every write goes
   through `require_lease` (`runs.py:358`), which checks owner, fence and expiry, and the door checks it again (VISION
   6.9).
4. **Wait.** A question or a Trade Approval moves the run to `waiting_input` and drops the lease (`executor.py:282`). A
   timer, external wait or pause uses `waiting_takeover` (`packages/db/src/lonora_db/tasks.py`).
5. **Finish.** `complete_run` (`runs.py:421`) refuses while steering messages are unconsumed, then writes the final
   message and `run.completed`. `fail_run` (`runs.py:513`) records a failure family. `return_outcome` delivers the result
   to a parent or peer exactly once.
6. **Crash and resume.** After a lease expires, the run is re-claimed with `recovery_count + 1` and resumes from its
   checkpoint with `interrupted=True`. A call that is neither read-only nor replay-safe comes back as
   `tool_execution_uncertain` and is never re-sent (`tool_dispatch.py:83-96`). Financial calls reconcile the same
   operation id (`tool_dispatch.py:43-70`). After five recoveries the watchdog fails the run with
   `run_recovery_limit`, unless it holds an unresolved financial operation, in which case it is held for reconciliation
   (`quarantine_run`, `runs.py:590`; `watchdog.py:191`).
7. **Drain.** On SIGTERM, `serve` waits up to 25 s for the worker and step tasks, then cancels them (`shutdown.py:8`).
   It then waits up to 30 s for relay requests (`RELAY_DRAIN_SECONDS`, `service.py:44`), returns its leases to `queued`
   with the fence kept (`release_leases`, `runs.py:551`) and closes its connections.

### 1.4 Always-on and proactive triggers (the framework side)

Every trigger is a durable record that starts an ordinary, bounded run. This is the shape both references
converged on.

- Routines: `ln_routines` with `next_run_at`, fired by the `routines` step every 5 s (`dispatch_routines`,
  `packages/automation/src/lonora_automation/runner.py`). Missed schedules collapse into one wake after downtime
  (`routines.py:170`).
- Market watches: checked in code by the `watches` step every 2 s (`wake_dispatch.py`, `lonora_market/watchers.py`).
  The model is woken only when a watch fires ("checks before the model").
- Task waits and timers (`task_wait.py`), broker events (`close_wake.py`, attributed wakes), `lonora wake` from
  workspace scripts (`workspace_wakes.py`), signed webhooks (`lonora_agent/automation/webhooks.py`), and the morning
  brief as its own step (`morning_brief`).
- Background runs may end silently (VISION 11.5: `BACKGROUND_TRIGGERS`, `run_state.py:42`).

---

## 2. What OpenMausBot and rakazo do better or differently

| Area | OpenMausBot | rakazo | Lonora |
|---|---|---|---|
| Process model | One Node process per home owns everything; the engines are child processes | API plus worker over Postgres; both can start runs | API plus a single Gateway over Postgres; only the Gateway runs agents |
| Job record | `runtime.db` assignments plus `assignment_events`, invariants I1..I10 asserted in tests | `Run` plus `Attempt`, `canTransition`, string statuses | `ln_runs` with a CHECK on values; `assert_transition` is called once (R6) |
| Claim and fence | Single writer by lease file | Atomic `updateMany` claim, `leaseFence`, fenced history writes | `FOR UPDATE SKIP LOCKED` claim, fence, `require_lease` on every write (A1) |
| Lease and heartbeat | n/a | 5 min lease, 60 s heartbeat, outage grace | 120 s lease, 40 s heartbeat, outage grace |
| Wake-up | In-process timers plus `kick()`, with a pace-driven tick (250 ms busy, 10 s parked, 1 h idle) | `NOTIFY runs:ready` as a latch plus a 5 s scan | Fixed 0.5 s poll per worker (R10) |
| Event stream | SSE with a replay buffer, or a fresh snapshot | SSE with a per-thread `seq` and NOTIFY latch; transient run events deleted at finalize | WebSocket or SSE with a global public cursor; nothing is ever deleted (R7) |
| Outward effects on restart | Per turn: rerun once unless the host reports an outward action, then `failed(interrupted)` | Effects replayed in a stable order from `ExternalEffect` | Per tool call: uncertain, never re-sent, financial reconciled by the door (A2) |
| Drain | 8 s deadline chosen to sit below Docker's 10 s | Stop claiming; runs finish their current step (up to 5 min) and hand back with no failure; `stop_grace_period: 50m` tied to the drain timer | 25 s, then cancel wherever the run is; relay 30 s more; stop grace 40 s (R2) |
| Process health | Compose healthcheck, crash guard exits 70, the launcher restarts with backoff | Worker health file every 30 s for the Docker healthcheck, `watchEventLoopStalls` | Heartbeat row and `/ready`; no Gateway container healthcheck, no loop-stall guard (R1) |
| Queue health | n/a | `run.queue_delayed` when an interactive run is due and unstarted for 30 s | Logs `queue_ms` at dispatch; no alarm (R3) |
| Lanes | Admission surfaces (`direct`, `unattended`, `guarded`, `peer`) | Interactive and background lanes, interactive scanned first | One reserved conversation worker; shared workers claim the oldest thread first (R4) |
| Missed schedules | Occurrence ledger with counted `missed` rows; catch-up within 12 h, staggered | Coalesced catch-up run, and a run 15+ minutes late is told both times | Collapsed silently (R5) |
| Singleton | Data-dir lease file (pid, boot id) | Advisory-lock leader for the reconciler | Operational only: `lonora` stops the old Gateway first (R8) |
| Finalize under outage | n/a | `retryWhileDatabaseUnavailable` around `finalizeRun` | One attempt; a transient error at the final commit fails the run (R9) |
| Spend caps | `usage-caps.ts`, stop unattended or everything | Spending limits | Forbidden by P1 and the owner's decisions (S1) |

---

## 3. Recommendations

### R1. Detect a wedged or dead Gateway from outside the Gateway, and restart it (P1, adapt, M)

**Gap.** Everything that would notice a stuck Gateway runs inside the Gateway: the watchdog, the heartbeat step and the
attention items it raises (`watchdog.py`, `heartbeat.py`). Readiness is computed from the heartbeat row
(`health.py`: `HEARTBEAT_FRESH = 45 s`) but only `/ready` reads it. Several things are missing:

- The `gateway` service in `infra/compose/docker-compose.prod.yml` has no `healthcheck`. The db, api, searxng, browser
  and workspace-net services each have one.
- No client reads `/ready` (no match in `apps/web/src`, `apps/mobile`, `packages/core/src`).
- The status line (`packages/db/src/lonora_db/trading_readiness.py`) does not know about the Gateway.
- No thread watches the event loop.

A Gateway whose event loop is blocked, or that has deadlocked, does not exit, so `restart: unless-stopped` and the
systemd unit's `Restart=on-failure` (`infra/systemd/lonora-gateway.service`) never fire. Runs, reconciliation, watches,
approval drift, push and the morning brief all stop, and the owner is told nothing. In Lonora Cloud the host agent's
30 s heartbeat would report it to the operator (`docs/cloud/PLAN.md`, the "Heartbeat (30 s)" row), but the
self-hosted owner gets nothing, and even in the Cloud the owner sees nothing in the app.

**What the references do.** rakazo's worker writes a health file every 30 s for a Docker healthcheck, and runs
`watchEventLoopStalls` (`apps/worker/src/index.ts:81-87`). OpenMausBot has a compose healthcheck, plus a crash guard
that exits with code 70 so the launcher restarts it with backoff.

**Adapt.**

1. A loop-stall guard: a plain `threading.Thread` started in `apps/worker/src/lonora_worker/main.py` that checks a
   timestamp the asyncio loop updates once a second. Past a stall limit (for example 120 s, above the longest legitimate
   synchronous section), it dumps the stacks with `faulthandler`, logs a stable code and calls `os._exit(70)`, so the
   existing restart policy restarts the process. Restarting is safe by construction: leases expire or are fenced (A1),
   in-flight sends are ambiguous and reconciled, never re-sent (6.3).
2. A container `healthcheck` for `gateway` that reads this process's own liveness (a small file written by the heartbeat
   step, as rakazo does, or its `ln_gateways` row). This shows up in `lonora status` and in the Cloud host agent, which
   already reads service state.
3. The API process, which is separate and still alive, adds "the worker is not running" to what the apps already read,
   computed from `gateway_health`. For example, `trading_readiness.py` or the attention view (VISION 11.7) shows one
   line while no Gateway heartbeat is fresh. It is an honest status line (VISION 17), not a control.

Whether the API should also send a push in that case (VISION 11.4 lists broker health problems) is a product question
I leave open. The three steps above need no decision.

- Files: `apps/worker/src/lonora_worker/main.py`, `apps/worker/src/lonora_worker/health.py` (today a 6-line wrapper),
  `packages/gateway/src/lonora_gateway/heartbeat.py`, `packages/gateway/src/lonora_gateway/health.py`,
  `infra/compose/docker-compose.prod.yml`, `infra/systemd/lonora-gateway.service`,
  `packages/db/src/lonora_db/trading_readiness.py`, `apps/api/src/lonora_api/health.py`, `docs/gateway-reliability.md`,
  `docs/operations.md`.
- VISION: P6, 3.1.5 (system alerts, connection health), 11.7, 17 (status line; durable runs with recovery after
  restarts), Amendment 3 (the host agent already consumes `/ready`). There is no conflict, and section 6 is untouched.

### R2. Drain at a step boundary, within one deadline that fits the stop grace (P2, adapt, M)

**Gap.** `Gateway.serve` (`service.py:505-520`) waits 25 s for the worker loops and then cancels whatever is running
(`shutdown.py:8`). After that it waits up to 30 s for relay requests, then calls `release_leases`. The container gets
`stop_grace_period: 40s` (`docker-compose.prod.yml:96`) and systemd gets `TimeoutStopSec=40`. So:

- Every turn longer than 25 s is cancelled wherever it is: mid model stream, mid tool call, or mid broker send. Nothing
  in `lonora_agent` sees a shutdown signal (no match for `draining`, `stopping` or `shutdown` in
  `packages/agent-runtime/src`). The door turns a cancelled send into `ambiguous`/`operation_interrupted_before_send`
  and reconciles it (`execution.py:440-455, 558-590`). That is correct (6.3), but every deploy or restart during a turn
  can create uncertain operations, "not confirmed" lines and Settle cards that a clean hand-back would have avoided.
- 25 s plus 30 s is more than 40 s. If an owner's order arrives through the relay late in the drain, the process can be
  SIGKILLed before `release_leases` runs. Lease expiry (120 s) remains the fallback, so this is safe but slower.

**What the references do.** rakazo's stopping worker claims nothing new and lets each run finish its current step (up
to `RUN_DRAIN_MS = 5 min`, `run-wakeup.ts:35`). The run then saves its turn and hands back as `queued` with no failure
recorded, and `stop_grace_period: 50m` is tied to that timer. OpenMausBot runs all cleanup concurrently under one 8 s
deadline chosen to sit below Docker's 10 s.

**Adapt.**

- A stop event on `ToolContext`, checked by the tool loop before each model call and before starting each tool call.
  When it is set, the run checkpoints (as it already does per round) and is released to `queued` with
  `reason_code: gateway_drained`, which is the existing `release_leases` path, so it does not count as a crash recovery.
- A financial call already in flight is never cancelled by the drain: it finishes inside its own broker deadline.
- One shutdown deadline, computed below the stop grace (for example 30 s inside a 40 s grace, or raise the grace), with
  run drain and relay drain running concurrently rather than one after the other.

This is not a Stop control (Amendment 1): it refuses nothing and decides nothing, and the turn continues on the next
Gateway from its checkpoint. It makes `lonora quiesce` (PHASES P1-T5, Amendment 3.9) and the weekend update window
(DECISIONS D11) cleaner.

- Files: `packages/gateway/src/lonora_gateway/service.py`, `packages/gateway/src/lonora_gateway/shutdown.py`,
  `packages/agent-runtime/src/lonora_agent/executor.py`, `packages/agent-runtime/src/lonora_agent/tool_loop.py`,
  `packages/tools/src/lonora_tools/context.py`, `infra/compose/docker-compose.prod.yml`,
  `infra/systemd/lonora-gateway.service`, `docs/gateway-reliability.md` ("Drain and lease renewal").
- VISION: 6.3 and 6.8 (fewer operations left uncertain; the rules themselves are unchanged), 14.1.2 (the core tests must
  pass; `tests/check_execution_recovery.py` should gain a drain case), 17, Amendment 3.9, DECISIONS D11. There is no
  conflict.

### R3. Alarm on owner and broker-event runs left queued (P2, adopt, S)

**Gap.** The watchdog checks stalled steps, runs recovered too often, routines and timer waits more than 5 minutes
overdue, and aging trades (`watchdog.py:249` `overdue_wakes` and its siblings). It never checks a `queued` run that is
due and unclaimed. `run_dispatch.py` logs `queue_ms` at claim time, which is after the fact. With six workers busy on
long routine turns, an owner's message to a second agent, or a broker-event wake on an open position, can wait minutes
and nobody is told.

**What rakazo does.** `checkQueueAge` (`run-wakeup.ts:333-363`) logs `run.queue_delayed` when an interactive run has been
due and unstarted for 30 s, `run.queue_recovered` when it clears, and includes pool, worker and event-loop numbers.

**Adopt.** Add one watchdog check. A run with trigger `user`/`group`/`broker_event` (or a system-alert wake) that is due
and unclaimed past a threshold (for example 60 s) opens one `gateway_degraded` episode with `reason_code: runs_delayed`,
using the same episode and withdrawal mechanism as `overdue_wakes`. It also logs `run.queue_delayed` with counts and the
oldest wait. Add Arabic and English text for the new reason code.

- Files: `packages/gateway/src/lonora_gateway/watchdog.py`, `packages/gateway/src/lonora_gateway/run_dispatch.py`
  (time to first output, if wanted), the attention texts, `docs/gateway-reliability.md`,
  `tests/test_gateway_reliability.py`.
- VISION: P6, 11.7, 17. No conflict.

### R4. Claim by wake priority and run age, not by thread age; size the worker pool on its own (P2, adapt, M)

**Gap.** `claim_next` picks the eligible thread with `order_by(ThreadRow.created_at)` (`runs.py:307`). The oldest thread
wins, whatever is waiting in it and however long it has waited. Lonora's own conversation and the oldest routine work
threads always come first, and a newer thread can starve under sustained load. Within the shared pool nothing ranks a
broker-event wake on an agent's own position (VISION 4.7.1, 5.5.2) ahead of a routine. The pool size is
`maximum_subagents + 1` (`service.py:484`), so changing subagent fan-out silently changes run concurrency. Each idle
claim attempt also runs the `expire_submits` update (`runs.py:246`), 12 times a second across the pool.

**What the references do.** rakazo scans the interactive lane before the background lane and orders by `(createdAt, id)`
of the run. OpenMausBot's pure `admit()` names surfaces (`direct`, `unattended`, `peer`) with different busy behaviour.

**Adapt.** Order eligible threads by the best waiting run: a small fixed rank first, then that run's `created_at`. The
rank is the owner's message and system-alert wakes, then broker events, then approval-resume and owner-card wakes, then
peers and subagents, then routines, watches and workspace wakes. Keep the reserved conversation worker. Add a
`worker_count` setting independent of `maximum_subagents`. Move `expire_submits` to a maintenance step. Rule Q (card
submissions wait behind earlier runs, `runs.py:260-276`) is unchanged.

The ranking is scheduling order, not a limit: nothing is refused or capped (P1).

- Files: `packages/db/src/lonora_db/runs.py`, `packages/contracts/src/lonora_contracts/runs.py`,
  `packages/gateway/src/lonora_gateway/service.py`, `apps/api/src/lonora_api/env.py`,
  `apps/worker/src/lonora_worker/runtime.py`, `tests/test_run_integrity.py`.
- VISION: P1 (no limit is added), 4.7.1, 5.4, 11.8. No conflict.

### R5. Tell a late routine that it is late, and count what was collapsed (P2, adapt, S)

**Gap.** `enqueue_routine` (`routines.py:141-172`) collapses missed schedules into one wake, which is right, but the run
carries neither the time it was due nor how many occurrences were collapsed. Its context has the picture's `as_of`
stamps but no line about the schedule (`packages/agent-runtime/src/lonora_agent/context/routine.py`). A "London open"
routine that fires 90 minutes late after downtime reads as if it fired on time.

**What the references do.** rakazo's `routine-lateness.ts` tells a run that starts 15 or more minutes late both times,
and `routine-coalescing.ts` reuses one pending catch-up run. OpenMausBot's occurrence ledger records counted `missed`
rows with a cause.

**Adapt.** `enqueue_routine` stores `scheduled_for` and `collapsed` (the count of skipped occurrences) in the run's
server-only metadata, which `create_run` already strips from callers. The routine wake context adds one fixed
server-authored line when the run is more than 15 minutes late: "due at X, started at Y, N earlier occurrences were not
run". It is server text, so it stays inside the 6.10 provenance rules. A full occurrence ledger is not needed.

- Files: `packages/db/src/lonora_db/routines.py`, `packages/db/src/lonora_db/runs.py` (the server-only key list),
  `packages/agent-runtime/src/lonora_agent/context/routine.py`, `docs/proactive-wakes.md`.
- VISION: 5.4 (full picture on every wake), 6.10 (fixed server text), 11.5, 11.8. No conflict.

### R6. One transition gate for every run status write, plus invariant tests (P2, adopt, M)

**Gap.** `ALLOWED` exists (`run_state.py:11-28`), but `assert_transition` is called in one place (`complete_run`,
`runs.py:435`). About 17 other run status writes in 8 modules set `row.status` directly: `executor.py` (116, 282, 301),
`runs.py` (339, 525, 617, 575), `tasks.py` (57, 521, 536, 541, 664, 669), `messages.py:831`, `trade_approvals.py:92`,
`cancellation.py` (37, 66), `genui_submit.py:577` and `collaboration/outcome_return.py:227`. The CHECK constraint
validates values, not transitions, and no test asserts the table. An illegal move such as `cancelled → queued` would
pass silently.

**What the references do.** OpenMausBot keeps the state machine pure and asserts invariants I1..I10 in its test suite,
for example "no non-terminal assignment without a live owner" and "no result is delivered twice". rakazo routes writes
through `canTransition`.

**Adopt.** Add `transition(row, target, *, at)` in `lonora_core.run_state` that asserts, stamps `updated_at` and returns
the previous status, and use it at every write above. Add a property-style test over the real functions with these
invariants:

- at most one leased or running run per thread;
- no `leased`/`running` run without a future lease or a live Gateway;
- every terminal run with a parent or peer has exactly one outcome receipt;
- no write succeeds under a stale fence;
- a released run keeps its fence;
- a run holding a `reserved`/`submitted`/`ambiguous` journal row is never failed by quarantine.

- Files: `packages/core/src/lonora_core/run_state.py`, and each file above.
- VISION: 6.9 (run integrity: the lease checks stay; this adds the transition check), 14.1.2-14.1.3 (no assertion about
  6.1-6.9 is removed; new assertions only), 17. No conflict.

### R7. Expire streaming projection events of finished runs (P2, adopt, M)

**Gap.** Every 1 KB chunk of a streamed reply (`DELTA_CHUNK_CHARS = 1024`, `progress.py:11`), every `run.rich_partial`
(which carries the whole compiled component tree), every `run.reply_started`/`run.context_started` and every
`tool.started`/`tool.completed` is an `ln_events` row. No code deletes any `ln_events` row. For a 24/7 trading assistant
with routines and watches this grows without bound: on the order of gigabytes a year on a busy installation. That
weighs on the Starter VM disk (DECISIONS D13), on nightly `scripts/backup.sh` dumps and their retention, and on restore
tests. Clients rebuild live activity from the live stream and from `model_metadata.activity`
(`packages/core/src/turn-activity.ts`). Once a run is terminal, the committed `message.created` and `run.*` status
events carry what the owner sees.

**What the references do.** rakazo deletes transient run events (`transientRunEventsWhere`,
`packages/db/src/threads/events.ts:110`) when a run finalizes and when an account or group is removed. OpenMausBot caps
per-thread logs (`capThreadLog`) and prunes finished runtime trees after 30 days.

**Adopt, kind-scoped.** Add a non-critical `event_retention` step that deletes, in batches, only `run.delta`,
`run.rich_partial`, `run.reply_started` and `run.context_started` events of runs that have been terminal for more than a
window (for example 7 days, so a reconnecting client always replays recent runs). The step never touches kinds that
code reads back: `tool.completed` (read for a day by `context/environment.py`), decisions, opportunity transitions,
`agent.created`, `memory.updated`, `broker.external_activity`, attention and notify events. Whether old
`tool.started`/`tool.completed` rows should also expire can wait for a check of what "Technical details" shows for old
runs. The trading journal, receipts and settlement records are separate tables and stay untouched (VISION 3.1.2, 5.5).

- Files: `packages/db/src/lonora_db/events.py`, `packages/gateway/src/lonora_gateway/service.py` (the new step),
  possibly an index in `schema.py` and a migration under `packages/db/migrations/versions/`, `docs/gateway-reliability.md`.
- VISION: 3.1.2 and 5.5 (journal and receipts are never deleted; events are not the journal), Amendment 3.4 (disk is a
  plan resource), DECISIONS D10, D13. No conflict.

### R8. One Gateway per installation, enforced by a Postgres lock, with immediate recovery at boot (P2, adapt, M)

**Gap.** Lonora depends on exactly one Gateway per installation ("one subscription and one synchronization owner per
account", `docs/operations.md`), but only the `lonora` script enforces it, by stopping the old Gateway before starting a
new one (`infra/compose/lonora`, `quiesce`). Nothing in code stops a second Gateway: a manual
`docker compose up --scale`, a systemd unit next to compose, or a stuck container during a failed update. Run claims and
sends stay correct with two Gateways: claims use `SKIP LOCKED` plus fences, sends hold a per-account advisory lock
(`execution.py:487-494`), and reconciliation uses a try-lock (`reconciliation.py:72`). But MetaApi streams, the market
step, the relay, the voice tasks and the in-memory watchdog episodes would be duplicated.

A second effect: after a crash, the new Gateway waits up to the full 120 s lease before it re-claims the dead process's
runs, because it cannot tell that the old process is gone.

**What the references do.** OpenMausBot uses a data-dir lease file (pid, boot id, machine id) that "may only prove a
lease dead, never alive". rakazo elects its reconciler leader with a session advisory lock (`pg_try_advisory_lock`).

**Adapt.** At start, the Gateway takes a session-level `pg_try_advisory_lock` on a dedicated connection and holds it for
its lifetime. If the lock is held, it logs and exits, or waits, with a stable code. Once it acquires the lock, it knows
every earlier Gateway's database session has ended, so it immediately requeues runs leased by any other `lease_owner`,
using the `release_leases` semantics with the fence kept, instead of waiting for lease expiry. A Gateway that lost its
database connection but is still alive cannot write afterwards, because every write is fenced (A1), and the door's
journal and locks are unchanged.

- Files: `packages/gateway/src/lonora_gateway/service.py`, `packages/db/src/lonora_db/runs.py`,
  `packages/db/src/lonora_db/client.py`, `packages/gateway/src/lonora_gateway/heartbeat.py`, `docs/operations.md`,
  `docs/gateway-reliability.md`.
- VISION: 6.6 (per-account send serialization stays as is), 17 (recovery after restarts), Amendment 3.1 (one dedicated
  installation per customer). No conflict.

### R9. Retry the final commit of a run on a transient database error (P3, adopt, S)

**Gap.** `keep_lease` tolerates database blips, but the final transactions in `execute_run` (`complete_run`, the
`waiting_input` write and the retry release) are attempted once. A transient `SQLAlchemyError` there lands in
`except Exception` → `record_failure(..., "runtime_error")` (`executor.py:350-352`). If the database is back by then,
a run whose answer was ready is recorded as failed. If not, the run is recovered later and its last model call is
repeated.

**What rakazo does.** `finalizeRun` is wrapped in `retryWhileDatabaseUnavailable`, and the lease fence makes the retry
safe.

**Adopt.** Wrap those final writes in the same bounded retry `keep_lease` uses, for transient errors only and while the
lease is still valid. The fence makes a duplicate impossible.

- Files: `packages/agent-runtime/src/lonora_agent/executor.py`.
- VISION: 6.9, 17. No conflict.

### R10. Use `LISTEN/NOTIFY` as a wake-up latch for run claims and event streams (P3, adapt, M)

**Gap.** Six workers poll `claim_next` every 0.5 s, and each connected client polls `events_after` every 0.1 to 0.5 s.
Each of those polls runs `publish_committed`, which takes the global advisory lock and a row lock on the counter and
commits (`events.py:31`). That adds up to 0.5 s to a first reply and puts constant lock traffic on Postgres while idle.
It is fine for one owner today. It is the first thing to improve if the per-customer VM is sized down
(DECISIONS D1, D13).

**What the references do.** rakazo publishes ids on `pg_notify` after commit. The row stays the truth, NOTIFY is only a
latch, and a missed notification costs latency, never correctness. OpenMausBot's tick is paced (busy, parked, idle) and
has `kick()`.

**Adapt.** After `create_run` and after any commit that emits events, send `NOTIFY` with ids only (no payload content,
well under the 8 KB cap). The Gateway and the stream generators wait on the notification or their current interval,
whichever comes first, and keep polling as the fallback. A natural follow-up is to publish cursors once per commit
instead of on every poll.

- Files: `packages/db/src/lonora_db/events.py`, `packages/db/src/lonora_db/runs.py`, `packages/db/src/lonora_db/client.py`,
  `packages/bus/src/lonora_bus/durable_events.py`, `packages/gateway/src/lonora_gateway/service.py`.
- VISION: P6 (responsiveness). No conflict.

### R11. Framework counters for the Lonora Cloud host agent, with no trading data (P3, adapt, M, needs the owner's decision)

**Gap.** Lonora exposes `/health`, `/ready` and `lonora status`. There is no machine-readable view of queue age, runs by
status, lease expiries, fenced writes rejected, quarantines or step liveness. DECISIONS D26 plans a metrics stack for the
fleet, and the host agent heartbeat (`docs/cloud/PLAN.md`) already carries `/ready`. rakazo has no metrics endpoint
either, and its own report lists that as a gap. OpenMausBot keeps local JSONL traces only.

**Adapt.** Extend `lonora status --json` (or a loopback-only endpoint) with framework counters only. Keep it off by
default for self-hosted installations (Amendment 3.6).

**Decision needed.** Amendment 3.3 forbids the operator to read "trading data", and 3.6 says hosting hooks "read the
trading journal at most". A count of unresolved operations, or of Settle cards waiting, is derived from the journal.
Whether such counts may leave the installation for the operator is the owner's call. Without that decision, ship only
the non-trading counters.

- Files: `infra/compose/lonora`, `apps/api/src/lonora_api/health.py`, `packages/gateway/src/lonora_gateway/health.py`.
- VISION: Amendment 3.3, 3.4, 3.6, 3.7; DECISIONS D26.

---

## 4. Where Lonora is already ahead or at parity

### A1. The run row is the queue: claim, lease, fence, fenced writes

`claim_next` with `FOR UPDATE SKIP LOCKED` on the thread and then the run (`runs.py:239-355`), `lease_fence` incremented
per claim, `require_lease` on every write and in the door (`runs.py:358`; VISION 6.9), thread-before-run lock order
(`locked_run_thread`), one active run per thread, and drain releases that keep the fence (`runs.py:551`). This is
rakazo's design ported (and attributed) to Python, and stronger than OpenMausBot's single-writer lease, which Lonora does
not need. Keep it.

### A2. Restart rules for outward effects, per tool call

Effects are judged per call, not per turn. A call is replayed after a crash only if it is read-only or declared
`replay_safe`. Legacy checkpoints never gain replay permission (`legacy_pending`). Anything else returns
`tool_execution_uncertain` (`tool_dispatch.py:83-96`). Financial calls reconcile the same operation id even if the model
invents a new call id (`tool_dispatch.py:56-70`). The door turns cancellation into `ambiguous`, never into a re-send
(`execution.py:440-455, 558-590`; VISION 6.2-6.4). The owner sees one honest line (`uncertain_outcome.py`).

This is finer than OpenMausBot's rule ("rerun the turn once unless an outward action happened"). It also already does
what the rakazo report warns rakazo itself does not do ("an effect must be recorded as intended before the broker call
and reconciled afterwards"). Do not copy rakazo's approved-effect replay.

### A3. Supervised steps, per-item isolation, deterministic watchdog, quarantine that holds runs with unresolved trades

Each step has its own interval, timeout, backoff and liveness record (`liveness.py`). Each item has its own transaction,
a 45 s limit and a quarantine after five failures with one coalesced attention item (`item_failures.py`). Items tied to
an unresolved trade are never quarantined. The watchdog only alerts or quarantines (`watchdog.py`), and a run over the
recovery cap is held while it has an unresolved journal row (`quarantine_run`). OpenMausBot has a timer per feature and
its own report tells Lonora to avoid that. rakazo's reconciler has no item-level quarantine. R1 completes this layer from
the outside.

### A4. Agent-to-agent delivery as one transaction plus a normal run

`delegate_peer` writes the echo in both conversations, creates the target run and the peer record in one transaction.
It locks both threads in a global order to avoid deadlock, fences the parent run, is idempotent on `resource_id`
(conflicting retries refused with `peer_intent_conflict`), walks the ancestry to refuse cycles and depth over 32, and
marks the target's wake as data, never instructions (`PEER_WAKE`, `context/routine.py:37`; VISION 3.2.3, 6.10).
Outcomes are returned once per fence by receipt (`outcome_return.py:27`), and the `outcomes` step repairs lost returns.
rakazo's `messageBot` has the same shape but only a hop counter of 100. The broader multi-agent comparison belongs to its
own report.

### A5. Update, rollback, held rollback and maintenance mode

`infra/compose/lonora` stops the API and the Gateway, backs up, migrates as its own step, starts the API before the
Gateway, waits for `/ready`, and rolls back automatically. It refuses ("ROLLBACK HELD") to restore a backup over trading
or control records written by the new version (`docs/operations.md`). Neither reference has an equivalent that protects
broker-side truth.

### A6. Send serialization per account rather than a run-level lease on the MT5 account

The rakazo report suggests copying `ComputerExecutionLease` as "one run holds the MT5 account". Lonora serializes at the
send (per-account advisory lock, `execution.py:487-494`; VISION 6.6) and orders mode changes under `authority_lock`.
Holding the account for a whole run would make a risk-reducing close wait behind another agent's long analysis turn.
Keep the narrower lock.

---

## 5. Skip

### S1. Spend caps and budget stop modes (OpenMausBot `usage-caps.ts`, `OMB_USAGE_CAP_STOPS`)

P1 forbids caps, quotas and activity budgets. DECISIONS D6 and D41 record BYOK and cite the earlier owner decisions that
forbid spend caps and budgets. Usage stays observable (`packages/llm-usage`, `lonora_db/usage.py`) and is never
enforced. Already decided; no new decision needed.

### S2. A "reads and drafts only" fence on unattended runs (OpenMausBot `read-and-draft.ts`)

This conflicts with P1 and 4.5: Full mode keeps working while the owner is away. Ask mode already turns risk-increasing
requests into Trade Approval cards (4.1). Skip.

### S3. Expiry for approval waits (rakazo `STUCK_WORK_EXPIRE_AFTER_MS`, and the rakazo report's per-action approval lifetimes)

VISION 10.3.1.3: a Trade Approval card has no time limit. It ends only by approve, reject, drift, or withdrawal by the
agent or by a mode change. Drift on the quote (`approval_drift` step) replaces the time limit. Skip. R3 alarms on runs
that never started; it does not expire waits.

### S4. Multi-tenant row-level security, a separate job queue, memory-based admission, starting runs inside the API (rakazo)

Amendment 3.1 and DECISIONS D1: one dedicated installation per customer, and a shared installation stays out of scope.
Lonora's tables already carry `owner_id`. The supervised steps plus `ItemGuard` cover everything rakazo puts in Graphile.
Lonora's agents do not spawn engine processes, so memory admission buys little. rakazo's own report lists starting runs
inside the API process as something to avoid; Lonora's split is the better one. OpenMausBot's whole-file JSON registries
and single-process design are likewise not for Lonora.

---

## 6. Notes for the other gap reports

- **Proactivity (the framework side).** Lonora already has the shape both references converged on: durable trigger
  records, checks in code before the model (watches), bounded runs, and silence when nothing is new. The framework gaps
  are R4 (whose wake runs first) and R5 (lateness and collapsed occurrences). The rest belongs to the proactivity
  report.
- **How bots talk to each other.** The transport is sound (A4). Open questions about addressing, groups and Lonora's
  lead powers belong to the multi-agent report.
- **Model and sign-in topics** are out of scope here. Nothing in this report touches VISION 12 or P8.
