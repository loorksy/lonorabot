Superseded by VISION.md

# Financial execution integrity and recovery

Every live broker mutation passes through `ExecutionService.execute`
(`packages/trading/src/lonora_trading/execution.py`). The adapter's `before_send`
callback is the only place a mutation is authorized; it runs under the per-account
advisory lock shared with broker recovery. This document describes what the journal
records, what blocks what, and how uncertainty is settled without ever resending.

## Operation lifecycle

`lonora_contracts.trading.OperationStatus` (mirrored by `OperationStatus` in
`packages/contracts/src/trading.ts`):

| Status | Meaning |
| --- | --- |
| `reserved` | Identity journaled; the send boundary was provably not crossed. |
| `submitted` | `before_send` authorized the mutation (`details.execution.send_authorized`); it may be at the broker. |
| `confirmed` | The broker acknowledged it, or broker evidence later established it. |
| `failed` | Known outcome: broker rejection, a pre-send block, never sent (`details.send_state == "not_sent"`), or the requested target state is observed not to hold. |
| `ambiguous` | Possibly sent, outcome unknown. Never resent automatically. |
| `resolved` | Uncertainty settled without establishing the operation's own outcome: an owner attestation, or broker state showing the target no longer exists or was changed by something else. Never broker confirmation. |

The executor reserves the row as `reserved`, and `before_send` moves it to
`submitted` under the journal row lock in the same transaction that records send
authorization. Any failure before `before_send` returns is persisted as
`failed` with `send_state: "not_sent"`; any failure after it stays `ambiguous`.
`persist_result` never regresses `confirmed`, `failed` or `resolved`, and keeps the
server-captured execution record, quality and evidence.

The executor holds the per-account send lock from before `before_send` until the
final outcome (confirmed, failed or ambiguous, including cancellation) is persisted.
Two facts follow and are relied on: under the lock, any *other* `submitted` row of
the account has lost its sender; and a sibling operation waiting for the lock sees
the previous operation's real outcome, never a stale `submitted` row.

`journal_data` (GET `/trading/journal`) adds the derived `send_state`
(`not_sent | sent | unknown`), `verification_status`,
`awaiting_broker_confirmation` and `resolution`. Each owner-visible transition emits
`trading.operation_updated` in the same transaction.

## Scoped admission and reduce-only actions

`lonora_trading/admission.py` defines a request as risk-reducing only against the
fresh broker target read at the boundary:

- `close_position` of an existing position on the same symbol, fully or for at most
  its current volume (closing a hedge leg reduces gross exposure and is admitted as an
  exit, even though it changes the net direction on the symbol);
- `cancel_order` of an existing pending order on the same symbol whose fill would not
  shrink the symbol's absolute net position volume. Cancelling a *protective* order —
  an opposite-side order that would offset open positions, such as a sell stop below a
  net long book — removes protection and is risk-increasing, like removing a stop;
- `modify_position` that moves the stop-loss strictly toward the market (higher for a
  buy, lower for a sell) or adds one to an unprotected position, with the take-profit
  unchanged and nothing cleared.

Everything else — entries, pending-order edits, take-profit changes, removing or
widening protection — is risk-increasing.

- A risk-reducing request stays admissible on every path; this relaxes no
  authorization (owner session, exact approval or matching signed grant still apply,
  and the lease, preflight and broker checks still run).
- An unresolved operation (`submitted` or `ambiguous`) blocks new risk-increasing
  requests on the same account and symbol, or the same position/order ticket, for
  every admission path including the owner API. It never blocks a risk-reducing
  request. A `reserved` row never blocks. The final check runs inside `before_send`,
  under the send lock, against both statuses. The earlier reservation-phase check
  runs before the lock is taken, where a `submitted` sibling may still be in flight
  and about to settle, so it rejects only on `ambiguous` operations; a request
  admitted there waits for the lock and is re-checked.
- A `degraded` broker observation blocks only markets with unresolved operations
  (also for decision readiness) with `broker_reconciliation_required`; a
  `disconnected` one (or any other non-admissible observation) blocks new risk on the
  whole account with `broker_observation_unavailable` — the account state could not
  be verified, which is a different cause than a previous operation — but still
  admits exits.

## Owner restrictions and monetary limits at the send boundary

