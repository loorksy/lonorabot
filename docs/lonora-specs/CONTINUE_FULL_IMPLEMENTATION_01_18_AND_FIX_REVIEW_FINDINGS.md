TITLE:
Lonora — Fix Review Findings First, Then Continue Until Specifications 01–18 Are Fully Implemented and Verified

REPOSITORY:
loorksy/lonorabot

CURRENT INTEGRATION BRANCH:
feat/coherent-agent-foundations

CURRENT REVIEW CHECKPOINT:
Commit 1209f41 / PR #2 was reviewed as an integration checkpoint.

IMPORTANT:

Do NOT merge to main.

Continue working on the existing integration branch unless a new branch is technically necessary.

The current implementation is NOT considered complete.

Your job is now:

1. Fix the concrete review findings below first.
2. Re-run the relevant regression and safety tests.
3. Update the implementation matrix and progress documentation.
4. Continue implementing the remaining requirements across specifications 01 through 18.
5. Do not stop after the next feature or implementation wave.
6. Continue through successive integration waves until every requirement in specifications 01–18 is either VERIFIED or has a genuinely unavoidable concrete external blocker.
7. Do not ask for another instruction merely because one implementation wave finished.

The goal is completion of the entire 01–18 specification program, not another checkpoint.

==================================================
PART 1 — FIX THESE REVIEW FINDINGS FIRST
==================================================

These findings come from review of the current branch implementation.

Do not merely document them.

Inspect the relevant code, reproduce the problem where possible, implement a correct fix, add regression tests, and verify the fix.

--------------------------------------------------
FINDING 1 — WATCH CONFIRMATION TTL MUST USE THE
ACTUAL MARKET OBSERVATION TIME
--------------------------------------------------

Current area:

packages/market/src/lonora_market/watchers.py

packages/market/src/lonora_market/watch_lifecycle.py

The current watch evaluation path can pass evaluation `now` as the observation time used to calculate confirmation expiry.

This can incorrectly give old-but-delayed evidence a fresh confirmation lifetime.

Example:

Market evidence was observed earlier.

Processing happens later.

The confirmation TTL must NOT restart from processing time.

Required behavior:

Confirmation freshness/expiry must derive from the authoritative evidence timestamp.

Depending on the detector/input this may be:

- quote.observed_at
- candle time / actual candle-close evidence time
- detector Observation observed_at
- economic event observation/scheduled time where applicable
- another explicit source timestamp

Do not use worker processing time as a substitute for source observation time.

Processing time may still be stored separately.

Required invariant:

OLD EVIDENCE MUST NEVER BECOME NEW EVIDENCE JUST BECAUSE IT WAS PROCESSED LATE.

Add regression tests for:

- delayed quote observation
- delayed candle observation
- confirmation TTL
- already-stale confirmation
- restart/replay preserving the same expiry result

Live and replay evaluation must produce consistent lifecycle semantics.

--------------------------------------------------
FINDING 2 — ONE COLLABORATION SESSION MUST CREATE
AT MOST ONE HOST SYNTHESIS/FOLLOW-UP FOR A ROUND
--------------------------------------------------

Current area:

packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py

packages/db/src/lonora_db/collaboration.py

A collaboration may contain several Participant Agents.

When participant results arrive after the Host Run has already completed, the current outcome-return path may allow multiple child outcomes to independently create separate Host follow-up Runs.

Example:

Host asks:

Agent A
Agent B
Agent C

All three complete.

The system must NOT create:

Host follow-up #1
Host follow-up #2
Host follow-up #3

for the same collaboration synthesis round.

Required behavior:

Participant results are accumulated into the durable Collaboration Session.

When the session reaches a state requiring synthesis, schedule exactly ONE synthesis/follow-up Run for that session/round.

Use a durable idempotent identity/receipt.

The synthesis Run must be able to inspect all available participant outcomes.

If another participant finishes after synthesis was already scheduled:

