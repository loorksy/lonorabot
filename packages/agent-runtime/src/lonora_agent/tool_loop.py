import json
import logging
from dataclasses import dataclass, replace
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_contracts.model_routing import Capability
from lonora_contracts.runs import WORK_TRIGGERS
from lonora_core.run_state import is_conversational
from lonora_core.user_error import LonoraError
from lonora_db.runs import checkpoint, require_lease
from lonora_session.idempotency import request_hash
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from lonora_tools.schema import ToolArgumentsError
from lonora_tools.tool_results import store_result, stored_result

from .cancellation import cancellation_checkpoint
from .context.builder import build_context
from .context.skills import assert_skill_authority, refresh_skill_context, selected_skill_ids
from .continuation import schedule_task_continuation, slice_limit
from .environment import (
    ToolRetryScheduled,
    blocked_route,
    bounded_result,
    environment_state,
    observe,
    retry_pending,
    route_key,
    schedule_retry,
)
from .model_runtime import model_turn
from .progress import progress
from .recovery import restore_execution
from .skills.access import RunSkillAccess, admitted_view_ids
from .skills.snapshot import read_snapshot
from .steering import merge_steering, owner_steering_pending
from .stop_gates import reset_stop_gate, task_stop_gate
from .tasks import task_checkpoint
from .tool_guard import advance_guard

log = logging.getLogger("lonora.tool_loop")


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
    for sibling in pending:
        messages.append(
            ModelMessage(
                role="tool",
                tool_call_id=sibling.id,
                content=json.dumps(
                    {
                        "ok": False,
                        "code": "tool_call_superseded",
                        "reason": "task_wait_requires_fresh_analysis_after_wake",
                    }
                ),
            )
        )
    pending.clear()


async def report_wait_superseded(context: ToolContext, superseded: list[ToolCall]) -> None:
    for sibling in superseded:
        await progress(
            context,
            "tool.cancelled",
            {"name": sibling.name, "call_id": sibling.id, "code": "tool_call_superseded"},
        )


