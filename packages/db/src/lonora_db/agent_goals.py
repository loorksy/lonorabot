"""Light goals and knowledge links: owner resources that belong to exactly one agent."""

from typing import Any

from lonora_contracts.agent_goals import AgentGoal
from lonora_contracts.knowledge import KnowledgeLink
from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentGoalRow, KnowledgeLinkRow, ResourceRow
from .transactions import ResourceRepository


class AgentBoundRepository(ResourceRepository):
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
        if not agent_id or thread_id:
            raise LonoraError(self.kind + "_agent_required", 422)
        return await super().create(
            session, owner_id, payload, agent_id=agent_id, resource_id=resource_id
        )


class AgentGoalRepository(AgentBoundRepository):
    """A light goal schedules nothing and grants nothing (W15-9): it is only a note."""

    row_type = AgentGoalRow
    kind = "agent_goals"
    payload_model = AgentGoal


class KnowledgeLinkRepository(AgentBoundRepository):
    row_type = KnowledgeLinkRow
    kind = "knowledge_links"
    payload_model = KnowledgeLink
