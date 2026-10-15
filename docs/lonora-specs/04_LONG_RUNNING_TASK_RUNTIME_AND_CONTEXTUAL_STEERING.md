TITLE:
Build Lonora Unified Long-Running Task Runtime with Contextual Steering, Live Status Inspection, Interruption, and Resume

CONTEXT:
We are working on Lonora.

This is an implementation task.

The objective is to make Lonora feel like a persistent professional Agent that can continue substantial work in the background while remaining immediately conversational.

The user must be able to talk to the same Agent while a long-running task is still executing.

The Agent should behave like the supervisor of the work:

- continue the task
- inspect what is happening
- answer status questions immediately
- accept changes while work is running
- pause safely
- resume safely
- cancel safely
- delegate work
- recover after restart
- distinguish conversation from task control
- report real state rather than role-playing progress

Do NOT build this as a UI illusion.

The behavior must come from the runtime architecture.

Required workflow:

INSPECT
→ MAP CURRENT RUN/STEERING/GATEWAY ARCHITECTURE
→ DESIGN
→ IMPLEMENT
→ INTEGRATE
→ TEST
→ RECOVERY TEST
→ FIX
→ VERIFY

Do not stop at an architecture report.

==================================================
PRIMARY PRODUCT EXPERIENCE
==================================================

The intended experience is:

User:
"Deploy the project."

Agent:
"Got it. I'm working on it."

The deployment begins.

While deployment is still running:

User:
"How is it going?"

The Agent should answer immediately after inspecting the real task state:

"The build is finished. I'm verifying the deployment now."

The original deployment must continue.

The user may then say:

"Don't build Android anymore. Keep Web only."

The Agent should understand that this modifies the currently running task.

It should safely steer the task without starting from zero.

This is the target behavior.

==================================================
CORE PRINCIPLE
==================================================

A long-running task must NOT block conversation.

The architecture should support two concurrent logical lanes for the same Agent:

CONVERSATION LANE

The Agent can:

- answer the user
- inspect task state
- explain progress
- receive new instructions
- clarify ambiguity
- discuss unrelated topics when appropriate

WORK LANE

The Agent can:

- execute steps
- use tools
- delegate work
- wait for external events
- retry
- verify results
- continue independently

Both lanes share authoritative durable task state.

Conceptually:

                    LONORA AGENT
                         │
             ┌───────────┴───────────┐
             │                       │
     Conversation Lane          Work Lane
             │                       │
      answer immediately        execute task
      inspect status            use tools
      understand changes        delegate
      receive steering          wait/retry
             │                       │
             └───────────┬───────────┘
                         │
                  Durable Task State

Do not create two unrelated Agents to simulate this.

It must remain the same persistent Agent identity.

==================================================
CRITICAL REQUIREMENT:
NO KEYWORD-BASED USER COMMAND ROUTING
==================================================

Lonora must understand user intent.

It must NOT wait for predefined phrases.

Do NOT implement core task control using:

message.includes(...)

regular expressions matching command words

lists of synonyms

hardcoded phrases

fixed Arabic sentences

fixed English sentences

magic words

slash commands as the primary interface

Examples of prohibited architecture:

if message contains "status":
    inspect task

if message contains "stop":
    pause task

if message contains "continue":
    resume task

This is explicitly NOT the desired behavior.

==================================================
SEMANTIC INTENT UNDERSTANDING
==================================================

The user communicates naturally.

These different utterances may express the same intent:

"Where are we?"

"How is it going?"

"Did anything finish?"

"Are you still working on it?"

"What's happening with the deployment?"

The system should understand their meaning from context.

Likewise:

"Leave Android and finish Web only."

"No, forget that part and continue with the rest."

"Keep doing everything except the mobile build."

may all modify the current task differently depending on conversation and task context.

Do not store these example sentences as routing keywords.

They are examples only.

==================================================
CONTEXTUAL INTENT RESOLUTION
==================================================

When the user sends a message while one or more tasks exist, the Agent should interpret it using:

current conversation

recent conversational references

active tasks

task names

task plans

current steps

completed steps

pending steps

active tools

subtasks

previous user steering

current waiting reason

relevant Agent memory/context

Then produce a structured internal intent.

Conceptually:

Natural User Message
        ↓
Contextual Understanding
        ↓
