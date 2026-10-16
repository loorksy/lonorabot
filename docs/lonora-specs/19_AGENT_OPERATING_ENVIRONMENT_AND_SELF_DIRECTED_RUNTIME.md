TITLE:
19_AGENT_OPERATING_ENVIRONMENT_AND_SELF_DIRECTED_RUNTIME

PROJECT:
Lonora

REPOSITORY:
loorksy/lonorabot

PRIMARY REFERENCE IMPLEMENTATION:
https://github.com/HKUDS/nanobot

STATUS:
Production implementation specification.

This is NOT an architecture-only exercise.

Inspect the current repository first, study Nanobot deeply, design the smallest coherent extension of Lonora's existing architecture, implement it, migrate where required, add tests, run validation, and integrate the capability into the existing Agent/Gateway/Run/Task/Tool/Voice infrastructure.

Do NOT merge to main unless explicitly instructed.

==================================================
1. PURPOSE
==================================================

Lonora must stop behaving like:

user message
→ model
→ one tool call
→ tool error
→ tell user the error
→ wait for another user message

Lonora must behave like a persistent self-directed Agent:

owner goal
→ understand the goal
→ inspect its environment
→ determine the next action
→ validate the action
→ execute
→ observe the result
→ persist progress
→ diagnose failures
→ repair/recover when possible
→ continue automatically
→ wait durably when necessary
→ wake on the relevant event
→ verify completion
→ return to the owner only when appropriate

The fundamental rule is:

THE OWNER PROVIDES THE GOAL.
LONORA MANAGES THE PATH.

The owner must not be required to operate Lonora's tools manually.

==================================================
2. THIS IS A CORE RUNTIME CAPABILITY
==================================================

This specification is foundational.

It applies to:

- normal conversation
- long-running tasks
- trading analysis
- Super Bot
- market monitoring
- watches
- routines
- collaboration
- subagents
- voice
- broker recovery
- research
- charts
- memory
- persistent goals
- notifications
- background work

Do not implement this as a trading-only feature.

Lonora remains a persistent general Agent system with native market/trading capabilities.

==================================================
3. DO NOT BUILD A SECOND AGENT RUNTIME
==================================================

Before implementing anything, audit and reuse the existing Lonora architecture.

Known existing primitives include, but are not limited to:

- AgentRuntime
- existing Gateway / resident worker
- Run leases and fencing
- Task/Run infrastructure
- ToolLoop
- ToolRegistry
- global ModelRouter
- existing Threads
- existing Messages
- existing steering
- checkpoints
- tickets/tasks
- routines
- watches
- market wakeups
- broker recovery
- existing event ledger
- EffectReceipt/idempotency mechanisms
- memory
- collaboration/peer runs
- subagents
- existing voice path
- trading journal
- execution/reconciliation
- live Agent state

Do not create parallel versions of these systems.

The new Agent Operating Environment must connect and strengthen the existing runtime.

Prefer:

extend existing primitive
→ make it coherent
→ reuse across capabilities

over:

create new subsystem beside it.

Do not introduce a second:

- scheduler
- event bus
- Run engine
- Task engine
- Agent runtime
- memory engine
- tool registry
- Gateway
- conversation engine
- broker ledger
- collaboration runtime

without an exceptionally strong technical reason and a clean migration plan.

==================================================
4. NANOBOT IS A PRIMARY ENGINEERING REFERENCE
==================================================

Primary reference:

https://github.com/HKUDS/nanobot

Nanobot must be studied deeply.

Do NOT inspect only its README.

Do NOT merely copy a diagram.

Do NOT treat it as superficial inspiration.

Study the actual repository, source code, tests, runtime entry points, persistence model and execution flows.

The objective is to understand how a coherent persistent Agent system operates end-to-end and apply the relevant lessons to Lonora.

Study everything useful.

At minimum inspect Nanobot's implementation of:

- Agent loop
- request admission
- context construction
- context management
- conversation/session state
- persistent memory
- memory retrieval
- memory updates
- learning/persistent knowledge
- tool registration
- tool schemas
- tool invocation
- tool-result return
- failure handling
- retry behavior
- continuation after failure
- task/workflow handling
- persistent work
- long-horizon goals
- background execution
- scheduled work
- Agent wakeups
- Gateway/runtime lifecycle
- restart behavior
- recovery
- channels
- multi-channel Agent continuity
- subagents
- multi-Agent delegation
- subagent result return
- MCP
- automation
- state persistence
- event processing
- permissions
- production entry points
- observability
- tests

Do not stop at this list.

If Nanobot contains any relevant mechanism, abstraction, lifecycle, pattern, state machine or recovery technique, study it.

==================================================
5. REQUIRED NANOBOT ARCHITECTURE STUDY
==================================================

Create:

docs/lonora-specs/NANOBOT_ARCHITECTURE_STUDY.md

This must be based on actual Nanobot source code.

For every relevant Nanobot subsystem record:

- actual Nanobot component/module
- responsibility
- real execution behavior
- persistent state involved
- lifecycle
- failure/recovery behavior
- why the design is useful
- Lonora's current equivalent, if any
- whether Lonora is weaker/equivalent/stronger
- what should be adopted conceptually
- what should be adapted
- what should not be imported
- which Lonora subsystem should own the equivalent behavior

Trace real execution paths.

Trace at least:

USER REQUEST:

channel
→ session/thread
→ Agent
→ context
→ model
→ tool
→ result
→ next Agent turn
→ persistence
→ completion

BACKGROUND WORK:

event
→ wake
→ Agent/Task
→ execution
→ state update
→ wait
→ wake
→ continue

FAILURE:

tool/runtime failure
→ error representation
→ diagnosis
→ recovery/alternate action
→ continuation