After the execution-quality gate and global controls, `before_send` evaluates the
owner's monetary limits (`ExecutionPolicy.risk`, `lonora_trading/risk_limits.py`) from
fresh broker economics for any request that is not risk-reducing. Open risk counts
`submitted` and `ambiguous` entries and confirmed entries awaiting verification whose
ticket is not yet visible, so an unresolved operation can never free risk budget. The
final transaction then checks owner restrictions (`lonora_trading/restrictions.py`)
under a shared restriction lock before moving the row to `submitted`. Either block is
recorded on the reserved row (`details.risk_assessment`, `details.admission_block`)
and concluded as `failed` with `send_state: not_sent`; `persist_result` keeps both as
server evidence. Neither ever blocks a risk-reducing request, except an explicit
`all_mutations` restriction. See `account-authority.md` for the semantics.

## Observe-only recovery

`reconcile_ambiguous` (the gateway's own `reconcile` step, every 10 s, bounded and
rotating, with a 30 s timeout per broker observation; see `docs/gateway-reliability.md`)
and `reconcile_broker_account` share `observe_operation` and never send. No other
maintenance step can delay or stop it.
`reconcile_broker_account` observes while holding the account send lock, so every
`submitted` row it sees has lost its sender; rows it cannot settle mark the account
`degraded` for their market.

1. An abandoned `reserved` row (lease gone, or 5 minutes without a lease) is released
   to `failed` / `operation_not_sent` without any broker call. The release and the
   reserved→submitted transition share the row lock, so a late sender stops at
   `before_send`.
2. A `submitted` row is only observed once its sender is proven gone: its lease (if
   any) is no longer live and the account send lock can be taken
   (`pg_try_advisory_xact_lock`) while the row is still `submitted`. A busy lock
   proves nothing and the row waits for a later pass. An `ambiguous` row is observed
   directly. Observation starts with the adapter's correlated reconciliation
   (operation identity / MetaApi `clientId`).
3. If that is inconclusive, set-type management actions are compared with the broker
   target (`lonora_trading/target_state.py`). Repeating these cannot add exposure,
   so the target is evidence. Three facts are compared: the request, the target as
   `before_send` observed it (server-captured evidence) and the target now.
   - `confirmed` from target state means only that the *requested end state holds*
     (`details.conclusion: "requested_end_state_observed"`), not that this request
     produced it: modify whose requested fields all match (`target_state_matches`);
     cancel whose order is gone without fill evidence after the settle window
     (`order_no_longer_pending`).
   - `failed` (`target_state_not_reached`) only after the two-minute settle window
     and only when the requested fields (or, for a full close, the volume) still equal
     the before-send target (`conclusion: "before_send_state_unchanged"`), or when a
     cancelled order is still pending (a cancel cannot partly apply). A fully filled
     order before its cancel → `failed` (`order_filled_before_cancel`).
   - `resolved` when the target is gone (`target_closed` /
     `target_no_longer_pending`) or, after the settle window, differs from both the
     request and the before-send state (`target_changed`: a partial fill of a close,
     a later admitted change such as a trailing stop, or a manual edit). A full close
     whose position is gone is `resolved` (`target_closed`), not `confirmed`: a stop,
     take-profit, manual or other close leaves the same state, and a close receipt
     would imply this operation's exit.
   - Without before-send evidence no `failed` or `target_changed` conclusion is drawn.
     Creates and partial closes are never inferred from state; a partial fill of a
     cancelled order stays uncertain.
4. Still inconclusive, or the broker cannot be observed at all (unreachable, MetaApi
   `broker_history_limit`, a malformed receipt): a `submitted` row whose sender is
   gone becomes `ambiguous` (`execution_interrupted_after_send`), so the owner can
   settle it with an attestation. Unavailable evidence is never treated as either
   outcome.

`recheck_verifications` re-reads `confirmed` rows whose resulting state is still
`pending` every 30 s until `verified`, or `unverified` after 15 minutes. The broker
receipt is never changed.

## Owner resolution with evidence

`POST /trading/journal/{operation_id}/resolve` with
`{"outcome": "executed" | "not_executed" | "unknown", "statement": "...", "broker_reference": "..."}`
records an attestation for an `ambiguous` live operation. The statement and reference
are optional; without a statement the record reads "Owner attested; not broker
confirmation." The conversation's resolve card (`docs/owner-actions.md`) runs the same
attestation. It requires the
authenticated owner session (cookie with CSRF, or bearer token); the passkey device
proof is not required because the action authorizes no broker mutation. The row
becomes `resolved` with `details.resolution` (source `owner`, outcome, statement,
reference, actor, time, `broker_confirmed: false`) and `details.prior_receipt`; the
request, execution record and evidence stay. A durable `trading.operation_resolved`
event records the audit fact. In-progress operations return `operation_in_progress`
and settled ones `operation_already_settled`. The Web journal offers this form for
ambiguous entries.

