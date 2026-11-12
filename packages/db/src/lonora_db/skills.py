from typing import Any, cast

from lonora_contracts.skills import AgentSkill
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import ResourceRow, SkillRow, SkillVersionRow
from .transactions import ResourceRepository


class SkillRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for skills, keeping every saved version."""

    row_type = SkillRow
    kind = "skills"
    payload_model = AgentSkill

    async def create(
        self,
        session: AsyncSession,
        owner_id: str,
        payload: dict[str, Any],
        *,
        agent_id: str | None = None,
        thread_id: str | None = None,
        resource_id: str | None = None,
    ) -> ResourceRow:
        row = await super().create(
            session,
            owner_id,
            payload,
            agent_id=agent_id,
            thread_id=thread_id,
            resource_id=resource_id,
        )
        record_version(session, row)
        return row

    async def update(
        self,
        session: AsyncSession,
        owner_id: str,
        resource_id: str,
        payload: dict[str, Any],
        version: int,
    ) -> ResourceRow:
        row = await super().update(session, owner_id, resource_id, payload, version)
        record_version(session, row)
        return row


def record_version(session: AsyncSession, row: ResourceRow) -> None:
    session.add(
        SkillVersionRow(
            skill_id=row.id,
            version=row.version,
            owner_id=row.owner_id,
            agent_id=row.agent_id,
            payload=dict(row.payload),
            created_at=row.updated_at,
        )
    )


async def skill_versions(
    session: AsyncSession, owner_id: str, skill: ResourceRow
) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(SkillVersionRow)
        .where(SkillVersionRow.owner_id == owner_id, SkillVersionRow.skill_id == skill.id)
        .order_by(SkillVersionRow.version.desc())
        .limit(100)
    )
    return [
        {
            "version": row.version,
            "created_at": row.created_at.isoformat(),
            "name": str(row.payload.get("name", "")),
            "description": manifest_description(row.payload),
            "enabled": bool(row.payload.get("enabled", True)),
            "current": row.version == skill.version,
        }
        for row in rows
    ]


def manifest_description(payload: dict[str, Any]) -> str:
    manifest = cast(dict[str, Any], payload.get("manifest") or {})
    return str(manifest.get("description", ""))


async def version_payload(
    session: AsyncSession, owner_id: str, skill_id: str, version: int
) -> dict[str, Any]:
    row = await session.get(SkillVersionRow, (skill_id, version))
    if row is None or row.owner_id != owner_id:
        raise LonoraError("skill_version_not_found", 404)
    return dict(row.payload)