Typed Internal Intent
        ↓
Server Validation
        ↓
Task Controller

The internal intent may represent concepts such as:

INSPECT_TASK
MODIFY_TASK
PAUSE_TASK
RESUME_TASK
CANCEL_TASK
APPEND_WORK
REPLACE_PENDING_WORK
CHANGE_PRIORITY
ANSWER_TASK_QUESTION
CREATE_NEW_TASK
CONTINUE_CONVERSATION

These names are conceptual.

Use contracts appropriate to the existing Lonora architecture.

The user must never need to know these internal intent names.

==================================================
NO FIXED USER TEXT CONTRACT
==================================================

Do NOT require the user to say:

"PAUSE"

"RESUME"

"STATUS"

"CANCEL"

or any exact phrase.

Natural language is the interface.

The user should even be able to say:

"No, not that one. Leave it and finish the other thing."

The Agent should resolve references from context when sufficiently clear.

==================================================
AMBIGUITY HANDLING
==================================================

Semantic understanding does not mean guessing dangerously.

If the user refers to multiple possible tasks and the target cannot be resolved confidently, ask the smallest possible clarification.

Example:

There are three active tasks.

User:
"Stop that one."

If conversation context clearly identifies one task:

act on that task.

If not:

ask which task.

Do not guess for destructive or high-impact operations.

==================================================
MODEL UNDERSTANDS INTENT;
SERVER CONTROLS STATE
==================================================

The Agent interprets meaning.

The runtime validates actions.

Conceptually:

User Language
     ↓
Agent Reasoning
     ↓
Structured Intent
     ↓
Server Validation
     ↓
Task State Transition

The LLM must not directly manipulate database task states without validated runtime operations.

==================================================
USE CURRENT LONORA ARCHITECTURE
==================================================

Before implementing, inspect existing:

Run contracts

RunRow

current Run statuses

Gateway dispatch

worker execution

steering

user_interrupt_pending

consume_steering

Run checkpoints

Run cancellation

Run resume

waiting_input

waiting_takeover

subagent Runs

market wakes

routine wakes

events

thread messages

streaming

tool loop

goal execution

Existing Lonora already contains important primitives for:

queued work

leased work

running work

waiting

resume

cancel

steering

background triggers

subagents

Do not create a duplicate runtime if existing components can be extended.

==================================================
TASK VS RUN
==================================================

Establish a clean distinction between:

TASK

The durable logical job the user cares about.

RUN

A concrete execution attempt or continuation of that Task.

STEP

A meaningful unit inside the work plan.

Example:

Task:
"Deploy Lonora"

Run #1:
build attempt

Run #2:
resume after infrastructure failure

Run #3:
verification continuation

From the user's perspective:

one Task

Do not show every internal Run as if it were a separate user request.

==================================================
DO NOT ADD TASK ENTITY BLINDLY
==================================================

Inspect the current Run model first.

If the existing model can cleanly represent a durable logical Task with multiple execution attempts, extend it appropriately.

If not, introduce a Task layer.

Do not add unnecessary abstractions merely because this prompt uses the word "Task."

==================================================
UNIFIED TASK STATES
==================================================

Keep top-level Task states small and understandable.

Support semantics equivalent to:

CREATED
QUEUED
RUNNING
WAITING
PAUSED
COMPLETED
FAILED
CANCELLED

Do not create hundreds of top-level statuses.

Detailed activity belongs in:

phase
reason
current_step
metadata

==================================================
TASK PHASE
==================================================

Track what the Agent is actually doing separately from the main state.

Examples:

PLANNING
THINKING
READING
RESEARCHING
DELEGATING
EXECUTING
WRITING
BUILDING
UPLOADING
DEPLOYING
TESTING
VERIFYING
REVIEWING
MONITORING
RECONCILING
RETRYING

These phases should correspond to real runtime activity.

Do not display fake phases purely for animation.

==================================================
USER-FACING ACTIVITY
==================================================

The interface may show concise activity such as:

Working
Checking
Researching
Executing
Reviewing
Verifying
Waiting
Monitoring

But each visible activity must derive from real runtime state.

Do not randomly rotate phrases to simulate intelligence.

==================================================
WAITING STATE
==================================================

WAITING must include a reason.

Examples:

