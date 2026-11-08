"""The durable agent tool loop: execution, checkpoints, steering, waits and limits.

The final tool-less report at a limit (``finish_turn``) adapts the
iteration-budget grace call of Hermes Agent
``agent/chat_completion_helpers.py::handle_max_iterations``, source
https://github.com/NousResearch/hermes-agent at revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a. Lonora checkpoints the report before
returning it, so a restart commits the same text instead of calling again.

MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json
import logging
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.runs import WORK_TRIGGERS
from lonora_core.run_state import is_conversational
from lonora_core.user_error import LonoraError
from lonora_db.runs import checkpoint, require_lease
from lonora_db.schema import RunRow
from lonora_db.tasks import report_task_degraded
from lonora_session.idempotency import request_hash
from lonora_tools.base import ToolScope, run_scope
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from lonora_tools.tool_results import store_result

from .cancellation import cancellation_checkpoint
from .context.builder import build_context
from .context.skills import assert_skill_authority, refresh_skill_context, selected_skill_ids
from .context_engine import (
    DELEGATED_KEY,
    DELEGATED_TRIGGERS,
    FENCE_CODES,
    compact_context,
    compacted_view,
    record_observed,
    request_overhead,
    resolve_limits,
)
from .continuation import MAXIMUM_SLICES, schedule_task_continuation, slice_limit
from .environment import (
    ToolRetryScheduled,
    bounded_result,
    environment_state,
    observe,
    retry_pending,
    schedule_retry,
)
from .model_recovery import (
    ATTENTION_REASON,
    CONTINUOUS,
    CONVERSATION,
    RETRY_REASON,
    STATE_KEY,
    WORK,
    BackoffProfile,
    input_scale,
    plan_failure,
    record_success,
    reset_streak,
)
from .model_runtime import model_turn
from .progress import progress
from .recovery import restore_execution
from .runtime_notices import (
    NO_ANSWER,
    append_notice,
    attach_notice,
    attention_message,
    attention_notice,
    budget_warning,
    finish_instruction,
    is_owner_message,
    is_runtime_notice,
    limit_fallback,
    notice_message,
    prefers_arabic,
    resumed_notice,
)
from .skills.access import admitted_view_ids
from .skills.snapshot import read_snapshot
from .steering import merge_steering, owner_steering_pending
from .stop_gates import reset_stop_gate, task_progress, task_stop_gate
from .tasks import task_checkpoint
from .tool_batch import Segment, gather_bounded, next_segment
from .tool_dispatch import dispatch_call
from .tool_exposure import ensure_exposure, inventory, native_definitions, remember_use
from .tool_guardrails import (
    after_call,
    before_call,
    blocked_result,
    halt_reason,
    reset_guardrails,
)
from .tool_intent import (
    cancel_superseded_approvals,
    clear_inflight,
    close_unexecuted,
    inflight_ids,
    mark_inflight,
    start_budget_epoch,
)

log = logging.getLogger("lonora.tool_loop")

# Executable model rounds left before the final limit at which the model is told.
BUDGET_WARNING_ROUNDS = 2
OWNER_ATTENTION = "owner_attention"
# Set by Task controls when the owner resumes or revises work held for attention.
ATTENTION_RESUMED = "owner_attention_resumed"


@dataclass
class LoopOutcome:
    text: str
    metadata: dict[str, Any]
    waiting: bool = False
    external_wait: bool = False
    input_request: dict[str, Any] | None = None


async def persist(
    context: ToolContext,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
) -> None:
    state["messages"] = [message.model_dump(mode="json") for message in messages]
    state["pending"] = [call.model_dump(mode="json") for call in pending]
    async with context.db.sessions() as session, session.begin():
        await checkpoint(session, context.lease, state)


async def compact_for_turn(
    context: ToolContext,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
    capability: Capability,
    tools: list[ToolDefinition],
    *,
    inventory_text: str = "",
    policy_tools: Collection[str] | None = None,
) -> Callable[[list[ModelMessage]], list[ModelMessage]]:
    """Keep the next request under its model's window; return the request view.

    Compaction is persisted in the checkpoint before the request, so it is not
    recomputed after a restart and canonical messages are never rewritten. It
    never fails the turn: fencing errors propagate, anything else keeps the
    current view and admission degrades the request instead.
    """

    async def save() -> None:
        await persist(context, state, messages, pending)

    try:
        limits = await resolve_limits(
            context, capability, for_agent=True, input_scale=input_scale(state)
        )
        await compact_context(
            context,
            state,
            messages,
            limits,
            extra_tokens=request_overhead(
                messages, tools, limits, inventory=inventory_text, available=policy_tools
            ),
            save=save,
        )
    except LonoraError as error:
        if error.code in FENCE_CODES:
            raise
        log.warning("context_compaction_failed code=%s", error.code)
    except Exception as error:
        log.warning("context_compaction_failed type=%s", type(error).__name__)
    return lambda request: compacted_view(request, state)


def rich_metadata(state: dict[str, Any]) -> dict[str, Any]:
    value = state.get("rich_content")
    return {"rich_content": value} if isinstance(value, dict) else {}


def wait_update(messages: list[ModelMessage], call_id: str) -> dict[str, Any]:
    """Only display content attached to this exact accepted wait describes it."""
    message = next(
        (
            message
            for message in reversed(messages)
            if message.role == "assistant"
            and any(call.id == call_id for call in message.tool_calls)
        ),
        None,
    )
    result: dict[str, Any] = {
        "call_id": call_id,
        "text": message.content.strip() if message else "",
    }
    if message and message.rich_content is not None:
        result["rich_content"] = message.rich_content
    return result


def external_wait_outcome(state: dict[str, Any]) -> LoopOutcome:
    environment = environment_state(state)
    identifier = environment["wait"].get("call_id")
    if not isinstance(identifier, str) or not identifier:
        raise LonoraError("task_wait_identity_invalid", 409)
    update = environment.get("wait_update")
    # Legacy checkpoints never published this narration. Keep them silent rather
    # than promoting old private prose through a newer disclosure boundary.
    rich_content: dict[str, Any] | None = None
    if update is None:
        text = ""
    elif not isinstance(update, dict):
        raise LonoraError("task_wait_identity_invalid", 409)
    else:
        saved = cast(dict[str, Any], update)
        if saved.get("call_id") != identifier or not isinstance(saved.get("text"), str):
            raise LonoraError("task_wait_identity_invalid", 409)
        text = cast(str, saved["text"])
        raw_rich = saved.get("rich_content")
        if isinstance(raw_rich, dict):
            rich_content = cast(dict[str, Any], raw_rich)
    return LoopOutcome(
        text,
        {
            **state.get("selection", {}),
            "external_wait_call_id": identifier,
            **({"rich_content": rich_content} if rich_content is not None else {}),
        },
        external_wait=True,
    )


def close_pending(
    state: dict[str, Any],
    registry: ToolRegistry,
    messages: list[ModelMessage],
    pending: list[ToolCall],
    reason: str | None,
    *,
    code: str = "",
) -> list[ToolCall]:
    """Answer every pending call; return those that may already have executed.

    A non-read-only call whose in-flight marker survived a restart may have crossed
    its effect boundary before the worker died. It is answered as dispatch answers an
    interrupted call (``tool_execution_uncertain``, route marked ambiguous), never as
    superseded or not executed, so the model reconciles instead of repeating it.
    """
    environment = environment_state(state)
    started = inflight_ids(environment) | set(environment.get("legacy_pending", []))
    uncertain: list[ToolCall] = []
    for call in list(pending):
        tool = registry.tools.get(call.name)
        if call.id in started and not (tool and tool.read_only):
            result: dict[str, Any] = {"ok": False, "code": "tool_execution_uncertain"}
            observe(state, call, tool, result)
            messages.append(
                ModelMessage(
                    role="tool",
                    tool_call_id=call.id,
                    content=json.dumps(result, ensure_ascii=False),
                )
            )
            record_observed(state, call.id)
            uncertain.append(call)
        else:
            close_unexecuted(messages, [call], reason, code=code)
    environment["legacy_pending"] = [
        identifier
        for identifier in environment.get("legacy_pending", [])
        if identifier not in {call.id for call in pending}
    ]
    pending.clear()
    return uncertain


async def report_closed(
    context: ToolContext, closed: list[ToolCall], uncertain: list[ToolCall], code: str
) -> None:
    for call in closed:
        if call in uncertain:
            await progress(
                context,
                "tool.completed",
                {
                    "name": call.name,
                    "call_id": call.id,
                    "ok": False,
                    "code": "tool_execution_uncertain",
                },
            )
        else:
            await progress(
                context, "tool.cancelled", {"name": call.name, "call_id": call.id, "code": code}
            )


def supersede_wait_siblings(messages: list[ModelMessage], pending: list[ToolCall]) -> None:
    """Close the current tool block without carrying stale actions across a wait.

    Their identities remain durable observations, just as for owner steering.
    After waking, the model must decide again from current external evidence.
    """
    close_unexecuted(messages, pending, "task_wait_requires_fresh_analysis_after_wake")


async def report_wait_superseded(context: ToolContext, superseded: list[ToolCall]) -> None:
    for sibling in superseded:
        await progress(
            context,
            "tool.cancelled",
            {"name": sibling.name, "call_id": sibling.id, "code": "tool_call_superseded"},
        )


def latest_answer(messages: list[ModelMessage]) -> str:
    """The best held answer: the newest assistant prose since the owner's request."""
    for message in reversed(messages):
        if is_owner_message(message):
            break
        if message.role == "assistant" and message.content.strip():
            return message.content.strip()
    return ""


