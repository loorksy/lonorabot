"""Instruction-only Skills an Agent saves in one call, with versions it can restore.

Every save writes the Skill resource's next version (``SkillVersionRow``), like an owner
edit. Restoring version N saves that version's instructions as the next version, under a new
semantic version above every number the Skill ever had, so one number never names two
texts; the text of a version the owner revoked cannot be saved or restored.
Packages from the workspace or GitHub keep their own lifecycle (skill_package_control).
"""

from dataclasses import replace
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.skills import AgentSkill
from lonora_core.user_error import LonoraError
from lonora_db.lead import is_lead
from lonora_db.schema import EffectReceiptRow, SkillRow, SkillVersionRow
from lonora_db.skill_controls import read_skill_controls
from lonora_db.skills import SkillRepository, record_version, skill_versions, version_payload
from lonora_db.transactions import owned_agent
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..workspace_access import scoped_run
from .lifecycle import owned_skill, validate_graph
from .registry import built_in_skills


def semver(value: Any) -> tuple[int, int, int] | None:
    parts = str(value).split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


async def history_rows(session: AsyncSession, row: SkillRow | None) -> list[SkillVersionRow]:
    if row is None:
        return []
    return list(
        await session.scalars(select(SkillVersionRow).where(SkillVersionRow.skill_id == row.id))
    )


async def guard_versions(
    session: AsyncSession, context: ToolContext, skill_id: str, row: SkillRow | None, content: str
) -> str:
    """The next semantic version, above every version this Skill ever had or the owner
    revoked, so one number never names two texts. Text of a revoked version is refused."""
    controls = await read_skill_controls(session, context.owner_id, context.agent_id)
    revoked = {item.version for item in controls.revoked if item.skill_id == skill_id}
    saved = await history_rows(session, row)
    labels: list[Any] = list(revoked)
    for item in saved:
        manifest: dict[str, Any] = item.payload.get("manifest") or {}
        labels.append(manifest.get("version"))
        if manifest.get("version") in revoked and item.payload.get("content") == content:
            raise LonoraError("skill_version_revoked", 409)
    numbers = [number for value in labels if (number := semver(value)) is not None]
    if not numbers:
        return "1.0.0"
    major, minor, patch = max(numbers)
    return f"{major}.{minor}.{patch + 1}"


def instruction_payload(
    base: dict[str, Any] | None,
    skill_id: str,
    title: str,
    description: str,
    content: str,
    version: str,
) -> dict[str, Any]:
    """The owner's settings of an existing Skill (enabled, activation, tools, budget) stay;
    the text, title and description are the Agent's, labelled as Agent-authored."""
    manifest: dict[str, Any] = dict((base or {}).get("manifest") or {})
    manifest.setdefault("activation", {"mode": "explicit"})
    return AgentSkill.model_validate(
        {
            "name": skill_id,
            "content": content,
            "enabled": (base or {}).get("enabled", True),
            "manifest": {
                **manifest,
                "id": skill_id,
                "version": version,
                "title": title,
                "description": description,
                "source": "installed",
            },
        }
    ).model_dump(mode="json")


def summary(row: SkillRow, status: str, **extra: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = row.payload.get("manifest") or {}
    return {
        "skill_id": row.payload["name"],
        "resource_id": row.id,
        "resource_version": row.version,
        "version": manifest.get("version"),
        "enabled": row.payload.get("enabled", True),
        "status": status,
        **extra,
    }


def editable(row: SkillRow) -> None:
    if "package" in row.state:
        raise LonoraError("skill_package_lifecycle_required", 409)


async def save_skill(
    context: ToolContext, registry: ToolRegistry, arguments: dict[str, Any]
) -> dict[str, Any]:
    skill_id = arguments["skill_id"]
    if skill_id in built_in_skills():
        raise LonoraError("skill_builtin_override_denied", 409)
    async with context.db.sessions() as session, session.begin():
        await scoped_run(session, context, mutate=True)
        if receipt := await session.get(EffectReceiptRow, context.effect_key):
            return receipt.result
        row = await owned_skill(session, context, skill_id)
        expected = arguments["expected_version"]
        if (row.version if row else 0) != expected:
            raise LonoraError("version_conflict", 409)
        if row is not None:
            editable(row)
        payload = instruction_payload(
            row.payload if row else None,
            skill_id,
            arguments["title"],
            arguments["description"],
            arguments["content"],
            await guard_versions(session, context, skill_id, row, arguments["content"]),
        )
        await validate_graph(session, context, registry, payload, row.id if row else None)
        if row is None:
            created = await SkillRepository().create(
                session,
                context.owner_id,
                payload,
                agent_id=context.agent_id,
                resource_id=context.resource_id,
            )
            assert isinstance(created, SkillRow)
            row, status = created, "created"
        else:
            row.payload, row.version, row.updated_at = payload, row.version + 1, utcnow()
            record_version(session, row)
            status = "updated"
        result = summary(row, status)
        session.add(EffectReceiptRow(key=context.effect_key, result=result))
        return result


async def as_target(
    session: AsyncSession, context: ToolContext, agent_id: str | None
) -> ToolContext:
    """The caller's own Skills, or, for Lonora only, a team agent's (3.1.2, 5.5.5)."""
    if agent_id is None or agent_id == context.agent_id:
        return context
    if not await is_lead(session, context.owner_id, context.agent_id):
        raise LonoraError("method_lead_only", 403)
    await owned_agent(session, context.owner_id, agent_id)
    return replace(context, agent_id=agent_id)


async def skill_history(
    context: ToolContext, skill_id: str, agent_id: str | None = None
) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        context = await as_target(session, context, agent_id)
        row = await owned_skill(session, context, skill_id)
        if row is None:
            raise LonoraError("skill_not_found", 404)
        versions = await skill_versions(session, context.owner_id, row)
        return {"skill_id": skill_id, "resource_version": row.version, "versions": versions}


async def restore_skill(
    context: ToolContext, registry: ToolRegistry, arguments: dict[str, Any]
) -> dict[str, Any]:
    skill_id = arguments["skill_id"]
    async with context.db.sessions() as session, session.begin():
        await scoped_run(session, context, mutate=True)
        if receipt := await session.get(EffectReceiptRow, context.effect_key):
            return receipt.result
        # From here on, the Skill's own agent: its catalog, revocations and graph.
        context = await as_target(session, context, arguments.get("agent_id"))
        row = await owned_skill(session, context, skill_id)
        if row is None:
            raise LonoraError("skill_not_found", 404)
        if row.version != arguments["expected_version"]:
            raise LonoraError("version_conflict", 409)
        editable(row)
        target = await version_payload(session, context.owner_id, row.id, arguments["version"])
        manifest: dict[str, Any] = target.get("manifest") or {}
        version = await guard_versions(session, context, skill_id, row, target["content"])
        # The restored text keeps the Skill's current on/off state: a restore never
        # switches on a Skill the owner switched off.
        payload = AgentSkill.model_validate(
            {
                **target,
                "enabled": row.payload.get("enabled", True),
                "manifest": {**manifest, "version": version} if manifest else None,
            }
        ).model_dump(mode="json")
        await validate_graph(session, context, registry, payload, row.id)
        row.payload, row.version, row.updated_at = payload, row.version + 1, utcnow()
        record_version(session, row)
        result = summary(row, "restored", restored_version=arguments["version"])
        session.add(EffectReceiptRow(key=context.effect_key, result=result))
        return result
