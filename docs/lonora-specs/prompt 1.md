CODEX MASTER ENGINEERING MANDATE

Lonora — Agent-First Architectural Simplification, Autonomous Trading & Native Live Voice

Repository: https://github.com/loorksy/lonorabot

Architectural references:

- https://github.com/HKUDS/nanobot
- https://github.com/NousResearch/hermes-agent

Mission type: Full repository audit, architectural refactoring, implementation, integration, migration and verification.

Priority: Critical.

Execution requirement: Implement the architecture in working production code. An analysis-only response, a theoretical design, or superficial prompt modifications are not acceptable deliverables.

---

Mandatory General Agent Capabilities — Claude Code / Nanobot Parity

Lonora must implement or verify the following capabilities as first-class agent capabilities. Reuse existing infrastructure. Do not introduce duplicate runtimes, schedulers, gateways, memory systems, or orchestration frameworks.

1. Autonomous Intelligence and Execution

Lonora must provide:

- Natural-language understanding with complete conversational continuity.
- Model-driven multi-step reasoning and planning.
- Autonomous execution of authorized tasks.
- Dynamic tool discovery, selection, and invocation.
- Multi-tool execution within the same task.
- Bounded parallel tool execution when safe.
- Error diagnosis, recovery, retries, and alternative approaches.
- Long-running task execution with durable checkpoints.
- Task continuation after interruption, reconnection, or process restart.
- Context management, summarization, and retrieval.
- Persistent memory and previous-session recovery.

2. Scheduling and Workflow Automation

Lonora must support:

- One-time scheduled tasks.
- Recurring tasks and routines.
- Event-driven and condition-based automation.
- Dynamic workflow creation and modification.
- Workflow dependencies and parallel execution.
- Persistent workflow state and progress tracking.
- Automatic execution of appropriate next steps.
- Cancellation, pause, resume, and recovery.
- Hooks for tool events, task events, schedules, and workflow transitions.
- Verified completion and failure reporting.

Use Lonora's existing resident Gateway as the execution authority.

3. Universal Skills and Plugins

Lonora must support:

- Automatic discovery of available skills.
- Context-aware skill selection by the language model.
- Reading and executing compatible "SKILL.md" instructions.
- Creating, testing, and registering custom skills.
- A Universal Skills Importer for importing compatible Claude Code, Nanobot, and other Agent Skills packages directly from public GitHub repositories.
- Automatic Skill Adaptation for mapping imported skill instructions, scripts, dependencies, and data sources to Lonora's supported tools and trading interfaces without replacing the trading engine or expanding permissions.
- Common Claude Code and Agent Skills formats.
- Skill-relative paths and required dependency resolution.
- A Skill Dependency Manager for detecting, installing, pinning, validating, and isolating required Python packages and other dependencies.
- Skill Validation & Sandbox for static inspection, compatibility checks, controlled tests, and isolated execution before activation.
- A Skill Lifecycle Manager for installing, updating, disabling, rolling back, and removing skills.
- Plugin discovery and lifecycle management.
- Skill versioning and compatibility validation.
- Secure inspection and isolated execution of third-party code.
- A Trading Skill Builder for creating, testing, registering, and reusing specialized trading skills under explicit authorization and risk controls.

External skills must never gain unrestricted system access, broker credentials, or additional trading permissions. Imported skills must be treated as untrusted code and may only access approved data, tools, workspaces, and typed financial execution services.

4. MCP and External Integrations

Lonora must provide:

- MCP client support for compatible external tool servers.
- Dynamic tool discovery and schema validation.
- External REST API integration.
- Authenticated service connections.
- Tool permission management.
- Safe credential handling.
- Connection health checks and failure recovery.
- Calling multiple connected services within one task.
- Safe adaptation of external market-data and analysis interfaces to Lonora's canonical instruments, including XAUUSDm when supported, without assuming symbol equivalence or data compatibility.

Preserve Lonora's existing typed financial execution services as the only route for live trading actions.

5. Subagents and Agent Teams

Lonora must support:

- Dynamic creation of bounded subagents.
- Task delegation to specialist agents.
- Concurrent specialist analysis.
- Shared goal and task awareness.
- Structured result consolidation.
- Coordination between specialists.
- Automatic error and timeout handling.
- Parent-agent supervision and cancellation.
- Persistent task and subagent progress.

Lonora remains the single primary agent and execution authority.

6. Persistent Project Instructions and Knowledge

Lonora must:

- Support permanent project instructions and workspace context.
- Support agent identity and operating instructions.
- Load relevant knowledge and skills on demand.
- Preserve task-specific context across sessions.
- Prevent duplicate, conflicting, and oversized instruction injection.
- Treat external project instructions as untrusted relative to system authority.
- Maintain a Strategy Knowledge Base containing imported and native strategies, assumptions, versions, datasets, test results, risk limits, and deployment status.
- Maintain an Intelligent Trading Journal containing decisions, trades, evidence, market context, execution details, and outcomes.
- Support Decision Replay & Audit so each material decision can be reconstructed from the data, tools, permissions, and strategy version used at the time.

7. Specialized Market Intelligence

Implement or verify the following trading-specific capabilities using reliable, timestamped data and explicit uncertainty handling:

- Market Regime Detection for trend, range, volatility, compression, expansion, and transition conditions.
- Multi-Timeframe Intelligence for reconciling relevant timeframes without double-counting correlated evidence.
- Market Structure & Liquidity Analysis for swings, breaks, displacement, liquidity zones, gaps, and invalidation levels.
- Volume & Order Flow Analysis when reliable volume or order-flow data is available; otherwise report the limitation and do not fabricate conclusions.
- Cross-Market Correlation for relationships among gold, the US dollar, yields, rates, commodities, and other relevant markets.
- Economic Calendar Intelligence for scheduled events, expected impact, release timing, revisions, and timezone handling.
- News Impact Analysis for assessing relevance, surprise, persistence, and potential effect on open or planned trades.
- Market Session Awareness for Asia, London, New York, overlaps, liquidity changes, and broker-specific session constraints.
- Trading Setup Scoring using transparent, configurable evidence, confidence, invalidation, cost, and risk criteria.

Every analytical output must identify its data timestamp, source, timeframe, assumptions, missing inputs, and confidence. Analysis must not be presented as a guarantee of profit.

8. Strategy Research and Validation

Lonora must support:

