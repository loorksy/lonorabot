import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import SecretRow
from .transactions import SettingsRepository

# What a model_provider Secret card saved, as one record: the secret it wrote and, for an
# OpenAI-compatible endpoint, the base URL that key belongs to. The router reads the key
# by this id, never by a workspace name, so a secret an agent or a script saved under
# OPENAI_API_KEY is not the router's key.
CONNECTION_SETTING = "model_provider:"
# A provider connected by the owner's sign-in keeps one JSON credential in scope
# ``provider`` under its id (``lonora_providers.chatgpt_sign_in``). The scan of workspace
# output (VISION 7.2.6) knows each of its tokens as a value of its own.
SIGN_IN_CREDENTIALS = frozenset({"openai_chatgpt"})
SIGN_IN_TOKENS = ("access_token", "refresh_token", "id_token")


def sign_in_tokens(name: str, value: str) -> dict[str, str]:
    """The tokens of a sign-in credential, each under ``name:field``."""
    try:
        record: Any = json.loads(value)
    except ValueError:
        return {}
    if not isinstance(record, dict):
        return {}
    fields = cast(dict[str, Any], record)
    return {
        name + ":" + field: token
        for field in SIGN_IN_TOKENS
        if isinstance(token := fields.get(field), str) and token
    }


@dataclass(frozen=True)
class SavedKey:
    secret_id: str
    # The card's base URL; None for a fixed provider and for a key saved before cards.
    url: str | None
    # When that secret was last written: a rotation keeps the id and changes this.
    updated_at: datetime


async def saved_key(session: AsyncSession, provider: str) -> SavedKey | None:
    """The provider's key the owner saved last, on a Secret card or before cards existed
    (scope ``provider``), with the URL saved beside it. None: no saved key."""
    card = await SettingsRepository().get(session, CONNECTION_SETTING + provider)
    candidates: list[tuple[SecretRow, str | None]] = []
    if card.get("secret_id"):
        row = await session.get(SecretRow, card["secret_id"])
        if row is not None:
            candidates.append((row, card.get("url")))
    legacy = await session.scalar(
        select(SecretRow).where(SecretRow.scope == "provider", SecretRow.name == provider)
    )
    if legacy is not None:
        candidates.append((legacy, None))
    if not candidates:
        return None
    row, url = max(candidates, key=lambda item: item[0].updated_at)
    return SavedKey(row.id, url, row.updated_at)