# Subagents delegate at most two levels deep; a few extra hops guard bad data.
_MAXIMUM_DELEGATION_HOPS = 4


async def recovery_profile(context: ToolContext, task_run: bool) -> BackoffProfile:
    """How long this Run may back off: whoever waits on it decides.

    Continuous Task work keeps monitoring through an outage; finite Task and
    background work outlast ordinary outages; a conversation (and a subagent
    it delegated, which the conversation waits on) fails honestly within
    about a minute.
    """
    if task_run:
        progress = await task_progress(context)
        return CONTINUOUS if progress is not None and progress.continuous else WORK
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        trigger, parent_id = run.trigger, run.parent_run_id
        for _ in range(_MAXIMUM_DELEGATION_HOPS):
            if trigger != "subagent" or parent_id is None:
                break
            parent = await session.get(RunRow, parent_id)
            if parent is None:
                break
            if parent.model_metadata.get("task_id"):
                return WORK
            trigger, parent_id = parent.trigger, parent.parent_run_id
    return WORK if trigger in WORK_TRIGGERS else CONVERSATION


async def request_owner_attention(
    context: ToolContext,
    state: dict[str, Any],
    messages: list[ModelMessage],
    reason: str,
    text: str,
) -> LoopOutcome:
    """Hand unfinished Task work to its owner as a resumable question.

    The Run is not failed and the Task is not completed: the checkpoint stays
    intact and the owner's reply continues it. Prose already passed the model
    runtime's financial-truth gate, so no unverified effect becomes success,
    and the runtime's own account of what is unfinished leads the message so a
    held answer claiming completion is never the owner's only report.
    """
    arabic = prefers_arabic(messages)
    completion = await task_progress(context)
    notice = attention_notice(
        reason, arabic, [title for _, title in completion.incomplete] if completion else ()
    )
    # Every escalation gets its own question id. A Task-control resume cancels the
    # previous question without adding a message (its notice joins the last tool
    # result), so the transcript length alone would repeat the cancelled id.
    taken = {
        str(cast(dict[str, Any], item).get("id"))
        for item in cast(list[Any], state.get("input_requests", []))
        if isinstance(item, dict)
    }
    sequence = int(state.get("attention_sequence", 0)) + 1
    while f"attention-{len(messages)}-{sequence}" in taken:
        sequence += 1
    state["attention_sequence"] = sequence
    question: dict[str, Any] = {
        "id": f"attention-{len(messages)}-{sequence}",
        "question": attention_message(notice, text, arabic),
        "choices": [],
        "kind": OWNER_ATTENTION,
        "reason": reason,
    }
    state["pending_input_request"] = question
    state["exit_reason"] = reason
    await persist(context, state, messages, [])
    return attention_outcome(state, question)


