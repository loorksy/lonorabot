# Vision

Lonora exists so people can own trading teammates that persist, understand their
objectives, observe real markets, and finish authorized work beyond a single chat.
It provides one durable home for each Agent's identity, conversation, memory,
procedures, schedules, chart state and trading goals.

## Current delivery focus

The next product milestone is one dependable trading teammate, measured through
one complete mission. The owner's journey is: connect an account, describe an
objective, authorize management once when wanted, and follow actual results with
a directly accessible stop control. Internal Task, Goal and grant distinctions
must not become instructions the owner has to learn.

Reuse the current Agent loop, memory, progressive procedures, durable work and
financial executor. Resolve competing management paths and test conversational
continuity before expanding capability families. The acceptance sequence is:
understand -> inspect -> plan -> act or wait -> verify -> remember -> resume.
Choosing not to trade is a valid result when supported by current evidence.

Each Agent should have private persistent working state and isolated computation
when needed. A dedicated always-running desktop is not a prerequisite. Add visual
computer interaction only for an identified task that needs it. Model quality,
context and complete feedback determine useful behavior; more infrastructure or
longer instructions do not establish intelligence or profitable trading.

The concrete acceptance priorities and current gaps are maintained in
[the existing product requirements](docs/lonora-specs/AUTONOMOUS_TRADING_PRODUCT_REQUIREMENTS.md).
This focus sets implementation order; it does not claim the mission is verified.

## Persistent trading teammates

An Agent is a continuing identity with one primary visible conversation. Text,
voice, background work and collaboration use that same Agent and owned state.
A Personal Agent can inspect the owner's accounts and markets. A specialist
retains its owner-selected exact account and symbol, including broker suffixes.
No account, instrument, risk amount or autonomous mode is chosen by default.

The Agent works toward the owner's objective and asks only for information,
judgment, authorization or protected input that it actually needs. It remembers
prior answers, corrects its understanding and resumes persisted work after a wake.
A brief acknowledgment is not completion. Monitoring means a saved watch or
scheduled review, not a promise to keep thinking after the conversation closes.

## Calm on the surface, rigorous underneath

Chat contains replies, useful progress, results and genuine requests for help.
Internal calls, execution attempts and orchestration are not the owner's burden.
Frontends express intent and render authoritative state; the server validates
ownership, controls, approval, execution, verification and recovery.
Routines remain simple scheduled prompts. Watches react deterministically to
market changes; the language model wakes for meaningful work rather than ticks.

Reports belong in delivered files, drawings in the persisted chart, and approved
orders in the broker account. A saved file does not prove it was viewed. A broker
acknowledgment does not prove the independently observed account matches the
intended change. Unavailable verification remains explicit.

## Explicit, bounded trust

Financial mutations pass through the existing Trading ON/OFF, Emergency Stop,
ownership, exact scope, immutable approval, preflight, operation identity and
journal boundaries. Super Bot is a mode of the same Agent. Autonomous authority
requires a current owner-authenticated account scope. Full management can leave
product quotas unset; optional owner limits remain explicit. One review is enough
for matching subsequent operations, and the owner can stop management directly.
Collaboration shares evidence without transferring financial authority.
Manual owner intervention wins over stale automation.

Uncertain financial effects reconcile before any retry. Shadow mode cannot mutate
the broker. No claim of profit, safety or success can substitute for evidence.
Facts, analysis and expectations remain distinguishable in every surface.

## Memory and procedures stay simple

Following nanobot, behavior, owner preferences, durable knowledge, conversation
checkpoints and reusable procedures have distinct homes. Lonora uses its existing
owned PostgreSQL records and versioned writes for those homes. It does not add
another memory database or a shared writable directory across owners.
Descriptions make procedures discoverable; detailed instructions load only when
needed. Procedures teach work and never grant tools, credentials or permission.

## Current product truth

Web and Expo mobile connect to one Python API and resident Gateway. Closing a
client does not terminate persisted watches, schedules or goals. Broker-neutral
contracts currently connect MetaApi or explicitly supplied simulation state.
Cloud charts, supported server indicators, attributed drawings, snapshots,
account reads, financial approvals and an execution journal already exist.
Provider routing is shared; available external services depend on configuration.
The Agent has a persistent analytical workspace with isolated shell/Python
execution, reviewed dependencies, artifact delivery and validated reusable
procedures. It has no general-purpose desktop or access to broker secrets from
that workspace. Broader strategy adaptation and native behavior still require
their own implementation and verification.

## What to resist

Resist disposable prompt presets, duplicated runtimes, visual workflow languages,
fake progress, invented prices, default trading pairs, repetitive consent questions,
opaque authority, model calls per tick and features without durable ownership.
Prefer a small shared implementation when it strengthens continuity, user control,
verified execution and a quiet experience. This file records current direction;
Git history records superseded decisions.
