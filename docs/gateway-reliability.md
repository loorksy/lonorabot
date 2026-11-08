# Gateway reliability

How the always-on gateway keeps working when one of its parts fails, how it notices
that it is not keeping up, and how financial records survive ordinary deletes. None of
this makes a trading decision or repeats an external effect: an uncertain operation
stays uncertain until the broker or the owner settles it
(`docs/financial-execution-recovery.md`).

## Supervised steps

The gateway (`lonora_gateway/service.py`) runs its run workers and every maintenance
step as separate supervised tasks. A step (`lonora_gateway/liveness.py`) has its own
interval, an iteration timeout and a liveness record. An iteration that raises is
logged with a stable code (never the exception message), backs off (up to 60 s) and
runs again. An iteration that hangs past its timeout is cancelled and counted as a
failure, `step_timeout`. A failing or hanging step never delays another one, so a
broken routine can no longer stop broker reconciliation.

| Step | Interval | Timeout | Critical |
| --- | --- | --- | --- |
| `heartbeat` | 10 s | 30 s | yes |
| `owners` | 10 s | 60 s | yes |
| `routines`, `task_waits` | 5 s | 120 s | yes |
| `task_retries`, `outcomes`, `goals` | 10 s | 120 s | yes |
| `reconcile`, `verifications`, `account_recovery` | 10 s | 300 s | yes |
| `market`, `watches`, `channels`, `attention` | 2 s | 120 s | yes |
| `watchdog` | 30 s | 120 s | yes |
| `activation_reviews`, `opportunities` | 10 s | 120 s | no |
| `shadow`, `charts` | 2 s | 120 s | no |
| `history` | 10 s | 600 s | no |
| `voice` | 0.5 s | 60 s | no |
| `incoming` (incoming calls) | 2 s | 60 s | no |

Each run worker has a liveness record too. A worker running a Run is busy, never
stalled; the Run's lease covers it. A step is stalled when its current iteration has
run longer than `max(120 s, 12 × interval)`, or when it has not succeeded for that long.
Steps that serve several owners run each owner separately, so one owner's failure never
skips another.

## Per-item isolation

Inside a step, every item is isolated by `ItemGuard` (`lonora_db/item_failures.py`):
routines, automatic task retries, activation reviews, task waits, outcome returns,
attention events and items, watches, channel integrations, goal decisions and goal
target reviews, and opportunities. Each item runs in its own transaction. An item that
raises is recorded in `ln_item_failures` (kind, item, failure count, code, next attempt)
and backs off (10 s doubling to 10 min). A SQL predicate keeps backing-off and
quarantined items out of the batch, so they never take the slot of a healthy item.
Success clears the record.

