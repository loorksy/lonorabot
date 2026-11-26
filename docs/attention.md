# Attention items for the owner's events

What needs the owner (mandate 11.4, six kinds since Amendment 5) is one attention item per event, raised and withdrawn
by the server with no model involved. The contract is `AttentionNotification`,
`ATTENTION_EVENTS` and `BROKER_HEALTH_CODES` in `lonora_contracts/attention.py`,
mirrored in `packages/contracts/src/attention.ts`. The item is the payload of the
`attention.updated` and `attention.ready` events.

| Event | Code | Raised when | Withdrawn when |
|---|---|---|---|
| `trade_approval` | `approval_required` | a Trade Approval card becomes pending | the card is no longer pending |
| `settle_operation` | `operation_uncertain` | an operation becomes ambiguous (its Settle card is raised from the same event) | the operation is no longer ambiguous, or its Settle card ended (answered, superseded or expired) |
| `secret_request` | `secret_requested` | a Secret card (`secret`) becomes pending | the card is no longer pending, or its lifetime ran out |
| `mandate_card` | `mandate_proposed` | a Mandate card (`trading_mode`) becomes pending: an agent proposed it, or Lonora offered its own at onboarding; one item per agent, so a second card for the same agent while one is shown raises none | the card is no longer pending (the owner tapped it, or its agent was deleted), or another Mandate card for the same agent was tapped after it was raised |
| `broker_health` | `broker_token_rejected` | the account is disconnected with `broker_credentials_rejected` | the account is no longer disconnected with that problem, or its connection is disabled or removed |
| `broker_health` | `broker_account_undeployed` | the account is disconnected with `broker_account_undeployed` or `broker_account_not_found` | the same |
| `broker_health` | `broker_connection_lost` | the account has been disconnected for any other reason for 2 minutes (`LOST_CONNECTION_GRACE`) | the same |
| `broker_health` | `broker_rate_limited` | the account has been disconnected because MetaApi throttles its requests (`broker_rate_limited`) for 2 minutes; the account itself is fine and the adapter retries at the time MetaApi gives | the same |
| `background_health` | `gateway_stopped` | no Gateway heartbeat has been fresh for 3 minutes (`STOPPED_AFTER`), counted from the last heartbeat and never from before the API started; raised by the API (`tell_owner_if_stopped`, `lonora_gateway/health.py`), since a stopped Gateway cannot; one item per stop | a Gateway heartbeat is fresh again (45 s, `lonora_db/gateways.py`) |
| `background_health` | `model_access_failed` | a background run failed because every model it could use refused access: a rejected key (`auth`) or spent credit (`billing`), one item per provider; a model the key may not use (`permission`) or the provider does not have (`model_not_found`), one item per provider and model; one open item per route, cause and saved key (`executor.record_failure`, `raise_model_access`); one raised again within a day of the last that pushed carries `repeat` and does not push | another key is saved for that provider (its `credential`, the saved key's id and write time, differs), or a run that a model of that route answered completes (`settle_model_access`); a refused or missing model also once no agent would try it for background work any more (`model_in_use`), for example after the owner chose another |

- Every item is `action_required`, except `broker_rate_limited`, which is
  `important_change` (MetaApi throttling needs no action from the owner); a broker
  problem on an account with open positions or unresolved operations is `critical`.
  Each is ready at once, and it becomes ready
  once (one `attention.ready` event per item id).
- Card items come from the `owner_action.updated` and `trading.*` events through the
  attention projection (`lonora_gateway/attention.py`). Broker health items come from
  the account's stored `broker_recovery` snapshot (`lonora_core/broker_health.py`),
  checked on every attention tick: at most one open item per account and outage (the
  time the account became disconnected). The adapter's reason flaps between polls
  within one outage: a rejected token or an undeployed account stays the outage's
  problem while later polls show only a generic lost connection, and a lost connection
  is replaced by a specific problem (a rejected token or an undeployed account) once
  one shows. The two generic reasons, a lost connection and MetaApi throttling,
  alternate within one outage; the one raised first stays the outage's item.
- `withdraw_ended` (`lonora_db/attention.py`) checks the open items of these codes on
  every tick, 200 at a time, rotating through them in id order, and withdraws the ones
  whose card ended or whose problem cleared, including one the owner has already seen,
  with `suppression_code` `attention_superseded_state`; a seen item keeps its
  `updated_at`, so withdrawing it does not move it in the history.
- Broker health items open in Lonora's conversation, with `account_id`, `since` and the
  adapter's `reason_code` in their parameters; the owner text names the problem
  (`lonora_bus/attention_messages.json`).
- A model-access item opens in the conversation of the agent whose background run failed,
  with `provider`, `provider_name`, `route`, `reason` and `credential` in its parameters.
  Its owner text and push name the provider and the failure family only
  (`attention_text` with the item's parameters); while it stands, routines whose every
  model it covers are held (`docs/proactivity.md`).
- The stopped-Gateway item opens in Lonora's conversation, with `last_heartbeat` in its
  parameters. The API checks every 30 s (`watch_gateway`, `lonora_api/health.py`) and,
  while no Gateway runs, sends the push itself (`dispatch_push`). The view shows the
  line only while no heartbeat is fresh; once one is, the Gateway's own sweep
  (`withdraw_ended`) withdraws the item. Nothing wakes Lonora for it: its own work is what
  stopped.

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
  model, a peer, a page or the owner reaches it. A lost connection whose reason is a
  broker login MetaApi reports failing (`broker_login_rejected`,
  `broker_login_not_established`) also carries the fixed text of what was observed, and
  only that (`LOGIN_OBSERVED` in `lonora_db/secret_cards.py`): the account may have been
  trading until the drop, so no first-connect cause is attached.
- It keeps Lonora's normal authority: it is not observe-only.
- A paused Lonora is not woken (4.7); the owner still has the item, and Lonora is woken
  for it on the first tick after it resumes, while the problem still stands. A wake
  that fails is logged and tried again on a later tick.
- An uncertain operation delivered without its record (its projection kept failing,
  `quarantine_event`) names no operation, so it wakes nobody; the owner has the item.

## The attention view

The owner's one "needs your attention" view across all agents (mandate 11.7) is a server
projection with no model: `GET /attention/view` (`attention_view`, `AttentionViewRow`).

- It lists, newest first:
  - the open, still-current items of the owner's events above (Trade Approval, Settle,
    Secret and Mandate cards, broker health problems, Lonora's stopped background work,
    a model provider refusing background work);
  - Tasks that need the owner's review (`task_review`);
  - every run in a conversation that waits on the owner's answer to its question
    (`waiting_input` with a pending input request), as `owner_question`;
  - each agent's own unread alert (`owner_notify`, `agent_notification`), as
    `agent_alert`, with its summary: an alert has no other place outside its chat.
  - the watchdog's unread items about an operation still unresolved after its
    threshold (`operation_unresolved`) or work stopped after repeated interruptions
    (`run_quarantined`), as `system_alert`: they have no other lasting place either.
- Web and mobile show the same list as the «يحتاج انتباهك» tab. A row opens its
  conversation, where the fixed card or the question stands; opening it decides
  nothing. Opening a row with an item marks the item read: an alert (an agent's or the
  watchdog's) then leaves the list, a card or a Task review stays until it is answered.
  A question has no item; it is read once its conversation is read up to it.
- Each row says whether the owner has already looked at it (`seen`). The tab's dot,
  whose spoken label is "new" («جديد»), shows while the view lists a row that is not
  seen: both clients read `GET /attention/view` for it, so an unopened card or an
  unread question lights it however old it is, and a row already looked at does not.
