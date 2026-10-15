"""Sessions coordinate existing peer runs; they never host a second executor."""

from typing import Any

from lonora_contracts.collaboration import (
    CollaborationParticipant,
    CollaborationRound,
    CollaborationState,
)
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_security.collaboration import require_collaboration
from lonora_session.idempotency import stable_id
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .peer_messages import PeerMessageRepository
from .runs import create_run
from .schema import CollaborationSessionRow, MessageRow, RunRow, ThreadRow
from .threads import conversation_thread
from .transactions import ResourceRepository, owned_agent, owned_thread, resource_data


class CollaborationRepository(ResourceRepository):
    row_type = CollaborationSessionRow
    kind = "collaboration_sessions"


async def current_session(session: AsyncSession, owner_id: str, thread_id: str):
    return await session.scalar(
        select(CollaborationSessionRow)
        .where(
            CollaborationSessionRow.owner_id == owner_id,
            CollaborationSessionRow.thread_id == thread_id,
            CollaborationSessionRow.state["status"]
            .as_string()
            .in_(["collaborating", "synthesizing"]),
        )
        .order_by(CollaborationSessionRow.created_at.desc())
        .limit(1)
    )


async def invite(
    session: AsyncSession,
    owner_id: str,
    thread: ThreadRow,
    host_run: RunRow,
    participant_ids: list[str],
    subject: str,
    *,
    session_id: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Caller holds host thread lock; stable request ids make replay a no-op."""
    if not thread.agent_id or thread.agent_id != host_run.agent_id:
        raise LonoraError("collaboration_host_required", 409)
    ids = list(dict.fromkeys(participant_ids))
    ids = [identifier for identifier in ids if identifier != thread.agent_id]
    if not ids or len(ids) > 16:
        raise LonoraError("collaboration_participants_required", 422)
    ancestor: RunRow | None = host_run
    seen: set[str] = set()
    while ancestor:
        if ancestor.id in seen or len(seen) >= 4:
            raise LonoraError("delegation_depth_exceeded", 409)
        seen.add(ancestor.id)
        if ancestor.agent_id in ids:
            raise LonoraError("peer_cycle", 409)
        ancestor = (
            await session.get(RunRow, ancestor.parent_run_id) if ancestor.parent_run_id else None
        )
    targets = [await owned_agent(session, owner_id, identifier) for identifier in ids]
    if any(target.paused for target in targets):
        raise LonoraError("agent_paused", 409)
    request_id = message_id or host_run.id
    identifier = session_id or stable_id(host_run.id, "collaboration:" + request_id)
    row = await session.get(CollaborationSessionRow, identifier, with_for_update=True)
    if session_id and row is None:
        raise LonoraError("collaboration_sessions_not_found", 404)
    if row and row.owner_id != owner_id:
        raise LonoraError("collaboration_sessions_not_found", 404)
    if row and (row.thread_id != thread.id or row.agent_id != thread.agent_id):
        raise LonoraError("collaboration_thread_mismatch", 409)
    if row is None:
        row = await CollaborationRepository().create(
            session,
            owner_id,
            {"subject": subject, "host_run_id": host_run.id, "origin_request_id": request_id},
            agent_id=thread.agent_id,
            thread_id=thread.id,
            resource_id=identifier,
        )
        row.state = CollaborationState().model_dump(mode="json")
    state = CollaborationState.model_validate(row.state)
    if state.status in {"completed", "cancelled"}:
        raise LonoraError("collaboration_closed", 409)
    round_id = stable_id(row.id, "round:" + host_run.id + ":" + request_id)
    round = next((item for item in state.rounds if item.id == round_id), None)
    if round is not None:
        expected_ids = {
            stable_id(row.id, "participant:" + round_id + ":" + target.id) for target in targets
        }
        if round.subject != subject or set(round.participant_run_ids) != expected_ids:
            raise LonoraError("collaboration_intent_conflict", 409)
        return resource_data(row)
    if len(state.rounds) >= 8:
        raise LonoraError("collaboration_round_limit", 409)
    round = CollaborationRound(
        id=round_id, request_id=request_id, host_run_id=host_run.id, subject=subject
    )
    state.rounds.append(round)
    for target in targets:
        participant = next((p for p in state.participants if p.agent_id == target.id), None)
        if participant is None:
            if len(state.participants) >= 16:
                raise LonoraError("collaboration_participant_limit", 409)
            participant = CollaborationParticipant(agent_id=target.id)
            state.participants.append(participant)
        run_id = stable_id(row.id, "participant:" + round_id + ":" + target.id)
        existing = await session.get(RunRow, run_id)
        if existing:
            if existing.prompt != subject or existing.agent_id != target.id:
                raise LonoraError("collaboration_intent_conflict", 409)
            continue
        if len(participant.run_ids) >= 64:
            raise LonoraError("collaboration_round_limit", 409)
        target_thread = await conversation_thread(session, owner_id, target.id)
        require_collaboration(owner_id, target.owner_id, len(seen) - 1)
        try:
            # Message admission already holds the host thread. A reciprocal
            # invitation must fail recoverably, never wait in a lock cycle.
            async with session.begin_nested():
                await session.execute(
                    select(ThreadRow.id)
                    .where(ThreadRow.id == target_thread.id)
                    .with_for_update(nowait=True)
                )
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) == "55P03":
                raise LonoraError("collaboration_participant_busy", 409) from None
            raise
        request_message = MessageRow(
            thread_id=target_thread.id,
            agent_id=thread.agent_id,
            role="assistant",
            seq=target_thread.next_seq,
            content=subject,
            client_nonce="peer:" + run_id + ":target",
        )
        target_thread.next_seq += 1
        session.add(request_message)
        await session.flush()
        await create_run(
            session,
            owner_id,
            RunRequest(
                thread_id=target_thread.id,
                agent_id=target.id,
                trigger="peer",
                prompt=subject,
                parent_run_id=host_run.id,
                metadata={
                    "collaboration_session_id": row.id,
                    "collaboration_round_id": round_id,
                    "peer_message_id": run_id,
                    "return_thread_id": thread.id,
                    "return_agent_id": thread.agent_id,
                    "depth": min(int(host_run.model_metadata.get("depth", 0)) + 1, 4),
                },
            ),
            run_id,
        )
        source = await owned_agent(session, owner_id, thread.agent_id)
        await PeerMessageRepository().create(
            session,
            owner_id,
            {
                "requester_run_id": host_run.id,
                "run_id": run_id,
                "task": subject,
                "source_agent_id": source.id,
                "source_agent_name": source.name,
                "target_agent_id": target.id,
                "target_agent_name": target.name,
                "source_thread_id": thread.id,
                "target_thread_id": target_thread.id,
                "source_message_id": message_id,
                "target_message_id": request_message.id,
                "status": "queued",
                "collaboration_session_id": row.id,
            },
            agent_id=target.id,
            thread_id=target_thread.id,
            resource_id=run_id,
        )
        participant.run_ids.append(run_id)
        round.participant_run_ids.append(run_id)
        participant.status = "working"
        participant.result, participant.error_code = "", None
        participant.source_message_id, participant.observed_at = None, None
        participant.source_thread_id = target_thread.id
    state.status = "collaborating"
    row.state = state.model_dump(mode="json")
    row.version += 1
    row.updated_at = utcnow()
    emit(
        session,
        owner_id,
        "collaboration.updated",
        thread_id=thread.id,
        agent_id=thread.agent_id,
        payload={"id": row.id, "version": row.version},
    )
    return resource_data(row)


async def record_outcome(session: AsyncSession, child: RunRow, message: MessageRow | None):
    session_id = child.model_metadata.get("collaboration_session_id")
    if not isinstance(session_id, str):
        return
    row = await session.get(CollaborationSessionRow, session_id, with_for_update=True)
    if row is None:
        return
    origin = await owned_thread(session, row.owner_id, child.thread_id)
    if origin.agent_id != child.agent_id:
        raise LonoraError("collaboration_participant_mismatch", 409)
    state = CollaborationState.model_validate(row.state)
    participant = next((p for p in state.participants if child.id in p.run_ids), None)
    if participant is None or state.status == "cancelled" or participant.run_ids[-1] != child.id:
        return
    if child.status == "completed":
        participant.status = "completed"
    elif child.status == "cancelled":
        participant.status = "cancelled"
    else:
        participant.status = "failed"
    participant.result = (child.result or "")[:30000]
    participant.error_code = child.error_code
    participant.source_message_id = message.id if message else None
    participant.observed_at = utcnow().isoformat()
    if all(p.status in {"completed", "failed", "cancelled"} for p in state.participants):
        state.status = "synthesizing"
    row.state = state.model_dump(mode="json")
    row.version += 1
    row.updated_at = utcnow()
    emit(
        session,
        row.owner_id,
        "collaboration.updated",
        thread_id=row.thread_id,
        agent_id=row.agent_id,
        payload={"id": row.id, "version": row.version},
    )


async def schedule_synthesis(
    session: AsyncSession, child: RunRow, host: RunRow, thread: ThreadRow
) -> None:
    """One durable synthesis identity per round, serialized by the host thread.

    Collect every terminal participant before scheduling; a running host already
    consumes the attributed outcomes through steering and needs no extra run.
    """
    identifier = child.model_metadata.get("collaboration_session_id")
    if not isinstance(identifier, str):
        return
    row = await session.get(CollaborationSessionRow, identifier, with_for_update=True)
    if row is None or row.owner_id != thread.owner_id or row.thread_id != thread.id:
        raise LonoraError("collaboration_thread_mismatch", 409)
    state = CollaborationState.model_validate(row.state)
    if state.status in {"completed", "cancelled"}:
        return
    round = next((r for r in state.rounds if child.id in r.participant_run_ids), None)
    if round is None:
        # Existing pre-round sessions are upgraded from their persisted child lineage.
        children = list(
            await session.scalars(
                select(RunRow).where(
                    RunRow.parent_run_id == host.id,
                    RunRow.model_metadata["collaboration_session_id"].as_string() == row.id,
                )
            )
        )
        round = CollaborationRound(
            id=stable_id(row.id, "legacy:" + host.id),
            request_id=host.id,
            host_run_id=host.id,
            subject=str(row.payload.get("subject", "")),
            participant_run_ids=[run.id for run in children][:16],
        )
        if len(state.rounds) >= 8:
            raise LonoraError("collaboration_round_limit", 409)
        state.rounds.append(round)
    if round.synthesis_run_id:
        return
    participants = list(
        await session.scalars(select(RunRow).where(RunRow.id.in_(round.participant_run_ids)))
    )
    # Terminal state alone is insufficient: every outcome must have been delivered
    # into this host thread, including when several children complete concurrently.
    delivered = all(
        [
            await session.get(
                MessageRow, run.model_metadata.get("collaboration_return_message_id", "")
            )
            for run in participants
        ]
    )
    if not participants or len(participants) != len(round.participant_run_ids) or not delivered:
        return
    if any(run.status not in {"completed", "failed", "cancelled"} for run in participants):
        return
    if host.status in {"queued", "running", "leased", "waiting_input", "waiting_takeover"}:
        round.synthesis_run_id = host.id
    elif host.status == "completed":
        run_id = stable_id(row.id, "synthesis:" + round.id)
        existing = await session.get(RunRow, run_id)
        if existing is None:
            await create_run(
                session,
                row.owner_id,
                RunRequest(
                    thread_id=thread.id,
                    agent_id=host.agent_id,
                    trigger="follow_up",
                    parent_run_id=host.id,
                    prompt="Inspect the durable collaboration session and synthesize the available participant evidence for this round. Do not transfer permissions or invent missing evidence.",
                    metadata={
                        "collaboration_session_id": row.id,
                        "collaboration_round_id": round.id,
                        "collaboration_synthesis": True,
                        "depth": host.model_metadata.get("depth", 0),
                    },
                ),
                run_id,
            )
        round.synthesis_run_id = run_id
    else:
        return
    row.state = state.model_dump(mode="json")
    row.version += 1
    row.updated_at = utcnow()
    emit(
        session,
        row.owner_id,
        "collaboration.synthesis_scheduled",
        thread_id=thread.id,
        agent_id=host.agent_id,
        run_id=round.synthesis_run_id,
        payload={"id": row.id, "round_id": round.id, "run_id": round.synthesis_run_id},
    )