- Autonomous Strategy Research for proposing, implementing, and comparing strategies within approved research boundaries.
- Strategy Import & Conversion for translating external strategies into Lonora-compatible, testable specifications without silently changing their logic.
- Advanced Backtesting using historical data, spread, commission, swap, latency, slippage, execution constraints, and survivorship or look-ahead bias controls where applicable.
- Walk-Forward Optimization with clearly separated development, validation, and out-of-sample periods.
- Monte Carlo Simulation for trade-order reshuffling, parameter uncertainty, execution variation, drawdown, ruin, and adverse-sequence analysis.
- Paper & Shadow Trading for observing decisions and simulated execution before live authorization.
- Strategy Performance Monitoring for detecting degradation, drift, data changes, abnormal losses, and breached limits, with automatic quarantine or suspension when configured thresholds are exceeded.
- Evidence-Based Strategy Improvement based on reproducible results and verified data rather than unsupported assumptions.
- Trade Performance Attribution for separating signal quality, sizing, timing, execution, costs, market regime, and operational causes of profit or loss.

No strategy may be promoted to live execution solely because it performs well on a single backtest or in-sample period.

9. Trading, Execution, and Account Risk

Lonora must provide:

- Intelligent Trade Lifecycle covering opportunity detection, validation, authorization, order submission, acknowledgement, monitoring, modification, partial closure, final closure, reconciliation, and post-trade recording.
- Dynamic Position Management for stops, targets, trailing logic, partial exits, and invalidation within explicit user and risk-manager authorization.
- Portfolio Exposure Management across instruments, strategies, directions, correlated positions, margin, leverage, and aggregate risk.
- Execution Quality Analysis for spread, slippage, latency, rejection, fill quality, commissions, swaps, and total transaction cost.
- Broker-Aware Execution for symbol specifications, contract size, precision, minimum distances, trading hours, margin rules, order types, and broker limitations.
- Risk Scenario Simulation for gaps, volatility shocks, correlated losses, liquidity deterioration, rejected orders, and consecutive-loss sequences.
- Broker & Market Data Recovery for safe reconciliation after data, network, broker, or Gateway interruption, with idempotency and protection against duplicate orders.
- Pre-trade, in-trade, and post-trade risk checks, including maximum loss, exposure, drawdown, stale-data, market-closure, and emergency-stop controls.
- Verification of broker state and reconciliation of local state with authoritative account state. An API request alone must never be treated as proof of successful execution.

Live trading remains disabled unless explicitly authorized through Lonora's existing financial authorization boundary. Imported or generated skills may propose actions but may not bypass approval, risk checks, typed services, or emergency controls.

10. Reporting, Learning, and Verification

Lonora must support:

- Automatic task progress summaries.
- Evidence-backed completion reports.
- Comparison of analytical outputs and strategies.
- Verification of tool results against actual execution state.
- Generated reports, files, charts, and structured artifacts.
- Traceability between user request, actions, evidence, and final result.
- Clear identification of unfinished work and external blockers.
- Recording strategy versions, data versions, configuration, permissions, and execution outcomes for reproducibility.
- Detection and reporting of discrepancies between intended, requested, acknowledged, and actually executed actions.
- Post-trade review, decision replay, audit export, and controlled strategy updates.

Mandatory Acceptance Tests

A. Universal Skills Import and Adaptation

Given the public repository:

"https://github.com/Jakeschincariol/day-trader-skill"

Lonora must be able to inspect the repository, enumerate its "SKILL.md" files and executable utilities, identify supported and unsupported components, resolve or report dependencies, and import only compatible skills into an isolated workspace.

It must validate the imported scripts, run controlled tests, adapt compatible data-source and instrument references to Lonora's canonical interfaces and XAUUSDm where technically supported, and clearly report any component that cannot be adapted. It must not replace the trading engine, bypass the Gateway, access broker credentials directly, or expand trading permissions.

B. End-to-End Specialized Trading Workflow

Using approved historical or paper data, Lonora must be able to:

1. Detect the current market regime and relevant market sessions.
2. Combine multi-timeframe structure, liquidity, volume or order-flow data when reliable, cross-market context, economic-calendar information, and news impact.
3. Score a potential setup with transparent evidence, costs, invalidation, and confidence.
4. Research or import a strategy and convert it into a testable Lonora-compatible specification.
5. Run realistic backtesting, walk-forward validation, and Monte Carlo analysis.
6. Start paper or shadow trading before any live authorization.
7. Simulate position sizing, portfolio exposure, execution quality, and adverse risk scenarios.
8. Record the decision and evidence in the trading journal and strategy knowledge base.
9. Produce a verified report identifying data limitations, assumptions, unfinished work, and recommended next steps.

C. Execution Safety and Recovery

In a controlled paper or explicitly authorized live environment, Lonora must demonstrate:

- Full trade lifecycle tracking.
- Dynamic position management within configured limits.
- Broker-aware validation.
- Reconciliation after Gateway restart, broker disconnection, stale data, rejected orders, and partial fills.
- Idempotent recovery without duplicate orders.
- Automatic suspension or escalation when risk limits, data-quality limits, or strategy-performance limits are breached.
- Decision replay showing the strategy version, inputs, tools, permissions, and evidence used for each material action.

D. Scheduling and Continuation

Lonora must be able to schedule authorized recurring market monitoring, persist workflow state, execute the appropriate next steps, report failures, and resume the workflow after a Gateway restart or temporary disconnection.

All acceptance tests must remain under Lonora's existing security, financial authorization, data-integrity, and execution boundaries.

Do not declare these capabilities complete because their names exist in source code. Demonstrate that they function end to end with automated tests, controlled integration tests, observable evidence, and explicit failure-path coverage.

---

1. Executive Mandate

Transform Lonora into a streamlined, highly capable, persistent, single-owner autonomous AI trading agent.

The target experience is:

Claude Code's operational flexibility + Nanobot's agent-centered architecture + Hermes Agent's extensible workspace, specialized for financial trading.

Lonora must behave like an intelligent agent, not a rigid workflow engine disguised as a chatbot.

The language model itself must be responsible for understanding natural-language requests, interpreting conversation context, reasoning, planning, selecting tools, executing work, evaluating results and deciding the next step.

The surrounding software must provide reliable capabilities, state, memory, tools, execution, persistence and financial authorization.

