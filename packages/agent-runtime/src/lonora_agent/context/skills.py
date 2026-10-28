from collections.abc import Sequence
from html import escape
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow, AnalyticalWorkspaceRow, CloudChartRow, MessageRow, SkillRow
from lonora_db.skill_controls import read_skill_controls
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..skills.document import skill_document
from ..skills.packages import PackageVersion, read_state, validate_package_files, validation_image
from ..skills.registry import (
    SkillDefinition,
    SkillRegistry,
    built_in_skills,
    installed_registry,
    legacy_skill_id,
)
from ..skills.resolver import SkillSignals, eligibility_reason, resolve_skills
from ..skills.snapshot import MAX_SNAPSHOT_SKILLS, apply_snapshot, read_snapshot, write_snapshot


def package_entry(row: SkillRow, definition: SkillDefinition) -> PackageVersion:
    entry = next(
        (
            item
            for item in read_state(row.state).versions
            if item.payload.manifest == definition.manifest
            and skill_document(item.payload.content, item.payload.name, required=True)[1]
            == definition.content
        ),
        None,
    )
    if entry is None:
        raise LonoraError("skill_package_content_changed", 409)
    return entry


def pin_package_image(
    metadata: dict[str, Any], rows: Sequence[SkillRow], selected: Sequence[SkillDefinition]
) -> dict[str, Any]:
    """Pin the admitted immutable profile; later execution cannot silently switch it."""
    selected_by_id = {item.manifest.id: item for item in selected}
    images: set[str] = set()
    for row in rows:
        definition = selected_by_id.get(row.payload.get("name", ""))
        if definition is None or "package" not in row.state:
            continue
        image = validation_image(package_entry(row, definition))
        if image is not None:
            images.add(image)
    if not images:
        return metadata
    if len(images) != 1:
        raise LonoraError("skill_package_validation_required", 409)
    image = next(iter(images))
    if metadata.get("skill_execution_image") not in {None, image}:
        raise LonoraError("workspace_profile_changed", 409)
    return {**metadata, "skill_execution_image": image}


async def effective_skill_registry(
    session: AsyncSession,
    context: ToolContext,
    registry: ToolRegistry,
    rows: Sequence[SkillRow],
    metadata: dict[str, Any],
) -> tuple[SkillRegistry, dict[str, str]]:
    """One effective pinned catalog for automatic selection and progressive reads."""
    known_tools = registry.names()
    skills, rejected = installed_registry([row.payload for row in rows], known_tools)
    skills = apply_snapshot(
        skills, rejected, read_snapshot(metadata.get("skill_snapshot")), known_tools
    )
    current_image: str | None = None
    profile_failure: str | None = None
    workspace_files: dict[str, bytes] | None = None
    for row in rows:
        identity = row.payload.get("name", "")
        definition = skills.definitions.get(identity)
        if definition is None or identity in rejected or "package" not in row.state:
            continue
        try:
            entry = package_entry(row, definition)
            image = validation_image(entry)
            if workspace_files is None:
                from ..workspace import read_snapshot as read_workspace_snapshot

                workspace = await session.get(AnalyticalWorkspaceRow, context.agent_id)
                if workspace is None or workspace.active_operation_id:
                    raise LonoraError("skill_package_source_changed", 409)
                workspace_files = read_workspace_snapshot(workspace.snapshot)
            validate_package_files(entry, workspace_files)
            if image is not None:
                if current_image is None and profile_failure is None:
                    try:
                        if context.workspace_access is None:
                            raise LonoraError("workspace_runtime_unavailable", 409)
                        current_image = await context.workspace_access.profile(
                            context.for_call(context.call_id or "skill-profile")
                        )
                    except LonoraError as error:
                        profile_failure = error.code
                if profile_failure is not None:
                    raise LonoraError(profile_failure, 409)
                if image != current_image:
                    raise LonoraError("skill_package_validation_required", 409)
                if metadata.get("skill_execution_image") not in {None, image}:
                    raise LonoraError("workspace_profile_changed", 409)
        except LonoraError as error:
            rejected[identity] = error.code
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
    available = registry.names(read_only)
    signals = SkillSignals(
        # Description-first discovery; explicit requests, durable triggers and
        # already viewed pins still apply without routing by owner keywords.
        intents=frozenset(),
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
            **pin_package_image(locked.model_metadata, rows, selection.selected),
            "skill_selection": selection.diagnostics(),
            "skill_snapshot": snapshot_payload,
        }

    return (
        "<skill_runtime>\n"
        + "# Skills\nDescriptions are discovery hints. Read a suitable SKILL.md with skill_view before applying it.\n"
        + "\n".join(
            "- " + escape(identity) + " — " + escape(definition.manifest.description)
            for identity, definition in sorted(skills.definitions.items())
            if eligibility_reason(definition, signals, rejected) is None
        )[:6000]
        + "\n# Active Skills\n"
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
        current, rejected = await effective_skill_registry(
            session, context, registry, rows, run.model_metadata
        )
        read_only = (
            run.trigger == "subagent" or run.model_metadata.get("authority") == "observe_only"
        )
        signals = SkillSignals(
            read_only=read_only,
            available_tools=frozenset(registry.names(read_only)),
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
