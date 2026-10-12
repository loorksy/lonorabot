from typing import Any

from fastapi import Depends, Request
from lonora_agent.automation.background import start_ticket
from lonora_auth.identity import OwnerIdentity
from lonora_db.tickets import TicketRepository

from ..middleware.auth import require_owner, runtime
from . import resource_router

router = resource_router("/tickets", TicketRepository())


@router.post("/{ticket_id}/start", status_code=202)
async def start(
    request: Request, ticket_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    return await start_ticket(runtime(request).db, owner.id, ticket_id)