RESTART:

work running
→ process stops
→ process returns
→ durable state loaded
→ external state revalidated
→ safe continuation

SUBAGENT:

parent need
→ delegation
→ bounded child context
→ child work
→ child result
→ result returned
→ parent continuation

Do not finalize this specification without completing this study.

==================================================
6. LEARN FROM NANOBOT, DO NOT BLINDLY CLONE IT
==================================================

Nanobot is a trusted primary reference for Agent-system coherence.

It is not permission to replace Lonora wholesale.

For every Nanobot mechanism:

first inspect whether Lonora already has an equivalent.

If Lonora's implementation is stronger, retain it.

If Nanobot demonstrates a missing concept, integrate that concept into Lonora coherently.

Do not copy architectural weaknesses merely because they exist upstream.

Trading-specific safety in Lonora is intentionally stronger and remains authoritative.

If actual source code is copied or substantially adapted:

- inspect the Nanobot license
- preserve required attribution
- preserve copyright notices where required
- update THIRD_PARTY_NOTICES or repository equivalent
- document material direct reuse

Prefer architectural understanding and native Lonora implementation unless direct reuse is technically superior.

==================================================
7. THE LONORA AGENT LOOP
==================================================

Implement or refactor Lonora so that its fundamental persistent loop is conceptually:

EVENT / OWNER INPUT
↓
UNDERSTAND
↓
LOAD DURABLE STATE
↓
BUILD BOUNDED CONTEXT
↓
DETERMINE NEXT ACTION
↓
VALIDATE ACTION
↓
EXECUTE
↓
OBSERVE RESULT
↓
CLASSIFY RESULT
↓
PERSIST PROGRESS
↓
DECIDE NEXT STATE

Possible next states:

CONTINUE
WAIT
RETRY
RECOVER
DELEGATE
ASK_OWNER
COMPLETE
FAIL_TERMINAL

The loop must be resumable.

The loop must not exist only in model memory.

Important execution state must be durable.

==================================================
8. UNDERSTAND THE EVENT IN CONTEXT
==================================================

An Agent invocation may originate from:

- user text
- finalized voice input
- steering while a Task is running
- watch confirmation
- market event
- broker event
- routine
- webhook
- scheduled work
- collaboration result
- subagent result
- recovery
- reconnect
- Task resume
- external state change

The Agent must understand whether the new input is:

- a new goal
- continuation of an existing goal
- steering of active work
- cancellation
- revision
- status request
- answer to a requested question
- external observation
- background wakeup

Do not implement semantic understanding through keyword/synonym/magic-phrase routing.

Natural-language semantics must come from contextual model understanding and typed intent/state.

Explicit syntaxes such as stable `@agent` mentions may be parsed deterministically.

==================================================
9. DURABLE ACTIVE WORK STATE
==================================================

A user request that requires work must become durable work state.

The Agent must not depend on remembering its task only inside the current model turn.

For active work, the system must be able to recover:

- objective
- Agent identity
- origin Thread
- work Thread where appropriate
- Task identity
- current Run attempt
- current phase
- plan revision
- completed steps
- pending steps
- current wait condition
- tool attempts
- meaningful tool results
- last successful checkpoint
- current external dependencies
- recent recoverable errors
- side-effect state
- required authorization
- related watch/goal/collaboration/subagent identities
- next safe action

Use the existing Task/Run/Ticket/checkpoint primitives where possible.

Do not invent a disconnected workflow engine.

==================================================
10. USER REQUEST != SINGLE MODEL TURN
==================================================

One user request may require many internal turns.

Example:

Owner:

"Analyze gold."

Correct behavior:

understand request
→ resolve exact authorized symbol
→ inspect broker/market health
→ retrieve quote
→ retrieve candles
→ inspect relevant timeframes
→ inspect relevant account state
→ calculate deterministic indicators
→ analyze structure
→ evaluate contradicting evidence
→ validate freshness
→ create recommendation
→ verify evidence is still fresh
→ answer owner

This may require many model/tool cycles.

The user must not need to manually say:

"continue"

"try again"

"now get candles"

"retry"

"inspect the other tool"

unless owner input is genuinely required.

==================================================
11. TOOL FAILURE IS USUALLY AN OBSERVATION,
NOT TASK COMPLETION
==================================================

A tool failure usually means:

the Agent learned something about its environment.

It does NOT automatically mean:

the owner's goal failed.

Example:

tool
→ error
→ classify
→ determine whether recoverable
→ repair
→ retry safely
→ choose alternate route
→ continue

Do not immediately expose every internal tool failure to the user.

==================================================
12. STRUCTURED TOOL ENVIRONMENT
==================================================

Lonora must understand its available environment.

The Agent/runtime must have structured access to tool metadata including, where possible:

- tool identifier
- purpose
- input schema
- output contract
- capability
- side-effect class
- required scope
- authorization requirements
- common typed error codes
- whether retry is safe
- whether operation is idempotent
- whether operation may mutate external state
- whether external reconciliation is required after uncertainty
- result-size behavior
- pagination/bounded-read options where relevant

Reuse ToolRegistry and existing contracts.

Do not maintain tool behavior as hidden hardcoded prompt prose when structured metadata can represent it.

==================================================
13. VALIDATE TOOL CALLS BEFORE EXECUTION
==================================================

Where practical:

model proposes tool call
→ validate arguments against the actual schema
→ normalize only safe deterministic fields
→ reject or repair invalid calls
→ execute

The Agent must be able to inspect the real tool schema after argument failures.

Example:

goal_create
→ tool_arguments_invalid

The Agent must NOT respond to the user:

"Tell me to try again."

Instead:

