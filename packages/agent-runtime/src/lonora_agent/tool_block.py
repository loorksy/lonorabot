"""Execute an assistant tool-call block and record its results in call order.

Segments come from ``tool_batch``, every call runs under ``tool_dispatch``'s
receipt, reconciliation and crash-replay rules, and ``tool_intent`` marks the
intent before an effect. Results are observed, appended and checkpointed in
the original call order through the loop's ``save``. A read retry, a trade
approval and the waits suspend the block exactly where their call left it.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import request_hash
from lonora_tools.base import Tool, ToolScope
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from lonora_tools.tool_results import store_result

from .context.skills import assert_skill_authority
from .context_engine import FENCE_CODES, record_observed
from .environment import (
    ToolRetryScheduled,
    bounded_result,
    environment_state,
    observe,
    schedule_retry,
)
from .loop_outcomes import (
    LoopOutcome,
    external_wait_outcome,
    final_answer,
    question_outcome,
    rich_metadata,
    supersede_wait_siblings,
    wait_update,
)
from .progress import progress
from .runtime_notices import attach_notice
from .skills.access import admitted_view_ids
from .tool_batch import Segment, gather_bounded, next_segment
from .tool_dispatch import dispatch_call
from .tool_exposure import remember_use
from .tool_guardrails import after_call, before_call, blocked_result
from .tool_intent import (
    cancel_superseded_approvals,
    clear_inflight,
    close_unexecuted,
    inflight_ids,
    mark_inflight,
)

log = logging.getLogger("lonora.tool_loop")


async def close_pending(
    context: ToolContext,
    registry: ToolRegistry,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
    reason: str | None,
    code: str,
) -> tuple[list[ToolCall], list[ToolCall]]:
    """Answer every pending call; return them and those that may already have executed.

    A non-read-only call whose in-flight marker survived a restart may have crossed
    its effect boundary before the worker died. It is answered as dispatch answers an
    interrupted call (``tool_execution_uncertain``, route marked ambiguous), never as
    superseded or not executed, so the model reconciles instead of repeating it. The
    approvals of the other calls are cancelled and every intent marker is cleared.
    """
    environment = environment_state(state)
    started = inflight_ids(environment) | set(environment.get("legacy_pending", []))
    closed = list(pending)
    uncertain: list[ToolCall] = []
    for call in closed:
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
        if identifier not in {call.id for call in closed}
    ]
    pending.clear()
    await cancel_superseded_approvals(context, [c for c in closed if c not in uncertain])
    clear_inflight(environment, {call.id for call in closed})
    return closed, uncertain


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


def started_payload(call: ToolCall, tool: Tool | None) -> dict[str, Any]:
    """The activity line's facts: the registry's toolset and effect, never a guessed label."""
    payload: dict[str, Any] = {"name": call.name, "call_id": call.id}
    if tool is not None:
        payload["toolset"] = tool.toolset
        payload["effect"] = (
            "financial" if tool.financial else "read" if tool.read_only else "change"
        )
    return payload


def contract_hash(tool: Tool | None) -> str | None:
    return request_hash(tool.definition().model_dump(mode="json")) if tool else None


async def execute_segment(
    context: ToolContext,
    registry: ToolRegistry,
    state: dict[str, Any],
    segment: Segment,
    scope: ToolScope,
    save: Callable[[], Awaitable[None]],
) -> list[dict[str, Any]]:
    """Run one segment; results come back in the original call order."""
    environment = environment_state(state)
    interrupted = inflight_ids(environment) | set(environment.get("legacy_pending", []))
    decisions = [before_call(state, call, registry.tools.get(call.name)) for call in segment.calls]
    for call in segment.calls:
        await progress(
            context, "tool.started", started_payload(call, registry.tools.get(call.name))
        )
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
            await save()

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
            if error.code in FENCE_CODES:
                raise
            # As for a serial call, any other refusal is each call's observation.
            return [
                {"ok": False, "code": error.code}
                if decision.action not in {"block", "halt"}
                else blocked_result(decision)
                for decision in decisions
            ]
        mark_inflight(environment_state(state), runnable)
        await save()

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


async def result_content(context: ToolContext, call: ToolCall, result: dict[str, Any]) -> str:
    """The transcript form of a result; an oversized one is stored and bounded."""
    content = json.dumps(result, ensure_ascii=False)
    if len(content) <= 120000:
        return content
    summary = bounded_result(result)
    if "runtime_notice" in result:
        summary["runtime_notice"] = result["runtime_notice"]
    try:
        summary = await store_result(context, call, result, summary)
    except LonoraError as error:
        if error.code in FENCE_CODES:
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
    return json.dumps(summary, ensure_ascii=False)


async def execute_next_segment(
    context: ToolContext,
    registry: ToolRegistry,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
    exposure: dict[str, Any],
    scope: ToolScope,
    save: Callable[[], Awaitable[None]],
) -> LoopOutcome | None:
    """Execute the block's next segment and record each result, removing it from ``pending``.

    Returns the outcome that ends this pass (an approval, a wait or a silent
    final answer), or ``None`` when the block continues.
    """
    segment = next_segment(pending, registry.tools)
    results = await execute_segment(context, registry, state, segment, scope, save)
    for index, (call, result) in enumerate(zip(segment.calls, results, strict=True)):
        tool = registry.tools.get(call.name)
        guarded = result.get("code") == "guardrail_blocked" and result.get("executed") is False
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
                    "contract_hash": contract_hash(tool),
                },
            )
            schedule_retry(state, call, record["failures"])
            await save()
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
            await save()
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
        content = await result_content(context, call, result)
        messages.append(ModelMessage(role="tool", content=content, tool_call_id=call.id))
        record_observed(state, call.id)
        del pending[0]
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
        await save()
        await progress(
            context,
            "tool.completed",
            {
                "name": call.name,
                "call_id": call.id,
                "ok": result.get("ok"),
                "code": result.get("code"),
                "contract_hash": contract_hash(tool),
            },
        )
        await remember_use(context, registry, exposure, call, result, scope=scope)
        if result.get("_runtime_external_wait"):
            await report_closed(context, superseded, [], "tool_call_superseded")
            return external_wait_outcome(state)
        if result.get("_runtime_wait"):
            return question_outcome(state, state["pending_input_request"])
        if result.get("_runtime_silence") and not pending:
            prose = next(
                (message.content for message in reversed(messages) if message.role == "assistant"),
                "",
            ).strip()
            outcome = await final_answer(
                context,
                state,
                messages,
                prose,
                {
                    **state.get("selection", {}),
                    "reply_outcome": "answered" if prose or rich_metadata(state) else "silent",
                    **rich_metadata(state),
                },
                save,
            )
            if outcome is not None:
                return outcome
    return None
