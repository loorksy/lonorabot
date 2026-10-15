PROJECT: Lonora (`loorksy/lonorabot`)

IMPORTANT:
- Implement, do not stop at an architecture report.
- Inspect the current repository before changing code. Do not assume conceptual names in this prompt already exist.
- Reuse existing Lonora primitives. Do not build a parallel runtime, event bus, broker ledger, or trading executor.
- Preserve Trading ON/OFF, Emergency Stop, ownership checks, authorization, risk controls, exact broker symbols, idempotency, journal, locking, and reconciliation.
- Never fabricate unavailable market, account, order-flow, execution, correlation, or performance data. Mark unavailable data as unavailable.
- Keep existing global model routing; do not introduce per-Agent provider/model selection.
- Keep Arabic-first/RTL compatibility.
- Do not mention paid API/token/key requirements.
- Work on a dedicated branch and add focused tests.


# 07 — Agent Mentions and Direct In-Thread Addressing

## Objective
Make `@Agent` a first-class optional way to address one or more real Lonora Agents inside the current conversation.

Natural-language addressing continues to work. `@mentions` are a precision shortcut, not a mandatory command language.

## Inspect first
The repo already contains mention parsing/candidate helpers and Web/Mobile composer support. Extend them rather than replacing the whole composer.

A committed mention must resolve to stable Agent identity, not only visible text.

## Required UX
Examples:
- `@eur-agent ...`
- `@eur-agent @macro-agent ...`
- `@lonora ...`
- `@all ...`

These are examples only; do not hardcode their text.

## Stable identity
Persist mention metadata using `agent_id` or the existing stable Agent id.

Agent rename must not break old stored mentions.
Autocomplete should show the current name.

## Autocomplete
Typing `@` shows eligible Agents with enough information to disambiguate:
- avatar
- name
- symbol/scope when relevant
- specialization if available
- paused/availability state if useful

Support touch/mobile/keyboard.

## Candidate scope
May include:
- current collaboration participants
- owner Agents eligible for direct collaboration
- Personal Agent

Never expose Agents from another owner.

## `@all`
`@all` means all participants in the current Collaboration Session only.

It must never silently mean every Agent in the owner's account.

If no session exists, do not silently wake all Agents.

## Routing
If mentioned Agent is already a participant, route message to it in the existing session.
If not participating, validate eligibility and invite/add it where appropriate.
Do not create duplicate participants.

## Multiple mentions
One user message may address multiple Agents.
Each receives the same user-authored request plus only relevant session context.
Responses remain attributable to each real Agent.

## Natural language still works
The user can also address an Agent conversationally without `@`.
Do not require mention syntax.

Parsing explicit `@` syntax is allowed; this is not the prohibited keyword-based task-control system.

## Guest response
Mentioned Agent may respond directly in current Thread with:
- real avatar/name
- participant marker
- its own message

Host identity remains unchanged.

## Navigation
From mention result or Guest message, user can open that Agent's own chat.
Do not lose active Collaboration Session.

## Permission safety
Mentioning grants no authority.

Any financial action still checks:
- owner/session
- Agent account/symbol scope
- Trading ON/OFF
- Emergency Stop
- approval/authorization
- risk
- idempotency/reconciliation

## Bidi/RTL
Support Arabic/RTL and mixed Arabic/Latin Agent names safely.
Mention rendering should preserve caret behavior and bidi isolation.

## Tests
Cover:
- `@` opens candidate list
- selecting stores stable Agent id
- rename does not break stored mention
- one mention targets one Agent
- multiple mentions target several
- `@all` targets current session only
- repeated mention does not duplicate participant
- Guest response uses real identity
- open Agent chat works
- natural-language addressing works without `@`
- mention does not grant permission
- cross-owner Agent cannot be mentioned
- Web/Mobile consistent
- RTL/mixed text correct

## Definition of done
`@Agent` is a polished optional direct-address feature backed by stable Agent identity, integrated with Collaboration Sessions, available on Web/Mobile, and unable to bypass permissions.
