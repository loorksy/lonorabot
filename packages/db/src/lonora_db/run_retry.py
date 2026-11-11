"""Retry of a failed conversational reply (Q22): the error card's «إعادة المحاولة».

The retry is a new Run with the same input: the same owner message (``input_seq``), the
same responder agent and trigger, in the same conversation. It re-runs a reply only:
a Run that reserved, sent or asked approval for a financial operation is never retried,
whatever that operation's outcome, so a retry can never repeat a trade. One failed Run
has at most one retry (a stable id), so a second request returns the same new Run.
"""

from datetime import timedelta
from math import ceil

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import stable_id
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .events import emit
from .runs import aware, failure_data, run_data
from .schema import MessageRow, RunRow, ThreadRow, TradeApprovalRow, TradingJournalRow
from .transactions import owned_agent, owned_thread
from .voice_provenance import carry_voice_handoff

# Replies to the owner's own message in a conversation or a group.
RETRYABLE_TRIGGERS = frozenset({"user", "group"})


# How long after it failed a reply is still answered on its own once a model is connected.
UNCONFIGURED_RETRY_WINDOW = timedelta(hours=48)


class RunRetryTooEarly(LonoraError):
    """The provider asked to wait (Retry-After) and the wait has not elapsed."""

    def __init__(self, seconds: int):
        super().__init__("run_retry_too_early", 409)
        self.retry_after_seconds = seconds


async def descendants(session: AsyncSession, run_id: str) -> list[str]:
    """Every run this one started: peers, collaboration, subagents (``parent_run_id``) and
    Tasks or tickets (``started_by_run_id``), to any depth."""
    found: list[str] = []
    frontier = [run_id]
    for _ in range(16):
        if not frontier:
            break
        children = list(
            await session.scalars(
                select(RunRow.id).where(
                    or_(
                        RunRow.parent_run_id.in_(frontier),
                        RunRow.model_metadata["started_by_run_id"].as_string().in_(frontier),
                    )
                )
            )
        )
        children = [child for child in children if child not in found and child != run_id]
        found.extend(children)
        frontier = children
    return found


async def financial_effect(session: AsyncSession, run_id: str) -> bool:
    """Whether the Run touched the executor: any journal operation or trade approval."""
    operation = await session.scalar(
        select(TradingJournalRow.operation_id)
        .where(
            or_(
                TradingJournalRow.result["details"]["execution"]["run_id"].as_string() == run_id,
                TradingJournalRow.result["details"]["lease"]["run_id"].as_string() == run_id,
            )
        )
        .limit(1)
    )
    approval = await session.scalar(
        select(TradeApprovalRow.id).where(TradeApprovalRow.run_id == run_id).limit(1)
    )
    return operation is not None or approval is not None


async def retry_run(session: AsyncSession, owner_id: str, run_id: str) -> RunRow:
    candidate = await session.get(RunRow, run_id)
    if candidate is None:
        raise LonoraError("run_not_found", 404)
    # Thread before Run: the lock order of message admission and claiming.
    thread = await owned_thread(session, owner_id, candidate.thread_id, lock=True)
    row = await session.get(RunRow, run_id, with_for_update=True, populate_existing=True)
    assert row is not None
    retry_id = stable_id(row.id, "run-retry")
    existing = await session.get(RunRow, retry_id)
    if existing is not None:
        return existing
    if (
        row.status != "failed"
        or row.trigger not in RETRYABLE_TRIGGERS
        or row.parent_run_id
        or row.model_metadata.get("task_id")
        or await financial_effect(session, row.id)
    ):
        raise LonoraError("run_not_retryable", 409)
    # A reply that started other work (a peer, a collaboration, a subagent, a Task) is no
    # longer a plain reply: that work may have reserved, sent or asked approval for money,
    # or still be running. Retrying could repeat it, so it is never retried.
    if await descendants(session, row.id):
        raise LonoraError("run_not_retryable", 409)
    # Edit-and-resend replaced the owner's message: the old request must not run again.
    source = await session.scalar(
        select(MessageRow.id).where(
            MessageRow.thread_id == row.thread_id,
            MessageRow.seq == row.input_seq,
            MessageRow.role == "user",
        )
    )
    if source is not None and await session.scalar(
        select(MessageRow.id).where(MessageRow.edited_from == source).limit(1)
    ):
        raise LonoraError("run_not_retryable", 409)
    failure = failure_data(row) or {}
    wait = failure.get("retry_after_seconds")
    if wait:
        remaining = (aware(row.updated_at) + timedelta(seconds=wait) - utcnow()).total_seconds()
        if remaining > 0:
            raise RunRetryTooEarly(ceil(remaining))
    agent = await owned_agent(session, owner_id, row.agent_id)
    if agent.paused:
        raise LonoraError("agent_paused", 409)
    retry = RunRow(
        id=retry_id,
        thread_id=thread.id,
        agent_id=agent.id,
        trigger=row.trigger,
        prompt=row.prompt,
        input_seq=row.input_seq,
        model_metadata={"retry_of": row.id},
    )
    # A spoken request stays provisional in its retry (it needs its own approval card), and a
    # later spoken correction withdraws the retry's approvals too.
    await carry_voice_handoff(session, row, retry)
    session.add(retry)
    await session.flush()
    emit(
        session,
        owner_id,
        "run.queued",
        thread_id=thread.id,
        agent_id=agent.id,
        run_id=retry.id,
        payload={"run": run_data(retry), "retry_of": row.id},
    )
    return retry


async def retry_unconfigured(session: AsyncSession, owner_id: str) -> list[RunRow]:
    """Queue again every reply that failed only because no model was configured.

    Called when the owner connects a provider or chooses a model. Each failed message
    gets its retry, oldest first, so a conversation is answered in the order it was
    written (a worker claims a conversation's Runs oldest first); the owner does not
    have to find and tap every card. The same rules as the owner's own retry apply
    (``retry_run``), and a reply that cannot be retried is left as it is. A failure the
    conversation has moved past (a later message there was answered or is being
    answered) stays history, and so does an old one: an instruction from days ago is
    not carried out today because a key was saved.
    """
    later = aliased(RunRow)
    moved_on = (
        select(later.id)
        .where(
            later.thread_id == RunRow.thread_id,
            later.input_seq > RunRow.input_seq,
            later.status.not_in(["failed", "cancelled"]),
            later.trigger.in_(RETRYABLE_TRIGGERS),
        )
        .exists()
    )
    failed = list(
        await session.scalars(
            select(RunRow)
            .join(ThreadRow, ThreadRow.id == RunRow.thread_id)
            .where(
                ThreadRow.owner_id == owner_id,
                RunRow.status == "failed",
                RunRow.error_code == "model_not_configured",
                RunRow.trigger.in_(RETRYABLE_TRIGGERS),
                RunRow.created_at >= utcnow() - UNCONFIGURED_RETRY_WINDOW,
                ~moved_on,
            )
            .order_by(RunRow.input_seq, RunRow.created_at)
        )
    )
    retried: list[RunRow] = []
    for row in failed:
        if await session.get(RunRow, stable_id(row.id, "run-retry")) is not None:
            continue
        try:
            retried.append(await retry_run(session, owner_id, row.id))
        except LonoraError:
            continue
    return retried
