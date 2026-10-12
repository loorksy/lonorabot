from typing import Any

from fastapi import Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import ThreadCreate
from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.runs import create_run, run_data
from lonora_db.threads import create_thread
from lonora_db.tickets import TicketRepository

from ..middleware.auth import require_owner, runtime
from . import resource_router

router = resource_router("/tickets", TicketRepository())


@router.post("/{ticket_id}/start", status_code=202)
async def start(
    request: Request, ticket_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        ticket = await TicketRepository().get(session, owner.id, ticket_id, lock=True)
        if not ticket.agent_id:
            raise LonoraError("ticket_agent_required", 409)
        if ticket.payload.get("status") == "working":
            raise LonoraError("ticket_already_running", 409)
        thread = await create_thread(
            session, owner.id, ThreadCreate(agent_id=ticket.agent_id, title=ticket.payload["title"])
        )
        run = await create_run(
            session,
            owner.id,
            RunRequest(
                thread_id=thread.id,
                agent_id=ticket.agent_id,
                trigger="tickets",
                prompt=ticket.payload["title"] + "\n" + ticket.payload.get("description", ""),
                metadata={"ticket_id": ticket.id},
            ),
        )
        ticket.thread_id = thread.id
        ticket.payload = {**ticket.payload, "status": "working", "run_id": run.id}
        ticket.version += 1
        return run_data(run)
