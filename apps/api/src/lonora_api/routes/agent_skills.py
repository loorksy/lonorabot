"""Validate the complete installed graph before committing owner skill changes."""

from typing import Any

from lonora_agent.skills.registry import installed_registry
from lonora_contracts.skills import AgentSkill
from lonora_core.user_error import LonoraError
from lonora_db.schema import ResourceRow, SkillRow
from lonora_db.skills import SkillRepository
from lonora_db.transactions import owned_agent
from lonora_tools.loader import load_tools
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import resource_router


class ValidatedSkillRepository(SkillRepository):
    async def validate_graph(
        self,
        session: AsyncSession,
        owner_id: str,
        agent_id: str | None,
        payload: dict[str, Any] | None,
        exclude_id: str | None = None,
    ) -> None:
        if agent_id:
            await owned_agent(session, owner_id, agent_id, lock=True)
        rows = list(
            await session.scalars(
                select(SkillRow).where(
                    SkillRow.owner_id == owner_id,
                    SkillRow.agent_id == agent_id,
                )
            )
        )
        values = [row.payload for row in rows if row.id != exclude_id]
        if payload is not None:
            validated = AgentSkill.model_validate(payload)
            values.append(validated.model_dump(mode="json"))
        try:
            _, rejected = installed_registry(
                values, {tool.name for tool in load_tools().definitions()}
            )
        except LonoraError as error:
            raise LonoraError(error.code, 409) from None
        if payload is not None:
            name = str(payload.get("name", ""))
            reason = rejected.get(name) or rejected.get(name + "@installed")
            if reason and reason not in {"skill_disabled"}:
                raise LonoraError(reason, 422)

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
        await self.validate_graph(session, owner_id, agent_id, payload)
        return await super().create(
            session,
            owner_id,
            payload,
            agent_id=agent_id,
            thread_id=thread_id,
            resource_id=resource_id,
        )

    async def update(
        self,
        session: AsyncSession,
        owner_id: str,
        resource_id: str,
        payload: dict[str, Any],
        version: int,
    ) -> ResourceRow:
        row = await self.get(session, owner_id, resource_id)
        await self.validate_graph(session, owner_id, row.agent_id, payload, resource_id)
        return await super().update(session, owner_id, resource_id, payload, version)

    async def delete(self, session: AsyncSession, owner_id: str, resource_id: str) -> None:
        row = await self.get(session, owner_id, resource_id)
        await self.validate_graph(session, owner_id, row.agent_id, None, resource_id)
        await super().delete(session, owner_id, resource_id)


router = resource_router("/skills", ValidatedSkillRepository())
