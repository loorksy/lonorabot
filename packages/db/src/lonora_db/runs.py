from datetime import UTC, datetime, timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease, RunRequest
from lonora_core.run_state import assert_transition
from lonora_core.user_error import LonoraError
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import AgentRow, GroupRow, MessageRow, RunRow, SteeringRow, ThreadRow
from .transactions import owned_agent, owned_thread


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def run_data(row: RunRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "thread_id": row.thread_id,
        "agent_id": row.agent_id,
        "parent_run_id": row.parent_run_id,
        "status": row.status,
        "trigger": row.trigger,
        "error_code": row.error_code,
        "result": row.result,
        "model_metadata": row.model_metadata,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


async def create_run(
    session: AsyncSession, owner_id: str, request: RunRequest, run_id: str | None = None
) -> RunRow:
    thread = await owned_thread(session, owner_id, request.thread_id, lock=True)
    agent = await owned_agent(session, owner_id, request.agent_id)
    if thread.agent_id and thread.agent_id != agent.id:
        raise LonoraError("agent_thread_mismatch", 409)
    if thread.group_id:
        group = await session.get(GroupRow, thread.group_id)
        if group is None or agent.id not in group.payload.get("member_ids", []):
            raise LonoraError("agent_not_group_member", 409)
    if request.parent_run_id:
        parent = await session.get(RunRow, request.parent_run_id)
        if parent is None:
            raise LonoraError("parent_run_not_found", 404)
        await owned_thread(session, owner_id, parent.thread_id)
    if agent.paused:
        raise LonoraError("agent_paused", 409)
    row = RunRow(
        thread_id=thread.id,
        agent_id=agent.id,
        trigger=request.trigger,
        prompt=request.prompt,
        parent_run_id=request.parent_run_id,
        input_seq=thread.next_seq - 1,
        model_metadata=request.metadata,
    )
    if run_id:
        row.id = run_id
    session.add(row)
    await session.flush()
    emit(session, owner_id, "run.queued", thread_id=thread.id, agent_id=agent.id, run_id=row.id)
    return row


async def claim_next(session: AsyncSession, worker_id: str, lease_seconds: int) -> RunRow | None:
    now = utcnow()
    eligible = or_(
        RunRow.status == "queued",
        and_(RunRow.status.in_(["leased", "running"]), RunRow.lease_expires_at <= now),
    )
    active = exists(
        select(RunRow.id).where(
            RunRow.thread_id == ThreadRow.id,
            RunRow.status.in_(["leased", "running"]),
            RunRow.lease_expires_at > now,
        )
    )
    pending = exists(
        select(RunRow.id)
        .join(AgentRow, AgentRow.id == RunRow.agent_id)
        .where(RunRow.thread_id == ThreadRow.id, eligible, AgentRow.paused.is_(False))
    )
    # Claim the thread lock first so two queued turns cannot be claimed simultaneously.
    thread = await session.scalar(
        select(ThreadRow)
        .where(pending, ~active)
        .order_by(ThreadRow.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if thread is None:
        return None
    row = await session.scalar(
        select(RunRow)
        .join(AgentRow, AgentRow.id == RunRow.agent_id)
        .where(RunRow.thread_id == thread.id, eligible, AgentRow.paused.is_(False))
        .order_by(RunRow.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if row is None:
        return None
    recovered = row.status != "queued"
    if thread.group_id and not row.execution_state:
        row.input_seq = max(row.input_seq, thread.next_seq - 1)
    row.status = "leased"
    row.lease_owner = worker_id
    row.lease_fence += 1
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.updated_at = now
    row.error_code = None
    emit(
        session,
        thread.owner_id,
        "run.recovered" if recovered else "run.leased",
        thread_id=row.thread_id,
        agent_id=row.agent_id,
        run_id=row.id,
        payload={"fence": row.lease_fence},
    )
    await session.flush()
    return row


async def require_lease(session: AsyncSession, lease: Lease, lock: bool = False) -> RunRow:
    query = select(RunRow).where(RunRow.id == lease.run_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if (
        row is None
        or row.status not in {"leased", "running"}
        or row.lease_owner != lease.owner
        or row.lease_fence != lease.fence
        or row.lease_expires_at is None
        or aware(row.lease_expires_at) <= utcnow()
    ):
        raise LonoraError("stale_lease", 409)
    return row


async def renew_lease(session: AsyncSession, lease: Lease, lease_seconds: int) -> None:
    row = await require_lease(session, lease, lock=True)
    row.lease_expires_at = utcnow() + timedelta(seconds=lease_seconds)


async def checkpoint(session: AsyncSession, lease: Lease, state: dict[str, Any]) -> None:
    row = await require_lease(session, lease, lock=True)
    row.execution_state = state
    row.updated_at = utcnow()


async def complete_run(
    session: AsyncSession, lease: Lease, answer: str, metadata: dict[str, Any]
) -> bool:
    row = await require_lease(session, lease, lock=True)
    thread = await session.get(ThreadRow, row.thread_id, with_for_update=True)
    if thread is None:
        raise LonoraError("thread_not_found", 404)
    outstanding = await session.scalar(
        select(SteeringRow.id)
        .where(SteeringRow.run_id == row.id, SteeringRow.consumed.is_(False))
        .limit(1)
    )
    if outstanding:
        return False
    assert_transition(row.status, "completed")
    if answer and row.trigger != "tickets":
        message = MessageRow(
            thread_id=thread.id,
            agent_id=row.agent_id,
            role="assistant",
            seq=thread.next_seq,
            content=answer,
        )
        thread.next_seq += 1
        session.add(message)
        await session.flush()
        from .messages import message_data

        emit(
            session,
            thread.owner_id,
            "message.created",
            thread_id=thread.id,
            agent_id=row.agent_id,
            run_id=row.id,
            payload=message_data(message),
        )
    row.status = "completed"
    row.result = answer
    row.model_metadata = {**row.model_metadata, **metadata}
    row.updated_at = utcnow()
    row.lease_expires_at = None
    emit(
        session,
        thread.owner_id,
        "run.completed",
        thread_id=thread.id,
        agent_id=row.agent_id,
        run_id=row.id,
    )
    return True


async def fail_run(session: AsyncSession, lease: Lease, code: str) -> None:
    row = await require_lease(session, lease, lock=True)
    row.status = "failed"
    row.error_code = code
    row.updated_at = utcnow()
    row.lease_expires_at = None
    thread = await session.get(ThreadRow, row.thread_id)
    if thread:
        emit(
            session,
            thread.owner_id,
            "run.failed",
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            run_id=row.id,
            payload={"code": code},
        )
