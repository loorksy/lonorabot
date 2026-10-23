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

`check_incoming_calls.py` covers disposable PostgreSQL concurrency, restart,
provider lost acknowledgement without blind retry, a committed pre-IO fence,
concurrent dispatch, cancellation/restart, provider acknowledgement versus device
presentation, legacy state recovery, ownership, current policy, quiet hours,
rate, TTL, credential revocation, category withdrawal, Agent pause, terminal replay
and unchanged financial controls.
`check_voice_handoff_recovery.py` covers ordering, silence, restart/replay,
late correction, same-Run steering, conflict and lease fencing.
`tests/voice` also verifies bounded same-Agent context, paid admission and reconnect.
Foreground state predicates have TypeScript tests; native delivery remains blocked.
