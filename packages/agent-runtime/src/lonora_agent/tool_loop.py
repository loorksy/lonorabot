import json
from dataclasses import dataclass
from typing import Any

from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_contracts.model_routing import Capability
from lonora_core.run_state import is_conversational
from lonora_core.user_error import LonoraError
from lonora_db.runs import checkpoint, require_lease
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry

from .cancellation import cancellation_checkpoint
from .context.builder import build_context
from .context.skills import refresh_skill_context
from .model_runtime import model_turn
from .progress import progress
from .recovery import restore_execution
from .steering import merge_steering, owner_steering_pending
from .tasks import task_checkpoint
from .tool_guard import advance_guard


@dataclass
class LoopOutcome:
    text: str
    metadata: dict[str, Any]
    waiting: bool = False


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
            Capability.BACKGROUND
            if run.trigger in {"routine", "watch", "webhook", "tickets", "subagent"}
            else Capability.CONVERSATION
        )
    messages, pending = restore_execution(state)
    if not messages:
        messages = await build_context(context, registry)
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
            if state.get("waiting_call_id") != call.id:
                state["guard"] = advance_guard(state.get("guard", {}), call.name, call.arguments)
            await progress(context, "tool.started", {"name": call.name, "call_id": call.id})
            try:
                result = await registry.execute(call, context, read_only)
                result = {"ok": True, **result}
            except LonoraError as error:
                if error.code == "stale_lease":
                    raise
                result = {"ok": False, "code": error.code}
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
                content = json.dumps({"ok": False, "code": "tool_result_too_large"})
            messages.append(ModelMessage(role="tool", content=content, tool_call_id=call.id))
            pending = pending[1:]
            await persist(context, state, messages, pending)
            await progress(
                context,
                "tool.completed",
                {
                    "name": call.name,
                    "call_id": call.id,
                    "ok": result.get("ok"),
                    "code": result.get("code"),
                },
            )
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
            "capability": turn_capability.value,
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
