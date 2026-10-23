# GPT-Live voice transport

Lonora uses the OpenAI Live API with `gpt-live-1` (or globally selected `gpt-live-1-mini`). Configure the OpenAI credential in Web settings; the project must have Live API access. Text and tool work retain the existing global routing and Python agent. The browser needs HTTPS, WebRTC and microphone permission. There is no separate RTC server or public RTC port.

A user click creates one WebRTC offer and one stable client receipt. The API commits that receipt before `POST /v1/live/sessions`; repeated or ambiguous requests cannot negotiate the same paid intent again. The project key stays on the server. The API returns an SDP answer only after the resident Gateway attaches to `/v1/live/sessions/{id}/attach`. React effect replay and browser refresh do not start calls.

The Gateway retains timestamped transcript observations and handles `session.delegation.created`. The public client-delegation contract supplies a delegation ID and audio offset, **not** task text or a finalized utterance. A fragment ending at the offset does not establish semantic completeness; silence may put the offset after the last word. There is no invented final-turn event and no separate STT/LLM/TTS pipeline.

For each source window, the Gateway orders deltas by audio timestamps, validates event identities and finite timestamps, and retains source event IDs, a content fingerprint and a revision. A 1.2-second stability interval schedules an observation; it does **not** authorize financial execution or certify final speech. Known overlaps, fragments crossing a boundary, missing/evicted input and conflicting event replays fail closed. Delayed fragments revise the same delegation idempotently through normal same-thread messages/steering. Earlier spoken outcomes are suppressed when a newer observation steers their active run. Arbitrary silence after speech is accepted without requiring `end_ms >= offset_ms`.

The existing PostgreSQL voice row owns this state. Row locks serialize concurrent observers; stable message receipts survive a new runtime/engine, and a stale Gateway lease cannot submit work. Transcript retention is bounded by 2,048 fragments and 60,000 characters per channel; at 256 delegations the call closes while retaining receipts instead of forgetting IDs and admitting replays. A rejected snapshot produces one bounded handoff-failure result after 30 seconds, without claiming unintelligible speech or asking the owner to repeat it. A changed source snapshot can recover without replaying the original snapshot.

Submitted observations persist `Run.model_metadata.voice_handoff` with session/delegation IDs, revision, fingerprint, source event IDs and `finalized: false`. The normal Agent/Thread/Task runtime interprets context and performs real steering/cancellation. Observation alone cannot create or consume autonomous financial authority. A separate explicit UI approval of frozen financial parameters remains valid; spoken text never becomes that approval. Backend results return through bounded `session.commentary.append` events with acknowledged, persistent delivery state.

**Remaining provider limitation:** bounded settling cannot prove that an arbitrary later fragment or correction will never arrive. Fully finalized semantic delegation is not available in the documented client protocol. Do not describe this bridge as verified semantic finalization or claim real provider/device verification from fixtures. A future provider contract with documented committed intent can extend this path without adding a second Agent runtime.

Ending a call closes its transport and drains `session.closed` usage. It does not cancel a durable trading task; speech interruption preserves background work, and task cancellation uses the authoritative task controls. Lost Gateway leases cannot write transcripts or submit tasks. Calls have a transport inactivity timeout. Raw microphone audio and provider keys are not stored in the public session response.

File STT/TTS utilities remain available independently; they are not dependencies of GPT-Live calls. Compatible signed mobile releases use the native WebRTC transport. JavaScript exports do not establish physical-device support, and native push-initiated incoming calls are not yet implemented.

Run the retained checks against an explicitly selected migrated disposable PostgreSQL database:

```sh
.venv/bin/python -m pytest tests/voice -q
.venv/bin/python tests/check_voice_handoff_recovery.py
```

These tests use explicit OpenAI contract fixtures and real PostgreSQL admission/agent queues. They verify idempotency, ambiguous paid failures, cancellation, source ordering, silence offsets, provisional provenance, late revisions, same-run steering, a fresh database engine/runtime, conflicting replay rejection, lease fencing, transcript failure handling, acknowledged results and final usage. They do not claim a call against a real OpenAI project. Actual project access, microphone/audio playback and network behavior require a live call after configuring that credential.

Official references:

- https://developers.openai.com/api/docs/models/gpt-live-1
- https://developers.openai.com/api/docs/guides/live
- https://developers.openai.com/api/docs/guides/live-delegation
- https://developers.openai.com/api/docs/guides/voice-server-controls
