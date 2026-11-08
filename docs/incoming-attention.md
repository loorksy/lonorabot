# Incoming attention and voice continuity

The existing attention ledger and VoiceSessionRow now represent an opt-in incoming
conversation invitation. They reuse owner identity, exact Agent/Thread scope,
registered credentials, existing transactional events and Gateway lifecycle. They do
not create another Agent, notification scheduler or financial authorization.

The owner selects categories, registered credential, timezone, quiet hours, minimum interval and
short invitation lifetime in Voice settings. The Agent may inspect current ready
attention and request a conversation only for a meaningful scoped item. One
owner-level lock protects simultaneous requests. Attention identity deduplicates
replays; restart retains ringing/accepted/rejected/missed/cancelled state. Consent,
current attention, Agent pause, credential validity and timing are rechecked before
dispatch and acceptance. Expired invitations become missed and never reopen.

Accepting opens the same Agent and conversation through existing GPT Live/WebRTC.
It grants no financial permission. Ordinary updates remain in conversation.
Owner-wide voice admission separately prevents concurrent paid calls with distinct
client receipts. Same-receipt reconnect remains available. An abandoned unanswered
allocation can expire; a known remote session must close before replacement.

## Reach-me preference

The incoming-call policy record is the owner's single reach-me preference, part
of the owner profile every Agent reads (`docs/agent-memory-and-recall.md`). Its
`channel` is one of `activity` (keep it in Activity, no interruption), `notify`
(the inbox; see below), `message` (a message in the Agent's conversation) or `call`
(an incoming invitation). `enabled` is derived: invitations are possible exactly
when the channel is `call`, so the two can never disagree. A stored policy or a
client from before the channel existed keeps its meaning (`enabled` true reads as
`call`); a request that states both and contradicts itself is refused
(`incoming_call_channel_conflict`). These checks keep their own code in the API
response (`incoming_call_channel_conflict`, `incoming_call_device_required`,
`incoming_call_quiet_hours_incomplete`, `invalid_timezone`) instead of a generic
`invalid_request`, and Web and Mobile show the same Arabic or English text for each.
`notify` means the inbox: the alerts Lonora raises and the alerts an Agent raises
itself with `owner_notify` (below).

The owner sets it in Web Knowledge (About you) or Mobile Voice settings
(`PUT /api/owner/preferences`), or in chat: "Send me a message instead of
calling" makes the Agent call `owner_preferences_update`, which needs a Run that
answers the owner's message and records a revertible, attributed revision. Choosing
`call` from chat uses the selected enrolled device, otherwise the most recently
enrolled one, and turns on calls when the owner's decision is needed. While the
channel is not `call`, `owner_call_request` returns `owner_prefers_other_channel`
with the channel to use and creates no invitation (it and the call gate read the
channel afresh under the same owner lock a change takes, so a call never rings
against a newer "message me instead"); the device choice is kept for
a later "call me". Delivery is in-app only: none of this proves a device rang.

## Agent alerts (`owner_notify`)

An Agent can start contact itself. `owner_notify` (`lonora_tools/incoming_call.py`,
`notify_owner` in `lonora_db/attention.py`) takes an importance (`critical`,
`action_required`, `important_change` or `informational`; an opportunity needs the
server's evidence revalidation, so an Agent reports it as an important change), a
plain summary in the owner's language (8-400 characters, no ids or JSON), up to 8
evidence references, a `dedupe_key` and an optional `expires_at` (at most 31 days
ahead). It creates one attention item with code `agent_notification` through the
same `decide_attention` path as server alerts, in the Agent's own conversation (a
wake in the work lane reports to the conversation it came from, `report_thread` in
`lonora_db/threads.py`). The rules:

- One item per Agent and `dedupe_key`, whatever happens later: a repeat returns the
  first result with `deduplicated: true`.
- At most 6 alerts per Agent per rolling hour (`owner_notify_rate_limited`).
- Quiet hours (the reach-me preference) hold everything but `critical` until they end
  (`held_for_quiet_hours`, with `held_until`); the gateway's `ready_attention` then
  publishes it (`publish_ready`, shared with server alerts).
- Reach-me `activity` keeps non-critical alerts out of the inbox (`activity_only`);
  the owner's informational preference applies as for server alerts.
- `critical` and `action_required` alerts are ready at once; others within seconds.
- Delivery is in-app only (`delivery: "in_app"`): Web and Mobile show the label
  "Your agent alerted you" / «نبّهك وكيلك» with the summary in its own text direction.
  Off-app channels skip these items until Wave 3.

`owner_call_request` can target the returned `attention_id` (the Agent's own alert
stays current until it expires or the owner reads it), still under reach-me `call`,
the enrolled device, the allowed category, quiet hours and the call rate.
`owner_attention_list` and `owner_call_request` scope to the same report thread, so
a wake can call about the alert it raised. Nothing here grants authority.

## Delivery boundary

Foreground Mobile presentation is implemented. The optional provider protocol
returns a typed acknowledgement meaning only **provider accepted**. It does not
prove that a device received, displayed or rang for the invitation. The persisted
`ringing` invitation status allows the foreground invitation surface; it is not
an operating-system delivery receipt.

Before provider IO, the existing voice row commits an uncertainty fence. Owner
locking and that fence prevent simultaneous dispatch by concurrent Gateway
workers. Consent, source attention, scope and expiry are checked again before
dispatch. A timeout, cancellation or process loss leaves the attempt uncertain;
subsequent ticks never resend it automatically. There is no provider
reconciliation implementation or proven provider retry guarantee yet, so an
uncertain invitation waits for foreground acceptance, cancellation or expiry.
Stable invitation/idempotency identifiers assist future transport deduplication;
they do not claim exactly-once behavior from FCM or another external provider.
Older `retry_pending` rows are treated as uncertain, and older `delivered` rows
mean only provider accepted. No fake-provider acknowledgement establishes native
device readiness.

**Native background/killed-app delivery is unavailable**, because no production
FCM/APNs registration, platform incoming-call integration or verified physical
device delivery exists. A saved invitation or fake-provider receipt is not proof
a real device rang. PSTN remains unconfigured and OFF; no telephone provider,
owner telephone consent or outbound call was created.

The current Android 0.2.8 runtime remains foreground-only. It has no native push
registration or incoming-call module, and active native voice ends on background
transitions. Adding those modules requires a future compatible native release;
an OTA cannot supply missing native functionality. Physical installation proof
and secure push-token registration remain missing. Current foreground acceptance
uses the authenticated owner session and a selected passkey credential ID. It
checks credential membership and revocation, not a signed possession assertion
from the receiving installation. A synced passkey ID is not physical-device proof;
foreground invitations therefore are not bound to a proven physical device.
Registration and response proof are the next shared authentication foundation,
not completed by this delivery correction. Acceptance remains unrelated to
financial authority.

The native Live transcript path orders finite timestamped fragments, aggregates
bounded non-overlapping delegation windows, deduplicates repeats, persists revision
fingerprints and steers the same work when later corrections arrive. Silent gaps
are valid; an audio offset is not a finalized semantic user turn. Current client
Live delegation documentation supplies ID/offset, not a semantic finalization
proof. Provenance therefore remains provisional and cannot spend standing
financial authority. Late transcript corrections atomically withdraw their old
unexecuted approval and continue the same work. Exact UI confirmation of financial parameters remains a
separate valid confirmation. Physical Live behavior still needs provider/device
acceptance; deterministic recovery is not a claim of model-quality verification.

## Verification

`check_owner_profile.py` proves that "send me a message instead of calling",
said in chat, makes the next qualifying event ring nothing and produce exactly one
message. `check_incoming_calls.py` covers disposable PostgreSQL concurrency, restart,
provider lost acknowledgement without blind retry, a committed pre-IO fence,
concurrent dispatch, cancellation/restart, provider acknowledgement versus device
presentation, legacy state recovery, ownership, current policy, quiet hours,
rate, TTL, credential revocation, category withdrawal, Agent pause, terminal replay
and unchanged financial controls.
`check_voice_handoff_recovery.py` covers ordering, silence, restart/replay,
late correction, same-Run steering, conflict and lease fencing.
`tests/voice` also verifies bounded same-Agent context, paid admission and reconnect.
Foreground state predicates have TypeScript tests; native delivery remains blocked.