USER_INPUT
APPROVAL
SUBAGENT
EXTERNAL_EVENT
WEBHOOK
MARKET_CONDITION
SCHEDULE
RETRY_BACKOFF
EXTERNAL_PROCESS
DEPENDENCY

This allows the Agent to answer:

"Why are you waiting?"

from authoritative state.

==================================================
LONG-RUNNING TASK STATE MACHINE
==================================================

Conceptually:

TASK_CREATED
      ↓
QUEUED
      ↓
RUNNING
      ↓
PLANNING
      ↓
EXECUTING
      ↓
      ├──────────────→ WAITING
      │                    │
      │                   WAKE
      │                    │
      ├──────────────→ PAUSED
      │                    │
      │                  RESUME
      │                    │
      ├──────────────→ RETRYING
      │                    │
      │               RECONCILE
      │                    │
      └────────────────────┘
                ↓
            VERIFYING
                ↓
            COMPLETED

Failure paths:

RUNNING
→ FAILED

Any safe cancellable state:
→ CANCELLED

Use the existing Lonora state model where possible.

==================================================
STATUS QUERY DURING EXECUTION
==================================================

A status question must NOT interrupt the task.

Expected behavior:

Task RUNNING
      +
User asks about progress
      ↓
Read current Task snapshot
      ↓
Respond
      ↓
Task continues uninterrupted

This is mandatory.

==================================================
REAL STATUS INSPECTION
==================================================

When the Agent says:

"Let me check."

it must actually inspect runtime state.

Do not allow role-played task status.

Provide a runtime capability equivalent to:

task_status_read

or reuse an existing authoritative status API/tool.

The status source should include enough information to answer accurately.

==================================================
TASK STATUS SNAPSHOT
==================================================

Create or expose a structured TaskStatusSnapshot.

It should support information equivalent to:

task_id

state
phase

summary

current_step
last_completed_step
next_step

started_at
updated_at

waiting_reason
blocking_reason

active_runs
active_tools
active_subtasks

recent_meaningful_events

last_checkpoint

recoverable_error

can_pause
can_resume
can_cancel

progress_kind

Do not inject enormous logs into the Agent context.

==================================================
PROGRESS MUST NOT BE FABRICATED
==================================================

Do not invent percentages.

If progress is measurable:

report it.

If a plan contains known steps, report completed/current/remaining steps.

Example:

Completed:
✓ inspect repository
✓ build Web

Current:
● build Android

Remaining:
○ publish
○ verify

If progress cannot be objectively measured:

use an indeterminate progress state.

Never produce fake values such as:

"83% complete"

without real evidence.

==================================================
CONVERSATIONAL STATUS LEVELS
==================================================

The Agent should adapt detail to the user's question.

A short status question may produce:

"The build is finished. I'm verifying the deployment now."

A request for more detail may produce:

"Repository inspection and Web build are complete. Android build is running. Publishing starts after that."

A detailed inspection request may include:

steps
subtasks
tools
errors
artifacts
recent events

Do not overwhelm every status response with internal logs.

==================================================
STEERING DURING EXECUTION
==================================================

The user must be able to alter an active task naturally.

Example:

Original task:
Deploy Web and Android.

While running:

User:
"Keep Web, but don't build Android."

The Agent should understand this as a modification of the current Task.

It should not require the user to cancel everything and create a new Task.

==================================================
STEERING TYPES
==================================================

Support semantics equivalent to:

MODIFY CURRENT STEP

MODIFY FUTURE STEPS

APPEND NEW WORK

REMOVE PENDING WORK

REPLACE REMAINING PLAN

CHANGE PRIORITY

CHANGE CONSTRAINT

These should be internal typed operations.

The user communicates naturally.

==================================================
STEERING APPLICATION
==================================================

When steering arrives:

User instruction
      ↓
Resolve target Task
      ↓
Understand requested change
      ↓
Compare against current execution state
      ↓
Determine safe application point
      ↓
Apply now
or
Apply at next checkpoint
      ↓
Update plan
      ↓
Continue

==================================================
DO NOT REWRITE HISTORY
==================================================

If the user asks to prevent something that already happened, do not pretend it has not happened.

Example:

Deployment already completed.

User:
"Don't deploy it."

The Agent should explain:

"The deployment already completed before that instruction arrived."

Then offer safe next actions if relevant.

