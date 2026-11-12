"""Each agent's own `lonora` CLI token (mandate 7.3.3).

Lonora issues every agent one token. The CLI endpoint maps a presented token to exactly
one agent; deleting the agent deletes its row (``ON DELETE CASCADE``), which revokes it.
"""

import hashlib
import secrets

from lonora_core.user_error import LonoraError
from lonora_security.secrets import SecretCipher
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentCliTokenRow, AgentRow

# 32 random bytes; the prefix only makes a leaked token recognizable in a scan.
TOKEN_PREFIX = "lnr_"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def cli_token(session: AsyncSession, key: str, owner_id: str, agent_id: str) -> str:
    """The agent's token, issued on first use. The same value every time, so commands
    started earlier (background processes included) keep working."""
    row = await session.get(AgentCliTokenRow, agent_id)
    cipher = SecretCipher(key)
    if row is not None and row.owner_id == owner_id:
        return cipher.decrypt(row.ciphertext)
    agent = await session.get(AgentRow, agent_id)
    if agent is None or agent.owner_id != owner_id:
        raise LonoraError("agent_not_found", 404)
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    session.add(
        AgentCliTokenRow(
            agent_id=agent_id,
            owner_id=owner_id,
            token_hash=token_hash(token),
            ciphertext=cipher.encrypt(token),
        )
    )
    await session.flush()
    return token


async def revoke_cli_token(session: AsyncSession, agent_id: str) -> None:
    """Revoke the agent's token now. Deleting the agent row does the same by cascade."""
    await session.execute(delete(AgentCliTokenRow).where(AgentCliTokenRow.agent_id == agent_id))


async def agent_for_cli_token(session: AsyncSession, token: str) -> AgentRow | None:
    """The one agent a token names, or None for any token Lonora did not issue."""
    if not token.startswith(TOKEN_PREFIX) or len(token) > 128:
        return None
    return await session.scalar(
        select(AgentRow)
        .join(AgentCliTokenRow, AgentCliTokenRow.agent_id == AgentRow.id)
        .where(
            AgentCliTokenRow.token_hash == token_hash(token),
            AgentCliTokenRow.owner_id == AgentRow.owner_id,
        )
    )
