from typing import Any

from lonora_contracts.domain import MessageCreate
from lonora_core.group_mentions import mentions
from lonora_core.message_replies import require_same_thread
from lonora_core.run_state import is_conversational
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import (
    AgentRow,
    ArtifactRow,
    EffectReceiptRow,
    GroupRow,
    MessageRow,
    RunRow,
    SteeringRow,
)
from .transactions import owned_agent, owned_thread


def message_data(row: MessageRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "thread_id": row.thread_id,
        "agent_id": row.agent_id,
        "seq": row.seq,
        "role": row.role,
        "content": row.content,
        "reply_to": row.reply_to,
        "mentions": row.mentions,
        "attachment_ids": row.attachment_ids,
        "created_at": row.created_at.isoformat(),
    }


async def history(
    session: AsyncSession,
    owner_id: str,
    thread_id: str,
    limit: int = 100,
    before: int | None = None,
) -> list[MessageRow]:
    await owned_thread(session, owner_id, thread_id)
    query = select(MessageRow).where(MessageRow.thread_id == thread_id)
    if before:
        query = query.where(MessageRow.seq < before)
    rows = list(
        (await session.scalars(query.order_by(MessageRow.seq.desc()).limit(min(limit, 200)))).all()
    )
    return list(reversed(rows))


