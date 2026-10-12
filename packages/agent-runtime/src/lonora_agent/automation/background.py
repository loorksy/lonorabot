from typing import Any

from lonora_contracts.runs import RunRequest
from lonora_db.client import Database
from lonora_db.runs import create_run, run_data
from lonora_db.tickets import TicketRepository


async def start_ticket(db: Database, owner_id: str, ticket_id: str) -> dict[str, Any]:
    async with db.sessions() as session, session.begin():
        ticket = await TicketRepository().get(session, owner_id, ticket_id, lock=True)
        request = RunRequest(
            agent_id=ticket.agent_id or "",
            thread_id=ticket.thread_id or "",
            trigger="tickets",
            prompt=ticket.payload.get("description", ticket.payload["title"]),
            metadata={"ticket_id": ticket.id},
        )
        run = await create_run(session, owner_id, request)
        ticket.payload = {**ticket.payload, "status": "working", "run_id": run.id}
        ticket.version += 1
        return run_data(run)
