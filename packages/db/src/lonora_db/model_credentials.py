from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import SecretRow
from .secrets import WORKSPACE

# A model provider's key is the owner's workspace secret under the provider's usual
# environment-variable name (Q14 (b)): the router reads it on the server, and a tool an
# agent runs in the workspace finds it under the name that tool expects (12.2).
PROVIDER_KEY_NAMES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "zai": "ZAI_API_KEY",
    "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
}
# The owner's base URL for an OpenAI-compatible endpoint: not a secret, a setting.
ENDPOINT_SETTING = "model_endpoint:"


async def credential_id(session: AsyncSession, provider: str) -> str | None:
    """The provider's key: the workspace secret saved on a Secret card, else a key saved
    before that card existed (scope ``provider``)."""
    name = PROVIDER_KEY_NAMES.get(provider)
    if name is not None:
        row = await session.scalar(
            select(SecretRow).where(SecretRow.scope == WORKSPACE, SecretRow.name == name)
        )
        if row:
            return row.id
    row = await session.scalar(
        select(SecretRow).where(SecretRow.scope == "provider", SecretRow.name == provider)
    )
    return row.id if row else None
