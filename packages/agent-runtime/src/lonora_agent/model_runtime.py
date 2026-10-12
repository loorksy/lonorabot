from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_llm_usage.models import UsageRecord
from lonora_llm_usage.store import save_usage
from lonora_tools.context import ToolContext


async def model_turn(
    context: ToolContext,
    messages: list[ModelMessage],
    tools: list[ToolDefinition],
    capability: Capability,
) -> tuple[ModelReply, ModelSelection]:
    reply, selection = await context.router.complete(capability, messages, tools)
    await save_usage(
        context.db,
        context.owner_id,
        context.agent_id,
        context.thread_id,
        UsageRecord(context.lease.run_id, selection.provider, selection.model, reply.usage),
    )
    return reply, selection
