from lonora_contracts.model_routing import PROVIDER_KEY_NAMES
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import SecretRow
from .secrets import WORKSPACE

# The owner's base URL for an OpenAI-compatible endpoint: not a secret, a setting.
ENDPOINT_SETTING = "model_endpoint:"


async def credential_id(session: AsyncSession, provider: str) -> str | None:
    """The provider's key the owner saved last: on a Secret card (the workspace secret
    under its usual name) or before cards existed (scope ``provider``)."""
    saved = [(SecretRow.scope == "provider") & (SecretRow.name == provider)]
    name = PROVIDER_KEY_NAMES.get(provider)
    if name is not None:
        saved.append((SecretRow.scope == WORKSPACE) & (SecretRow.name == name))
    row = await session.scalar(
        select(SecretRow).where(or_(*saved)).order_by(SecretRow.updated_at.desc()).limit(1)
    )
    return row.id if row else None