inspect actual schema
→ inspect current goal requirements
→ identify invalid/missing field
→ rebuild request
→ validate
→ retry

Only ask the owner if required information truly cannot be obtained.

==================================================
14. ERROR CLASSIFICATION
==================================================

Implement a coherent typed error classification/recovery layer.

Do not rely solely on free-form model interpretation.

Useful categories may include equivalents of:

INVALID_INPUT
INVALID_TOOL_ARGUMENTS
RESULT_TOO_LARGE
TEMPORARY_UNAVAILABLE
CONNECTION_FAILURE
STALE_STATE
VERSION_CONFLICT
MISSING_CAPABILITY
NOT_CONFIGURED
NOT_FOUND
HEALTH_BLOCKED
AUTHORIZATION_REQUIRED
PERMISSION_DENIED
EXTERNAL_WAIT
AMBIGUOUS_MUTATION
TERMINAL_DOMAIN_FAILURE

Adapt naming to existing Lonora contracts.

Do not create duplicate error representations when existing stable error codes already serve the purpose.

==================================================
15. RECOVERY EXAMPLES
==================================================

INVALID TOOL ARGUMENTS:

tool_arguments_invalid
↓
inspect tool contract
↓
identify invalid field
↓
repair arguments
↓
validate
↓
retry

--------------------------------------------

RESULT TOO LARGE:

tool_result_too_large
↓
do not abandon task
↓
narrow query / paginate / request bounded subset
↓
retrieve only relevant information
↓
continue

--------------------------------------------

MISSING CHART INDICATOR:

chart_indicator_not_found
↓
inspect chart
↓
determine whether indicator must be added
↓
add/read or choose equivalent data source
↓
continue

--------------------------------------------

BROKER CONNECTION FAILURE:

broker_connection_timeout
↓
inspect authoritative broker recovery state
↓
attempt safe reconnect/reconciliation using existing recovery system
↓
verify connection
↓
retry safe reads
↓
continue

Do not blindly retry a financial mutation.

--------------------------------------------

STALE MARKET DATA:

stale evidence
↓
retrieve fresh evidence
↓
re-evaluate thesis/recommendation
↓
continue or WAIT

--------------------------------------------

VERSION CONFLICT:

authoritative state changed
↓
reload latest state
↓
reconsider intended action
↓
continue only if still valid

--------------------------------------------

AMBIGUOUS FINANCIAL MUTATION:

send may have occurred
↓
DO NOT RESEND
↓
reconcile with broker
↓
resolve exact outcome
↓
continue

==================================================
16. RETRY POLICY
==================================================

Retries must be deliberate.

Do not create uncontrolled retry loops.

Retry decisions must consider:

- error classification
- operation side effect
- prior attempts
- idempotency
- elapsed time
- state version
- external system health
- whether the world may have changed

Use bounded attempts and backoff where appropriate.

Persist enough retry state so a restart does not reset an unsafe retry loop.

==================================================
17. LOOP / FAILURE ESCAPE PROTECTION
==================================================

Prevent:

same tool
→ same arguments
→ same error
→ same tool
→ same arguments
→ same error forever

Track meaningful failure signatures.

The Agent should know when a route has already failed.

After repeated equivalent failure:

- change strategy
- inspect deeper state
- choose alternate tool/path
- wait for external recovery
- or escalate appropriately

Do not waste model calls repeating identical failures.

==================================================
18. WHEN TO INVOLVE THE OWNER
==================================================

The Agent should ask the owner only when the owner is genuinely required.

Good reasons include:

- financial approval required
- Super Bot authority grant/expansion
- missing personal choice
- true semantic ambiguity affecting outcome
- unavailable required information that only owner can provide
- sensitive authorization
- irreversible decision requiring owner confirmation
- genuine external blocker

Bad reasons include:

- malformed tool arguments
- internal schema misunderstanding
- result too large
- needing pagination
- safe read retry
- selecting a different internal tool
- determining the bound broker symbol
- discovering existing account identity
- recovering an internal connection
- parsing the Agent's own previous tool result

Internal technical failures are generally Lonora's responsibility.

==================================================
19. OWNER-FACING ERROR TRUTHFULNESS
==================================================

If Lonora understood the request but failed during execution, never say:

"I did not understand your request."

Example:

Owner:
"Analyze gold."

Tool later fails.

Wrong:

"I didn't understand. Please repeat."

Correct:

"I understood the gold analysis request. Market data is currently unavailable, and recovery attempts did not restore it yet."

Separate:

UNDERSTANDING FAILURE

from:

EXECUTION FAILURE.

==================================================
20. TEXT AND VOICE ARE CHANNELS TO THE SAME AGENT
==================================================

This is a critical requirement.

VOICE MUST NOT BE A SECOND AGENT.

Do NOT build:

Chat Agent
Voice Agent
Trading Agent

Build:

ONE LONORA AGENT
+
multiple channels.

Voice is only:

- microphone input
- speech recognition
- turn detection
- interruption/barge-in
- spoken output
- realtime transport

Agent reasoning, memory, Tasks, tools and state remain in the same Agent runtime.

Voice and text must share:

- Agent identity
- owner identity
- Thread
- durable Task
- active Goal
- memory
- Run state
- tools
- market state
- broker state
- collaboration
- watches
- Super Bot authority
- approvals
- decision history

==================================================
21. VOICE TASK CONTINUITY
==================================================

Example:

Owner by voice:

"Analyze gold."

Lonora:

"Okay, I'll analyze gold now."

This spoken acknowledgement must NOT complete the Task.

Internally:

Task: analyze gold
status: running

Lonora continues working.

If the owner says nothing for 30 seconds:

the Task still exists.

If the owner asks:

"Where did you get to?"