def attention_outcome(state: dict[str, Any], question: dict[str, Any]) -> LoopOutcome:
    reason = str(question.get("reason") or "task_attention")
    return LoopOutcome(
        str(question["question"]),
        {
            **state.get("selection", {}),
            **rich_metadata(state),
            "exit_reason": reason,
            OWNER_ATTENTION: reason,
            "reply_outcome": "needs_owner_attention",
        },
        True,
        input_request=question,
    )


async def final_answer(
    context: ToolContext,
    state: dict[str, Any],
    messages: list[ModelMessage],
    text: str,
    metadata: dict[str, Any],
) -> LoopOutcome | None:
    """Apply the bounded task stop gates; ``None`` means the turn continues."""
    verdict = await task_stop_gate(context, state)
    if verdict.continue_turn:
        append_notice(messages, "completion_check", verdict.nudge or "")
        await persist(context, state, messages, [])
        return None
    if verdict.exhausted:
        return await request_owner_attention(
            context, state, messages, verdict.exhausted, text or latest_answer(messages)
        )
    return LoopOutcome(text, metadata)


async def execute_segment(
    context: ToolContext,
    registry: ToolRegistry,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
    segment: Segment,
    scope: ToolScope,
) -> list[dict[str, Any]]:
    """Run one segment; results come back in the original call order."""
    environment = environment_state(state)
    interrupted = inflight_ids(environment) | set(environment.get("legacy_pending", []))
    decisions = [before_call(state, call, registry.tools.get(call.name)) for call in segment.calls]
    for call in segment.calls:
        await progress(context, "tool.started", {"name": call.name, "call_id": call.id})
    if segment.kind == "serial":
        call, decision = segment.calls[0], decisions[0]
        if decision.action in {"block", "halt"}:
            return [blocked_result(decision)]

        async def before_effect() -> None:
            # Receipts and known financial reconciliation above retain priority.
            # New effects cannot use instructions withdrawn since selection.
            await assert_skill_authority(
                context, registry, active_ids=state["instruction_skill_ids"]
            )
            # Persist intent before any handler can cross an effect
            # boundary. Unreceipted mutations cannot replay after death.
            mark_inflight(environment_state(state), [call])
            await persist(context, state, messages, pending)

        return [
            await dispatch_call(
                context,
                registry,
                state,
                call,
                scope,
                interrupted=call.id in interrupted,
                before_effect=before_effect,
            )
        ]
    runnable = [
        call
        for call, decision in zip(segment.calls, decisions, strict=True)
        if decision.action not in {"block", "halt"}
    ]
    if runnable:
        # Same boundary as a serial call, once for the whole read segment: a
        # crash leaves every call marked, and read-only calls simply re-run.
        try:
            await assert_skill_authority(
                context, registry, active_ids=state["instruction_skill_ids"]
            )
        except LonoraError as error:
            if error.code in {"stale_lease", "skill_continuation_unavailable"}:
                raise
            # As for a serial call, any other refusal is each call's observation.
            return [
                {"ok": False, "code": error.code}
                if decision.action not in {"block", "halt"}
                else blocked_result(decision)
                for decision in decisions
            ]
        mark_inflight(environment_state(state), runnable)
        await persist(context, state, messages, pending)

    def runner(call: ToolCall) -> Callable[[], Awaitable[dict[str, Any]]]:
        async def run() -> dict[str, Any]:
            return await dispatch_call(
                context,
                registry,
                state,
                call,
                scope,
                interrupted=call.id in interrupted,
                before_effect=None,
            )

        return run

    executed = iter(await gather_bounded([runner(call) for call in runnable]))
    return [
        next(executed) if decision.action not in {"block", "halt"} else blocked_result(decision)
        for decision in decisions
    ]