- update the session evidence/state
- do not create another duplicate synthesis Run unless a deliberate new bounded collaboration round is required

Do not solve this with an in-memory boolean.

It must survive:

- retries
- process restart
- duplicate outcome delivery
- concurrent participant completion

Also guarantee that duplicate synthesis cannot lead to duplicate downstream financial action.

Add concurrency/idempotency regression tests with several participants finishing nearly simultaneously.

--------------------------------------------------
FINDING 3 — CANCELLED TASK MUST NOT ALSO APPEAR
AS FAILED
--------------------------------------------------

Current area:

packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py

packages/db/src/lonora_db/tasks.py

Current completion propagation can produce conflicting representations such as:

TaskState.status = cancelled

while:

Ticket payload status = failed

Required behavior:

There must be one consistent task outcome.

At minimum:

Run completed
→ Task completed
→ public/internal task outcome completed

Run failed
→ Task failed

Run cancelled
→ Task cancelled

Do not map cancellation to failure.

Audit all:

- snapshots
- task APIs
- Agent live state
- Web
- Mobile
- background outcome return
- retry/resume logic
- notification/attention consumers

for assumptions about the old status.

Add regression tests ensuring a cancelled task never reappears as failed after:

- outcome return
- restart
- API read
- Web projection
- Mobile projection

--------------------------------------------------
FINDING 4 — CHILD AGENTS CREATED FROM THE PERSONAL
AGENT MUST NOT BECOME UNSCOPED FINANCIAL ACTORS
--------------------------------------------------

Current areas:

packages/agent-runtime/src/lonora_agent/collaboration/child_agents.py

packages/db/src/lonora_db/agents.py

packages/db/src/lonora_db/agent_binding.py

The Personal Agent intentionally has broad owner-account/all-market visibility.

That broad visibility is NOT a delegable financial scope.

Currently a child created from the Personal Agent can inherit:

trading_account_id = None
trading_symbol = None

and become a legacy/unbound Agent.

This must not create a financial scope loophole.

Required architecture:

Personal Agent:
- broad visibility
- explicit special role

Specialized trading Agent:
- exact account
- exact broker symbol

Temporary/research child/subagent:
- bounded delegated task
- no implicit broad financial mutation authority

A child of the Personal Agent must NOT become a second Personal Agent and must NOT gain unrestricted financial execution merely because its binding fields are empty.

Choose the cleanest explicit representation that fits the current architecture.

Possible solution direction:

Introduce/retain a clear non-financial delegated scope or explicit read-only authority for such children.

Do not force a fake symbol binding merely to satisfy the schema.

Required invariant:

PERSONAL VISIBILITY MUST NOT BE TRANSITIVELY DELEGATED AS FINANCIAL AUTHORITY.

Also audit:

assert_market_binding()

and all code paths that currently treat:

account_id is None
and
trading_symbol is None

as unrestricted legacy behavior.

Preserve required backward compatibility where genuinely necessary, but do not allow new child Agents to enter an ambiguous unrestricted scope.

Add tests for:

- Personal Agent creates child
- child can perform allowed research/read-only work
- child cannot mutate arbitrary broker markets
- child cannot bypass execution scope through a descendant
- specialist child retains exact inherited binding
- collaboration does not transfer financial authority

--------------------------------------------------
FINDING 5 — DO NOT REUSE AN UNRELATED ACTIVE
COLLABORATION SESSION
--------------------------------------------------

Current area:

packages/db/src/lonora_db/collaboration.py

The current active-session lookup is primarily based on:

owner
thread
active status

This can accidentally attach a new unrelated collaboration request to an older still-active session.

Required behavior:

Distinguish explicitly between:

CONTINUE EXISTING COLLABORATION

and:

START A NEW COLLABORATION

A new user objective must not silently inherit an unrelated prior collaboration merely because the same Thread contains an active session.

