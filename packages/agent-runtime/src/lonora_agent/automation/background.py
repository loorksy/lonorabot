from typing import Any

from lonora_contracts.domain import ThreadCreate
from lonora_contracts.runs import Lease, RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.runs import create_run, require_lease, run_data
from lonora_db.schema import EffectReceiptRow
from lonora_db.threads import create_thread
from lonora_db.tickets import TicketRepository


async def start_ticket(
    db: Database,
    owner_id: str,
    ticket_id: str,
    *,
    lease: Lease | None = None,
    effect_key: str | None = None,
) -> dict[str, Any]:
    async with db.sessions() as session, session.begin():
        if lease:
            await require_lease(session, lease, lock=True)
        if effect_key:
            existing = await session.get(EffectReceiptRow, effect_key)
            if existing:
                return existing.result
        ticket = await TicketRepository().get(session, owner_id, ticket_id, lock=True)
        if not ticket.agent_id:
            raise LonoraError("ticket_agent_required", 409)
        if ticket.payload.get("status") == "working":
            raise LonoraError("ticket_already_running", 409)
        if not ticket.thread_id:
            thread = await create_thread(
                session,
                owner_id,
                ThreadCreate(agent_id=ticket.agent_id, title=ticket.payload["title"]),
            )
            ticket.thread_id = thread.id
        request = RunRequest(
            agent_id=ticket.agent_id,
            thread_id=ticket.thread_id,
            trigger="tickets",
            prompt=ticket.payload["title"] + "\n" + ticket.payload.get("description", ""),
            metadata={"ticket_id": ticket.id},
        )
        run = await create_run(session, owner_id, request)
        ticket.payload = {**ticket.payload, "status": "working", "run_id": run.id}
        ticket.version += 1
        result = run_data(run)
        if effect_key:
            session.add(EffectReceiptRow(key=effect_key, result=result))
        return result