It must not attempt to replace the model's intelligence with thousands of hardcoded linguistic rules, conversational examples or overlapping orchestration layers.

Foundational principle:

«Build capabilities around the model. Do not program the conversation instead of allowing the model to understand it.»

The final product must remain one integrated system named Lonora.

Do not replace the application with Nanobot, Hermes or OpenClaw.

Do not introduce another independent agent framework, Gateway, financial engine, event bus or duplicate session system.

Study those projects, identify useful architectural techniques, and integrate the appropriate capabilities into Lonora's existing architecture.

---

2. Non-Negotiable Engineering Rules

1. Inspect the repository before modifying anything.
2. Inventory the entire first-party codebase and trace affected execution paths end to end.
3. Distinguish genuine infrastructure requirements from accidental complexity.
4. Remove unused code, redundant abstractions, duplicate policies and unnecessary orchestration only after verifying their dependencies.
5. Preserve working capabilities and existing user data.
6. Reuse existing services wherever possible.
7. Keep exactly one primary agent runtime and one resident Gateway.
8. Preserve the current broker execution infrastructure.
9. Preserve financial risk enforcement, emergency stop, order idempotency, durable journals and broker reconciliation.
10. Do not introduce special-case keyword classifiers to understand natural-language requests.
11. Do not build separate reasoning engines for voice, trading, Super Bot and ordinary chat.
12. Do not rely on prompt changes to solve problems that require changes to runtime code.
13. Do not introduce a second STT-to-LLM-to-TTS pipeline for live voice.
14. Do not silently weaken financial authorization or expand granted account scope.
15. Do not claim successful execution without verifiable evidence.
16. Make changes incrementally, with tests and reversible migrations.
17. Do not fabricate test results, completed implementations or production verification.
18. Do not stop after producing a report. Continue with implementation within the available environment and tool permissions.
19. Do not require predefined keywords, command phrases or fixed linguistic triggers for agent actions.
20. The agent must infer the appropriate response and available actions from the user's request, conversation context, current state and tool results.
21. The agent should proactively present relevant capabilities or next steps when appropriate, based on what it has actually observed and completed. It may naturally offer actions such as drawing analysis on a chart, identifying entry zones, marking stop-loss and target levels, comparing timeframes or creating monitoring, but these must not be implemented as mandatory phrases, keyword triggers or fixed dialogue branches.
22. All source code, identifiers, schemas, comments, logs, error messages, tool names and internal configuration must use English only. Arabic or other user-facing languages must be handled through localization resources, model instructions and runtime language negotiation, not embedded in source code.
23. The language model must be free to understand and answer in the language appropriate to the user and conversation context. The runtime must preserve the user's language preference and must not force Arabic, English or any other language unless explicitly configured by the owner.

The amount of code must decrease wherever complexity can safely be eliminated. New capabilities must not justify uncontrolled framework growth.

---

3. Mandatory Repository Audit

Start with the current "main" branch and inspect the actual implementation.

Prioritize these areas:

packages/agent-runtime/
packages/tools/
packages/trading/
packages/market/
packages/gateway/
packages/voice/
packages/adapters/
packages/adapter-kit/
packages/contracts/
packages/db/
packages/memory/
packages/security/
packages/channels/
apps/api/
apps/web/
apps/mobile/
tests/
docs/

Inspect the implementation and dependencies of these known files:

packages/agent-runtime/resources/system/lonora.md
packages/agent-runtime/resources/system/manifest.json
packages/agent-runtime/resources/bootstrap/SOUL.md
packages/agent-runtime/resources/bootstrap/AGENTS.md
packages/agent-runtime/resources/constitution/

packages/agent-runtime/src/lonora_agent/tool_loop.py
packages/agent-runtime/src/lonora_agent/model_runtime.py
packages/agent-runtime/src/lonora_agent/context/builder.py
packages/agent-runtime/src/lonora_agent/context/history.py
packages/agent-runtime/src/lonora_agent/skills/system_policy.py

packages/tools/src/lonora_tools/trading_decision.py
packages/tools/src/lonora_tools/trade.py
packages/tools/src/lonora_tools/super_bot.py
packages/tools/src/lonora_tools/market_watch.py
packages/tools/src/lonora_tools/search.py

packages/db/src/lonora_db/super_bot.py
packages/trading/src/lonora_trading/goals.py

packages/voice/src/lonora_voice/realtime.py
packages/voice/src/lonora_voice/sessions.py
packages/voice/src/lonora_voice/context.py
packages/voice/src/lonora_voice/transcript.py
packages/voice/src/lonora_voice/barge_in.py
packages/adapters/src/lonora_adapters/voice/realtime.py

apps/mobile/lib/voice-session.tsx
apps/mobile/lib/voice-transport.ts
apps/web/src/hooks/useVoice.ts
apps/web/src/lib/voice.ts

packages/core/src/lonora_core/public_reply.py

Also discover all additional call sites, schemas, tests, database models, authorization services, configuration sources and runtime entrypoints involved.

Do not assume that this list is exhaustive or that all paths remain unchanged.

Produce an internal dependency map identifying:

- What performs reasoning?
- What builds conversation context?
- What executes tools?
- What persists ongoing tasks?
- What invokes the broker?
- What grants and verifies financial authority?
- What provides live audio?
- What delegates live voice requests?
- What processes background monitoring?
- What creates notifications?
- What repeats or conflicts with another component?
- Where are user-facing language decisions made?
- Where are language-specific strings, prompts or templates embedded in code?
- Which components incorrectly depend on keywords, command phrases or fixed linguistic patterns?

Use this audit to drive actual code changes.

---

4. Simplify the Agent Architecture

Lonora must operate around one clear conceptual execution loop:

Observe → Reason → Plan → Act → Verify → Continue

The model decides which supported capabilities to use.

Implement or refine the runtime so that it:

- Receives the owner's message and correct conversational context.
- Allows the model to determine the user's intent naturally.
- Exposes appropriate tools and skill descriptions.
- Executes requested tool calls.
- Returns real execution results to the model.
- Continues until the task is complete, legitimately blocked or durably delegated for future work.
- Preserves task state across reconnections and Gateway restarts.
- Allows the model to choose relevant follow-up actions based on observed results rather than predefined keywords.
- Allows the model to answer in the user's language or the configured preferred language.

Do not insert a separate rule-based intent interpretation engine.

