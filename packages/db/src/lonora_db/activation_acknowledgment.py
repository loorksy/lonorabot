"""One truthful, localized confirmation after verified device authorization."""

from lonora_bus.attention import attention_text
from lonora_session.idempotency import stable_id
from sqlalchemy.ext.asyncio import AsyncSession

from .conversation_locale import conversation_locale
from .events import emit
from .messages import message_data
from .schema import EffectReceiptRow, MessageRow, SuperBotRequestRow
from .transactions import owned_thread


def acknowledgment_key(request_id: str) -> str:
    return "activation-ack:" + request_id


async def acknowledge_activation(session: AsyncSession, row: SuperBotRequestRow) -> None:
    if row.status != "activated":
        return
    thread = await owned_thread(session, row.owner_id, row.thread_id, lock=True)
    key = acknowledgment_key(row.id)
    if await session.get(EffectReceiptRow, key):
        return
    locale = await conversation_locale(session, row.owner_id, thread.id)
    mode = "shadow" if row.envelope.get("execution_mode", "live") == "shadow" else row.mode
    message = MessageRow(
        id=stable_id(row.id, "activation-ack"),
        thread_id=thread.id,
        agent_id=row.agent_id,
        seq=thread.next_seq,
        role="assistant",
        content=attention_text("super_bot_activated_" + mode, locale),
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
