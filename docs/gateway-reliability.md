Superseded by VISION.md

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
| `task_retries`, `outcomes` | 10 s | 120 s | yes |
| `reconcile`, `verifications`, `account_recovery` | 10 s | 300 s | yes |
| `market`, `watches`, `channels`, `attention` | 2 s | 120 s | yes |
| `watchdog` | 30 s | 120 s | yes |
| `activation_reviews`, `opportunities` | 10 s | 120 s | no |
| `charts` | 2 s | 120 s | no |
| `history` | 10 s | 600 s | no |
| `closed_trades` (the closed-trade ledger from broker deal history) | 30 s | 300 s | no |
| `close_wakes` (a closed trade wakes its owner for a self-review) | 10 s | 120 s | no |
| `instrument_currencies` (instrument currencies of held symbols, for the account picture) | 30 s | 120 s | no |
| `calendar` (the owner's economic calendar sources, cached for the account picture) | 600 s | 120 s | no |
| `voice` | 0.5 s | 60 s | no |
| `incoming` (incoming calls) | 2 s | 60 s | no |
| `thread_prefs` (keep-archived off: a new message unarchives) | 2 s | 60 s | no |

Each run worker has a liveness record too. A worker running a Run is busy, never
stalled; the Run's lease covers it. Only a poll that returns counts as liveness: a
worker whose every claim fails records the failure and goes stale, so readiness and the
watchdog report it while the supervisor restarts it. A step is stalled when its current
iteration has run longer than `max(120 s, 12 × interval, timeout + interval)`, or when
it has not succeeded for that long. The threshold is never shorter than one legitimate
iteration, so a slow broker inside reconciliation's own timeout is a broker problem
(`broker_degraded`), not a stalled service.
Steps that serve several owners run each owner separately, so one owner's failure never
skips another.

## Per-item isolation

Inside a step, every item is isolated by `ItemGuard` (`lonora_db/item_failures.py`):
routines, automatic task retries, activation reviews, task waits, outcome returns,
attention events and items, watches, channel integrations and opportunities. Each item runs in its own transaction and has its
own time limit (45 s; 100 s for a channel integration's batch of deliveries), well
below the step's timeout. An item that raises, or hangs past its limit (code
`timeout`), is recorded in `ln_item_failures` (kind, item, failure count, code, next
attempt) and backs off (10 s doubling to 10 min). A hanging item is therefore isolated
like a raising one instead of being cut off silently by the step timeout and selected
first again on every pass. A SQL predicate keeps backing-off and
quarantined items out of the batch, so they never take the slot of a healthy item.
Success clears the record.

After five consecutive failures an item is quarantined, and the owner gets an
attention item, `maintenance_item_quarantined` ("A background item was paused after
repeated errors; everything else keeps running"). There is one open item per kind: a
further quarantine of the same kind adds to its `count` instead of a new item, so a
systematic fault cannot flood the inbox.

- a routine is disabled, a watch is disabled (`state.code: watch_quarantined`), an
  activation review is recorded as skipped, an attention event is recorded as decided
  (`attention_projection_failed`) and an attention item is suppressed; re-enabling a
  routine or watch starts fresh;
- a critical or action-required notification is never lost to a projection bug: a
  quarantined event still raises its own code (for example `emergency_stop`) straight
  to ready, without the details its failed projection would have added, and a
  quarantined pending item of that importance is delivered as it is;
- an automatic task retry is turned into a Task failure that waits for the owner, which
  already reaches the owner as `task_review`;
- a task wait or outcome return stays in the ledger quarantine.

Opportunities can track a financial operation, so they are never quarantined: they only back off. Channel integrations only back off
too, so a provider outage never silences notifications. Reconciliation already isolates
each operation, and every broker observation on the reconciliation and watch poll paths
has its own timeout (30 s and 20 s). A watch whose observation times out records
`watch_observation_timeout` as watch health and backs off like any unavailable source.

`check_watches` filters in SQL (enabled, not expired, not quarantined, with an agent and
thread) and, when polling, takes only due watches: never-checked first, then the most
overdue. Old or retired watches can no longer starve new ones.

The attention cursor advances per event, over the prefix of events already handled
(critical events are handled first): an event that raises or hangs is retried from the
failure ledger instead of holding the cursor, and an iteration cancelled by the step
timeout keeps every event it already decided. Later events (critical broker alerts
included) are projected on time. Incoming calls are their own
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
  item ("A trade still has no confirmed broker result"). It is never resent. An
  ambiguous operation whose resolve card still waits for the owner's answer, or whose
  `operation_uncertain` item is still open, raises none: the owner is asked once
  (`docs/owner-actions.md`).

These items are written straight to `ready` (`raise_system_attention`), so they do not
depend on the attention loop being healthy. Each names and opens the agent and
conversation it is about: `run_quarantined` the agent and conversation where the Run
stopped, `operation_unresolved` those of the Run that placed the trade. Only an item
about no agent (a stalled step) or whose agent is gone uses the Personal Agent.

Stall episodes live in memory, so every `gateway_degraded` item records its episode and
gateway. Each watchdog pass withdraws an unread item whose episode is no longer current
on its own gateway, or whose gateway has stopped or lost its heartbeat. After a restart
(often what cleared the stall) the owner is therefore not told the service is late
while every step is live. `run_quarantined` and
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

Deleting an agent, a conversation, a Run or a broker connection never deletes a
financial, authority or evidence record (migration `0036_durable_records`):

- contextual links become `ON DELETE SET NULL`: the conversation of a grant, approval
  or Super Bot request, and the Run of an approval;
- identity links keep their id as a plain value, with no cascade: the agent and account
  of a grant, approval or restriction, and the goal id a retired Super Bot request names.
  A NULL agent on a restriction would mean "every agent", so a
  deleted agent's restriction never turns account-wide.

The trading journal and trading decisions already had no such links. A downgrade is
refused while any record has outlived its parent.

`DELETE /agents/{id}`, `DELETE /threads/{id}` and `DELETE /trading/connections/{id}`
are refused with 409 `delete_blocked_unresolved_operation` while an operation they
touch is still `reserved`, `submitted` or `ambiguous`. The owner sees "This can't be deleted yet: a trade linked to it still has no
confirmed broker result. Settle that operation first; nothing was deleted." Otherwise
the delete first settles what depended on the deleted parent, which never needs the
passkey, so nothing is left looking active while it can no longer run:

- open approvals (pending, or approved but not yet sent) are cancelled, so a cancelled
  approval can no longer authorize a send;
- grants of the agent, of the account, or signed in the deleted conversation are
  revoked through the normal revocation (their full-management Task stops), so the
  permission frame shows "autonomous stopped" and the trade path asks for approval
  again, instead of a grant that still reads active but always fails;
- retired Super Bot requests (W15-9) are audit history only and are left as they are;
- pending owner action cards the agent raised, the conversation shows or that act on
  the account are superseded (`agent_deleted`, `conversation_deleted`,
  `account_deleted`).

## Verification

- `tests/test_gateway_reliability.py`: a poison routine, watch and attention event back
  off and are quarantined while the others run; a hanging attention event times out
  into the ledger and never holds the cursor; a failing step never stops
  reconciliation and liveness is persisted; a hung iteration times out; a worker whose
  claims fail goes stale; the stall threshold; readiness; recovery-count quarantine and
  the financial hold; the watchdog's one-item rules, item origin and withdrawal of
  ended episodes after a restart; coalesced quarantine notices and the kept critical
  alert; drain release and lease renewal; durable records, delete refusal and the
  settlement of a deleted conversation's grant, with its retired Super Bot
  request kept as history.
- `tests/check_account_authority.py`: deleting a grant's conversation revokes it; the
  grant list, the permission frame and the trade path agree.
- `tests/check_durable_records.py` (fresh PostgreSQL): the migration's constraints,
  lossy-downgrade refusal and round trip, the three delete routes and `/ready`.
