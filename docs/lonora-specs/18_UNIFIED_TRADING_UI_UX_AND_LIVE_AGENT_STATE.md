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


# 18 — Unified Trading UI/UX and Live Agent State

## Objective

Create one coherent Web/Mobile UX for Lonora's trading Agent state without turning the product into a dense trading dashboard.

The chat remains primary.

The UI should make it immediately obvious:
- who is speaking
- what the Agent is doing
- why it is waiting
- whether Super Bot is active
- whether a setup/thesis/watch is active
- whether a collaboration is active
- whether a manual trade is being monitored
- whether data/broker health is degraded
- whether the user needs to act

## Inspect first

Reuse current:
- Web chat context/message cards
- Mobile thread screen/composer
- working indicator / Run state
- CollaborationMarker
- ToolActivityDisclosure
- TradeApprovals
- TradingGoals
- chart/trading components
- reconnect/recovery notices
- message streaming
- current Arabic translations

Do not create a separate full-screen trading app unless the existing navigation already requires one.

## One live-state model

UI state must come from authoritative backend/runtime contracts.

Do not independently infer state in Web and Mobile using incompatible logic.

Create/reuse a compact live Agent-state projection containing relevant fields such as:
- Agent identity
- working/idle/waiting
- current phase
- active long-running Task summary
- Super Bot state
- current goal progress
- active watch/thesis summary
- active Collaboration Session
- manual position attention state
- data/broker health
- action-required state

Keep payload bounded.

## Chat header

Provide a minimal live indicator near Agent identity.

Examples of user-facing semantics:
- working
- monitoring
- waiting
- Super active
- degraded

Do not show five badges simultaneously.
Prioritize the most important current state.

Tapping the indicator may open a compact status sheet/card.

## Compact status card

A compact status view may show only the currently useful facts:

Agent
Current state
Goal/progress if active
What it is waiting for
Active setup/watch count
Open-position count if relevant
Collaboration participants if active
Health warning if relevant

Provide actions only when they are currently valid:
- pause/resume
- stop
- inspect details
- Emergency Stop
- open collaboration
- open position/thesis

## "Why waiting?"

This must be first-class UX.

If state is WAITING, expose a concrete reason from runtime:
- waiting for M15 confirmation
- waiting for price to reach zone
- waiting for participant analysis
- waiting for owner approval
- waiting because broker feed is degraded

Do not show generic "waiting" when a structured reason exists.

## Working indicator

Existing Agent animation/working indicator should reflect real phase:
- thinking
- researching
- executing
- verifying
- monitoring
- waiting

Do not randomly rotate decorative states.

The composer remains usable while background work runs.

## Guest Agents

Inside a Host Thread:
- Guest Agent messages show real avatar/name
- subtle participant marker
- tapping Agent opens profile/actions
- "Open Agent chat" is available
- current Collaboration Session remains visible/preserved

Do not visually merge Guest output into Host identity.

## Mentions

Use Prompt 07 behavior:
- autocomplete
- stable Agent identity
- multi-Agent mention
- `@all` scoped to current collaboration

Keep mention rendering clean in RTL/mixed-script chat.

## Super Bot UI

Super Bot should be understandable from chat without settings hunting.

Support:
- activation card from Prompt 03
- active status indicator
- goal/progress
- current state
- why waiting
- active watches
- pause/stop
- Emergency Stop

Do not expose all internal detectors by default.

## Opportunity/thesis cards

When useful, show a compact trading thesis/opportunity card:
- exact symbol
- BUY/SELL/WAIT
- state: forming/confirmed/invalidated/expired
- key entry/invalidation/targets when valid
- evidence-quality summary
- last updated

Allow expand for details/evidence.

Do not leave stale "confirmed" cards looking active after invalidation/expiry.

## Manual trade UI

Manual/external position event appears primarily in Personal Agent chat.

Show:
- exact symbol
- direction/volume
- current Lonora assessment
- observe/manage state
- relevant specialist link

One logical trade event should not appear as duplicate cards in several Agent chats.

## Health/degraded UI

When Prompt 13/17 reports degraded health:
- compact warning in relevant Agent/chat
- affected account/symbol
- what is suspended
- recovery status

Do not flood chat with repeated reconnect messages.

## Approval lifecycle

Resolved approval cards must update in place and stop behaving like a permanent footer that pushes newer messages above them.

Maintain chronological message ordering.

## Mobile chat reliability

Preserve/fix behaviors from Prompt 02:
- open at latest relevant message
- auto-follow only when user is near bottom
- floating jump-to-latest control when scrolled up
- keyboard-safe composer
- loading vs empty state
- latest meaningful inbox preview/time
- no duplicate generic reconnect errors

## Web reconnect

On reconnect:
- reconcile authoritative message/run/card state
- do not duplicate stale error cards
- do not replay resolved approval UI as active
- restore current Agent live state

## Progressive disclosure

Default:
simple.

Expanded details:
- evidence
- watch transitions
- collaboration status
- tool activity
- execution quality
- decision replay

Do not force advanced internals on every user.

## Accessibility

Support:
- screen readers
- status labels
- keyboard navigation on Web
- adequate touch targets on Mobile
- RTL
- bidi isolation for symbols/prices/Agent names
- reduced-motion behavior where existing design supports it

## Visual consistency

Use the existing Lonora design system/components.
Do not create one-off cards with conflicting spacing, typography, or interaction patterns.

## Tests

Cover:
- Web/Mobile render same authoritative live state
- working indicator maps to real phase
- composer remains usable while work runs
- WAIT reason visible
- Guest Agent identity correct
- open Guest Agent chat preserves collaboration
- Super Bot active/paused/stopped states correct
- stale thesis card transitions to invalidated/expired
- manual trade event appears once through Personal Agent
- degraded broker/data state visible without spam
- approval card resolves in place
- chronological timeline preserved
- reconnect does not duplicate cards/errors
- mobile bottom-follow/keyboard behavior works
- RTL/mixed symbols/mentions render correctly
- Emergency Stop remains immediately reachable

## Definition of done

Lonora presents one simple, live, truthful trading experience across Web and Mobile: chat stays primary, real Agent/runtime state is visible, waiting is explainable, Guest Agents are clear, Super Bot is understandable, degraded conditions are obvious, and advanced evidence/details remain available through progressive disclosure rather than dashboard clutter.
