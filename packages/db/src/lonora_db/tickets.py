from typing import Any

from lonora_contracts.domain import Ticket
from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import TicketRow
from .transactions import ResourceRepository


class TicketRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for tickets."""

    row_type = TicketRow
    kind = "tickets"
    payload_model = Ticket

    async def update(
        self,
        session: AsyncSession,
        owner_id: str,
        resource_id: str,
        payload: dict[str, Any],
        version: int,
    ) -> TicketRow:
        row = await self.get(session, owner_id, resource_id, lock=True)
        if row.state.get("task"):
            # Task lifecycle and plan live in one durable state. The generic
            # board editor must never change them independently of task control.
            raise LonoraError("task_use_control", 409)
        updated = await super().update(session, owner_id, resource_id, payload, version)
        assert isinstance(updated, TicketRow)
        return updated