Lonora reads the actual Task state and responds accurately.

Example:

"I have the current quote and one-minute candles. I'm checking the 15-minute structure now."

Do not fabricate progress.

==================================================
22. VOICE STEERING
==================================================

During active work:

Lonora:
"The hourly structure currently..."

Owner interrupts:

"No, focus on one minute."

The speech interruption should:

- stop or duck spoken output
- finalize the owner steering input
- attach it to the same active Task
- update/revise the plan if applicable
- continue the same Task

It must NOT create a disconnected new Agent session.

==================================================
23. VOICE DISCONNECT != TASK CANCELLATION
==================================================

If a voice connection drops:

call disconnected
≠
Task cancelled

Background-safe work should continue.

When the owner reconnects:

"Where are we?"

Lonora must recover the same persistent state.

If work cannot safely continue without the live call, represent that explicitly as waiting.

==================================================
24. PARTIAL SPEECH MUST NOT BECOME A FINANCIAL COMMAND
==================================================

Realtime speech may arrive as fragments.

Example:

"buy..."

"buy one..."

"buy one lot..."

Do not create several independent actions.

Maintain:

partial transcript
→ finalized utterance
→ typed intent
→ validated action

Only finalized, sufficiently clear input may affect Task intent.

Partial transcription must never directly trigger financial mutation.

==================================================
25. BARGE-IN SAFETY
==================================================

If the owner interrupts spoken output:

stop spoken response when appropriate.

Do NOT automatically cancel:

- durable Task
- broker reconciliation
- already committed external operation
- confirmed trade request already crossing the mutation boundary

Speech cancellation and side-effect cancellation are separate concepts.

==================================================
26. SAME THREAD SEMANTICS
==================================================

Voice interactions belong to the same logical conversation.

If the owner previously typed:

"Watch gold around 4200."

then starts a call:

"What happened with the watch?"

Lonora must know the existing watch.

If the owner creates a watch during voice:

it must later be visible in text.

No voice-only hidden world.

==================================================
27. LONG-RUNNING WORK
==================================================

The Agent loop must support work that exceeds one request/response cycle.

Possible phases may include equivalents of:

UNDERSTANDING
PLANNING
GATHERING
EXECUTING
VERIFYING
WAITING
RECOVERING
COMPLETED
FAILED
CANCELLED

Do not invent fake progress.

Derive status from authoritative Run/Task/tool state.

==================================================
28. WAIT IS A REAL RUNTIME STATE
==================================================

Some work should not spin continuously.

Example:

"Watch gold and tell me when structure changes."

Correct:

create durable watch
→ persist Task/Goal state
→ Agent sleeps
→ deterministic market system monitors cheaply
→ relevant event occurs
→ Agent wakes
→ revalidates
→ continues

Do NOT keep an LLM running every tick.

==================================================
29. WAKE SOURCES
==================================================

The same Agent may wake from:

- owner input
- market watch
- routine
- broker state change
- task retry timer
- collaboration result
- subagent result
- notification action
- reconnect
- scheduled event
- health recovery

All wakes must re-enter the same coherent Agent operating environment.

==================================================
30. REVALIDATE THE WORLD AFTER WAKE
==================================================

Persistent work may wake after seconds, minutes or hours.

Never assume old context is still true.

On wake:

load durable state
→ inspect why it woke
→ retrieve relevant fresh external state
→ determine what changed
→ continue

For financial work:

fresh market/broker/account state is mandatory before action.

==================================================
31. RESTART RECOVERY
==================================================

The Agent runtime must tolerate process restart.

Before restart:

Task running
step 3
waiting on broker recovery

After restart:

the new worker must be able to determine:

- Task identity
- current Run status
- what was already completed
- what side effects may already exist
- whether a prior mutation is ambiguous
- current broker/market state
- what safe next action is

Never blindly replay external mutations.

==================================================
32. TASK IDENTITY != RUN ATTEMPT
==================================================

A durable owner goal/task may survive multiple Run attempts.

Do not conflate:

logical Task

with:

one worker/model execution attempt.

A retry/recovery may create a new attempt while continuing the same logical work.

Preserve Task history and outcome.

==================================================
33. SIDE-EFFECT AWARENESS
==================================================

Classify operations conceptually as:

READ_ONLY
IDEMPOTENT
MUTATING
IRREVERSIBLE

Adapt terminology to current code if equivalent structures exist.

Recovery policy must differ by class.

READ_ONLY:
usually safe to retry.

IDEMPOTENT:
retry with correct identity/fencing.

MUTATING:
must know exact mutation status before retry.

IRREVERSIBLE:
requires strongest confirmation and recovery discipline.

==================================================
34. MEMORY AND LEARNING
==================================================

Study Nanobot's memory and learning architecture deeply.

Strengthen Lonora's existing memory rather than blindly adding another memory database.

Separate concepts such as:

- conversation context
- durable owner knowledge
- Agent memory
- Task state
- historical evidence
- execution records
- learned operational facts

Do not dump every historical fact into the model prompt.

Use bounded relevant retrieval.

==================================================
35. OPERATIONAL LEARNING
==================================================

Lonora should learn from previous runtime failures where useful.

Example:

a specific route repeatedly returns an unsupported oversized object.

The Agent may remember/use the known bounded alternative on future equivalent work.

However:

do not allow model-generated learning to silently rewrite:

- core financial policy
- owner permissions
- exact market binding
- Emergency Stop
- trading safety
- risk rules
- execution reconciliation

Operational learning is not authority expansion.

==================================================
36. MEMORY PROVENANCE
==================================================

When durable memory influences important behavior, preserve enough provenance to understand:

- where it came from
- when it was learned
- whether it is owner-provided
- tool-observed
- inferred
- external-source-derived
- stale/expired where relevant