async def continue_ongoing_task(
    context: ToolContext, state: dict[str, Any], messages: list[ModelMessage]
) -> bool:
    verdict = await task_stop_gate(context, state)
    if verdict.continue_turn:
        messages.append(ModelMessage(role="system", content=verdict.nudge or ""))
        await persist(context, state, messages, [])
    return verdict.continue_turn


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
    while int(state.get("rounds", 0)) < slice_limit(state, maximum_rounds):
        await cancellation_checkpoint(context)
        await task_checkpoint(context)
        # New user input follows the complete tool-result block, never splits it.
        while pending:
            await task_checkpoint(context)
            if await owner_steering_pending(context):
                superseded = list(pending)
                from lonora_db.schema import TradeApprovalRow
                from lonora_db.trade_approvals import approval_event
                from lonora_session.idempotency import stable_id

                async with context.db.sessions() as session, session.begin():
                    await require_lease(session, context.lease, lock=True)
                    for superseded_call in superseded:
                        approval = await session.get(
                            TradeApprovalRow,
                            stable_id(context.lease.run_id, "approval:" + superseded_call.id),
                            with_for_update=True,
                        )
                        if approval and approval.status in {"pending", "approved"}:
                            approval.status = "cancelled"
                            approval_event(session, approval)

                for call in superseded:
                    messages.append(
                        ModelMessage(
                            role="tool",
                            tool_call_id=call.id,
                            content=json.dumps({"ok": False, "code": "tool_call_superseded"}),
                        )
                    )
                pending.clear()
                state.pop("waiting_call_id", None)
                await persist(context, state, messages, pending)
                for call in superseded:
                    await progress(
                        context,
                        "tool.cancelled",
                        {"name": call.name, "call_id": call.id, "code": "tool_call_superseded"},
                    )
                break
            call = pending[0]
            if retry_pending(state, call):
                raise ToolRetryScheduled()
            tool = registry.tools.get(call.name)
            blocked = blocked_route(state, call)
            environment = environment_state(state)
            interrupted = environment.get("inflight", {}).get(
                "call_id"
            ) == call.id or call.id in environment.get("legacy_pending", [])
            result: dict[str, Any]
            await progress(context, "tool.started", {"name": call.name, "call_id": call.id})
            try:
                receipt = await stored_result(context, call)
                if (
                    receipt is not None
                    and receipt.get("status") == "ambiguous"
                    and tool
                    and tool.financial
                    and tool.replay_safe
                ):
                    # The financial handler owns its durable journal and reconciles
                    # the SAME operation. An observation receipt must not freeze it.
                    receipt = None
                if receipt is not None:
                    result = receipt
                elif (
                    blocked
                    and blocked.get("ambiguous")
                    and blocked.get("receipt_replay")
                    and tool
                    and tool.financial
                    and tool.replay_safe
                ):
                    # Inspect/reconcile the SAME durable financial operation,
                    # even if the model invents a new call ID. Never mint a new
                    # approval/operation merely to learn the previous outcome.
                    original = call.model_copy(update={"id": blocked["origin_call_id"]})
                    result = await registry.execute(original, context, read_only)
                elif blocked:
                    result = {
                        "ok": False,
                        "code": "broker_result_ambiguous"
                        if blocked.get("ambiguous")
                        else "tool_route_exhausted",
                        "recovery": {
                            "next_action": "reconcile_before_any_resend"
                            if blocked.get("ambiguous")
                            else "alternate_route_or_wait"
                        },
                    }
                elif interrupted and not (
                    tool
                    and (
                        tool.read_only
                        or (
                            tool.replay_safe
                            and (
                                call.id not in environment.get("legacy_pending", [])
                                or tool.legacy_replay_safe
                            )
                        )
                    )
                ):
                    result = {"ok": False, "code": "tool_execution_uncertain"}
                else:
                    # Receipts and known financial reconciliation above retain priority.
                    # New effects cannot use instructions withdrawn since selection.
                    await assert_skill_authority(
                        context, registry, active_ids=state["instruction_skill_ids"]
                    )
                    # Persist intent before any handler can cross an effect
                    # boundary. Unreceipted mutations cannot replay after death.
                    environment["inflight"] = {
                        "call_id": call.id,
                        "route_key": route_key(call),
                        "tool": call.name,
                    }
                    await persist(context, state, messages, pending)
                    result = await registry.execute(
                        call,
                        replace(
                            context,
                            skill_access=RunSkillAccess(
                                registry, tuple(state["instruction_skill_ids"])
                            ),
                        ),
                        read_only,
                    )
                result = {"ok": True, **result}
            except LonoraError as error:
                if error.code in {"stale_lease", "skill_continuation_unavailable"}:
                    raise
                error_result: dict[str, Any] = {"ok": False, "code": error.code}
                if isinstance(error, ToolArgumentsError):
                    error_result["issues"] = error.issues
                    error_result["retryable"] = True
                result = error_result
            except (TimeoutError, ConnectionError) as error:
                result = {
                    "ok": False,
                    "code": (
                        "tool_read_timeout"
                        if isinstance(error, TimeoutError)
                        else "tool_connection_failure"
                    )
                    if tool and tool.read_only
                    else "tool_execution_uncertain",
                }
            except Exception as error:
                # Unknown tool failures remain observations. Exception content
                # may contain credentials; only the type belongs in diagnostics.
                log.warning(
                    "tool_execution_failed name=%s type=%s", call.name, type(error).__name__
                )
                result = {
                    "ok": False,
                    "code": "tool_internal_failure"
                    if tool and tool.read_only
                    else "tool_execution_uncertain",
                }
            record = observe(state, call, tool, result)
            environment_state(state).pop("inflight", None)
            environment_state(state)["legacy_pending"] = [
                identifier
                for identifier in environment_state(state).get("legacy_pending", [])
                if identifier != call.id
            ]
            environment_state(state).pop("retry", None)
            if result.get("recovery", {}).get("safe_to_retry"):
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
            if result.get("ok") is not False and state.get("waiting_call_id") != call.id:
                state["guard"] = advance_guard(state.get("guard", {}), call.name, call.arguments)
            if result.get("_runtime_retry"):
                state["waiting_call_id"] = call.id
                await persist(context, state, messages, pending)
                return LoopOutcome(
                    str(result.get("question", "")),
                    {**state.get("selection", {}), "trade_approval_id": result.get("approval_id")},
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
                environment_state(state)["wait"] = result["_runtime_external_wait"]
                environment_state(state)["wait_update"] = wait_update(messages, call.id)
                environment_state(state)["phase"] = "waiting"
                superseded = list(pending)
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
                if await continue_ongoing_task(context, state, messages):
                    break
                prose = next(
                    (
                        message.content
                        for message in reversed(messages)
                        if message.role == "assistant"
                    ),
                    "",
                ).strip()
                return LoopOutcome(
                    prose,
                    {
                        **state.get("selection", {}),
                        "reply_outcome": "answered" if prose or rich_metadata(state) else "silent",
                        **rich_metadata(state),
                    },
                )
        if await merge_steering(context, state, messages):
            updated_skills = await refresh_skill_context(
                context, registry, messages, retained_ids=state.get("viewed_skill_ids", [])
            )
            if updated_skills is not None:
                state["instruction_skill_ids"] = sorted(
                    set(updated_skills) | set(state.get("viewed_skill_ids", []))
                )
        await task_checkpoint(context, state, messages)
        await assert_skill_authority(
            context, registry, active_ids=cast(list[str], state["instruction_skill_ids"])
        )
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
            updated_skills = await refresh_skill_context(
                context, registry, messages, retained_ids=state.get("viewed_skill_ids", [])
            )
            if updated_skills is not None:
                state["instruction_skill_ids"] = sorted(
                    set(updated_skills) | set(state.get("viewed_skill_ids", []))
                )
            continue
        if not reply.text.strip() and reply.rich_content is None and is_conversational(run.trigger):
            messages.append(
                ModelMessage(
                    role="system",
                    content="No answer was provided for the selected request. Provide the substantive result or ask a necessary clarification with wait_for_input. Do not invent results.",
                )
            )
            await persist(context, state, messages, pending)
            continue
        if await continue_ongoing_task(context, state, messages):
            continue
        return LoopOutcome(
            reply.text,
            {
                **state["selection"],
                **rich_metadata(state),
                "reply_outcome": "answered"
                if reply.text.strip() or reply.rich_content
                else "silent",
            },
        )
    if await schedule_task_continuation(context, state, maximum_rounds):
        raise ToolRetryScheduled()
    raise LonoraError("tool_round_limit", 409)