Do not impose fixed dialogue trees for words such as:

Yes
Okay
Continue
Go ahead

These are ordinary contextual language, and the language model must understand them through conversation history.

The runtime must provide accurate context rather than invent rules for each possible sentence.

Retain runtime controls for real concerns such as execution permissions, resource management, transaction integrity, cancellation, concurrency and risk.

---

5. Rebuild the Agent Instructions

The existing "lonora.md" has become excessively large and contains extensive operating rules and illustrative conversations.

Refactor it into a much smaller, coherent, maintainable instruction architecture.

Requirements:

- Retain essential identity, operating principles and truthful behavior.
- Remove repetitive behavioral examples and unnatural response templates.
- Remove hardcoded conversational decision trees.
- Remove conflicting instructions.
- Eliminate redundant policy duplication across system instructions, constitutions and skills.
- Keep technical tool contracts in code and schemas rather than copying them into large prompts.
- Load specialized knowledge only when relevant.
- Preserve financial security rules as enforced code, not merely text.
- Update policy manifests, hashes, loaders, snapshots and tests accordingly.
- Ensure existing persisted runs can resume safely after policy changes.
- Keep all source instructions, identifiers and internal text in English.
- Define language behavior generically: respond in the user's language or configured preference, without embedding Arabic dialogue examples or language-specific command triggers.
- Do not prescribe fixed phrases that the agent must say or recognize.
- Encourage the agent to offer relevant capabilities naturally when supported by the current task and available tools.

The core personality should encourage:

- Natural conversational intelligence.
- Proactive execution.
- Contextual understanding.
- Clear, helpful replies.
- Honest uncertainty.
- Reliable completion of work.
- Language-appropriate communication.
- Natural presentation of relevant next steps without keyword-driven behavior.

Do not enforce arbitrary one-sentence or two-sentence answers.

Concise when appropriate; detailed when useful; never robotic.

---

6. Repair Conversational Intelligence

The following behaviors are unacceptable:

Failure A

Owner: "Analyze gold and give me a recommendation."

Agent: "I can analyze it."

Owner: "Please do."

Agent: "What exactly would you like me to do?"

Failure B

Owner: "Monitor the one-minute gold chart and notify me when an entry appears."

Agent: "I will monitor it."

No verified persisted monitoring is created.

Failure C

Owner: "Who are you?"

Agent: "I am Boty."

Owner: "Is that all?"

Agent: "Yes, that is everything."

Fix these failures through better context continuity, model access to relevant state, appropriate instructions and reliable tool execution.

The agent must not pretend that a verbal acknowledgment constitutes task completion.

Provide lightweight, reliable distinctions between:

- Answered informational request.
- Completed action.
- Running durable task.
- Scheduled monitoring.
- Waiting for external conditions.
- Missing essential information.
- Failed operation.

These are execution states, not hardcoded language-intent classifications.

Review "public_reply.py" and remove overly broad lexical restrictions that suppress natural vocabulary or trigger unnecessary rewriting.

Continue protecting actual sensitive identifiers, credentials, secrets and internal data.

The agent may proactively suggest or initiate relevant supported actions when the task context warrants them, such as producing a chart artifact, identifying entry areas, marking risk levels, comparing timeframes or creating a watch. Such behavior must be selected by the model from available capabilities and verified state, not triggered by keyword lists or fixed phrases.

---

7. Eliminate Excessive WAIT Behavior

Investigate the actual decision engine, including:

packages/tools/src/lonora_tools/trading_decision.py
packages/agent-runtime/resources/skills/market-analysis/SKILL.md
packages/agent-runtime/resources/constitution/trading-policy.md

The current system may turn an otherwise useful decision into "WAIT" when any evidence component fails, including observations not strictly necessary to form a market bias.

Refactor decision handling into three separate concepts:

1. Market assessment: BUY bias, SELL bias, NEUTRAL or insufficient evidence.
2. Entry readiness: whether an actual trade setup has been confirmed.
3. Execution readiness: whether a trade can safely and lawfully be submitted under the current account authorization and risk controls.

Missing order history must not automatically erase an otherwise valid directional market assessment.

Conversely, a directional bias must never automatically authorize executing a trade.

The agent should proactively recover missing evidence where possible:

- Retry appropriate read-only observations.
- Use relevant alternative timeframes when technically justified.
- Inspect instrument specifications.
- Re-evaluate current conditions.
- Create conditional entry plans.
- Persist event-driven monitoring when requested.

If trading is not justified, explain the actual missing confirmation and what will happen next.

"WAIT" remains a legitimate outcome, but it must not become the default conversational escape route.

Never invent a quote, indicator, signal or tradable setup.

---

8. Introduce a Real Agent Workspace and Terminal

Build a first-class execution workspace inspired by Hermes Agent and Nanobot.

The main Lonora agent must be able to:

- Create and edit files.
- Execute shell commands.
- Run Python.
- Create research and analysis scripts.
- Install or access permitted analytical dependencies.
- Build custom indicators.
- Develop and backtest strategies.
- Evaluate statistical results.
- Debug failing analysis scripts.
- Save reusable analytical tools.
- Inspect generated artifacts.
- Reuse previous work.

The workspace must be available as ordinary agent tools.

It must not introduce another coding agent or independent autonomous runtime.

Use strong OS-level or container-level isolation:

- Separate workspace filesystem.
- Explicit resource limits.
- Bounded execution time and process count.
- Restricted network access by default.
- No host-level administrative privileges.
- No exposure of broker credentials or platform secrets.
- No uncontrolled access to other service data.
- Secure dependency installation policy.

Critical security boundary:

Generated shell commands and Python scripts must not place live broker orders directly.

Live financial operations must always use Lonora's existing typed, authorized and journaled trading services.

The agent is free to create analytical tools; it is not free to bypass financial execution controls.

Workspace tools must expose clear English schemas and descriptions. User-facing explanations and generated reports may use the user's language, but internal tool contracts and source code must remain language-neutral and English-only.

---

9. Self-Managed Skills and Tools

Allow Lonora to create and improve reusable skills from legitimate experience.

Capabilities should include:

- Identifying a missing analytical capability.
- Implementing a new workspace-based tool.
- Testing the tool.
- Registering it in the agent's reusable workspace.
- Documenting its purpose.
- Reusing it in later tasks.
- Disabling or revising defective skills.

