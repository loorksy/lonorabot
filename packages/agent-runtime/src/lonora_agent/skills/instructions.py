"""Instruction-only Skills an Agent saves in one call, with versions it can restore.

Every save writes the Skill resource's next version (``SkillVersionRow``), like an owner
edit. Restoring version N saves that version's instructions as the next version, under
a new semantic version, so a pinned run snapshot never meets two texts with one number.
Packages from the workspace or GitHub keep their own lifecycle (skill_package_control).
"""

from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.skills import AgentSkill
from lonora_core.user_error import LonoraError
from lonora_db.schema import EffectReceiptRow, SkillRow
from lonora_db.skill_controls import read_skill_controls
from lonora_db.skills import SkillRepository, record_version, skill_versions, version_payload
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry

from ..workspace_access import scoped_run
from .lifecycle import owned_skill, validate_graph
from .registry import built_in_skills


def next_semver(payload: dict[str, Any] | None) -> str:
    """The next patch version; a first save, or a skill saved without one, is 1.0.0."""
    manifest: dict[str, Any] = (payload or {}).get("manifest") or {}
    if "version" not in manifest:
        return "1.0.0"
    major, minor, patch = (int(part) for part in manifest["version"].split("."))
    return f"{major}.{minor}.{patch + 1}"


def instruction_payload(
    skill_id: str, title: str, description: str, content: str, version: str
) -> dict[str, Any]:
    return AgentSkill.model_validate(
        {
            "name": skill_id,
            "content": content,
            "enabled": True,
            "manifest": {
                "id": skill_id,
                "version": version,
                "title": title,
                "description": description,
                "source": "installed",
                "activation": {"mode": "explicit"},
            },
        }
    ).model_dump(mode="json")


def summary(row: SkillRow, status: str, **extra: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = row.payload.get("manifest") or {}
    return {
        "skill_id": row.payload["name"],
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
            skill_id,
            arguments["title"],
            arguments["description"],
            arguments["content"],
            next_semver(row.payload if row else None),
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
        row = await owned_skill(session, context, skill_id)
        if row is None:
            raise LonoraError("skill_not_found", 404)
        if row.version != arguments["expected_version"]:
            raise LonoraError("version_conflict", 409)
        editable(row)
        target = await version_payload(session, context.owner_id, row.id, arguments["version"])
        manifest: dict[str, Any] = target.get("manifest") or {}
        controls = await read_skill_controls(session, context.owner_id, context.agent_id)
        if any(
            item.skill_id == skill_id and item.version == manifest.get("version")
            for item in controls.revoked
        ):
            raise LonoraError("skill_version_revoked", 409)
        payload = AgentSkill.model_validate(
            {
                **target,
                "manifest": {**manifest, "version": next_semver(row.payload)} if manifest else None,
            }
        ).model_dump(mode="json")
        await validate_graph(session, context, registry, payload, row.id)
        row.payload, row.version, row.updated_at = payload, row.version + 1, utcnow()
        record_version(session, row)
        result = summary(row, "restored", restored_version=arguments["version"])
        session.add(EffectReceiptRow(key=context.effect_key, result=result))
        return result