async def send_message(
    session: AsyncSession, owner_id: str, thread_id: str, request: MessageCreate
) -> dict[str, Any]:
    thread = await owned_thread(session, owner_id, thread_id, lock=True)
    existing = await session.scalar(
        select(MessageRow).where(
            MessageRow.thread_id == thread_id, MessageRow.client_nonce == request.client_nonce
        )
    )
    if existing:
        receipt = await session.get(EffectReceiptRow, "message:" + existing.id)
        if receipt is None:
            # Backfill older messages using their steering link or creation interval.
            # A later turn must never be returned as this message's original run.
            run_ids = list(
                await session.scalars(
                    select(SteeringRow.run_id).where(SteeringRow.message_id == existing.id)
                )
            )
            next_message = await session.scalar(
                select(MessageRow)
                .where(
                    MessageRow.thread_id == thread_id,
                    MessageRow.seq > existing.seq,
                    MessageRow.role == "user",
                )
                .order_by(MessageRow.seq)
                .limit(1)
            )
            created = select(RunRow.id).where(
                RunRow.thread_id == thread_id,
                RunRow.created_at >= existing.created_at,
                RunRow.trigger.in_(["user", "group"]),
            )
            if next_message:
                created = created.where(RunRow.created_at < next_message.created_at)
            run_ids = list(dict.fromkeys(run_ids + list(await session.scalars(created))))
            receipt = EffectReceiptRow(key="message:" + existing.id, result={"run_ids": run_ids})
            session.add(receipt)
        return {
            "message": message_data(existing),
            "run_ids": receipt.result.get("run_ids", []),
            "deduplicated": True,
        }
    for mentioned_id in request.mention_agent_ids:
        await owned_agent(session, owner_id, mentioned_id)
    collaboration = None
    if request.mention_all or request.collaboration_session_id:
        from .collaboration import CollaborationRepository, current_session

        collaboration = (
            await CollaborationRepository().get(session, owner_id, request.collaboration_session_id)
            if request.collaboration_session_id
            else await current_session(session, owner_id, thread_id)
        )
        if collaboration and (
            collaboration.thread_id != thread_id or collaboration.agent_id != thread.agent_id
        ):
            raise LonoraError("collaboration_thread_mismatch", 409)
        if collaboration is None:
            raise LonoraError("collaboration_session_required", 409)
    reply = None
    if request.reply_to:
        reply = await session.get(MessageRow, request.reply_to)
        if reply is None:
            raise LonoraError("reply_not_found", 404)
        require_same_thread(thread_id, reply.thread_id)
    for artifact_id in request.attachment_ids:
        artifact = await session.get(ArtifactRow, artifact_id)
        if artifact is None or artifact.owner_id != owner_id:
            raise LonoraError("artifact_not_found", 404)
    message = MessageRow(
        thread_id=thread_id,
        seq=thread.next_seq,
        role="user",
        **request.model_dump(
            exclude={"client_nonce", "mention_agent_ids", "mention_all", "collaboration_session_id"}
        ),
        mentions={
            "agent_ids": list(dict.fromkeys(request.mention_agent_ids)),
            "all": request.mention_all,
            "session_id": collaboration.id if collaboration else None,
        },
        client_nonce=request.client_nonce,
    )
    # reply_to/attachment_ids are part of the message; no model or provider is selected here.
    thread.next_seq += 1
    if not thread.title:
        thread.title = request.content[:80]
    session.add(message)
    await session.flush()
    targets: list[str] = []
    if thread.agent_id:
        targets = [thread.agent_id]
    elif thread.group_id:
        group = await session.get(GroupRow, thread.group_id)
        if group:
            member_ids = list(group.payload.get("member_ids", []))
            agents = list(
                (
                    await session.scalars(
                        select(AgentRow).where(
                            AgentRow.id.in_(member_ids), AgentRow.owner_id == owner_id
                        )
                    )
                ).all()
            )
            explicit = set(request.mention_agent_ids)
            if explicit and not explicit.issubset({a.id for a in agents}):
                raise LonoraError("agent_not_group_member", 409)
            targets = (
                [a.id for a in agents if a.id in explicit]
                if explicit
                else mentions(request.content, {a.id: a.name for a in agents})
            )
            if not targets and request.reply_to and reply and reply.agent_id:
                targets = [a.id for a in agents if a.id == reply.agent_id]
            if not targets:
                available = {a.id for a in agents if not a.paused}
                for member_id in member_ids:
                    if member_id in available:
                        targets = [member_id]
                        break
    run_ids: list[str] = []
    for agent_id in targets:
        agent = await owned_agent(session, owner_id, agent_id)
        if agent.paused:
            continue
        active = await session.scalar(
            select(RunRow)
            .where(
                RunRow.thread_id == thread_id,
                RunRow.agent_id == agent_id,
                RunRow.status.in_(["queued", "leased", "running", "waiting_input"]),
            )
            .order_by(RunRow.created_at)
            .limit(1)
        )
        if active and is_conversational(active.trigger):
            if active.status == "queued":
                active.input_seq = message.seq
                if active.execution_state:
                    # A queued continuation restores its checkpoint instead of rebuilding history.
                    session.add(SteeringRow(run_id=active.id, message_id=message.id))
            else:
                session.add(SteeringRow(run_id=active.id, message_id=message.id))
                if active.status == "waiting_input":
                    active.status = "queued"
            run_ids.append(active.id)
        else:
            run = RunRow(
                thread_id=thread_id,
                agent_id=agent_id,
                input_seq=message.seq,
                trigger="group" if thread.group_id else "user",
            )
            session.add(run)
            await session.flush()
            run_ids.append(run.id)
            emit(
                session,
                owner_id,
                "run.queued",
                thread_id=thread_id,
                agent_id=agent_id,
                run_id=run.id,
            )
    if thread.agent_id and (request.mention_agent_ids or request.mention_all):
        from .collaboration import invite

        participant_ids = list(request.mention_agent_ids)
        if collaboration:
            participant_ids.extend(
                p["agent_id"] for p in collaboration.state.get("participants", [])
            )
        participant_ids = [
            identifier
            for identifier in dict.fromkeys(participant_ids)
            if identifier != thread.agent_id
        ]
        if participant_ids and run_ids:
            host_run = await session.get(RunRow, run_ids[0])
            assert host_run is not None
            await invite(
                session,
                owner_id,
                thread,
                host_run,
                participant_ids,
                request.content,
                message_id=message.id,
                session_id=collaboration.id if collaboration else None,
            )
    session.add(EffectReceiptRow(key="message:" + message.id, result={"run_ids": run_ids}))
    emit(session, owner_id, "message.created", thread_id=thread_id, payload=message_data(message))
    return {"message": message_data(message), "run_ids": run_ids, "deduplicated": False}