Avoid complicated skill marketplaces or external agent registries.

Keep the system single-owner and straightforward.

Treat generated skill content as lower-trust instructions.

New skills cannot grant financial authority, alter execution safeguards or override the system's security boundaries.

Generated skills must not introduce keyword-based intent routing, language-specific command triggers or hardcoded user dialogue. They must describe capabilities and constraints in English and allow the model to decide when they are relevant.

---

10. Simplify Financial Authorization — One-Time Delegation

The owner must not have to approve every individual trade after enabling an appropriately scoped autonomous trading authorization.

Implement a clean, persistent authorization model:

Owner authorizes once → Agent operates independently within that authorization → Owner can revoke or change it.

The initial authorization must be authenticated and bound to explicit scope, such as:

- Trading account.
- Permitted instruments.
- Maximum volume and exposure.
- Per-trade and daily loss limits.
- Maximum concurrent positions.
- Permitted management operations.
- Expiration, if configured.
- Trading enabled/disabled state.

The user experience must remain simple.

Do not require the user to create a complicated Goal with every future trading step predeclared merely to delegate ordinary account trading responsibility.

Support adaptive strategy decisions within a durable, account-scoped authorization envelope.

The agent may open, modify and close positions without individual approvals only when the existing grant authorizes the exact action and all execution requirements are satisfied.

Authorization must be enforced server-side on every financial operation.

Retain:

- Emergency Stop.
- Risk ceilings.
- Revocation.
- Ownership and account isolation.
- Broker-state verification.
- Durable journals.
- Idempotent operations.
- Reconciliation after uncertain results.

Do not let model text, chat history, generated code, scripts or skills create or enlarge financial authority.

Material changes that increase granted risk or scope require fresh owner authentication.

Never promise profitability or guaranteed execution.

---

11. Unify the Agent and Super Bot

Lonora must have one primary agent identity.

Super Bot must become an operating capability of that agent, not a separate conversational brain.

Simplify Advisory, Supervised and Autonomous into understandable operating states, without separate duplicated trading workflows.

The owner should be able to express goals naturally in any supported language, for example:

"Monitor my gold account."
"Trade autonomously within my limits."
"Stop opening new positions."
"Manage my current positions."
"Find a scalping opportunity."
"Explain why you did not trade."

The agent determines which authorized tools and services are appropriate from context and current state.

The server validates every actual financial action.

Do not force the owner to navigate several internal modes or approval rituals for routine operations.

Retain explicit authority for actions affecting existing manual positions when that authority is required.

---

12. Persistent Goals and Proactive Market Work

Use the existing resident Gateway.

Improve persistent task planning so that an owner can provide a broad objective and the agent can create and maintain its own bounded implementation plan.

The agent should be able to:

- Research.
- Analyze.
- Build analytical tools.
- Backtest.
- Monitor.
- Act within authorization.
- Review results.
- Adapt strategies.
- Continue after application or call disconnect.
- Recover after process restart.

Do not require a fixed full plan before any meaningful work can begin.

Allow legitimate plan revisions without resetting the entire objective.

Use existing durable tasks, watches, schedules and runtime checkpoints.

Do not poll the LLM continuously when an event-driven wait is sufficient.

Never claim ongoing monitoring unless it has been successfully persisted and scheduled.

The agent may proactively surface relevant actions or options based on task progress and available evidence, but must not depend on predefined keywords or fixed user phrases.

---

13. Critical: Preserve GPT Live Native Voice Architecture

The current voice system uses GPT Live over WebRTC. This architecture MUST be preserved.

Do not replace it with a traditional:

STT → Text LLM → TTS

pipeline.

Do not introduce a redundant speech recognition provider or independent TTS engine into the primary live call path.

The user speaks directly with GPT Live through WebRTC.

GPT Live remains responsible for natural realtime audio understanding, turn-taking, speech output and conversational interaction.

Lonora's existing agent runtime remains responsible for persistent tools, trading, memory, financial permissions and durable work.

These are two interfaces to one agent identity and state, not two independent trading agents.

Audit the existing WebRTC and server-side sideband implementation, especially:

packages/voice/src/lonora_voice/realtime.py
packages/voice/src/lonora_voice/sessions.py
packages/voice/src/lonora_voice/context.py
packages/adapters/src/lonora_adapters/voice/realtime.py
apps/mobile/lib/voice-transport.ts
apps/web/src/lib/voice.ts

Verify current provider event contracts and supported delegation semantics before redesigning the integration.

Voice instructions, event schemas and internal logs must remain English-only. The live model may understand and respond in Arabic or another language according to the user's speech and configured language preference.

---

14. Critical: Fix the Live Voice Delegation Failure

This is a real observed user-facing bug.

Conversation:

Owner: "Give me a recommendation on gold."

Voice agent: "Okay, give me a moment."

A few seconds later:

Voice agent: "I did not understand your request. Could you repeat it?"

The owner already issued an understandable request.

The live model acknowledged the request, yet the backend delegation path may fail to reconstruct or deliver it.

Known implementation concern:

packages/voice/src/lonora_voice/realtime.py

The current delegation implementation assembles "session.input_transcript.delta" fragments and uses an offset-based completeness check.

If reconstruction is incomplete after five seconds, it returns a message equivalent to:

The full request was not transcribed.
Ask the user to repeat it before taking any action.

This failure behavior must be redesigned.

Mandatory objectives:

- Do not use arbitrary transcript-fragment timing as the authoritative definition of a completed voice instruction.
- Prefer documented semantic delegation or finalized-turn events where supported by the actual provider contract.
- Verify event identity, ordering and lifecycle.
- Maintain a reliable mapping between voice turns, delegated work and backend runs.
- Preserve the complete actionable request.
- Prevent duplicate execution.
- Handle delayed and out-of-order events.
- Support provider recovery and reconnect.
- Preserve partial utterance safety for financial actions.
- Distinguish genuine unintelligible speech from a synchronization or delegation transport failure.
- Never ask the owner to repeat an already understood request solely because the internal handoff failed.
- Do not silently submit partial or truncated financial instructions.
- Avoid indefinite waiting or retry loops.

If the provider protocol cannot supply a fully verified semantic request directly, implement a reliable, documented, bounded handoff strategy that preserves the native audio-first architecture.

Do not invent unsupported provider APIs or event names.

Add instrumentation that can prove which stage failed without storing raw microphone audio or leaking sensitive content.

