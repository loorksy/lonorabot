from time import monotonic
from typing import Any

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.domain import new_id
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.public_reply import redact_private_reply
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
from .public_stream import PublicStream
from .skills.system_policy import apply_operating_policy
from .stream_publication import StreamPublication
from .visual_response import VisualReplyProjector, visual_observation_catalog


async def model_turn(
    context: ToolContext,
    messages: list[ModelMessage],
    tools: list[ToolDefinition],
    capability: Capability,
    *,
    capability_inventory: str = "",
) -> tuple[ModelReply, ModelSelection]:
    preparation_started = monotonic()
    stage_started = preparation_started
    preparation_ms: dict[str, float] = {}

    def prepared(stage: str) -> None:
        nonlocal stage_started
        now = monotonic()
        preparation_ms[stage] = round((now - stage_started) * 1000, 2)
        stage_started = now

    await refresh_routing_context(context, messages)
    prepared("routing_context")
    request_messages = apply_operating_policy(messages, tools)
    if capability_inventory:
        # Fresh projection on every model turn, including restored checkpoints.
        # This is the actual permitted registry, not remembered self-description.
        request_messages.insert(1, ModelMessage(role="system", content=capability_inventory))
    observations = visual_observation_catalog(messages)
    if observations:
        request_messages.append(ModelMessage(role="system", content=observations))
    prepared("policy_and_observation_catalog")
    request_messages, image_diagnostics = await prepare_image_observations(
        context, request_messages
    )
    prepared("image_observations")
    if any(message.images for message in request_messages):
        capability = Capability.VISION
    turn_id = new_id()
    await progress(context, "run.reply_started", {"turn_id": turn_id})
    prepared("stream_start_commit")
    preparation_ms["total"] = round((monotonic() - preparation_started) * 1000, 2)

    public_ids = public_broker_ids(messages)
    incremental_allowed = not unverified_financial_result(messages) and not unsettled_wait_result(
        messages
    )
    streaming = PublicStream(set(), public_ids, enabled=incremental_allowed)
    projector = VisualReplyProjector(context, messages)
    request_started = monotonic()
    first_text_ms: float | None = None
    first_publication_ms: float | None = None

    def publication_for(
        active_turn: str, admission: PublicStream, compiler: VisualReplyProjector
    ) -> StreamPublication:
        last_rich: dict[str, Any] | None = None

        async def publish(raw: str) -> None:
            nonlocal last_rich, first_publication_ms
            projection = await compiler.project(raw, partial=True)
            before = len(admission.sent)
            # Completed components are independent boundaries, including images
            # whose backward-compatible text alternative may be only a newline.
            for boundary in projection.visual_boundaries():
                if boundary > len(admission.sent):
                    admission.offer(projection.text[:boundary], complete_boundary=True)
            admission.offer(projection.text)
            accepted = admission.sent[before:]
            rich = projection.rich_until(len(admission.sent))
            rich_changed = rich is not None and rich != last_rich
            if accepted or rich_changed:
                payload: dict[str, Any] = {"turn_id": active_turn, "text": accepted}
                if rich_changed:
                    payload["rich_content"] = rich
                await progress(context, "run.delta" if accepted else "run.rich_partial", payload)
                if first_publication_ms is None:
                    first_publication_ms = round((monotonic() - request_started) * 1000, 2)
                last_rich = rich

        return StreamPublication(publish)

    publication = publication_for(turn_id, streaming, projector)

    async def delta(chunk: str) -> None:
        nonlocal first_text_ms
        if chunk and first_text_ms is None:
            first_text_ms = round((monotonic() - request_started) * 1000, 2)
        await publication.offer(chunk)

    async def attempt(selection: ModelSelection) -> None:
        nonlocal turn_id, streaming, projector, publication
        await publication.cancel()
        turn_id = new_id()
        streaming = PublicStream(set(), public_ids, enabled=incremental_allowed)
        projector = VisualReplyProjector(context, messages)
        await progress(
            context,
            "run.reply_started",
            {"turn_id": turn_id, "provider": selection.provider, "model": selection.model},
        )
        publication = publication_for(turn_id, streaming, projector)

    try:
        reply, selection = await context.router.complete(
            capability, request_messages, tools, on_delta=delta, on_attempt=attempt
        )
        provider_total_ms = round((monotonic() - request_started) * 1000, 2)
        await publication.finish()
    except BaseException:
        await publication.cancel()
        raise
    # Providers cannot inject compiled display data. Only this request's output
    # can be compiled against its actual observations and owned resources.
    reply = reply.model_copy(update={"rich_content": None})
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
    # Style is model guidance, never a second generation or a failed user
    # request. Sensitive spans are removed deterministically from the actual
    # answer; financial truth was established above and is not rewritten.
    projection_started = monotonic()
    projection = await projector.project(reply.text)
    answer, rich_content = projection.text, projection.rich_until()
    visual_errors = projection.errors
    protected = redact_private_reply(answer, public_ids=public_ids)
    privacy_redacted = protected != answer or projection.privacy_redacted
    reply = reply.model_copy(update={"text": protected, "rich_content": rich_content})
    reply.provider_metadata = {
        **reply.provider_metadata,
        "runtime_capability": capability.value,
        "image_observations": image_diagnostics,
        "public_rewrite": False,
        "privacy_redacted": privacy_redacted,
        "visual_errors": visual_errors,
        "visual_diagnostics": projector.diagnostics,
        "stream_timings": {
            "preparation_ms": preparation_ms,
            "turn_first_text_ms": first_text_ms,
            "turn_request_total_ms": provider_total_ms,
            **reply.provider_metadata.get("request_timings", {}),
            "first_publication_ms": first_publication_ms,
            "final_projection_ms": round((monotonic() - projection_started) * 1000, 2),
            "preview_truncated": publication.truncated,
        },
    }
    # Publish the accepted reply once. The fenced event writer chunks it in one
    # transaction, independently of tiny provider tokens, retries or rewrites.
    if streaming.sent and not reply.text.startswith(streaming.sent):
        # Privacy redaction or a late tool call replaces the provisional generation.
        turn_id = new_id()
        await progress(context, "run.reply_started", {"turn_id": turn_id})
        streaming.sent = ""
    remaining = reply.text[len(streaming.sent) :]
    if remaining:
        await progress(context, "run.delta", {"turn_id": turn_id, "text": remaining})
    return reply, selection