Use durable identifiers / host request lineage / explicit session relationship.

At minimum, session continuation should be associated with the correct:

- collaboration id
- originating user message/request
- Host Run / bounded round
- subject/objective identity

`@all` inside an existing collaboration must continue to address only that collaboration's participants.

A new collaboration request must receive a new session when it represents a different objective.

Add tests for:

- two unrelated collaborations in one Thread
- explicit continuation of first session
- `@all` targets correct session
- second request does not append to first
- retries do not duplicate either session

==================================================
PART 2 — REVIEW THE FIXES AS A CONNECTED SYSTEM
==================================================

After fixing the five findings:

Run a cross-feature review.

Specifically check interactions between:

Task lifecycle
Collaboration lifecycle
Agent scope
Personal Agent
Guest Agents
Market Watch lifecycle
Historical decisions
Execution-quality gate
Manual broker activity
Broker recovery
Live Agent state
Web/Mobile timeline

Do not fix each issue locally while leaving contradictory behavior elsewhere.

==================================================
PART 3 — CONTINUE THE ENTIRE 01–18 PROGRAM
==================================================

After review findings are fixed, continue implementation.

DO NOT STOP.

All files under:

docs/lonora-specs/

01 through 18

remain authoritative implementation references.

Do not implement them sequentially by filename.

Continue to use dependency-aware vertical capability waves.

==================================================
CURRENT KNOWN OPEN AREAS
==================================================

According to the current progress checkpoint, important remaining work includes, but is not limited to:

- complete thesis identity and lifecycle
- opportunity memory
- thesis expiry and decay
- market phase/regime transition intelligence
- confirmation-to-thesis linkage
- automatic capture of meaningful financial decisions
- complete historical evidence/version snapshots
- Shadow Trading lifecycle
- virtual entry/management/exit tracking
- trading performance intelligence
- analysis quality
- entry quality
- management quality
- execution quality attribution
- recurring trading error analysis
- setup/playbook performance history
- measured cross-market relationship intelligence
- changing-correlation detection
- intelligent attention policy
- notification deduplication/coalescing
- meaningful proactive notifications
- complete collaboration evidence fusion
- bounded conflict-resolution rounds
- fresh final collaboration market revalidation
- Super Bot activation proposal
- trusted device authorization
- single-use/replay-safe activation
- authority expansion re-authentication
- full Super Bot permission envelope
- task retry/recovery policy
- dependent Web/Mobile UX
- unified live state acceptance
- voice/trading continuity acceptance
- end-to-end recovery acceptance

This list is NOT a substitute for the specification matrix.

Read all source requirements.

==================================================
THESIS / OPPORTUNITY WORK
==================================================

Continue using the shared evidence foundation already implemented.

Do NOT create a separate evidence database or second market state engine.

A durable opportunity/thesis must preserve:

- exact account/symbol
- originating evidence/watch
- created time
- status
- versions
- supporting evidence
- contradicting evidence
- last validation time
- expiry/invalidation reason
- transition history

Required semantics include:

FORMING
CONFIRMED
DEGRADED
INVALIDATED
EXPIRED

where appropriate.

A thesis can expire even if Stop Loss was never reached.

Fresh evidence always wins over remembered thesis state.

==================================================
SHADOW TRADING
==================================================

Implement the full specification.

Critical invariant:

SHADOW MODE MUST NEVER SEND A BROKER MUTATION.

It must use real market evidence but virtual execution.

Track:

- what Lonora would have done
- virtual entry
- stop/targets
- management decisions
- virtual exit/outcome
- strategy/detector version
- real-vs-shadow identity

Never silently combine shadow and live performance statistics.

Shadow success must never automatically enable live autonomy.

==================================================
PERFORMANCE INTELLIGENCE
==================================================

Build on actual recorded decisions and outcomes.

Separate:

analysis quality

entry quality

management quality

execution quality

Do not equate profit with correctness.

