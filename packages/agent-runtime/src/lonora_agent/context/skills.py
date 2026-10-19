from collections.abc import Sequence
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow, CloudChartRow, MessageRow, SkillRow
from lonora_db.skill_controls import read_skill_controls
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..skills.registry import SkillRegistry, built_in_skills, installed_registry, legacy_skill_id
from ..skills.resolver import SkillSignals, eligibility_reason, resolve_skills
from ..skills.runtime import infer_intents
from ..skills.snapshot import MAX_SNAPSHOT_SKILLS, apply_snapshot, read_snapshot, write_snapshot


async def effective_skill_registry(
    session: AsyncSession,
    context: ToolContext,
    registry: ToolRegistry,
    rows: Sequence[SkillRow],
    metadata: dict[str, Any],
) -> tuple[SkillRegistry, dict[str, str]]:
    """One effective pinned catalog for automatic selection and progressive reads."""
    known_tools = {item.name for item in registry.definitions()}
    skills, rejected = installed_registry([row.payload for row in rows], known_tools)
    skills = apply_snapshot(
        skills, rejected, read_snapshot(metadata.get("skill_snapshot")), known_tools
    )
    controls = await read_skill_controls(session, context.owner_id, context.agent_id)
    revoked = {(item.skill_id, item.version) for item in controls.revoked}
    for identity, definition in skills.definitions.items():
        if (identity, definition.manifest.version) in revoked:
            rejected[identity] = "skill_version_revoked"
    return skills, rejected


async def read_skill_context(
    session: AsyncSession,
    context: ToolContext,
    agent: AgentRow,
    registry: ToolRegistry,
    task_text: str | None = None,
    retained_ids: list[str] | None = None,
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
    requested: set[str] = set(retained_ids or [])
    if isinstance(requested_raw, list):
        requested.update(item for item in cast(list[Any], requested_raw) if isinstance(item, str))
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
    skills, rejected = await effective_skill_registry(
        session, context, registry, rows, run.model_metadata
    )
    snapshot = read_snapshot(run.model_metadata.get("skill_snapshot"))
    selection = resolve_skills(skills, signals, rejected=rejected)
    if set(retained_ids or []) - {item.manifest.id for item in selection.selected}:
        raise LonoraError("skill_continuation_unavailable", 409)
    snapshot_payload = write_snapshot(snapshot, selection)
    # Hold the run fence only for the metadata write, never while retrieving memory/context.
    async with context.db.sessions() as writer, writer.begin():
        locked = await require_lease(writer, context.lease, lock=True)
        locked.model_metadata = {
            **locked.model_metadata,
            "skill_selection": selection.diagnostics(),
            "skill_snapshot": snapshot_payload,
        }

    return (
        "<skill_runtime>\n"
        + selection.context()
        + "\nDiscover other relevant procedures with skills_list, then skill_view. "
        "Read only useful procedures; Skills never grant tools or financial authority "
        "or authorize installing code or dependencies." + "\n</skill_runtime>"
    )


async def refresh_skill_context(
    context: ToolContext,
    registry: ToolRegistry,
    messages: list["ModelMessage"],
    retained_ids: list[str] | None = None,
) -> list[str] | None:
    """Steering may change relevance; retain policies, history and indivisible tool exchanges."""
    import re

    async with context.db.sessions() as session:
        agent = await session.get(AgentRow, context.agent_id)
        if agent is None:
            raise LonoraError("context_identity_missing", 404)
        task_text = next((item.content for item in reversed(messages) if item.role == "user"), None)
        block = await read_skill_context(session, context, agent, registry, task_text, retained_ids)
    for message in messages:
        if message.role == "system" and "<skill_runtime>" in message.content:
            message.content = re.sub(
                r"<skill_runtime>.*?</skill_runtime>",
                lambda _: block,
                message.content,
                count=1,
                flags=re.S,
            )
            return await selected_skill_ids(context)
    return None


async def selected_skill_ids(context: ToolContext) -> list[str]:
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        active: Any = run.model_metadata.get("skill_selection", {}).get("selected_skill_ids", [])
        if not isinstance(active, list) or len(cast(list[Any], active)) > MAX_SNAPSHOT_SKILLS:
            raise LonoraError("skill_snapshot_invalid", 409)
        if any(not isinstance(item, str) for item in cast(list[Any], active)):
            raise LonoraError("skill_snapshot_invalid", 409)
        return list(cast(list[str], active))


async def assert_skill_authority(
    context: ToolContext, registry: ToolRegistry, *, active_ids: list[str] | None = None
) -> None:
    """Recheck selected pinned instructions without changing selection or pending effects.

    A Skill is not a tool grant. This boundary additionally prevents a resumed or
    multi-tool Run from continuing to use instructions their owner has withdrawn.
    No model call, dependency installation or instruction upgrade happens here.
    """
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        snapshot = read_snapshot(run.model_metadata.get("skill_snapshot"))
        selection: Any = run.model_metadata.get("skill_selection", {})
        if not isinstance(selection, dict):
            raise LonoraError("skill_snapshot_invalid", 409)
        active_raw: Any = (
            active_ids
            if active_ids is not None
            else cast(dict[str, Any], selection).get("selected_skill_ids", [])
        )
        if not isinstance(active_raw, list):
            raise LonoraError("skill_snapshot_invalid", 409)
        if len(cast(list[Any], active_raw)) > MAX_SNAPSHOT_SKILLS or any(
            not isinstance(item, str) for item in cast(list[Any], active_raw)
        ):
            raise LonoraError("skill_snapshot_invalid", 409)
        active = cast(list[str], active_raw)
        if not active:
            return
        rows = (
            await session.scalars(select(SkillRow).where(SkillRow.agent_id == context.agent_id))
        ).all()
        known_tools = {item.name for item in registry.definitions()}
        current, rejected = installed_registry([row.payload for row in rows], known_tools)
        read_only = (
            run.trigger == "subagent" or run.model_metadata.get("authority") == "observe_only"
        )
        signals = SkillSignals(
            read_only=read_only,
            available_tools=frozenset(item.name for item in registry.definitions(read_only)),
        )
        controls = await read_skill_controls(session, context.owner_id, context.agent_id)
        revoked = {(item.skill_id, item.version) for item in controls.revoked}
        failures: dict[str, str] = {}
        for identity in active:
            pinned = snapshot.get(identity)
            definition = current.definitions.get(identity)
            if pinned is None:
                failures[identity] = "skill_snapshot_unavailable"
            elif (identity, pinned.manifest.version) in revoked:
                failures[identity] = "skill_version_revoked"
            elif identity in rejected:
                failures[identity] = rejected[identity]
            elif definition is None:
                failures[identity] = "skill_snapshot_unavailable"
            elif definition.manifest.source != pinned.manifest.source:
                failures[identity] = "skill_snapshot_source_changed"
            elif reason := eligibility_reason(pinned, signals, rejected):
                failures[identity] = reason
            elif set(pinned.manifest.dependencies) - set(active):
                failures[identity] = "skill_dependency_unavailable"
        # Diagnostics are server-owned, bounded by the existing selected snapshot.
        run.model_metadata = {
            **run.model_metadata,
            "skill_authority": {
                "status": "blocked" if failures else "allowed",
                "rejected_skills": failures,
            },
        }
    if failures:
        # Raise after committing diagnostics; preserve checkpoint and operation IDs.
        raise LonoraError("skill_continuation_unavailable", 409)
