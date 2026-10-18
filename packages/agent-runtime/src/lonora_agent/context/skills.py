from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow, CloudChartRow, MessageRow, SkillRow
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..skills.registry import built_in_skills, installed_registry, legacy_skill_id
from ..skills.resolver import SkillSignals, resolve_skills
from ..skills.runtime import infer_intents
from ..skills.snapshot import apply_snapshot, read_snapshot, write_snapshot


async def read_skill_context(
    session: AsyncSession,
    context: ToolContext,
    agent: AgentRow,
    registry: ToolRegistry,
    task_text: str | None = None,
) -> str:
    run = await require_lease(session, context.lease)
    rows = (await session.scalars(select(SkillRow).where(SkillRow.agent_id == agent.id))).all()
    latest = await session.scalar(
        select(MessageRow.content)
        .where(
            MessageRow.thread_id == context.thread_id,
            MessageRow.role == "user",
            MessageRow.seq <= run.input_seq,
        )
        .order_by(MessageRow.seq.desc())
        .limit(1)
    )
    text = task_text if task_text is not None else run.prompt or latest or ""
    requested_raw: Any = run.model_metadata.get("requested_skills", [])
    requested: set[str] = set()
    if isinstance(requested_raw, list):
        requested = {item for item in cast(list[Any], requested_raw) if isinstance(item, str)}
    # Explicit names in an owner request are instruction-selection hints, never command routing.
    names = {name: name for name in built_in_skills()}
    for row in rows:
        name = str(row.payload.get("name", ""))
        names[name] = name if row.payload.get("manifest") else legacy_skill_id(name)
    for name, identity in names.items():
        if name and f"[skill:{name}]" in text:
            requested.add(identity)
    has_goal = isinstance(run.model_metadata.get("goal_id"), str)
    has_chart = bool(
        await session.scalar(
            select(CloudChartRow.id).where(CloudChartRow.agent_id == agent.id).limit(1)
        )
    )
    read_only = run.trigger == "subagent" or run.model_metadata.get("authority") == "observe_only"
    available = {item.name for item in registry.definitions(read_only=read_only)}
    signals = SkillSignals(
        intents=infer_intents(text, has_goal=has_goal, trigger=run.trigger),
        trigger=run.trigger,
        read_only=read_only,
        requested=frozenset(requested),
        available_tools=frozenset(available),
        has_market=bool(agent.trading_account_id),
        has_goal=has_goal,
        has_chart=has_chart,
    )
    known_tools = {item.name for item in registry.definitions()}
    skills, rejected = installed_registry([row.payload for row in rows], known_tools)
    snapshot = read_snapshot(run.model_metadata.get("skill_snapshot"))
    skills = apply_snapshot(skills, rejected, snapshot, known_tools)
    selection = resolve_skills(skills, signals, rejected=rejected)
    snapshot_payload = write_snapshot(snapshot, selection)
    # Hold the run fence only for the metadata write, never while retrieving memory/context.
    async with context.db.sessions() as writer, writer.begin():
        locked = await require_lease(writer, context.lease, lock=True)
        locked.model_metadata = {
            **locked.model_metadata,
            "skill_selection": selection.diagnostics(),
            "skill_snapshot": snapshot_payload,
        }

    return "<skill_runtime>\n" + selection.context() + "\n</skill_runtime>"


async def refresh_skill_context(
    context: ToolContext, registry: ToolRegistry, messages: list["ModelMessage"]
) -> None:
    """Steering may change relevance; retain policies, history and indivisible tool exchanges."""
    import re

    async with context.db.sessions() as session:
        agent = await session.get(AgentRow, context.agent_id)
        if agent is None:
            return
        task_text = next((item.content for item in reversed(messages) if item.role == "user"), None)
        block = await read_skill_context(session, context, agent, registry, task_text)
    for message in messages:
        if message.role == "system" and "<skill_runtime>" in message.content:
            message.content = re.sub(
                r"<skill_runtime>.*?</skill_runtime>",
                lambda _: block,
                message.content,
                count=1,
                flags=re.S,
            )
            return
