"""Instruction-only Skills an Agent saves in one call, with versions it can restore.

Every save writes the Skill resource's next version (``SkillVersionRow``), like an owner
edit. Restoring version N saves that version's instructions as the next version, under a new
semantic version above every number the Skill ever had, so one number never names two
texts; the text of a version the owner revoked cannot be saved or restored.
Packages from the workspace or GitHub keep their own lifecycle (skill_package_control).
"""

from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.skills import AgentSkill
from lonora_core.user_error import LonoraError
from lonora_db.schema import EffectReceiptRow, SkillRow, SkillVersionRow
from lonora_db.skill_controls import read_skill_controls
from lonora_db.skills import (
    SkillRepository,
    manifest_description,
    record_version,
    skill_versions,
    version_payload,
)
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..run_scope import scoped_run
from .lifecycle import owned_skill, validate_graph
from .registry import built_in_skills


def semver(value: Any) -> tuple[int, int, int] | None:
    parts = str(value).split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


async def history_rows(
    session: AsyncSession, context: ToolContext, skill_id: str
) -> list[SkillVersionRow]:
    """Every saved version of this agent's Skill named ``skill_id``, newest first, the
    versions of a deleted Skill included."""
    return list(
        await session.scalars(
            select(SkillVersionRow)
            .where(
                SkillVersionRow.owner_id == context.owner_id,
                SkillVersionRow.agent_id == context.agent_id,
                SkillVersionRow.payload["name"].as_string() == skill_id,
            )
            .order_by(SkillVersionRow.created_at.desc(), SkillVersionRow.version.desc())
        )
    )


def deleted_versions(saved: list[SkillVersionRow]) -> list[SkillVersionRow]:
    """The versions of the most recently saved resource of a Skill that no longer exists."""
    return [item for item in saved if saved and item.skill_id == saved[0].skill_id]


async def guard_versions(
    session: AsyncSession, context: ToolContext, skill_id: str, content: str
) -> str:
    """The next semantic version, above every version this Skill ever had or the owner
    revoked, so one number never names two texts. Text of a revoked version is refused."""
    controls = await read_skill_controls(session, context.owner_id, context.agent_id)
    revoked = {item.version for item in controls.revoked if item.skill_id == skill_id}
    saved = await history_rows(session, context, skill_id)
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
        if row is None:
            # A deleted instruction Skill of this name comes back under its own id, so its
            # earlier versions stay in its history (5.5.5).
            deleted = deleted_versions(await history_rows(session, context, skill_id))
            if deleted and not deleted[0].package:
                row = await revived(session, context, skill_id, expected)
        if row is not None:
            editable(row)
        payload = instruction_payload(
            row.payload if row else None,
            skill_id,
            arguments["title"],
            arguments["description"],
            arguments["content"],
            await guard_versions(session, context, skill_id, arguments["content"]),
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


async def skill_history(context: ToolContext, skill_id: str) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        row = await owned_skill(session, context, skill_id)
        if row is not None:
            versions = await skill_versions(session, context.owner_id, row)
            return {"skill_id": skill_id, "resource_version": row.version, "versions": versions}
        deleted = deleted_versions(await history_rows(session, context, skill_id))
        if not deleted:
            raise LonoraError("skill_not_found", 404)
        # A deleted Skill: its versions stay, and skill_restore with expected_version 0
        # brings one back.
        return {
            "skill_id": skill_id,
            "resource_version": 0,
            "deleted": True,
            "versions": [
                {
                    "version": item.version,
                    "created_at": item.created_at.isoformat(),
                    "name": str(item.payload.get("name", "")),
                    "description": manifest_description(item.payload),
                    "enabled": bool(item.payload.get("enabled", True)),
                    "current": False,
                }
                for item in deleted
            ],
        }


async def restore_skill(
    context: ToolContext, registry: ToolRegistry, arguments: dict[str, Any]
) -> dict[str, Any]:
    skill_id = arguments["skill_id"]
    async with context.db.sessions() as session, session.begin():
        await scoped_run(session, context, mutate=True)
        if receipt := await session.get(EffectReceiptRow, context.effect_key):
            return receipt.result
        row = await owned_skill(session, context, skill_id)
        if row is None:
            row = await revived(session, context, skill_id, arguments["expected_version"])
        elif row.version != arguments["expected_version"]:
            raise LonoraError("version_conflict", 409)
        editable(row)
        target = await version_payload(session, context.owner_id, row.id, arguments["version"])
        manifest: dict[str, Any] = target.get("manifest") or {}
        version = await guard_versions(session, context, skill_id, target["content"])
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


async def revived(
    session: AsyncSession, context: ToolContext, skill_id: str, expected: int
) -> SkillRow:
    """A deleted Skill comes back under its own resource id, at its last saved version,
    with the on/off state it had; the restore then saves the chosen version after it."""
    deleted = deleted_versions(await history_rows(session, context, skill_id))
    if not deleted:
        raise LonoraError("skill_not_found", 404)
    if expected != 0:
        raise LonoraError("version_conflict", 409)
    last = deleted[0]
    if last.package:
        # A removed package comes back only through its own lifecycle, with its
        # source hashes and validation (skill_package_import or skill_package_create).
        raise LonoraError("skill_package_lifecycle_required", 409)
    row = SkillRow(
        id=last.skill_id,
        owner_id=context.owner_id,
        agent_id=context.agent_id,
        payload=dict(last.payload),
        version=last.version,
    )
    session.add(row)
    await session.flush()
    return row
