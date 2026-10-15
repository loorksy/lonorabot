TITLE:
Refactor Lonora Skills Runtime into a Production-Grade Skill System

CONTEXT:
We are working on the Lonora project.

The current Skills system exists, but it is still too simple and does not yet meet the standard expected from a production-grade agent runtime.

Also review:
https://github.com/affaan-m/ECC

Use ECC as a reference for how mature systems structure skills, instructions, validation, manifests, and reusable components.

Do NOT copy ECC blindly.

Lonora is not a coding-assistant framework.

Lonora is a persistent agent runtime with:
- long-running agents
- memory
- tools
- routines
- collaboration
- market access
- charts
- trading
- financial execution

Therefore, Lonora requires a stricter runtime contract than ECC, especially for tool access, activation, provenance, context budgeting, and financial safety.

This is an implementation task.

Do not stop after writing a review or architecture proposal.

The required process is:

REVIEW
→ UNDERSTAND
→ DESIGN
→ IMPLEMENT
→ INTEGRATE
→ VALIDATE
→ TEST
→ FIX

==================================================
CURRENT PROBLEM
==================================================

Lonora currently loads built-in skills from:

packages/agent-runtime/resources/skills/*/SKILL.md

The current flow is approximately:

built_in_skills()
    ↓
enabled_skills()
    ↓
skill_context()
    ↓
all enabled skills are injected into the Agent system context

This means the runtime currently tends to inject all enabled Skills into every Run.

That creates several problems:

- Skills unrelated to the current task are loaded.
- Context size grows unnecessarily.
- Instructions from unrelated domains can interfere with each other.
- Skill conflicts are not explicitly managed.
- There is no real skill-routing system.
- Skill metadata is too weak.
- There is no dependency model.
- There is no conflict model.
- There is no risk classification.
- There is no required-tool contract.
- There is no activation policy.
- There is no context budget.
- There is no explicit provenance model.
- Installed skills can override built-in skills with the same name without a sufficiently explicit trust policy.

The current AgentSkill contract is approximately:

name
content
enabled

That is not enough for a production-grade agent system.

==================================================
EXPECTED BEHAVIOR
==================================================

Transform the current Skills system into a real Skill Runtime.

The target flow should be:

Run
 ↓
Intent / Trigger / Runtime Context
 ↓
Skill Resolver
 ↓
Candidate Skills
 ↓
Eligibility Check
 ↓
Dependency Resolution
 ↓
Conflict Resolution
 ↓
Tool Availability Check
 ↓
Risk / Policy Check
 ↓
Context Budgeting
 ↓
Selected Skills
 ↓
Load only the selected Skills
 ↓
Agent Context

The runtime must NOT inject every enabled Skill into every Run.

Examples:

"Analyze gold"
→ market-analysis
→ chart-analysis

"What do you remember about my project?"
→ memory

"Execute my trading plan"
→ trading-goal
→ trade-management

"Research this topic"
→ research

==================================================
CORE DESIGN PRINCIPLE
==================================================

Separate these three concepts clearly:

1. Policy
2. Skill
3. Playbook

--------------------------------------------------
POLICY
--------------------------------------------------

Policies are system rules that the Agent cannot disable, override, or bypass.

Examples:

- Do not expose secrets.
- Respect Trading OFF.
- Respect Emergency Stop.
- Never blindly retry ambiguous financial mutations.
- Preserve exact broker symbol identity.
- Never claim a trade succeeded before receiving confirmed broker evidence.
- Respect cancellation.
- Respect owner authority.
- Treat untrusted content as untrusted.

These are not Skills.

These are runtime laws.

They should remain enforced both:

- in instructions
- and, where applicable, server-side in code

--------------------------------------------------
SKILL
--------------------------------------------------

A Skill is task-specific knowledge and workflow guidance.

Examples:

- memory
- research
- market-analysis
- chart-analysis
- trade-management
- position-management
- market-watch

Skills should be loaded only when relevant.

--------------------------------------------------
PLAYBOOK
--------------------------------------------------

A Playbook is a multi-stage operational workflow.

Examples:

- autonomous-trading-goal
- trade-entry
- position-monitoring
- trade-exit
- ambiguous-execution-recovery
- market-analysis-cycle

Playbooks are not general policies and not simple Skills.

They represent stateful execution procedures.

==================================================
TARGET RESOURCE STRUCTURE
==================================================

Refactor the current resources into a clearer structure similar to:

packages/agent-runtime/
└── resources/
    ├── constitution/
    │   ├── identity.md
    │   ├── tool-policy.md
    │   ├── memory-policy.md
    │   ├── security-policy.md
    │   ├── collaboration-policy.md
    │   └── trading-policy.md
    │
    ├── skills/
    │   ├── market-analysis/
    │   │   ├── SKILL.md
    │   │   ├── skill.yaml
    │   │   ├── references/
    │   │   └── examples/
    │   │
    │   ├── chart-analysis/
    │   │   ├── SKILL.md
    │   │   ├── skill.yaml
    │   │   ├── references/
    │   │   └── examples/
    │   │
    │   ├── trade-management/
    │   │   ├── SKILL.md
    │   │   ├── skill.yaml
    │   │   ├── references/
    │   │   └── examples/
    │   │
    │   ├── trading-goal/
    │   ├── position-management/
    │   ├── market-watch/
    │   ├── research/
    │   └── memory/
    │
    ├── playbooks/
    │   ├── autonomous-trading-goal/
    │   ├── trade-entry/
    │   ├── position-monitoring/
    │   ├── trade-exit/
    │   ├── ambiguous-execution-recovery/
    │   └── market-analysis-cycle/
    │
    ├── schemas/
    │   ├── skill.schema.json
    │   └── playbook.schema.json
    │
    └── registry/
        ├── skills.yaml
        └── playbooks.yaml

Do not create directories blindly if the existing project architecture suggests a cleaner equivalent.

Preserve existing correct behavior where possible.

==================================================
SKILL MANIFEST
==================================================

Every Skill must have a machine-readable manifest.

For example:

skill.yaml

The exact schema may be adjusted to fit the project, but it should support concepts similar to:

id
version
title
description
source
stability
activation
risk_class
required_capabilities
required_tools
dependencies
conflicts
priority
context_budget

Example:

id: market-analysis
version: 1.0.0
title: Market Analysis
description: Analyze a verified broker market using current sourced data.

owner: lonora-core
source: builtin
stability: stable

activation:
  mode: automatic
  intents:
    - analyze_market
    - market_outlook
    - technical_analysis

risk:
  class: read_only

capabilities:
  requires:
    - market.read
    - chart.read

tools:
  allow:
    - market_symbols
    - market_instrument
    - market_quote
    - market_candles
    - chart_inspect
    - chart_snapshot

dependencies:
  - chart-analysis

conflicts: []

context:
  priority: 60
  max_tokens: 2500

Do not treat this exact example as mandatory syntax.

Design the manifest around Lonora's existing contracts and runtime.

==================================================
SKILL.md CONTENT STANDARD
==================================================

SKILL.md should remain LLM-facing instructions.

Do NOT turn SKILL.md into a configuration file.

A production-grade SKILL.md should support sections such as:

Purpose

When to Activate

When NOT to Activate

Preconditions

Required Evidence

Workflow

Decision Rules

Tool Usage

Failure Handling

Anti-Patterns

Output Contract

Examples

Related Skills

Keep the content concise enough to avoid unnecessary context cost.

==================================================
REQUIRED IMPLEMENTATION CHANGES
==================================================

1. Add machine-readable manifests for every built-in Skill.

2. Add manifest validation.

3. A Skill with an invalid manifest must not silently enter the runtime.

4. Refactor the existing Skills runtime components.

Review and evolve:

loader.py
registry.py
resolver.py
runtime.py

Introduce concepts equivalent to:

SkillDefinition
SkillManifest
SkillRegistry
SkillResolver
SkillContextBuilder

Use naming consistent with the existing codebase.

5. Do not inject all Skills into every Run.

6. Select only relevant Skills.

7. Add dependency resolution.

8. Add deterministic conflict resolution.

9. Add tool-availability checks.

10. Add capability checks.

11. Add context budgeting.

12. Add versioning.

13. Add source/provenance.

14. Add risk classification.

15. Add activation modes.

At minimum:

automatic
explicit
trigger_based

16. Add priority handling.

17. Add stable diagnostics for why a Skill was selected or rejected.

==================================================
DETERMINISTIC ACTIVATION
==================================================

Do not make Skill selection depend only on an LLM guess.

Use deterministic runtime signals wherever possible.

Examples:

- run trigger
- explicit requested skill
- available tools
- thread type
- group context
- routine trigger
- subagent trigger
- goal type
- market binding
- trading goal state
- required capabilities
- currently available broker connection
- whether a chart context exists

LLM-based classification may be used as a secondary signal if necessary, but not as the only source of truth.

==================================================
TOOL GATING
==================================================

A Skill must not be loaded if its required tools are unavailable.

Example:

market-analysis may require:

market_symbols
market_instrument
market_quote
market_candles

trade-management may require:

account_read
trade_execute
trade_reconcile

If the required tools are unavailable:

- do not silently load the Skill
- return a clear rejection reason
- record diagnostics

==================================================
DEPENDENCIES
==================================================

Support explicit dependencies.

Example:

trade-management
depends_on:
  - market-analysis

If a dependency cannot be satisfied, the dependent Skill must not be loaded.

Do not allow circular dependency graphs.

Validate them.

==================================================
CONFLICTS
==================================================

Support explicit conflicts.

Conflict resolution must be deterministic.

Possible factors:

- higher priority
- explicit user request
- built-in safety policy
- trigger type
- risk class

Do not resolve conflicts randomly or implicitly.

==================================================
RISK CLASSIFICATION
==================================================

Add a clear risk model.

Examples:

read_only
state_mutating
external_action
financial

Do not let a financial Skill automatically bypass server-side financial controls.

The runtime metadata is descriptive and useful for gating, but server controls remain authoritative.

==================================================
SOURCE / PROVENANCE
==================================================

Every Skill should identify where it came from.

Examples:

builtin
owner
installed
external

Do not allow an installed Skill to silently replace a built-in Skill.

Implement an explicit override policy.

For example:

- reject duplicate IDs by default
- allow trusted override only when explicitly configured
- record provenance and override reason

Do not keep the current implicit shadowing behavior.

==================================================
INSTALLED SKILL COMPATIBILITY
==================================================

Do not break existing installed agent Skills.

Review the existing AgentSkill persistence contract.

Introduce one of:

- migration
- compatibility adapter
- legacy SkillDefinition wrapper

Existing skills should continue to work while the new runtime is introduced.

However, legacy Skills should be clearly identified as legacy/untyped until upgraded.

==================================================
CONTEXT BUDGET
==================================================

Each Skill should define or inherit a context budget.

The runtime should not inject unlimited Skill content.

Support:

- priority
- max tokens or equivalent budget
- truncation or exclusion rules
- deterministic ordering

A low-priority Skill should not push critical policies out of context.

==================================================
POLICY LAYER
==================================================

Move immutable rules out of Skills.

Create a constitution/policy layer.

The policy layer should be loaded independently of Skill selection.

Examples:

identity
tool policy
memory policy
security policy
collaboration policy
trading policy

These must not be treated as optional Skills.

==================================================
TRADING_CONTEXT.MD REFACTOR
==================================================

The current trading_context.md contains too many responsibilities.

It currently mixes:

- immutable trading policy
- broker usage instructions
- market analysis procedure
- execution procedure
- MetaApi-specific guidance
- chart guidance
- approval rules

Split those responsibilities.

A target direction is:

constitution/trading-policy.md
    ↓
immutable rules

skills/market-analysis/
    ↓
market analysis workflow

skills/trade-management/
    ↓
trade execution and management workflow

playbooks/ambiguous-execution-recovery/
    ↓
uncertain financial mutation recovery

references/metaapi/
    ↓
MetaApi-specific operational references

Preserve the existing correct behavior during the migration.

Do not remove important trading constraints.

==================================================
METAAPI SEPARATION
==================================================

MetaApi-specific implementation details must not become part of the Agent constitution.

MetaApi is an adapter/provider implementation.

The Agent should reason in broker-neutral terms whenever possible.

For example:

Broker Adapter
→ MetaApi

not:

Agent core policy
→ MetaApi-specific assumptions

Keep exact broker symbol handling and execution safety intact.

==================================================
PLAYBOOK RUNTIME
==================================================

Introduce or prepare a clear Playbook model for stateful workflows.

At minimum support the architecture needed for:

autonomous-trading-goal
trade-entry
position-monitoring
trade-exit
ambiguous-execution-recovery
market-analysis-cycle

A Playbook may contain:

id
version
state model
entry conditions
required skills
required tools
transitions
terminal states
recovery behavior

Do not implement an unnecessary generic workflow engine if Lonora already has Goals, Runs, Routines, Wakes, or state machines that can express this cleanly.

Integrate with existing primitives.

==================================================
OBSERVABILITY
==================================================

Record enough information to debug Skill selection after a Run.

At minimum expose or persist:

selected_skill_ids
skill_versions
skill_sources
selection_reason
rejected_skills
rejection_reason

This may live in:

run metadata
runtime diagnostics
events

Choose the location that best matches existing architecture.

The selection must be inspectable and reproducible after an incident.

==================================================
CONTEXT BUILDER
==================================================

Update the Agent Context Builder.

The new flow should be approximately:

Base Policies
+
Agent Instructions
+
Binding Context
+
Memory
+
Scratchpad
+
Selected Skills
+
Reply Context
+
Wake Context
+
Goal Context
+
Group/Subagent Context
+
History
+
Attachments

Do NOT restore the old behavior of blindly injecting every Skill.

==================================================
EXAMPLE EXPECTED SELECTION
==================================================

Task:

"What do you remember about my project?"

Expected:

Policies
+
memory

Not:

memory
research
market-analysis
chart-analysis
trade-management

--------------------------------------------------

Task:

"Analyze XAUUSDm on the 1h chart"

Expected:

Policies
+
market-analysis
+
chart-analysis

--------------------------------------------------

Task:

"Open a trade based on the current plan"

Expected:

Policies
+
trading-goal
+
trade-management
+
only the dependencies actually required

--------------------------------------------------

Task:

"Search the web for the latest central bank statement"

Expected:

Policies
+
research

==================================================
VALIDATION
==================================================

Add validation for:

- manifest schema
- duplicate IDs
- invalid versions
- missing dependencies
- circular dependencies
- invalid conflicts
- unknown tools
- unsupported capability requirements
- invalid context budgets
- invalid activation modes
- illegal built-in overrides

Fail early during startup/build where appropriate.

==================================================
TEST COVERAGE
==================================================

Add or update tests for at least:

- memory-only task
- market-analysis task
- chart-analysis task
- trade-management task
- routine-triggered task
- subagent-triggered task
- explicit Skill request
- installed Skill
- disabled Skill
- legacy Skill compatibility
- invalid manifest
- missing dependency
- circular dependency
- conflicting Skills
- unsupported required tool
- duplicate Skill ID
- built-in override attempt
- context budget enforcement
- deterministic ordering
- observability metadata

Do not add only superficial unit tests.

Test the actual Runtime → Resolver → Context Builder integration.

==================================================
REFERENCE PHILOSOPHY
==================================================

Use ECC for ideas such as:

- structured Skills
- explicit activation guidance
- anti-patterns
- reusable instructions
- manifests
- validation
- organized references
- examples

But Lonora additionally requires:

- runtime Skill selection
- deterministic activation
- provenance
- tool gating
- capability gating
- risk classification
- financial safety
- context budgeting
- runtime diagnostics
- compatibility with persistent Agents and Runs

==================================================
IMPLEMENTATION RULES
==================================================

Before changing code:

1. Inspect the current Lonora implementation.
2. Find all callers of the current Skills runtime.
3. Inspect the database Skill model.
4. Inspect the contracts.
5. Inspect Context Builder.
6. Inspect Run metadata.
7. Inspect tool registry.
8. Inspect trading policies.
9. Inspect installed Skill behavior.

Then implement.

Do not rewrite working systems unnecessarily.

Refactor incrementally.

Do not create duplicate abstractions.

Do not leave production paths as:

pass

TODO

NotImplementedError

fake response

unless the project intentionally uses a test-only fake.

==================================================
DO NOT BREAK SERVER-SIDE SAFETY
==================================================

Instruction refactoring must not weaken server-side controls.

In particular:

- Trading OFF remains server-authoritative.
- Emergency Stop remains server-authoritative.
- Financial idempotency remains server-authoritative.
- Execution journal remains server-authoritative.
- Reconciliation remains server-authoritative.
- Exact broker symbol identity remains preserved.
- Secrets remain inaccessible to model context.

Skills and prompts guide the Agent.

They are not the security boundary.

==================================================
QUALITY GATES
==================================================

Run all relevant project checks.

For Python:

pytest
ruff
pyright

For Web/TypeScript when affected:

pnpm lint
pnpm typecheck
pnpm build

Also run any repository-specific validation already present.

Fix regressions caused by this work.

==================================================
DEFINITION OF DONE
==================================================

Do not consider the task complete until:

- Every built-in Skill has a valid manifest.
- Built-in Skills pass validation.
- Policies are separated from Skills.
- Playbooks have a clear model or integration path.
- Runtime no longer injects all Skills into every Run.
- Relevant Skills are selected deterministically.
- Dependencies work.
- Conflicts work.
- Required-tool gating works.
- Capability gating works.
- Context budgeting works.
- Provenance is recorded.
- Versions are recorded.
- Legacy installed Skills continue to work.
- Silent built-in override is eliminated.
- Context Builder uses selected Skills only.
- Skill selection is observable.
- Trading safety remains intact.
- Tests pass.
- Lint/type checks pass.
- No critical TODO remains.

==================================================
GIT WORKFLOW
==================================================

Work on a dedicated branch.

Do not merge into main.

Make logical commits.

Example commit themes:

refactor(skills): add typed skill manifests
feat(skills): add deterministic runtime resolver
feat(skills): add dependency and conflict validation
refactor(prompts): separate immutable policies from skills
feat(playbooks): add stateful playbook contracts
test(skills): cover resolver and context integration

Use names consistent with the actual repository.

==================================================
FINAL RESPONSE
==================================================

Do not return a long architecture report instead of implementation.

Implement first.

After implementation, return only a concise completion report containing:

- Branch
- Commits
- Main files changed
- What was implemented
- One or two examples of Skill selection before vs after
- Tests/checks that passed
- Any real blocker that remains

If the task is not fully complete, do not claim completion.

State exactly what remains and why.

==================================================
FINAL PRINCIPLE
==================================================

The goal is not to create a folder full of Markdown prompts.

The goal is to build a real, inspectable, deterministic, production-grade Skill Runtime.

Lonora should move from:

Markdown Skill Loader

to:

Validated Skill Registry
        ↓
Deterministic Resolver
        ↓
Dependency / Conflict Engine
        ↓
Tool / Capability Gating
        ↓
Context Budgeting
        ↓
Selected Skill Context
        ↓
Agent Runtime

Do the implementation now.