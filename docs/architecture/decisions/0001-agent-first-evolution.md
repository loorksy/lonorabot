# ADR 0001: Evolve the existing Lonora agent runtime

- Status: Accepted as the implementation direction; individual capabilities remain subject to verification.
- Date: 2026-10-21
- Source: `prompt 1.md` supplied in this task.

## Context

The repository already has one persistent Agent runtime and resident Gateway, a typed tool registry, durable Runs and Tasks, conversation and memory storage, versioned Skills, bounded peer/subagent work, MCP connections, native GPT Live/WebRTC, broker adapters, and server-enforced trade approvals, autonomous Goal grants, journals, idempotency, reconciliation, market evidence, charts, Watches, Routines, Shadow mode, and decision records. These are separate product packages, but they share Lonora's existing Agent identity and execution boundary.

The current tool registry is assembled by `lonora_tools.loader`; the Agent's Observe/Reason/Act loop and durable checkpoints live in `lonora_agent.tool_loop` and `lonora_agent.tasks`. Broker mutations go through the typed `lonora_trading` services. Voice uses OpenAI's Live session negotiation and a resident server-side event attachment, then delegates to the same chat thread and runtime.

The requested mandate also describes capabilities that are not present in the default built-in tool set. In particular, the default Agent has no shell, arbitrary filesystem, isolated Python workspace, importer that runs third-party Skills, or general skill dependency installer. The production API and Gateway containers do not mount the Docker socket or declare a separate sandbox runtime. At the audited base, voice delegation assembled transcript deltas by offset and turned a five-second synchronization delay into a request to repeat the utterance; system instructions were a 4,660-line policy bundle with hashed distribution checks.

## Decision

Extend the existing Agent, Gateway, tools, memory, and financial services. Do not install Hermes or Nanobot as a second runtime, and do not create a second task, trading, voice, or authorization authority. Treat third-party Skill content as untrusted and keep any future code execution outside the API and Gateway privilege boundary.

Keep the existing GPT Live/WebRTC transport and backend Agent delegation. A transcript synchronization failure must remain distinct from unintelligible speech; it must never create financial work from an incomplete utterance or tell the owner to repeat a request solely because the handoff is late.

Keep account ownership, server-verified device grants, exact broker scope, global Trading controls, Emergency Stop, risk limits, approvals where required, idempotency, execution journals, and broker reconciliation authoritative during all changes. Broader persistent account grants require an explicit scope design and integration tests before changing execution behavior.

## Dependency order

1. Verify and simplify Agent instructions, conversational context, tool-loop behavior, and voice handoff while retaining the existing runtime contracts.
2. Define the isolated analytical workspace boundary and resource limits before exposing shell, file, or Python tools.
3. Extend Skills on top of that workspace; discovery, validation, dependency installation, execution, and rollback must share one owner-scoped lifecycle and cannot grant trading authority.
4. Reuse current market evidence, chart, Shadow, journal, Goal, Watch, and execution services for deeper strategy work; add only capabilities that are absent and can be validated from reliable data.
5. Integrate mobile/Web experience only after server state and authorization contracts are stable.

## Evidence and open work

- Verified in this implementation slice: a transcript arriving after the previous five-second threshold remains pending, out-of-order transcript fragments are assembled by audio time, and an expired incomplete handoff reports that no work started without asking for repetition.
- Voice regression checks: all 14 cases in `tests/voice/test_live.py` passed against disposable PostgreSQL.
- The compact policy removes the 60 authored dialogue examples and duplicated schemas for 90 tools. The existing provider schema path, domain guidance, cache boundary, and resumed-checkpoint refresh remain in use.
- The voice change is a mitigation, not the final protocol redesign: an offset is not a finalized-turn marker, and the current completion predicate remains an open item. Provider documentation: <https://developers.openai.com/api/docs/guides/live-delegation>.
- The universal external Skill importer, isolated analytical workspace, dependency manager, general strategy backtesting, and native push-initiated calls are not established by this audit and remain unverified or missing.
- This decision record is not a claim that the full mandate is complete.