Authoritative state always wins over conversational convenience.

==================================================
SAFE INTERRUPTS
==================================================

Pause and cancellation must be cooperative and safe.

Do not kill arbitrary operations in a way that leaves corrupted state.

Conceptually:

pause_requested
      ↓
worker observes request
      ↓
reach safe checkpoint
      ↓
persist state
      ↓
PAUSED

When a currently executing action cannot safely stop midway:

finish or reconcile the atomic action

then pause before starting the next action.

==================================================
IMMEDIATE SAFETY CONTROLS
==================================================

Existing Emergency Stop and financial safety controls remain separate.

Do not delay a server-side emergency financial stop merely to reach a conversational checkpoint.

Safety-critical runtime controls override normal graceful task pausing.

==================================================
CHECKPOINTS
==================================================

Long-running work must persist resumable checkpoints.

After meaningful steps, store enough durable information to resume safely.

Examples:

completed steps
current step
plan revision
artifacts
external operation identifiers
tool results
subtask state
resume context
errors
timestamps

The exact representation should fit existing Lonora Run/checkpoint architecture.

==================================================
WORKER RESTART RECOVERY
==================================================

If the worker dies:

Task must not disappear.

After restart:

recover active Task
      ↓
inspect checkpoint
      ↓
inspect external state where necessary
      ↓
reconcile
      ↓
resume safely

Do not repeat completed work unnecessarily.

==================================================
IDEMPOTENCY AND EXTERNAL SIDE EFFECTS
==================================================

Classify task steps by side-effect characteristics.

Support semantics equivalent to:

READ_ONLY
IDEMPOTENT
MUTATING
IRREVERSIBLE

Examples:

reading status can usually be repeated

publishing a release may require reconciliation

sending an external action may require operation identity

financial execution must follow existing financial idempotency rules

Never blindly repeat a mutating action after an ambiguous failure.

==================================================
AMBIGUOUS EXTERNAL RESULT
==================================================

If a request was sent but the response was lost:

Do NOT assume failure.

Do NOT blindly retry.

Use:

RECONCILE

Conceptually:

External action sent
      ↓
response uncertain
      ↓
inspect authoritative external state
      ↓
CONFIRMED DONE
or
CONFIRMED NOT DONE
or
STILL AMBIGUOUS

Then act safely.

==================================================
RESUME
==================================================

Resume means:

continue from durable state.

It must NOT mean:

restart from the beginning.

Expected flow:

read Task
↓
read checkpoint
↓
read external state if needed
↓
reconcile
↓
rebuild runtime context
↓
continue next valid step

==================================================
FAILED TASKS
==================================================

Not all failure is terminal.

Represent recoverability.

Example:

FAILED
recoverable = true

The user may naturally say:

"Try again."

The Agent should understand that the existing Task may be resumed with a new execution attempt.

Do not automatically create a completely unrelated Task.

==================================================
RETRY POLICY
==================================================

Differentiate:

automatic retry

retry with backoff

requires owner intervention

requires modified plan

terminal failure

Do not retry indefinitely.

Persist:

failure code
failed step
attempt
recoverability
next retry time when applicable

==================================================
BACKGROUND WAKE SYSTEM
==================================================

A waiting Task should not consume Agent reasoning continuously.

It should wake from events.

Possible wake sources include:

USER_MESSAGE
SUBTASK_RESULT
TOOL_RESULT
WEBHOOK
SCHEDULE
MARKET_WATCH
EXTERNAL_EVENT
APPROVAL
RETRY_TIMER
RESOURCE_CHANGE

Reuse existing Lonora wake/event infrastructure where possible.

==================================================
WAKE FLOW
==================================================

Conceptually:

Task WAITING
     ↓
Wake Event
     ↓
Load Task
     ↓
Load checkpoint
     ↓
Load relevant new evidence
     ↓
Revalidate assumptions
     ↓
Continue

Do not continue from stale assumptions after a long wait.

==================================================
SUBTASKS AND SUBAGENTS
==================================================

A long Task may delegate work.

Conceptually:

Parent Task
   ├── Subtask A
   ├── Subtask B
   └── Subtask C

The main Agent remains responsible for understanding overall progress.

The user should be able to ask for status while subtasks are still running.

Example internal state:

Frontend review      COMPLETED
Backend review       RUNNING
Security review      WAITING

The Agent may answer immediately:

"The frontend review is done. Backend review is still running, and security review is waiting on it."

==================================================
DO NOT BLOCK ON ALL SUBAGENTS FOR STATUS
==================================================

A status query should inspect their current states.

It must not wait for all child work to finish before answering.

==================================================
TASK EVENTS
==================================================

Introduce or normalize durable events similar to:

task.created
task.queued
task.started

task.phase_changed

task.step_started
task.step_progressed
task.step_completed
task.step_failed

task.steering_received
task.steering_applied

task.pause_requested
task.paused

task.resume_requested
task.resumed

task.waiting
task.woken

task.subtask_started
task.subtask_completed
task.subtask_failed

task.tool_started
task.tool_completed
task.tool_failed

task.checkpointed

task.retry_scheduled
task.reconciling

task.cancel_requested
task.cancelled

task.completed
task.failed

Use existing Lonora event conventions rather than introducing a duplicate event system.

==================================================
EVENTS ARE NOT CHAT MESSAGES
==================================================

Do not dump every runtime event into the conversation.

Internal events should remain internal/activity data.

Only meaningful user-facing transitions should become conversational updates.

Examples:

"Build completed; deployment has started."

"Deployment is waiting for approval."

"The verification failed and I'm retrying."

Avoid chat spam.

==================================================
TASK SUMMARY IN AGENT CONTEXT
==================================================

When the Agent receives a normal conversation turn, include a compact summary of relevant active Tasks.

Example concept:

ACTIVE TASKS

Task A
state: RUNNING
phase: DEPLOYING

Task B
state: WAITING
reason: SUBTASK

Do not inject complete task logs into every model call.

If deeper information is required, the Agent should inspect the Task explicitly.

==================================================
MULTIPLE ACTIVE TASKS
==================================================

One Agent may have multiple long-running activities.

Example:

Deployment
RUNNING

Market monitoring
WAITING

Research
RUNNING

Routine
SCHEDULED

The Agent must resolve which Task the user refers to from context.

Do not assume the newest Task every time.

==================================================
CONVERSATIONAL REFERENCES
==================================================

Support natural contextual references.

Examples:

"the deployment"

"the first one"

"the other task"

"that build"

"leave that one"

"continue the gold one"

Do not solve this with a dictionary of phrases.

Resolve references semantically from conversation and Task context.

==================================================
TASK PRIORITY
==================================================

Support Task priority appropriate to the existing scheduler.

Possible semantics:

LOW
NORMAL
HIGH
URGENT

Priority affects scheduling.

It must never bypass:

security
financial safety
authorization
resource ownership
idempotency

==================================================
USER INTERRUPTION VS STATUS QUESTION
==================================================

This distinction is critical.

A status question:

"How is it going?"

must NOT supersede current work.

A steering instruction:

"Stop building Android."

may affect future execution.

A new unrelated question:

"What's RSI?"

may simply receive an answer while the Task continues.

A cancellation request:

"I don't want this deployment anymore."

should control the Task.

The distinction must come from semantic contextual understanding.

Not keywords.

==================================================
CONVERSATION RESPONSIVENESS
==================================================

Do not force every user message to wait behind the currently running Tool Loop.

If the architecture currently serializes all conversation turns behind one long Run, refactor it.

The Agent must have a low-latency path for conversational interaction and task control while background work continues.

Preserve thread ordering and durable message semantics.

==================================================
FOREGROUND RESPONSE SHOULD NOT DUPLICATE WORK
==================================================

If the background task already has a tool operation executing, a status conversation must not accidentally start a duplicate tool operation.

Inspect only.

==================================================
STREAMING / WORKING INDICATOR
==================================================

Existing Agent working indicators should reflect real activity.

The UI may show:

Working
Checking
Researching
Executing
Reviewing
Waiting

The indicator should remain compatible with the conversation being interactive.

Do not treat "Agent is working" as "composer disabled."

==================================================
CHAT MUST REMAIN USABLE
==================================================

While a background Task runs:

the composer remains usable

messages can be sent

the Agent may respond

status can be inspected

steering can be submitted

the user can pause/cancel

Do not lock the entire thread simply because a Run exists.

==================================================
TASK CONTROL CARD
==================================================

