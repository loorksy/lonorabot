from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .schema import SecretRow
from .transactions import SettingsRepository

# What a model_provider Secret card saved, as one record: the secret it wrote and, for an
# OpenAI-compatible endpoint, the base URL that key belongs to. The router reads the key
# by this id, never by a workspace name, so a secret an agent or a script saved under
# OPENAI_API_KEY is not the router's key.
CONNECTION_SETTING = "model_provider:"


@dataclass(frozen=True)
class SavedKey:
    secret_id: str
    # The card's base URL; None for a fixed provider.
    url: str | None
    # When that secret was last written: a rotation keeps the id and changes this.
    updated_at: datetime


async def saved_key(session: AsyncSession, provider: str) -> SavedKey | None:
    """The provider's key the owner saved on a Secret card, with the URL saved beside it.
    None: no saved key (or its secret was deleted)."""
    card = await SettingsRepository().get(session, CONNECTION_SETTING + provider)
    row = await session.get(SecretRow, card["secret_id"]) if card.get("secret_id") else None
    if row is None:
        return None
    return SavedKey(row.id, card.get("url"), row.updated_at)
