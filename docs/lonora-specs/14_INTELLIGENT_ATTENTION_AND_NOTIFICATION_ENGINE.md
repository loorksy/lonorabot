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


# 14 — Intelligent Attention and Notification Engine

## Objective

Build a unified attention layer that decides when Lonora should proactively interrupt the owner, when it should update silently, and how multiple related events are deduplicated into one meaningful notification.

The goal is high-signal communication, not chat spam.

## Inspect first

Inspect current:
- event system
- Gateway channel dispatch
- Web/Mobile message updates
- trading approvals
- routines/watches
- manual position events
- collaboration events
- thread/message creation
- any existing notification/channel abstractions

Reuse them.

## Core principle

Not every event is a user notification.

Separate:

RUNTIME EVENT
→ ATTENTION DECISION
→ USER-FACING NOTIFICATION (only if justified)

The system should preserve internal events even when no notification is emitted.

## Attention categories

Support a small structured importance model such as:

CRITICAL
ACTION_REQUIRED
IMPORTANT_CHANGE
OPPORTUNITY
INFORMATIONAL
SILENT

Use project conventions rather than forcing exact labels.

## Examples

Critical:
- Emergency/risk condition
- account/broker state that threatens active execution safety

Action required:
- approval
- owner clarification needed
- authorization needed

Important change:
- thesis invalidated
- manual position materially changed
- Super Bot paused/degraded
- broker/feed recovered after a meaningful outage

Opportunity:
- watched setup confirmed and still valid

Informational:
- meaningful task milestone

Silent:
- routine tick
- repeated unchanged watch evaluation
- internal retry that recovered without consequence

Examples are guidance, not hardcoded phrase matching.

## Deduplication

Prevent repeated notifications for the same logical event.

Use durable identity such as:
- event/resource id
- Agent
- account
- symbol
- watch/thesis/goal id
- state transition version

Do not deduplicate only by rendered text.

## Coalescing

Related events arriving close together may be summarized into one notification when it improves clarity.

Examples:
- several watch subconditions complete → one "setup confirmed" update
- broker reconnect + market-data recovery → one recovery update
- several Agents contribute to one collaboration → one final result, not three redundant notices

Do not delay critical safety notifications unnecessarily.

## Ownership

Notification ownership must follow the system roles already defined:

- account-level events → Personal Agent
- specialist watch/thesis events → owning specialist
- collaboration result → Host Agent/current Collaboration Session
- direct `@mention` response → mentioned Agent
- Super Bot state → owning Agent

Avoid duplicate messages from multiple Agents for the same account event.

## User-attention policy

Represent owner preferences/policy cleanly if current settings architecture allows it.

Useful controls may include:
- proactive opportunity notifications on/off
- routine progress verbosity
- quiet/silent informational updates
- critical/action-required always allowed

Do not allow preferences to suppress mandatory safety/authorization information if the product requires it.

## Context-aware silence

Lonora should remain silent when:
- nothing materially changed
- a watch is still in the same state
- a recommendation remains unchanged
- an internal retry recovered without user impact
- a collaborator returned redundant evidence that does not change the session

Persist state so this is deterministic.

## Meaningful transition detection

Notify on real transitions such as:
- FORMING → CONFIRMED
- CONFIRMED → INVALIDATED
- ACTIVE → PAUSED
- broker healthy → disconnected
- disconnected → recovered
- manual position opened/closed
- approval requested/resolved
- goal materially advanced/completed

Do not notify on every poll/tick.

## Message style

User-facing updates should be concise and conversational.

They should state:
- what changed
- why it matters
- whether action is required
- what Lonora is doing next

Avoid raw internal event names in the normal chat.

## In-thread vs push/channel delivery

Use existing channel architecture.

Decide separately:
- record in Thread
- show in active chat
- push/send through connected channel

Do not create duplicate messages if the user is already actively viewing the same event unless product behavior requires it.

## Rate control

Add bounded anti-spam protection:
- coalescing window where appropriate
- per-resource transition suppression
- repeated identical-state suppression

Critical events must not be hidden by a generic rate limiter.

## Collaboration integration

Do not notify every participant completion by default.

Prefer:
- meaningful participant conflict
- owner-requested status
- final recommendation
- action-required issue

## Trading integration

Opportunity notification must revalidate:
- quote freshness
- setup validity
- execution quality where relevant

Do not push "BUY NOW" from a stale trigger.

## Auditability

Persist enough to answer:
- which runtime event caused a notification
- which Agent owned it
- why it was delivered/suppressed/coalesced
- which channel/thread received it

Do not store secret device credentials.

## Tests

Cover:
- repeated unchanged watch does not spam
- meaningful watch transition notifies once
- account-level event routes through Personal Agent once
- collaboration participant completions do not each spam the user
- final collaboration result is delivered
- critical event bypasses ordinary coalescing delay
- duplicate reconnect events coalesce
- stale opportunity is revalidated before notifying
- suppression decision is auditable
- user preference suppresses optional informational notification
- action-required/critical behavior remains correct
- Web/Mobile/channel delivery does not duplicate the same logical message unexpectedly

## Definition of done

Lonora proactively speaks when something materially changes or the owner needs to act, remains quiet when nothing meaningful changed, deduplicates/coalesces related events, and preserves one clear Agent owner for each user-facing notification.
