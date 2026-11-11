from datetime import datetime, timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import stable_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import AgentRow, RunRow, TradeApprovalRow
from .transactions import owned_thread
from .voice_provenance import carry_voice_handoff

# How long an approval card can be approved (Q32): a lifetime between 30 and 60 minutes.
# Past it a pending card settles as expired when next read or decided (no scheduler) and
# «طلب جديد» asks the agent again; it never becomes approvable by itself.
MINIMUM_APPROVAL_LIFETIME = timedelta(minutes=30)
MAXIMUM_APPROVAL_LIFETIME = timedelta(minutes=60)
APPROVAL_LIFETIME = timedelta(minutes=45)
# The run «طلب جديد» starts: fixed server text (lonora_agent.context.routine).
RENEW_TRIGGER = "owner_card"


def approval_expiry(created_at: datetime, requested: datetime | None = None) -> datetime:
    """When a new approval stops being approvable: ``requested`` when it lies inside the
    lifetime range, clamped to it otherwise, else the default lifetime."""
    if requested is None:
        return created_at + APPROVAL_LIFETIME
    return min(
        max(requested, created_at + MINIMUM_APPROVAL_LIFETIME),
        created_at + MAXIMUM_APPROVAL_LIFETIME,
    )


def overdue(row: TradeApprovalRow, now: datetime | None = None) -> bool:
    """A pending approval past its expiry (older rows have none and never expire)."""
    return (
        row.status == "pending"
        and row.expires_at is not None
        and row.expires_at <= (now or utcnow())
    )


def approval_data(row: TradeApprovalRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "thread_id": row.thread_id,
        "agent_id": row.agent_id,
        "timeline_seq": row.timeline_seq,
        "requests": row.requests,
        # Read lazily: a pending card past its expiry is shown expired before it settles.
        "status": "expired" if overdue(row) else row.status,
        "results": row.results,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat(),
    }


def approval_event(session: AsyncSession, row: TradeApprovalRow) -> None:
    emit(
        session,
        row.owner_id,
        "trading.approval.updated",
        thread_id=row.thread_id,
        agent_id=row.agent_id,
        run_id=row.run_id,
        payload=approval_data(row),
    )


