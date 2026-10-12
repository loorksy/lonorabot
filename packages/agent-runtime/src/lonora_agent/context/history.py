from lonora_adapter_kit.types import ModelMessage
from lonora_db.schema import AgentRow, MessageRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def history_context(
    session: AsyncSession,
    thread_id: str,
    input_seq: int,
    summary_seq: int = 0,
    agent_id: str | None = None,
) -> list[ModelMessage]:
    rows = (
        await session.scalars(
            select(MessageRow)
            .where(
                MessageRow.thread_id == thread_id,
                MessageRow.seq <= input_seq,
                MessageRow.seq > summary_seq,
                MessageRow.role.in_(["user", "assistant"]),
            )
            .order_by(MessageRow.seq.desc())
            .limit(100)
        )
    ).all()
    names = {
        agent.id: agent.name
        for agent in (
            await session.scalars(
                select(AgentRow).where(
                    AgentRow.id.in_([row.agent_id for row in rows if row.agent_id])
                )
            )
        ).all()
    }
    messages: list[ModelMessage] = []
    for row in reversed(rows):
        peer = bool(agent_id and row.agent_id and row.agent_id != agent_id)
        content = (
            "[Peer " + names.get(row.agent_id or "", row.agent_id or "") + "]\n" + row.content
            if peer
            else row.content
        )
        messages.append(
            ModelMessage(
                role="user" if row.role == "user" or peer else "assistant", content=content
            )
        )
    return messages
