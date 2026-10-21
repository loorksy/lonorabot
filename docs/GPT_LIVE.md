# GPT-Live voice transport

Lonora uses the OpenAI Live API with `gpt-live-1` (or globally selected `gpt-live-1-mini`). Configure the OpenAI credential in Web settings; the project must have Live API access. Text and tool work retain the existing global routing and Python agent. The browser needs HTTPS, WebRTC and microphone permission. There is no separate RTC server or public RTC port.

A user click creates one WebRTC offer and one stable client receipt. The API commits that receipt before `POST /v1/live/sessions`; repeated or ambiguous requests cannot negotiate the same paid intent again. The project key stays on the server. The API returns an SDP answer only after the resident Gateway attaches to `/v1/live/sessions/{id}/attach`. React effect replay and browser refresh do not start calls.

The Gateway retains timestamped transcripts and handles `session.delegation.created`. It uses the delegation ID to submit an idempotent message to the current agent conversation. Missing, incomplete, oversized or evicted input is not submitted as a trading task. The handoff waits up to 30 seconds for delayed fragments and reports a handoff failure without calling it unintelligible speech or asking the owner to repeat it. Fragments are sorted by their source audio timestamps. Backend results return through bounded `session.commentary.append` events with acknowledged, persistent delivery state. All normal agent tools, permissions, durable runs and trading controls still apply.

The current offset-based completion predicate still needs redesign: the official client-delegation event contains no task text or finalized-turn marker, and a fragment end timestamp is not proof of semantic completeness. This bounded mitigation is not a claim of final protocol recovery or physical-device verification.

Ending a call closes its transport and drains `session.closed` usage. It does not cancel a durable trading task; speech interruption preserves background work, and task cancellation uses the authoritative task controls. Lost Gateway leases cannot write transcripts or submit tasks. Calls have a transport inactivity timeout. Raw microphone audio and provider keys are not stored in the public session response.

File STT/TTS utilities remain available independently; they are not dependencies of GPT-Live calls. Compatible signed mobile releases use the native WebRTC transport. JavaScript exports do not establish physical-device support, and native push-initiated incoming calls are not yet implemented.

Run the retained checks against an explicitly selected migrated disposable PostgreSQL database:

```sh
.venv/bin/python -m pytest tests/voice -q
```

These tests use explicit OpenAI contract fixtures and real PostgreSQL admission/agent queues. They verify idempotency, ambiguous paid failures, cancellation, lease fencing, transcript failure handling, acknowledged results and final usage. They do not claim a call against a real OpenAI project. Actual project access, microphone/audio playback and network behavior require a live call after configuring that credential.

Official references:

- https://developers.openai.com/api/docs/models/gpt-live-1
- https://developers.openai.com/api/docs/guides/live
- https://developers.openai.com/api/docs/guides/live-delegation
- https://developers.openai.com/api/docs/guides/voice-server-controls