Detect recurring patterns only from meaningful samples.

Do not silently self-modify hard rules or financial safety controls.

==================================================
CROSS-MARKET INTELLIGENCE
==================================================

Implement measured, time-aligned relationship analysis where actual data exists.

Do not hardcode permanent correlation truths.

Represent:

stable

weakening

breaking

inverted

unreliable

unavailable

or equivalent typed states.

Correlation is evidence.

It is not causation and not a direct trade command.

==================================================
ATTENTION / NOTIFICATION ENGINE
==================================================

Separate:

runtime event

from:

owner notification

Implement:

importance

ownership

deduplication

coalescing

state-transition awareness

silence when nothing materially changed

critical/action-required delivery

One logical event should not spam the owner through several Agents.

==================================================
COLLABORATION COMPLETION
==================================================

Finish:

structured participant evidence

evidence provenance

conflict tracking

bounded re-analysis

no majority voting

final evidence fusion

market revalidation

one unified result

Guest Agent identity

session persistence

cross-thread navigation

permission isolation

Collaboration shares evidence, not financial authority.

==================================================
SUPER BOT AUTHORIZATION
==================================================

Implement the original specification fully.

Natural-language request creates a proposal.

It must NOT directly enable autonomy.

Use the same in-chat activation UX.

Sensitive authority requires trusted owner/device confirmation where supported.

The server is authoritative.

Required properties include:

- exact permission envelope
- owner identity
- Agent identity
- allowed account/market scope
- replay protection
- one-time challenge semantics
- expiry
- re-authentication when expanding authority
- easy reduction/revocation
- Emergency Stop never requires authentication to stop

Never store raw biometric/PIN/pattern information.

Do not invent an authentication mechanism unsupported by the platform.

==================================================
TASK RUNTIME COMPLETION
==================================================

Finish the long-running Task specification.

Required remaining behavior includes:

- durable retry policy
- recovery after worker/process failure
- retry backoff where appropriate
- no duplicate side effects
- checkpoint resume
- pause/resume/cancel correctness
- conversational steering
- truthful status
- concurrent conversation lane
- work lane
- side-effect-aware recovery

Do not create a second scheduler.

==================================================
WEB / MOBILE / VOICE
==================================================

Complete the dependent UX.

All clients consume authoritative shared state.

No separate fake client intelligence.

Verify:

- bottom-follow behavior
- keyboard-safe composer
- reconnect reconciliation
- latest meaningful inbox
- approval lifecycle in place
- live Agent state
- task state
- Guest Agents
- mentions
- Super Bot state
- thesis/opportunity state
- degraded broker/market state
- manual trade monitoring
- notifications
- decision replay

Voice must use the same Agent / Thread / Tasks / Super Bot / Collaboration state.

Partial speech must not trigger financial execution.

==================================================
NATIVE ANDROID
==================================================

Native Android validation is currently an external/environmental blocker if no emulator/device is available.

Do not falsely mark it VERIFIED.

Continue implementing everything that can be implemented/tested without the physical runtime.

Maintain explicit status:

BLOCKED: native Android acceptance requires actual Android runtime

until it is genuinely executed.

Do not block all other work because Android hardware is absent.

==================================================
REMOTE CI
==================================================

GitHub Actions currently cannot run because of the external GitHub account/billing lock.

Do not treat this as passing CI.

Do not attempt to change billing/account settings.

Continue running the complete local validation suite.

Record:

REMOTE_CI_BLOCKED_EXTERNAL

separately from:

LOCAL_TESTS_PASSING

==================================================
IMPLEMENTATION MATRIX IS AUTHORITATIVE FOR PROGRESS
==================================================

Continuously update:

docs/lonora-specs/IMPLEMENTATION_MATRIX.md

docs/lonora-specs/DEPENDENCY_GRAPH.md

docs/lonora-specs/PROGRESS.md

Do not use vague statements like:

"mostly done"

