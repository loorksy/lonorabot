from typing import Any

from lonora_contracts.domain import ThreadCreate
from lonora_contracts.market_watch import Watch
from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import IntegrationRow, MarketWatchRow
from .threads import create_thread
from .transactions import ResourceRepository, ResourceRow


class MarketWatchRepository(ResourceRepository):
    row_type = MarketWatchRow
    kind = "market_watches"
    payload_model = Watch

    async def validate_references(
        self, session: AsyncSession, owner_id: str, payload: dict[str, Any]
    ) -> None:
        await super().validate_references(session, owner_id, payload)
        if payload.get("integration_id"):
            source = await session.get(IntegrationRow, payload["integration_id"])
            if (
                source is None
                or source.owner_id != owner_id
                or source.payload.get("type") != "economic_calendar"
            ):
                raise LonoraError("calendar_integration_not_found", 404)

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
        if not agent_id:
            raise LonoraError("watch_agent_required", 422)
        if not thread_id:
            thread = await create_thread(
                session,
                owner_id,
                ThreadCreate(
                    agent_id=agent_id,
                    title=str(payload.get("symbol") or payload.get("kind") or "Watch"),
                ),
            )
            thread_id = thread.id
        return await super().create(
            session,
            owner_id,
            payload,
            agent_id=agent_id,
            thread_id=thread_id,
            resource_id=resource_id,
        )