async def finish_turn(
    context: ToolContext,
    registry: ToolRegistry,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
    capability: Capability,
    *,
    reason: str,
    task_run: bool,
) -> LoopOutcome:
    """One final tool-less model call instead of failing the Run at a limit.

    Adapted from Hermes Agent's iteration-budget grace call (see the module
    notice). The reply is checkpointed before it is returned, so a restart
    commits the same text instead of making another model call.
    """
    saved = state.get("limit_exit")
    if isinstance(saved, dict) and isinstance(cast(dict[str, Any], saved).get("text"), str):
        text = cast(str, cast(dict[str, Any], saved)["text"])
    else:
        halt = halt_reason(state) or {}
        superseded = list(pending)
        uncertain = close_pending(
            state, registry, messages, pending, reason, code="tool_call_not_executed"
        )
        await cancel_superseded_approvals(context, [c for c in superseded if c not in uncertain])
        # The final request is its own trailing notice, the last thing read. A
        # restart after this checkpoint finds it already there: never add it twice.
        notice = notice_message(
            "work_limit", finish_instruction(reason, str(halt.get("message") or ""))
        )
        if not (messages and is_runtime_notice(messages[-1]) and messages[-1] == notice):
            messages.append(notice)
        state["exit_reason"] = reason
        clear_inflight(environment_state(state), {call.id for call in superseded})
        await persist(context, state, messages, pending)
        await report_closed(context, superseded, uncertain, "tool_call_not_executed")
        turn_capability = (
            Capability.VISION if any(message.images for message in messages) else capability
        )
        selection: ModelSelection | None
        try:
            view = await compact_for_turn(context, state, messages, pending, turn_capability, [])
            # No tools are offered, but a provider may still propose calls; the
            # resolver lets the truth gates read a bridged financial proposal.
            reply, selection = await model_turn(
                context,
                messages,
                [],
                turn_capability,
                resolve_calls=registry.resolve_calls,
                context_view=view,
            )
        except LonoraError as error:
            if error.code in {"stale_lease", "skill_continuation_unavailable"}:
                raise
            # The report is a courtesy at a limit: an unavailable model must not
            # turn the bounded stop into a Run failure. Nothing more executes.
            log.warning("finish_turn_model_unavailable code=%s", error.code)
            reply, selection = ModelReply(), None
        if reply.tool_calls:
            # No tools were offered. A provider that still proposes calls gets
            # none executed; financial prose was already withheld upstream.
            log.info("finish_turn_ignored_tool_calls count=%s", len(reply.tool_calls))
        text = reply.text.strip() or limit_fallback(prefers_arabic(messages))
        if reply.rich_content is None or not reply.text.strip():
            state.pop("rich_content", None)
        else:
            state["rich_content"] = reply.rich_content
        if selection is not None:
            state["selection"] = {
                "provider": selection.provider,
                "model": selection.model,
                "capability": reply.provider_metadata.get(
                    "runtime_capability", turn_capability.value
                ),
                "stream_timings": reply.provider_metadata.get("stream_timings", {}),
                "visual_errors": reply.provider_metadata.get("visual_errors", []),
                "visual_diagnostics": reply.provider_metadata.get("visual_diagnostics", []),
            }
        messages.append(
            ModelMessage(
                role="assistant",
                content=text,
                rich_content=state.get("rich_content"),
            )
        )
        state["limit_exit"] = {"reason": reason, "text": text}
        await persist(context, state, messages, pending)
    if task_run:
        question = state.get("pending_input_request")
        if isinstance(question, dict) and cast(dict[str, Any], question).get("kind") == (
            OWNER_ATTENTION
        ):
            return attention_outcome(state, cast(dict[str, Any], question))
        completion = await task_progress(context)
        if completion is None or not completion.contract_satisfied():
            # Never mark unfinished Task work completed; the owner decides next.
            return await request_owner_attention(context, state, messages, reason, text)
        # Every declared step is recorded complete with evidence, so the report
        # completes the Task; complete_run still enforces that contract.
        return LoopOutcome(
            text,
            {
                **state.get("selection", {}),
                **rich_metadata(state),
                "exit_reason": reason,
                "reply_outcome": "answered",
            },
        )
    return LoopOutcome(
        text,
        {
            **state.get("selection", {}),
            **rich_metadata(state),
            "exit_reason": reason,
            "reply_outcome": "limited",
        },
    )


