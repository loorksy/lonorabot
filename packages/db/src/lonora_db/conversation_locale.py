"""Bounded language evidence from canonical owner messages, not work prompts."""

import re
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import MessageRow
from .transactions import SettingsRepository, owned_thread


async def conversation_locale(
    session: AsyncSession, owner_id: str, thread_id: str
) -> Literal["ar", "en"]:
    await owned_thread(session, owner_id, thread_id)
    messages = await session.scalars(
        select(MessageRow.content)
        .where(MessageRow.thread_id == thread_id, MessageRow.role == "user")
        .order_by(MessageRow.seq.desc())
        .limit(16)
    )
    for content in messages:
        text = content[:1600]
        if re.search(r"[\u0620-\u064a]", text):
            return "ar"
        # Ignore bare identifiers and short button labels such as Approve.
        if " " in text and len(re.findall(r"[A-Za-z]", text)) >= 8:
            return "en"
    preferences = await SettingsRepository().get(session, "attention-policy:" + owner_id)
    return "en" if preferences.get("locale") == "en" else "ar"