"foundation complete"

for final acceptance.

Every source requirement must end as one of:

VERIFIED

BLOCKED WITH A CONCRETE EXTERNAL BLOCKER

DEFERRED WITH AN EXPLICIT TECHNICAL REASON

However:

Do not defer something merely because it is difficult.

Implement everything possible in the repository.

==================================================
DO NOT STOP AT A CHECKPOINT
==================================================

This instruction is important.

After completing:

thesis work

DO NOT STOP.

Continue to:

shadow/performance.

After shadow/performance:

DO NOT STOP.

Continue to:

notifications / cross-market / collaboration completion.

After that:

DO NOT STOP.

Continue to:

Super Bot authorization / task recovery / UI / voice.

After another integration wave:

DO NOT ask:

"Should I continue?"

Continue automatically.

Only stop for:

1. a genuine external blocker that prevents further repository work,

or

2. complete implementation and verification of every implementable requirement across specifications 01–18.

==================================================
SHORT INTEGRATION LOOPS
==================================================

Continue using short integration waves:

implement shared capability
→ integrate
→ test
→ inspect for duplication
→ update matrix
→ continue

Do not build several isolated giant branches and attempt one huge merge later.

==================================================
REGRESSION SAFETY
==================================================

At every integration wave preserve:

Personal Agent uniqueness

specialist exact-symbol binding

Trading ON/OFF

Emergency Stop

trade approval semantics

Super Bot authority boundaries

operation idempotency

no blind retry

broker reconciliation

owner intervention precedence

health gating

no stale recommendation

no evidence = no recommendation

no LLM-per-tick

global model routing

bounded context

collaboration permission isolation

==================================================
TESTING
==================================================

Continue expanding tests as capabilities are implemented.

Run relevant:

Python unit/integration tests

PostgreSQL integration tests

Node tests

Web browser tests

Expo Web tests

Ruff

Pyright

client lint/type checks

build/export

existing broker/recovery/chart/trading suites

simulation and replay tests

Never use live-money automated testing.

==================================================
FINAL ACCEPTANCE REVIEW
==================================================

When implementation is actually complete, perform one complete cross-spec audit against all 18 original specification files.

Check every requirement.

Do not trust only the progress notes.

Re-open the original specification sections and verify behavior.

Also review for:

duplicate contracts

duplicate state machines

parallel orchestration systems

legacy bypasses

scope loopholes

race conditions

duplicate Agent notifications

duplicate financial execution paths

stale evidence

hindsight leakage

unbounded context

unbounded collaboration loops

unsafe retries

Web/Mobile semantic divergence

==================================================
FINAL COMPLETION CONDITION
==================================================

Do NOT declare the program complete until:

- all implementable requirements in specifications 01–18 are VERIFIED
- all relevant local tests pass
- migrations are consistent
- no known safety-critical review finding remains open
- integration matrix is updated
- dependency graph reflects final architecture
- progress document contains final status
- outstanding external blockers are explicitly listed
- no requirement is silently omitted

External Android-device acceptance and externally blocked GitHub Actions may remain explicitly BLOCKED if the environment truly cannot provide them.

Those external blockers do not justify leaving unrelated repository implementation unfinished.

==================================================
FINAL REPORT
==================================================

At true completion provide:

Branch

Final HEAD commit

PR

Commit groups

Migrations

Implemented shared foundations

Capabilities completed

Specifications 01–18 verification summary

Tests passed

Regression suites passed

Safety review

Remaining external blockers only

Any genuinely deferred item and concrete reason

Do not produce an interim completion message as if the entire program were done.

==================================================
MOST IMPORTANT INSTRUCTION
==================================================

Fix the five review findings first.

Then continue.

Do not stop at the next milestone.

Do not wait for another user message after each wave.

Continue dependency-aware implementation, integration, testing and review until the full Lonora specification set 01–18 is implemented and verified as far as the repository/environment technically allows.