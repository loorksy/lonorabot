# S19 continuity audit

Audit baseline: `21293ad606b6c97d247079bd91ab6f3f625861c7`.
Scope: logical Tasks, Run recovery/fencing, wait/wake, voice continuity,
subagents and collaboration. This records actual implementations and tests;
it does not mark specification 19 complete.

## Reuse the existing durable system

| Capability | Existing ownership and behavior | Evidence |
| --- | --- | --- |
| Run identity and fencing | `lonora_db/runs.py`: thread-before-Run claim lock, `skip_locked`, lease owner/fence/expiry, monotonic fence on recovery, lease validation before checkpoint/result | `tests/check_streaming.py`; `tests/test_task_runtime.py::test_pause_resume_checkpoint_and_fence_recovery` |
| Logical Task | `lonora_db/tasks.py`: existing ticket owns Task state; separate same-Agent work Thread keeps the owner conversation responsive | `test_same_agent_work_does_not_block_conversation`; `check_task_recovery.py` |
| Verified steps | `update_task_step` accepts only persisted successful tool-call IDs and refuses rewriting completed steps; financial evidence must be confirmed | `test_step_completion_requires_real_checkpoint_evidence`; `test_run_cannot_complete_declared_unverified_task_steps` |
| Task retry | `task_recovery.py`: persisted bounded attempts/backoff; recovery requeues the same checkpointed Run; uncertain external effects block replay | `test_bounded_retry_preserves_checkpoint_steps_and_fencing`; `test_unknown_external_mutation_cannot_be_retried_by_declared_read_only_step`; `test_financial_ambiguity_blocks_owner_resume_until_journal_settles` |
| Gateway recovery | `lonora_gateway/scheduler.py` dispatches `retry_due_tasks`; maintenance returns committed child outcomes after the commit/return crash window | `check_task_recovery.py`; `check_streaming.py` |
| Conversational steering | `messages.send_message` steers an active conversational Run instead of starting a competing one; `task_control` applies versioned plan changes to background work | `test_semantic_tool_control_and_revision_resume`; new `check_voice_task_continuity.py` |
| Voice channel | `lonora_voice/sessions.py` admits the exact owner/Agent/Thread; `RealtimeVoiceSession.delegate` uses the same `send_message` path | `tests/voice/test_live.py`; `tests/voice/test_context.py` |
| Speech interruption | `barge_in` persists only a speech-interrupt request and returns no cancelled Runs; closing voice does not cancel admitted backend work | `test_delegated_transcript_is_durable_once_and_close_keeps_work`; new continuity fixture |
| Partial speech | Transcript deltas alone admit no work; a provider delegation boundary must have the full transcript through its offset; incomplete/trimmed input fails closed | `test_incomplete_transcript_fails_closed_and_future_request_can_continue`; new continuity fixture |
| Subagent safety | `subagents.py` creates bounded same-Agent child Runs; ToolLoop enforces server registry read-only mode for `trigger=subagent`; depth and active-count limits persist in Run ancestry | `test_missing_tools_and_subagent_cannot_load_financial_skill`; `check_agent_binding.py`; `check_delegated_scope.py` |
| Peer results | `outcome_return.py`: per-Run/fence effect receipts, attributed result messages and parent steering; Gateway repairs missing deliveries | `check_streaming.py` |
| One collaboration synthesis | `collaboration.py`: stable per-round synthesis identity, serialized by host Thread; all terminal participant outcomes must be delivered first | `check_review_findings.py`: three simultaneous outcomes and nine duplicate deliveries create one synthesis |

## S19 gaps and smallest integration points

These are baseline findings, before the S19 recovery implementation wave.

1. **Ordinary safe-read failure has no durable continuation deadline.**
   Tool failures reach the model, but a model/runtime failure on a normal
   conversation has no Task recovery owner and can terminate the Run. Extend
   existing Run execution state/claim eligibility for bounded safe-read retry;
   do not create a second scheduler or Task engine. Preserve pending call ID,
   fence and side-effect identity. Parent workstream owns this change.

