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
| `resolved` | Uncertainty settled without establishing the operation's own outcome: an owner attestation, or broker state showing the target no longer exists. Never broker confirmation. |

The executor reserves the row as `reserved`, and `before_send` moves it to
`submitted` under the journal row lock in the same transaction that records send
authorization. Any failure before `before_send` returns is persisted as
`failed` with `send_state: "not_sent"`; any failure after it stays `ambiguous`.
`persist_result` never regresses `confirmed`, `failed` or `resolved`, and keeps the
server-captured execution record, quality and evidence.

`journal_data` (GET `/trading/journal`) adds the derived `send_state`
(`not_sent | sent | unknown`), `verification_status`,
`awaiting_broker_confirmation` and `resolution`. Each owner-visible transition emits
`trading.operation_updated` in the same transaction.

## Scoped admission and reduce-only actions

`lonora_trading/admission.py` defines a request as risk-reducing only against the
fresh broker target read at the boundary:

- `close_position` of an existing position on the same symbol, fully or for at most
  its current volume (closing a hedge leg reduces gross exposure and is admitted);
- `cancel_order` of an existing pending order on the same symbol;
- `modify_position` that moves the stop-loss strictly toward the market (higher for a
  buy, lower for a sell) or adds one to an unprotected position, with the take-profit
  unchanged and nothing cleared.

Everything else — entries, pending-order edits, take-profit changes, removing or
widening protection — is risk-increasing.

- Trading OFF and Emergency Stop reject risk-increasing requests only. A
  risk-reducing request stays admissible on every path; this relaxes no
  authorization (owner session, exact approval or matching signed grant still apply,
  and the lease, preflight and broker checks still run).
- An unresolved operation (`submitted` or `ambiguous`) blocks new risk-increasing
  requests on the same account and symbol, or the same position/order ticket, for
  every admission path including the owner API. It never blocks a risk-reducing
  request. A `reserved` row never blocks.
- A `degraded` broker observation blocks only markets with unresolved operations
  (also for decision readiness); a `disconnected` one blocks new risk on the account
  but still admits exits.

## Observe-only recovery

`reconcile_ambiguous` (gateway maintenance loop, every 10 s, bounded and rotating)
and `reconcile_broker_account` share `observe_operation` and never send:

1. An abandoned `reserved` row (lease gone, or 5 minutes without a lease) is released
   to `failed` / `operation_not_sent` without any broker call. The release and the
   reserved→submitted transition share the row lock, so a late sender stops at
   `before_send`.
2. A `submitted` row whose sender is gone, or an `ambiguous` row, is first observed
   through the adapter's correlated reconciliation (operation identity / MetaApi
   `clientId`).
3. If that is inconclusive, set-type management actions are compared with the broker
   target (`lonora_trading/target_state.py`). Repeating these cannot add exposure,
   so the target is evidence. After a two-minute settle window: modify whose fields
   all match → `confirmed`; mismatch → `failed` (`target_state_not_reached`); target
   gone → `resolved` (`target_closed` / `target_no_longer_pending`). Cancel: order
   still pending → `failed`; gone without fill evidence → `confirmed`
   (`order_no_longer_pending`); fully filled first → `failed`
   (`order_filled_before_cancel`); partial fill stays uncertain. A full close whose
   position is gone → `confirmed` (`position_no_longer_open`). Creates and partial
   closes are never inferred from state.
4. Still inconclusive: a `submitted` row becomes `ambiguous`
   (`execution_interrupted_after_send`).

`recheck_verifications` re-reads `confirmed` rows whose resulting state is still
`pending` every 30 s until `verified`, or `unverified` after 15 minutes. The broker
receipt is never changed.

## Owner resolution with evidence

`POST /trading/journal/{operation_id}/resolve` with
`{"outcome": "executed" | "not_executed" | "unknown", "statement": "...", "broker_reference": "..."}`
records an attestation for an `ambiguous` live operation. It requires the
authenticated owner session (cookie with CSRF, or bearer token); the passkey device
proof is not required because the action authorizes no broker mutation. The row
becomes `resolved` with `details.resolution` (source `owner`, outcome, statement,
reference, actor, time, `broker_confirmed: false`) and `details.prior_receipt`; the
request, execution record and evidence stay. A durable `trading.operation_resolved`
event records the audit fact. In-progress operations return `operation_in_progress`
and settled ones `operation_already_settled`. The Web journal offers this form for
ambiguous entries. A resolved Goal step stays blocked for an explicit owner decision.

## Sequences

Both the standing-authority and approval paths stop a batch after the first result
that is not `confirmed`; the remaining requests are reported as `failed` with
`batch_halted_after_unconfirmed_result` and `send_state: "not_sent"`.

## Verification

- `tests/test_financial_admission.py`: risk-reducing classification, global controls,
  target-state rules, send state and batch halting.
- `tests/check_execution_recovery.py` (disposable PostgreSQL, simulation broker,
  real child processes): crash before send, interruption after submission before
  acknowledgement (Owner addendum §6 step 7: blocked new risk, traceable operation,
  no resend), scoped blocking versus reduce-only admission under Emergency Stop,
  Trading OFF, degraded and disconnected recovery, owner attestation through the API,
  modify/cancel target-state reconciliation, verification recheck and the approval
  batch stop.
- `tests/check_trading.py`: concurrency, lost responses, cancellation, legacy rows and
  observer fencing.
