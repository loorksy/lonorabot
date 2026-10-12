from lonora_contracts.runs import RunRequest
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.messages import message_data
from lonora_db.runs import create_run
from lonora_db.schema import EffectReceiptRow, MessageRow, RunRow, SteeringRow, ThreadRow, TicketRow


async def return_outcome(db: Database, run_id: str) -> None:
    async with db.sessions() as session, session.begin():
        child = await session.get(RunRow, run_id, with_for_update=True)
        if child is None or child.status not in {"completed", "failed", "cancelled"}:
            return
        receipt = "outcome:" + run_id
        if await session.get(EffectReceiptRow, receipt):
            return
        if child.trigger == "tickets":
            ticket = await session.get(
                TicketRow, child.model_metadata.get("ticket_id", ""), with_for_update=True
            )
            if ticket:
                ticket.payload = {
                    **ticket.payload,
                    "status": "done" if child.status == "completed" else "failed",
                }
                ticket.state = {**ticket.state, "result": child.result}
                ticket.version += 1
        if child.parent_run_id:
            parent = await session.get(RunRow, child.parent_run_id, with_for_update=True)
            if parent:
                thread = await session.get(ThreadRow, parent.thread_id, with_for_update=True)
                if thread:
                    outcome = (
                        "<peer_outcome run_id='"
                        + child.id
                        + "'>\n"
                        + (child.result or child.error_code or child.status)
                        + "\n</peer_outcome>"
                    )
                    message = MessageRow(
                        thread_id=thread.id,
                        agent_id=child.agent_id,
                        role="assistant",
                        seq=thread.next_seq,
                        content=outcome,
                    )
                    thread.next_seq += 1
                    session.add(message)
                    await session.flush()
                    emit(
                        session,
                        thread.owner_id,
                        "message.created",
                        thread_id=thread.id,
                        agent_id=child.agent_id,
                        payload=message_data(message),
                    )
                    if parent.status in {"running", "leased", "waiting_input"}:
                        session.add(SteeringRow(run_id=parent.id, message_id=message.id))
                        if parent.status == "waiting_input":
                            parent.status = "queued"
                    elif parent.status == "completed":
                        await create_run(
                            session,
                            thread.owner_id,
                            RunRequest(
                                thread_id=thread.id,
                                agent_id=parent.agent_id,
                                trigger="follow_up",
                                prompt="Use the returned peer outcome to complete the owner's request.",
                            ),
                        )
        session.add(EffectReceiptRow(key=receipt, result={"returned": True}))
