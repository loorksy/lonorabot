import time

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.domain import new_id
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_llm_usage.models import UsageRecord
from lonora_llm_usage.store import save_usage
from lonora_tools.context import ToolContext

from .progress import progress


async def model_turn(
    context: ToolContext,
    messages: list[ModelMessage],
    tools: list[ToolDefinition],
    capability: Capability,
) -> tuple[ModelReply, ModelSelection]:
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

    reply, selection = await context.router.complete(capability, messages, tools, on_delta=delta)
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
