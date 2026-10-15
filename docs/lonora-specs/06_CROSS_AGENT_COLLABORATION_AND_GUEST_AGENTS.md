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


# 06 — Cross-Agent Collaboration and In-Thread Guest Agents

## Objective
Extend Lonora's existing peer/collaboration primitives into a durable Agent Collaboration Session.

The Host Agent owns the current conversation and coordinates the session. It is not a superior manager. Participant Agents remain independent specialists with their own identity, scope, and permissions.

## Inspect first
The current repo already contains peer-triggered Runs, peer delegation, collaboration permission checks, returned peer outcomes/follow-ups, and collaboration UI markers.

Extend these primitives instead of creating a second multi-Agent runtime.

## When collaboration is useful
Resolve semantically from context, not fixed user phrases.

Examples:
- requested symbol is outside Host scope
- another Agent has relevant specialization
- user asks to compare markets
- user wants several Agents to review one setup
- Personal Agent account-wide context is needed

## Agent discovery
Use structured facts:
- owner
- exact account/symbol binding
- capabilities/specialization metadata that actually exists
- paused/available state
- relevant workload if the current runtime exposes it
- permission compatibility

Never discover Agents because their display name contains "EUR", "Gold", etc.

## Participant selection
Choose the smallest useful participant set.
Do not wake every matching Agent by default.
If the owner explicitly asks all relevant Agents to participate, include all eligible matches.

No specialist → Personal Agent fallback where appropriate.

## Agent Collaboration Session
Persist a session only if current peer primitives cannot represent the required semantics cleanly.

It must support:
- stable session id
- owner
- Host Agent
- origin/current Thread relationship
- user request/subject
- exact symbol(s) when relevant
- participants
- session status
- structured shared evidence
- participant outcomes
- final result
- timestamps

Lifecycle semantics:
CREATED → DISCOVERING → SELECTING → COLLABORATING → SYNTHESIZING → REVALIDATING → COMPLETED
with WAITING / FAILED / CANCELLED / EXPIRED when needed.

Use project naming conventions rather than forcing these exact strings.

## Host Agent responsibilities
- understand request
- discover/select participants
- open/coordinate session
- share only relevant context
- stay responsive to user
- inspect participant status
- receive outcomes
- expose material conflicts
- request bounded re-analysis when needed
- revalidate current market before a time-sensitive final recommendation
- present final result in current chat

Host must not:
- invent participant output
- rewrite another Agent's evidence
- hide material disagreement
- transfer permissions
- execute outside its own authority because it hosted the session

## Participant responsibilities
- keep real identity
- keep real scope/permissions
- receive minimal relevant context
- perform requested contribution
- return structured evidence/outcome
- optionally speak directly in Host Thread as a Guest Agent

Do not share the Host's full memory/history by default.

## Participant state
Track enough to represent:
INVITED / WORKING / WAITING / RESPONDED / COMPLETED / FAILED / CANCELLED/LEFT.

Host can answer status without waiting for all participants.

## Shared evidence
Share structured evidence, not unrestricted memory.

Preserve provenance:
- evidence id
- source Agent
- source tool/data source when available
- symbol/timeframe
- observed_at
- finding/value
- freshness
- quality/confidence semantics already used by Lonora

## Evidence fusion, not voting
Never implement "2 BUY vs 1 SELL = BUY".

Final result uses:
- supporting evidence
- contradicting evidence
- freshness/quality
- unresolved conflicts
- market/account constraints
- trading recommendation rules

WAIT is valid even if most participants lean BUY/SELL.

## Conflict handling
When participants disagree:
- store the conflict
- identify conflicting evidence
- optionally share relevant conflicting evidence back
- allow a bounded re-analysis round
- mark conflict resolved/unresolved

No endless debate loop.

## Final market revalidation
Before time-sensitive recommendation:
- refresh quote
- refresh spread if available
- refresh relevant candle/watch state
- check freshness
- include account exposure when relevant
- verify thesis still applies

If stale/invalidated → reassess or WAIT.

## Guest Agents in same chat
A participant may appear directly in Host Thread:
- own avatar
- own name
- participant/guest marker
- actual message attributable to that Agent

Host must not impersonate participant.

Provide action to open the participant's own chat.
Changing Thread must not destroy the Collaboration Session.

## Conversation remains live
While collaboration runs:
- user keeps chatting
- Host can answer status
- user can ask participant follow-up
- request can be adjusted
- participants can continue

Do not freeze composer.

## Failure
One participant failure does not automatically fail session.
Optional evidence → continue and disclose gap.
Essential evidence → replace participant, wait, or return WAIT/insufficient evidence.
Never fabricate missing contribution.

## Permission isolation
Collaboration shares evidence, never authority.
No Agent gains another Agent's:
- symbol scope
- account authority
- Super Bot authority
- approval state

Execution after recommendation still requires an independently authorized execution path.

## Tests
Cover:
- out-of-scope Host discovers specialist
- discovery uses metadata, not name parsing
- Personal Agent fallback
- multiple specialists can participate
- Host remains responsive
- participant status inspectable
- evidence provenance preserved
- Guest Agent appears as itself
- jump to participant Thread preserves session
- participant failure does not fabricate evidence
- conflict retained/re-analyzed
- no majority-vote logic
- final market revalidation
- stale thesis yields reassess/WAIT
- no permission transfer
- no duplicate financial execution

## Definition of done
One Agent can bring the right other Agents into one durable session, show them as real Guest Agents in the same chat, share evidence with provenance, resolve disagreement, revalidate the market, and return one evidence-based result without sharing permissions.