2. **The failure-loop guard is argument-based, not result-aware.**
   `tool_guard.advance_guard` counts consecutive equivalent calls and raises on
   the sixth call regardless of outcome. It cannot distinguish successful
   repeated reads from identical failures or provide a safe alternate route.
   Extend persisted ToolLoop recovery state using typed error and side-effect
   metadata. Keep it bounded across restarts. Parent workstream owns this change.

3. **Generic external waits are narrower than domain waits.**
   Ordinary `wait_for_input` always becomes `waiting_input`. Tasks have durable
   retry backoff, trading Goals have `goal_wait`, and watches carry Goal/step
   lineage, but a generic Task has no typed external-health/watch wait binding.
   Reuse the existing Task wait fields and established wake receipts when adding
   that behavior. Do not claim every watch wake already resumes a logical Task:
   `lonora_market/watchers.py` currently links `goal_id`/`step_id`, not `task_id`.

4. **Task automatic retry is conservative and opt-in.**
   `TaskRetryPolicy.mode` defaults to `owner`; all remaining steps and previous
   tool calls must satisfy server read-only checks before automatic replay.
   Do not globally change the default to retry mutations. For safe transient
   ordinary reads, add bounded runtime recovery at the existing Run boundary.

5. **Collaboration's active-host synthesis path needs explicit acceptance.**
   `schedule_synthesis` deliberately reuses a running host instead of creating
   another Run. Such hosts close the session through `collaboration_finish`;
   automatic outcome closure applies to separately marked synthesis Runs.
   Existing concurrency tests primarily cover a host that already completed.
   Add a scripted active-host test before claiming that path fully verified.
   A successful child is evidence, never a transfer of financial authority.

6. **Voice continuity previously had helper-level evidence, not the complete
   runtime acceptance chain.** This gap is addressed by the new fixture below.
   It uses the existing voice path and requires no voice runtime replacement.

## New runtime acceptance evidence

`tests/check_voice_task_continuity.py` runs the real sideband state machine,
PostgreSQL message admission, AgentRuntime, global router object, ToolRegistry,
Task operations, checkpoints and canonical result delivery. Model completions
are explicitly scripted; provider, microphone and broker network calls are not
part of this fixture.

The fixture proves:

- Partial financial speech and incomplete delegation admit no Message/Run or
  trading journal entry.
- A complete voice request calls real `task_start`; the spoken acknowledgement
  completes the conversational turn while the same logical Task remains queued.
- Background work persists a real evidence-backed completed step.
- Advancing transport inactivity by 31 seconds, speech barge-in and call close
  leave the Task and work Run active.
- A new resident call on the same owner/Agent/Thread obtains actual progress
  through `task_inspect`, without guessing from the voice transcript.
- A later spoken revision uses versioned `task_control` and updates the same
  Task; the original worker consumes plan revision 2 at its safe boundary.
- Both steps complete using actual persisted successful call IDs, first-step
  work is not replayed, exactly one work Run exists and one final result appears
  in the original conversation.

The 31-second interval is injected into the stored transport activity timestamp,
avoiding a real-time sleep. Voice reconnection is tested at the already-attached
Gateway sideband boundary; paid admission ownership and transport negotiation
are separately covered in `tests/voice`.

Local checks during this audit:

- `pytest -q tests/test_task_runtime.py`: **11 passed**.
- Disposable migrated PostgreSQL `pytest -q tests/voice`: **17 passed**.
- Disposable migrated PostgreSQL `check_voice_task_continuity.py`: **passed**.
- Ruff on the new fixture: **passed**.

Native Android microphone/permission/transport behavior is outside this fixture.
No APK build, deployment, production migration or financial execution was run.

## Integrated follow-up

The baseline gaps above are addressed by the shared runtime extension: safe-read Run backoff, Task source waits/wakes on the existing scheduler, contract-aware operational history, and new active-host acceptance in `check_runtime_collaboration.py`. Voice continuity and11 Task cases were retained in the26-fixture acceptance runner. Financial review added stable original-call reconciliation, frozen optional Goal step/attempt receipts and explicit fencing of legacy checkpoints without proven identity. No second voice/task/recovery engine was needed. Native device acceptance remains separate and blocked under the owner no-build instruction.
