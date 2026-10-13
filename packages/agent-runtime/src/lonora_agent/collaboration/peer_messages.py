from typing import Any

from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.events import emit
from lonora_db.messages import message_data
from lonora_db.peer_messages import PeerMessageRepository
from lonora_db.runs import create_run, require_lease, run_data
from lonora_db.schema import MessageRow, RunRow, ThreadRow
from lonora_db.threads import conversation_thread
from lonora_db.transactions import owned_agent
from lonora_security.collaboration import require_collaboration
from lonora_tools.context import ToolContext
from sqlalchemy import select


async def delegate_peer(context: ToolContext, agent_id: str, task: str) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        parent = await require_lease(session, context.lease)
        existing = await session.get(RunRow, context.resource_id)
        if existing:
            if (
                existing.agent_id != agent_id
                or existing.prompt != task
                or existing.parent_run_id != parent.id
            ):
                raise LonoraError("peer_intent_conflict", 409)
            return run_data(existing)
        if agent_id == context.agent_id:
            raise LonoraError("peer_self_target", 409)
        ancestor: RunRow | None = parent
        seen: set[str] = set()
        while ancestor:
            if ancestor.id in seen or ancestor.agent_id == agent_id:
                raise LonoraError("peer_cycle", 409)
            seen.add(ancestor.id)
            if len(seen) > 32:
                raise LonoraError("delegation_depth_exceeded", 409)
            ancestor = (
                await session.get(RunRow, ancestor.parent_run_id)
                if ancestor.parent_run_id
                else None
            )
        target = await owned_agent(session, context.owner_id, agent_id)
        require_collaboration(context.owner_id, target.owner_id, max(context.depth, len(seen) - 1))
        thread = await conversation_thread(session, context.owner_id, agent_id)
        # Requests write both conversations. Always lock their rows in one global order,
        # then fence the parent run, so reciprocal independent requests cannot deadlock.
        locked: dict[str, ThreadRow] = {}
        for thread_id in sorted({context.thread_id, thread.id}):
            row = await session.scalar(
                select(ThreadRow)
                .where(ThreadRow.id == thread_id, ThreadRow.owner_id == context.owner_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if row is None:
                raise LonoraError("thread_not_found", 404)
            locked[thread_id] = row
        await require_lease(session, context.lease, lock=True)
        existing = await session.get(RunRow, context.resource_id, populate_existing=True)
        if existing:
            if (
                existing.agent_id != agent_id
                or existing.prompt != task
                or existing.parent_run_id != parent.id
            ):
                raise LonoraError("peer_intent_conflict", 409)
            return run_data(existing)
        source = await owned_agent(session, context.owner_id, context.agent_id)
        request_messages: dict[str, MessageRow] = {}
        for side, thread_id in (("source", context.thread_id), ("target", thread.id)):
            conversation = locked[thread_id]
            message = MessageRow(
                thread_id=thread_id,
                agent_id=context.agent_id,
                role="assistant",
                seq=conversation.next_seq,
                content=task,
                client_nonce=f"peer:{context.resource_id}:{side}",
            )
            conversation.next_seq += 1
            session.add(message)
            await session.flush()
            request_messages[side] = message
            emit(
                session,
                context.owner_id,
                "message.created",
                thread_id=thread_id,
                agent_id=context.agent_id,
                payload=message_data(message),
            )
        run = await create_run(
            session,
            context.owner_id,
            RunRequest(
                thread_id=thread.id,
                agent_id=agent_id,
                trigger="peer",
                prompt=task,
                parent_run_id=context.lease.run_id,
                metadata={
                    "depth": context.depth + 1,
                    "return_thread_id": context.thread_id,
                    "return_agent_id": context.agent_id,
                    "peer_message_id": context.resource_id,
                },
            ),
            context.resource_id,
        )
        await PeerMessageRepository().create(
            session,
            context.owner_id,
            {
                "requester_run_id": context.lease.run_id,
                "run_id": run.id,
                "task": task,
                "source_agent_id": source.id,
                "source_agent_name": source.name,
                "target_agent_id": target.id,
                "target_agent_name": target.name,
                "source_thread_id": context.thread_id,
                "target_thread_id": thread.id,
                "source_message_id": request_messages["source"].id,
                "target_message_id": request_messages["target"].id,
                "status": "queued",
            },
            agent_id=agent_id,
            thread_id=thread.id,
            resource_id=context.resource_id,
        )
        emit(
            session,
            context.owner_id,
            "peer.requested",
            thread_id=context.thread_id,
            agent_id=context.agent_id,
            run_id=context.lease.run_id,
            payload={"id": context.resource_id, "target_agent_id": target.id},
        )
        return run_data(run)
