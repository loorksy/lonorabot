from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import PeerMessageRow, ResourceRow, RunRow
from .transactions import ResourceRepository, owned_thread


class PeerMessageRepository(ResourceRepository):
    """Owner-scoped exchanges visible in both their sender and recipient conversations."""

    row_type = PeerMessageRow
    kind = "peer_messages"

    async def list(
        self,
        session: AsyncSession,
        owner_id: str,
        agent_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[ResourceRow]:
        query = select(PeerMessageRow).where(PeerMessageRow.owner_id == owner_id)
        if agent_id:
            query = query.where(
                or_(
                    PeerMessageRow.agent_id == agent_id,
                    PeerMessageRow.payload["source_agent_id"].as_string() == agent_id,
                )
            )
        if thread_id:
            await owned_thread(session, owner_id, thread_id)
            legacy_source = exists(
                select(RunRow.id).where(
                    RunRow.id == PeerMessageRow.payload["requester_run_id"].as_string(),
                    RunRow.thread_id == thread_id,
                )
            )
            query = query.where(
                or_(
                    PeerMessageRow.thread_id == thread_id,
                    PeerMessageRow.payload["source_thread_id"].as_string() == thread_id,
                    legacy_source,
                )
            )
        return list(
            (
                await session.scalars(query.order_by(PeerMessageRow.created_at.desc()).limit(200))
            ).all()
        )