Do not treat inferred facts as immutable owner facts.

==================================================
37. CONTEXT MANAGEMENT
==================================================

Study Nanobot's context strategy.

Lonora must build bounded context from relevant state.

Do not dump:

- every message
- every broker position ever seen
- every market symbol
- every skill
- every task
- every collaboration
- every historical decision

into every model invocation.

Retrieve only what is useful for the current goal.

Preserve:

system constitution
Agent identity
scope
relevant memory
current Task
relevant evidence
necessary tools
recent conversation
necessary collaboration results

==================================================
38. SKILLS
==================================================

Integrate with the selective Skills Runtime from specification 01.

Do not inject every skill into every turn.

The Agent loop/environment should understand:

- which skill is relevant
- which tools it requires
- whether scope allows it
- whether dependencies exist
- whether the context budget allows it

Nanobot may inform the design, but reuse Lonora's skill architecture.

==================================================
39. SUBAGENTS
==================================================

Subagents must participate in the same operating philosophy.

Parent determines a bounded need.

Child receives:

- explicit task
- bounded context
- bounded tools
- bounded scope
- no authority escalation

Child works independently.

Child returns an actual result.

Parent consumes the result and continues.

Do not expose a second hidden hierarchy/manager framework.

Do not introduce manager/planner architecture unless existing source architecture genuinely requires it.

==================================================
40. SUBAGENT FAILURE
==================================================

A failed child does not automatically fail the parent goal.

Parent should inspect:

- what failed
- what evidence was returned
- whether another route exists
- whether another participant should be consulted
- whether task can continue without that evidence

Do not fabricate child output.

==================================================
41. COLLABORATION
==================================================

Integrate with the existing durable Collaboration Session.

Collaboration is evidence fusion.

It is not voting.

Agent loop must understand:

- participant pending
- participant completed
- participant failed
- evidence conflicts
- whether synthesis can happen
- whether another bounded round is justified
- whether fresh market revalidation is needed

Exactly one synthesis/follow-up should exist for one collaboration round.

==================================================
42. SELF-DIAGNOSIS
==================================================

Lonora needs internal runtime visibility sufficient to answer:

- What am I working on?
- What phase am I in?
- What failed?
- What have I already tried?
- Which dependencies are unavailable?
- What can I safely do next?
- What am I waiting for?
- Does the owner need to intervene?

Do not rely on asking the model to guess runtime state from prose.

Expose typed state.

==================================================
43. RUNTIME STATUS MUST BE TRUTHFUL
==================================================

When the owner asks:

"What are you doing?"

"Where did you get to?"

"Why are you waiting?"

Answer from persisted actual state.

Examples:

"Waiting for broker reconciliation."

"Reading 15-minute candles."

"Two collaborators finished; one is still working."

"Trade approval is waiting for your button."

Never invent model-style activity labels disconnected from actual execution.

==================================================
44. INTERNAL ENVIRONMENT INSPECTION
==================================================

The Agent should be capable of inspecting its own operational environment through safe structured interfaces.

Examples:

- available tools
- tool schema
- current Task
- current Run
- recent errors
- active watches
- broker health
- market health
- current Agent scope
- relevant collaborators
- authorization state

Do not expose secrets.

Do not allow model text to mutate authoritative policy merely because it can inspect it.

==================================================
45. PRODUCTION FLOW
==================================================

This feature must work in the actual resident Gateway runtime.

Do not implement a demo-only loop.

Verify:

API/user input
→ durable message/task
→ Gateway claims work
→ Agent loop
→ tools
→ checkpoints
→ wait/retry/wake
→ outcome
→ Web/Mobile/Voice live projection

==================================================
46. MULTI-PROCESS SAFETY
==================================================

Assume more than one worker/process may observe durable state.

Use existing:

- leases
- fencing
- row locks
- versions
- receipts
- idempotency

Do not use process-local booleans as authoritative work ownership.

Prevent duplicate:

- Task continuation
- synthesis
- retries
- wakeups
- notifications
- financial mutations

==================================================
47. FINANCIAL SAFETY REMAINS SERVER-AUTHORITATIVE
==================================================

Self-directed Agent behavior does NOT mean model-controlled financial safety.

The model may decide what to investigate.

The server decides what is allowed.

The following remain hard authoritative boundaries:

- Trading ON/OFF
- Emergency Stop
- exact broker symbol
- account scope
- specialist binding
- Personal Agent authority rules
- Super Bot authorization
- trade approvals
- risk controls
- sizing
- exposure rules
- fresh market evidence
- broker connection state
- final execution revalidation
- operation identity
- execution journal
- no-blind-retry behavior
- reconciliation
- owner intervention precedence

The Agent can never reason its way around these controls.

==================================================
48. NO BLIND FINANCIAL RETRY
==================================================

This requirement is absolute.

If a financial mutation may have reached the broker:

UNKNOWN RESULT
≠
FAILED

Do not resend.

Reconcile first.

Only after authoritative resolution may the Agent determine the next action.

==================================================
49. NO EVIDENCE = NO RECOMMENDATION
==================================================

Agent autonomy must not increase hallucinated market analysis.

If required evidence cannot be obtained:

WAIT
or
UNAVAILABLE

must remain valid outcomes.

Do not invent:

- price
- candles
- account state
- position
- entry
- stop
- target
- fill
- performance

==================================================
50. EXACT BROKER SYMBOL
==================================================

The owner must not be forced to repeat technical symbol formatting already known by the Agent.

If a specialist is bound to:

XAUUSDm

and the owner says:

"gold"

or a case-only equivalent:

the Agent should use its authoritative binding.

