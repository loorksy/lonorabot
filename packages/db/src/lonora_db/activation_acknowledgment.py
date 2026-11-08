"""One truthful, localized confirmation in the conversation after a grant is signed.

A grant signed from its card in the chat is confirmed by the card itself; one signed
from the trading-level controls gets this single line from the agent instead.
"""

from lonora_bus.attention import attention_text
from lonora_session.idempotency import stable_id
from sqlalchemy.ext.asyncio import AsyncSession

from .conversation_locale import conversation_locale
from .events import emit
from .messages import message_data
from .schema import AccountAuthorityRow, EffectReceiptRow, MessageRow
from .transactions import owned_thread


def acknowledgment_key(grant_id: str) -> str:
    return "activation-ack:" + grant_id


async def acknowledge_grant(session: AsyncSession, row: AccountAuthorityRow) -> None:
    if row.status != "active" or row.thread_id is None:
        return
    thread = await owned_thread(session, row.owner_id, row.thread_id, lock=True)
    key = acknowledgment_key(row.id)
    if await session.get(EffectReceiptRow, key):
        return
    locale = await conversation_locale(session, row.owner_id, thread.id)
    message = MessageRow(
        id=stable_id(row.id, "activation-ack"),
        thread_id=thread.id,
        agent_id=row.agent_id,
        seq=thread.next_seq,
        role="assistant",
        content=attention_text("grant_activated", locale),
    )
    thread.next_seq += 1
    session.add(message)
    await session.flush()
    session.add(EffectReceiptRow(key=key, result={"message_id": message.id, "locale": locale}))
    emit(
        session,
        row.owner_id,
        "message.created",
        thread_id=thread.id,
        agent_id=row.agent_id,
        payload=message_data(message),
    )
