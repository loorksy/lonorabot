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

from .events import emit
from .runs import aware, failure_data, run_data
from .schema import RunRow, TradeApprovalRow, TradingJournalRow
from .transactions import owned_agent, owned_thread

# Replies to the owner's own message in a conversation or a group.
RETRYABLE_TRIGGERS = frozenset({"user", "group"})


class RunRetryTooEarly(LonoraError):
    """The provider asked to wait (Retry-After) and the wait has not elapsed."""

    def __init__(self, seconds: int):
        super().__init__("run_retry_too_early", 409)
        self.retry_after_seconds = seconds


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
        model_metadata={
            "retry_of": row.id,
            **({"execution_mode": "shadow"} if agent.execution_mode == "shadow" else {}),
        },
    )
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