After five consecutive failures an item is quarantined, and the owner gets one
attention item, `maintenance_item_quarantined` ("A background item was paused after
repeated errors; everything else keeps running"):

- a routine is disabled, a watch is disabled (`state.code: watch_quarantined`), an
  activation review is recorded as skipped, an attention event is recorded as decided
  (`attention_projection_failed`) and an attention item is suppressed; re-enabling a
  routine or watch starts fresh;
- an automatic task retry is turned into a Task failure that waits for the owner, which
  already reaches the owner as `task_review`;
- a task wait or outcome return stays in the ledger quarantine.

Goal decisions, goal target reviews and opportunities can track a financial operation,
so they are never quarantined: they only back off. Channel integrations only back off
too, so a provider outage never silences notifications. Reconciliation already isolates
each operation, and every broker observation on the reconciliation and watch poll paths
has its own timeout (30 s and 20 s). A watch whose observation times out records
`watch_observation_timeout` as watch health and backs off like any unavailable source.

`check_watches` filters in SQL (enabled, not expired, not quarantined, with an agent and
thread) and, when polling, takes only due watches: never-checked first, then the most
overdue. Old or retired watches can no longer starve new ones.

The attention cursor advances past every event in the batch: an event that raises is
retried from the failure ledger instead of holding the cursor, so later events
(critical broker alerts included) are projected on time. Incoming calls are their own
step and are no longer behind attention.

## Watchdog

`lonora_gateway/watchdog.py` runs every 30 s without a model. Each check is isolated
from the others.

- **Stalled steps.** A critical step that hangs or keeps failing raises one
  `gateway_degraded` item per stall episode (`reason_code: step_stalled`).
- **Runs recovered too often.** Each crash recovery increments `ln_runs.recovery_count`;
  a claim from the queue resets it. After five consecutive recoveries `claim_next` no
  longer re-leases the Run. The watchdog fails it with `run_recovery_limit`, returns
  the outcome to its parent and raises `run_quarantined` (a Task instead records the
  failure, which reaches the owner as `task_review`). A Run with a `reserved`,
  `submitted` or `ambiguous` live journal operation is held, never failed: the
  reconciler settles that operation first, and only then is the Run quarantined.
- **Overdue wakes.** Routines and timer waits more than five minutes past due raise one
  `gateway_degraded` item per episode (`reason_code: wakes_overdue`), unless a stalled
  scheduler step already reported it.
- **Aging operations.** A live operation still `reserved`, `submitted` or `ambiguous`
  fifteen minutes after it was submitted raises exactly one `operation_unresolved`
  item ("A trade still has no confirmed broker result"). It is never resent.

These items are written straight to `ready` (`raise_system_attention`), so they do not
depend on the attention loop being healthy. `run_quarantined` and
`operation_unresolved` need action and are mirrored to Telegram while still current.
Every new code has Arabic and English text on web, mobile and in channel messages.

## Readiness

The heartbeat is its own step: it writes the liveness of every step and worker to
`ln_gateways.liveness`. `GET /ready` returns 200 only while a gateway heartbeat is
younger than 45 s and none of its critical steps is stalled; otherwise 503, with the
stalled step names. Gateway rows whose last heartbeat is more than seven days old are
pruned.

## Drain and lease renewal

On SIGTERM the gateway stops claiming, lets running work finish for up to 25 s and then
cancels it. It then returns every lease it still holds to the queue (`release_leases`):
status `queued`, fence kept. A late write from the old lease is still rejected, the
checkpoint and its in-flight markers are untouched, and the next gateway resumes the
work at once instead of after `run_lease_seconds`. A release is a clean hand-over and
does not count as a crash recovery.

A Run renews its lease every third of the lease length (`keep_lease`). A transient
database error (dropped connection, failover, timeout, or a renewal that hangs) is
retried until shortly before the lease would expire; only a fenced `stale_lease`, an unknown error or running out of
lease time stops the Run.

## Durable records

Deleting an agent, a conversation, a Run, a goal or a broker connection never deletes a
financial, authority or evidence record (migration `0036_durable_records`):

- contextual links become `ON DELETE SET NULL`: the conversation of a grant, approval,
  goal or Super Bot request, and the Run of an approval;
- identity links keep their id as a plain value, with no cascade: the agent and account
  of a grant, approval or restriction, the goal of a decision or Super Bot request, and
  the agent of a goal. A NULL agent on a restriction would mean "every agent", so a
  deleted agent's restriction never turns account-wide.

The trading journal and trading decisions already had no such links. A downgrade is
refused while any record has outlived its parent.

`DELETE /agents/{id}`, `DELETE /threads/{id}` and `DELETE /trading/connections/{id}`
are refused with 409 `delete_blocked_unresolved_operation` while an operation they
touch is still `reserved`, `submitted` or `ambiguous`. The owner sees "This can't be deleted yet: a trade linked to it still has no
confirmed broker result. Settle that operation first; nothing was deleted." Otherwise
the delete first narrows what depended on the deleted parent, which never needs the
passkey: open approvals (pending, or approved but not yet sent) are cancelled, so a
cancelled approval can no longer authorize a send; the agent's or account's grants are
revoked and the agent's Super Bot requests are cancelled.

## Verification

- `tests/test_gateway_reliability.py`: a poison routine, watch and attention event back
  off and are quarantined while the others run; a failing step never stops
  reconciliation and liveness is persisted; a hung iteration times out; readiness;
  recovery-count quarantine and the financial hold; the watchdog's one-item rules;
  drain release and lease renewal; durable records and delete refusal.
- `tests/check_durable_records.py` (fresh PostgreSQL): the migration's constraints,
  lossy-downgrade refusal and round trip, the three delete routes and `/ready`.