Keep UI simple.

The conversation may expose a small current-task indicator.

Example:

● Verifying deployment

Tapping it may show:

Deploy project

State
Running

Current
Verify deployment

Completed
✓ Build
✓ Upload

Next
○ Health check

[ Pause ]
[ Cancel ]

Do not turn the chat into a large project-management dashboard.

==================================================
NATURAL LANGUAGE REMAINS PRIMARY
==================================================

Buttons are convenience controls.

They are NOT the only way to control the task.

The user can communicate naturally in chat.

==================================================
NO FAKE "BOSS" ROLEPLAY
==================================================

Lonora should feel like a supervisor because it actually supervises durable work.

Do not achieve this merely by adding conversational phrases such as:

"Let me check the cameras."

unless the Agent actually inspects task state.

Behavior must be grounded in runtime reality.

==================================================
TRUTHFULNESS
==================================================

The Agent must not say:

"I'm almost finished"

unless task state supports that conclusion.

The Agent must not say:

"The deployment succeeded"

until verified.

The Agent must not say:

"I'm checking"

without actually inspecting.

The Agent must not claim a Subagent completed if it is still running.

==================================================
STATUS FRESHNESS
==================================================

Status inspection must include a timestamp or freshness concept internally.

If state is stale, refresh it before claiming current progress when feasible.

==================================================
FINANCIAL TASKS
==================================================

The same Task Runtime should support Super Bot and trading goals where appropriate.

However, financial execution retains stricter controls.

Natural language interpretation must never bypass:

Trading ON/OFF
Emergency Stop
execution authorization
risk policy
idempotency
journal
reconciliation

==================================================
SUPER BOT EXAMPLE
==================================================

Super Bot is monitoring gold.

User:
"What are you doing?"

Agent inspects active goal/watch state.

Response:

"I'm waiting for price to return to the H1 trendline. The entry confirmation has not formed yet."

Later:

User:
"What's missing?"

Agent inspects current setup.

Response:

"Price reached the area. I'm still waiting for the M15 confirmation."

These answers must come from real Watch/Goal state.

==================================================
TASK + WATCH RELATIONSHIP
==================================================

A long-running Task may transition into WAITING based on a dynamic Watch.

Example:

Task:
Wait for trading setup

State:
WAITING

Reason:
MARKET_CONDITION

Watch:
M15 bullish confirmation

When Watch becomes CONFIRMED:

wake Task

revalidate

continue

==================================================
DATABASE DURABILITY
==================================================

Persist enough state so that:

browser close does not stop work

mobile close does not stop work

worker restart does not lose the Task

Gateway restart does not silently duplicate execution

conversation restart can inspect the same Task

==================================================
OBSERVABILITY
==================================================

For every long-running Task, make it possible to inspect:

who created it

which Agent owns it

which Thread it belongs to

current state

current phase

current plan revision

current Run

parent/child relationships

last checkpoint

waiting reason

last meaningful event

last error

next action when known

==================================================
TESTING REQUIREMENTS
==================================================

Add strong automated coverage for at least:

1. Long-running Task continues while user asks a status question.

2. Status question receives current state without interrupting work.

3. No keyword matching is required for status understanding.

4. Natural paraphrases resolve to the same semantic task intent.

5. Contextual reference resolves correct active Task.

6. Ambiguous destructive reference asks for clarification.

7. Unrelated conversation does not alter active Task.

8. Steering modifies pending work.

9. Steering does not rewrite already completed work.

10. Steering during current step applies immediately only when safe.

11. Otherwise steering applies at safe checkpoint.

12. Pause reaches safe checkpoint.

13. Resume continues from checkpoint.

14. Resume does not repeat completed steps.

15. Cancel prevents new work.

16. Cancel does not corrupt external operation state.

17. Worker restart recovers active Task.

18. Waiting Task wakes from an event.

19. Waiting Task does not continuously consume Agent reasoning.

20. Subtask continues while main Agent answers user.

21. Status includes child task state.

22. Recoverable failure can resume.

23. Retry policy respects attempt limits.

24. Ambiguous external action is reconciled instead of blindly retried.

25. Duplicate Run does not duplicate external mutation.

26. Task event history remains durable.

27. Internal events do not spam chat.

28. Working indicator reflects real phase.