The handoff must not depend on Arabic, English or any other language-specific keywords. It must use provider turn semantics, verified transcript state, model-generated structured delegation or equivalent transport-level evidence.

---

15. Natural, Continuous Voice Conversations

Voice must behave like a real ongoing conversation with the same Lonora agent.

Required behavior:

- Natural conversation in Arabic, English and other configured languages.
- Accurate turn-taking.
- Natural interruption and barge-in.
- No forced command words.
- No artificial "please repeat" loops.
- No invented progress.
- No loss of ongoing goals during a call.
- No loss of task progress after call termination.
- Seamless continuity between typed and spoken messages.
- Correct handling of short contextual instructions.
- Correct handling of a new instruction while older analysis is still running.
- Language selection based on the user's speech, conversation context and configured preference.

Example:

Owner: "Analyze gold."
Lonora: "I am reviewing the market."

Owner: "On the one-minute timeframe."

The agent must understand that the latest utterance modifies the ongoing analysis.

It must not start an unrelated task or ask the owner to repeat the original objective.

If work is genuinely running, GPT Live may provide a natural status acknowledgment while the same backend task continues.

The voice layer must never fabricate that work has started, completed or been scheduled.

Interrupting speech must not automatically cancel durable backend execution.

---

16. Proactive Outbound Calling

Add the capability for Lonora to initiate voice calls to the owner when genuinely necessary.

Implement two delivery categories.

A. Native in-app incoming calls — primary

Lonora should be able to initiate an incoming call experience on the owner's mobile application.

Requirements:

- Owner opt-in.
- Verified owner device registration.
- Authenticated incoming-call signaling.
- Push-based wake-up when supported.
- Native incoming-call UX appropriate to Android and iOS.
- Secure call acceptance and rejection.
- Reuse GPT Live/WebRTC for the actual conversation after connection.
- Correct handling of foreground, background and terminated-app states within platform restrictions.
- No fake incoming-call screen that works only while the application is already open.
- No duplicate simultaneous calls.
- Clear call state and timeout handling.
- Respect operating-system permissions and policies.

The existing mobile implementation appears to terminate active voice sessions on background transitions. Investigate and redesign lifecycle management as necessary.

B. Real telephone calls — optional integration

Provide an extensible implementation for calling a verified telephone number through an authorized telephony provider where configured.

Requirements:

- Explicit owner opt-in and verified destination.
- Legitimate telephony provider integration.
- Secure provider webhooks.
- Authentication and event verification.
- Clear call initiation, answer and end states.
- Bounded retries.
- Costs and rate controls.
- Reuse the underlying Lonora agent identity, task state and financial authorization.
- No silent fallback to a nonfunctional simulated phone call.

Do not claim real PSTN calling is operational without a configured provider and demonstrated end-to-end verification.

Calling policy

The agent may determine whether an event merits contacting the owner.

Examples:

- Critical account or risk conditions.
- Broker failures affecting active positions.
- Unexpected financial execution uncertainty.
- An urgent decision genuinely requiring owner intervention.
- Time-sensitive opportunities, if the owner explicitly enabled opportunity calls.

Ordinary market updates should normally use messages or notifications.

Implement owner preferences, quiet hours, deduplication and anti-spam safeguards.

Do not let generated scripts initiate arbitrary third-party phone calls.

Calling decisions must be based on event state, authorization and model reasoning, not keyword matching or fixed language phrases.

---

17. Trading Analysis and Strategy Research

Improve Lonora's ability to perform serious trading research.

Support:

- Live broker market data.
- Exact broker instrument symbols.
- Multiple relevant timeframes.
- Technical indicators.
- Market structure analysis.
- Entry, stop-loss and target planning.
- Position sizing from verified account and instrument parameters.
- Transaction costs, spread and slippage modeling.
- Historical backtests.
- Out-of-sample validation.
- Strategy comparison.
- Risk-adjusted performance evaluation.
- Persistent analysis reports.
- Strategy monitoring and revision.

The agent should be able to build missing analytical tools in its isolated workspace.

Avoid overfitting and misleading performance claims.

Live execution remains a separately authorized action.

The agent may decide to present relevant analytical outputs, including chart artifacts, entry areas, stop-loss and target levels or timeframe comparisons, when supported by the user's request, current analysis and available tools. These must be generated from verified data and must not be activated by keyword lists.

---

18. Charts and Visual Analysis

Ensure the agent can respond to requests for chart-based analysis, drawings, entry areas, risk levels, targets and timeframe comparisons.

Use existing chart and drawing capabilities whenever possible.

Return an actual generated chart, supported drawing artifact or precise actionable explanation of a genuine limitation.

Do not respond with silence, a fake image link or a claim that a chart was produced when none exists.

Preserve the current web/mobile chart experience.

Chart actions must be selected from available tools and current context. Do not implement special keyword classifiers for chart requests.

---

19. Internet Research and External Tools

Improve reliable external research without inventing unavailable access.

The agent should:

- Discover available web research capabilities.
- Use configured search when available.
- Fetch authorized sources directly when supported.
- Verify source freshness.
- Differentiate current evidence from historical context.
- Recover appropriately from unavailable providers.
- Clearly explain actual missing configuration when it cannot proceed.

Do not confuse an internal conversation search with an internet search.

Do not unnecessarily require the user to provide a link when a working authorized search capability already exists.

Research tool selection must be model-driven and context-aware, not based on language-specific keywords.

---

20. Memory, Skills and Collaboration

Preserve a coherent persistent identity and working memory across sessions.

Improve:

- Conversation recall.
- Long-running task context.
- Durable goal memory.
- Strategy and backtest history.
- Learned analytical procedures.
- Skill discovery.
- Tool creation and reuse.
- Subagent delegation.
- Collaboration evidence consolidation.
- User language preference and language continuity.

Subagents are optional internal workers, not separate mandatory authorities.

The primary Lonora agent remains responsible for the overall result.

Collaborators must not inherit, create or bypass financial permissions.

Avoid duplicate memories, repeated retrieval and unnecessary context inflation.

---

21. Simplify the User Experience

The owner should interact with one intelligent trading agent, not a collection of complicated internal modules.

Reduce visible complexity where possible.

Prioritize:

- Natural chat.
- Native live calls.
- Trading account overview.
- Simple continuous authorization settings.
- Positions and orders.
- Active goals and monitoring.
- Strategy workspace and results.
- Meaningful alerts.
- Minimal model/provider settings.
- Language preference and automatic language continuity.

Keep advanced technical diagnostics accessible without making ordinary operation depend on them.

Preserve the existing web/mobile design system and RTL support where applicable.

Do not rebuild the entire UI unnecessarily.

User-facing localization must be separated from source code. Do not embed Arabic text or other localized prose in internal Python, TypeScript, schemas, logs or tool definitions. Use localization resources, provider configuration and model language behavior for user-visible language.

---

22. Testing and Acceptance Criteria

Implement meaningful automated regression coverage and integration tests.

The following scenarios are mandatory.

Conversational tests

- A short contextual continuation continues a previously proposed analysis without requiring a keyword.
- A confirmation preserves the preceding relevant context.
- The agent does not repeatedly ask already answered questions.
- The agent explains its capabilities naturally.
- An actual requested action does not finish as a mere acknowledgment.
- The agent can respond in the user's language or configured language.
- The agent can proactively offer relevant supported actions without keyword classifiers.
- No source code or internal tool schema contains Arabic or other non-English text.

Trading tests

- Useful market bias survives irrelevant evidence failures.
- Insufficient entry evidence does not produce an invented trade.
- The agent proactively attempts relevant read-only recovery.
- "WAIT" includes meaningful next steps when applicable.
- One valid persistent authorization allows repeated authorized trades without per-trade approvals.
- Exceeding authorization or risk limits remains blocked.
- Revoked authorization blocks further financial execution.
- Ambiguous broker results do not create duplicate orders.
- Emergency Stop remains authoritative.
- Generated Python cannot bypass the trading engine.

Workspace tests

- Shell execution works inside isolation.
- Python analysis scripts can run.
- File creation and retrieval work.
- Resource limits are enforced.
- Host secrets and broker credentials remain inaccessible.
- Newly generated skills can be tested and reused.
- Generated skills cannot introduce keyword-based routing or bypass security boundaries.

Voice tests

- GPT Live retains realtime WebRTC audio transport.
- No separate mandatory STT/TTS pipeline is introduced.
- Speech requests in Arabic and other supported languages reach the backend correctly.
- Delayed transcript fragments do not cause false misunderstanding.
- The same voice request is not executed twice.
- Partial financial utterances do not trigger unintended execution.
- Short follow-up speech modifies the ongoing task.
- Barge-in interrupts speech without silently canceling work.
- Long-running analysis continues after the call ends.
- Voice and text share consistent conversation and task state.
- Android background and reconnect behavior are verified.
- Incoming app calls work in supported mobile lifecycle states.
- Outbound telephone calls are verified only when the provider is actually configured.
- Voice delegation does not depend on language-specific keywords.

User-visible reliability tests

- Monitoring claims correspond to persisted watches.
- Chart claims correspond to actual chart artifacts.
- Financial success claims correspond to broker evidence.
- Critical events notify the owner without duplicate calls or message spam.
- User-facing language follows the configured preference or conversation context.

Use unit, integration, contract and end-to-end testing as appropriate.

For real mobile and telephony capabilities, distinguish automated verification from actual device/provider testing. Explicitly report anything that could not be tested.

---

23. Mandatory Implementation Sequence

Execute in the following order.

Phase A — Architecture audit

Inventory the current design, verify references, map dependencies and identify redundant components, language-specific source content and keyword-driven behavior.

Phase B — Agent simplification

Reduce policy complexity, repair natural dialogue, improve context continuity and streamline the primary tool-calling loop. Remove keyword classifiers and fixed linguistic triggers.

Phase C — Workspace and skills

Introduce isolated shell/Python execution, file operations and reusable analytical skills.

Phase D — Trading intelligence

Refactor market assessment, entry readiness, missing-data recovery, strategy research and chart outputs.

Phase E — Authorization and Super Bot

Implement durable one-time account-scoped authorization, remove repetitive per-trade approvals within the valid scope and unify trading operating modes.

Phase F — Persistent autonomy

Improve durable planning, monitoring, notifications, memory and subagent coordination.

Phase G — GPT Live reliability

Fix the actual WebRTC delegation bridge, false repetition requests, speech interruption and context continuity.

Phase H — Proactive calling

Implement native incoming mobile calls first, then optional real telephone integration.

Phase I — UI simplification

Expose the new capabilities through a clean, minimal web/mobile experience and localization architecture.

Phase J — Cleanup and verification

Delete replaced code, remove dead interfaces, migrate persisted state safely, remove embedded non-English source text, run tests, inspect regressions and document the final architecture.

Each phase must include relevant tests and a review of regressions before depending on it in later phases.

Use incremental commits or clearly separated implementation checkpoints.

Do not delete working code based solely on filename similarity or presumed redundancy.

Do not activate live autonomous trading on a real account as part of testing without an actual owner-approved authorization. Use isolated simulation or disposable demo environments for validation.

---

24. Definition of Done

This mission is complete only when the resulting Lonora system demonstrates the following:

1. One agent brain: The language model drives natural interpretation, planning and tool selection.
2. One runtime: No duplicate agent frameworks or separate trading brains.
3. One Gateway: Existing resident execution infrastructure is reused.
4. Less accidental complexity: Duplicated and unnecessary files or instructions have been removed.
5. Natural conversation: Short replies and follow-ups in supported languages are understood from context.
6. Real execution: The agent uses tools rather than merely describing work.
7. Real terminal: An isolated analytical workspace is operational.
8. Reusable skills: The agent can create, validate and reuse analytical procedures.
9. Better trading decisions: Market bias, entry readiness and execution readiness are separated.
10. Persistent financial authorization: One authenticated, bounded authorization can cover subsequent permitted trades.
11. Autonomous account operations: The agent can act within the existing broker and risk controls.
12. Reliable persistent tasks: Monitoring and analysis survive disconnects and restarts.
13. Native GPT Live: WebRTC voice remains realtime and audio-first.
14. Reliable voice delegation: The agent no longer asks users to repeat requests because transcript fragments arrived late.
15. Proactive calls: Supported, consented incoming calls can be initiated by Lonora.
16. Verified results: Actions, monitoring and charts are backed by actual execution evidence.
17. Working application: Web, mobile, API, Gateway and trading integration remain functional.
18. Language-neutral internals: Source code, schemas, logs and internal tool contracts contain English only, while user-facing responses support the user's language through localization and model behavior.
19. No keyword dependency: Agent behavior is selected from context, state, model reasoning and verified tool capabilities rather than predefined keywords or command phrases.
20. Mandatory parity capabilities: Autonomous execution, scheduling, workflow automation, universal skills, MCP integrations, bounded subagents, persistent project knowledge, specialized market intelligence, strategy validation, execution safety, reporting, and all acceptance tests defined in this mandate function end to end with observable evidence and explicit failure-path coverage.

