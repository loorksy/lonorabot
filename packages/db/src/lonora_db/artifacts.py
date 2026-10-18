from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import ArtifactRow, ResourceRow
from .transactions import ResourceRepository, owned_thread


class ArtifactRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for artifacts."""

    row_type = ArtifactRow
    kind = "artifacts"

    async def list(
        self,
        session: AsyncSession,
        owner_id: str,
        agent_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[ResourceRow]:
        query = select(ArtifactRow).where(
            ArtifactRow.owner_id == owner_id,
            or_(
                ArtifactRow.state["internal_tool_result"].as_boolean().is_(None),
                ArtifactRow.state["internal_tool_result"].as_boolean().is_(False),
            ),
        )
        if agent_id:
            query = query.where(ArtifactRow.agent_id == agent_id)
        if thread_id:
            await owned_thread(session, owner_id, thread_id)
            query = query.where(ArtifactRow.thread_id == thread_id)
        return list(await session.scalars(query.order_by(ArtifactRow.created_at.desc()).limit(200)))