async def locked_approval(
    session: AsyncSession, owner_id: str, approval_id: str
) -> tuple[TradeApprovalRow, RunRow | None]:
    """The owner's approval and its run, locked in the order a decision takes them."""
    candidate = await session.get(TradeApprovalRow, approval_id)
    if candidate is None or candidate.owner_id != owner_id:
        raise LonoraError("trade_approval_not_found", 404)
    # An approval whose conversation was deleted can no longer be decided.
    await owned_thread(session, owner_id, candidate.thread_id or "", lock=True)
    run = await session.scalar(
        select(RunRow).where(RunRow.id == candidate.run_id).with_for_update()
    )
    row = await session.scalar(
        select(TradeApprovalRow)
        .where(TradeApprovalRow.id == approval_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row, run


def wake_waiting_run(session: AsyncSession, row: TradeApprovalRow, run: RunRow | None) -> None:
    """The run waiting on this card continues: its trade call reads the outcome."""
    if run is not None and run.status == "waiting_input":
        run.status = "queued"
        run.updated_at = utcnow()
        emit(
            session,
            row.owner_id,
            "run.queued",
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            run_id=run.id,
        )


async def expire_if_due(session: AsyncSession, row: TradeApprovalRow) -> bool:
    """Settle a pending approval past its expiry as expired (once), with the usual
    update event; the run waiting on it continues and learns it expired. The caller
    holds the locks ``locked_approval`` takes."""
    if not overdue(row):
        return False
    run = await session.get(RunRow, row.run_id) if row.run_id else None
    row.status, row.updated_at = "expired", utcnow()
    wake_waiting_run(session, row, run)
    approval_event(session, row)
    return True


async def settle_if_expired(session: AsyncSession, owner_id: str, approval_id: str) -> bool:
    """Lazily settle one approval: True when it is (now) expired."""
    row, _ = await locked_approval(session, owner_id, approval_id)
    await expire_if_due(session, row)
    return row.status == "expired"


async def decide(
    session: AsyncSession, owner_id: str, approval_id: str, decision: str
) -> dict[str, Any]:
    row, run = await locked_approval(session, owner_id, approval_id)
    desired = "approved" if decision == "approve" else "rejected"
    if row.status == "expired" or overdue(row):
        # Never approvable once its lifetime ended; «طلب جديد» asks the agent again.
        raise LonoraError("trade_approval_expired", 409)
    if row.status != "pending":
        if row.status != desired and not (decision == "approve" and row.status == "completed"):
            raise LonoraError("trade_approval_already_decided", 409)
        return approval_data(row)
    if run is None or run.status not in {"waiting_input", "running", "leased", "queued"}:
        raise LonoraError("trade_approval_run_unavailable", 409)
    pending_calls = run.execution_state.get("pending", [])
    if run.execution_state and not any(call.get("id") == row.call_id for call in pending_calls):
        raise LonoraError("trade_approval_run_unavailable", 409)
    row.status, row.updated_at = desired, utcnow()
    wake_waiting_run(session, row, run)
    approval_event(session, row)
    return approval_data(row)


def renew_prompt(row: TradeApprovalRow) -> str:
    """Fixed text and the server's own identifier only: nothing a model wrote."""
    return (
        "The owner tapped New request on your expired approval card (approval_id="
        f"{row.id}). Nothing was approved or sent. Re-check the market, the account and "
        "your reasons now with fresh data. If the trade still makes sense, request it again "
        "with trade_execute so a new approval card is raised through the normal path; "
        "otherwise tell the owner in one line why not."
    )


async def renew_approval(session: AsyncSession, owner_id: str, approval_id: str) -> RunRow:
    """«طلب جديد» on an expired approval: one conversational run of the same agent in the
    same conversation asks it again. It creates no approval and approves nothing: the
    agent re-validates and raises a new card through the normal path. Repeating the tap
    returns the same run."""
    from lonora_contracts.runs import RunRequest

    from .runs import create_run

    row, _ = await locked_approval(session, owner_id, approval_id)
    await expire_if_due(session, row)
    if row.status != "expired":
        raise LonoraError("trade_approval_not_renewable", 409)
    run_id = stable_id(row.id, "renew-approval")
    existing = await session.get(RunRow, run_id)
    if existing is not None:
        return existing
    agent = await session.get(AgentRow, row.agent_id)
    if agent is None or agent.owner_id != owner_id or row.thread_id is None:
        raise LonoraError("trade_approval_not_renewable", 409)
    run = await create_run(
        session,
        owner_id,
        RunRequest(
            thread_id=row.thread_id,
            agent_id=agent.id,
            trigger=RENEW_TRIGGER,
            prompt=renew_prompt(row),
            metadata={"renews_trade_approval_id": row.id},
        ),
        run_id,
    )
    # A spoken request stays provisional when it is asked again (its own approval card), and
    # a later spoken correction withdraws the new run's approvals too.
    source = await session.get(RunRow, row.run_id)
    if source is not None:
        await carry_voice_handoff(session, source, run)
        await session.flush()
    return run


async def require_approved_target_current(
    session: AsyncSession,
    owner_id: str,
    run_id: str,
    request: TradeRequest,
    observed: dict[str, Any] | None,
) -> None:
    target_id = request.position_id or request.order_id
    if not target_id:
        return
    key = request.account_id + (":position:" if request.position_id else ":order:") + target_id
    approvals = await session.scalars(
        select(TradeApprovalRow).where(
            TradeApprovalRow.owner_id == owner_id,
            TradeApprovalRow.run_id == run_id,
            TradeApprovalRow.status == "approved",
        )
    )
    for approval in approvals:
        if (
            any(item.get("operation_id") == request.operation_id for item in approval.requests)
            and key in approval.broker_snapshot
        ):
            if approval.broker_snapshot[key] != observed:
                raise LonoraError("trade_approval_broker_state_changed", 409)