---

25. Required Final Engineering Report

After implementation, provide:

1. Original architectural problems found.
2. Actual root causes, distinguishing verified defects from hypotheses.
3. Files removed and why they were safe to remove.
4. Components merged or simplified.
5. Components created or extended.
6. How the final agent execution loop works.
7. How the terminal and skill workspace work.
8. How account authorization now works.
9. How autonomous trading is executed and verified.
10. How GPT Live delegates tasks to Lonora.
11. The confirmed cause and fix for the voice repetition failure.
12. How proactive incoming calls are implemented.
13. How the system preserves security and financial risk controls.
14. How language selection and localization are implemented.
15. How keyword-driven behavior was removed or prevented.
16. How Universal Skills Importer, Skill Adaptation, dependency management, validation sandbox, lifecycle management, MCP integrations, workflow persistence, subagent supervision, Strategy Knowledge Base, Intelligent Trading Journal, Decision Replay & Audit, market intelligence, strategy validation, execution recovery, and reporting capabilities were implemented and verified.
17. Tests executed and their actual results.
18. Any unsupported provider, device or infrastructure dependencies.
19. Any unfinished work with the exact blocker.
20. Relevant commits, pull request and deployment/migration instructions.

Maintain a concise architectural decision record explaining why the final solution was chosen.

Do not declare the mission complete if significant functionality is still mocked, disconnected, untested or represented only by documentation.

---

FINAL DIRECTIVE

Simplify Lonora without making it less capable.

Use Nanobot for clarity of agent organization.

Use Hermes Agent for inspiration on workspace flexibility and reusable capabilities.

Use Claude Code as the benchmark for intelligent, proactive tool-driven task execution.

Preserve Lonora's specialized trading infrastructure and durable Gateway.

Preserve GPT Live as a native realtime WebRTC voice interface.

Remove unnecessary behavioral programming, keyword classifiers, fixed command phrases and redundant workflow machinery.

Implement one-time bounded financial authorization.

Make the agent capable of understanding natural requests, carrying out real work, creating tools, monitoring the market and speaking naturally with its owner in the appropriate language.

The agent should proactively present relevant capabilities and next steps when justified by the task and available evidence, without requiring the owner to use predefined phrases.

The model must provide intelligence. The runtime must provide capabilities. The financial engine must enforce authorized risk.

Begin with the architecture audit and proceed to real, tested implementation.

This is an engineering implementation mandate, not a request for architectural suggestions.
FINAL ARCHITECTURAL ENFORCEMENT — MANDATORY

The following requirements take precedence wherever earlier instructions create ambiguity or conflict.

1. Reuse Before Building

Before implementing any new capability, Codex MUST inspect and determine whether the capability already exists in Lonora.

Classify each capability as:

- Existing and fully functional.
- Existing but defective.
- Existing but incomplete.
- Missing and requiring implementation.

Repair and extend existing capabilities before creating new components.

Do not build duplicate services, managers, schedulers, registries, databases, or agent frameworks.

Architectural simplicity is a mandatory acceptance criterion.

2. Incremental and Verifiable Delivery

Execute the mandate through independently testable phases.

For each phase:

1. Inspect the affected implementation.
2. Establish existing behavior with tests.
3. Apply focused code changes.
4. Run relevant automated and integration tests.
5. Verify backward compatibility and persisted state.
6. Remove obsolete code only after replacement verification.
7. Record the changes and actual test results.

Use a dedicated development branch and reviewable commits.

Do not merge unverified architectural changes directly into the production branch.

Do not declare a capability implemented solely because its interface or configuration exists.

If a capability requires unavailable external credentials, hardware, or service access, implement and test the supported portions, clearly document the blocker, and do not claim end-to-end operational readiness.

3. Language-Neutral Engineering

Use English for source identifiers, comments, technical contracts, tool schemas, internal prompts, and diagnostic messages.

However, localization resources, multilingual test fixtures, and legitimate user-generated content MUST be allowed in their original languages.

Do not remove meaningful multilingual regression coverage.

The prohibition on keyword-based language interpretation applies to conversational intent routing, not to necessary protocol parsing, validation, authentication, security controls, or explicitly configured commands.

4. Secure External Skill Execution

Treat external Skills, Plugins, repositories, scripts, and MCP tool descriptions as untrusted inputs.

Support automatic discovery, inspection, compatibility validation, and installation workflows within defined permissions.

Execute third-party code only inside an appropriately isolated environment with authorized capabilities.

Never permit imported code or instructions to escalate privileges, access broker secrets, bypass financial controls, or alter the authoritative trading engine.

Skill adaptation must be validated against the original behavior and documented when equivalence cannot be preserved.

5. One Agent Identity, Multiple Interfaces

Lonora must expose one primary persistent agent identity and one authoritative task and permission system.

GPT Live may be a separate realtime voice model, but it must operate as an interface to the same agent identity, conversation context, task state, and trading authorization.

Do not interpret the "one agent brain" requirement as a prohibition on specialized model interfaces, bounded subagents, or provider-specific voice runtime components.

Prevent duplicated agent authority, not legitimate separation of technical responsibilities.

6. Financial Test Isolation

All automated financial execution tests MUST run in simulation, paper trading, or explicitly designated disposable test environments.

Never execute live orders, alter real account permissions, or modify real positions during architectural verification without separately authenticated, explicit owner authorization for that action.

Persistent autonomous grants must remain bounded, revocable, and enforced by the authoritative server-side risk engine.

7. Final Engineering Standard

The implementation must demonstrate measurable functional improvement without unnecessary architectural growth.

Prefer fewer coherent components over larger collections of overlapping managers and abstractions.

Preserve operational reliability, financial safety, maintainability, and real-world testability.

The objective is not to maximize the number of features or files. The objective is to deliver the simplest working architecture that satisfies the required capabilities.