# One vocabulary (W15-9)

The owner meets one authority system and plain words. This page records what was
retired, what replaced it and where the owner-visible labels come from. The
enforcement path is unchanged: the single executor, the per-account lock, the signed
grant, the money limits, the pauses and Stop new trading.

## Super Bot and goal autonomy are retired

- A signed `AccountAuthority` grant is the only authority. The `super_bot_propose`,
  `super_bot_status` and `super_bot_stop` tools, the `/agents/{id}/super-bot` and
  `/super-bot/*` routes and the Super Bot activation cards on Web and Mobile are
  removed. Device enrollment and revocation (`/auth/devices*`) stay.
- Migration `0040_retire_super_bot_requests` (after `0040_explicit_agent_permission_rows`)
  marks pending and activated `ln_super_bot_requests` rows `retired` and keeps every
  row; it withdraws their open "needs authorization" inbox items and gives grants that
  were already active a skipped readiness-review receipt. A marker row records each
  change, so the downgrade restores exactly those rows. Nothing reads a retired row.
- A goal is a plan under the agent's trading level and signed grant
  (`trading-goals.md`). `GoalCreate` and `GoalControl` have no `autonomous` field and no
  owner limit knobs; a live step outside the grant becomes an approval card under
  *On its own*. (Shadow trading is removed, Q57.)
- The readiness review and the confirmation line after signing are keyed on grants
  (`account-authority.md`). The avatar crown is "trades on its own"
  (`trades_on_its_own`), shown while the agent is not paused and holds a grant in
  force.
- The attention codes `super_bot_authorization` and `super_bot_changed` stay valid for
  stored rows and read "Request updated"; nothing raises them any more.

## The brake is "Stop new trading"

"Emergency Stop" is named "Stop new trading" / «إيقاف الصفقات الجديدة» everywhere the
owner or a model reads it (`trading-safety.md`, the operating policy, constitution,
prompts and bundled skills), because it closes nothing. The stored flag and the API
field keep their names.

## The trading control appears only where trading is possible

The composer shows the trading level (No trading / Ask me / On its own) only for an
agent that can trade: Lonora, an agent with an account, a level above No trading, a
grant (signed or awaiting the signature) or a trade waiting for the owner in the
conversation. Any other agent shows a small "No trading" / «لا يتداول» badge. The rule
is one shared function, `showsTradingControl` in `@lonora/core`, used by Web and Mobile.
It is presentation only.

## No raw ids or JSON in normal views

- Activity rows say what the agent does ("Searching sources", «يحفظ في الذاكرة») from
  the tool's registry metadata: `tool.started` now carries the tool's `toolset` and its
  `effect` (`read`, `change` or `financial`), and `activityCallLabel` in `@lonora/core`
  turns them into one Arabic or English line. A short override table, keyed by
  registry id, names the few tools whose family label would state the wrong action
  (`owner_action_propose` "Preparing a card for you", `wait_for_input` "Waiting for
  your reply", the skill tools,
  `market_position_size`, `owner_call_request`); `tests/test_one_vocabulary.py` keeps
  it in sync with the registry. The phase follows the same metadata instead of a
  pattern on tool names. Events from before the metadata read as "Using a tool". The
  registry id stays available as `data-tool` / a test id.
- Goal execution history and the trading journal show the step or symbol, the status
  and the broker ticket; the operation id, the decision evidence and the raw broker
  result sit behind "Technical details". A goal's reason code is shown as a sentence.
- A colleague's result reaches a conversation inside a `<peer_outcome>` wrapper that
  agents read; `peerOutcome` in `@lonora/core` strips it for inbox previews and Mobile
  message bubbles.
- Approval cards show labeled values: "Broker ticket" before a broker reference, and a
  result code only as its owner sentence. The reason under a broker result comes from
  `financialResultReason` in `@lonora/core` on both clients: an uncertain result
  (`broker_result_ambiguous`, `execution_interrupted_after_send`,
  `broker_result_mismatch`, `operation_in_progress` or any code recorded after the send
  boundary) always says it will not be sent again and to check positions and orders,
  never "Try again"; a known not-sent cause says why; Web falls back to its general
  error text only for a result known not to have executed.

## One label table for Web and Mobile

Operation status (`operationStatusText`), approval-card status (`approvalStatusText`),
the result reason (`financialResultReason`) and the broker ticket label
(`brokerTicketLabel`) come from `@lonora/core`; neither
client keeps its own copy. Mobile "bot" wording is "agent" / «وكيل».

## Error copy says the outcome

`stale_lease`, `context_limit_exceeded`, `invalid_tool_exchange` and `tool_round_limit`
no longer tell the owner to start a new conversation or mention another worker: they
say what happened and that the conversation is kept. `agent_permission_changed` (a
goal step whose agent changed level while it was prepared) has shared owner text.

## Verification

- `tests/test_one_vocabulary.py`: no Super Bot tool, no goal autonomy field, retired
  events raise no attention, `tool.started` carries the registry toolset and effect.
- `tests/web/one-vocabulary.test.ts`: no owner-visible catalog text (Web, Mobile,
  attention messages, core label tables) names Super Bot or Emergency Stop; the shared
  label tables; activity labels; the trading-control rule; the peer wrapper.
- `tests/check_device_authority.py`: the retired surface, the composer confirmation
  line, the marker, device revocation and the migration round trip.
- `tests/check_activation_review.py`, `tests/check_goals.py`,
  `tests/check_conversational_setup.py` and
  `tests/check_unified_permissions.py` on fresh databases.