Do not make the owner act as the system's symbol resolver.

Never strip broker suffixes or silently map to another instrument.

==================================================
51. SUPER BOT
==================================================

Super Bot is a mode/authority state on the same Agent.

It is NOT another Agent runtime.

When the owner says:

"Enable Super Bot."

The Agent must attempt to perform all internal prerequisite work it can:

inspect current state
→ inspect existing goal
→ construct/repair required goal where appropriate
→ validate
→ prepare proposal
→ reach the actual owner-authorization boundary

Do not repeatedly ask the owner to fix internal tool payloads.

The owner should mainly see the real authority proposal/authorization step.

==================================================
52. CHART WORK
==================================================

Chart operations must also use the self-directed loop.

Example:

chart_inspect → tool_result_too_large

Do not stop.

Use:

- bounded inspection
- alternate view
- known scene identifier
- smaller result
- targeted chart operation
- snapshot if appropriate

If an indicator is missing:

inspect
→ add if allowed
→ read
→ continue

Internal chart mechanics are generally not the owner's responsibility.

==================================================
53. BROKER RECOVERY
==================================================

Reuse the existing broker recovery/reconciliation system.

If safe market/account reads fail:

Agent should inspect broker health.

If appropriate:

trigger or wait for recovery
→ reconcile
→ verify health
→ retry safe read

Do not invent a second reconnect implementation inside prompts.

==================================================
54. RESEARCH / EXTERNAL CAPABILITY FAILURE
==================================================

If a requested capability is unavailable because a provider/integration is not configured:

determine whether another authorized source/tool can satisfy the goal.

If yes:
use it.

If no:
report the actual missing capability.

Do not pretend configuration exists.

==================================================
55. ONE GLOBAL MODEL ROUTER
==================================================

Preserve Lonora's global model routing.

Do not create per-Agent model/provider selectors.

Supported settings architecture remains global.

Agent environment selection and recovery must not introduce hidden model routing configuration per Agent.

==================================================
56. SECURITY OF TOOL RESULTS
==================================================

Tool outputs, web pages, peer results and external text are untrusted data.

They cannot override:

- system policy
- owner permissions
- trading rules
- scope
- secrets policy

Preserve instruction/data separation.

==================================================
57. NO CHAIN-OF-THOUGHT STORAGE
==================================================

Do not persist or expose private hidden reasoning.

Persist useful operational facts such as:

- action selected
- tool invoked
- typed error
- evidence reference
- state transition
- user-visible rationale
- next wait condition
- decision record

Do not store hidden chain-of-thought.

==================================================
58. OBSERVABILITY
==================================================

Add enough operational visibility to debug the Agent runtime.

Useful records/events should make it possible to reconstruct:

goal
→ Run attempt
→ tool calls
→ results
→ recoverable errors
→ retries
→ waits
→ wakes
→ completion

without storing hidden reasoning.

Provide stable reason/error codes.

==================================================
59. USER EXPERIENCE
==================================================

The owner should experience Lonora as:

"I ask for a result and it works on it."

not:

"I operate its internal APIs."

Bad experience:

Owner:
"Enable Super Bot."

Lonora:
"goal_create failed. Say 'retry'."

Owner:
"retry."

Lonora:
"watch_price_required. Tell me to retry again."

This is unacceptable.

Correct experience:

Owner:
"Enable Super Bot."

Lonora internally:

inspect state
→ discovers no valid Goal
→ builds valid Goal
→ schema validates it
→ creates it
→ prepares Super Bot proposal
→ reaches owner-authorization boundary

Then owner sees the actual authorization proposal.

==================================================
60. EXAMPLE — ANALYZE GOLD
==================================================

Owner:

"Analyze gold."

Expected behavior:

resolve current Agent scope
→ identify exact broker symbol
→ inspect broker/market health
→ recover safe data connection if needed
→ quote
→ candles
→ indicators
→ structure
→ relevant account/exposure
→ evidence classification
→ recommendation contract
→ freshness check
→ answer

If candles fail:

classify failure
→ recover/alternate safe route
→ retry boundedly
→ continue

Only fail the task if required evidence genuinely cannot be obtained.

==================================================
61. EXAMPLE — VOICE
==================================================

Owner by voice:

"Analyze gold."

Lonora:

"Sure, I'm analyzing gold now."

Internally:

create/continue same Task
→ working

Several seconds later the owner says:

"Where are you?"

Lonora:

reads actual Task state

not the transcript alone.

Possible answer:

"I've checked the live quote and one-minute candles. I'm comparing them with the 15-minute structure."

If call disconnects:

Task persists.

If user returns in text:

"What happened with the analysis?"

same Agent
same Task
same context.

==================================================
62. EXAMPLE — INVALID TOOL ARGUMENTS
==================================================

goal_create
→ tool_arguments_invalid

Expected:

inspect actual schema
→ compare proposed args
→ identify missing/invalid requirement
→ inspect existing account/symbol/goal context
→ repair
→ validate
→ retry

Not:

"Please tell me to try again."

==================================================
63. EXAMPLE — RESULT TOO LARGE
==================================================

chart_inspect
→ tool_result_too_large

Expected:

recognize bounded-read problem
→ request relevant section / smaller view
→ use targeted chart operations
→ continue

Not:

"I cannot use this chart."

==================================================
64. EXAMPLE — CONNECTION FAILURE
==================================================

market_candles
→ broker_connection_timeout

Expected:

inspect broker recovery state
→ initiate/wait for safe recovery where appropriate
→ verify connection
→ retry read
→ continue

If still unavailable after bounded recovery:

Task result may be:

WAIT / unavailable due to broker data failure

But the Agent must not claim:

"I didn't understand the request."