Consumers of `resolved`:

- Opportunity theses (`sync_opportunity_execution`, run by the executor, by this
  route and by the gateway maintenance steps) read the outcome from the attestation: `executed`
  acts on the thesis as a confirmed entry would; `not_executed` releases the pending
  link so the thesis can be acted on again; an entry of `unknown` outcome still acts
  on the thesis so it can never authorize a second entry. A management operation of
  unknown outcome (owner `unknown` or any broker-state resolution) releases its
  pending link; when it is a broker-state `target_closed` on the thesis entry
  position, the position is observed closed and the thesis completes
  (`thesis_position_no_longer_open`).
- The agent's historical trade record (`record_excerpt`) keeps `send_state`,
  `prior_receipt`, `resolution` (without the owner's session reference) and the
  target-state `conclusion`, so an agent can tell a never-sent failure from a broker
  rejection and see how an operation was settled.
- The runtime's tool observation treats `resolved` as settled (never retried, the
  route keeps replaying the same operation) but not as success: it attaches the
  recovery hint `reload_authoritative_state`.

## Sequences

A batch of full closes of distinct positions (`trade_close_positions`, an approved
close-all) is a set of independent exits: no close depends on another, each one is
admitted again against its own fresh broker target under the send lock, and admission
never blocks a risk-reducing exit. Both the standing-authority and approval paths
therefore send every close of such a batch, whatever the result of the others: a close
whose reviewed position was stopped out or changed fails on its own, a close blocked by
a restriction is reported on its own, and a lost response leaves only that close
`ambiguous`. Calling the identical close-all again replays the completed approval.

Any other multi-request batch is treated as a dependent sequence: both paths stop after
the first result that is not `confirmed`, and the remaining requests are reported as
`failed` with `batch_halted_after_unconfirmed_result` and `send_state: "not_sent"`.
Today every other caller (`trade_execute`) submits a single request.

## Verification

- `tests/test_financial_admission.py`: risk-reducing classification, global controls,
  target-state rules (including a partly executed full close and a superseded
  modify), send state, batch halting and independent close-all batches, the agent
  history view and thesis outcomes.
- `tests/check_execution_recovery.py` (disposable PostgreSQL, simulation broker,
  real child processes): crash before send, interruption after submission before
  acknowledgement (Owner addendum §6 step 7: blocked new risk, traceable operation,
  no resend), scoped blocking versus reduce-only admission on the uncertain market,
  degraded and disconnected recovery, owner attestation through the API,
  a crashed submission whose broker observation keeps failing (held send lock, then
  ambiguous and owner-resolvable), a sibling that waits for a definitive rejection
  under the send lock, modify/cancel target-state reconciliation, verification
  recheck, an approved close-all that keeps sending its other exits after a stopped-out
  position and after a lost response, and approved agent cards that close, cancel and
  tighten on an uncertain market while entries and wider stops there stay blocked.
- `tests/check_opportunity_runtime.py`: owner attestations settle a thesis entry
  link (`not_executed` releases it, `executed` acts on it), and an observed-closed
  entry position completes its thesis.
- `tests/check_trading.py`: concurrency, lost responses, cancellation, legacy rows and
  observer fencing.

## Durable records and deletes

Journal rows, approvals, grants, restrictions and retired Super Bot
requests survive the agent, conversation, Run or broker connection they name (migration
`0036_durable_records`). A delete of an agent, a conversation or a broker connection is
refused with `delete_blocked_unresolved_operation` while an operation it touches has no
confirmed broker outcome. Otherwise the delete settles what depended on the parent: a
grant signed in a deleted conversation is revoked visibly and its waiting owner action
cards superseded, so no record keeps reading active while it can no longer run. A live
operation still uncertain after fifteen minutes raises one `operation_unresolved`
attention item from the watchdog, in the conversation of the agent that placed it,
unless its resolve card already asks the owner; it is never resent. See
`docs/gateway-reliability.md`.
