import json
import logging
from dataclasses import dataclass
from typing import Any

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
from .context.skills import refresh_skill_context
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
from .steering import merge_steering, owner_steering_pending
from .tasks import task_checkpoint
from .tool_guard import advance_guard

log = logging.getLogger("lonora.tool_loop")


@dataclass
class LoopOutcome:
    text: str
    metadata: dict[str, Any]
    waiting: bool = False
    external_wait: bool = False


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


async def execute_tool_loop(
    context: ToolContext, registry: ToolRegistry, maximum_rounds: int
) -> LoopOutcome:
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        state = dict(run.execution_state)
        read_only = (
            run.trigger == "subagent" or run.model_metadata.get("authority") == "observe_only"
        )
        capability = (
            Capability.BACKGROUND if run.trigger in WORK_TRIGGERS else Capability.CONVERSATION
        )
    messages, pending = restore_execution(state)
    if "environment" not in state and pending:
        # Older checkpoints did not distinguish proposed from in-flight calls.
        # Unknown legacy mutations must not acquire a new replay permission.
        environment_state(state)["legacy_pending"] = [call.id for call in pending]
    if not messages:
        messages = await build_context(context, registry)
    environment = environment_state(state)
    if environment.get("wait"):
        return LoopOutcome("", state.get("selection", {}), external_wait=True)
    wake = environment.get("last_wake")
    if wake and environment.get("consumed_wake") != wake:
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
    while int(state.get("rounds", 0)) < maximum_rounds:
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
                    # Persist intent before any handler can cross an effect
                    # boundary. Unreceipted mutations cannot replay after death.
                    environment["inflight"] = {
                        "call_id": call.id,
                        "route_key": route_key(call),
                        "tool": call.name,
                    }
                    await persist(context, state, messages, pending)
                    result = await registry.execute(call, context, read_only)
                result = {"ok": True, **result}
            except LonoraError as error:
                if error.code == "stale_lease":
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
            content = json.dumps(result, ensure_ascii=False)
            if len(content) > 120000:
                summary = bounded_result(result)
                try:
                    summary = await store_result(context, call, result, summary)
                except LonoraError as error:
                    if error.code == "stale_lease":
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
            if result.get("_runtime_external_wait"):
                environment_state(state)["wait"] = result["_runtime_external_wait"]
                environment_state(state)["phase"] = "waiting"
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
                return LoopOutcome("", state.get("selection", {}), external_wait=True)
            if result.get("_runtime_wait"):
                return LoopOutcome(str(result["question"]), state.get("selection", {}), True)
            if result.get("_runtime_silence") and not pending:
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
                        "reply_outcome": "answered" if prose else "silent",
                    },
                )
        if await merge_steering(context, state, messages):
            await refresh_skill_context(context, registry, messages)
        await task_checkpoint(context, state, messages)
        turn_capability = (
            Capability.VISION if any(message.images for message in messages) else capability
        )
        reply, selection = await model_turn(
            context, messages, registry.definitions(read_only), turn_capability
        )
        state["rounds"] = int(state.get("rounds", 0)) + 1
        state["selection"] = {
            "provider": selection.provider,
            "model": selection.model,
            "capability": reply.provider_metadata.get("runtime_capability", turn_capability.value),
        }
        messages.append(
            ModelMessage(role="assistant", content=reply.text, tool_calls=reply.tool_calls)
        )
        pending = list(reply.tool_calls)
        await persist(context, state, messages, pending)
        if pending:
            continue
        if await merge_steering(context, state, messages):
            await refresh_skill_context(context, registry, messages)
            continue
        if not reply.text.strip() and is_conversational(run.trigger):
            messages.append(
                ModelMessage(
                    role="system",
                    content="No answer was provided for the selected request. Provide the substantive result or ask a necessary clarification with wait_for_input. Do not invent results.",
                )
            )
            await persist(context, state, messages, pending)
            continue
        return LoopOutcome(
            reply.text,
            {**state["selection"], "reply_outcome": "answered" if reply.text.strip() else "silent"},
        )
    raise LonoraError("tool_round_limit", 409)
