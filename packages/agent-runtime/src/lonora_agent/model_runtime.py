from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.domain import new_id
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.public_reply import public_reply_violation
from lonora_core.user_error import LonoraError
from lonora_llm_usage.models import UsageRecord
from lonora_llm_usage.store import save_usage
from lonora_tools.context import ToolContext

from .context.financial_result import (
    FINANCIAL_CALLS,
    public_broker_ids,
    unsettled_wait_result,
    unverified_financial_result,
)
from .context.image_observations import prepare_image_observations
from .context.team import refresh_routing_context
from .progress import progress
from .public_rewrite import rewrite_request
from .public_stream import PublicStream
from .skills.system_policy import apply_operating_policy, policy_bundle


async def model_turn(
    context: ToolContext,
    messages: list[ModelMessage],
    tools: list[ToolDefinition],
    capability: Capability,
    *,
    capability_inventory: str = "",
) -> tuple[ModelReply, ModelSelection]:
    await refresh_routing_context(context, messages)
    request_messages = apply_operating_policy(messages, tools)
    if capability_inventory:
        # Fresh projection on every model turn, including restored checkpoints.
        # This is the actual permitted registry, not remembered self-description.
        request_messages.insert(1, ModelMessage(role="system", content=capability_inventory))
    request_messages, image_diagnostics = await prepare_image_observations(
        context, request_messages
    )
    if any(message.images for message in request_messages):
        capability = Capability.VISION
    turn_id = new_id()
    await progress(context, "run.reply_started", {"turn_id": turn_id})

    names = set(policy_bundle().tool_policies) | {tool.name for tool in tools}
    public_ids = public_broker_ids(messages)
    streaming = PublicStream(
        names,
        public_ids,
        enabled=not any(tool.name in FINANCIAL_CALLS for tool in tools)
        and not unverified_financial_result(messages)
        and not unsettled_wait_result(messages),
    )

    async def delta(chunk: str) -> None:
        accepted = streaming.feed(chunk)
        if accepted:
            await progress(context, "run.delta", {"turn_id": turn_id, "text": accepted})

    async def attempt(selection: ModelSelection) -> None:
        nonlocal turn_id, streaming
        turn_id = new_id()
        streaming = PublicStream(names, public_ids, enabled=streaming.enabled)
        await progress(
            context,
            "run.reply_started",
            {"turn_id": turn_id, "provider": selection.provider, "model": selection.model},
        )

    reply, selection = await context.router.complete(
        capability, request_messages, tools, on_delta=delta, on_attempt=attempt
    )
    await save_usage(
        context.db,
        context.owner_id,
        context.agent_id,
        context.thread_id,
        UsageRecord(
            context.lease.run_id,
            selection.provider,
            selection.model,
            reply.usage,
            context_budget=reply.provider_metadata.get("context_budget", {}),
        ),
    )
    # A compact advertised surface must not weaken public disclosure checks for
    # other first-party capability names retained in history or tool results.
    names = set(policy_bundle().tool_policies) | {tool.name for tool in tools}
    public_ids = public_broker_ids(messages)
    unverified = unverified_financial_result(messages)
    if any(call.name in FINANCIAL_CALLS for call in reply.tool_calls):
        # Proposed mutations have no broker outcome yet. Keep their execution
        # once, but do not publish premature success beside the proposal.
        reply = reply.model_copy(update={"text": ""})
    elif unverified and (reply.text or not reply.tool_calls):
        # A wait may carry an owner update as well as tool calls. That prose
        # has the same independent-verification boundary as a final answer.
        reply = reply.model_copy(update={"text": unverified})
    elif any(call.name == "task_wait" for call in reply.tool_calls):
        # Continuous work still reports real failures before suspending. Never
        # replace an uncertain result with a premature success or silent wait.
        result_summary = unsettled_wait_result(messages)
        if result_summary:
            reply = reply.model_copy(update={"text": result_summary})
    rewritten = False
    if public_reply_violation(reply.text, names, public_ids=public_ids):
        if reply.tool_calls:
            # Keep the actual operation once; discard only private narration.
            reply = reply.model_copy(update={"text": ""})
        else:
            rewritten = True
            # Editing is a separate text-only task. Replaying the working
            # conversation here made the model repeat the owner's raw diagnostic
            # codes instead of explaining their meaning, rejecting even greetings.
            rewrite_messages = rewrite_request(reply.text)
            reply, selection = await context.router.complete(
                capability, rewrite_messages, [], on_delta=delta, on_attempt=attempt
            )
            await save_usage(
                context.db,
                context.owner_id,
                context.agent_id,
                context.thread_id,
                UsageRecord(
                    context.lease.run_id,
                    selection.provider,
                    selection.model,
                    reply.usage,
                    context_budget=reply.provider_metadata.get("context_budget", {}),
                ),
            )
            if reply.tool_calls or public_reply_violation(reply.text, names, public_ids=public_ids):
                raise LonoraError("public_reply_unavailable", 502)
    reply.provider_metadata = {
        **reply.provider_metadata,
        "runtime_capability": capability.value,
        "image_observations": image_diagnostics,
        "public_rewrite": rewritten,
    }
    # Publish the accepted reply once. The fenced event writer chunks it in one
    # transaction, independently of tiny provider tokens, retries or rewrites.
    if streaming.sent and not reply.text.startswith(streaming.sent):
        # A guarded rewrite or late tool call replaces the provisional generation.
        turn_id = new_id()
        await progress(context, "run.reply_started", {"turn_id": turn_id})
        streaming.sent = ""
    remaining = reply.text[len(streaming.sent) :]
    if remaining:
        await progress(context, "run.delta", {"turn_id": turn_id, "text": remaining})
    return reply, selection
