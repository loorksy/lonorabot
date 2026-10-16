# Nanobot architecture study

Studied repository: [HKUDS/nanobot](https://github.com/HKUDS/nanobot) at `faf1efaf09d2d69d1887b6ac6b0c6441e3ccccb2` (shallow clone of the default branch on 2026-10-16). License: MIT, copyright 2025-present Xubin Ren and the nanobot contributors. No Nanobot source was copied into Lonora. The comparison is architectural.

Nanobot is one process-local agent loop with a file/SQLite session, a tool registry, and a message bus. Lonora is a leased, multi-worker gateway with a PostgreSQL journal. Where Lonora is already stricter, that behavior stays.

## User request

Nanobot: channel inbound message → `AgentLoop._run_agent_loop` (`nanobot/agent/loop.py`) → session transcript → `AgentRunner.run` (`nanobot/agent/runner.py`) → model → tool registry → tool result appended to the transcript → next iteration until a final message or the iteration budget. Checkpoints are written through `checkpoint_callback`. Pending channel messages can be injected mid-turn (`_drain_pending`). An active goal can add a continuation prompt (`_goal_continue`) so one user request keeps working after the model would otherwise stop.

Lonora equivalent: owner message → queued Run → Gateway lease → `execute_tool_loop` → `model_turn` → `ToolRegistry.execute` → checkpoint on `RunRow.execution_state` → next round. Steering, tasks, and watches already wake the same Run.

Comparison: **ADAPTED**. Lonora already has the multi-step loop, leases, and checkpoints. Nanobot's useful missing piece was a typed observation after a tool failure, plus a durable record that the same arguments already failed, so the next model turn changes route instead of asking the owner to retry. That now lives in `lonora_core.operating` and the existing tool loop. Nanobot's in-process session lock was not imported; Lonora's lease fence is stronger for multiple workers.

## Background work

Nanobot: cron and local triggers call `submit_cron_turn` / `submit_local_trigger_turn` and re-enter the same runner. The gateway process owns the loop (`AgentLoop.run`).

Lonora: routines, watches, broker recovery, and task retry already enter the same Gateway scheduler and ToolLoop. No second scheduler was added.

Comparison: **LONORA_ALREADY_STRONGER** for durable wakes, idempotent receipts, and restart. **NOT_APPLICABLE** for Nanobot's process-local cron service.

## Failure

Nanobot: the runner records `failure_error_kind`, truncates oversized tool text (`max_tool_result_chars`), retries malformed tool calls and length recovery, and can finalize after the iteration budget. Tool argument validation is schema-local in `nanobot/agent/tools/base.py` (`Schema.validate_json_schema_value`). A tool error is data in the transcript, not an automatic end of the user's goal.

Lonora before this change: `ToolArgumentsError` already returned `issues` and `retryable`, and the loop continued. Oversized results became `tool_result_too_large` with no recovery hint. Identical calls were stopped only by a hard `repeated_tool_call` guard at six attempts, including successes. Financial ambiguity was enforced in the executor, not as a loop observation.

Comparison: **ADAPTED**. Lonora now classifies the existing error code (`repair`, `narrow`, `retry_read`, `reconcile`, `reload`, `wait`, `change_strategy`, `ask_owner`, `terminal`), attaches schema field names on invalid arguments, blocks a repeated failed argument hash before execution, and refuses a second financial send after an ambiguous classification. Hidden chain-of-thought is still not stored. Nanobot's free-form validator sentences were not copied; Lonora keeps stable codes.

## Restart

Nanobot: session files and SQLite (`nanobot/session`) restore the transcript. Tests such as `tests/session/test_recovery.py` and `tests/agent/test_cursor_recovery.py` cover that file model. A process restart reloads the session and continues.

Lonora: `RunRow.execution_state` already restores messages, pending tool calls, and the lease fence. `failure_routes` is now part of that checkpoint, so a restarted worker does not treat a known failed route as new. Completed tool results stay in the checkpoint and are not replayed.

Comparison: **LONORA_ALREADY_STRONGER** for fencing and financial journals. **ADOPTED** only as the route list inside the existing checkpoint. Nanobot's file session was not imported.

## Subagent

Nanobot: `nanobot/agent/subagent.py` starts a child runner with its own session and returns a result to the parent. The child does not inherit the parent's full runtime configuration blindly; tool loading is scoped.

Lonora: `subagent_spawn`, delegated research roles, and collaboration sessions already return real outcomes into the parent conversation. Financial authority is checked on Run ancestry. This change does not add a manager framework. Collaboration still schedules one synthesis run per round.

Comparison: **LONORA_ALREADY_STRONGER** for authority ancestry and durable collaboration. **NOT_APPLICABLE** to copy Nanobot's in-process subagent manager.

## Memory and context

Nanobot: `MemoryStore` in `nanobot/agent/memory.py` keeps `MEMORY.md`, `USER.md`, `SOUL.md`, and `history.jsonl`, with consolidation so the prompt stays bounded. Dream commits are a separate learning path and can rewrite durable memory files.

Lonora: owner memory, scratchpad, skills, and task state are already separate. Context is built per run and governed by the existing budget. Exhausted routes are now one scratchpad note with `provenance=tool-observed` and `authority=none`. The note cannot change trading policy, symbol binding, Emergency Stop, or reconciliation. Inferred notes are not written into `MEMORY.md`.

Comparison: **ADAPTED** for operational route memory only. **REJECTED_WITH_REASON** for Dream-style autonomous rewrite of identity or policy. That would conflict with server-authoritative financial safety.

## Tools and self-inspection

Nanobot: `MyTool` (`nanobot/agent/tools/self.py`) exposes runtime configuration and can change model settings when allowed. Tool schemas are part of the registry definition.

Lonora: one global model router stays mandatory. `runtime_status` now returns the live Agent projection, the current run's public failure routes (tool, code, count; no arguments), and each tool's name, read-only flag, and side-effect class. Full schemas are returned only for the tool that just failed validation, as field names and types. Secrets are not included. Nanobot's per-session model preset was not adopted.

Comparison: **ADAPTED** for inspection. **REJECTED_WITH_REASON** for runtime model mutation.

## Voice

Nanobot's audio package is a channel into the same loop. Lonora voice already shares the Agent, thread, and tools, and speech interruption returns no cancelled runs (`lonora_voice.barge_in`). Disconnect closes the voice session and does not cancel the durable Run.

Comparison: **LONORA_ALREADY_STRONGER**. No second voice agent was added.

## What was not imported

- Process-local bus, file workspace, and shell/exec tools.
- Per-agent model presets.
- Dream memory commits.
- Concurrent in-process tool execution. Lonora tools stay serialized under the Run lease so financial mutations cannot race.
- Keyword command routing.

## Acceptance against the study

| Nanobot concept | Decision |
| --- | --- |
| Multi-step agent loop | LONORA_ALREADY_STRONGER, extended with typed observations |
| Goal continuation prompt | ADAPTED as one bounded continuation when a failure has no owner-facing answer |
| Schema validation errors | ADAPTED onto existing `tool_arguments_invalid` issues |
| Oversized tool results | ADAPTED as `tool_result_too_large` plus field names and `narrow` |
| Session checkpoint / restart | LONORA_ALREADY_STRONGER; route list added to the existing checkpoint |
| Cron / wake | LONORA_ALREADY_STRONGER |
| Subagents | LONORA_ALREADY_STRONGER |
| Memory files | ADAPTED only as a non-authoritative scratchpad note |
| Dream learning | REJECTED_WITH_REASON |
| Self tool / model preset | REJECTED_WITH_REASON for model changes; ADAPTED for read-only environment status |
| Channel-equal voice | LONORA_ALREADY_STRONGER |
