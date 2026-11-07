import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.runs import WORK_TRIGGERS
from lonora_core.run_state import is_conversational
from lonora_core.user_error import LonoraError
from lonora_db.runs import checkpoint, require_lease
from lonora_session.idempotency import request_hash
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from lonora_tools.tool_results import store_result

from .cancellation import cancellation_checkpoint
from .context.builder import build_context
from .context.skills import assert_skill_authority, refresh_skill_context, selected_skill_ids
from .continuation import MAXIMUM_SLICES, schedule_task_continuation, slice_limit
from .environment import (
    ToolRetryScheduled,
    bounded_result,
    environment_state,
    observe,
    retry_pending,
    schedule_retry,
)
from .model_runtime import model_turn
from .progress import progress
from .recovery import restore_execution
from .runtime_notices import (
    NO_ANSWER,
    append_notice,
    attach_notice,
    attention_fallback,
    budget_warning,
    finish_instruction,
    is_owner_message,
    limit_fallback,
    notice_message,
    prefers_arabic,
)
from .skills.access import admitted_view_ids
from .skills.snapshot import read_snapshot
from .steering import merge_steering, owner_steering_pending
from .stop_gates import reset_stop_gate, task_stop_gate
from .tasks import task_checkpoint
from .tool_batch import Segment, gather_bounded, next_segment
from .tool_dispatch import dispatch_call
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

# Model rounds with tools left before the final limit at which the model is told.
BUDGET_WARNING_ROUNDS = 2
OWNER_ATTENTION = "owner_attention"


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
    runtime's financial-truth gate, so no unverified effect becomes success.
    """
    held = text.strip() or attention_fallback(prefers_arabic(messages))
    question: dict[str, Any] = {
        "id": "attention-" + str(len(messages)),
        "question": held,
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
    read_only: bool,
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
                read_only,
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
                read_only,
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

    Adapted from Hermes Agent's iteration-budget grace call
    (``agent/chat_completion_helpers.py::handle_max_iterations``; MIT, Copyright
    (c) 2025 Nous Research). The reply is checkpointed before it is returned,
    so a restart commits the same text instead of making another model call.
    """
    saved = state.get("limit_exit")
    if isinstance(saved, dict) and isinstance(cast(dict[str, Any], saved).get("text"), str):
        text = cast(str, cast(dict[str, Any], saved)["text"])
    else:
        halt = halt_reason(state) or {}
        superseded = list(pending)
        await cancel_superseded_approvals(context, superseded)
        close_unexecuted(messages, pending, reason, code="tool_call_not_executed")
        # The final request is its own trailing notice, the last thing read.
        messages.append(
            notice_message("work_limit", finish_instruction(reason, str(halt.get("message") or "")))
        )
        state["exit_reason"] = reason
        clear_inflight(environment_state(state), {call.id for call in superseded})
        await persist(context, state, messages, pending)
        for call in superseded:
            await progress(
                context,
                "tool.cancelled",
                {"name": call.name, "call_id": call.id, "code": "tool_call_not_executed"},
            )
        turn_capability = (
            Capability.VISION if any(message.images for message in messages) else capability
        )
        selection: ModelSelection | None
        try:
            reply, selection = await model_turn(context, messages, [], turn_capability)
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
        # Never mark unfinished Task work completed; the owner decides next.
        question = state.get("pending_input_request")
        if isinstance(question, dict) and cast(dict[str, Any], question).get("kind") == (
            OWNER_ATTENTION
        ):
            return attention_outcome(state, cast(dict[str, Any], question))
        return await request_owner_attention(context, state, messages, reason, text)
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
        read_only = (
            run.trigger == "subagent" or run.model_metadata.get("authority") == "observe_only"
        )
        capability = (
            Capability.BACKGROUND if run.trigger in WORK_TRIGGERS else Capability.CONVERSATION
        )
        task_run = bool(run.model_metadata.get("task_id"))
    messages, pending = restore_execution(state)
    if "discovered_tool_names" not in state:
        # Restore the presentation of previously used capabilities on legacy
        # checkpoints. Discovery never changes the registry's authority checks.
        state["discovered_tool_names"] = sorted(
            {
                call.name
                for message in messages
                for call in message.tool_calls
                if call.name in registry.tools
            }
            | {call.name for call in pending if call.name in registry.tools}
        )
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
        superseded = list(pending)
        await cancel_superseded_approvals(context, superseded)
        close_unexecuted(messages, pending, None)
        clear_inflight(environment_state(state), {call.id for call in superseded})
        state.pop("waiting_call_id", None)
        await persist(context, state, messages, pending)
        for call in superseded:
            await progress(
                context,
                "tool.cancelled",
                {"name": call.name, "call_id": call.id, "code": "tool_call_superseded"},
            )

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
                await cancel_superseded_approvals(context, superseded)
                close_unexecuted(messages, pending, reason, code="tool_call_not_executed")
                clear_inflight(environment_state(state), {call.id for call in superseded})
                await persist(context, state, messages, pending)
                for call in superseded:
                    await progress(
                        context,
                        "tool.cancelled",
                        {"name": call.name, "call_id": call.id, "code": "tool_call_not_executed"},
                    )
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
                context, registry, state, messages, pending, segment, read_only
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
                if (
                    not guarded
                    and not result.get("_runtime_retry")
                    and state.get("waiting_call_id") != call.id
                ):
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
                if call.name == "tool_environment" and result.get("ok") is not False:
                    state["discovered_tool_names"] = sorted(
                        set(state["discovered_tool_names"]) | registry.discovered_names(result)
                    )
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
        remaining = final_limit - int(state.get("rounds", 0))
        if 0 < remaining <= BUDGET_WARNING_ROUNDS and state.get("budget_warned") != remaining:
            append_notice(messages, "budget", budget_warning(remaining))
            state["budget_warned"] = remaining
        turn_capability = (
            Capability.VISION if any(message.images for message in messages) else capability
        )
        reply, selection = await model_turn(
            context,
            messages,
            registry.discovery_definitions(
                read_only, set(cast(list[str], state["discovered_tool_names"]))
            ),
            turn_capability,
            capability_inventory=registry.capability_inventory(read_only),
        )
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
