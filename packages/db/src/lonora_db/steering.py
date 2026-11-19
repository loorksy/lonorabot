from lonora_contracts.runs import Lease
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .runs import require_lease
from .schema import MessageRow, SteeringRow


async def user_interrupt_pending(session: AsyncSession, run_id: str) -> bool:
    # Peer and subagent outcomes are assistant messages. They wake the run, but only a
    # later user message withdraws an approved order that has not been sent.
    return (
        await session.scalar(
            select(SteeringRow.id)
            .join(MessageRow, MessageRow.id == SteeringRow.message_id)
            .where(
                SteeringRow.run_id == run_id,
                SteeringRow.consumed.is_(False),
                MessageRow.role == "user",
            )
            .limit(1)
        )
    ) is not None


async def consume_steering(session: AsyncSession, lease: Lease) -> list[MessageRow]:
    run = await require_lease(session, lease, lock=True)
    pending = list(
        (
            await session.scalars(
                select(SteeringRow)
                .where(SteeringRow.run_id == run.id, SteeringRow.consumed.is_(False))
                .with_for_update()
            )
        ).all()
    )
    messages: list[MessageRow] = []
    for steering in pending:
        message = await session.get(MessageRow, steering.message_id)
        if message:
            messages.append(message)
        steering.consumed = True
    messages.sort(key=lambda message: message.seq)
    # Only the run's own thread moves its history window; an owner's answer from the
    # conversation a background run reports to has that conversation's numbering.
    own = [message.seq for message in messages if message.thread_id == run.thread_id]
    if own:
        run.input_seq = max(run.input_seq, max(own))
    return messages
