from typing import Any, cast

from lonora_contracts.domain import utcnow
from lonora_contracts.runs import RunRequest
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.messages import message_data
from lonora_db.runs import create_run
from lonora_db.schema import (
    EffectReceiptRow,
    MessageRow,
    PeerMessageRow,
    RunRow,
    SteeringRow,
    ThreadRow,
    TicketRow,
)
from sqlalchemy import String, exists, literal, or_, select
from sqlalchemy import cast as sql_cast


def outcome_receipt(run_id: str, fence: int) -> str:
    return f"outcome:{run_id}:{fence}"


async def return_outcome(db: Database, run_id: str) -> None:
    async with db.sessions() as session, session.begin():
        child = await session.get(RunRow, run_id)
        if child is None or child.status not in {"completed", "failed", "cancelled"}:
            return
        parent = await session.get(RunRow, child.parent_run_id) if child.parent_run_id else None
        thread = (
            await session.get(
                ThreadRow, parent.thread_id, with_for_update=True, populate_existing=True
            )
            if parent
            else None
        )
        # Parent message admission and cancellation lock its thread before its run.
        if parent:
            parent = await session.get(
                RunRow, parent.id, with_for_update=True, populate_existing=True
            )
        child = await session.get(RunRow, run_id, with_for_update=True, populate_existing=True)
        if child is None or child.status not in {"completed", "failed", "cancelled"}:
            return
        receipt = outcome_receipt(run_id, child.lease_fence)
        if await session.get(EffectReceiptRow, receipt):
            return
        legacy = await session.get(EffectReceiptRow, "outcome:" + run_id)
        if legacy and "fence" not in legacy.result:
            # Already returned by older releases. Preserve that receipt, then fence later retries.
            legacy.result = {**legacy.result, "fence": child.lease_fence}
            session.add(EffectReceiptRow(key=receipt, result={"returned": True, "legacy": True}))
            return
        if child.trigger == "tickets":
            ticket = await session.get(
                TicketRow, child.model_metadata.get("ticket_id", ""), with_for_update=True
            )
            if ticket and ticket.agent_id == child.agent_id and ticket.thread_id == child.thread_id:
                ticket.payload = {
                    **ticket.payload,
                    "status": "done" if child.status == "completed" else "failed",
                }
                ticket.state = {**ticket.state, "result": child.result}
                ticket.version += 1
                if ticket.state.get("task"):
                    from lonora_contracts.tasks import TaskState
                    from lonora_db.tasks import save_task

                    task = TaskState.model_validate(ticket.state["task"])
                    task.status = (
                        "completed"
                        if child.status == "completed"
                        else "cancelled"
                        if child.status == "cancelled"
                        else "failed"
                    )
                    task.phase = task.status
                    save_task(session, ticket, task)
                    origin = await session.get(
                        ThreadRow, task.origin_thread_id, with_for_update=True
                    )
                    if (
                        origin
                        and origin.owner_id == ticket.owner_id
                        and origin.agent_id == child.agent_id
                        and child.result
                    ):
                        final = MessageRow(
                            thread_id=origin.id,
                            agent_id=child.agent_id,
                            role="assistant",
                            seq=origin.next_seq,
                            content=child.result,
                        )
                        origin.next_seq += 1
                        session.add(final)
                        await session.flush()
                        emit(
                            session,
                            ticket.owner_id,
                            "message.created",
                            thread_id=origin.id,
                            agent_id=child.agent_id,
                            run_id=child.id,
                            payload=message_data(final),
                        )
        returned_message: MessageRow | None = None
        if parent and thread:
            outcome = f"<peer_outcome run_id='{child.id}' status='{child.status}'>\n{child.result or child.error_code or child.status}\n</peer_outcome>"
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
            returned_message = message
            emit(
                session,
                thread.owner_id,
                "message.created",
                thread_id=thread.id,
                agent_id=child.agent_id,
                payload=message_data(message),
            )
            if parent.status == "queued":
                parent.input_seq = max(parent.input_seq, message.seq)
                if parent.execution_state:
                    session.add(SteeringRow(run_id=parent.id, message_id=message.id))
            elif parent.status in {"running", "leased", "waiting_input", "waiting_takeover"}:
                session.add(SteeringRow(run_id=parent.id, message_id=message.id))
                if parent.status == "waiting_input":
                    parent.status = "queued"
            elif parent.status == "completed" and child.status != "cancelled":
                await create_run(
                    session,
                    thread.owner_id,
                    RunRequest(
                        thread_id=thread.id,
                        agent_id=parent.agent_id,
                        trigger="follow_up",
                        prompt="Use the returned peer outcome to complete the owner's request.",
                        metadata={"depth": parent.model_metadata.get("depth", 0)},
                    ),
                )
        from lonora_db.collaboration import record_outcome

        await record_outcome(session, child, returned_message)
        peer = await session.get(PeerMessageRow, child.id, with_for_update=True)
        if peer:
            prior_ids = peer.payload.get("source_outcome_message_ids", [])
            identifiers = (
                [value for value in cast(list[Any], prior_ids) if isinstance(value, str)]
                if isinstance(prior_ids, list)
                else []
            )
            if returned_message:
                identifiers.append(returned_message.id)
            peer.payload = {
                **peer.payload,
                "status": child.status,
                "result": child.result or "",
                "error_code": child.error_code,
                "source_outcome_message_id": returned_message.id if returned_message else None,
                "source_outcome_message_ids": identifiers[-64:],
                "target_outcome_message_id": child.model_metadata.get("result_message_id"),
            }
            peer.version += 1
            peer.updated_at = utcnow()
            for thread_id in {peer.thread_id, peer.payload.get("source_thread_id")}:
                if isinstance(thread_id, str):
                    emit(
                        session,
                        peer.owner_id,
                        "peer_messages.updated",
                        thread_id=thread_id,
                        agent_id=child.agent_id,
                        run_id=child.id,
                        payload={"id": peer.id, "version": peer.version},
                    )
        session.add(EffectReceiptRow(key=receipt, result={"returned": True}))
        if legacy:
            legacy.result = {"returned": True, "fence": child.lease_fence}
        else:
            session.add(
                EffectReceiptRow(
                    key="outcome:" + run_id, result={"returned": True, "fence": child.lease_fence}
                )
            )


async def return_pending_outcomes(db: Database, limit: int = 20) -> int:
    """Repair the commit/return crash window and cancelled queued children, at most 20 per tick."""
    receipt = literal("outcome:") + RunRow.id + literal(":") + sql_cast(RunRow.lease_fence, String)
    async with db.sessions() as session:
        identifiers = list(
            await session.scalars(
                select(RunRow.id)
                .where(
                    RunRow.status.in_(["completed", "failed", "cancelled"]),
                    or_(RunRow.parent_run_id.is_not(None), RunRow.trigger == "tickets"),
                    ~exists(select(EffectReceiptRow.key).where(EffectReceiptRow.key == receipt)),
                )
                .order_by(RunRow.updated_at, RunRow.id)
                .limit(min(max(limit, 1), 20))
            )
        )
    for identifier in identifiers:
        await return_outcome(db, identifier)
    return len(identifiers)