==================================================
65. INTEGRATE WITH SPECIFICATIONS 01–18
==================================================

This specification does not replace specifications 01–18.

It provides the coherent Agent operating environment they depend on.

Review its impact on:

01 Skills Runtime
02 Mobile Chat Reliability
03 Super Bot / Market Intelligence
04 Long-running Task Runtime
05 Personal Agent
06 Collaboration
07 Mentions
08 Shadow Trading
09 Execution Revalidation
10 Exposure / Cross-Market
11 Opportunity / Thesis
12 Manual Trading
13 Market Health
14 Attention / Notifications
15 Voice
16 Explainability
17 Broker Recovery
18 Unified UI/UX

Do not duplicate their domain models.

Update them only where integration changes are required.

==================================================
66. IMPLEMENTATION MATRIX
==================================================

Add this specification to the implementation tracking system.

Update:

docs/lonora-specs/IMPLEMENTATION_MATRIX.md

docs/lonora-specs/DEPENDENCY_GRAPH.md

docs/lonora-specs/PROGRESS.md

Add requirement identifiers:

S19-...

Track each requirement independently.

Do not mark specification 19 VERIFIED merely because an Agent can call several tools.

==================================================
67. REQUIRED IMPLEMENTATION PLAN
==================================================

Before major coding, report:

1. current repository HEAD
2. current branch
3. existing Agent-loop execution path
4. existing ToolLoop behavior
5. Run/Task/checkpoint behavior
6. voice execution path
7. recovery behavior
8. Nanobot modules studied
9. major design gaps
10. primitives to reuse
11. primitives requiring extension
12. migrations, if any
13. test strategy
14. first integration wave

Then implement.

Do not wait for another instruction unless genuinely blocked.

==================================================
68. IMPLEMENT IN SMALL INTEGRATION WAVES
==================================================

Suggested dependency-aware sequence:

WAVE A
Nanobot architecture study + current Lonora runtime audit

WAVE B
typed Agent loop state/result classification + tool environment introspection

WAVE C
tool-error diagnosis/recovery + bounded retries + failure-loop protection

WAVE D
durable continuation/wait/wake/restart semantics

WAVE E
voice same-Agent integration and steering continuity

WAVE F
Super Bot/chart/broker/research vertical recovery scenarios

WAVE G
subagent/collaboration integration

WAVE H
UI/live-state/observability

WAVE I
full cross-spec regression and completion review

Adjust after repository audit.

Do not create isolated competing implementations.

==================================================
69. TESTING REQUIREMENTS
==================================================

Add focused unit/integration tests for the Agent loop.

Required scenarios include:

- successful multi-tool goal
- invalid tool arguments repaired automatically
- oversized tool result narrowed automatically
- recoverable safe-read failure
- repeated identical failure changes strategy
- retry attempt survives restart
- wait/wake resumes same logical Task
- worker crash/restart
- owner steering active Task
- cancellation
- pause/resume
- duplicate wake protection
- duplicate Run protection
- duplicate side-effect protection
- ambiguous mutation reconciled, never resent
- Personal Agent broad visibility does not delegate financial authority
- specialist exact scope remains enforced
- subagent cannot amplify permissions
- collaboration result resumes parent
- one synthesis Run per collaboration round
- voice Task survives silence
- voice Task survives disconnect/reconnect
- voice steering affects same Task
- partial speech cannot trigger financial mutation
- user asks "where are you?" and receives real Task state
- "analyze gold" recovers from safe broker-read failure where possible
- `goal_create` invalid payload can be corrected without user operating the tool
- chart oversized result can use bounded alternative
- restart does not repeat completed task step

==================================================
70. TEST WITH REALISTIC SCRIPTED AGENT BEHAVIOR
==================================================

Do not test only isolated helper functions.

Include scripted end-to-end AgentRuntime tests where model outputs deliberately make mistakes.

Example:

model emits invalid goal_create arguments
→ runtime/tool returns typed failure
→ next model turn receives structured failure/schema context
→ model repairs call
→ tool succeeds
→ Agent continues

This proves the system is an Agent loop rather than a one-shot tool dispatcher.

==================================================
71. FAILURE-INJECTION TESTS
==================================================

Inject:

- broker timeout
- stale quote
- stale candles
- PostgreSQL restart where practical
- worker cancellation
- version conflict
- duplicated event
- delayed peer result
- oversized result
- invalid arguments
- external mutation ambiguity

Verify safe recovery.

==================================================
72. PERFORMANCE
==================================================

Do not call the LLM unnecessarily.

Use deterministic systems for:

- event filtering
- health
- watch conditions
- scheduling
- leases
- deduplication
- retry timing
- permission checks
- financial safety
- state transitions where deterministic

Wake the Agent/model when semantic reasoning is useful.

Do not run the LLM on every market tick.

==================================================
73. CONTEXT COST
==================================================

Recovery must not cause unlimited prompt growth.

Do not append every failed call forever.

Maintain bounded useful attempt/error summaries plus durable detailed records outside the model context.

The model needs enough history to avoid repetition, not an unbounded log.

==================================================
74. BACKWARD COMPATIBILITY
==================================================

Preserve existing users/data/runtime behavior where safe.

If legacy Agent behavior creates a scope loophole, migrate or fence it explicitly rather than silently preserving unsafe ambiguity.

Document compatibility decisions.

==================================================
75. DATABASE
==================================================

Reuse current tables/state structures where appropriate.

Do not create a table for every tiny runtime concept.

Do not dump the entire Agent runtime into one giant JSON document either.

Use schema according to lifecycle/query/concurrency requirements.

All new durable state must have clear ownership and update semantics.

==================================================
76. MIGRATIONS
==================================================

Any migration must:

- be reversible where reasonably possible
- preserve existing data
- use server-compatible defaults
- avoid unsafe destructive rewrites
- be tested on disposable PostgreSQL

Do not deploy production migrations.

==================================================
77. WEB / MOBILE
==================================================

Expose useful state, not internal noise.

The UI should be able to show things such as:

- Working
- Gathering market data
- Waiting for approval
- Waiting for market condition
- Recovering broker connection
- Consulting another Agent
- Paused
- Completed

Only if these states derive from actual backend state.

Do not show every internal retry to the owner.

==================================================
78. VOICE USER EXPERIENCE
==================================================

Voice should feel like speaking to the Agent while it works.

Example:

Owner:
"Analyze gold."

Lonora:
"Okay, give me a moment."

Agent continues.

If work finishes while call remains active:

Lonora may speak the result.

If an important progress transition occurs and speaking is appropriate:

Lonora may provide a concise progress update.

Do not spam progress.

Integrate with intelligent attention policy.

==================================================
79. ATTENTION
==================================================

Event
≠
notification
≠
spoken interruption

The Agent operating environment must cooperate with specification 14.

Only meaningful transitions should interrupt the owner.

==================================================
80. SECURITY
==================================================

Never expose:

- credentials
- raw secret values
- private encryption material
- hidden chain-of-thought

Tool introspection must expose safe schemas/metadata, not secrets.

==================================================
81. COMPLETION CRITERIA
==================================================

Specification 19 is not complete until Lonora can demonstrably:

- receive a goal
- retain it durably
- perform multiple internal steps
- recover from common tool/runtime failures
- repair invalid tool calls
- avoid repeated equivalent failure loops
- wait and wake
- survive restart
- resume the same logical Task
- distinguish understanding failure from execution failure
- use the owner only when genuinely necessary
- preserve server-authoritative financial safety
- use voice and text as channels to the same Agent
- allow voice steering of active work
- preserve Task state across voice disconnect
- use subagents without creating authority escalation
- use collaboration without duplicate synthesis
- provide truthful status
- maintain bounded model context
- preserve idempotency and no-blind-retry guarantees
- pass required local tests

==================================================
82. NANOBOT COMPARATIVE ACCEPTANCE
==================================================

Before marking S19 complete, revisit:

docs/lonora-specs/NANOBOT_ARCHITECTURE_STUDY.md

For every relevant Nanobot feature studied, explicitly conclude one of:

ADOPTED
ADAPTED
LONORA_ALREADY_STRONGER
NOT_APPLICABLE
REJECTED_WITH_REASON

No major Agent-runtime concept discovered in Nanobot should be silently ignored.

==================================================
83. CROSS-SPEC FINAL REVIEW
==================================================

After implementing 19:

re-run a cross-spec review of 01–19.

Specifically inspect for:

- duplicate runtimes
- duplicate Task concepts
- duplicate memory
- duplicate recovery systems
- inconsistent voice/text state
- Agent scope loopholes
- duplicate retries
- duplicate financial mutations
- unbounded loops
- unbounded context
- fake status
- user-operated internal tools
- stale market evidence
- unsafe background financial work

Fix inconsistencies.

==================================================
84. QUALITY GATES
==================================================

Use the repository's real quality commands.

Expected categories include:

- Python tests
- PostgreSQL integration tests
- Ruff
- Pyright
- Node tests
- Web tests
- Expo Web tests
- TypeScript checks
- client lint
- builds/exports
- existing broker tests
- chart tests
- trading tests
- recovery tests
- voice tests
- newly added S19 tests

Do not claim native Android VERIFIED without actually testing a native Android runtime.

If unavailable:

BLOCKED_EXTERNAL_NATIVE_ANDROID

Do not claim remote GitHub Actions passed while the account billing lock prevents jobs from starting.

==================================================
85. DO NOT STOP AFTER FOUNDATION WORK
==================================================

Do not finish after:

"Agent loop foundation implemented."

Continue through:

- real recovery
- real Task continuation
- voice integration
- restart recovery
- actual vertical scenarios
- UX/live projection
- tests
- cross-spec integration

This specification requires working behavior, not only contracts.

==================================================
86. DO NOT ASK THE OWNER TO CONTINUE EACH WAVE
==================================================

Once implementation begins:

continue automatically through the implementation waves.

Do not stop after each commit to ask:

"Should I continue?"

Stop only when:

- genuinely externally blocked from further repository work

or

- specification 19 and its dependent integration are fully implemented and verified.

==================================================
87. FINAL REPORT
==================================================

At completion provide:

- branch
- final HEAD
- PR
- commits grouped by capability
- Nanobot modules studied
- NANOBOT_ARCHITECTURE_STUDY summary
- existing Lonora primitives reused
- Agent-loop implementation
- error/recovery implementation
- Task continuation/restart implementation
- voice same-Agent integration
- subagent/collaboration integration
- migrations
- tests
- quality gates
- cross-spec regressions
- external blockers
- remaining deferred work with explicit technical reason only

Do not claim completion if major requirements remain merely "foundation exists" or "in progress."

==================================================
88. CORE DESIGN MANTRA
==================================================

Lonora is not:

LLM + many tools.

Lonora is:

A PERSISTENT AGENT OPERATING INSIDE A DURABLE ENVIRONMENT.

The owner supplies intent.

Lonora:

understands
→ inspects
→ acts
→ observes
→ learns what happened
→ repairs
→ continues
→ waits
→ wakes
→ verifies
→ finishes.

Text and voice are simply two interfaces to that same Agent.

Tool errors are usually Agent problems to investigate, not instructions for the owner.

Financial authority remains server-controlled.

This is the behavior specification for Lonora's Agent Operating Environment.