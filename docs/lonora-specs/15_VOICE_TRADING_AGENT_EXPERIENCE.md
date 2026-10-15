PROJECT: Lonora (`loorksy/lonorabot`)

IMPORTANT:
- This is an implementation task. Do not stop at an architecture-only answer.
- Inspect the current repository before changing code. Do not assume conceptual names in this prompt already exist.
- Reuse existing Lonora primitives and contracts. Do not create parallel runtimes, duplicate event buses, duplicate broker ledgers, or duplicate chat state systems.
- Preserve exact broker symbols, owner/account/Agent scoping, Trading ON/OFF, Emergency Stop, authorization, risk controls, idempotency, journal, locking, and broker reconciliation.
- Never fabricate unavailable market, execution, account, notification, or replay evidence.
- Keep current global model routing; do not introduce per-Agent model/provider selectors.
- Keep Arabic-first/RTL compatibility across Web and Mobile.
- Do not mention paid API/token/key requirements.
- Work on a dedicated branch, add focused tests, and run relevant existing checks.


# 15 — Voice Trading Agent Experience

## Objective

Make voice a first-class interface to the same persistent Lonora Agent, Thread, tools, tasks, Collaboration Sessions, Super Bot state, and trading safety model.

Voice must not create a separate "voice Agent" or separate trading brain.

## Inspect first

The repository already contains a resident realtime voice path where microphone audio stays on WebRTC and tools remain in Lonora.

Inspect:
- voice realtime/session runtime
- Web/Mobile call components
- current transcript handling
- thread/message creation
- tool dispatch
- barge-in/cancel behavior
- Android/iOS native audio/WebRTC behavior
- existing voice status/error handling

Extend the real stack.

## Same identity and state

A voice call with an Agent must use the same:
- agent_id
- thread_id
- task state
- Super Bot state
- watches/goals/theses
- collaboration sessions
- permissions
- trading controls

The owner can start in text, switch to voice, then return to text without losing context.

## Conversational responsiveness

While long-running work or Super Bot monitoring continues, the owner can ask by voice:
- current task status
- market status
- why the Agent is waiting
- what changed
- which collaborator is still working

The Agent should inspect real runtime state before answering.

## Voice task steering

Natural-language voice can:
- modify a running task
- pause/resume/cancel when semantically understood
- change non-sensitive preferences
- ask for status

Use the same contextual-intent/runtime validation from Prompt 04.

No fixed voice command words.

## Financial actions

Voice never bypasses existing financial authority.

A spoken request to execute/expand autonomous authority must still pass the same:
- Trading ON/OFF
- Emergency Stop
- account/symbol scope
- risk
- approval/authorization
- device/owner confirmation where required
- idempotency/reconciliation

Do not treat voice recognition as sufficient identity proof for sensitive authority expansion.

## Super Bot voice control

Owner may ask naturally:
- what Super Bot is doing
- why it is waiting
- pause/resume
- change a safer limit
- request a sensitive authority expansion

Sensitive changes must still invoke the same secure confirmation flow defined in Prompt 03's activation extension.

## Barge-in

Support interruption of Agent speech where current voice stack permits it.

When user starts speaking:
- stop/duck current spoken response appropriately
- preserve already committed runtime actions
- do not automatically cancel background tasks unless the semantic user instruction actually means cancel/pause

Barge-in is a speech interaction feature, not a task cancellation primitive.

## Streaming transcript

Persist/use transcript consistently enough that:
- text chat sees the meaningful user/Agent exchange
- conversation context remains coherent after call ends
- partial/interim speech is not treated as a final financial instruction

Only finalized semantic utterances may become actionable intent.

## Incomplete speech safety

Do not execute from partial transcript fragments.

Example:
"Buy gold if..."

must not execute from "Buy gold" before the rest of the utterance arrives.

Use final/committed utterance semantics.

## Collaboration by voice

Owner can address visible/active Guest Agents by name or `@mention` equivalent in transcript when supported.

Examples:
- ask EUR specialist a follow-up
- ask all current participants for final view
- return to Host Agent

Use the same Collaboration Session; do not create a voice-only collaboration path.

## Voice status phrases

The Agent may answer concisely:
- working
- waiting
- checking
- verifying

But it must inspect real state; no fake "I'm checking" role-play.

## Audio failure safety

Handle gracefully:
- mic permission denied
- WebRTC connection failure
- audio route change
- app backgrounding
- reconnect
- realtime provider failure
- transcript failure

The app must not crash.
Background tasks/Super Bot must continue server-side unless explicitly stopped.

## Mobile verification

Test on actual Android runtime where available, especially because native WebRTC/audio failures may not surface as ordinary JS exceptions.

Verify:
- start/end call
- background/foreground
- interruption/barge-in
- text ↔ voice continuity
- call while background task runs
- call while Super Bot waits
- failure/reconnect

## UI

Voice UI should show:
- current Agent identity
- listening/speaking/connecting state
- compact task/Super Bot activity when relevant
- current Guest Agent identity when another Agent is speaking

Do not build a separate trading dashboard inside the call screen.

## Tests

Cover:
- voice uses same Agent/Thread
- text context survives into voice and back
- background task continues during voice
- status query reads real task state
- partial transcript cannot trigger financial execution
- final utterance can produce normal validated intent
- barge-in stops speech without cancelling unrelated task
- Super Bot sensitive change still requires secure authorization
- Guest Agent can respond in same collaboration by voice/text continuity
- reconnect does not duplicate actions
- native failure does not crash mobile
- app close does not stop server-side Super Bot/task

## Definition of done

Voice is another interface to the same persistent Lonora Agent and trading runtime: same context, same tools, same collaboration, same Super Bot, same safety, same durable work—without a separate voice brain or weaker financial controls.
