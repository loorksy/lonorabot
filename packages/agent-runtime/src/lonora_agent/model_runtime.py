import time

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.domain import new_id
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_llm_usage.models import UsageRecord
from lonora_llm_usage.store import save_usage
from lonora_tools.context import ToolContext

from .context.governance import MAXIMUM_CONTEXT_CHARS, govern_context
from .context.team import refresh_routing_context
from .progress import progress


async def model_turn(
    context: ToolContext,
    messages: list[ModelMessage],
    tools: list[ToolDefinition],
    capability: Capability,
) -> tuple[ModelReply, ModelSelection]:
    await refresh_routing_context(context, messages)
    messages = govern_context(
        messages, MAXIMUM_CONTEXT_CHARS - sum(len(tool.model_dump_json()) for tool in tools)
    )
    turn_id = new_id()
    await progress(context, "run.reply_started", {"turn_id": turn_id})
    buffer = ""
    last_emit = time.monotonic()

    async def delta(chunk: str) -> None:
        nonlocal buffer, last_emit
        buffer += chunk
        if len(buffer) >= 120 or time.monotonic() - last_emit >= 0.15:
            await progress(context, "run.delta", {"turn_id": turn_id, "text": buffer})
            buffer = ""
            last_emit = time.monotonic()

    async def attempt(selection: ModelSelection) -> None:
        nonlocal turn_id, buffer
        turn_id = new_id()
        buffer = ""
        await progress(
            context,
            "run.reply_started",
            {"turn_id": turn_id, "provider": selection.provider, "model": selection.model},
        )

    reply, selection = await context.router.complete(
        capability, messages, tools, on_delta=delta, on_attempt=attempt
    )
    if buffer:
        await progress(context, "run.delta", {"turn_id": turn_id, "text": buffer})
    await save_usage(
        context.db,
        context.owner_id,
        context.agent_id,
        context.thread_id,
        UsageRecord(context.lease.run_id, selection.provider, selection.model, reply.usage),
    )
    return reply, selection
