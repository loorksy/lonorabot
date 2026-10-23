# Incoming attention and voice continuity

The existing attention ledger and VoiceSessionRow now represent an opt-in incoming
conversation invitation. They reuse owner identity, exact Agent/Thread scope,
registered devices, existing transactional events and Gateway lifecycle. They do
not create another Agent, notification scheduler or financial authorization.

The owner selects categories, device, timezone, quiet hours, minimum interval and
short invitation lifetime in Voice settings. The Agent may inspect current ready
attention and request a conversation only for a meaningful scoped item. One
owner-level lock protects simultaneous requests. Attention identity deduplicates
replays; restart retains ringing/accepted/rejected/missed/cancelled state. Consent,
current attention, Agent pause, device validity and timing are rechecked before
dispatch and acceptance. Expired invitations become missed and never reopen.

Accepting opens the same Agent and conversation through existing GPT Live/WebRTC.
It grants no financial permission. Ordinary updates remain in conversation.
Owner-wide voice admission separately prevents concurrent paid calls with distinct
client receipts. Same-receipt reconnect remains available. An abandoned unanswered
allocation can expire; a known remote session must close before replacement.

## Delivery boundary

Foreground Mobile presentation is implemented. A provider protocol has bounded,
idempotent delivery semantics and failure/recovery tests with a fake provider.
**Native background/killed-app delivery is unavailable**, because no production
FCM/APNs registration, platform incoming-call integration or verified physical
device delivery exists. A saved invitation or fake-provider receipt is not proof
a real device rang. PSTN remains unconfigured and OFF; no telephone provider,
owner telephone consent or outbound call was created.

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

`check_incoming_calls.py` covers disposable PostgreSQL concurrency, restart,
provider lost acknowledgement, one delivery effect, ownership, current policy,
quiet hours, rate, TTL, terminal replay and unchanged financial controls.
`check_voice_handoff_recovery.py` covers ordering, silence, restart/replay,
late correction, same-Run steering, conflict and lease fencing.
`tests/voice` also verifies bounded same-Agent context, paid admission and reconnect.
Foreground state predicates have TypeScript tests; native delivery remains blocked.
