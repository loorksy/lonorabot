from lonora_adapter_kit.types import ModelMessage
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import binding_context
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow, ThreadRow
from lonora_db.trading_goals import goal_read_thread
from lonora_memory.semantic import retrieve_memory
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry

from ..skills.loader import load_constitution, load_prompt
from .attachments import attachment_context
from .decisions import decision_context
from .goals import goal_context
from .governance import govern_context
from .history import history_context
from .memory import read_memory_context
from .reply import reply_context
from .routine import wake_context
from .scratchpad import scratchpad_context
from .skills import read_skill_context
from .team import routing_frame


async def build_context(
    context: ToolContext, registry: ToolRegistry | None = None
) -> list[ModelMessage]:
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        agent = await session.get(AgentRow, context.agent_id)
        thread = await session.get(ThreadRow, context.thread_id)
        if agent is None or thread is None:
            raise LonoraError("context_identity_missing", 404)
        blocks = load_constitution()
        blocks.extend(
            [
                agent.instructions,
                binding_context(agent),
                await read_memory_context(session, agent.id),
                await scratchpad_context(session, agent.id),
                await read_skill_context(session, context, agent, registry or load_tools()),
                await reply_context(session, thread.id, run.input_seq),
                wake_context(run),
                await decision_context(session, context.owner_id, context.agent_id),
                await goal_context(
                    session,
                    context.owner_id,
                    context.agent_id,
                    await goal_read_thread(session, run)
                    if run.model_metadata.get("authority") == "observe_only"
                    else context.thread_id,
                    run.model_metadata.get("goal_id") or run.model_metadata.get("review_goal_id"),
                ),
            ]
        )
        if thread.group_id:
            blocks.append(load_prompt("group_behavior"))
        if run.trigger == "subagent":
            blocks.append(load_prompt("subagent_system"))
        if thread.context_summary:
            blocks.append("<history_summary>" + thread.context_summary + "</history_summary>")
        attachments, images = await attachment_context(
            session, context.owner_id, thread.id, run.input_seq, context.artifact_root
        )
        if attachments:
            blocks.append(attachments)
        messages = [
            ModelMessage(role="system", content="\n\n".join(block for block in blocks if block)),
            ModelMessage(
                role="system",
                content=await routing_frame(
                    session, context.owner_id, context.agent_id, context.thread_id
                ),
            ),
        ] + await history_context(
            session, thread.id, run.input_seq, thread.summary_seq, context.agent_id
        )
        # New peer requests already exist as attributed messages in the canonical history.
        # Appending their task again would duplicate context and override later owner steering.
        explicit_prompt = (
            ""
            if run.trigger == "peer" and run.model_metadata.get("peer_message_id")
            else run.prompt
        )
        if explicit_prompt:
            messages.append(ModelMessage(role="user", content=explicit_prompt))
        query = explicit_prompt or next(
            (message.content for message in reversed(messages) if message.role == "user"), ""
        )
        if query:
            semantic = await retrieve_memory(
                context.db, context.router.credentials, context.owner_id, agent.id, query
            )
            if semantic:
                messages[0].content += "\n\n" + semantic
        if images:
            target = next(
                (message for message in reversed(messages) if message.role == "user"), None
            )
            if target:
                target.images = images
        return govern_context(messages)
