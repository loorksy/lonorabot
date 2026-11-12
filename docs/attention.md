# Attention items for the owner's events

What needs the owner (mandate 11.4) is one attention item per event, raised and withdrawn
by the server with no model involved. The contract is `AttentionNotification`,
`ATTENTION_EVENTS` and `BROKER_HEALTH_CODES` in `lonora_contracts/attention.py`,
mirrored in `packages/contracts/src/attention.ts`. The item is the payload of the
`attention.updated` and `attention.ready` events.

| Event | Code | Raised when | Withdrawn when |
|---|---|---|---|
| `trade_approval` | `approval_required` | a Trade Approval card becomes pending | the card is no longer pending |
| `settle_operation` | `operation_uncertain` | an operation becomes ambiguous (its Settle card is raised from the same event) | the operation is no longer ambiguous, or its Settle card ended (answered, superseded or expired) |
| `secret_request` | `secret_requested` | a `connect_credential` card becomes pending | the card is no longer pending, or its lifetime ran out |
| `broker_health` | `broker_token_rejected` | the account is disconnected with `broker_credentials_rejected` | the account is no longer disconnected with that problem, or its connection is disabled or removed |
| `broker_health` | `broker_account_undeployed` | the account is disconnected with `broker_account_undeployed` or `broker_account_not_found` | the same |
| `broker_health` | `broker_connection_lost` | the account has been disconnected for any other reason for 2 minutes (`LOST_CONNECTION_GRACE`) | the same |

- Every item is `action_required` (a broker problem on an account with open positions
  or unresolved operations is `critical`), so it is ready at once, and it becomes ready
  once (one `attention.ready` event per item id).
- Card items come from the `owner_action.updated` and `trading.*` events through the
  attention projection (`lonora_gateway/attention.py`). Broker health items come from
  the account's stored `broker_recovery` snapshot (`lonora_core/broker_health.py`),
  checked on every attention tick: at most one open item per account and outage (the
  time the account became disconnected). The adapter's reason flaps between polls
  within one outage: a rejected token or an undeployed account stays the outage's
  problem while later polls show only a generic lost connection, and a lost connection
  is replaced by the specific problem once one shows.
- `withdraw_ended` (`lonora_db/attention.py`) checks the open items of these codes on
  every tick, 200 at a time, rotating through them in id order, and withdraws the ones
  whose card ended or whose problem cleared, including one the owner has already seen,
  with `suppression_code` `attention_superseded_state`; a seen item keeps its
  `updated_at`, so withdrawing it does not move it in the history.
- Broker health items open in Lonora's conversation, with `account_id`, `since` and the
  adapter's `reason_code` in their parameters; the owner text names the problem
  (`lonora_bus/attention_messages.json`).

## Lonora's system alerts

Lonora receives the system alerts (mandate 3.1.5, 9.4): each broker health problem and
each uncertain operation wakes Lonora once (`lonora_db/system_alerts.py`). On every
attention tick, `wake_for_alerts` wakes Lonora for each open alert item it has not been
woken for yet.

- The wake is a Run of Lonora with trigger `broker_event` in a new work thread, with
  `origin_thread_id` set to Lonora's conversation, so its non-empty answer is posted
  there (`outcome_return`). Its id is derived from the problem (`alert_key`: the code,
  account and outage start, or the operation id), so the same problem never wakes
  Lonora twice: not across gateways, nor when its item is raised again in the same
  outage after the connection was disabled and enabled.
- Its prompt is fixed server text that names only server values (the problem, the
  account or operation id, the adapter's reason code, the start time). No text from a
  model, a peer, a page or the owner reaches it.
- It keeps Lonora's normal authority: it is not observe-only.
- A paused Lonora is not woken (4.7); the owner still has the item, and Lonora is woken
  for it on the first tick after it resumes, while the problem still stands. A wake
  that fails is logged and tried again on a later tick.
- An uncertain operation delivered without its record (its projection kept failing,
  `quarantine_event`) names no operation, so it wakes nobody; the owner has the item.
