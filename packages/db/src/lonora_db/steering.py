from lonora_contracts.runs import Lease
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .runs import require_lease
from .schema import MessageRow, SteeringRow


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
    if messages:
        run.input_seq = max(run.input_seq, messages[-1].seq)
    return messages