29. Composer remains usable while Task runs.

30. Multiple Tasks can coexist.

31. User can naturally refer to one of several Tasks.

32. Server rejects invalid task transition even if model proposes it.

33. Trading safety remains authoritative.

==================================================
NO-KEYWORD TESTING
==================================================

Specifically test intent understanding using paraphrased, indirect, and contextual messages.

Do NOT make tests pass by adding those exact strings to a phrase dictionary.

The implementation should demonstrate that behavior comes from semantic/contextual interpretation.

Tests should include variations in:

Arabic
English
short references
follow-up references
incomplete conversational phrases

where supported by the Agent.

==================================================
DO NOT BUILD A SECOND ORCHESTRATOR
==================================================

Lonora already has:

Gateway
Runs
Events
Steering
Subagents
Goals
Wakes

Extend these coherently.

Do not introduce another independent queue/runtime/orchestrator unless the current architecture objectively requires it.

==================================================
QUALITY GATES
==================================================

Run relevant project checks.

At minimum where applicable:

pytest
ruff
pyright

pnpm lint
pnpm typecheck
pnpm build

Also run existing Run/streaming/steering/subagent/market/trading checks.

==================================================
DEFINITION OF DONE
==================================================

This task is complete only when:

- Long-running work no longer blocks conversation.
- Same Agent can talk while work continues.
- Status inspection is grounded in actual runtime state.
- User can steer active work conversationally.
- No fixed user phrases are required.
- No keyword routing is used as the primary mechanism.
- No regex synonym system is used as the primary intent mechanism.
- Contextual references to tasks work.
- Ambiguous dangerous instructions require clarification.
- Task state is durable.
- Run attempts are distinct from logical Task identity.
- Steps/checkpoints are resumable.
- Pause works safely.
- Resume continues from checkpoint.
- Cancel works safely.
- External ambiguous mutations reconcile before retry.
- Waiting Tasks sleep and wake from events.
- Subtasks can continue independently.
- User can inspect Subtask progress.
- Multiple Tasks can coexist.
- UI working state derives from real phases.
- Composer remains interactive during background work.
- Worker restart recovery works.
- Internal events are observable but do not spam chat.
- Server validates all state transitions.
- Trading safety remains unchanged.
- Relevant tests and checks pass.

==================================================
GIT WORKFLOW
==================================================

Work on a dedicated branch.

Do not merge directly into main.

Use logical commits.

Possible commit themes:

feat(tasks): add durable long-running task lifecycle
feat(tasks): separate logical tasks from run attempts
feat(tasks): add checkpoints and safe resume
feat(tasks): add contextual steering
feat(agent): support conversational task inspection during execution
feat(tasks): add waiting and wake semantics
feat(tasks): add safe pause and cancellation
feat(tasks): add subtask progress aggregation
feat(ui): expose live task activity without blocking chat
test(tasks): cover steering recovery and concurrent conversation

Use names that match the actual codebase.

==================================================
FINAL RESPONSE
==================================================

Do not return only an architecture proposal.

Implement first.

When finished, provide a concise completion report containing:

- Branch
- Commits
- Existing components reused
- Task lifecycle implemented
- Task/Run distinction
- Checkpoint/resume behavior
- Contextual intent/steering implementation
- Confirmation that keyword routing is not used as the core mechanism
- Status-query behavior
- Concurrent conversation behavior
- Pause/cancel behavior
- Restart recovery
- Subtask behavior
- Tests/checks passed
- Real remaining blockers

==================================================
FINAL PRINCIPLE
==================================================

Lonora must understand intent, not commands.

The user should speak naturally.

The Agent should understand the conversation.

The runtime should validate the action.

The Task should continue independently.

The conversation should remain alive.

The Agent should always be able to inspect where the work really is.

The experience should feel like:

User:
"Do this."

Lonora starts working.

User:
"Where are we?"

Lonora checks real state and answers immediately.

The work continues.

User:
"Leave that part. Finish the rest."

Lonora understands the intended change, applies it safely, and continues.

User:
"Pause for now."

Lonora reaches a safe checkpoint and pauses.

User:
"Continue."

Lonora resumes from where it stopped.

No magic words.

No fixed phrases.

No fake progress.

No frozen conversation.

No starting over unnecessarily.

One persistent Agent supervising real persistent work.