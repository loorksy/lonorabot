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
from .skills.system_policy import apply_operating_policy, policy_bundle


async def model_turn(
    context: ToolContext,
    messages: list[ModelMessage],
    tools: list[ToolDefinition],
    capability: Capability,
) -> tuple[ModelReply, ModelSelection]:
    await refresh_routing_context(context, messages)
    request_messages, image_diagnostics = await prepare_image_observations(
        context, apply_operating_policy(messages, tools)
    )
    if any(message.images for message in request_messages):
        capability = Capability.VISION
    turn_id = new_id()
    await progress(context, "run.reply_started", {"turn_id": turn_id})
    fragments: list[str] = []

    async def delta(chunk: str) -> None:
        fragments.append(chunk)
        # Provisional provider text is private until the complete reply passes
        # the disclosure boundary. A later rewrite cannot retract leaked bytes.

    async def attempt(selection: ModelSelection) -> None:
        nonlocal turn_id
        turn_id = new_id()
        fragments.clear()
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
            rewrite_messages = [
                *request_messages,
                ModelMessage(role="assistant", content=reply.text),
                ModelMessage(
                    role="system",
                    content="Rewrite only the preceding answer in the owner's conversation language. "
                    "Keep its supported facts, uncertainty and result unchanged. "
                    "Do not perform work, call anything or add success claims. "
                    "Use short ordinary prose without internal identifiers, machine status, "
                    "cards, tools, skills, runs, events, API or translated equivalents. "
                    "For approval say the request awaits confirmation. For pending verification "
                    "say the actual outcome still needs checking. Never claim an action occurred "
                    "unless its independently verified evidence is present.",
                ),
            ]
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
    # Emit only accepted text, including providers that omit or retry deltas.
    accepted = (
        fragments
        if "".join(fragments) == reply.text
        else [reply.text[offset : offset + 120] for offset in range(0, len(reply.text), 120)]
    )
    for chunk in accepted:
        await progress(context, "run.delta", {"turn_id": turn_id, "text": chunk})
    return reply, selection
