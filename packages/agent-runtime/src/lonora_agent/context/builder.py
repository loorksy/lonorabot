import json
import logging
from collections.abc import Awaitable
from time import perf_counter

from lonora_adapter_kit.types import ModelMessage
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import binding_context
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow, ThreadRow
from lonora_db.trading_goals import goal_read_thread
from lonora_memory.conversation import ConversationRecallScope
from lonora_memory.semantic import retrieve_memory
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry

from ..progress import progress
from ..skills.loader import load_constitution, load_prompt
from .attachments import attachment_context
from .decisions import decision_context
from .environment import operational_context
from .goals import goal_context
from .governance import govern_context
from .history import history_context
from .memory import read_memory_context
from .reply import reply_context
from .routine import wake_context
from .scratchpad import scratchpad_context
from .skills import read_skill_context
from .team import routing_frame

log = logging.getLogger(__name__)


async def build_context(
    context: ToolContext, registry: ToolRegistry | None = None
) -> list[ModelMessage]:
    started = perf_counter()
    stages: dict[str, float] = {}

    async def timed[T](name: str, operation: Awaitable[T]) -> T:
        begin = perf_counter()
        try:
            return await operation
        finally:
            stages[name] = round((perf_counter() - begin) * 1000, 2)

    await progress(context, "run.context_started", {})
    begin = perf_counter()
    async with context.db.sessions() as session:
        run = await timed("lease", require_lease(session, context.lease))
        agent = await timed("agent", session.get(AgentRow, context.agent_id))
        thread = await timed("thread", session.get(ThreadRow, context.thread_id))
        stages["identity"] = round((perf_counter() - begin) * 1000, 2)
        if agent is None or thread is None:
            raise LonoraError("context_identity_missing", 404)
        begin = perf_counter()
        blocks = load_constitution()
        stages["constitution"] = round((perf_counter() - begin) * 1000, 2)
        blocks.extend(
            [
                agent.instructions,
                binding_context(agent),
                await timed("memory", read_memory_context(session, agent.id)),
                await timed("scratchpad", scratchpad_context(session, agent.id)),
                await timed(
                    "environment",
                    operational_context(
                        session, context.owner_id, agent.id, registry or load_tools()
                    ),
                ),
                await timed(
                    "skills", read_skill_context(session, context, agent, registry or load_tools())
                ),
                await timed("reply", reply_context(session, thread.id, run.input_seq)),
                wake_context(run),
                await timed(
                    "decisions", decision_context(session, context.owner_id, context.agent_id)
                ),
                await timed(
                    "goals",
                    goal_context(
                        session,
                        context.owner_id,
                        context.agent_id,
                        await goal_read_thread(session, run)
                        if run.model_metadata.get("authority") == "observe_only"
                        else context.thread_id,
                        run.model_metadata.get("goal_id")
                        or run.model_metadata.get("review_goal_id"),
                    ),
                ),
            ]
        )
        if thread.group_id:
            blocks.append(load_prompt("group_behavior"))
        if run.trigger == "subagent":
            blocks.append(load_prompt("subagent_system"))
        if run.model_metadata.get("voice_handoff", {}).get("finalized") is False:
            blocks.append(
                "<voice_observation>Current speech is a provisional transcript and may receive "
                "later corrections. Use the existing conversation; ask only for genuinely "
                "ambiguous details. Fragment timestamps do not establish complete intent or "
                "financial authorization. Exact financial confirmation follows the ordinary "
                "server approval policy. Keep this guidance private.</voice_observation>"
            )
        if thread.context_summary:
            blocks.append("<history_summary>" + thread.context_summary + "</history_summary>")
        attachments, images = await timed(
            "attachments",
            attachment_context(
                session, context.owner_id, thread.id, run.input_seq, context.artifact_root
            ),
        )
        if attachments:
            blocks.append(attachments)
        messages = [
            ModelMessage(role="system", content="\n\n".join(block for block in blocks if block)),
            ModelMessage(
                role="system",
                content=await timed(
                    "collaboration",
                    routing_frame(
                        session, context.owner_id, context.agent_id, context.thread_id, run
                    ),
                ),
            ),
        ] + await timed(
            "history",
            history_context(
                session, thread.id, run.input_seq, thread.summary_seq, context.agent_id
            ),
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
            semantic = await timed(
                "recall",
                retrieve_memory(
                    context.db,
                    context.router.credentials,
                    context.owner_id,
                    agent.id,
                    query,
                    conversation_scope=ConversationRecallScope(
                        thread.id, run.input_seq, thread.summary_seq, include_neighbor=True
                    )
                    if thread.agent_id == agent.id
                    and not thread.group_id
                    and thread.purpose == "conversation"
                    else None,
                ),
            )
            if semantic:
                messages[0].content += "\n\n" + semantic
        if images:
            target = next(
                (message for message in reversed(messages) if message.role == "user"), None
            )
            if target:
                target.images = images
        begin = perf_counter()
        prepared = govern_context(messages)
        stages["governance"] = round((perf_counter() - begin) * 1000, 2)
    duration = round((perf_counter() - started) * 1000, 2)
    log.info(
        "agent_context_ready duration_ms=%.2f messages=%d stages_ms=%s",
        duration,
        len(prepared),
        json.dumps(stages, sort_keys=True),
    )
    await progress(context, "run.context_ready", {"duration_ms": duration, "stage_timings": stages})
    return prepared