async def execute_tool_loop(
    context: ToolContext, registry: ToolRegistry, maximum_rounds: int
) -> LoopOutcome:
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        state: dict[str, Any] = dict(run.execution_state)
        scope = run_scope(run.trigger, run.model_metadata)
        capability = (
            Capability.BACKGROUND if run.trigger in WORK_TRIGGERS else Capability.CONVERSATION
        )
        task_run = bool(run.model_metadata.get("task_id"))
    # Compaction must not label another Agent's request as the owner's.
    state[DELEGATED_KEY] = run.trigger in DELEGATED_TRIGGERS
    messages, pending = restore_execution(state)
    if messages and "instruction_skill_ids" not in state:
        # Legacy checkpoints have no binding between saved instructions and the
        # latest metadata selection. Conservatively check all retained versions.
        state["instruction_skill_ids"] = list(
            read_snapshot(run.model_metadata.get("skill_snapshot"))
        ) or await selected_skill_ids(context)
    if "environment" not in state and pending:
        # Older checkpoints did not distinguish proposed from in-flight calls.
        # Unknown legacy mutations must not acquire a new replay permission.
        environment_state(state)["legacy_pending"] = [call.id for call in pending]
    if not messages:
        messages = await build_context(context, registry)
        state["instruction_skill_ids"] = await selected_skill_ids(context)
    # Chosen once per Run and frozen in the checkpoint: the native tools array
    # is identical on every model turn, so discovery never invalidates the
    # reusable prompt prefix. Exposure is presentation, never authority.
    exposure = await ensure_exposure(
        context, registry, state, messages, pending, scope=scope, task_run=task_run
    )
    resumed = state.pop(ATTENTION_RESUMED, None)
    if isinstance(resumed, dict):
        # A Task control resumed work held for owner attention: that is owner
        # input, so it starts a new review epoch, and at a limit a new budget.
        reset_stop_gate(state)
        reset_guardrails(state)
        reset_streak(state)
        if state.get("limit_exit") or int(state.get("rounds", 0)) >= slice_limit(
            state, maximum_rounds
        ):
            start_budget_epoch(state)
        state.pop("exit_reason", None)
        append_notice(
            messages,
            "owner_resumed",
            resumed_notice(str(cast(dict[str, Any], resumed).get("action") or "")),
        )
        await persist(context, state, messages, pending)
    question = state.get("pending_input_request")
    if isinstance(question, dict):
        question = cast(dict[str, Any], question)
        if not await owner_steering_pending(context):
            if not pending and await merge_steering(context, state, messages):
                # A peer outcome woke a Run that waits for its owner. Keep it as
                # evidence for the answer; otherwise the outstanding steering row
                # would make the executor re-enter this wait indefinitely.
                await persist(context, state, messages, pending)
            if question.get("kind") == OWNER_ATTENTION:
                return attention_outcome(state, question)
            return LoopOutcome(
                str(question["question"]),
                {**state.get("selection", {}), **rich_metadata(state)},
                True,
                input_request=question,
            )
        # A new owner message supersedes an unpublished question before it reaches chat.
        state.pop("pending_input_request", None)
        await persist(context, state, messages, pending)
    environment = environment_state(state)
    if environment.get("wait"):
        if pending:
            # Older checkpoints could suspend halfway through a tool block.
            # Repair their unexecuted siblings before any future wake can run
            # stale financial intent or insert a user message into that block.
            superseded = list(pending)
            supersede_wait_siblings(messages, pending)
            await persist(context, state, messages, pending)
            await report_wait_superseded(context, superseded)
        return external_wait_outcome(state)
    wake = environment.get("last_wake")
    wake_superseded: list[ToolCall] = []
    if wake and environment.get("consumed_wake") != wake:
        # A previous release may have committed the wake before upgrading its
        # worker. Close its pre-wait proposals before adding the new observation.
        wake_superseded = list(pending)
        supersede_wait_siblings(messages, pending)
        reset_stop_gate(state)
        reset_guardrails(state)
        messages.append(
            ModelMessage(
                role="user",
                content="<runtime_wake>"
                + json.dumps(wake, ensure_ascii=False).replace("<", "\\u003c")
                + "</runtime_wake>",
            )
        )
        environment["consumed_wake"] = wake
    await persist(context, state, messages, pending)
    await report_wait_superseded(context, wake_superseded)

    async def refresh_after_steering() -> None:
        updated_skills = await refresh_skill_context(
            context, registry, messages, retained_ids=state.get("viewed_skill_ids", [])
        )
        if updated_skills is not None:
            state["instruction_skill_ids"] = sorted(
                set(updated_skills) | set(state.get("viewed_skill_ids", []))
            )

    async def supersede_for_steering() -> None:
        # Owner input supersedes only calls that never started; one interrupted
        # after its in-flight marker may have executed and is reported uncertain.
        superseded = list(pending)
        uncertain = close_pending(state, registry, messages, pending, None)
        await cancel_superseded_approvals(context, [c for c in superseded if c not in uncertain])
        clear_inflight(environment_state(state), {call.id for call in superseded})
        state.pop("waiting_call_id", None)
        await persist(context, state, messages, pending)
        await report_closed(context, superseded, uncertain, "tool_call_superseded")

    while True:
        await cancellation_checkpoint(context)
        await task_checkpoint(context)
        limit = slice_limit(state, maximum_rounds)
        if int(state.get("rounds", 0)) >= limit or halt_reason(state) or state.get("limit_exit"):
            reason = "guardrail_halt" if halt_reason(state) else "tool_round_limit"
            if await owner_steering_pending(context):
                # Owner input at a boundary is a new request: it supersedes the
                # unexecuted proposals and authorizes one new bounded budget.
                await supersede_for_steering()
                if await merge_steering(context, state, messages):
                    await refresh_after_steering()
                start_budget_epoch(state)
                await persist(context, state, messages, pending)
                continue
            if (
                reason == "tool_round_limit"
                and not state.get("limit_exit")
                and await schedule_task_continuation(context, state, maximum_rounds)
            ):
                raise ToolRetryScheduled()
            if pending:
                superseded = list(pending)
                uncertain = close_pending(
                    state, registry, messages, pending, reason, code="tool_call_not_executed"
                )
                await cancel_superseded_approvals(
                    context, [c for c in superseded if c not in uncertain]
                )
                clear_inflight(environment_state(state), {call.id for call in superseded})
                await persist(context, state, messages, pending)
                await report_closed(context, superseded, uncertain, "tool_call_not_executed")
            if await merge_steering(context, state, messages):
                # A peer outcome arrived after the final reply was drafted; the
                # reply must account for it, so draft it again (bounded by input).
                await refresh_after_steering()
                state.pop("limit_exit", None)
            return await finish_turn(
                context,
                registry,
                state,
                messages,
                pending,
                capability,
                reason=reason,
                task_run=task_run,
            )
        # New user input follows the complete tool-result block, never splits it.
        while pending:
            await task_checkpoint(context)
            if await owner_steering_pending(context):
                await supersede_for_steering()
                break
            if retry_pending(state, pending[0]):
                raise ToolRetryScheduled()
            segment = next_segment(pending, registry.tools)
            results = await execute_segment(
                context, registry, state, messages, pending, segment, scope
            )
            for index, (call, result) in enumerate(zip(segment.calls, results, strict=True)):
                tool = registry.tools.get(call.name)
                guarded = (
                    result.get("code") == "guardrail_blocked" and result.get("executed") is False
                )
                record = observe(state, call, tool, result)
                environment = environment_state(state)
                clear_inflight(environment, {call.id})
                environment["legacy_pending"] = [
                    identifier
                    for identifier in environment.get("legacy_pending", [])
                    if identifier != call.id
                ]
                environment.pop("retry", None)
                if result.get("recovery", {}).get("safe_to_retry"):
                    # Later reads of this segment are discarded and re-run with
                    # this call; only a completed prefix is ever checkpointed.
                    clear_inflight(environment, {later.id for later in segment.calls[index:]})
                    await progress(
                        context,
                        "tool.completed",
                        {
                            "name": call.name,
                            "call_id": call.id,
                            "ok": False,
                            "code": result.get("code"),
                            "attempt": record["failures"],
                            "recovery_pending": True,
                            "contract_hash": request_hash(tool.definition().model_dump(mode="json"))
                            if tool
                            else None,
                        },
                    )
                    schedule_retry(state, call, record["failures"])
                    await persist(context, state, messages, pending)
                    raise ToolRetryScheduled()
                if not guarded and not result.get("_runtime_retry"):
                    # An approval wait is not an execution yet; the approved
                    # dispatch of the same call is, and is counted exactly once.
                    decision = after_call(state, call, tool, result, failed=record["failures"] > 0)
                    if decision.action in {"warn", "halt"}:
                        attach_notice(result, "tool_guardrail", decision.message)
                if result.get("_runtime_retry"):
                    clear_inflight(environment, {later.id for later in segment.calls[index:]})
                    state["waiting_call_id"] = call.id
                    await persist(context, state, messages, pending)
                    return LoopOutcome(
                        str(result.get("question", "")),
                        {
                            **state.get("selection", {}),
                            "trade_approval_id": result.get("approval_id"),
                        },
                        True,
                    )
                state.pop("waiting_call_id", None)
                viewed_ids = await admitted_view_ids(
                    context, registry, call, result, state["instruction_skill_ids"]
                )
                if viewed_ids:
                    state["viewed_skill_ids"] = sorted(
                        set(state.get("viewed_skill_ids", [])) | set(viewed_ids)
                    )
                    state["instruction_skill_ids"] = sorted(
                        set(cast(list[str], state["instruction_skill_ids"])) | set(viewed_ids)
                    )
                content = json.dumps(result, ensure_ascii=False)
                if len(content) > 120000:
                    summary = bounded_result(result)
                    if "runtime_notice" in result:
                        summary["runtime_notice"] = result["runtime_notice"]
                    try:
                        summary = await store_result(context, call, result, summary)
                    except LonoraError as error:
                        if error.code in {"stale_lease", "skill_continuation_unavailable"}:
                            raise
                        summary["result_persisted"] = False
                        summary["result_storage_error"] = error.code
                    except Exception as error:
                        # Presentation persistence failure must not retry a completed mutation.
                        log.warning(
                            "tool_result_storage_failed name=%s type=%s",
                            call.name,
                            type(error).__name__,
                        )
                        summary["result_persisted"] = False
                        summary["result_storage_error"] = "tool_result_storage_unavailable"
                    content = json.dumps(summary, ensure_ascii=False)
                messages.append(ModelMessage(role="tool", content=content, tool_call_id=call.id))
                record_observed(state, call.id)
                pending = pending[1:]
                superseded: list[ToolCall] = []
                if result.get("_runtime_external_wait"):
                    environment["wait"] = result["_runtime_external_wait"]
                    environment["wait_update"] = wait_update(messages, call.id)
                    environment["phase"] = "waiting"
                    superseded = list(pending)
                    clear_inflight(environment, {later.id for later in superseded})
                    supersede_wait_siblings(messages, pending)
                if result.get("_runtime_wait"):
                    state["pending_input_request"] = {
                        "id": call.id,
                        "question": str(result["question"]),
                        "choices": result.get("choices", []),
                    }
                await persist(context, state, messages, pending)
                await progress(
                    context,
                    "tool.completed",
                    {
                        "name": call.name,
                        "call_id": call.id,
                        "ok": result.get("ok"),
                        "code": result.get("code"),
                        "contract_hash": request_hash(tool.definition().model_dump(mode="json"))
                        if tool
                        else None,
                    },
                )
                await remember_use(context, registry, exposure, call, result, scope=scope)
                if result.get("_runtime_external_wait"):
                    await report_wait_superseded(context, superseded)
                    return external_wait_outcome(state)
                if result.get("_runtime_wait"):
                    return LoopOutcome(
                        str(result["question"]),
                        {**state.get("selection", {}), **rich_metadata(state)},
                        True,
                        input_request=state["pending_input_request"],
                    )
                if result.get("_runtime_silence") and not pending:
                    prose = next(
                        (
                            message.content
                            for message in reversed(messages)
                            if message.role == "assistant"
                        ),
                        "",
                    ).strip()
                    outcome = await final_answer(
                        context,
                        state,
                        messages,
                        prose,
                        {
                            **state.get("selection", {}),
                            "reply_outcome": "answered"
                            if prose or rich_metadata(state)
                            else "silent",
                            **rich_metadata(state),
                        },
                    )
                    if outcome is not None:
                        return outcome
            if halt_reason(state):
                break
        if halt_reason(state):
            # The boundary handler finishes gracefully with the halt reason.
            continue
        if await merge_steering(context, state, messages):
            await refresh_after_steering()
        await task_checkpoint(context, state, messages)
        await assert_skill_authority(
            context, registry, active_ids=cast(list[str], state["instruction_skill_ids"])
        )
        # Only the last slice ends the Run; earlier Task slices continue later.
        per_slice = int(cast(dict[str, Any], state["task_continuation"])["rounds_per_slice"])
        final_limit = per_slice * MAXIMUM_SLICES if task_run else limit
        # Calls proposed in a turn execute only when another round follows it,
        # so count the turns, this one included, whose calls can still run.
        executable = final_limit - int(state.get("rounds", 0)) - 1
        if executable <= 0:
            # Offering tools now would waste the turn on calls that never run:
            # the last budgeted turn is the final tool-less report instead.
            return await finish_turn(
                context,
                registry,
                state,
                messages,
                pending,
                capability,
                reason="tool_round_limit",
                task_run=task_run,
            )
        if executable <= BUDGET_WARNING_ROUNDS and state.get("budget_warned") != executable:
            append_notice(messages, "budget", budget_warning(executable))
            state["budget_warned"] = executable
        turn_capability = (
            Capability.VISION if any(message.images for message in messages) else capability
        )
        native = native_definitions(registry, exposure, scope)
        inventory_text = inventory(registry, exposure, scope)
        policy_tools = registry.names(scope)
        view = await compact_for_turn(
            context,
            state,
            messages,
            pending,
            turn_capability,
            native,
            inventory_text=inventory_text,
            policy_tools=policy_tools,
        )
        try:
            reply, selection = await model_turn(
                context,
                messages,
                native,
                turn_capability,
                capability_inventory=inventory_text,
                # Bridge calls become the real calls before any boundary sees them.
                resolve_calls=registry.resolve_calls,
                policy_tools=policy_tools,
                context_view=view,
                input_scale=input_scale(state),
            )
        except LonoraError as error:
            if error.code in FENCE_CODES:
                raise
            # Every candidate failed. Nothing ran for this turn and nothing is
            # repeated: retry the same checkpoint later or tell the owner.
            profile = await recovery_profile(context, task_run)
            decision = plan_failure(state, error, profile)
            if decision.kind == "compact":
                log.warning("model_context_overflow input_scale=%s", input_scale(state))
                await persist(context, state, messages, pending)
                continue
            if decision.kind == "retry" and decision.not_before is not None:
                environment_state(state)["retry"] = {
                    "not_before": decision.not_before.isoformat(),
                    "reason_code": RETRY_REASON,
                    "code": error.code,
                    "attempt": decision.failures,
                }
                await persist(context, state, messages, pending)
                if decision.notify:
                    # Monitoring continues; the owner hears of the outage once.
                    async with context.db.sessions() as session, session.begin():
                        await report_task_degraded(
                            session,
                            await require_lease(session, context.lease),
                            ATTENTION_REASON,
                            error.code,
                            cast(dict[str, Any], state[STATE_KEY]).get("first_failed_at"),
                        )
                log.warning(
                    "model_turn_retry_scheduled code=%s attempt=%s notify=%s",
                    error.code,
                    decision.failures,
                    decision.notify,
                )
                raise ToolRetryScheduled() from None
            if decision.kind == "escalate":
                await persist(context, state, messages, pending)
                if task_run:
                    # The Task waits for its owner, resumable from this checkpoint.
                    return await request_owner_attention(
                        context, state, messages, ATTENTION_REASON, ""
                    )
            raise
        record_success(state)
        if reply.rich_content is None:
            state.pop("rich_content", None)
        else:
            state["rich_content"] = reply.rich_content
        state["rounds"] = int(state.get("rounds", 0)) + 1
        state["selection"] = {
            "provider": selection.provider,
            "model": selection.model,
            "capability": reply.provider_metadata.get("runtime_capability", turn_capability.value),
            "stream_timings": reply.provider_metadata.get("stream_timings", {}),
            "visual_errors": reply.provider_metadata.get("visual_errors", []),
            "visual_diagnostics": reply.provider_metadata.get("visual_diagnostics", []),
        }
        log.info(
            "model_turn_completed timings=%s visual_errors=%s",
            json.dumps(state["selection"]["stream_timings"], sort_keys=True),
            len(state["selection"]["visual_errors"]),
        )
        empty = not reply.text.strip() and reply.rich_content is None and not reply.tool_calls
        if empty and is_conversational(run.trigger):
            # An empty provider turn carries nothing to keep; the notice follows
            # the existing tail instead of an empty assistant message.
            append_notice(messages, "no_answer", NO_ANSWER)
            await persist(context, state, messages, pending)
            continue
        messages.append(
            ModelMessage(
                role="assistant",
                content=reply.text,
                tool_calls=reply.tool_calls,
                rich_content=reply.rich_content,
            )
        )
        pending = list(reply.tool_calls)
        await persist(context, state, messages, pending)
        if pending:
            continue
        if await merge_steering(context, state, messages):
            await refresh_after_steering()
            continue
        outcome = await final_answer(
            context,
            state,
            messages,
            reply.text,
            {
                **state["selection"],
                **rich_metadata(state),
                "reply_outcome": "answered"
                if reply.text.strip() or reply.rich_content
                else "silent",
            },
        )
        if outcome is not None:
            return outcome
